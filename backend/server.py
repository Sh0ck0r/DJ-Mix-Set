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


class Mix(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    artist: str = ""
    genre: str = ""
    bpm: Optional[int] = None
    duration: float = 0.0  # seconds
    description: str = ""
    audio_filename: Optional[str] = None  # local file in /storage/audio
    cover_filename: Optional[str] = None
    audio_url: Optional[str] = None  # external streaming url alternative
    cover_url: Optional[str] = None  # external image url alternative
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
            current["title"] = m_title.group(1).strip()
            continue
        m_perf = CUE_PERFORMER_RE.match(line)
        if m_perf:
            current["artist"] = m_perf.group(1).strip()
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
    raise HTTPException(status_code=404, detail="Cover not found")


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
