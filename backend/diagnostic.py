
import asyncio
import os
import sys
import httpx

sys.path.append(os.getcwd())
from app.core.config import settings

async def diagnostic():
    fh = settings.FINNHUB_API_KEY
    print(f"Testing Finnhub Key: {fh}")
    url = "https://finnhub.io/api/v1/quote"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params={"symbol": "AAPL", "token": fh})
        print(f"Finnhub Status: {resp.status_code}")
        print(f"Finnhub Body: {resp.text}")

    poly = settings.POLYGON_API_KEY
    print(f"\nTesting Polygon Key: {poly}")
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/AAPL"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params={"apiKey": poly})
        print(f"Polygon Status: {resp.status_code}")
        print(f"Polygon Body: {resp.text}")

if __name__ == "__main__":
    asyncio.run(diagnostic())
