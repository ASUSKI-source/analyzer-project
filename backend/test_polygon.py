import httpx
import asyncio

async def f():
    url = "https://api.polygon.io/v1/last/crypto/BTC/USD"
    
    async with httpx.AsyncClient() as c:
        r = await c.get(url, params={"apiKey": "9XYpyfmpwJlCAtkFxpmUT0hF34AbG_Io"})
        print(f"Status: {r.status_code}")
        print(f"JSON: {r.json()}")

if __name__ == "__main__":
    asyncio.run(f())
