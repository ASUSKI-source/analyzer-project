
import asyncio
import os
import sys

sys.path.append(os.getcwd())
from app.core.cache import cache_client

async def clear_cache():
    await cache_client.connect()
    await cache_client.flush()
    print("Redis Cache Flushed Successfully.")

if __name__ == "__main__":
    asyncio.run(clear_cache())
