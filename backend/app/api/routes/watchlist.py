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
from app.schemas.watchlist import WatchlistAddRequest, WatchlistResponse
from app.services.watchlist import (
    get_user_watchlist,
    add_to_watchlist,
    remove_from_watchlist,
    search_symbols
)

router = APIRouter()


@router.get("/", response_model=WatchlistResponse)
async def get_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all symbols on the authenticated user's watchlist."""
    items = await get_user_watchlist(db, current_user)
    return {"symbols": items, "count": len(items)}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_watchlist_symbol(
    payload: WatchlistAddRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add a symbol to the authenticated user's watchlist.
    Security: user_id extracted from JWT, never from the request body.
    """
    result = await add_to_watchlist(db, current_user, payload.symbol)
    
    if result["already_existed"]:
        return {"status": "exists", "message": f"{payload.symbol} is already on your watchlist"}
    
    return {"status": "added", "symbol": result["symbol"], "name": result["name"]}


@router.delete("/{symbol}")
async def remove_watchlist_symbol(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove a symbol from the authenticated user's watchlist."""
    symbol = symbol.upper()
    removed = await remove_from_watchlist(db, current_user, symbol)
    
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{symbol} was not found on your watchlist"
        )
    
    return {"status": "removed", "symbol": symbol}


@router.get("/search")
async def search_tickers(q: str = ""):
    """
    Search for ticker symbols by name or symbol.
    No auth required — safe for guests to use.
    Uses local dictionary for instant results (no external API calls).
    """
    results = await search_symbols(q)
    return {"results": results, "count": len(results)}
