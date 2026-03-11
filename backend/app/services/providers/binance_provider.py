"""
Binance Provider Adapter — wraps existing coingecko.py (Binance US) logic.
Handles cryptocurrency symbols only. Very high rate limit (1200 weight/min).
"""
import logging
import httpx
from typing import Dict, Any, List
from app.services.providers.base_provider import BaseProvider
from app.core.cache import cache_client

logger = logging.getLogger(__name__)

# Map internal symbols to Binance pair symbols
SYMBOL_TO_BINANCE: Dict[str, str] = {
    "BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT",
    "DOGE": "DOGEUSDT", "ADA": "ADAUSDT", "XRP": "XRPUSDT",
    "DOT": "DOTUSDT", "AVAX": "AVAXUSDT", "MATIC": "MATICUSDT",
    "LINK": "LINKUSDT", "SHIB": "SHIBUSDT", "LTC": "LTCUSDT",
    "BCH": "BCHUSDT", "UNI": "UNIUSDT", "NEAR": "NEARUSDT",
    "ATOM": "ATOMUSDT", "APT": "APTUSDT", "ARB": "ARBUSDT",
    "OP": "OPUSDT", "TIA": "TIAUSDT", "INJ": "INJUSDT",
    "RENDER": "RENDERUSDT", "FET": "FETUSDT", "PEPE": "PEPEUSDT",
}


class BinanceProvider(BaseProvider):
    """
    Primary crypto data provider. Free API, 1200 weight/min.
    Fast batch endpoint — fetches all tickers in one call.
    """
    name = "binance"
    speed_weight = 0.9  # Slightly below Finnhub since a single call fetches everything

    def __init__(self):
        super().__init__()
        self._remaining_quota = 500  # Conservative estimate of weight budget

    def supports_symbol(self, symbol: str) -> bool:
        return symbol.upper() in SYMBOL_TO_BINANCE

    async def fetch_quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch crypto prices from Binance US in a single batch call."""
        valid = [s.upper() for s in symbols if self.supports_symbol(s)]
        if not valid:
            return []

        # Check fast cache first
        results: List[Dict[str, Any]] = []
        symbols_to_fetch: List[str] = []

        for sym in valid:
            cached = await cache_client.get(f"fast_quote:{sym}")
            if cached:
                results.append(cached)
            else:
                symbols_to_fetch.append(sym)

        if not symbols_to_fetch:
            return results

        url = "https://api.binance.us/api/v3/ticker/24hr"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)

                # Track weight usage from headers
                used_weight = response.headers.get("X-MBX-USED-WEIGHT-1M")
                if used_weight is not None:
                    self.update_quota(max(0, 1200 - int(used_weight)))

                response.raise_for_status()
                data = response.json()

                binance_map = {item["symbol"]: item for item in data}

                for sym in symbols_to_fetch:
                    b_id = SYMBOL_TO_BINANCE.get(sym)
                    if b_id and b_id in binance_map:
                        coin = binance_map[b_id]
                        res = {
                            "symbol": sym,
                            "price": round(float(coin.get("lastPrice", 0)), 4),
                            "changePercent": round(float(coin.get("priceChangePercent", 0)), 2),
                        }
                        await cache_client.set(f"fast_quote:{sym}", res, expire_seconds=10)
                        await cache_client.set(f"last_good_price:{sym}", res, expire_seconds=86400)
                        results.append(res)

                self.record_success()

        except Exception as e:
            self.record_failure()
            logger.warning(f"[{self.name}] Binance API error: {e}")
            # Fall back to cache for missing symbols
            for sym in symbols_to_fetch:
                cached = await cache_client.get(f"last_good_price:{sym}")
                if cached:
                    results.append(cached)

        return results
