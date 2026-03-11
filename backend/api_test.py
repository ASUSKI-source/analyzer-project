
import asyncio
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from app.services.finnhub import fetch_stock_quote
from app.services.polygon import fetch_polygon_price
from app.core.config import settings

async def test_apis():
    print(f"DEBUG: Finnhub Key exists: {bool(settings.FINNHUB_API_KEY)}")
    print(f"DEBUG: Polygon Key exists: {bool(settings.POLYGON_API_KEY)}")
    
    print("\n--- Testing AAPL (Stock) ---")
    finn_aapl = await fetch_stock_quote("AAPL")
    print(f"Finnhub Result: {finn_aapl}")
    
    poly_aapl = await fetch_polygon_price("AAPL")
    print(f"Polygon Result: {poly_aapl}")

if __name__ == "__main__":
    asyncio.run(test_apis())
