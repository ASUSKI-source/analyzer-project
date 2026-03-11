import httpx
import asyncio

async def f():
    url = "https://api.binance.us/api/v3/ticker/24hr"
    async with httpx.AsyncClient() as c:
        r = await c.get(url)
        print(r.status_code)
        data = r.json()
        print(len(data))
        btc = next((item for item in data if item["symbol"] == "BTCUSDT"), None)
        print("BTC:", btc)

if __name__ == "__main__":
    asyncio.run(f())
