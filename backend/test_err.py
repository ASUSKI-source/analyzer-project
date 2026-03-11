import asyncio
from app.services.market_data import get_live_intraday_history

async def f():
    data = await get_live_intraday_history("BTC", 1)
    print("BTC rows:", len(data))
    if data:
        print("BTC last:", data[-1])

if __name__ == "__main__":
    asyncio.run(f())
