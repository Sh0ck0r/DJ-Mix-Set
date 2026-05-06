"""Runtime app settings persisted in MongoDB.

Stored as a single doc with id="app" in the `settings` collection. Lets the
admin tweak LLM endpoint / model / API key from the UI without redeploying
the backend. Falls back to env defaults on first run.
"""
import os
from typing import Optional

from state import db

# Defaults read from env on first run (so docker-compose users get sane defaults).
_DEFAULTS = {
    "id": "app",
    "llm_base_url": os.environ.get("LLM_BASE_URL", "http://localhost:30000/v1"),
    "llm_api_key": os.environ.get("LLM_API_KEY", ""),
    "llm_model": os.environ.get("LLM_MODEL", "default"),
    "llm_enabled": True,
}

# Fields the admin UI is allowed to write
WRITABLE = {"llm_base_url", "llm_api_key", "llm_model", "llm_enabled"}

# Fields the GET endpoint redacts (never echoed back in plaintext to UI)
SECRET_FIELDS = {"llm_api_key"}


async def get_settings() -> dict:
    """Return the current settings dict (creates the doc on first call)."""
    doc = await db.settings.find_one({"id": "app"}, {"_id": 0})
    if doc is None:
        await db.settings.insert_one(dict(_DEFAULTS))
        return dict(_DEFAULTS)
    # backfill any missing keys from defaults so older docs upgrade cleanly
    merged = {**_DEFAULTS, **doc}
    return merged


async def get_public_settings() -> dict:
    """Settings shape returned to the admin UI (api key replaced with bool)."""
    s = await get_settings()
    return {
        "llm_base_url": s.get("llm_base_url", ""),
        "llm_model": s.get("llm_model", ""),
        "llm_enabled": bool(s.get("llm_enabled", True)),
        "llm_api_key_set": bool(s.get("llm_api_key")),
    }


async def update_settings(patch: dict) -> dict:
    """Apply a partial update. Empty-string api_key means 'leave unchanged'."""
    current = await get_settings()
    update: dict = {}
    for k, v in patch.items():
        if k not in WRITABLE:
            continue
        if k == "llm_api_key":
            # Empty -> keep existing; explicit None -> clear; anything else -> set
            if v == "" or v is None and patch.get("clear_api_key") is not True:
                continue
        update[k] = v
    if patch.get("clear_api_key") is True:
        update["llm_api_key"] = ""
    if not update:
        return await get_public_settings()
    merged = {**current, **update}
    await db.settings.update_one({"id": "app"}, {"$set": merged}, upsert=True)
    return await get_public_settings()


async def get_llm_config() -> Optional[dict]:
    """Return {base_url, api_key, model} for use by llm_service. None if disabled."""
    s = await get_settings()
    if not s.get("llm_enabled"):
        return None
    base = (s.get("llm_base_url") or "").rstrip("/")
    if not base:
        return None
    return {
        "base_url": base,
        "api_key": s.get("llm_api_key") or "EMPTY",
        "model": s.get("llm_model") or "default",
    }
