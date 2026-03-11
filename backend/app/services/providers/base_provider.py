"""
Base provider interface for the Smart Data Broker.
All market data providers must implement this contract.
"""
import abc
import logging
from typing import Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class QuoteResult:
    """Unified quote shape returned by all providers."""
    symbol: str
    price: float
    change_percent: float


class BaseProvider(abc.ABC):
    """
    Abstract base class for all market data providers.
    
    Each implementation must:
      1. Fetch live quotes for a list of symbols
      2. Report its remaining API quota (used by the DataBroker scorer)
      3. Report its speed weight (static; fast providers score higher)
      4. Report which symbols it supports
    """

    name: str = "base"
    speed_weight: float = 1.0  # 1.0 = fastest, 0.1 = slowest

    def __init__(self):
        self._remaining_quota: int = 999  # Default: unlimited
        self._consecutive_failures: int = 0

    # ── Public API ──────────────────────────────────────────────

    @abc.abstractmethod
    async def fetch_quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch live price quotes for the given symbols.
        Must return dicts matching: {"symbol": str, "price": float, "changePercent": float}
        """
        ...

    @abc.abstractmethod
    def supports_symbol(self, symbol: str) -> bool:
        """Returns True if this provider can fetch data for the given symbol."""
        ...

    # ── Quota Tracking ──────────────────────────────────────────

    @property
    def remaining_quota(self) -> int:
        return self._remaining_quota

    def update_quota(self, remaining: int):
        """Called after each API response with the rate-limit header value."""
        self._remaining_quota = remaining

    def record_failure(self):
        """Called when a fetch attempt fails. Increases the failure penalty."""
        self._consecutive_failures += 1

    def record_success(self):
        """Called when a fetch attempt succeeds. Resets the failure counter."""
        self._consecutive_failures = 0

    # ── Scoring ─────────────────────────────────────────────────

    @property
    def score(self) -> float:
        """
        Composite score used by the DataBroker to rank providers.
        Higher = better.
        
        Formula:  remaining_quota × speed_weight × reliability_penalty
        """
        reliability = max(0.1, 1.0 - (self._consecutive_failures * 0.25))
        return self._remaining_quota * self.speed_weight * reliability
