
import asyncio
import httpx

async def test_key(name, key, url, param_name):
    print(f"Testing {name} Key: {key}")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params={param_name: key})
            print(f"{name} Status: {resp.status_code}")
            print(f"{name} Body: {resp.text[:200]}")
        except Exception as e:
            print(f"{name} Error: {e}")

async def diagnostic():
    # Finnhub possibilities
    full_fh = "d6oa8ppr01qu09cinou0d6oa8ppr01qu09cinoug"
    fh_v1 = "d6oa8ppr01qu09cinou0"
    fh_v2 = "d6oa8ppr01qu09cinoug"
    fh_url = "https://finnhub.io/api/v1/quote?symbol=AAPL"
    
    await test_key("Finnhub Full", full_fh, fh_url, "token")
    await test_key("Finnhub P1", fh_v1, fh_url, "token")
    await test_key("Finnhub P2", fh_v2, fh_url, "token")

    # Polygon
    poly = "ifDWmtN_pZIRYJhnduGidQM3qCQQj34A"
    poly_url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/AAPL"
    await test_key("Polygon", poly, poly_url, "apiKey")

if __name__ == "__main__":
    asyncio.run(diagnostic())
