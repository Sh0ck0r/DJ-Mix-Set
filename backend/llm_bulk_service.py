"""Bulk LLM operations: AUTO-TAG ALL and AUTO-DESCRIBE ALL.

Walks every mix in the library and runs `generate_tags` or `write_mix_description`
on each one in the background, with bounded concurrency so the local LLM
server doesn't get hammered. The frontend polls for live progress.
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Literal

from cache import cache
from state import db
from llm_service import LLMError, LLMNotConfigured, write_mix_description, write_mix_tags

log = logging.getLogger("mixdeck")

Kind = Literal["tags", "descriptions"]
_LLM_CONCURRENCY = int(os.environ.get("LLM_BULK_CONCURRENCY", "2"))

_bulk_tasks: dict[str, dict] = {}


def get_task(task_id: str) -> dict | None:
    return _bulk_tasks.get(task_id)


def list_active() -> list[dict]:
    """Return all bulk-LLM tasks (current + recent), newest first."""
    return sorted(
        _bulk_tasks.values(),
        key=lambda t: t.get("started_at") or "",
        reverse=True,
    )


async def _process_one(kind: Kind, mix: dict) -> None:
    """Run a single LLM operation against one mix and persist the result."""
    if kind == "tags":
        tags = await write_mix_tags(mix)
        if tags:
            await db.mixes.update_one({"id": mix["id"]}, {"$set": {"tags": tags}})
    elif kind == "descriptions":
        desc = await write_mix_description(mix)
        if desc:
            await db.mixes.update_one({"id": mix["id"]}, {"$set": {"description": desc}})


async def _run_bulk(task_id: str, kind: Kind, force: bool) -> None:
    state = _bulk_tasks[task_id]
    sem = asyncio.Semaphore(_LLM_CONCURRENCY)
    try:
        # Pull the mix list once at the start so a parallel scan/edit doesn't
        # extend the run unexpectedly.
        projection = {"_id": 0, "id": 1, "title": 1, "artist": 1, "genre": 1, "bpm": 1,
                      "camelot": 1, "key": 1, "duration": 1, "tracks": 1, "tags": 1, "description": 1}
        all_mixes = await db.mixes.find({}, projection).to_list(2000)

        if not force:
            if kind == "tags":
                targets = [m for m in all_mixes if not (m.get("tags") and len(m["tags"]) > 0)]
            else:  # descriptions
                targets = [m for m in all_mixes if not (m.get("description") or "").strip()]
        else:
            targets = list(all_mixes)
        state["total"] = len(targets)
        state["skipped_existing"] = len(all_mixes) - len(targets)

        if not targets:
            state["status"] = "done"
            state["finished_at"] = datetime.now(timezone.utc).isoformat()
            return

        # Per-mix worker
        async def worker(mix: dict) -> None:
            async with sem:
                state["current_mix"] = {"id": mix["id"], "title": mix.get("title") or "Untitled"}
                try:
                    await _process_one(kind, mix)
                    state["succeeded"] += 1
                except (LLMNotConfigured, LLMError) as e:
                    state["failed"] += 1
                    state["errors"].append({
                        "mix_id": mix["id"],
                        "title": mix.get("title") or "Untitled",
                        "error": str(e)[:300],
                    })
                    # If the LLM is unconfigured/down, abort the whole run early -
                    # there's no point hammering it for every remaining mix.
                    if isinstance(e, LLMNotConfigured):
                        state["aborted"] = True
                        raise
                except Exception as e:  # noqa: BLE001
                    state["failed"] += 1
                    state["errors"].append({
                        "mix_id": mix["id"],
                        "title": mix.get("title") or "Untitled",
                        "error": str(e)[:300],
                    })
                state["processed"] += 1

        try:
            # Run all workers but bail on the first LLMNotConfigured (abort signal)
            await asyncio.gather(*(worker(m) for m in targets), return_exceptions=False)
        except LLMNotConfigured:
            pass

        if state.get("aborted"):
            state["status"] = "failed"
            state["error"] = "LLM not configured (check Admin → Settings)"
        else:
            state["status"] = "done"
        state["finished_at"] = datetime.now(timezone.utc).isoformat()
        # Bust caches so newly tagged/described mixes show up immediately
        if state["succeeded"] > 0:
            await cache.invalidate_mixes()
    except Exception as e:
        log.exception("Bulk %s task %s crashed", kind, task_id)
        state["status"] = "failed"
        state["error"] = str(e)
        state["finished_at"] = datetime.now(timezone.utc).isoformat()


def start_bulk(kind: Kind, force: bool = False) -> str:
    """Allocate a task_id, kick off the background bulk LLM op, return the id."""
    task_id = str(uuid.uuid4())
    _bulk_tasks[task_id] = {
        "task_id": task_id,
        "kind": kind,
        "force": bool(force),
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "total": 0,
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped_existing": 0,
        "current_mix": None,
        "aborted": False,
        "errors": [],
        "error": None,
    }
    asyncio.create_task(_run_bulk(task_id, kind, force))
    # Cull old finished tasks (keep last 10 per kind)
    by_kind: dict[str, list[tuple[str, dict]]] = {}
    for tid, t in _bulk_tasks.items():
        if t["status"] == "running":
            continue
        by_kind.setdefault(t["kind"], []).append((tid, t))
    for k, lst in by_kind.items():
        if len(lst) > 10:
            lst.sort(key=lambda x: x[1].get("finished_at") or "")
            for tid, _ in lst[: len(lst) - 10]:
                _bulk_tasks.pop(tid, None)
    return task_id
