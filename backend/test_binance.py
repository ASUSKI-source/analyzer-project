import httpx
import asyncio

async def f():
    url = "https://api.binance.us/api/v3/ticker/24hr"
    async with httpx.AsyncClient() as c:
        r = await c.get(url, params={"symbols": '["BTCUSDT","INVALIDCOINUSDT","ETHUSDT"]'})
        print(r.status_code)
        print(r.json())

if __name__ == "__main__":
    asyncio.run(f())
