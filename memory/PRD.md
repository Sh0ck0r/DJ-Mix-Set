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
- **Harmonic recommendations** — `GET /api/mixes/{id}/compatible` finds mixes within ±4 BPM and adjacent Camelot keys (same key, ±1 number, relative major↔minor). Frontend shows a recs row at the bottom of every Mix Detail page.
- **Manual key/camelot override** — MixUpdate now accepts `key` and `camelot` fields so admins can correct analyzer output without touching Mongo.
- **Bulk directory scan** — recursive in-place ingest, zero disk dup, idempotent, admin UI panel with results table.
- **Automatic audio analysis** — librosa + mutagen. Per-track BPM + musical key + Camelot code. Concurrency-limited background task queue. Live ANALYZING→ANALYZED status badges.
- **Full DJ Console redesign** — XD-01-style twin jogwheels, dual CDJ waveform, 4-channel mixer, master volume + crossfader, performance pads.

## Implemented (2026-02 — Phase 3: Background Scan + Library-Wide Analysis Overview)
- **Background scan task with live progress** — `POST /api/admin/scan` now returns `{task_id, status:"running"}` immediately and runs the directory walk + ingest in an asyncio task. New `GET /api/admin/scan/{task_id}` returns full live state (`processed`, `total`, `current_file`, `added/skipped/failed` counts + arrays, terminal `status`). Fast path validation (invalid path → 400 sync). Old finished tasks auto-culled (keeps last 20). No more HTTP timeouts on massive libraries.
- **Live progress UI** — `BulkScan.jsx` polls every 600ms, shows a glowing progress bar with `processed/total`, current filename, and live `added/skipped/failed` counters. Final state renders the same imported/skipped/failed result tables as before.
- **Analysis overview** — `GET /api/admin/analysis_overview` returns library-wide BPM+Key analysis counters (`{counts:{none,pending,running,done,failed}, total, active_workers}`).
- **Test suite migration** — added `tests/_scan_helpers.py::scan_and_wait()` polling helper. Migrated `test_scan.py`, `test_analysis.py`, `test_phase2.py` to the new contract. **78/78 backend tests pass** (was 70/70), zero regressions. New `test_bg_scan.py` covers auth, validation, polling, idempotency, cache invalidation, and overview shape.

## Implemented (2026-02 — Phase 4: Analysis Overview UI + Stream Bug Fix + Backend Refactor)
- **AnalysisOverviewBar** — new `/app/frontend/src/components/AnalysisOverviewBar.jsx` renders a 6-cell live header strip on the AdminDashboard (LIBRARY · ANALYZED · RUNNING · QUEUED · FAILED · WORKERS) with a glowing green progress bar across the bottom and an `ANALYZE ALL` button that calls `POST /api/admin/analyze_all`. Auto-polls every 4s while any work is pending/running.
- **Stream/cover URL bug fix** — `streamUrl()` and `coverUrl()` in `lib/api.js` only returned a URL when `audio_filename`/`cover_filename` was set, leaving every FTP-scanned mix (which only has `source_path`/`source_cover_path`) unplayable in the UI even though the backend stream endpoint handled it. Both helpers now fall back to `source_path`/`source_cover_path`. `MixCard.jsx` and `MixDetail.jsx` `playable` checks updated.
- **Jog-wheel scrub verified** — direct Playwright e2e: 60° clockwise drag = +5.48s, 60° counter-clockwise = −4.27s. Math proven: `seconds = (angleDelta / 360) * 30`, throttled to `player.seek` every >0.25s, final seek on drag end. Added a tiny dev-only `window.__mixdeckAudio` hook in `PlayerContext.jsx` for e2e/debug access.
- **server.py refactored 1290 → 697 lines** (46% reduction). Extracted into 6 focused modules: `state.py` (db + paths + env), `models.py` (Pydantic types), `cue.py` (parser + cover/cue file discovery), `artwork.py` (iTunes/MusicBrainz/Discogs cascade), `analysis_service.py` (background BPM/Key + semaphore), `scan_service.py` (background bulk-scan task tracker). API contract identical, **78/78 backend tests still pass**, full frontend e2e regression clean (testing_agent_v3_fork iter 8: 100%/100%, zero issues).

## Implemented (2026-02 — Phase 5: Local LLM + Mobile UX + Social Sharing)
- **Local LLM integration (SGLang/Ollama/vLLM/anything OpenAI-compatible)** — new `llm_service.py` speaks the standard `/v1/chat/completions` + `/v1/models` endpoints. Reads endpoint, model, and API key dynamically from the `settings` MongoDB collection so admin can swap models at runtime without restarting. Defaults seeded from `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` env on first run.
- **Admin Settings page** (`/admin/settings`) — `AdminSettings.jsx`: fields for BASE URL, MODEL, optional API key (masked), ENABLED toggle, SAVE + TEST CONNECTION. Test pings `/v1/models` and surfaces a green/red status panel with the available model list. New endpoints: `GET /api/admin/settings`, `PATCH /api/admin/settings`, `POST /api/admin/settings/test_llm`.
- **AI "Generate Description" button** on the mix edit modal — `POST /api/admin/mixes/{id}/generate_description` builds a prompt from the mix's tracklist + per-track BPM/key data and calls the local LLM to write a 2–4 sentence Mixmag-style blurb. Failure modes (LLM disabled / unreachable / malformed response) surface as toast errors with the actual upstream error text.
- **OpenGraph share previews** — `GET /api/share/{mix_id}` returns a tiny HTML page with `og:title`, `og:description`, `og:image`, `og:url`, `twitter:card`, and a meta-refresh redirect to the React player. Discord/iMessage/Twitter/Slack now render rich preview cards. The share button on `MixDetail` now copies this URL (preserves `?t=NN` deep-seek).
- **MediaSession API integration** — phone lock-screen + Bluetooth + CarPlay + Android Auto controls. `PlayerContext` sets `navigator.mediaSession.metadata` with title/artist/album/artwork (live track art via `coverUrl`), wires up `play`, `pause`, `seekbackward (15s)`, `seekforward (15s)`, `seekto`, `previoustrack`, `nexttrack` action handlers, and updates `playbackState` + `setPositionState` so the OS scrubber tracks correctly.
- **Resume where you left off** — every 5s while listening (and on pause/unmount) the player saves `{mixId: {t, at, title}}` to `localStorage["mixdeck_resume"]`. On revisit a green banner shows "RESUME at 32:14" with one-click resume (loads mix + seeks) and a dismiss button. Auto-clears when listener finishes the mix (within 30s of end).
- **Test results** — testing_agent_v3_fork iter 9: backend 100% (85/85 new + 8 expected skipped Redis tests), frontend 100% (15/15 UI assertions). Zero issues, zero action items after the MediaSession artwork polish fix.

## Implemented (2026-02 — Phase 6: Long-Mix Optimization Pack)
Tuned for the user's actual production use case (TRANCEHYPE2025 = 9.3 hours / 100+ tracks, deployed live at shock.tube).
- **Tracklist search/filter** — `CueTrackList` now shows a search box (only when >8 tracks). Filters by title/artist/BPM/Camelot/key. Live result count `12/127`. Clear button. Empty-state message for no matches.
- **Performance pads pagination** — `PerformancePads` now banks 8 tracks at a time with PREV/NEXT arrows + page-dot indicators + label `BANK 3/13 · TRX 17-24/127`. Auto-flips to the bank containing the currently-playing track. Pads on inactive ranks render disabled/empty so layout stays stable.
- **AI mood/vibe tags** — new `POST /api/admin/mixes/{id}/generate_tags` endpoint uses the local LLM with a JSON-array prompt + tolerant parser (strips code fences, kebab-cases, dedupes, caps at 7). Tags persist on the mix document. UI: AI TAG button + manual chip input on the edit modal, tag-chip cloud on Library with counts, click-to-filter, ?tag=NAME URL sync, deep-link tag chips on every mix detail page.
- **Tag CRUD bonus** — `MixUpdate` model now also accepts `tracks: List[Track]`, opening the door to a future inline track editor without breaking the cue-position model.
- **Test results** — testing_agent_v3_fork iter 10: backend 100% (97/97 + 8 skipped, +12 new test cases), frontend 100% after one critical fix (MixEditModal `tags` field default — testing agent fixed in scope). Zero outstanding issues.

## Implemented (2026-02 — Phase 7: Bulk AI Operations + Embeddable Player + Smarter Recommendations)
- **AUTO-TAG ALL & AUTO-METADATA ALL** — new `llm_bulk_service.py` walks the entire library and runs `generate_tags` / `write_mix_description` against the local LLM with bounded concurrency (`LLM_BULK_CONCURRENCY` env, default 2). New endpoints: `POST /api/admin/llm/auto_tag_all`, `POST /api/admin/llm/auto_describe_all`, `GET /api/admin/llm/bulk/{task_id}`, `GET /api/admin/llm/bulk` for live progress. Skips mixes that already have results unless `?force=true`. Top-level status correctly transitions to `failed` if all mixes failed (e.g. LLM down) so the UI renders the red FAILED branch.
- **Bulk runner UI** — new `BulkLLMRunner.jsx` component on `/admin/settings`. Two side-by-side runners (TAGS / DESCRIPTIONS) with FORCE checkbox + RUN button. Live progress bar with processed/total counter, succeeded ✓ / failed ⚠ / skipped breakdown, currently-processing mix name, and the actual upstream error text on failure. Success panel auto-clears after 8s; failure panel stays sticky so admins can read errors.
- **Embeddable player** — new `GET /api/embed/{mix_id}` returns a tiny standalone HTML5 `<audio>` player with cover art, title/artist, BPM/KEY/duration meta, scanline grid background, and an "OPEN ON MIXDECK ▸" CTA. Designed for 600×180 iframe but degrades to mobile (vertical stack) at <480px. New EMBED CODE button on every mix detail page copies a ready-to-paste `<iframe>` snippet to clipboard.
- **Smarter "More Like This"** — `/api/mixes/{id}/compatible` now also scores by **shared tag overlap** (1.5 pts per shared tag, capped at 6) on top of BPM proximity, Camelot adjacency, and matching genre. The CompatibleMixesRow re-headed to "MORE LIKE THIS" + "SAME ENERGY · ADJACENT KEY · SHARED TAGS". Each card now displays up to 2 #tag chips beside BPM/Camelot.
- **Test results** — testing_agent_v3_fork iter 11: backend 100% (113/113 + 8 skipped, +16 new test cases), frontend 95% with 2 critical import bugs (Code2 icon, embedUrl helper) self-fixed by testing agent in-scope. UX deviation on bulk-failure status fixed by main agent (status='failed' when all mixes fail). Final state: zero outstanding issues, full feature batch shipped.

## Tech / Libraries
- Backend: fastapi, motor, pydantic, PyJWT, aiofiles, python-multipart
- Frontend: react-router-dom, axios, sonner, lucide-react, tailwindcss
- Fonts: Unbounded (display), JetBrains Mono (body), Chivo (UI)
- Colors: void #050505, surface #0D0E15, cyan #00F0FF, green #39FF14, red #FF003C

## Backlog (P0/P1/P2)
- P2: "Also in this genre" row on mix detail
- P2: Drag-to-reorder tracks, manual track list editor
- P2: Download-for-offline / mix archive zip
- P2: Per-track cover-art lazy fetch button on mix detail (currently auto-fetched on track change in the player)
- P2: Mobile-first refinement of the DJ console (jog wheels currently size down but mixer EQ knobs get cramped < 480px)
