
import asyncio
import httpx
from app.core.config import settings

async def test():
    fh_key = "d6oagfpr01qu09ciof10"
    url = "https://finnhub.io/api/v1/quote"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params={"symbol": "AAPL", "token": fh_key})
        print(f"FINNHUB_STATUS|{r.status_code}")
        print(f"FINNHUB_BODY|{r.text}")

if __name__ == "__main__":
    asyncio.run(test())
