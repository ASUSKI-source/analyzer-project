"""
Pydantic schemas for Watchlist CRUD operations.
CONVENTIONS §2: Schemas validate input/output at the HTTP boundary.
"""
from typing import List
from pydantic import BaseModel, ConfigDict, Field, field_validator
import re


class WatchlistCreateRequest(BaseModel):
    """Input validation for creating a new watchlist."""
    name: str = Field(..., min_length=1, max_length=50, description="Name of the new watchlist")


class WatchlistHeader(BaseModel):
    """Basic metadata for a watchlist."""
    id: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class WatchlistSymbol(BaseModel):
    """Single watchlist entry returned to the frontend."""
    symbol: str
    name: str
    asset_type: str

    model_config = ConfigDict(from_attributes=True)


class WatchlistSymbolsResponse(BaseModel):
    """Symbols payload for a specific watchlist."""
    id: str
    name: str
    symbols: List[WatchlistSymbol]
    count: int


class WatchlistListResponse(BaseModel):
    """List of all watchlists for a user."""
    watchlists: List[WatchlistHeader]
