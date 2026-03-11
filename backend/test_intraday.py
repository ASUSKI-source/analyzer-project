import httpx
import asyncio
from datetime import datetime, timedelta, timezone

async def f():
    async with httpx.AsyncClient() as c:
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
        r3 = await c.get(f"https://api.polygon.io/v2/aggs/ticker/AAPL/range/5/minute/{start}/{end}", params={
            "adjusted": "true",
            "sort": "asc",
            "apiKey": "9XYpyfmpwJlCAtkFxpmUT0hF34AbG_Io"
        })
        print("Polygon Status:", r3.status_code)
        data3 = r3.json()
        print("Polygon counts:", data3.get("resultsCount", 0))
        if data3.get("resultsCount", 0) > 0:
             print("Polygon sample:", data3["results"][0])

if __name__ == "__main__":
    asyncio.run(f())
