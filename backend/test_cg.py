import asyncio
import httpx

async def f():
    async with httpx.AsyncClient() as c:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        r = await c.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd', headers=headers)
        print(f"Status: {r.status_code}")
        print(f"Body: {r.text}")

if __name__ == "__main__":
    asyncio.run(f())
