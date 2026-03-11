
import asyncio
import os
import sys

sys.path.append(os.getcwd())

from app.core.database import async_session_factory
from app.models.market import Asset
from app.models.user import user_watchlist_association
from app.services.aggregator import fetch_watchlist_prices
from sqlalchemy import select

async def check_watchlist():
    async with async_session_factory() as session:
        # Get all symbols in all watchlists
        res = await session.execute(select(Asset.symbol, Asset.asset_type))
        assets = res.all()
        print(f"Watchlist Assets in DB: {assets}")
        
        symbols = [a[0] for a in assets]
        if symbols:
            prices = await fetch_watchlist_prices(symbols)
            print(f"Prices for symbols {symbols}:")
            for p in prices:
                print(f"  {p}")
        else:
            print("No assets in DB.")

if __name__ == "__main__":
    asyncio.run(check_watchlist())
