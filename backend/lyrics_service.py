"""Lyrics lookup via LRCLIB.net (free, no API key, modern open lyrics DB).

Returns either time-synced (LRC-format) or plain lyrics. Results — including
explicit misses — are cached in the `track_lyrics` collection keyed by a
normalised `artist|title|round(duration)` so repeated lookups are instant
and don't hammer the upstream.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

from state import db

LRCLIB_GET = "https://lrclib.net/api/get"
LRCLIB_SEARCH = "https://lrclib.net/api/search"
USER_AGENT = "MIXDECK/1.0 (https://github.com/mixdeck)"

log = logging.getLogger("mixdeck")


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"\s+feat\.?\s+.*$", "", s)
    s = re.sub(r"\s+ft\.?\s+.*$", "", s)
    s = re.sub(r"\s+remix.*$", "", s)
    s = re.sub(r"\s+(extended|original|radio|club|vocal|instrumental)\s+(mix|edit|version)\s*$", "", s)
    s = re.sub(r"[^\w\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _cache_key(artist: str, title: str, duration: Optional[float]) -> str:
    d = int(round(duration)) if duration else 0
    return f"{_norm(artist)}|{_norm(title)}|{d // 5}"  # bucket by 5s windows for fuzzy match


# LRC timestamp regex - used by parse_lrc for both finding and stripping prefixes.
LRC_LINE_RE = re.compile(r"^\[(\d+):(\d+)(?:[.:](\d+))?\](.*)$")  # legacy, kept for callers that import it


def parse_lrc(synced: str) -> list[dict]:
    """Convert LRC-format text to [{time, text}], sorted by time.

    Handles:
    - Single-timestamp lines: `[01:23.45]Lyric here`
    - Multi-timestamp lines (used by LRCLIB to dedupe repeated choruses):
      `[00:30.00][01:30.00][02:30.00]Same chorus line` → emits 3 entries
    - Section labels (`ti:`, `ar:`, etc) are stripped.
    """
    out: list[dict] = []
    if not synced:
        return out
    tag_re = re.compile(r"\[(\d+):(\d+)(?:[.:](\d+))?\]")
    prefix_re = re.compile(r"^(?:\[\d+:\d+(?:[.:]\d+)?\])+")
    for raw in synced.splitlines():
        line = raw.strip()
        if not line:
            continue
        tags = tag_re.findall(line)
        if not tags:
            continue
        text = prefix_re.sub("", line).strip()
        for mins, secs, frac in tags:
            t = int(mins) * 60 + int(secs) + (int(frac.ljust(3, "0")[:3]) / 1000 if frac else 0)
            out.append({"time": round(t, 3), "text": text})
    # Filter out section labels (commonly [Verse 1], [Chorus] etc that appear as ti/ar/al headers)
    out = [item for item in out if item["text"] and not item["text"].lower().startswith(("ti:", "ar:", "al:", "by:", "length:", "offset:", "re:", "ve:"))]
    out.sort(key=lambda x: x["time"])
    return out


async def _query_lrclib_get(artist: str, title: str, duration: Optional[float]) -> Optional[dict]:
    params: dict = {"artist_name": artist, "track_name": title}
    if duration:
        params["duration"] = int(round(duration))
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=headers) as c:
            r = await c.get(LRCLIB_GET, params=params)
            if r.status_code != 200:
                return None
            return r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("LRCLIB /get failed: %s", e)
        return None


async def _query_lrclib_search(artist: str, title: str) -> Optional[dict]:
    """Fallback fuzzy search when /get returns nothing."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=headers) as c:
            r = await c.get(LRCLIB_SEARCH, params={"artist_name": artist, "track_name": title})
            if r.status_code != 200:
                return None
            results = r.json()
            if not isinstance(results, list) or not results:
                return None
            # Prefer the result with syncedLyrics, fall back to first
            for item in results:
                if item.get("syncedLyrics"):
                    return item
            return results[0]
    except (httpx.HTTPError, ValueError) as e:
        log.warning("LRCLIB /search failed: %s", e)
        return None


async def lookup_lyrics(
    artist: str,
    title: str,
    duration: Optional[float] = None,
    refresh: bool = False,
) -> dict:
    """Top-level helper. Returns:
        {
          "synced": [{time, text}, ...] or [],
          "plain":  "..." (string) or "",
          "source": "lrclib" | "manual" | None,
          "found":  bool,
          "cached": bool,
        }
    Hits the per-track Mongo cache first (including explicit misses) so we
    don't keep hammering LRCLIB for tracks that genuinely have no synced lyrics.
    """
    artist = (artist or "").strip()
    title = (title or "").strip()
    if not artist and not title:
        return {"synced": [], "plain": "", "source": None, "found": False, "cached": False}
    key = _cache_key(artist, title, duration)

    if not refresh:
        cached = await db.track_lyrics.find_one({"key": key}, {"_id": 0})
        if cached is not None:
            return {
                "synced": cached.get("synced") or [],
                "plain": cached.get("plain") or "",
                "source": cached.get("source"),
                "found": bool(cached.get("synced") or cached.get("plain")),
                "cached": True,
            }

    data = await _query_lrclib_get(artist, title, duration)
    if not data:
        data = await _query_lrclib_search(artist, title)

    synced_list: list[dict] = []
    plain = ""
    source: Optional[str] = None
    if data:
        synced_raw = data.get("syncedLyrics") or ""
        plain = (data.get("plainLyrics") or "").strip()
        synced_list = parse_lrc(synced_raw)
        if synced_list or plain:
            source = "lrclib"

    await db.track_lyrics.update_one(
        {"key": key},
        {
            "$set": {
                "key": key,
                "artist": artist,
                "title": title,
                "duration": int(round(duration)) if duration else None,
                "synced": synced_list,
                "plain": plain,
                "source": source,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    return {
        "synced": synced_list,
        "plain": plain,
        "source": source,
        "found": bool(synced_list or plain),
        "cached": False,
    }


async def set_manual(artist: str, title: str, duration: Optional[float], plain: str, synced: str) -> dict:
    """Admin override: paste plain text or raw LRC and we'll parse it."""
    key = _cache_key(artist, title, duration)
    synced_list = parse_lrc(synced) if synced else []
    payload = {
        "key": key,
        "artist": artist,
        "title": title,
        "duration": int(round(duration)) if duration else None,
        "synced": synced_list,
        "plain": (plain or "").strip(),
        "source": "manual",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.track_lyrics.update_one({"key": key}, {"$set": payload}, upsert=True)
    return {
        "synced": synced_list,
        "plain": payload["plain"],
        "source": "manual",
        "found": bool(synced_list or payload["plain"]),
        "cached": False,
    }
