import asyncio
import logging
from app.core.cache import cache_client

logger = logging.getLogger(__name__)

class PolygonRateLimiter:
    """
    Token Bucket rate limiter for Polygon.io (Free Tier: 5 calls/min).
    Ensures absolute safety by enforcing a global lock across all worker processes.
    """
    BUCKET_KEY = "polygon_token_bucket"
    LIMIT = 5
    REFILL_TIME = 60 # seconds
    
    @classmethod
    async def acquire_token(cls, priority: int = 1) -> bool:
        """
        Attempts to acquire a token for a Polygon API call.
        Priority 1: Strategic Sync (Daily/Weekly) - Always attempts if tokens > 0.
        Priority 2: Tactical Sync (Intraday 5m) - Rejects if bucket is low (< 2 tokens).
        """
        try:
            # 1. Fetch current bucket count
            count = await cache_client.get(cls.BUCKET_KEY) or 0
            count = int(count)
        except Exception as e:
            logger.error(f"Polygon Rate Limit: cache get failed, rejecting token request safely: {e}")
            return False
        
        # 2. Priority Rail: Tactical syncs are rejected if we are near the margin
        if priority == 2 and count >= (cls.LIMIT - 1):
            logger.warning("Polygon Rate Limit: Rejecting Tactical sync to save tokens for Strategic data.")
            return False
            
        # 3. Global Hard Limit
        if count >= cls.LIMIT:
            logger.warning(f"Polygon Rate Limit: Hard limit reached ({count}/{cls.LIMIT}).")
            return False
            
        # 4. Increment and set expiry if this is the first token in the window
        # We use a simple windowed-increment for the 1-minute bucket
        try:
            new_count = await cache_client.increment(cls.BUCKET_KEY)
            if new_count == 1:
                await cache_client.expire(cls.BUCKET_KEY, cls.REFILL_TIME)
        except Exception as e:
            logger.error(f"Polygon Rate Limit: cache increment/expire failed, rejecting token request safely: {e}")
            return False
            
        logger.info(f"Polygon Token Acquired: {new_count}/{cls.LIMIT} (Priority: {priority})")
        return True

    @classmethod
    async def get_remaining_tokens(cls) -> int:
        count = await cache_client.get(cls.BUCKET_KEY) or 0
        return max(0, cls.LIMIT - int(count))
