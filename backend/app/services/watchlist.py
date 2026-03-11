"""
Watchlist Service Layer.
CONVENTIONS §2: All business logic lives here, NOT in route handlers.
Routes only call these functions and return their output.
"""
import logging
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.user import User, user_watchlist_association
from app.models.market import Asset

logger = logging.getLogger(__name__)


async def get_user_watchlist(db: AsyncSession, user: User) -> List[Dict[str, Any]]:
    """
    Fetch all assets on a user's watchlist.
    Returns list of dicts with symbol, name, asset_type.
    """
    # Eagerly load the relationship to avoid lazy-load issues in async
    result = await db.execute(
        select(Asset)
        .join(user_watchlist_association, Asset.id == user_watchlist_association.c.asset_id)
        .where(user_watchlist_association.c.user_id == user.id)
        .order_by(user_watchlist_association.c.added_at.desc())
    )
    assets = result.scalars().all()

    return [
        {"symbol": a.symbol, "name": a.name, "asset_type": a.asset_type}
        for a in assets
    ]


async def add_to_watchlist(db: AsyncSession, user: User, symbol: str) -> Dict[str, Any]:
    """
    Add a symbol to the user's watchlist.
    Creates the Asset record if it doesn't exist yet (auto-discovery).
    Security: user_id comes from JWT, never from request body.
    """
    # Find or create the asset record
    result = await db.execute(select(Asset).where(Asset.symbol == symbol))
    asset = result.scalars().first()

    if not asset:
        # Auto-create asset entry for new symbols
        # Docs: We infer asset_type from symbol pattern. Crypto symbols contain hyphens (BTC-USD)
        # or are in our known crypto list. Everything else is 'stock'.
        # Use a more comprehensive list for auto-discovery
        crypto_symbols = {
            "BTC", "ETH", "SOL", "DOGE", "ADA", "XRP", "DOT", "AVAX", "MATIC", "LINK",
            "SHIB", "LTC", "BCH", "UNI", "NEAR", "ATOM", "APT", "ARB", "OP", "TIA",
            "INJ", "RENDER", "FET", "PEPE", "BONK", "SUI", "SEI", "WIF"
        }
        is_crypto = symbol.upper() in crypto_symbols or "-" in symbol
        asset = Asset(
            symbol=symbol,
            name=symbol,  # Placeholder name — updated when real data is fetched
            asset_type="crypto" if is_crypto else "stock"
        )
        db.add(asset)
        await db.flush()  # Get the asset.id without committing

    # Check if already on watchlist (prevent duplicate entries)
    existing = await db.execute(
        select(user_watchlist_association)
        .where(
            user_watchlist_association.c.user_id == user.id,
            user_watchlist_association.c.asset_id == asset.id
        )
    )
    if existing.first():
        return {"symbol": asset.symbol, "name": asset.name, "asset_type": asset.asset_type, "already_existed": True}

    # Insert the association
    await db.execute(
        user_watchlist_association.insert().values(user_id=user.id, asset_id=asset.id)
    )
    await db.commit()
    logger.info(f"User {user.email} added {symbol} to watchlist")

    return {"symbol": asset.symbol, "name": asset.name, "asset_type": asset.asset_type, "already_existed": False}


async def remove_from_watchlist(db: AsyncSession, user: User, symbol: str) -> bool:
    """
    Remove a symbol from the user's watchlist.
    Returns True if removed, False if it wasn't on the list.
    """
    result = await db.execute(select(Asset).where(Asset.symbol == symbol))
    asset = result.scalars().first()

    if not asset:
        return False

    delete_result = await db.execute(
        delete(user_watchlist_association)
        .where(
            user_watchlist_association.c.user_id == user.id,
            user_watchlist_association.c.asset_id == asset.id
        )
    )
    await db.commit()

    removed = delete_result.rowcount > 0
    if removed:
        logger.info(f"User {user.email} removed {symbol} from watchlist")
    return removed


async def search_symbols(query: str) -> List[Dict[str, str]]:
    """
    Search for ticker symbols matching a query string.
    Uses a curated local dictionary for instant results without 
    hitting external APIs (avoids Polygon rate limits per CONVENTIONS §7.1).
    """
    query = query.upper().strip()
    if len(query) < 1:
        return []

    # Curated symbol dictionary — covers the most commonly traded assets.
    # Docs: This is intentionally local to avoid rate-limiting on Polygon's
    # reference endpoint. Can be expanded or replaced with a DB table later.
    SYMBOL_DICT = [
        {"symbol": "AAPL", "name": "Apple Inc.", "type": "stock"},
        {"symbol": "MSFT", "name": "Microsoft Corp.", "type": "stock"},
        {"symbol": "GOOGL", "name": "Alphabet Inc.", "type": "stock"},
        {"symbol": "AMZN", "name": "Amazon.com Inc.", "type": "stock"},
        {"symbol": "NVDA", "name": "NVIDIA Corp.", "type": "stock"},
        {"symbol": "META", "name": "Meta Platforms Inc.", "type": "stock"},
        {"symbol": "TSLA", "name": "Tesla Inc.", "type": "stock"},
        {"symbol": "AMD", "name": "Advanced Micro Devices", "type": "stock"},
        {"symbol": "NFLX", "name": "Netflix Inc.", "type": "stock"},
        {"symbol": "JPM", "name": "JPMorgan Chase", "type": "stock"},
        {"symbol": "V", "name": "Visa Inc.", "type": "stock"},
        {"symbol": "DIS", "name": "Walt Disney Co.", "type": "stock"},
        {"symbol": "BA", "name": "Boeing Co.", "type": "stock"},
        {"symbol": "INTC", "name": "Intel Corp.", "type": "stock"},
        {"symbol": "CRM", "name": "Salesforce Inc.", "type": "stock"},
        {"symbol": "UBER", "name": "Uber Technologies", "type": "stock"},
        {"symbol": "COIN", "name": "Coinbase Global", "type": "stock"},
        {"symbol": "PLTR", "name": "Palantir Technologies", "type": "stock"},
        {"symbol": "SPY", "name": "S&P 500 ETF", "type": "stock"},
        {"symbol": "QQQ", "name": "Nasdaq 100 ETF", "type": "stock"},
        {"symbol": "VIX", "name": "CBOE Volatility Index", "type": "stock"},
        {"symbol": "BTC", "name": "Bitcoin", "type": "crypto"},
        {"symbol": "ETH", "name": "Ethereum", "type": "crypto"},
        {"symbol": "SOL", "name": "Solana", "type": "crypto"},
        {"symbol": "DOGE", "name": "Dogecoin", "type": "crypto"},
        {"symbol": "ADA", "name": "Cardano", "type": "crypto"},
        {"symbol": "XRP", "name": "Ripple", "type": "crypto"},
        {"symbol": "DOT", "name": "Polkadot", "type": "crypto"},
        {"symbol": "AVAX", "name": "Avalanche", "type": "crypto"},
        {"symbol": "MATIC", "name": "Polygon", "type": "crypto"},
        {"symbol": "LINK", "name": "Chainlink", "type": "crypto"},
    ]

    results = [
        s for s in SYMBOL_DICT
        if query in s["symbol"] or query in s["name"].upper()
    ]

    return results[:10]  # Cap at 10 results to keep responses fast
