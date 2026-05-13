"""Background BPM + key analysis for mixes.

Wraps `audio_analysis` (librosa) calls behind a global semaphore so bulk
scans don't thrash the server. Per-mix re-entrancy guard keeps duplicates
out of the queue.
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from audio_analysis import read_audio_info, analyze_segment
from cache import cache
from state import db, AUDIO_DIR
from lyrics_service import lookup_lyrics
import transcription_service

_analysis_locks: dict[str, asyncio.Task] = {}
_ANALYSIS_CONCURRENCY = int(os.environ.get("ANALYSIS_CONCURRENCY", "2"))
_analysis_semaphore: Optional[asyncio.Semaphore] = None

log = logging.getLogger("mixdeck")


def _get_analysis_semaphore() -> asyncio.Semaphore:
    global _analysis_semaphore
    if _analysis_semaphore is None:
        _analysis_semaphore = asyncio.Semaphore(_ANALYSIS_CONCURRENCY)
    return _analysis_semaphore


def active_workers() -> int:
    """Return the count of currently in-flight analysis tasks."""
    return len(_analysis_locks)


def is_running(mix_id: str) -> bool:
    return mix_id in _analysis_locks


async def _run_mix_analysis(mix_id: str) -> None:
    sem = _get_analysis_semaphore()
    async with sem:
        await _run_mix_analysis_inner(mix_id)


async def _run_mix_analysis_inner(mix_id: str) -> None:
    loop = asyncio.get_event_loop()
    try:
        await db.mixes.update_one({"id": mix_id}, {"$set": {"analysis_status": "running"}})
        doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
        if not doc:
            return
        src = doc.get("source_path") or (
            str(AUDIO_DIR / doc["audio_filename"]) if doc.get("audio_filename") else None
        )
        if not src or not Path(src).exists():
            await db.mixes.update_one({"id": mix_id}, {"$set": {"analysis_status": "failed"}})
            return

        # 1) Fast metadata via mutagen
        info = await loop.run_in_executor(None, read_audio_info, src)
        updates: dict = {}
        dur = info.get("duration") or 0.0
        if dur and dur > 0:
            updates["duration"] = dur
        if info.get("bpm_tag") and not doc.get("bpm"):
            updates["bpm"] = info["bpm_tag"]
        if info.get("genre_tag") and not doc.get("genre"):
            updates["genre"] = info["genre_tag"]

        tracks = doc.get("tracks") or []
        duration = updates.get("duration", doc.get("duration") or 0.0)

        if not tracks:
            # No cue sheet - just analyze the middle of the mix
            start = max(0.0, (duration or 60.0) * 0.4)
            res = await loop.run_in_executor(None, analyze_segment, src, start, 60.0)
            if res.get("bpm"):
                updates["bpm"] = res["bpm"]
            if res.get("key"):
                updates["key"] = res["key"]
                updates["camelot"] = res.get("camelot")
            if updates:
                await db.mixes.update_one({"id": mix_id}, {"$set": updates})
            await db.mixes.update_one({"id": mix_id}, {"$set": {"analysis_status": "done"}})
            await cache.invalidate_mixes()
            return

        # 2) Per-track analysis - analyze a 45s window from each track
        analyzed: list[dict] = []
        for i, t in enumerate(tracks):
            start = float(t.get("start_seconds") or 0.0)
            next_start = (
                float(tracks[i + 1]["start_seconds"]) if i + 1 < len(tracks) else (duration or start + 60)
            )
            window = min(45.0, max(20.0, next_start - start - 2.0))
            if window < 15:
                analyzed.append(t)
                continue
            offset = start + 8.0
            res = await loop.run_in_executor(None, analyze_segment, src, offset, window)
            t_new = dict(t)
            if res.get("bpm"):
                t_new["bpm"] = res["bpm"]
            if res.get("key"):
                t_new["key"] = res["key"]
                t_new["camelot"] = res.get("camelot")
            analyzed.append(t_new)
            if (i + 1) % 5 == 0:
                await db.mixes.update_one(
                    {"id": mix_id},
                    {"$set": {"tracks": analyzed + tracks[i + 1:], "analysis_status": "running"}},
                )

        bpms = [x["bpm"] for x in analyzed if x.get("bpm")]
        if bpms and not updates.get("bpm") and not doc.get("bpm"):
            updates["bpm"] = int(sorted(bpms)[len(bpms) // 2])

        await db.mixes.update_one(
            {"id": mix_id},
            {"$set": {**updates, "tracks": analyzed, "analysis_status": "done"}},
        )
        await cache.invalidate_mixes()

        # 3) Optional Whisper transcription per track (smart-merged with LRCLIB)
        # Runs only if the admin enabled it in Settings. Failures are isolated
        # per-track so one bad audio segment doesn't fail the whole analyze run.
        await _maybe_transcribe_tracks(mix_id, src, analyzed, duration)
    except Exception as e:
        log.exception("Analysis failed for %s: %s", mix_id, e)
        await db.mixes.update_one({"id": mix_id}, {"$set": {"analysis_status": "failed"}})
    finally:
        _analysis_locks.pop(mix_id, None)


def schedule_analysis(mix_id: str) -> None:
    """Queue a mix for background BPM + key analysis (idempotent per mix)."""
    if mix_id in _analysis_locks:
        return
    task = asyncio.create_task(_run_mix_analysis(mix_id))
    _analysis_locks[mix_id] = task


async def _maybe_transcribe_tracks(mix_id: str, src: str, tracks: list[dict], duration: float) -> None:
    """Run Whisper per-track if enabled. Force-aligns with LRCLIB when available.

    Failures are caught per-track so one bad segment doesn't take down the
    whole pass. Persists results to the `track_lyrics` collection keyed by
    artist|title so they're shared across all mixes containing the same track.
    """
    cfg = await transcription_service.get_whisper_config()
    if cfg is None:
        return  # Whisper disabled - nothing to do
    trim = int(cfg.get("transition_trim") or 15)

    log.info("Whisper: starting transcription pass for mix %s (%d tracks, trim=%ds)", mix_id, len(tracks), trim)
    from lyrics_service import _cache_key, parse_lrc  # local import to avoid cycle
    from datetime import datetime, timezone

    for i, t in enumerate(tracks):
        artist = (t.get("artist") or "").strip()
        title = (t.get("title") or "").strip()
        if not (artist or title):
            continue
        start = float(t.get("start_seconds") or 0.0)
        next_start = (
            float(tracks[i + 1]["start_seconds"]) if i + 1 < len(tracks) else (duration or start + 240)
        )
        # Subtract the transition zone (last N seconds of each track blend
        # into the next track in the mix, so Whisper must not transcribe it).
        clean_end = max(start, next_start - trim)
        # Cap segment at 8 minutes - Whisper handles long audio but cost scales
        track_duration = max(0.0, min(clean_end - start, 480.0))
        if track_duration < 5:
            continue
        try:
            # First, see if LRCLIB has it - we'll smart-merge if so
            existing = await lookup_lyrics(artist, title, track_duration)
            lrclib_synced = existing.get("synced") or []
            lines, words = await transcription_service.transcribe_with_word_timing(
                src, start, track_duration
            )
            if not lines:
                log.info("Whisper: no transcription for %s - %s", artist, title)
                continue
            if lrclib_synced:
                # Smart-merge: LRCLIB text + Whisper timing
                merged = transcription_service.force_align(lrclib_synced, words)
                final_synced = merged
                source = "whisper-aligned"
            else:
                final_synced = lines
                source = "whisper"
            key = _cache_key(artist, title, track_duration)
            await db.track_lyrics.update_one(
                {"key": key},
                {"$set": {
                    "key": key,
                    "artist": artist,
                    "title": title,
                    "duration": int(round(track_duration)),
                    "synced": final_synced,
                    "plain": "\n".join(line["text"] for line in final_synced),
                    "source": source,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True,
            )
            log.info("Whisper: %s '%s - %s' (%d lines)", source, artist, title, len(final_synced))
        except (transcription_service.WhisperNotConfigured, transcription_service.WhisperError) as e:
            log.warning("Whisper failed for %s - %s: %s", artist, title, e)
            # Don't abort - keep going for the other tracks
            continue
        except Exception as e:  # noqa: BLE001
            log.exception("Unexpected error transcribing %s - %s: %s", artist, title, e)
            continue
