"""Shared application state: db connection, storage paths, env config.

Imported by all service modules (cue, artwork, analysis_service, scan_service)
and the routers in server.py. Keeps cross-module concerns in one place so
nothing has to reach into server.py to find shared resources.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ===== Storage paths =====
STORAGE_DIR = ROOT_DIR / "storage"
AUDIO_DIR = STORAGE_DIR / "audio"
COVERS_DIR = STORAGE_DIR / "covers"
CUES_DIR = STORAGE_DIR / "cues"
WAVEFORMS_DIR = STORAGE_DIR / "waveforms"
for d in (AUDIO_DIR, COVERS_DIR, CUES_DIR, WAVEFORMS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ===== Auth =====
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "mixdeck2026")
JWT_SECRET = os.environ.get("JWT_SECRET", "mixdeck-secret-change-me")
JWT_ALGO = "HS256"

# ===== MongoDB =====
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# ===== Misc =====
DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "").strip()
LONG_TTL_WF = 86400  # waveform peaks - 24h
