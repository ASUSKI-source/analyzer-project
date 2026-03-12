import json
import logging
import time
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
        if key in self._fallback_cache:
            entry = self._fallback_cache[key]
            expires_at = entry.get("expires_at")
            if expires_at is None or expires_at > time.time():
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
        expires_at = None
        if expire_seconds and expire_seconds > 0:
            expires_at = time.time() + expire_seconds
        self._fallback_cache[key] = {
            "value": value,
            "expires_at": expires_at,
        }

    async def flush(self):
        if self.redis:
            try:
                await self.redis.flushdb()
                logger.info("Redis cache flushed.")
            except Exception as e:
                logger.error(f"Redis flush error: {e}")
        self._fallback_cache.clear()


    async def get_ttl(self, key: str) -> int:
        """Returns remaining TTL in seconds or -1 if no TTL/key doesn't exist."""
        if self.redis:
            try:
                return await self.redis.ttl(key)
            except Exception as e:
                logger.error(f"Redis ttl error: {e}")
                return self._get_ttl_fallback(key)
        else:
            return self._get_ttl_fallback(key)

    def _get_ttl_fallback(self, key: str) -> int:
        if key in self._fallback_cache:
            entry = self._fallback_cache[key]
            expires_at = entry.get("expires_at")
            if expires_at is None:
                return -1
            remaining = int(expires_at - time.time())
            return max(0, remaining)
        return -1

    async def increment(self, key: str, amount: int = 1) -> int:
        """
        Atomic-ish increment for counters.
        Redis path uses INCRBY; fallback path maintains an integer value.
        """
        if self.redis:
            try:
                return int(await self.redis.incrby(key, amount))
            except Exception as e:
                logger.error(f"Redis increment error: {e}")
        # Fallback path
        current = self._get_fallback(key)
        try:
            current_int = int(current) if current is not None else 0
        except (TypeError, ValueError):
            current_int = 0
        new_value = current_int + amount
        # Preserve existing fallback TTL if present, otherwise no expiry.
        entry = self._fallback_cache.get(key, {})
        self._fallback_cache[key] = {
            "value": new_value,
            "expires_at": entry.get("expires_at"),
        }
        return new_value

    async def expire(self, key: str, seconds: int) -> bool:
        """
        Set/update TTL for an existing key. Returns True if key exists.
        """
        if self.redis:
            try:
                return bool(await self.redis.expire(key, seconds))
            except Exception as e:
                logger.error(f"Redis expire error: {e}")
        # Fallback path
        if key not in self._fallback_cache:
            return False
        if seconds <= 0:
            del self._fallback_cache[key]
            return True
        self._fallback_cache[key]["expires_at"] = time.time() + seconds
        return True

    async def close(self):
        if self.redis:
            await self.redis.aclose()

cache_client = CacheClient()

async def get_redis():
    """Helper to ensure cache_client is connected and returned."""
    if not cache_client.redis:
        await cache_client.connect()
    return cache_client.redis
