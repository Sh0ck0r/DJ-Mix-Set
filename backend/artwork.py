"""Track artwork lookup cascade: iTunes -> MusicBrainz/CoverArt -> Discogs.

Successful hits and explicit misses are cached in the `track_artwork`
collection keyed by a normalised `artist|title`. Pass refresh=True to bypass
the cache and re-query upstream.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

from state import db, DISCOGS_TOKEN

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/recording"
COVERART_URL = "https://coverartarchive.org/release"
DISCOGS_SEARCH_URL = "https://api.discogs.com/database/search"
MB_USER_AGENT = "MIXDECK/1.0 (https://github.com/mixdeck)"

log = logging.getLogger("mixdeck")


def _clean_for_search(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"\s+feat\.?\s+.*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+ft\.?\s+.*$", "", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def _normalize_key(artist: str, title: str) -> str:
    def clean(s: str) -> str:
        s = (s or "").lower().strip()
        s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
        s = re.sub(r"\s+feat\.?\s+.*$", "", s)
        s = re.sub(r"\s+ft\.?\s+.*$", "", s)
        s = re.sub(r"[^\w\s-]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s
    return f"{clean(artist)}|{clean(title)}"


def _mb_escape(s: str) -> str:
    return re.sub(r'([+\-!(){}\[\]^"~*?:\\/])', r"\\\1", s)


async def _lookup_itunes(artist: str, title: str) -> Optional[str]:
    q_parts = [p for p in (artist or "", title or "") if p]
    if not q_parts:
        return None
    term = " ".join(q_parts)
    params = {"term": term, "media": "music", "entity": "musicTrack", "limit": 5}
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            resp = await c.get(ITUNES_SEARCH_URL, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
    except Exception as e:
        log.warning("iTunes lookup failed: %s", e)
        return None
    for r in data.get("results") or []:
        url = r.get("artworkUrl100") or r.get("artworkUrl60")
        if url:
            # upgrade to 600x600
            return re.sub(r"/\d+x\d+(bb)?(-\d+)?\.(jpg|png|jpeg)", "/600x600bb.jpg", url)
    return None


async def _lookup_musicbrainz(artist: str, title: str) -> Optional[str]:
    artist_c = _clean_for_search(artist)
    title_c = _clean_for_search(title)
    if not title_c:
        return None
    parts = []
    if title_c:
        parts.append(f'recording:"{_mb_escape(title_c)}"')
    if artist_c:
        parts.append(f'artist:"{_mb_escape(artist_c)}"')
    query = " AND ".join(parts)
    headers = {"User-Agent": MB_USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as c:
            resp = await c.get(MUSICBRAINZ_URL, params={"query": query, "fmt": "json", "limit": 5})
            if resp.status_code != 200:
                return None
            data = resp.json()
            release_ids: list[str] = []
            for rec in data.get("recordings") or []:
                for rel in rec.get("releases", []) or []:
                    rid = rel.get("id")
                    if rid and rid not in release_ids:
                        release_ids.append(rid)
                if len(release_ids) >= 6:
                    break
            for rid in release_ids[:6]:
                art_url = f"{COVERART_URL}/{rid}/front-500"
                try:
                    head = await c.head(art_url, follow_redirects=True, timeout=6.0)
                    if head.status_code == 200:
                        return art_url
                except Exception:
                    continue
    except Exception as e:
        log.warning("MusicBrainz lookup failed: %s", e)
    return None


async def _lookup_discogs(artist: str, title: str) -> Optional[str]:
    if not DISCOGS_TOKEN:
        return None
    artist_c = _clean_for_search(artist)
    title_c = _clean_for_search(title)
    if not title_c:
        return None
    params = {
        "q": f"{artist_c} {title_c}".strip(),
        "type": "release",
        "per_page": 5,
        "token": DISCOGS_TOKEN,
    }
    headers = {"User-Agent": MB_USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=headers) as c:
            resp = await c.get(DISCOGS_SEARCH_URL, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
    except Exception as e:
        log.warning("Discogs lookup failed: %s", e)
        return None
    for r in data.get("results") or []:
        url = r.get("cover_image") or r.get("thumb")
        if url and "spacer.gif" not in url:
            return url
    return None


async def lookup_track_artwork(artist: str, title: str, refresh: bool = False) -> dict:
    """Top-level helper used by the route. Returns {url, source, cached}."""
    artist = (artist or "").strip()
    title = (title or "").strip()
    if not artist and not title:
        return {"url": None, "source": None, "cached": False}
    key = _normalize_key(artist, title)
    if not refresh:
        cached = await db.track_artwork.find_one({"key": key}, {"_id": 0})
        if cached is not None:
            return {
                "url": cached.get("url"),
                "source": cached.get("source"),
                "cached": True,
            }
    source = None
    url = await _lookup_itunes(artist, title)
    if url:
        source = "itunes"
    else:
        url = await _lookup_musicbrainz(artist, title)
        if url:
            source = "musicbrainz"
        else:
            url = await _lookup_discogs(artist, title)
            if url:
                source = "discogs"
    await db.track_artwork.update_one(
        {"key": key},
        {"$set": {
            "key": key,
            "url": url,
            "source": source,
            "artist": artist,
            "title": title,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {"url": url, "source": source, "cached": False}
