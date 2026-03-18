import logging
import httpx
import asyncio
from typing import Dict, Any, List, Optional
from app.utils.http import get_http_client
from app.core.cache import cache_client

logger = logging.getLogger(__name__)

async def fetch_crypto_fear_and_greed() -> Dict[str, Any]:
    """
    Fetches the Crypto Fear & Greed Index from alternative.me.
    Cache for 4 hours as it updates daily.
    """
    cache_key = "crypto_fear_greed"
    cached = await cache_client.get(cache_key)
    if cached: return cached

    url = "https://api.alternative.me/fng/"
    try:
        client = get_http_client()
        response = await client.get(url, timeout=5.0)
        response.raise_for_status()
        data = response.json()
        
        fng_data = data.get("data", [{}])[0]
        result = {
            "value": fng_data.get("value"),
            "value_classification": fng_data.get("value_classification"),
            "timestamp": fng_data.get("timestamp")
        }
        await cache_client.set(cache_key, result, expire_seconds=14400)
        return result
    except Exception as e:
        logger.warning(f"Fear & Greed fetch failed: {e}")
        return {"value": None, "value_classification": "Unknown"}

async def fetch_binance_futures_data(symbol: str) -> Dict[str, Any]:
    """
    Fetches Long/Short ratio and Open Interest from Binance Futures (USDT-M).
    Returns metrics helpful for assessing "Short Squeeze" potential in crypto.
    """
    # Normalize BTC-USD to BTCUSDT for Binance
    binance_sym = symbol.upper().replace("-", "").replace("/", "")
    if not binance_sym.endswith("USDT"):
        binance_sym += "USDT"

    cache_key = f"crypto_futures_data:{binance_sym}"
    cached = await cache_client.get(cache_key)
    if cached: return cached

    base_url = "https://fapi.binance.com/futures/data"
    client = get_http_client()
    
    try:
        # 1. Long/Short Ratio (Top Traders)
        ls_res = await client.get(
            f"{base_url}/topLongShortAccountRatio",
            params={"symbol": binance_sym, "period": "1h", "limit": 1},
            timeout=5.0
        )
        # 2. Open Interest
        oi_res = await client.get(
            f"{base_url}/openInterestHist",
            params={"symbol": binance_sym, "period": "1h", "limit": 1},
            timeout=5.0
        )
        
        ls_data = ls_res.json()[0] if ls_res.status_code == 200 and ls_res.json() else {}
        oi_data = oi_res.json()[0] if oi_res.status_code == 200 and oi_res.json() else {}
        
        result = {
            "long_short_ratio": ls_data.get("longShortRatio"),
            "long_account": ls_data.get("longAccount"),
            "short_account": ls_data.get("shortAccount"),
            "open_interest": oi_data.get("sumOpenInterest"),
            "open_interest_value": oi_data.get("sumOpenInterestValue")
        }
        await cache_client.set(cache_key, result, expire_seconds=300) # 5 min
        return result
    except Exception as e:
        logger.debug(f"Binance futures data fetch failed for {binance_sym}: {e}")
        return {}

async def get_crypto_onchain_context(symbol: str) -> Dict[str, Any]:
    """
    Aggregates crypto-specific on-chain and derivative data.
    """
    # Fear & Greed is global, not per-symbol
    fng_task = fetch_crypto_fear_and_greed()
    futures_task = fetch_binance_futures_data(symbol)
    
    fng, futures = await asyncio.gather(fng_task, futures_task)
    
    return {
        "fear_and_greed": fng,
        "futures_sentiment": futures
    }
