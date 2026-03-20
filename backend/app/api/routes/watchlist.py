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
import logging
from app.schemas.watchlist import (
    WatchlistCreateRequest,
    AddSymbolRequest,
    WatchlistHeader,
    WatchlistSymbolsResponse,
    WatchlistListResponse,
    WatchlistSymbol
)

logger = logging.getLogger(__name__)
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


@router.get("/search")
async def search_tickers(q: str = "", db: AsyncSession = Depends(get_db)):
    """
    Search for ticker symbols by name or symbol.
    No auth required — safe for guests to use.
    Uses local database with external fallback if results are sparse.
    """
    results = await search_symbols(db, q)
    return {"results": results, "count": len(results)}


@router.post("/{watchlist_id}/symbols", status_code=status.HTTP_201_CREATED)
async def add_symbol_to_list(
    watchlist_id: str,
    payload: AddSymbolRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a symbol to a specific watchlist."""
    try:
        result = await add_to_watchlist(db, watchlist_id, payload.symbol.upper().strip(), current_user)
        if result.get("error") == "watchlist_not_found":
            raise HTTPException(status_code=404, detail="Watchlist not found or access denied")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("add_symbol_to_list failed watchlist=%s symbol=%s user=%s: %s",
                     watchlist_id, payload.symbol, current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add symbol — please try again")


@router.get("/{watchlist_id}", response_model=WatchlistSymbolsResponse)
async def get_watchlist_content_route(
    watchlist_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all symbols and the name for a specific watchlist."""
    from app.services.watchlist import get_watchlist_content
    data = await get_watchlist_content(db, watchlist_id, current_user)
    if data is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    return {
        "id": data["id"],
        "name": data["name"],
        "symbols": data["symbols"],
        "count": len(data["symbols"])
    }


@router.delete("/{watchlist_id}/symbols/{symbol}")
async def remove_symbol_from_list(
    watchlist_id: str,
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove a symbol from a specific watchlist."""
    removed = await remove_from_watchlist(db, watchlist_id, symbol.upper(), current_user)
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
    success = await delete_watchlist(db, watchlist_id, current_user)
    return {"status": "deleted" if success else "failed"}


