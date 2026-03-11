"""
AI Analysis Routes — Serves AI-powered watchlist reports.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.services.ai_analyzer import generate_watchlist_report
from app.services.watchlist import get_user_watchlist

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/watchlist-analysis")
async def get_watchlist_analysis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    symbols: Optional[str] = Query(None, description="Comma-separated symbols to analyze (overrides watchlist)")
):
    """
    Generate an AI-powered analysis of the user's watchlist.
    
    - Authenticated users only (401 for guests).
    - Override: pass ?symbols=AAPL,BTC,SPY to analyze specific symbols.
    - Reports are cached for 8 hours (open/close scanning).
    """
    # Determine which symbols to analyze
    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        # Pull from user's saved watchlist via the existing service
        watchlist_items = await get_user_watchlist(db, current_user)
        symbol_list = [item["symbol"] for item in watchlist_items]

    if not symbol_list:
        return {
            "error": "No symbols to analyze. Add items to your watchlist first.",
            "assets": []
        }

    # Cap at 20 symbols to prevent abuse
    symbol_list = symbol_list[:20]

    user_id = str(current_user.id)
    report = await generate_watchlist_report(symbols=symbol_list, user_id=user_id)

    return report
