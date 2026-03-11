"""
Crypto Service — Uses Binance.US API for Free, high-limit real-time data.
1200 weight/min limit (we use ~40 per 10s = 240/min).
Overrides legacy CoinGecko name for compatibility.
"""
import logging
import asyncio
import httpx
from typing import Dict, Any, List
from app.core.cache import cache_client
import random

logger = logging.getLogger(__name__)

# Map our internal symbols to Binance pair symbols
SYMBOL_TO_BINANCE: Dict[str, str] = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "DOGE": "DOGEUSDT",
    "ADA": "ADAUSDT",
    "XRP": "XRPUSDT",
    "DOT": "DOTUSDT",
    "AVAX": "AVAXUSDT",
    "MATIC": "MATICUSDT",
    "LINK": "LINKUSDT",
    "SHIB": "SHIBUSDT",
    "LTC": "LTCUSDT",
    "BCH": "BCHUSDT",
    "UNI": "UNIUSDT",
    "NEAR": "NEARUSDT",
    "ATOM": "ATOMUSDT",
    "APT": "APTUSDT",
    "ARB": "ARBUSDT",
    "OP": "OPUSDT",
    "TIA": "TIAUSDT",
    "INJ": "INJUSDT",
    "RENDER": "RENDERUSDT",
    "FET": "FETUSDT",
    "PEPE": "PEPEUSDT",
}


def is_crypto(symbol: str) -> bool:
    """Check if a symbol is a known cryptocurrency."""
    return symbol.upper() in SYMBOL_TO_BINANCE


async def fetch_crypto_prices(symbols: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch live crypto prices from Binance.US High-Limit Free API.
    """
    if not symbols:
        return []

    # Map symbols to Binance IDs and check Fast Cache
    valid_symbols = []
    binance_ids = []
    results_map: Dict[str, Dict[str, Any]] = {}
    
    for sym in symbols:
        sym_upper = sym.upper()
        # Fast 10-second cache check BEFORE hitting API to resolve redundant polling
        fast_cache = await cache_client.get(f"fast_quote:{sym_upper}")
        if fast_cache:
            results_map[sym_upper] = fast_cache
            continue
            
        b_id = SYMBOL_TO_BINANCE.get(sym_upper)
        if b_id:
            binance_ids.append(b_id)
            valid_symbols.append(sym_upper)

    
    if valid_symbols:
        # Fetch ALL Binance tickers to avoid invalid symbol HTTP 400 errors. Payload is fast.
        url = "https://api.binance.us/api/v3/ticker/24hr"
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                
                # Create a quick lookup map from the Binance array
                binance_market_map = {item["symbol"]: item for item in data}

                for sym in valid_symbols:
                    b_id = SYMBOL_TO_BINANCE.get(sym)
                    if b_id and b_id in binance_market_map:
                        coin = binance_market_map[b_id]
                        res = {
                            "symbol": sym,
                            "price": round(float(coin.get("lastPrice", 0)), 4),
                            "changePercent": round(float(coin.get("priceChangePercent", 0)), 2),
                        }
                        # Save to Fast Cache (10s) AND Price Shield (24h)
                        await cache_client.set(f"fast_quote:{sym}", res, expire_seconds=10)
                        await cache_client.set(f"last_good_price:{sym}", res, expire_seconds=86400)
                        results_map[sym] = res

        except Exception as e:
            logger.warning(f"Binance API error: {e}")

    # For any missing symbols (failed API or invalid syms), try cache then fallback
    final_results = []
    for sym in symbols:
        sym_upper = sym.upper()
        if sym_upper in results_map:
            final_results.append(results_map[sym_upper])
        else:
            # Fallback chain: Cache -> Mock
            cached = await cache_client.get(f"last_good_price:{sym_upper}")
            if cached:
                final_results.append(cached)
            else:
                final_results.append(_fallback(sym_upper))

    return final_results


async def fetch_single_crypto_price(symbol: str) -> Dict[str, Any]:
    """Convenience wrapper for a single symbol."""
    results = await fetch_crypto_prices([symbol])
    return results[0] if results else _fallback(symbol)


def _fallback(symbol: str) -> Dict[str, Any]:
    """Fallback mock data when APIs are unreachable. Using stable seeds."""
    symbol = symbol.upper()
    # Create a deterministic random generator for this symbol
    rng = random.Random(symbol)
    
    base_prices = {
        "BTC": 65000, "ETH": 3500, "SOL": 145, "DOGE": 0.12,
        "ADA": 0.45, "XRP": 0.55, "DOT": 7.5, "AVAX": 38,
        "MATIC": 0.72, "LINK": 18,
    }
    base = base_prices.get(symbol, rng.uniform(1.0, 500.0))
    return {
        "symbol": symbol,
        "price": round(base + rng.uniform(-base * 0.01, base * 0.01), 2),
        "changePercent": round(rng.uniform(-5, 5), 2),
    }
