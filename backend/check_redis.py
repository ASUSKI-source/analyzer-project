
import asyncio
import os
import sys

sys.path.append(os.getcwd())
from app.core.cache import cache_client

async def main():
    await cache_client.connect()
    price = await cache_client.get("last_good_price:SPY")
    print(f"SPY Cache: {price}")
    
    price2 = await cache_client.get("last_good_price:BTC")
    print(f"BTC Cache: {price2}")

if __name__ == "__main__":
    asyncio.run(main())
