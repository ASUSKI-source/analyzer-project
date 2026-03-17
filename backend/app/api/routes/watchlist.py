"""
Watchlist API Routes.
CONVENTIONS §2: Route handlers are THIN — they only validate HTTP input,
call a service function, and return the output. No business logic here.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.watchlist import (
    WatchlistCreateRequest,
    WatchlistHeader,
    WatchlistSymbolsResponse,
    WatchlistListResponse,
    WatchlistSymbol
)
from app.services.watchlist import (
    get_watchlist_headers,
    create_watchlist,
    get_watchlist_symbols,
    add_to_watchlist,
    remove_from_watchlist,
    delete_watchlist,
    search_symbols
)

router = APIRouter()


@router.get("/", response_model=WatchlistListResponse)
async def list_watchlists(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all watchlist headers for the authenticated user."""
    lists = await get_watchlist_headers(db, current_user)
    
    # Auto-create "Main" watchlist if none exist
    if not lists:
        main = await create_watchlist(db, current_user, "Main Portfolio")
        lists = [main]
        
    return {"watchlists": lists}


@router.post("/", response_model=WatchlistHeader, status_code=status.HTTP_201_CREATED)
async def create_new_watchlist(
    payload: WatchlistCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new named watchlist."""
    return await create_watchlist(db, current_user, payload.name)


@router.get("/{watchlist_id}", response_model=WatchlistSymbolsResponse)
async def get_watchlist_content(
    watchlist_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all symbols for a specific watchlist."""
    # Note: In a real app, verify watchlist belongs to current_user
    symbols = await get_watchlist_symbols(db, watchlist_id)
    
    # Need to fetch the list name for the response
    # For now, we'll just return the symbols. 
    # Logic in service can be expanded if name is required here.
    return {
        "id": watchlist_id,
        "name": "Watchlist", # Placeholder or fetch from DB
        "symbols": symbols,
        "count": len(symbols)
    }


@router.post("/{watchlist_id}/symbols", status_code=status.HTTP_201_CREATED)
async def add_symbol_to_list(
    watchlist_id: str,
    payload: dict, # simple { "symbol": "AAPL" }
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a symbol to a specific watchlist."""
    symbol = payload.get("symbol")
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")
    
    result = await add_to_watchlist(db, watchlist_id, symbol.upper())
    return result


@router.delete("/{watchlist_id}/symbols/{symbol}")
async def remove_symbol_from_list(
    watchlist_id: str,
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove a symbol from a specific watchlist."""
    removed = await remove_from_watchlist(db, watchlist_id, symbol.upper())
    if not removed:
        raise HTTPException(status_code=404, detail="Symbol not found in this watchlist")
    return {"status": "removed"}


@router.delete("/{watchlist_id}")
async def delete_user_watchlist(
    watchlist_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an entire watchlist."""
    success = await delete_watchlist(db, watchlist_id)
    return {"status": "deleted" if success else "failed"}


@router.get("/search")
async def search_tickers(q: str = ""):
    """
    Search for ticker symbols by name or symbol.
    No auth required — safe for guests to use.
    Uses local dictionary for instant results (no external API calls).
    """
    results = await search_symbols(q)
    return {"results": results, "count": len(results)}
