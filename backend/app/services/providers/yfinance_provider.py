"""
yfinance Provider Adapter — the "infinite battery" fallback.
Supports both stocks and crypto. No API key, no rate limits.
Lowest speed_weight because it uses synchronous HTTP under the hood.
"""
import asyncio
import logging
from typing import Dict, Any, List

from app.services.providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)


class YFinanceProvider(BaseProvider):
    """
    Fallback provider using the yfinance library.
    Always available (no API key needed), but slower due to synchronous I/O.
    """
    name = "yfinance"
    speed_weight = 0.3  # Lowest priority — only used when paid providers run low

    def __init__(self):
        super().__init__()
        self._remaining_quota = 999  # Effectively unlimited

    def supports_symbol(self, symbol: str) -> bool:
        """yfinance supports virtually all tradeable symbols."""
        return True

    async def fetch_quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch quotes using yfinance, wrapped in asyncio.to_thread()
        to avoid blocking the FastAPI event loop.
        """
        try:
            results = await asyncio.to_thread(self._sync_fetch, symbols)
            self.record_success()
            return results
        except Exception as e:
            self.record_failure()
            logger.warning(f"[{self.name}] yfinance error: {e}")
            return []

    def _sync_fetch(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Synchronous yfinance fetch — runs in a thread pool."""
        import yfinance as yf

        results: List[Dict[str, Any]] = []

        # Map crypto symbols to Yahoo's format (e.g., BTC → BTC-USD)
        yahoo_symbols = []
        original_map = {}
        for sym in symbols:
            sym_upper = sym.upper()
            if self._is_likely_crypto(sym_upper):
                yahoo_sym = f"{sym_upper}-USD"
            else:
                yahoo_sym = sym_upper
            yahoo_symbols.append(yahoo_sym)
            original_map[yahoo_sym] = sym_upper

        # Batch download for efficiency
        ticker_str = " ".join(yahoo_symbols)
        tickers = yf.Tickers(ticker_str)

        for yahoo_sym, original_sym in original_map.items():
            try:
                ticker = tickers.tickers.get(yahoo_sym)
                if not ticker:
                    continue

                info = ticker.fast_info
                price = getattr(info, "last_price", None)
                prev_close = getattr(info, "previous_close", None)

                if price and price > 0:
                    change_pct = 0.0
                    if prev_close and prev_close > 0:
                        change_pct = round(((price - prev_close) / prev_close) * 100, 2)

                    results.append({
                        "symbol": original_sym,
                        "price": round(price, 4 if price < 5 else 2),
                        "changePercent": change_pct,
                    })
            except Exception as e:
                logger.debug(f"[{self.name}] Skipping {yahoo_sym}: {e}")
                continue

        return results

    @staticmethod
    def _is_likely_crypto(symbol: str) -> bool:
        """Heuristic to detect crypto symbols."""
        crypto_symbols = {
            "BTC", "ETH", "SOL", "DOGE", "ADA", "XRP", "DOT",
            "AVAX", "MATIC", "LINK", "SHIB", "LTC", "BCH", "UNI",
            "NEAR", "ATOM", "APT", "ARB", "OP", "TIA", "INJ",
            "RENDER", "FET", "PEPE",
        }
        return symbol in crypto_symbols
