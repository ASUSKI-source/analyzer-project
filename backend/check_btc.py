import asyncio
from app.core.cache import cache_client

async def f():
    await cache_client.connect()
    val = await cache_client.get('last_good_price:BTC')
    print("last_good_price:BTC ->", val)
    await cache_client.close()

if __name__ == "__main__":
    asyncio.run(f())
