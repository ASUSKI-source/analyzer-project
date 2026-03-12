"""
DataBroker — the smart, quota-aware routing engine.

Scores all registered providers by remaining_quota × speed_weight × reliability
and picks the optimal one for each request. Falls back through providers on failure.
"""
import logging
import time
from typing import Dict, Any, List, Optional
from app.services.providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)


class DataBroker:
    """
    Central routing engine for market data.
    
    Usage:
        broker = DataBroker()
        broker.register(FinnhubProvider())
        broker.register(BinanceProvider())
        broker.register(YFinanceProvider())
        
        quotes = await broker.fetch_quotes(["AAPL", "BTC", "TSLA"])
    """

    def __init__(self):
        self._providers: List[BaseProvider] = []

    def register(self, provider: BaseProvider):
        """Add a provider to the routing pool."""
        self._providers.append(provider)
        logger.info(f"[DataBroker] Registered provider: {provider.name} "
                     f"(speed={provider.speed_weight}, quota={provider.remaining_quota})")

    def get_status(self) -> List[Dict[str, Any]]:
        """Returns the current state of all providers (for debugging/admin)."""
        return [
            {
                "name": p.name,
                "score": round(p.score, 1),
                "remaining_quota": p.remaining_quota,
                "speed_weight": p.speed_weight,
                "failures": p._consecutive_failures,
            }
            for p in sorted(self._providers, key=lambda p: p.score, reverse=True)
        ]

    async def fetch_quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Smart routing: splits symbols by provider support, scores providers,
        picks the best, and falls back on failure.
        """
        if not symbols:
            return []

        # Sanitize inputs
        clean_symbols = [s.upper().strip() for s in symbols]

        # Group symbols by which providers support them
        # For each symbol, get a ranked list of providers
        all_results: Dict[str, Dict[str, Any]] = {}
        remaining_symbols = set(clean_symbols)

        # Sort providers by score descending
        ranked = sorted(self._providers, key=lambda p: p.score, reverse=True)

        for provider in ranked:
            if not remaining_symbols:
                break

            # Which of the remaining symbols does this provider support?
            supported = [s for s in remaining_symbols if provider.supports_symbol(s)]
            if not supported:
                continue

            logger.info(
                f"[DataBroker] Routing {supported} → {provider.name} "
                f"(score={provider.score:.1f}, quota={provider.remaining_quota})"
            )

            batch_start = time.monotonic()
            try:
                results = await provider.fetch_quotes(supported)
                resolved_before = len(all_results)
                for r in results:
                    sym = r.get("symbol", "").upper()
                    if sym and r.get("price", 0) > 0:
                        all_results[sym] = r
                        remaining_symbols.discard(sym)
                elapsed = time.monotonic() - batch_start
                resolved_now = len(all_results) - resolved_before
                logger.info(
                    f"[DataBroker] {provider.name} completed in {elapsed:.2f}s; "
                    f"resolved_now={resolved_now}, unresolved_remaining={len(remaining_symbols)}"
                )
            except Exception as e:
                provider.record_failure()
                elapsed = time.monotonic() - batch_start
                logger.warning(f"[DataBroker] {provider.name} failed: {e}. "
                              f"elapsed={elapsed:.2f}s. Falling back to next provider.")

        # If any symbols still unresolved, log it
        if remaining_symbols:
            logger.warning(f"[DataBroker] No provider could resolve: {remaining_symbols}")

        total_resolved = len(all_results)
        logger.info(
            f"[DataBroker] completed request: requested={len(clean_symbols)}, "
            f"resolved={total_resolved}, unresolved={len(remaining_symbols)}"
        )

        # Return in original order, with zeroed-out entries for unresolved symbols
        return [
            all_results.get(s, {"symbol": s, "price": 0, "changePercent": 0})
            for s in clean_symbols
        ]


# ── Singleton Instance ──────────────────────────────────────────
# Initialized lazily by broker_instance() to avoid import-time side effects.

_broker: Optional[DataBroker] = None


def get_broker() -> DataBroker:
    """
    Returns the global DataBroker singleton.
    Initializes and registers all providers on first call.
    """
    global _broker
    if _broker is not None:
        return _broker

    from app.services.providers.finnhub_provider import FinnhubProvider
    from app.services.providers.binance_provider import BinanceProvider
    from app.services.providers.yfinance_provider import YFinanceProvider

    _broker = DataBroker()
    _broker.register(FinnhubProvider())
    _broker.register(BinanceProvider())
    _broker.register(YFinanceProvider())  # Always-available fallback

    logger.info(f"[DataBroker] Initialized with {len(_broker._providers)} providers.")
    return _broker
