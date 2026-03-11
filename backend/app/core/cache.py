import json
import logging
from typing import Any, Optional
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)

class CacheClient:
    def __init__(self):
        self.redis = None
        self._fallback_cache = {}

    async def connect(self):
        try:
            # Attempt to connect to Redis
            import asyncio
            self.redis = await aioredis.from_url(
                settings.REDIS_URL, 
                decode_responses=True, 
                socket_timeout=2.0, 
                socket_connect_timeout=2.0
            )
            # Ping to verify connection
            await asyncio.wait_for(self.redis.ping(), timeout=3.0)
            logger.info("Successfully connected to Redis cache.")
        except Exception as e:
            logger.warning(
                f"Redis connection failed (URL: {settings.REDIS_URL}). "
                "Falling back to in-memory cache. This is normal if you haven't started a Redis server."
            )
            # Log the full exception at debug level if needed for deep dives
            logger.debug(f"Redis error detail: {e}")
            self.redis = None

    async def get(self, key: str) -> Optional[Any]:
        if self.redis:
            try:
                data = await self.redis.get(key)
                return json.loads(data) if data else None
            except Exception as e:
                logger.error(f"Redis get error: {e}")
                return self._get_fallback(key)
        else:
            return self._get_fallback(key)

    def _get_fallback(self, key: str) -> Optional[Any]:
        import time
        if key in self._fallback_cache:
            entry = self._fallback_cache[key]
            if entry.get("expires_at", 0) > time.time():
                return entry["value"]
            else:
                # Expired
                del self._fallback_cache[key]
                return None
        return None

    async def set(self, key: str, value: Any, expire_seconds: int = 60):
        if self.redis:
            try:
                await self.redis.set(key, json.dumps(value), ex=expire_seconds)
            except Exception as e:
                logger.error(f"Redis set error: {e}")
                self._set_fallback(key, value, expire_seconds)
        else:
            self._set_fallback(key, value, expire_seconds)

    def _set_fallback(self, key: str, value: Any, expire_seconds: int):
        import time
        self._fallback_cache[key] = {
            "value": value,
            "expires_at": time.time() + expire_seconds
        }

    async def flush(self):
        if self.redis:
            try:
                await self.redis.flushdb()
                logger.info("Redis cache flushed.")
            except Exception as e:
                logger.error(f"Redis flush error: {e}")
        self._fallback_cache.clear()


    async def close(self):
        if self.redis:
            await self.redis.aclose()

cache_client = CacheClient()
