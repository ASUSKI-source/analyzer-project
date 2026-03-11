"""
Pydantic schemas for Watchlist CRUD operations.
CONVENTIONS §2: Schemas validate input/output at the HTTP boundary.
"""
from typing import List
from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


class WatchlistAddRequest(BaseModel):
    """Input validation for adding a symbol to a user's watchlist."""
    symbol: str = Field(..., min_length=1, max_length=10, description="Ticker symbol to add")

    @field_validator("symbol")
    @classmethod
    def sanitize_symbol(cls, v: str) -> str:
        """Security: Only allow alphanumeric symbols + hyphens, uppercase normalized."""
        v = v.strip().upper()
        if not re.match(r"^[A-Z0-9\-]+$", v):
            raise ValueError("Symbol must be alphanumeric (e.g. AAPL, BTC-USD)")
        return v


class WatchlistSymbol(BaseModel):
    """Single watchlist entry returned to the frontend."""
    symbol: str
    name: str
    asset_type: str

    model_config = ConfigDict(from_attributes=True)


class WatchlistResponse(BaseModel):
    """Full watchlist payload for a user."""
    symbols: List[WatchlistSymbol]
    count: int
