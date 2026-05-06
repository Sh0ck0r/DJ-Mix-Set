"""Local LLM client. Speaks the OpenAI-compatible API, so it works with
SGLang, Ollama, vLLM, LM Studio, llama.cpp server, text-generation-webui, etc.

Reads endpoint + model + key dynamically from settings_service so the admin
can swap at runtime without restarting the backend.
"""
import logging
from typing import Optional

import httpx

from settings_service import get_llm_config

log = logging.getLogger("mixdeck")


class LLMNotConfigured(Exception):
    """Raised when an LLM call is requested but settings are missing/disabled."""


class LLMError(Exception):
    """Upstream LLM API returned an error."""


async def _post(path: str, body: dict, timeout: float = 30.0) -> dict:
    cfg = await get_llm_config()
    if cfg is None:
        raise LLMNotConfigured("LLM is disabled or not configured. Set it in Admin → Settings.")
    url = f"{cfg['base_url']}{path}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            resp = await c.post(url, json=body, headers=headers)
    except httpx.HTTPError as e:
        raise LLMError(f"Cannot reach LLM at {cfg['base_url']}: {e}") from e
    if resp.status_code >= 400:
        raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:500]}")
    return resp.json()


async def chat(
    system: str,
    user: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 400,
    model: Optional[str] = None,
) -> str:
    """Single-shot chat completion. Returns the assistant message string."""
    cfg = await get_llm_config()
    if cfg is None:
        raise LLMNotConfigured("LLM is disabled or not configured.")
    body = {
        "model": model or cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = await _post("/chat/completions", body, timeout=60.0)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Malformed LLM response: {data}") from e


async def health_check() -> dict:
    """Hit /models to verify the endpoint reachable + auth working."""
    cfg = await get_llm_config()
    if cfg is None:
        return {"ok": False, "error": "LLM disabled or unconfigured"}
    url = f"{cfg['base_url']}/models"
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url, headers=headers)
        if r.status_code >= 400:
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
        data = r.json()
        models = []
        if isinstance(data, dict):
            models = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
        return {
            "ok": True,
            "base_url": cfg["base_url"],
            "configured_model": cfg["model"],
            "available_models": models[:50],
            "model_in_list": cfg["model"] in models if models else None,
        }
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Cannot reach {url}: {e}"}


# ===== High-level helpers =====
DESCRIPTION_SYSTEM = (
    "You are a music journalist who writes short, punchy, vibey descriptions of "
    "DJ mixes for a streaming site. Keep it 2-4 sentences. No emoji. No hashtags. "
    "No first person. Highlight the energy arc, dominant genre, BPM range, and key "
    "moments based on the tracklist. Write like Resident Advisor or Mixmag, not "
    "marketing copy."
)


def _format_track_list(tracks: list[dict], duration: float) -> str:
    if not tracks:
        return "(no tracklist available)"
    lines = []
    for t in tracks[:60]:
        idx = t.get("index", "?")
        title = t.get("title") or "Untitled"
        artist = t.get("artist") or "Unknown"
        bpm = t.get("bpm")
        cam = t.get("camelot")
        start = t.get("start_seconds", 0)
        m, s = int(start // 60), int(start % 60)
        meta_bits = []
        if bpm:
            meta_bits.append(f"{bpm} BPM")
        if cam:
            meta_bits.append(cam)
        meta = f" [{', '.join(meta_bits)}]" if meta_bits else ""
        lines.append(f"{idx:>2}. {m:02d}:{s:02d} — {artist} — {title}{meta}")
    if duration:
        m, s = int(duration // 60), int(duration % 60)
        lines.append(f"\nTotal duration: {m:02d}:{s:02d}")
    return "\n".join(lines)


async def write_mix_description(mix: dict) -> str:
    """Generate a 2-4 sentence description for a mix from its tracklist."""
    tracks = mix.get("tracks") or []
    duration = float(mix.get("duration") or 0.0)
    bpms = [int(t["bpm"]) for t in tracks if t.get("bpm")]
    bpm_range = f"{min(bpms)}-{max(bpms)} BPM" if bpms else "BPM unknown"
    genre = mix.get("genre") or "DJ Mix"
    title = mix.get("title") or "Untitled"
    artist = mix.get("artist") or "Unknown DJ"
    overall_bpm = mix.get("bpm")

    user_prompt = (
        f"Write a description for the following continuous DJ mix:\n\n"
        f"Title: {title}\n"
        f"DJ / Artist: {artist}\n"
        f"Genre: {genre}\n"
        f"Mix BPM (median): {overall_bpm or 'unknown'}\n"
        f"Per-track BPM range: {bpm_range}\n"
        f"Tracklist:\n{_format_track_list(tracks, duration)}\n\n"
        f"Write 2-4 sentences only. Plain text, no markdown, no headings."
    )
    return await chat(DESCRIPTION_SYSTEM, user_prompt, temperature=0.85, max_tokens=240)
