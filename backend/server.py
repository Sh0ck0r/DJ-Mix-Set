"""MIXDECK backend - DJ mix streaming with cue sheet support.

Slim composer: hosts the FastAPI app + the public API routes. Heavy logic
lives in dedicated modules:

- models.py            - Pydantic request/response types
- state.py             - db client, storage paths, env config
- cue.py               - CUE parsing + cover/cue file discovery
- artwork.py           - iTunes / MusicBrainz / Discogs artwork cascade
- analysis_service.py  - background BPM + key analysis (librosa)
- scan_service.py      - background bulk directory scan
- audio_analysis.py    - librosa primitives (read_audio_info, analyze_segment, peaks)
- cache.py             - Redis caching wrapper
"""
from datetime import datetime, timezone, timedelta
import asyncio
import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import List, Optional
from xml.sax.saxutils import escape as xml_escape

import aiofiles
import httpx  # noqa: F401  -- artwork.py uses it; kept here for import-side-effects parity
import jwt
from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Depends, Request
from fastapi.responses import StreamingResponse, FileResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

from audio_analysis import compute_waveform_peaks
from cache import cache
from artwork import lookup_track_artwork
from cue import parse_cue
from lyrics_service import lookup_lyrics, set_manual as set_manual_lyrics
from models import (
    LoginRequest,
    LoginResponse,
    Mix,
    MixCreate,
    MixUpdate,
    ScanRequest,
    Track,
)
from state import (
    ADMIN_PASSWORD,
    AUDIO_DIR,
    COVERS_DIR,
    CUES_DIR,
    JWT_ALGO,
    JWT_SECRET,
    LONG_TTL_WF,
    STORAGE_DIR,
    WAVEFORMS_DIR,
    client,
    db,
)
import analysis_service
import scan_service
import llm_service
import llm_bulk_service
import settings_service
import transcription_service
import os

app = FastAPI(title="MIXDECK API")
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)


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


# ===== Track artwork lookup =====
@api_router.get("/tracks/artwork")
async def track_artwork(artist: str = "", title: str = "", refresh: int = 0):
    """Cascading artwork lookup: iTunes -> MusicBrainz -> Discogs. Cached."""
    return await lookup_track_artwork(artist, title, refresh=bool(refresh))


# ===== Lyrics lookup (LRCLIB) =====
@api_router.get("/tracks/lyrics")
async def track_lyrics(
    artist: str = "",
    title: str = "",
    duration: Optional[float] = None,
    refresh: int = 0,
):
    """Synced-lyrics lookup via LRCLIB. Returns {synced, plain, source, found, cached}."""
    return await lookup_lyrics(artist, title, duration, refresh=bool(refresh))


class LyricsManualBody(BaseModel):
    artist: str
    title: str
    duration: Optional[float] = None
    plain: str = ""
    synced: str = ""  # raw LRC text - we parse it server-side


@api_router.post("/admin/tracks/lyrics", dependencies=[Depends(require_admin)])
async def set_manual_track_lyrics(body: LyricsManualBody):
    if not body.artist and not body.title:
        raise HTTPException(status_code=400, detail="artist or title required")
    return await set_manual_lyrics(body.artist, body.title, body.duration, body.plain, body.synced)


# ===== Public routes =====
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
async def list_mixes(q: Optional[str] = None, genre: Optional[str] = None, tag: Optional[str] = None):
    cache_key = f"mixes:list:{q or ''}:{genre or ''}:{tag or ''}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return [Mix(**d) for d in cached]
    query: dict = {}
    if genre:
        query["genre"] = genre
    if tag:
        query["tags"] = tag
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"artist": {"$regex": q, "$options": "i"}},
            {"genre": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
        ]
    docs = await db.mixes.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    await cache.set(cache_key, docs, ttl=300)
    return [Mix(**d) for d in docs]


@api_router.get("/mixes/tags")
async def list_tags():
    """Distinct tag list with counts, sorted by popularity. Used by the library tag-cloud."""
    cached = await cache.get("tags:list")
    if cached is not None:
        return cached
    pipeline = [
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1, "_id": 1}},
        {"$limit": 80},
    ]
    rows = []
    async for r in db.mixes.aggregate(pipeline):
        if r.get("_id"):
            rows.append({"tag": r["_id"], "count": int(r.get("count") or 0)})
    payload = {"tags": rows}
    await cache.set("tags:list", payload, ttl=600)
    return payload


@api_router.get("/mixes/genres")
async def list_genres():
    cached = await cache.get("genres")
    if cached is not None:
        return cached
    genres = await db.mixes.distinct("genre")
    payload = {"genres": [g for g in genres if g]}
    await cache.set("genres", payload, ttl=600)
    return payload


@api_router.get("/mixes/{mix_id}", response_model=Mix)
async def get_mix(mix_id: str):
    cache_key = f"mix:{mix_id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return Mix(**cached)
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    await cache.set(cache_key, doc, ttl=300)
    return Mix(**doc)


@api_router.post("/mixes/{mix_id}/play")
async def increment_play(mix_id: str):
    res = await db.mixes.update_one({"id": mix_id}, {"$inc": {"play_count": 1}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Mix not found")
    await cache.invalidate_mixes()
    return {"ok": True}


@api_router.get("/mixes/{mix_id}/compatible", response_model=List[Mix])
async def compatible_mixes(mix_id: str, limit: int = 8):
    cache_key = f"compatible:{mix_id}:{limit}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return [Mix(**d) for d in cached]
    src = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Mix not found")
    src_bpm = src.get("bpm")
    src_cam = (src.get("camelot") or "").upper().strip()
    src_tags: set[str] = set(src.get("tags") or [])

    compat_keys: set[str] = set()
    if src_cam and len(src_cam) >= 2:
        try:
            num = int(src_cam[:-1])
            mode = src_cam[-1]
            other = "B" if mode == "A" else "A"
            for n in (num, ((num - 2) % 12) + 1, (num % 12) + 1):
                compat_keys.add(f"{n}{mode}")
            compat_keys.add(f"{num}{other}")
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
        # Tag overlap: 1.5 points per shared tag (capped at 6)
        c_tags = set(c.get("tags") or [])
        if src_tags and c_tags:
            overlap = src_tags & c_tags
            score += min(6.0, 1.5 * len(overlap))
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda t: -t[0])
    result_docs = [c for _, c in scored[:limit]]
    await cache.set(cache_key, result_docs, ttl=300)
    return [Mix(**c) for c in result_docs]


# ===== Admin: Mix CRUD =====
@api_router.post("/admin/mixes", response_model=Mix, dependencies=[Depends(require_admin)])
async def create_mix(body: MixCreate):
    mix = Mix(**body.model_dump())
    await db.mixes.insert_one(mix.model_dump())
    await cache.invalidate_mixes()
    return mix


@api_router.patch("/admin/mixes/{mix_id}", response_model=Mix, dependencies=[Depends(require_admin)])
async def update_mix(mix_id: str, body: MixUpdate):
    raw = body.model_dump(exclude_unset=True)
    update: dict = {}
    for k, v in raw.items():
        if v is None:
            continue
        if k == "tracks":
            update[k] = [
                t if isinstance(t, dict) else t.model_dump()
                for t in v
            ]
        else:
            update[k] = v
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = await db.mixes.update_one({"id": mix_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Mix not found")
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    await cache.invalidate_mixes()
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
    wf_path = WAVEFORMS_DIR / f"{mix_id}.json"
    if wf_path.exists():
        wf_path.unlink()
    await db.mixes.delete_one({"id": mix_id})
    await cache.invalidate_mixes()
    return {"ok": True}


# ===== Admin: Uploads =====
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
    for old in AUDIO_DIR.glob(f"{mix_id}.*"):
        old.unlink()
    out_path = AUDIO_DIR / out_name
    await _save_upload(file, out_path)
    await db.mixes.update_one(
        {"id": mix_id}, {"$set": {"audio_filename": out_name, "audio_url": None}}
    )
    await cache.invalidate_mixes()
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
    await cache.invalidate_mixes()
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
    await cache.invalidate_mixes()
    return {"ok": True, "track_count": len(tracks), "tracks": [t.model_dump() for t in tracks]}


@api_router.post("/admin/mixes/{mix_id}/tracks", dependencies=[Depends(require_admin)])
async def set_tracks(mix_id: str, tracks: List[Track]):
    res = await db.mixes.update_one(
        {"id": mix_id}, {"$set": {"tracks": [t.model_dump() for t in tracks]}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Mix not found")
    await cache.invalidate_mixes()
    return {"ok": True}


@api_router.post("/admin/mixes/{mix_id}/duration", dependencies=[Depends(require_admin)])
async def set_duration(mix_id: str, duration: float = Form(...)):
    res = await db.mixes.update_one({"id": mix_id}, {"$set": {"duration": float(duration)}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Mix not found")
    await cache.invalidate_mixes()
    return {"ok": True}


@api_router.post("/mixes/{mix_id}/duration")
async def public_set_duration(mix_id: str, duration: float = Form(...)):
    """Browser sets the audio duration once metadata loads (only if currently zero)."""
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    if not doc.get("duration"):
        await db.mixes.update_one({"id": mix_id}, {"$set": {"duration": float(duration)}})
        await cache.invalidate_mixes()
    return {"ok": True}


# ===== Streaming with HTTP Range =====
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


# ===== Real waveform peaks (decoded once, cached on disk) =====
@api_router.get("/mixes/{mix_id}/waveform")
async def get_waveform(mix_id: str):
    """Return a downsampled peak array for the mix audio. Computed lazily."""
    cache_key = f"waveform:{mix_id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    wf_path = WAVEFORMS_DIR / f"{mix_id}.json"
    if wf_path.exists():
        try:
            payload = json.loads(wf_path.read_text(encoding="utf-8"))
            await cache.set(cache_key, payload, ttl=LONG_TTL_WF)
            return payload
        except Exception:
            wf_path.unlink(missing_ok=True)

    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    src = doc.get("source_path") or (str(AUDIO_DIR / doc["audio_filename"]) if doc.get("audio_filename") else None)
    if not src or not Path(src).exists():
        return {"peaks": [], "ready": False}

    loop = asyncio.get_event_loop()
    peaks = await loop.run_in_executor(None, compute_waveform_peaks, src, 1200)
    if not peaks:
        return {"peaks": [], "ready": False}
    payload = {"peaks": peaks, "ready": True, "bars": len(peaks)}
    try:
        wf_path.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass
    await cache.set(cache_key, payload, ttl=LONG_TTL_WF)
    return payload


# ===== Admin: Bulk scan & analysis =====
@api_router.post("/admin/scan", dependencies=[Depends(require_admin)])
async def scan_directory(body: ScanRequest):
    """Kick off a background scan and return a task_id for polling progress.

    Idempotent: a file is skipped if a mix with the same source_path already exists.
    Files are referenced in place - no copying, no disk duplication.
    """
    root = Path(body.path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail=f"Path does not exist or is not a directory: {root}")
    task_id = scan_service.start_scan(body)
    return {"task_id": task_id, "status": "running"}


@api_router.get("/admin/scan/{task_id}", dependencies=[Depends(require_admin)])
async def scan_task_status(task_id: str):
    state = scan_service.get_task(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Scan task not found or expired")
    return state


@api_router.get("/admin/analysis_overview", dependencies=[Depends(require_admin)])
async def analysis_overview():
    """Library-wide BPM + key analysis status counters."""
    counts = {"none": 0, "pending": 0, "running": 0, "done": 0, "failed": 0}
    async for d in db.mixes.find({}, {"analysis_status": 1, "_id": 0}):
        s = d.get("analysis_status") or "none"
        counts[s] = counts.get(s, 0) + 1
    total = sum(counts.values())
    return {"counts": counts, "total": total, "active_workers": analysis_service.active_workers()}


@api_router.post("/admin/analyze_all", dependencies=[Depends(require_admin)])
async def analyze_all(force: bool = False):
    """Re-queue analysis for every mix in the library that has an audio source."""
    queued = 0
    skipped = 0
    async for d in db.mixes.find({}, {"id": 1, "analysis_status": 1, "source_path": 1, "audio_filename": 1, "_id": 0}):
        if not (d.get("source_path") or d.get("audio_filename")):
            skipped += 1
            continue
        if not force and d.get("analysis_status") == "done":
            skipped += 1
            continue
        await db.mixes.update_one({"id": d["id"]}, {"$set": {"analysis_status": "pending"}})
        analysis_service.schedule_analysis(d["id"])
        queued += 1
    if queued:
        await cache.invalidate_mixes()
    return {"queued": queued, "skipped": skipped}


@api_router.post("/admin/mixes/{mix_id}/analyze", dependencies=[Depends(require_admin)])
async def analyze_mix(mix_id: str):
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    if analysis_service.is_running(mix_id):
        return {"ok": True, "status": "already_running"}
    await db.mixes.update_one({"id": mix_id}, {"$set": {"analysis_status": "pending"}})
    analysis_service.schedule_analysis(mix_id)
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


# ===== Admin: App settings (LLM endpoint, model, etc) =====
class SettingsUpdate(BaseModel):
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    llm_enabled: Optional[bool] = None
    clear_api_key: Optional[bool] = None
    whisper_base_url: Optional[str] = None
    whisper_api_key: Optional[str] = None
    whisper_model: Optional[str] = None
    whisper_enabled: Optional[bool] = None
    whisper_language: Optional[str] = None
    clear_whisper_api_key: Optional[bool] = None


@api_router.get("/admin/settings", dependencies=[Depends(require_admin)])
async def get_app_settings():
    return await settings_service.get_public_settings()


@api_router.patch("/admin/settings", dependencies=[Depends(require_admin)])
async def patch_app_settings(body: SettingsUpdate):
    patch = body.model_dump(exclude_unset=True)
    return await settings_service.update_settings(patch)


@api_router.post("/admin/settings/test_llm", dependencies=[Depends(require_admin)])
async def test_llm():
    """Pings the configured LLM endpoint (GET /v1/models) to verify reachability + auth."""
    return await llm_service.health_check()


@api_router.post("/admin/settings/test_whisper", dependencies=[Depends(require_admin)])
async def test_whisper():
    """Pings the configured Whisper endpoint to verify reachability + auth."""
    return await transcription_service.health_check()


# ===== Per-track Whisper transcription =====
@api_router.post("/admin/mixes/{mix_id}/transcribe_track/{track_index}", dependencies=[Depends(require_admin)])
async def transcribe_one_track(mix_id: str, track_index: int):
    """Re-run Whisper on a single track from a mix. Smart-merges with LRCLIB
    (uses LRCLIB text + Whisper timing) when LRCLIB has the track.
    """
    from lyrics_service import _cache_key as lyrics_cache_key
    from datetime import datetime, timezone

    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    tracks = doc.get("tracks") or []
    if track_index < 0 or track_index >= len(tracks):
        raise HTTPException(status_code=404, detail="Track index out of range")
    t = tracks[track_index]
    artist = (t.get("artist") or "").strip()
    title = (t.get("title") or "").strip()
    if not (artist or title):
        raise HTTPException(status_code=400, detail="Track is missing artist + title")

    src = doc.get("source_path") or (str(AUDIO_DIR / doc["audio_filename"]) if doc.get("audio_filename") else None)
    if not src or not Path(src).exists():
        raise HTTPException(status_code=400, detail="Mix has no readable audio source")

    start = float(t.get("start_seconds") or 0.0)
    next_start = (
        float(tracks[track_index + 1]["start_seconds"]) if track_index + 1 < len(tracks) else float(doc.get("duration") or start + 240)
    )
    duration = max(5.0, min(next_start - start, 480.0))

    from lyrics_service import lookup_lyrics
    try:
        existing = await lookup_lyrics(artist, title, duration)
        lrclib_synced = existing.get("synced") or []
        lines, words = await transcription_service.transcribe_with_word_timing(src, start, duration)
    except transcription_service.WhisperNotConfigured as e:
        raise HTTPException(status_code=400, detail=str(e))
    except transcription_service.WhisperError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not lines:
        raise HTTPException(status_code=502, detail="Whisper returned no usable transcription")

    if lrclib_synced:
        final_synced = transcription_service.force_align(lrclib_synced, words)
        source = "whisper-aligned"
    else:
        final_synced = lines
        source = "whisper"
    key = lyrics_cache_key(artist, title, duration)
    await db.track_lyrics.update_one(
        {"key": key},
        {"$set": {
            "key": key,
            "artist": artist,
            "title": title,
            "duration": int(round(duration)),
            "synced": final_synced,
            "plain": "\n".join(line["text"] for line in final_synced),
            "source": source,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {
        "lines": len(final_synced),
        "source": source,
        "artist": artist,
        "title": title,
    }


@api_router.post("/admin/mixes/{mix_id}/generate_description", dependencies=[Depends(require_admin)])
async def generate_mix_description(mix_id: str):
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    try:
        description = await llm_service.write_mix_description(doc)
    except llm_service.LLMNotConfigured as e:
        raise HTTPException(status_code=400, detail=str(e))
    except llm_service.LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not description:
        raise HTTPException(status_code=502, detail="LLM returned empty response")
    return {"description": description, "mix_id": mix_id}


@api_router.post("/admin/mixes/{mix_id}/generate_tags", dependencies=[Depends(require_admin)])
async def generate_mix_tags(mix_id: str):
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    try:
        tags = await llm_service.write_mix_tags(doc)
    except llm_service.LLMNotConfigured as e:
        raise HTTPException(status_code=400, detail=str(e))
    except llm_service.LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not tags:
        raise HTTPException(status_code=502, detail="LLM returned no usable tags")
    await db.mixes.update_one({"id": mix_id}, {"$set": {"tags": tags}})
    await cache.invalidate_mixes()
    return {"tags": tags, "mix_id": mix_id}


# ===== Bulk LLM operations: AUTO-TAG ALL / AUTO-DESCRIBE ALL =====
@api_router.post("/admin/llm/auto_tag_all", dependencies=[Depends(require_admin)])
async def auto_tag_all(force: bool = False):
    """Queue tag generation for every mix that doesn't have tags (force=true re-tags all)."""
    cfg = await settings_service.get_llm_config()
    if cfg is None:
        raise HTTPException(status_code=400, detail="LLM is disabled or not configured. Set it in Admin → Settings.")
    task_id = llm_bulk_service.start_bulk("tags", force=force)
    return {"task_id": task_id, "kind": "tags", "status": "running", "force": bool(force)}


@api_router.post("/admin/llm/auto_describe_all", dependencies=[Depends(require_admin)])
async def auto_describe_all(force: bool = False):
    """Queue description generation for every mix that doesn't have one (force=true re-writes all)."""
    cfg = await settings_service.get_llm_config()
    if cfg is None:
        raise HTTPException(status_code=400, detail="LLM is disabled or not configured. Set it in Admin → Settings.")
    task_id = llm_bulk_service.start_bulk("descriptions", force=force)
    return {"task_id": task_id, "kind": "descriptions", "status": "running", "force": bool(force)}


@api_router.get("/admin/llm/bulk/{task_id}", dependencies=[Depends(require_admin)])
async def bulk_llm_status(task_id: str):
    state = llm_bulk_service.get_task(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Bulk task not found or expired")
    return state


@api_router.get("/admin/llm/bulk", dependencies=[Depends(require_admin)])
async def list_bulk_tasks():
    return {"tasks": llm_bulk_service.list_active()[:30]}


# ===== Public OpenGraph share page =====
@api_router.get("/embed/{mix_id}")
async def embed_player(mix_id: str, request: Request):
    """A standalone, framework-free HTML5 audio player for embedding in
    external sites (blog, Linktree, SoundCloud profile, etc). Designed for
    a 600x180 iframe but degrades to any size.
    """
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    base = str(request.base_url).rstrip("/")
    title = doc.get("title") or "Untitled"
    artist = doc.get("artist") or "MIXDECK"
    duration = float(doc.get("duration") or 0)
    bpm = doc.get("bpm")
    cam = doc.get("camelot")
    play_url = f"{base}/mix/{mix_id}"
    stream_url = f"{base}/api/stream/{mix_id}"
    if doc.get("cover_url"):
        cover = doc["cover_url"]
    elif doc.get("cover_filename") or doc.get("source_cover_path"):
        cover = f"{base}/api/cover/{mix_id}"
    else:
        cover = ""
    e = xml_escape

    meta_bits = []
    if bpm:
        meta_bits.append(f"{bpm} BPM")
    if cam:
        meta_bits.append(f"KEY {cam}")
    if duration:
        m, s = int(duration // 60), int(duration % 60)
        meta_bits.append(f"{m}:{s:02d}")
    meta = " · ".join(meta_bits)

    cover_block = (
        f'<img src="{e(cover)}" alt="cover">'
        if cover
        else '<div class="ph"></div>'
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · MIXDECK Embed</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{height:100%;background:#050505;color:#e6e6e6;
    font-family:ui-monospace,'JetBrains Mono','Fira Code',Menlo,monospace;
    overflow:hidden;}}
  .wrap{{display:flex;height:100%;border:1px solid #1A1D2E;background:#0a0c14;
    background-image:linear-gradient(rgba(0,240,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,240,255,.025) 1px,transparent 1px);
    background-size:24px 24px;}}
  .art{{width:140px;flex-shrink:0;background:#000;display:flex;align-items:center;justify-content:center;border-right:1px solid #1A1D2E;overflow:hidden;}}
  .art img{{width:100%;height:100%;object-fit:cover;}}
  .ph{{width:100%;height:100%;background:linear-gradient(135deg,#0a0c14,#050505);}}
  .body{{flex:1;padding:14px 16px;display:flex;flex-direction:column;min-width:0;gap:8px;}}
  .label{{font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#00F0FF}}
  .title{{font-weight:900;font-size:18px;color:#fff;letter-spacing:-.01em;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
  .artist{{font-size:12px;color:#a1a1aa;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .meta{{font-size:11px;color:#71717a;letter-spacing:.06em;}}
  audio{{width:100%;height:34px;outline:none;filter:invert(1) hue-rotate(180deg) saturate(.6);}}
  .footer{{display:flex;align-items:center;justify-content:space-between;margin-top:auto;}}
  a.brand{{color:#00F0FF;text-decoration:none;font-size:10px;letter-spacing:.18em;
    text-transform:uppercase;border:1px solid rgba(0,240,255,.3);padding:4px 8px;
    transition:all .15s;}}
  a.brand:hover{{background:rgba(0,240,255,.08);border-color:#00F0FF;text-shadow:0 0 8px #00F0FF;}}
  .pulse{{display:inline-block;width:6px;height:6px;border-radius:50%;background:#FF003C;margin-right:6px;
    box-shadow:0 0 8px #FF003C;animation:p 1.4s infinite;}}
  @keyframes p{{50%{{opacity:.3}}}}
  @media(max-width:480px){{
    .wrap{{flex-direction:column}}
    .art{{width:100%;height:120px;border-right:0;border-bottom:1px solid #1A1D2E;}}
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="art">{cover_block}</div>
  <div class="body">
    <div class="label"><span class="pulse"></span>MIXDECK</div>
    <div class="title">{e(title)}</div>
    <div class="artist">{e(artist)}</div>
    <div class="meta">{e(meta)}</div>
    <audio controls preload="metadata" src="{e(stream_url)}"></audio>
    <div class="footer">
      <a class="brand" href="{e(play_url)}" target="_blank" rel="noopener">OPEN ON MIXDECK ▸</a>
    </div>
  </div>
</div>
</body>
</html>"""
    return Response(content=html, media_type="text/html; charset=utf-8")


# ===== Public OpenGraph share page =====
@api_router.get("/share/{mix_id}")
async def share_page(mix_id: str, request: Request, t: Optional[str] = None):
    """Returns a tiny HTML page with OpenGraph + Twitter card tags so links
    pasted in Discord / iMessage / Twitter / Slack render a rich preview.
    Real users get auto-redirected to the React player via meta-refresh.
    """
    doc = await db.mixes.find_one({"id": mix_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Mix not found")
    base = str(request.base_url).rstrip("/")
    title = doc.get("title") or "MIXDECK"
    artist = doc.get("artist") or ""
    desc = doc.get("description") or ""
    if not desc:
        # Build a fallback description from BPM/key/duration
        bits = []
        if doc.get("bpm"):
            bits.append(f"{doc['bpm']} BPM")
        if doc.get("camelot"):
            bits.append(f"Key {doc['camelot']}")
        if doc.get("duration"):
            mins = int(doc["duration"] // 60)
            bits.append(f"{mins} min")
        if doc.get("genre"):
            bits.append(doc["genre"])
        desc = " · ".join(bits) or "Continuous DJ mix"
    full_title = f"{title}{f' — {artist}' if artist else ''} · MIXDECK"

    if doc.get("cover_url"):
        cover = doc["cover_url"]
    elif doc.get("cover_filename") or doc.get("source_cover_path"):
        cover = f"{base}/api/cover/{mix_id}"
    else:
        cover = f"{base}/favicon.png"

    qs = f"?t={t}" if t else ""
    player_url = f"{base}/mix/{mix_id}{qs}"
    e = xml_escape  # alias
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{e(full_title)}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:type" content="music.song">
<meta property="og:site_name" content="MIXDECK">
<meta property="og:title" content="{e(full_title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{e(cover)}">
<meta property="og:url" content="{e(player_url)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(full_title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{e(cover)}">
<meta http-equiv="refresh" content="0;url={e(player_url)}">
<style>
body{{background:#050505;color:#e6e6e6;font-family:monospace;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
a{{color:#00F0FF}}
</style>
</head>
<body>
<p>Loading <a href="{e(player_url)}">{e(title)}</a> …</p>
</body>
</html>"""
    return Response(content=html, media_type="text/html; charset=utf-8")


# ===== RSS Podcast feed =====
@api_router.get("/feed.xml")
async def rss_feed(request: Request):
    """iTunes-compatible RSS 2.0 podcast feed for all mixes with audio."""
    cached = await cache.get("rss:feed")
    if cached:
        return Response(content=cached, media_type="application/rss+xml")
    docs = await db.mixes.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    base = str(request.base_url).rstrip("/")

    def item_url(m):
        return f"{base}/api/stream/{m['id']}"

    def cover(m):
        if m.get("cover_url"):
            return m["cover_url"]
        if m.get("cover_filename") or m.get("source_cover_path"):
            return f"{base}/api/cover/{m['id']}"
        return ""

    def length(m):
        return int(m.get("duration") or 0)

    items_xml = []
    for m in docs:
        if not (m.get("audio_filename") or m.get("audio_url") or m.get("source_path")):
            continue
        title = xml_escape(m.get("title") or "Untitled")
        author = xml_escape(m.get("artist") or "MIXDECK")
        desc = xml_escape(m.get("description") or "")
        guid = xml_escape(m["id"])
        enc_url = xml_escape(item_url(m))
        cv = xml_escape(cover(m))
        try:
            dt = datetime.fromisoformat(m.get("created_at") or "")
        except (ValueError, TypeError):
            dt = datetime.now(timezone.utc)
        pub = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        items_xml.append(f"""
    <item>
      <title>{title}</title>
      <itunes:author>{author}</itunes:author>
      <itunes:summary>{desc}</itunes:summary>
      <description>{desc}</description>
      <guid isPermaLink="false">{guid}</guid>
      <pubDate>{pub}</pubDate>
      <enclosure url="{enc_url}" type="audio/mpeg" length="0"/>
      <itunes:duration>{length(m)}</itunes:duration>
      <itunes:image href="{cv}"/>
      <link>{base}/mix/{guid}</link>
    </item>""")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>MIXDECK · Continuous DJ Mixes</title>
    <link>{base}</link>
    <atom:link href="{base}/api/feed.xml" rel="self" type="application/rss+xml"/>
    <language>en-us</language>
    <description>Continuous DJ mixes streamed from MIXDECK. Each episode is a full set with track-by-track cue points.</description>
    <itunes:author>MIXDECK</itunes:author>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="Music"/>
    <itunes:image href="{base}/favicon.png"/>
    {''.join(items_xml)}
  </channel>
</rss>"""
    await cache.set("rss:feed", xml, ttl=600)
    return Response(content=xml, media_type="application/rss+xml")


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
    await cache.connect()
    logger.info("MIXDECK API ready. Storage at %s", STORAGE_DIR)


@app.on_event("shutdown")
async def shutdown():
    await cache.disconnect()
    client.close()
