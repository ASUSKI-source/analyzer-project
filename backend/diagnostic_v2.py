
import asyncio
import httpx
from app.core.config import settings

async def test_key(name, key, url, param_name):
    if not key:
        print(f"FAILED: {name} Key is empty or not set.")
        return
    
    print(f"Testing {name} Key: {key[:4]}...{key[-4:] if len(key) > 4 else ''}")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params={param_name: key})
            print(f"{name} Status: {resp.status_code}")
            if resp.status_code == 200:
                print(f"✅ {name} Key is VALID.")
            else:
                print(f"❌ {name} Key INVALID (Status {resp.status_code})")
                print(f"   Response: {resp.text[:100]}")
        except Exception as e:
            print(f"⚠️ {name} Error: {e}")

async def diagnostic():
    # Test Polygon
    print("\n--- POLYGON DIAGNOSTIC ---")
    poly_url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/AAPL"
    await test_key("Polygon", settings.POLYGON_API_KEY, poly_url, "apiKey")

    # Test Finnhub
    print("\n--- FINNHUB DIAGNOSTIC ---")
    fh_url = "https://finnhub.io/api/v1/quote?symbol=AAPL"
    await test_key("Finnhub", settings.FINNHUB_API_KEY, fh_url, "token")

if __name__ == "__main__":
    asyncio.run(diagnostic())

