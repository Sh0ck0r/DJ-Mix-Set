"""Audio analysis for MIXDECK - BPM + musical key detection with librosa.

Called as a background task after scan. Extracts per-track BPM + musical key
by seeking to each track's start_seconds and analyzing a short window of audio.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, TypedDict
import logging

import numpy as np
import librosa
from mutagen import File as MutagenFile

log = logging.getLogger("mixdeck.audio")

# Krumhansl-Schmuckler key profiles (major and minor)
_MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
_MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)
_PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Camelot wheel mapping - standard DJ notation
# Format: "<root>:<mode>" -> "<number><A|B>" (A = minor, B = major)
_CAMELOT_MAP = {
    "C:major": "8B",  "A:minor": "8A",
    "G:major": "9B",  "E:minor": "9A",
    "D:major": "10B", "B:minor": "10A",
    "A:major": "11B", "F#:minor": "11A",
    "E:major": "12B", "C#:minor": "12A",
    "B:major": "1B",  "G#:minor": "1A",
    "F#:major": "2B", "D#:minor": "2A",
    "C#:major": "3B", "A#:minor": "3A",
    "G#:major": "4B", "F:minor": "4A",
    "D#:major": "5B", "C:minor": "5A",
    "A#:major": "6B", "G:minor": "6A",
    "F:major": "7B",  "D:minor": "7A",
}


class AudioInfo(TypedDict, total=False):
    duration: float
    codec: str
    bitrate: int
    sample_rate: int
    bpm_tag: Optional[int]
    title_tag: Optional[str]
    artist_tag: Optional[str]
    genre_tag: Optional[str]


def read_audio_info(path: str | Path) -> AudioInfo:
    """Fast metadata via mutagen (no audio decoding)."""
    info: AudioInfo = {}
    try:
        m = MutagenFile(str(path))
        if m is None:
            return info
        if m.info:
            info["duration"] = float(getattr(m.info, "length", 0.0) or 0.0)
            br = getattr(m.info, "bitrate", None)
            if br:
                info["bitrate"] = int(br)
            sr = getattr(m.info, "sample_rate", None)
            if sr:
                info["sample_rate"] = int(sr)
            info["codec"] = m.mime[0].split("/")[-1] if m.mime else Path(path).suffix.lstrip(".")

        def _tag(*keys):
            if not m.tags:
                return None
            for k in keys:
                v = m.tags.get(k)
                if v:
                    s = str(v[0]) if isinstance(v, list) else str(v)
                    return s.strip() or None
            return None

        bpm_raw = _tag("TBPM", "BPM", "bpm", "TMPO")
        if bpm_raw:
            try:
                info["bpm_tag"] = int(round(float(bpm_raw)))
            except ValueError:
                pass
        info["title_tag"] = _tag("TIT2", "TITLE", "title", "\xa9nam")
        info["artist_tag"] = _tag("TPE1", "ARTIST", "artist", "\xa9ART")
        info["genre_tag"] = _tag("TCON", "GENRE", "genre", "\xa9gen")
    except Exception as e:
        log.warning("mutagen read failed for %s: %s", path, e)
    return info


def _key_to_camelot(root_idx: int, is_minor: bool) -> tuple[str, str]:
    root = _PITCH_NAMES[root_idx]
    mode = "minor" if is_minor else "major"
    name = f"{root} {mode}"
    camelot = _CAMELOT_MAP.get(f"{root}:{mode}", "")
    return name, camelot


def analyze_window(y: np.ndarray, sr: int) -> dict:
    """Return {bpm, key, camelot} for an audio buffer y at sample rate sr."""
    out: dict = {}
    try:
        tempo = librosa.feature.tempo(y=y, sr=sr, aggregate=np.median)
        bpm = float(tempo[0]) if len(tempo) else 0.0
        # Fold tempo to a DJ-friendly range (most club tracks: 90-180).
        while bpm > 0 and bpm < 70:
            bpm *= 2
        while bpm > 185:
            bpm /= 2
        out["bpm"] = int(round(bpm)) if bpm else None
    except Exception as e:
        log.warning("BPM estimation failed: %s", e)

    try:
        # Chroma CENS is more robust for key detection on long windows
        chroma = librosa.feature.chroma_cens(y=y, sr=sr)
        chroma_vec = np.mean(chroma, axis=1)
        # normalise
        if chroma_vec.sum() > 0:
            chroma_vec = chroma_vec / chroma_vec.sum()

        def _corr(profile):
            p = profile / profile.sum()
            # circular correlation - score each of 12 rotations
            scores = np.zeros(12)
            for i in range(12):
                rolled = np.roll(p, i)
                scores[i] = np.corrcoef(chroma_vec, rolled)[0, 1]
            return scores

        maj_scores = _corr(_MAJOR_PROFILE)
        min_scores = _corr(_MINOR_PROFILE)
        best_maj = int(np.argmax(maj_scores))
        best_min = int(np.argmax(min_scores))
        if maj_scores[best_maj] >= min_scores[best_min]:
            name, camelot = _key_to_camelot(best_maj, is_minor=False)
        else:
            name, camelot = _key_to_camelot(best_min, is_minor=True)
        out["key"] = name
        out["camelot"] = camelot
    except Exception as e:
        log.warning("Key estimation failed: %s", e)
    return out


def analyze_segment(
    path: str | Path,
    start_seconds: float = 0.0,
    duration_seconds: float = 45.0,
    target_sr: int = 22050,
) -> dict:
    """Decode a short window and return {bpm, key, camelot}."""
    try:
        y, sr = librosa.load(
            str(path),
            sr=target_sr,
            mono=True,
            offset=max(0.0, float(start_seconds)),
            duration=float(duration_seconds),
        )
        if y is None or len(y) == 0:
            return {}
        return analyze_window(y, sr)
    except Exception as e:
        log.warning("analyze_segment failed for %s @ %s: %s", path, start_seconds, e)
        return {}
