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

## Implemented (2026-04)
- **Per-track artwork auto-fetch** — iTunes → MusicBrainz + Cover Art Archive → **Discogs** (tier 3, when `DISCOGS_TOKEN` env is set). Cached in Mongo (`track_artwork`), returns `source` field, `?refresh=1` re-queries.
- **Bulk directory scan** (`POST /api/admin/scan`) — recursive, in-place source_path referencing (zero disk dup), idempotent, auto cover detection, admin UI panel with results table.
- **Automatic audio analysis** — every scanned mix auto-queues background `librosa` analysis. Per-track **BPM + musical key + Camelot code** (8A, 4B etc) detected by seeking to each track's start_seconds and analyzing a 45s window. Uses `mutagen` for fast metadata (duration, ID3 BPM tag, genre). Concurrency limited to `ANALYSIS_CONCURRENCY` (default 2) so bulk scans don't thrash the server. Endpoints: `POST /api/admin/mixes/{id}/analyze`, `GET /api/mixes/{id}/analysis_status`. Admin UI shows live ANALYZING → ANALYZED badges with polling. Cue tracklist on the DECK page renders per-track BPM + Camelot badges. 41/41 backend tests pass.

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
