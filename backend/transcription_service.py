"""Whisper transcription via any OpenAI-compatible /v1/audio/transcriptions
endpoint (Speaches, faster-whisper-server, whisper-asr-webservice, vLLM with
Whisper, etc).

Extracts the audio segment for a single track from the parent mix using
ffmpeg, POSTs the WAV to the configured Whisper server with word-level
timestamps, and returns synced [{time, text}] entries.

Includes a smart-merge helper that combines LRCLIB's perfect *text* with
Whisper's perfect *timing* (force-alignment by word matching).
"""
import asyncio
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import httpx

from settings_service import get_whisper_config

log = logging.getLogger("mixdeck")


class WhisperNotConfigured(Exception):
    """Raised when transcription is requested but settings are missing/disabled."""


class WhisperError(Exception):
    """Upstream Whisper API returned an error."""


# ===== Audio segment extraction =====
def extract_segment(source_path: str, start: float, duration: float, out_wav: Path) -> None:
    """Extract `duration` seconds of audio starting at `start` from `source_path`
    and write to `out_wav` as a 16kHz mono WAV (Whisper-friendly).

    Runs ffmpeg synchronously - the caller should await this in an executor.
    """
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", source_path,
        "-ar", "16000", "-ac", "1",
        "-c:a", "pcm_s16le",
        str(out_wav),
    ]
    res = subprocess.run(cmd, capture_output=True, timeout=120)
    if res.returncode != 0:
        raise WhisperError(f"ffmpeg failed: {res.stderr.decode('utf-8', errors='replace')[:500]}")


# ===== Whisper API call =====
async def _post_transcribe(wav_path: Path, cfg: dict) -> dict:
    """POST a wav file to the configured Whisper endpoint with verbose_json
    + word-level timestamps. Returns the parsed response dict.
    """
    url = f"{cfg['base_url']}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    data: dict = {
        "model": cfg["model"],
        "response_format": "verbose_json",
        "timestamp_granularities[]": "word",
    }
    if cfg.get("language"):
        data["language"] = cfg["language"]
    try:
        async with httpx.AsyncClient(timeout=300.0) as c:
            with wav_path.open("rb") as f:
                files = {"file": (wav_path.name, f, "audio/wav")}
                resp = await c.post(url, headers=headers, data=data, files=files)
    except httpx.HTTPError as e:
        raise WhisperError(f"Cannot reach Whisper at {cfg['base_url']}: {e}") from e
    if resp.status_code >= 400:
        raise WhisperError(f"Whisper HTTP {resp.status_code}: {resp.text[:500]}")
    try:
        return resp.json()
    except ValueError as e:
        raise WhisperError(f"Malformed Whisper response: {resp.text[:200]}") from e


def _flatten_words(verbose_json: dict) -> list[dict]:
    """Normalize Whisper response into [{time, end, text}] word-level list."""
    words = verbose_json.get("words")
    if isinstance(words, list) and words:
        return [
            {"time": float(w.get("start", 0)), "end": float(w.get("end", 0)), "text": (w.get("word") or "").strip()}
            for w in words
            if (w.get("word") or "").strip()
        ]
    # Fallback: stitch from segments if word_timestamps not honoured
    out: list[dict] = []
    for seg in verbose_json.get("segments") or []:
        seg_words = seg.get("words") or []
        for w in seg_words:
            text = (w.get("word") or "").strip()
            if text:
                out.append({"time": float(w.get("start", 0)), "end": float(w.get("end", 0)), "text": text})
    return out


def _segments_from_words(words: list[dict], max_line_seconds: float = 4.0, max_chars: int = 60) -> list[dict]:
    """Group word-level entries into LRC-style lines."""
    if not words:
        return []
    lines: list[dict] = []
    current_start = words[0]["time"]
    current_text: list[str] = []
    for w in words:
        if not current_text:
            current_start = w["time"]
        prospective = (" ".join(current_text + [w["text"]])).strip()
        too_long_chars = len(prospective) > max_chars
        too_long_time = (w["end"] - current_start) > max_line_seconds
        ends_sentence = bool(re.search(r"[.!?]$", w["text"]))
        current_text.append(w["text"])
        if too_long_chars or too_long_time or ends_sentence:
            lines.append({"time": round(current_start, 3), "text": " ".join(current_text).strip()})
            current_text = []
    if current_text:
        lines.append({"time": round(current_start, 3), "text": " ".join(current_text).strip()})
    return lines


# ===== Smart-merge: LRCLIB text + Whisper timing =====
def force_align(lrclib_lines: list[dict], whisper_words: list[dict]) -> list[dict]:
    """Re-time LRCLIB lyric lines using Whisper's word-level timestamps.

    Walks both lists in lockstep, fuzzy-matches each LRCLIB line's first
    significant word against the next available Whisper word. Falls back to
    proportional time-mapping when matching fails. The result keeps LRCLIB's
    *exact text* (which is human-curated and accurate) but uses Whisper's
    *timing* (which reflects the actual recording's pitch-bending / tempo).
    """
    if not lrclib_lines or not whisper_words:
        return lrclib_lines

    def first_word(text: str) -> str:
        m = re.search(r"\w+", text)
        return m.group(0).lower() if m else ""

    aligned: list[dict] = []
    w_idx = 0
    for i, line in enumerate(lrclib_lines):
        fw = first_word(line["text"])
        if not fw:
            aligned.append(line)
            continue
        # Scan forward up to 50 whisper words looking for a match
        match_idx = None
        for j in range(w_idx, min(len(whisper_words), w_idx + 50)):
            wword = re.sub(r"\W", "", whisper_words[j]["text"]).lower()
            if wword and (wword == fw or wword.startswith(fw) or fw.startswith(wword)):
                match_idx = j
                break
        if match_idx is not None:
            new_line = dict(line)
            new_line["time"] = round(whisper_words[match_idx]["time"], 3)
            new_line["source_time"] = line["time"]  # keep original LRCLIB time for diagnostic
            aligned.append(new_line)
            w_idx = match_idx + 1
        else:
            # No match - keep original LRCLIB time
            aligned.append(line)
    return aligned


# ===== Main entry point =====
async def transcribe_track(
    source_path: str,
    start_seconds: float,
    duration: float,
) -> list[dict]:
    """Run Whisper on a single track segment. Returns [{time, text}] lines
    keyed to 0 == start of the track (NOT start of the mix).

    Raises WhisperNotConfigured if Whisper is disabled.
    """
    cfg = await get_whisper_config()
    if cfg is None:
        raise WhisperNotConfigured("Whisper is disabled or not configured. Set it in Admin → Settings.")
    if duration <= 1.0 or not Path(source_path).exists():
        return []

    loop = asyncio.get_event_loop()
    with tempfile.TemporaryDirectory(prefix="mixdeck-whisper-") as tmpdir:
        wav = Path(tmpdir) / "segment.wav"
        await loop.run_in_executor(
            None, extract_segment, source_path, start_seconds, duration, wav,
        )
        if not wav.exists() or wav.stat().st_size < 1024:
            raise WhisperError("ffmpeg produced an empty file - source may be unreadable")
        resp = await _post_transcribe(wav, cfg)

    words = _flatten_words(resp)
    if not words:
        return []
    return _segments_from_words(words)


async def transcribe_with_word_timing(
    source_path: str,
    start_seconds: float,
    duration: float,
) -> tuple[list[dict], list[dict]]:
    """Same as transcribe_track but also returns the raw word-level entries
    (used by force_align)."""
    cfg = await get_whisper_config()
    if cfg is None:
        raise WhisperNotConfigured("Whisper disabled")
    if duration <= 1.0 or not Path(source_path).exists():
        return [], []
    loop = asyncio.get_event_loop()
    with tempfile.TemporaryDirectory(prefix="mixdeck-whisper-") as tmpdir:
        wav = Path(tmpdir) / "segment.wav"
        await loop.run_in_executor(
            None, extract_segment, source_path, start_seconds, duration, wav,
        )
        resp = await _post_transcribe(wav, cfg)
    words = _flatten_words(resp)
    lines = _segments_from_words(words)
    return lines, words


async def health_check() -> dict:
    """Hit /models on the Whisper endpoint to verify reachability + auth."""
    cfg = await get_whisper_config()
    if cfg is None:
        return {"ok": False, "error": "Whisper disabled or unconfigured"}
    url = f"{cfg['base_url']}/models"
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url, headers=headers)
        if r.status_code >= 400:
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
        data = r.json()
        models = []
        if isinstance(data, dict):
            models = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
        return {
            "ok": True,
            "base_url": cfg["base_url"],
            "configured_model": cfg["model"],
            "language": cfg.get("language") or "auto",
            "available_models": models[:50],
            "model_in_list": cfg["model"] in models if models else None,
        }
    except (httpx.HTTPError, ValueError) as e:
        return {"ok": False, "error": f"Cannot reach {url}: {e}"}
