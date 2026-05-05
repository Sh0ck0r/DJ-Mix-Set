"""Pydantic models for the MIXDECK API. Pure data classes, no I/O."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


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
    key: Optional[str] = None
    camelot: Optional[str] = None
    description: Optional[str] = None
    audio_url: Optional[str] = None
    cover_url: Optional[str] = None


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str


class ScanRequest(BaseModel):
    path: str
    recursive: bool = True
    default_genre: str = ""
    analyze: bool = True  # auto-run BPM + key analysis on every new mix
