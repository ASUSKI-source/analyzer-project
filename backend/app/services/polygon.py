import logging
import asyncio
import httpx
from typing import Dict, Any, List, Optional
from app.core.config import settings
from app.core.cache import cache_client
import random

logger = logging.getLogger(__name__)

def _has_valid_key() -> bool:
    return bool(settings.POLYGON_API_KEY) and "testkey" not in settings.POLYGON_API_KEY

async def fetch_polygon_price(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Backup Service: Fetches real-time price from Polygon.io.
    Returns None if API fails, allowing caller to decide next fallback.
    """
    symbol = symbol.upper()
    cache_key = f"last_good_price:{symbol}"

    if not _has_valid_key():
        return await cache_client.get(cache_key)

    # Skip indices like VIX which are not supported by the stock-specific snapshot endpoint
    # on standard Polygon API keys.
    if symbol in ["VIX", "SPX", "NDX"]:
        logger.debug(f"Skipping Polygon stock snapshot for index {symbol}")
        return await cache_client.get(cache_key)

    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}"
    
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, params={"apiKey": settings.POLYGON_API_KEY})
            
            if response.status_code == 429:
                logger.warning(f"Polygon rate limit hit (429) for {symbol}")
                return await cache_client.get(cache_key)
                
            if response.status_code == 403:
                # Downgrade 403 to info/debug to avoid terminal clutter, as it's common for restricted assets
                logger.info(f"Polygon access restricted (403) for {symbol}. Likely requires higher-tier key.")
                return await cache_client.get(cache_key)

            response.raise_for_status()
            data = response.json()
            
            if "ticker" in data and data["ticker"]:
                ticker_data = data["ticker"]
                price = ticker_data.get("lastTrade", {}).get("p") or ticker_data.get("prevDay", {}).get("c")
                
                if price:
                    result = {
                        "symbol": symbol,
                        "price": round(price, 2),
                        "changePercent": round(ticker_data.get("todaysChangePerc", 0.0), 2)
                    }
                    # Update Price Shield
                    await cache_client.set(cache_key, result, expire_seconds=86400)
                    return result
                    
    except Exception as e:
        # Use debug level for the full exception to keep logs clean
        logger.debug(f"Polygon API unexpected error for {symbol}: {e}")
        
    # Return last good price from cache if API failed or was restricted
    return await cache_client.get(cache_key)


async def search_polygon_tickers(query: str) -> List[Dict[str, Any]]:
    """
    Search for tickers using Polygon's v3 reference API.
    Docs: https://polygon.io/docs/stocks/get_v3_reference_tickers
    """
    query = query.strip().upper()
    if not query or not _has_valid_key():
        return []
        
    url = "https://api.polygon.io/v3/reference/tickers"
    params = {
        "search": query,
        "active": "true",
        "limit": 10,
        "apiKey": settings.POLYGON_API_KEY
    }
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, params=params)
            if response.status_code == 429:
                return []
            
            response.raise_for_status()
            data = response.json()
            
            results = []
            for t in data.get("results", []):
                # Normalize types to match our 'stock' | 'crypto' internal convention
                mkt = t.get("market", "")
                asset_type = "stock" if mkt == "stocks" else "crypto" if mkt == "crypto" else "other"
                
                results.append({
                    "symbol": t.get("ticker"),
                    "name": t.get("name"),
                    "type": asset_type
                })
            return results
    except Exception as e:
        logger.error(f"Polygon ticker search failed: {e}")
        return []
async def fetch_polygon_52w_high_low(symbol: str) -> Dict[str, Optional[float]]:
    """
    Fetches real historical 52-week high/low for stocks and crypto using Polygon Aggregates.
    """
    if not _has_valid_key():
        return {"high": None, "low": None}

    symbol = symbol.upper()
    # Normalize for Polygon Crypto if it's a known coin (simple check)
    from app.services.coingecko import is_crypto
    poly_sym = f"X:{symbol}USD" if is_crypto(symbol) else symbol
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    url = f"https://api.polygon.io/v2/aggs/ticker/{poly_sym}/range/1/day/{start_str}/{end_str}"
    
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(url, params={"apiKey": settings.POLYGON_API_KEY, "adjusted": "true"})
            if res.status_code == 429: return {"high": None, "low": None}
            res.raise_for_status()
            data = res.json()
            results = data.get("results", [])
            if results:
                highs = [float(r["h"]) for r in results]
                lows = [float(r["l"]) for r in results]
                return {"high": max(highs), "low": min(lows)}
    except Exception as e:
        logger.warning(f"Polygon 52W fetch failed for {symbol}: {e}")

    return {"high": None, "low": None}
