from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.portfolio import (
    NamedWatchlistCreate,
    NamedWatchlistResponse,
    PortfolioCreate,
    PortfolioResponse,
)
from app.services.portfolio import (
    create_named_watchlist,
    create_portfolio,
    list_named_watchlists,
    list_portfolios,
)

router = APIRouter()


@router.get("/", response_model=List[PortfolioResponse])
async def get_portfolios(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the authenticated user's portfolio containers."""
    return await list_portfolios(db, current_user)


@router.post("/", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
async def post_portfolio(
    payload: PortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a portfolio container for future holdings simulation/tracking."""
    return await create_portfolio(db, current_user, payload.name)


@router.get("/watchlists", response_model=List[NamedWatchlistResponse])
async def get_named_watchlists(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List named watchlists (future multi-watchlist feature)."""
    return await list_named_watchlists(db, current_user)


@router.post("/watchlists", response_model=NamedWatchlistResponse, status_code=status.HTTP_201_CREATED)
async def post_named_watchlist(
    payload: NamedWatchlistCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a named watchlist container for future per-list symbol grouping."""
    return await create_named_watchlist(db, current_user, payload.name)
