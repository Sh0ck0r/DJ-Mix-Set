"""Bulk directory scan: walks a folder, ingests audio files (with optional
.cue sheets and adjacent cover art) as Mix documents. Runs entirely in the
background with a polling task_id so the API never blocks on huge libraries.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cache import cache
from cue import AUDIO_EXTS, parse_cue, extract_cue_header, find_cue_for, find_cover_for
from models import Mix, ScanRequest, Track
from state import db, CUES_DIR
from analysis_service import schedule_analysis

log = logging.getLogger("mixdeck")

_scan_tasks: dict[str, dict] = {}


def get_task(task_id: str) -> dict | None:
    return _scan_tasks.get(task_id)


async def _run_scan(task_id: str, body: ScanRequest) -> None:
    state = _scan_tasks[task_id]
    try:
        root = Path(body.path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            state["status"] = "failed"
            state["error"] = f"Path does not exist or is not a directory: {root}"
            state["finished_at"] = datetime.now(timezone.utc).isoformat()
            return

        audio_files: list[Path] = []
        if body.recursive:
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                    audio_files.append(p)
        else:
            for p in root.iterdir():
                if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                    audio_files.append(p)

        state["root"] = str(root)
        state["total"] = len(audio_files)

        existing = set()
        async for d in db.mixes.find({"source_path": {"$ne": None}}, {"source_path": 1, "_id": 0}):
            if d.get("source_path"):
                existing.add(d["source_path"])

        for audio in sorted(audio_files):
            state["processed"] += 1
            state["current_file"] = audio.name
            try:
                src = str(audio)
                if src in existing:
                    state["skipped"].append({"path": src, "reason": "already_ingested"})
                    state["skipped_count"] += 1
                    continue

                title = audio.stem
                artist = ""
                tracks: list[dict] = []
                cue = find_cue_for(audio)
                if cue:
                    try:
                        content = cue.read_text(encoding="utf-8", errors="replace")
                    except UnicodeDecodeError:
                        content = cue.read_text(encoding="latin-1", errors="replace")
                    cue_title, cue_performer = extract_cue_header(content)
                    if cue_title:
                        title = cue_title
                    if cue_performer:
                        artist = cue_performer
                    tracks = [t.model_dump() for t in parse_cue(content)]
                cover = find_cover_for(audio)

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

                if cue:
                    try:
                        (CUES_DIR / f"{mix.id}.cue").write_text(
                            cue.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
                        )
                    except Exception:
                        pass

                state["added"].append({
                    "id": mix.id,
                    "title": title,
                    "artist": artist,
                    "path": src,
                    "cue": bool(cue),
                    "tracks": len(tracks),
                    "cover": bool(cover),
                })
                state["added_count"] += 1
                existing.add(src)
                if body.analyze:
                    await db.mixes.update_one({"id": mix.id}, {"$set": {"analysis_status": "pending"}})
                    schedule_analysis(mix.id)
            except Exception as e:
                state["failed"].append({"path": str(audio), "error": str(e)})
                state["failed_count"] += 1

        if state["added_count"] > 0:
            await cache.invalidate_mixes()
        state["analysis_queued"] = state["added_count"] if body.analyze else 0
        state["status"] = "done"
        state["finished_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as e:
        log.exception("Scan task %s crashed", task_id)
        state["status"] = "failed"
        state["error"] = str(e)
        state["finished_at"] = datetime.now(timezone.utc).isoformat()


def start_scan(body: ScanRequest) -> str:
    """Allocate a task_id, kick off the background scan, return the id."""
    task_id = str(uuid.uuid4())
    _scan_tasks[task_id] = {
        "task_id": task_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "root": "",
        "processed": 0,
        "total": 0,
        "current_file": None,
        "added_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "analysis_queued": 0,
        "added": [],
        "skipped": [],
        "failed": [],
        "error": None,
    }
    asyncio.create_task(_run_scan(task_id, body))
    # Cull old finished tasks (keep last 20)
    finished = [(tid, t) for tid, t in _scan_tasks.items() if t["status"] != "running"]
    if len(finished) > 20:
        finished.sort(key=lambda x: x[1].get("finished_at") or "")
        for tid, _ in finished[: len(finished) - 20]:
            _scan_tasks.pop(tid, None)
    return task_id
