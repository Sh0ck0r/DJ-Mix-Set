"""MIXDECK backend - DJ mix streaming with cue sheet support."""
from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Depends, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import os
import re
import uuid
import jwt
import logging
import mimetypes
import aiofiles
import shutil
import httpx
import asyncio

from audio_analysis import read_audio_info, analyze_segment

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

STORAGE_DIR = ROOT_DIR / "storage"
AUDIO_DIR = STORAGE_DIR / "audio"
COVERS_DIR = STORAGE_DIR / "covers"
CUES_DIR = STORAGE_DIR / "cues"
for d in (AUDIO_DIR, COVERS_DIR, CUES_DIR):
    d.mkdir(parents=True, exist_ok=True)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "mixdeck2026")
JWT_SECRET = os.environ.get("JWT_SECRET", "mixdeck-secret-change-me")
JWT_ALGO = "HS256"

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="MIXDECK API")
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)


# ===== Models =====
class Track(BaseModel):
    index: int
    title: str
    artist: str = ""
    start_seconds: float = 0.0
    bpm: Optional[int] = None
    key: Optional[str] = None  # e.g. "A minor"
    camelot: Optional[str] = None  # e.g. "8A"


class Mix(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    artist: str = ""
    genre: str = ""
    bpm: Optional[int] = None
    key: Optional[str] = None
    camelot: Optional[str] = None
    duration: float = 0.0  # seconds
    description: str = ""
    audio_filename: Optional[str] = None  # local file in /storage/audio
    cover_filename: Optional[str] = None
    audio_url: Optional[str] = None  # external streaming url alternative
    cover_url: Optional[str] = None  # external image url alternative
    source_path: Optional[str] = None  # in-place reference (absolute filesystem path)
    source_cover_path: Optional[str] = None  # in-place cover reference
    analysis_status: str = "none"  # none | pending | running | done | failed
    tracks: List[Track] = []
    play_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MixCreate(BaseModel):
    title: str
    artist: str = ""
    genre: str = ""
    bpm: Optional[int] = None
    description: str = ""
    audio_url: Optional[str] = None
    cover_url: Optional[str] = None


class MixUpdate(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    genre: Optional[str] = None
    bpm: Optional[int] = None
    description: Optional[str] = None
    audio_url: Optional[str] = None
    cover_url: Optional[str] = None


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str


# ===== Auth =====
def create_admin_token() -> str:
    payload = {
        "sub": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def require_admin(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if creds is None:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return True


# ===== CUE sheet parser =====
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


# ===== iTunes Search artwork lookup (cached) =====
ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/recording"
COVERART_URL = "https://coverartarchive.org/release"
DISCOGS_SEARCH_URL = "https://api.discogs.com/database/search"
MB_USER_AGENT = "MIXDECK/1.0 (https://github.com/mixdeck)"
DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "").strip()


def _normalize_key(artist: str, title: str) -> str:
    def clean(s: str) -> str:
        s = (s or "").lower().strip()
        # strip common noise: "(original mix)", "[remastered]", featured, etc.
        s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
        s = re.sub(r"\s+feat\.?\s+.*$", "", s)
        s = re.sub(r"\s+ft\.?\s+.*$", "", s)
        s = re.sub(r"[^\w\s-]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s
    return f"{clean(artist)}|{clean(title)}"


def _clean_for_search(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"\s+feat\.?\s+.*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+ft\.?\s+.*$", "", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


async def _lookup_itunes(artist: str, title: str) -> Optional[str]:
    q_parts = [p for p in (artist or "", title or "") if p]
    if not q_parts:
        return None
    term = " ".join(q_parts)
    params = {"term": term, "media": "music", "entity": "musicTrack", "limit": 5}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(ITUNES_SEARCH_URL, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
    except Exception as e:
        logging.getLogger("mixdeck").warning("iTunes lookup failed: %s", e)
        return None
    results = data.get("results") or []
    if not results:
        return None
    # pick first with artwork
    for r in results:
        url = r.get("artworkUrl100") or r.get("artworkUrl60")
        if url:
            # upgrade to 600x600
            return re.sub(r"/\d+x\d+(bb)?(-\d+)?\.(jpg|png|jpeg)",
                          "/600x600bb.jpg", url)
    return None


def _mb_escape(s: str) -> str:
    # Lucene special chars -> escape them
    return re.sub(r'([+\-!(){}\[\]^"~*?:\\/])', r"\\\1", s)


async def _lookup_musicbrainz(artist: str, title: str) -> Optional[str]:
    """Fallback: search MusicBrainz for the recording, then hit Cover Art Archive."""
    artist_c = _clean_for_search(artist)
    title_c = _clean_for_search(title)
    if not title_c:
        return None
    query_parts = []
    if title_c:
        query_parts.append(f'recording:"{_mb_escape(title_c)}"')
    if artist_c:
        query_parts.append(f'artist:"{_mb_escape(artist_c)}"')
    query = " AND ".join(query_parts)
    headers = {"User-Agent": MB_USER_AGENT, "Accept": "application/json"}
    log = logging.getLogger("mixdeck")
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            resp = await client.get(
                MUSICBRAINZ_URL,
                params={"query": query, "fmt": "json", "limit": 5},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            recordings = data.get("recordings") or []
            # collect candidate release mbids, sorted by score
            release_ids: list[str] = []
            for rec in recordings:
                for rel in rec.get("releases", []) or []:
                    rid = rel.get("id")
                    if rid and rid not in release_ids:
                        release_ids.append(rid)
                if len(release_ids) >= 6:
                    break
            # Probe Cover Art Archive for the first release with artwork
            for rid in release_ids[:6]:
                art_url = f"{COVERART_URL}/{rid}/front-500"
                try:
                    head = await client.head(art_url, follow_redirects=True, timeout=6.0)
                    if head.status_code == 200:
                        return art_url
                except Exception:
                    continue
    except Exception as e:
        log.warning("MusicBrainz lookup failed: %s", e)
    return None


async def _lookup_discogs(artist: str, title: str) -> Optional[str]:
    """Tier-3 fallback using Discogs. Requires DISCOGS_TOKEN env var."""
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
        async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
            resp = await client.get(DISCOGS_SEARCH_URL, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
    except Exception as e:
        logging.getLogger("mixdeck").warning("Discogs lookup failed: %s", e)
        return None
    for r in data.get("results") or []:
        url = r.get("cover_image") or r.get("thumb")
        if url and "spacer.gif" not in url:
            return url
    return None


@api_router.get("/tracks/artwork")
async def track_artwork(artist: str = "", title: str = "", refresh: int = 0):
    """Return artwork URL for a track, cached in Mongo.

    Lookup order: iTunes -> MusicBrainz + Cover Art Archive -> Discogs.
    Both successful hits and misses are cached. Pass ?refresh=1 to force a
    re-lookup (useful for cached misses after adding new fallback sources).
    """
    artist = (artist or "").strip()
    title = (title or "").strip()
    if not artist and not title:
        return {"url": None}
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


# ===== Routes =====
@api_router.get("/")
async def root():
    return {"message": "MIXDECK API online", "version": "1.0.0"}


@api_router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    if body.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    return LoginResponse(token=create_admin_token())


@api_router.get("/auth/verify")
async def verify(_: bool = Depends(require_admin)):
    return {"valid": True}


@api_router.get("/mixes", response_model=List[Mix])
async def list_mixes(q: Optional[str] = None, genre: Optional[str] = None):
    query: dict = {}
    if genre:
        query["genre"] = genre
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"artist": {"$regex": q, "$options": "i"}},
            {"genre": {"$regex": q, "$options": "i"}},
        ]
    docs = await db.mixes.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [Mix(**d) for d in docs]


@api_router.get("/mixes/genres")
async def list_genres():
    genres = await db.mixes.distinct("genre")
    return {"genres": [g for g in genres if g]}


@api_router.get("/mixes/{mix_id}", response_model=Mix)
async def get_mix(mix_id: str):
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    return Mix(**doc)


@api_router.post("/mixes/{mix_id}/play")
async def increment_play(mix_id: str):
    res = await db.mixes.update_one({"id": mix_id}, {"$inc": {"play_count": 1}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Mix not found")
    return {"ok": True}


@api_router.get("/mixes/{mix_id}/compatible", response_model=List[Mix])
async def compatible_mixes(mix_id: str, limit: int = 8):
    """Find harmonically + tempo compatible mixes from the library.

    Rules (classic harmonic-mixing):
    - BPM within +/- 4 of this mix's BPM
    - Camelot wheel: same key, same number adjacent (+/-1), or relative
      major<->minor (same number, A<->B). Mode adjacent slots = perfect.
    """
    src = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Mix not found")
    src_bpm = src.get("bpm")
    src_cam = (src.get("camelot") or "").upper().strip()

    # Build the camelot adjacency set
    compat_keys: set[str] = set()
    if src_cam and len(src_cam) >= 2:
        try:
            num = int(src_cam[:-1])
            mode = src_cam[-1]
            other = "B" if mode == "A" else "A"
            for n in (num, ((num - 2) % 12) + 1, (num % 12) + 1):
                compat_keys.add(f"{n}{mode}")
            compat_keys.add(f"{num}{other}")  # relative major/minor
        except (ValueError, IndexError):
            pass

    candidates = await db.mixes.find({"id": {"$ne": mix_id}}, {"_id": 0}).to_list(2000)
    scored: list[tuple[float, dict]] = []
    for c in candidates:
        score = 0.0
        c_bpm = c.get("bpm")
        if src_bpm and c_bpm:
            diff = abs(c_bpm - src_bpm)
            if diff <= 4:
                score += 4 - diff
            elif diff <= 8:
                score += 0.5
        c_cam = (c.get("camelot") or "").upper().strip()
        if compat_keys and c_cam:
            if c_cam == src_cam:
                score += 4
            elif c_cam in compat_keys:
                score += 3
        if src.get("genre") and c.get("genre") == src.get("genre"):
            score += 1
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda t: -t[0])
    return [Mix(**c) for _, c in scored[:limit]]


@api_router.post("/admin/mixes", response_model=Mix, dependencies=[Depends(require_admin)])
async def create_mix(body: MixCreate):
    mix = Mix(**body.model_dump())
    await db.mixes.insert_one(mix.model_dump())
    return mix


@api_router.patch("/admin/mixes/{mix_id}", response_model=Mix, dependencies=[Depends(require_admin)])
async def update_mix(mix_id: str, body: MixUpdate):
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = await db.mixes.update_one({"id": mix_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Mix not found")
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    return Mix(**doc)


@api_router.delete("/admin/mixes/{mix_id}", dependencies=[Depends(require_admin)])
async def delete_mix(mix_id: str):
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    for key, folder in (("audio_filename", AUDIO_DIR), ("cover_filename", COVERS_DIR)):
        fname = doc.get(key)
        if fname:
            fp = folder / fname
            if fp.exists():
                fp.unlink()
    cue_path = CUES_DIR / f"{mix_id}.cue"
    if cue_path.exists():
        cue_path.unlink()
    await db.mixes.delete_one({"id": mix_id})
    return {"ok": True}


async def _save_upload(upload: UploadFile, dest: Path) -> int:
    size = 0
    async with aiofiles.open(dest, "wb") as f:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            await f.write(chunk)
    return size


@api_router.post("/admin/mixes/{mix_id}/audio", dependencies=[Depends(require_admin)])
async def upload_audio(mix_id: str, file: UploadFile = File(...)):
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    ext = Path(file.filename).suffix.lower()
    if ext not in (".mp3", ".flac", ".wav", ".m4a", ".ogg"):
        raise HTTPException(status_code=400, detail="Unsupported audio format")
    out_name = f"{mix_id}{ext}"
    # remove any old audio
    for old in AUDIO_DIR.glob(f"{mix_id}.*"):
        old.unlink()
    out_path = AUDIO_DIR / out_name
    await _save_upload(file, out_path)
    await db.mixes.update_one(
        {"id": mix_id}, {"$set": {"audio_filename": out_name, "audio_url": None}}
    )
    return {"ok": True, "filename": out_name}


@api_router.post("/admin/mixes/{mix_id}/cover", dependencies=[Depends(require_admin)])
async def upload_cover(mix_id: str, file: UploadFile = File(...)):
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    ext = Path(file.filename).suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        raise HTTPException(status_code=400, detail="Unsupported image format")
    out_name = f"{mix_id}{ext}"
    for old in COVERS_DIR.glob(f"{mix_id}.*"):
        old.unlink()
    out_path = COVERS_DIR / out_name
    await _save_upload(file, out_path)
    await db.mixes.update_one(
        {"id": mix_id}, {"$set": {"cover_filename": out_name, "cover_url": None}}
    )
    return {"ok": True, "filename": out_name}


@api_router.post("/admin/mixes/{mix_id}/cue", dependencies=[Depends(require_admin)])
async def upload_cue(mix_id: str, file: UploadFile = File(...)):
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    raw = await file.read()
    try:
        content = raw.decode("utf-8", errors="replace")
    except Exception:
        content = raw.decode("latin-1", errors="replace")
    out_path = CUES_DIR / f"{mix_id}.cue"
    out_path.write_text(content, encoding="utf-8")
    tracks = parse_cue(content)
    await db.mixes.update_one(
        {"id": mix_id},
        {"$set": {"tracks": [t.model_dump() for t in tracks]}},
    )
    return {"ok": True, "track_count": len(tracks), "tracks": [t.model_dump() for t in tracks]}


@api_router.post("/admin/mixes/{mix_id}/tracks", dependencies=[Depends(require_admin)])
async def set_tracks(mix_id: str, tracks: List[Track]):
    res = await db.mixes.update_one(
        {"id": mix_id}, {"$set": {"tracks": [t.model_dump() for t in tracks]}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Mix not found")
    return {"ok": True}


@api_router.post("/admin/mixes/{mix_id}/duration", dependencies=[Depends(require_admin)])
async def set_duration(mix_id: str, duration: float = Form(...)):
    res = await db.mixes.update_one({"id": mix_id}, {"$set": {"duration": float(duration)}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Mix not found")
    return {"ok": True}


# Public-facing duration update (the browser knows the audio duration after metadata loads)
@api_router.post("/mixes/{mix_id}/duration")
async def public_set_duration(mix_id: str, duration: float = Form(...)):
    # only set if currently zero
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    if not doc.get("duration"):
        await db.mixes.update_one({"id": mix_id}, {"$set": {"duration": float(duration)}})
    return {"ok": True}


# ===== Streaming with Range support =====
def _file_response_with_range(path: Path, request: Request):
    file_size = path.stat().st_size
    range_header = request.headers.get("range") or request.headers.get("Range")
    content_type, _ = mimetypes.guess_type(str(path))
    if content_type is None:
        if path.suffix.lower() == ".flac":
            content_type = "audio/flac"
        else:
            content_type = "application/octet-stream"

    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if m:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else file_size - 1
            end = min(end, file_size - 1)
            length = end - start + 1

            async def iter_range():
                async with aiofiles.open(path, "rb") as f:
                    await f.seek(start)
                    remaining = length
                    chunk_size = 1024 * 256
                    while remaining > 0:
                        data = await f.read(min(chunk_size, remaining))
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
                "Cache-Control": "public, max-age=3600",
            }
            return StreamingResponse(
                iter_range(), status_code=206, media_type=content_type, headers=headers
            )

    async def iter_full():
        async with aiofiles.open(path, "rb") as f:
            chunk_size = 1024 * 256
            while True:
                data = await f.read(chunk_size)
                if not data:
                    break
                yield data

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Cache-Control": "public, max-age=3600",
    }
    return StreamingResponse(iter_full(), media_type=content_type, headers=headers)


@api_router.get("/stream/{mix_id}")
async def stream_audio(mix_id: str, request: Request):
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    fname = doc.get("audio_filename")
    if fname:
        path = AUDIO_DIR / fname
        if path.exists():
            return _file_response_with_range(path, request)
    sp = doc.get("source_path")
    if sp:
        path = Path(sp)
        if path.exists() and path.is_file():
            return _file_response_with_range(path, request)
    raise HTTPException(status_code=404, detail="Audio file not found")


@api_router.get("/cover/{mix_id}")
async def get_cover(mix_id: str):
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    fname = doc.get("cover_filename")
    if fname:
        path = COVERS_DIR / fname
        if path.exists():
            return FileResponse(path)
    scp = doc.get("source_cover_path")
    if scp:
        path = Path(scp)
        if path.exists() and path.is_file():
            return FileResponse(path)
    raise HTTPException(status_code=404, detail="Cover not found")


# ===== Bulk directory scan =====
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac", ".opus"}
COVER_NAMES = ("cover", "folder", "front", "album")
COVER_EXTS = (".jpg", ".jpeg", ".png", ".webp")


class ScanRequest(BaseModel):
    path: str
    recursive: bool = True
    default_genre: str = ""
    analyze: bool = True  # auto-run BPM + key analysis on every new mix


# ===== Background audio analysis =====
_analysis_locks: dict[str, asyncio.Task] = {}
_ANALYSIS_CONCURRENCY = int(os.environ.get("ANALYSIS_CONCURRENCY", "2"))
_analysis_semaphore: Optional[asyncio.Semaphore] = None


def _get_analysis_semaphore() -> asyncio.Semaphore:
    global _analysis_semaphore
    if _analysis_semaphore is None:
        _analysis_semaphore = asyncio.Semaphore(_ANALYSIS_CONCURRENCY)
    return _analysis_semaphore


async def _run_mix_analysis(mix_id: str) -> None:
    """Analyse a mix in the background: extract per-track BPM + key and mix duration.
    Runs in a thread pool since librosa is CPU bound.
    Limited by a global semaphore so bulk scans don't thrash the server.
    """
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
        src = doc.get("source_path") or (str(AUDIO_DIR / doc["audio_filename"]) if doc.get("audio_filename") else None)
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
            return

        # 2) Per-track analysis - analyze a 45s window from each track
        analyzed: list[dict] = []
        for i, t in enumerate(tracks):
            start = float(t.get("start_seconds") or 0.0)
            # use window up to next track's start (capped at 45s, min 20s)
            next_start = (
                float(tracks[i + 1]["start_seconds"]) if i + 1 < len(tracks) else (duration or start + 60)
            )
            window = min(45.0, max(20.0, next_start - start - 2.0))
            # skip analysis if window is nonsensical
            if window < 15:
                analyzed.append(t)
                continue
            # skip past first 8 seconds to avoid the transition into the track
            offset = start + 8.0
            res = await loop.run_in_executor(None, analyze_segment, src, offset, window)
            t_new = dict(t)
            if res.get("bpm"):
                t_new["bpm"] = res["bpm"]
            if res.get("key"):
                t_new["key"] = res["key"]
                t_new["camelot"] = res.get("camelot")
            analyzed.append(t_new)
            # checkpoint every 5 tracks so the UI sees progress
            if (i + 1) % 5 == 0:
                await db.mixes.update_one(
                    {"id": mix_id},
                    {"$set": {"tracks": analyzed + tracks[i + 1:], "analysis_status": "running"}},
                )

        bpms = [x["bpm"] for x in analyzed if x.get("bpm")]
        if bpms and not updates.get("bpm") and not doc.get("bpm"):
            # median is a decent overall BPM for a mix
            updates["bpm"] = int(sorted(bpms)[len(bpms) // 2])

        await db.mixes.update_one(
            {"id": mix_id},
            {"$set": {**updates, "tracks": analyzed, "analysis_status": "done"}},
        )
    except Exception as e:
        logging.getLogger("mixdeck").exception("Analysis failed for %s: %s", mix_id, e)
        await db.mixes.update_one({"id": mix_id}, {"$set": {"analysis_status": "failed"}})
    finally:
        _analysis_locks.pop(mix_id, None)


def _schedule_analysis(mix_id: str) -> None:
    if mix_id in _analysis_locks:
        return
    task = asyncio.create_task(_run_mix_analysis(mix_id))
    _analysis_locks[mix_id] = task


@api_router.post("/admin/mixes/{mix_id}/analyze", dependencies=[Depends(require_admin)])
async def analyze_mix(mix_id: str):
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    if mix_id in _analysis_locks:
        return {"ok": True, "status": "already_running"}
    await db.mixes.update_one({"id": mix_id}, {"$set": {"analysis_status": "pending"}})
    _schedule_analysis(mix_id)
    return {"ok": True, "status": "pending"}


@api_router.get("/mixes/{mix_id}/analysis_status")
async def analysis_status(mix_id: str):
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0, "analysis_status": 1, "bpm": 1, "key": 1, "camelot": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    return {
        "status": doc.get("analysis_status") or "none",
        "bpm": doc.get("bpm"),
        "key": doc.get("key"),
        "camelot": doc.get("camelot"),
    }


def _find_cue(audio: Path) -> Optional[Path]:
    cue = audio.with_suffix(".cue")
    if cue.exists():
        return cue
    # case-insensitive fallback
    for sib in audio.parent.iterdir():
        if sib.is_file() and sib.stem.lower() == audio.stem.lower() and sib.suffix.lower() == ".cue":
            return sib
    return None


def _find_cover(audio: Path) -> Optional[Path]:
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


def _extract_cue_header(content: str) -> tuple[str, str]:
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


@api_router.post("/admin/scan", dependencies=[Depends(require_admin)])
async def scan_directory(body: ScanRequest):
    """Walk a directory and ingest every audio file (with optional matching .cue).

    Idempotent: a file is skipped if a mix with the same source_path already exists.
    Files are referenced in place — no copying, no disk duplication.
    """
    root = Path(body.path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail=f"Path does not exist or is not a directory: {root}")

    # Collect audio files
    audio_files: list[Path] = []
    if body.recursive:
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                audio_files.append(p)
    else:
        for p in root.iterdir():
            if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                audio_files.append(p)

    added = []
    skipped = []
    failed = []

    # Pre-fetch all existing source_paths for O(1) dup check
    existing = set()
    async for d in db.mixes.find({"source_path": {"$ne": None}}, {"source_path": 1, "_id": 0}):
        if d.get("source_path"):
            existing.add(d["source_path"])

    for audio in sorted(audio_files):
        try:
            src = str(audio)
            if src in existing:
                skipped.append({"path": src, "reason": "already_ingested"})
                continue

            # default metadata from filename
            title = audio.stem
            artist = ""
            tracks: list[dict] = []

            cue = _find_cue(audio)
            if cue:
                try:
                    content = cue.read_text(encoding="utf-8", errors="replace")
                except UnicodeDecodeError:
                    content = cue.read_text(encoding="latin-1", errors="replace")
                cue_title, cue_performer = _extract_cue_header(content)
                if cue_title:
                    title = cue_title
                if cue_performer:
                    artist = cue_performer
                tracks = [t.model_dump() for t in parse_cue(content)]

            cover = _find_cover(audio)

            mix = Mix(
                title=title,
                artist=artist,
                genre=body.default_genre or "",
                source_path=src,
                source_cover_path=str(cover) if cover else None,
                tracks=[Track(**t) for t in tracks],
            )
            doc = mix.model_dump()
            await db.mixes.insert_one(doc)

            # Persist the cue file for the record too (helps admin delete behavior)
            if cue:
                try:
                    (CUES_DIR / f"{mix.id}.cue").write_text(
                        cue.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
                    )
                except Exception:
                    pass

            added.append({
                "id": mix.id,
                "title": title,
                "artist": artist,
                "path": src,
                "cue": bool(cue),
                "tracks": len(tracks),
                "cover": bool(cover),
            })
            existing.add(src)
            # queue background analysis (BPM + key) for this newly added mix
            if body.analyze:
                await db.mixes.update_one({"id": mix.id}, {"$set": {"analysis_status": "pending"}})
                _schedule_analysis(mix.id)
        except Exception as e:
            failed.append({"path": str(audio), "error": str(e)})

    return {
        "scanned": len(audio_files),
        "added_count": len(added),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "analysis_queued": len(added) if body.analyze else 0,
        "added": added,
        "skipped": skipped,
        "failed": failed,
        "root": str(root),
    }


# ===== Demo seed =====
@api_router.post("/seed-demo")
async def seed_demo():
    """Seed a demo mix the first time so the player has something to show."""
    existing = await db.mixes.count_documents({})
    if existing > 0:
        return {"ok": True, "skipped": True, "count": existing}
    demo = Mix(
        title="MIDNIGHT DRIVE VOL.01",
        artist="DJ NEONWAVE",
        genre="Synthwave",
        bpm=120,
        description="A continuous mix through neon-lit streets. Pure synthwave bliss.",
        audio_url="https://www.kozco.com/tech/LRMonoPhase4.mp3",
        cover_url="https://images.unsplash.com/photo-1769120061986-a077f35b2569?crop=entropy&cs=srgb&fm=jpg&w=800&q=85",
        duration=192.0,
        tracks=[
            Track(index=1, title="Neon Skyline", artist="The Midnight", start_seconds=0),
            Track(index=2, title="Sunset Cruise", artist="FM-84", start_seconds=48),
            Track(index=3, title="Chrome Dreams", artist="Timecop1983", start_seconds=96),
            Track(index=4, title="Last Light", artist="Gunship", start_seconds=144),
        ],
    )
    await db.mixes.insert_one(demo.model_dump())
    return {"ok": True, "id": demo.id}


# ===== Wire up =====
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mixdeck")


@app.on_event("startup")
async def startup():
    logger.info("MIXDECK API ready. Storage at %s", STORAGE_DIR)


@app.on_event("shutdown")
async def shutdown():
    client.close()
