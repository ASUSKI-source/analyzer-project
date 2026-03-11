"""
Finnhub Provider Adapter — wraps existing finnhub.py logic into the BaseProvider interface.
Handles stocks and indices. Tracks rate-limit quota from response headers.
"""
import logging
import asyncio
import httpx
from typing import Dict, Any, List
from app.services.providers.base_provider import BaseProvider
from app.core.config import settings
from app.core.cache import cache_client

logger = logging.getLogger(__name__)

# Known stock/index symbols (non-exhaustive — anything NOT crypto is assumed stock)
KNOWN_INDICES = {"SPY", "QQQ", "VIX", "DIA", "IWM", "SPX", "NDX"}


class FinnhubProvider(BaseProvider):
    """
    Primary stock data provider. Free tier: 60 calls/min.
    Highest speed_weight because it returns data fastest.
    """
    name = "finnhub"
    speed_weight = 1.0

    def __init__(self):
        super().__init__()
        key = getattr(settings, "FINNHUB_API_KEY", None)
        self._has_key = bool(key) and "testkey" not in str(key)
        self._remaining_quota = 60 if self._has_key else 0

    def supports_symbol(self, symbol: str) -> bool:
        """Finnhub supports all stock/ETF/index symbols (not crypto)."""
        from app.services.coingecko import is_crypto
        return self._has_key and not is_crypto(symbol.upper())

    async def fetch_quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch quotes individually (Finnhub doesn't support batch)."""
        if not self._has_key:
            return []

        tasks = [self._fetch_single(sym.upper()) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful = []
        for r in results:
            if isinstance(r, Exception):
                self.record_failure()
                logger.warning(f"[{self.name}] Quote fetch error: {r}")
            elif r:
                self.record_success()
                successful.append(r)
        return successful

    async def _fetch_single(self, symbol: str) -> Dict[str, Any]:
        url = "https://finnhub.io/api/v1/quote"
        cache_key = f"last_good_price:{symbol}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params={
                    "symbol": symbol,
                    "token": settings.FINNHUB_API_KEY
                })

                # Track quota from headers
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining is not None:
                    self.update_quota(int(remaining))

                if response.status_code == 429:
                    self.record_failure()
                    logger.warning(f"[{self.name}] Rate limit hit for {symbol}")
                    return await cache_client.get(cache_key) or {}

                response.raise_for_status()
                data = response.json()

                if data.get("c", 0) == 0:
                    return await cache_client.get(cache_key) or {}

                result = {
                    "symbol": symbol,
                    "price": round(data["c"], 2),
                    "changePercent": round(data.get("dp", 0), 2),
                }
                await cache_client.set(cache_key, result, expire_seconds=86400)
                return result

        except Exception as e:
            self.record_failure()
            logger.warning(f"[{self.name}] Error for {symbol}: {e}")
            return await cache_client.get(cache_key) or {}
