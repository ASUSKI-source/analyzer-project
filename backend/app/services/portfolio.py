from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Portfolio, Watchlist
from app.models.user import User


async def list_portfolios(db: AsyncSession, user: User) -> List[Portfolio]:
    result = await db.execute(
        select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.created_at.desc())
    )
    return result.scalars().all()


async def create_portfolio(db: AsyncSession, user: User, name: str) -> Portfolio:
    portfolio = Portfolio(user_id=user.id, name=name.strip())
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return portfolio


async def list_named_watchlists(db: AsyncSession, user: User) -> List[Watchlist]:
    result = await db.execute(
        select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.created_at.desc())
    )
    return result.scalars().all()


async def create_named_watchlist(db: AsyncSession, user: User, name: str) -> Watchlist:
    watchlist = Watchlist(user_id=user.id, name=name.strip())
    db.add(watchlist)
    await db.commit()
    await db.refresh(watchlist)
    return watchlist
