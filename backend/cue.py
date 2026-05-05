"""CUE sheet parser + on-disk file discovery helpers.

Pure functions over file paths and strings. No db, no network.
"""
import re
from pathlib import Path
from typing import List, Optional

from models import Track

AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac", ".opus"}
COVER_NAMES = ("cover", "folder", "front", "album")
COVER_EXTS = (".jpg", ".jpeg", ".png", ".webp")

CUE_FILE_RE = re.compile(r'^\s*FILE\s+"?(.+?)"?\s+(\w+)\s*$', re.IGNORECASE)
CUE_TRACK_RE = re.compile(r'^\s*TRACK\s+(\d+)\s+(\w+)\s*$', re.IGNORECASE)
CUE_TITLE_RE = re.compile(r'^\s*TITLE\s+"?(.+?)"?\s*$', re.IGNORECASE)
CUE_PERFORMER_RE = re.compile(r'^\s*PERFORMER\s+"?(.+?)"?\s*$', re.IGNORECASE)
CUE_INDEX_RE = re.compile(r'^\s*INDEX\s+(\d+)\s+(\d+):(\d+):(\d+)\s*$', re.IGNORECASE)


def parse_cue(content: str) -> List[Track]:
    """Parse a .cue sheet into a list of Track objects."""
    tracks: List[Track] = []
    current: Optional[dict] = None
    for raw in content.splitlines():
        line = raw.rstrip()
        m_track = CUE_TRACK_RE.match(line)
        if m_track:
            if current is not None:
                tracks.append(Track(**current))
            current = {
                "index": int(m_track.group(1)),
                "title": "",
                "artist": "",
                "start_seconds": 0.0,
            }
            continue
        if current is None:
            continue
        m_title = CUE_TITLE_RE.match(line)
        if m_title:
            current["title"] = m_title.group(1).strip().strip('"').strip()
            continue
        m_perf = CUE_PERFORMER_RE.match(line)
        if m_perf:
            current["artist"] = m_perf.group(1).strip().strip('"').strip()
            continue
        m_idx = CUE_INDEX_RE.match(line)
        if m_idx and m_idx.group(1) == "01":
            mins = int(m_idx.group(2))
            secs = int(m_idx.group(3))
            frames = int(m_idx.group(4))  # 75 frames per second
            current["start_seconds"] = mins * 60 + secs + frames / 75.0
    if current is not None:
        tracks.append(Track(**current))
    return tracks


def extract_cue_header(content: str) -> tuple[str, str]:
    """Return (title, performer) from the top-level cue header (before first TRACK)."""
    title = ""
    performer = ""
    for raw in content.splitlines():
        line = raw.strip()
        if CUE_TRACK_RE.match(line):
            break
        m_title = CUE_TITLE_RE.match(line)
        if m_title and not title:
            title = m_title.group(1).strip().strip('"').strip()
            continue
        m_perf = CUE_PERFORMER_RE.match(line)
        if m_perf and not performer:
            performer = m_perf.group(1).strip().strip('"').strip()
    return title, performer


def find_cue_for(audio: Path) -> Optional[Path]:
    """Locate the .cue file matching a given audio file."""
    cue = audio.with_suffix(".cue")
    if cue.exists():
        return cue
    # case-insensitive fallback
    for sib in audio.parent.iterdir():
        if sib.is_file() and sib.stem.lower() == audio.stem.lower() and sib.suffix.lower() == ".cue":
            return sib
    return None


def find_cover_for(audio: Path) -> Optional[Path]:
    """Locate cover art adjacent to the audio file (same-name, then generic names)."""
    # 1. Same-name art: MixName.jpg
    for ext in COVER_EXTS:
        p = audio.with_suffix(ext)
        if p.exists():
            return p
    # 2. Generic names in same folder
    for name in COVER_NAMES:
        for ext in COVER_EXTS:
            p = audio.parent / f"{name}{ext}"
            if p.exists():
                return p
            p = audio.parent / f"{name.upper()}{ext}"
            if p.exists():
                return p
    return None
