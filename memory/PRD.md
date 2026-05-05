# MIXDECK - DJ Mix Streaming Platform

## Original Problem Statement
"I would like an App that is both Mobile and Web to play my DJ Mixes and stream them with track listing with the ability to read cue sheet playlists for nonstop mixes and a modern fancy digitized player"

## User Choices
- Uploads: admin panel upload (mp3 / flac primary)
- Cue sheets: standard .cue file parsing
- Hosting: self-hosted on user's own server (local filesystem storage)
- Access: public — anyone can listen; admin required to upload
- Aesthetic: dark neon / cyberpunk player with animated waveform & VU meters

## Personas
- **Admin (DJ/owner)**: uploads mixes, cue sheets, cover art; manages library
- **Listener (public)**: browses, streams, navigates tracklists; mobile + web

## Architecture
- **Backend**: FastAPI + Motor (MongoDB). Local filesystem storage under `/app/backend/storage/{audio,covers,cues}`. JWT-based admin auth with a single shared password (`ADMIN_PASSWORD` env).
- **Streaming**: HTTP Range requests supported for MP3/FLAC via `StreamingResponse` (enables proper seek + large file playback).
- **CUE parser**: regex-based, reads TRACK/TITLE/PERFORMER/INDEX 01 MM:SS:FF and stores an array of `Track` objects on the mix document.
- **Frontend**: React (CRA/Craco) + Tailwind + shadcn/ui, react-router, global `PlayerProvider` context with single HTML5 `<audio>` element + Web Audio `AnalyserNode` for VU meters.

## Implemented (2026-02)
- Mix CRUD (admin: create/update/delete)
- Audio / Cover / CUE sheet upload endpoints with automatic track parsing
- Public range-supported audio streaming endpoint
- Library page with hero, genre filters, search, grid of mix cards
- Mix detail page: cyber "DECK" container with REC light, scanlines, animated canvas waveform, click-to-seek, synchronized cue tracklist, transport controls, VU meters, volume
- Persistent glass mini-player (mobile-friendly) with waveform progress bar, equalizer animation, VU meters
- Admin login + dashboard (drag-drop upload, inline file replacement, delete)
- Demo seed (Synthwave mix + 4 tracks) shown first run

## Implemented (2026-05) — Phase 2: Caching, Real Waveforms, Editor, RSS
- **Redis caching layer** — new `cache.py` module wraps redis-py asyncio. Hot read paths cached: `/api/mixes` list (300s), `/api/mixes/{id}` detail (300s), `/api/mixes/genres` (600s), `/api/mixes/{id}/compatible` (300s), `/api/feed.xml` (600s), waveform peaks (24h). All write paths invalidate via `cache.invalidate_mixes()` — verified across 11 write endpoints. Graceful no-op when `REDIS_URL` is empty/unreachable. Configured via `.env`.
- **Real audio-decoded waveform peaks** — `GET /api/mixes/{id}/waveform` returns ~1200 normalised peak values from a librosa-decoded full audio file. Computed lazily on first request (~1-3s for short audio, scales linearly), persisted to `/storage/waveforms/{id}.json` (~6-10KB), cached in Redis 24h. Frontend `DjConsole` fetches and feeds the `FullWaveform` + `ZoomedWaveform` components — falls back to synthetic if not yet computed.
- **Inline metadata editor** — new `MixEditModal` component opens from each admin row's pencil icon. Edits title/artist/genre/BPM/key/Camelot/description in one place via PATCH. No more delete+re-upload to fix typos.
- **RSS podcast feed** — `GET /api/feed.xml` emits an iTunes/Apple-Podcasts compatible RSS 2.0 feed with proper RFC-822 pubDates, `<itunes:duration>`, `<itunes:image>`, per-mix `<enclosure>` pointing at the streaming endpoint. Library hero exposes a "SUBSCRIBE · RSS PODCAST FEED" button. **70/70 backend tests pass**, zero regressions.
- **Alternating Decks** — track parity (even=A, odd=B) decides which deck is "live" and which is "cued/preview" for the next track. Inactive deck dims and shows the upcoming cover art; on each track transition the active side flips with a 1.5s crossfade. Crossfader on screen drifts toward the live side. CH 1/CH 2 mixer channels light up to match.
- **Draggable JogWheels** — pointer-down on the active disc lets you spin it; 360° of rotation = 30 seconds of audio (CDJ-style). Inactive jog is non-interactive. Touch-friendly via Pointer Events API.
- **Track-art crossfade** on jog wheels — current art fades into the disc smoothly, previous art briefly retained for blend.
- **Deep-seek share links** — `?t=MM:SS` (also `HH:MM:SS` or raw seconds) auto-loads the mix and seeks to the timestamp once metadata is ready. New SHARE LINK button copies a timestamped URL to clipboard.
- **Harmonic recommendations** — `GET /api/mixes/{id}/compatible` finds mixes within ±4 BPM and adjacent Camelot keys (same key, ±1 number, relative major↔minor). Frontend shows a recs row at the bottom of every Mix Detail page. **15/15 new backend tests pass, 0 regressions.**
- **Manual key/camelot override** — MixUpdate now accepts `key` and `camelot` fields so admins can correct analyzer output without touching Mongo.
- **Bulk directory scan** — recursive in-place ingest, zero disk dup, idempotent, admin UI panel with results table.
- **Automatic audio analysis** — librosa + mutagen. Per-track BPM + musical key + Camelot code. Concurrency-limited background task queue. Live ANALYZING→ANALYZED status badges.
- **Full DJ Console redesign** — the DECK section is now a hardware-style console (`XD-01` layout) featuring:
  - Twin **JogWheels** (Deck A playing with rotating album art + progress ring, Deck B previewing next cue point)
  - **Dual CDJ-style waveform** (cyan top + orange bottom stereo bands, zoomed 30s window with center playhead diamond, full-mix overview below with track markers)
  - **4-channel Mixer** with hi/mid/low EQ knobs (knob indicators breathe with analyser band energy), per-channel VU meters + faders
  - **Master volume** + **Crossfader** with tick marks + glowing fader cap
  - **Performance Pads** (8 colored hot-cue pads mapped to first 8 tracks, tinted by Camelot key, one-tap jump-to-track)
  - Lint clean, responsive, mobile-friendly layout

## Tech / Libraries
- Backend: fastapi, motor, pydantic, PyJWT, aiofiles, python-multipart
- Frontend: react-router-dom, axios, sonner, lucide-react, tailwindcss
- Fonts: Unbounded (display), JetBrains Mono (body), Chivo (UI)
- Colors: void #050505, surface #0D0E15, cyan #00F0FF, green #39FF14, red #FF003C

## Backlog (P0/P1/P2)
- P1: Discogs tier-3 artwork fallback (trance/electronic whitelabel coverage beyond iTunes + MusicBrainz)
- P1: Edit mix metadata inline (currently requires delete + re-upload)
- P1: Background/streaming scan progress (for very large libraries 1000+ files)
- P2: RSS / podcast feed auto-export so listeners can subscribe in Apple Podcasts / Overcast
- P2: Share links with deep-seek (`?t=00:12:34`)
- P2: "Also in this genre" row on mix detail
- P2: Drag-to-reorder tracks, manual track list editor
- P2: Waveform from real audio peaks (decode audio to canvas once instead of deterministic synthetic waveform)
- P2: Download-for-offline / mix archive zip
