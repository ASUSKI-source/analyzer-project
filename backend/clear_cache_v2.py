import asyncio
from app.core.cache import cache_client

async def flush():
    print("Connecting to Redis...")
    await cache_client.connect()
    print("Flushing cache...")
    await cache_client.flush()
    print("Closing connection...")
    await cache_client.close()
    print("Cache cleared successfully.")

if __name__ == "__main__":
    asyncio.run(flush())
