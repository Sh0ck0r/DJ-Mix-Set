"""Bulk Whisper transcription: AUTO-TRANSCRIBE ALL.

Walks every mix in the library and re-transcribes every track in the
background. For each track it:
  1. Computes the clean audio window (start_seconds to next_start - trim).
  2. Looks up LRCLIB lyrics (used as canonical text if available).
  3. Calls the configured Whisper endpoint for word-level timing.
  4. Force-aligns LRCLIB text with Whisper timing (or uses raw Whisper).
  5. Upserts the result into `track_lyrics`.

Per-mix concurrency is bounded by `WHISPER_BULK_CONCURRENCY` (default 1 -
single GPU). Track-level processing is sequential within a mix to avoid
flooding the local Whisper server.
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cache import cache
from state import db, AUDIO_DIR
from lyrics_service import lookup_lyrics, _cache_key as lyrics_cache_key
import transcription_service
from settings_service import get_whisper_transition_trim

log = logging.getLogger("mixdeck")

_WHISPER_CONCURRENCY = int(os.environ.get("WHISPER_BULK_CONCURRENCY", "1"))

_bulk_tasks: dict[str, dict] = {}


def get_task(task_id: str) -> dict | None:
    return _bulk_tasks.get(task_id)


def list_active() -> list[dict]:
    """All bulk-Whisper tasks (current + recent), newest first."""
    return sorted(
        _bulk_tasks.values(),
        key=lambda t: t.get("started_at") or "",
        reverse=True,
    )


def _resolve_audio_path(mix: dict) -> str | None:
    src = mix.get("source_path")
    if src and Path(src).exists():
        return src
    if mix.get("audio_filename"):
        p = AUDIO_DIR / mix["audio_filename"]
        if p.exists():
            return str(p)
    return None


async def _track_already_done(artist: str, title: str, duration: float) -> bool:
    """Check if a Whisper-sourced lyric entry already exists for this track."""
    key = lyrics_cache_key(artist, title, duration)
    doc = await db.track_lyrics.find_one({"key": key}, {"_id": 0, "source": 1})
    if not doc:
        return False
    src = (doc.get("source") or "").lower()
    return src.startswith("whisper")


async def _process_track(state: dict, mix: dict, src_path: str, i: int, trim: int) -> None:
    tracks = mix.get("tracks") or []
    t = tracks[i]
    artist = (t.get("artist") or "").strip()
    title = (t.get("title") or "").strip()
    if not (artist or title):
        state["skipped_existing"] += 1
        return
    start = float(t.get("start_seconds") or 0.0)
    duration_mix = float(mix.get("duration") or 0)
    next_start = (
        float(tracks[i + 1]["start_seconds"])
        if i + 1 < len(tracks)
        else (duration_mix or start + 240)
    )
    clean_end = max(start, next_start - trim)
    track_duration = max(0.0, min(clean_end - start, 480.0))
    if track_duration < 5:
        state["skipped_existing"] += 1
        return
    if not state.get("force") and await _track_already_done(artist, title, track_duration):
        state["skipped_existing"] += 1
        return

    try:
        lrclib = await lookup_lyrics(artist, title, track_duration)
        lrclib_synced = lrclib.get("synced") or []
        lines, words = await transcription_service.transcribe_with_word_timing(
            src_path, start, track_duration
        )
        if not lines:
            state["failed"] += 1
            state["errors"].append({
                "mix_id": mix["id"], "title": mix.get("title"),
                "track": f"{artist} - {title}", "error": "no transcription returned"
            })
            return
        if lrclib_synced:
            final_synced = transcription_service.force_align(lrclib_synced, words)
            source = "whisper-aligned"
        else:
            final_synced = lines
            source = "whisper"
        key = lyrics_cache_key(artist, title, track_duration)
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
        state["succeeded"] += 1
    except transcription_service.WhisperNotConfigured as e:
        # No point continuing across mixes if Whisper is off
        state["aborted"] = True
        state["error"] = str(e)
        raise
    except transcription_service.WhisperError as e:
        state["failed"] += 1
        state["errors"].append({
            "mix_id": mix["id"], "title": mix.get("title"),
            "track": f"{artist} - {title}", "error": str(e)[:300]
        })
    except Exception as e:  # noqa: BLE001
        log.exception("Bulk Whisper unexpected error: %s", e)
        state["failed"] += 1
        state["errors"].append({
            "mix_id": mix["id"], "title": mix.get("title"),
            "track": f"{artist} - {title}", "error": str(e)[:300]
        })


async def _process_mix(state: dict, mix: dict, trim: int) -> None:
    state["current_mix"] = {"id": mix["id"], "title": mix.get("title") or "Untitled"}
    src_path = _resolve_audio_path(mix)
    tracks = mix.get("tracks") or []
    if not src_path or not tracks:
        # Nothing to do for this mix
        state["mixes_skipped"] += 1
        state["mixes_processed"] += 1
        return
    for i in range(len(tracks)):
        if state.get("aborted"):
            return
        try:
            await _process_track(state, mix, src_path, i, trim)
        except transcription_service.WhisperNotConfigured:
            return
        state["tracks_processed"] += 1
    state["mixes_processed"] += 1


async def _run_bulk(task_id: str, force: bool) -> None:
    state = _bulk_tasks[task_id]
    state["force"] = force
    sem = asyncio.Semaphore(_WHISPER_CONCURRENCY)
    try:
        # Pre-flight: make sure Whisper is configured before kicking off
        cfg = await transcription_service.get_whisper_config()
        if cfg is None:
            state["status"] = "failed"
            state["error"] = "Whisper is disabled or not configured. Set it in Admin → Settings."
            state["finished_at"] = datetime.now(timezone.utc).isoformat()
            return
        trim = await get_whisper_transition_trim()

        projection = {"_id": 0, "id": 1, "title": 1, "artist": 1, "duration": 1,
                      "tracks": 1, "audio_filename": 1, "source_path": 1}
        all_mixes = await db.mixes.find({}, projection).to_list(2000)
        # Only mixes with tracks count as targets
        targets = [m for m in all_mixes if m.get("tracks")]
        state["total"] = len(targets)
        state["tracks_total"] = sum(len(m.get("tracks") or []) for m in targets)
        if not targets:
            state["status"] = "done"
            state["finished_at"] = datetime.now(timezone.utc).isoformat()
            return

        async def worker(mix: dict) -> None:
            async with sem:
                if state.get("aborted"):
                    return
                try:
                    await _process_mix(state, mix, trim)
                except transcription_service.WhisperNotConfigured:
                    pass

        await asyncio.gather(*(worker(m) for m in targets), return_exceptions=False)

        if state.get("aborted"):
            state["status"] = "failed"
            if not state.get("error"):
                state["error"] = "Whisper not configured (check Admin → Settings)"
        elif state["failed"] > 0 and state["succeeded"] == 0:
            state["status"] = "failed"
            last_err = state["errors"][-1]["error"] if state["errors"] else "all tracks failed"
            state["error"] = f"All transcriptions failed — last error: {last_err}"
        else:
            state["status"] = "done"
        state["finished_at"] = datetime.now(timezone.utc).isoformat()
        if state["succeeded"] > 0:
            await cache.invalidate_mixes()
    except Exception as e:  # noqa: BLE001
        log.exception("Bulk Whisper task %s crashed", task_id)
        state["status"] = "failed"
        state["error"] = str(e)
        state["finished_at"] = datetime.now(timezone.utc).isoformat()


def start_bulk(force: bool = False) -> str:
    """Allocate a task_id, kick off the background bulk Whisper run."""
    task_id = str(uuid.uuid4())
    _bulk_tasks[task_id] = {
        "task_id": task_id,
        "kind": "whisper",
        "force": bool(force),
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        # Mix-level counters
        "total": 0,
        "processed": 0,            # alias of mixes_processed for UI compatibility
        "mixes_processed": 0,
        "mixes_skipped": 0,
        # Track-level counters
        "tracks_total": 0,
        "tracks_processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped_existing": 0,
        "current_mix": None,
        "aborted": False,
        "errors": [],
        "error": None,
    }
    # Keep `processed` mirrored to mixes_processed during the run via post-update
    async def runner() -> None:
        s = _bulk_tasks[task_id]
        task = asyncio.create_task(_run_bulk(task_id, force))
        while not task.done():
            s["processed"] = s["mixes_processed"]
            await asyncio.sleep(0.5)
        s["processed"] = s["mixes_processed"]
        try:
            await task
        except Exception:  # already logged inside _run_bulk
            pass
    asyncio.create_task(runner())

    # Cull old finished tasks (keep last 10)
    finished = [(tid, t) for tid, t in _bulk_tasks.items() if t["status"] != "running"]
    if len(finished) > 10:
        finished.sort(key=lambda x: x[1].get("finished_at") or "")
        for tid, _ in finished[: len(finished) - 10]:
            _bulk_tasks.pop(tid, None)
    return task_id
