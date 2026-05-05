"""Lightweight Redis cache wrapper for MIXDECK.

Gracefully no-ops when REDIS_URL is unset or unreachable. JSON-serializes values.
Pattern-based invalidation via key prefixes.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any, Optional

import redis.asyncio as redis

log = logging.getLogger("mixdeck.cache")

REDIS_URL_ENV = "REDIS_URL"
DEFAULT_TTL = int(os.environ.get("CACHE_TTL", "300"))  # 5 minutes
LONG_TTL = 3600  # 1 hour for stable data
KEY_PREFIX = "mixdeck:"


class _Cache:
    def __init__(self) -> None:
        self._client: Optional[redis.Redis] = None
        self._enabled = False
        self._healthy = False

    async def connect(self) -> None:
        # Read at connect time so dotenv-loaded vars are picked up
        url = os.environ.get(REDIS_URL_ENV, "").strip()
        self._enabled = bool(url)
        if not self._enabled:
            log.info("Redis caching disabled (REDIS_URL not set)")
            return
        try:
            self._client = redis.from_url(
                url,
                decode_responses=False,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
                health_check_interval=30,
                retry_on_timeout=True,
                max_connections=20,
            )
            await self._client.ping()
            self._healthy = True
            log.info("Redis cache connected: %s", url)
        except Exception as e:
            log.warning("Redis unavailable, caching disabled: %s", e)
            self._client = None
            self._healthy = False

    async def disconnect(self) -> None:
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
        self._client = None
        self._healthy = False

    @property
    def enabled(self) -> bool:
        return self._enabled and self._healthy and self._client is not None

    def _key(self, k: str) -> str:
        return KEY_PREFIX + k

    async def get(self, key: str) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            raw = await self._client.get(self._key(key))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            log.warning("cache.get(%s) failed: %s", key, e)
            return None

    async def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
        if not self.enabled:
            return
        try:
            payload = json.dumps(value, default=str).encode("utf-8")
            await self._client.setex(self._key(key), ttl, payload)
        except Exception as e:
            log.warning("cache.set(%s) failed: %s", key, e)

    async def delete(self, *keys: str) -> None:
        if not self.enabled or not keys:
            return
        try:
            await self._client.delete(*[self._key(k) for k in keys])
        except Exception as e:
            log.warning("cache.delete failed: %s", e)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern (e.g. 'mixes:*')."""
        if not self.enabled:
            return 0
        full_pat = self._key(pattern)
        try:
            count = 0
            cursor = 0
            while True:
                cursor, keys = await self._client.scan(cursor=cursor, match=full_pat, count=200)
                if keys:
                    await self._client.delete(*keys)
                    count += len(keys)
                if cursor == 0:
                    break
            return count
        except Exception as e:
            log.warning("cache.delete_pattern(%s) failed: %s", pattern, e)
            return 0

    async def invalidate_mixes(self) -> None:
        """Bust all mix-related cache entries on any write."""
        await self.delete_pattern("mixes:*")
        await self.delete_pattern("mix:*")
        await self.delete_pattern("genres")
        await self.delete_pattern("compatible:*")
        await self.delete("rss:feed")


cache = _Cache()
