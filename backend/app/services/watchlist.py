"""
Watchlist Service Layer.
CONVENTIONS §2: All business logic lives here, NOT in route handlers.
Routes only call these functions and return their output.
"""
import logging
import re
import uuid as _uuid
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, or_, func
from app.models.user import User
from app.models.portfolio import Watchlist, watchlist_asset_association
from app.models.market import Asset

logger = logging.getLogger(__name__)


def _to_uuid(value: Any) -> _uuid.UUID | None:
    """Safely coerce a string or UUID to a uuid.UUID; return None on failure."""
    if isinstance(value, _uuid.UUID):
        return value
    try:
        return _uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


async def _get_user_watchlist(db: AsyncSession, watchlist_id: Any, user_id: Any) -> Watchlist | None:
    wl_uuid = _to_uuid(watchlist_id)
    if wl_uuid is None:
        return None
    result = await db.execute(
        select(Watchlist).where(Watchlist.id == wl_uuid, Watchlist.user_id == user_id)
    )
    return result.scalars().first()


async def get_watchlist_headers(db: AsyncSession, user: User) -> List[Dict[str, Any]]:
    """Fetch all watchlist headers (id, name) for a user."""
    result = await db.execute(
        select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.created_at.asc())
    )
    lists = result.scalars().all()
    return [{"id": str(l.id), "name": l.name} for l in lists]


async def create_watchlist(db: AsyncSession, user: User, name: str) -> Dict[str, Any]:
    """Create a new named watchlist for a user."""
    new_list = Watchlist(user_id=user.id, name=name)
    db.add(new_list)
    await db.commit()
    logger.info(f"User {user.email} created watchlist: {name}")
    return {"id": str(new_list.id), "name": new_list.name}


async def get_watchlist_symbols(db: AsyncSession, watchlist_id: str, user: User) -> List[Dict[str, Any]] | None:
    """Fetch all assets on a specific watchlist."""
    watchlist = await _get_user_watchlist(db, watchlist_id, user.id)
    if not watchlist:
        return None
    result = await db.execute(
        select(Asset)
        .join(watchlist_asset_association, Asset.id == watchlist_asset_association.c.asset_id)
        .where(watchlist_asset_association.c.watchlist_id == watchlist.id)
        .order_by(watchlist_asset_association.c.added_at.desc())
    )
    assets = result.scalars().all()
    return [{"symbol": a.symbol, "name": a.name, "asset_type": a.asset_type} for a in assets]


async def add_to_watchlist(db: AsyncSession, watchlist_id: str, symbol: str, user: User) -> Dict[str, Any]:
    """Add a symbol to a specific watchlist."""
    watchlist = await _get_user_watchlist(db, watchlist_id, user.id)
    if not watchlist:
        return {"error": "watchlist_not_found"}

    # Find or create the asset record
    result = await db.execute(select(Asset).where(Asset.symbol == symbol))
    asset = result.scalars().first()

    if not asset:
        crypto_symbols = {"BTC", "ETH", "SOL", "DOGE", "ADA", "XRP", "DOT", "AVAX", "MATIC", "LINK", "SHIB", "LTC", "BCH", "UNI", "NEAR", "ATOM", "APT", "ARB", "OP", "TIA", "INJ", "RENDER", "FET", "PEPE", "BONK", "SUI", "SEI", "WIF"}
        is_crypto = symbol.upper() in crypto_symbols or "-" in symbol
        asset = Asset(symbol=symbol, name=symbol, asset_type="crypto" if is_crypto else "stock")
        db.add(asset)
        await db.flush()

    # Check if already on this specific watchlist
    existing = await db.execute(
        select(watchlist_asset_association)
        .where(
            watchlist_asset_association.c.watchlist_id == watchlist.id,
            watchlist_asset_association.c.asset_id == asset.id
        )
    )
    if existing.first():
        return {"symbol": asset.symbol, "name": asset.name, "asset_type": asset.asset_type, "already_existed": True}

    await db.execute(
        watchlist_asset_association.insert().values(watchlist_id=watchlist.id, asset_id=asset.id)
    )
    await db.commit()
    return {"symbol": asset.symbol, "name": asset.name, "asset_type": asset.asset_type, "already_existed": False}


async def remove_from_watchlist(db: AsyncSession, watchlist_id: str, symbol: str, user: User) -> bool:
    """Remove a symbol from a specific watchlist."""
    watchlist = await _get_user_watchlist(db, watchlist_id, user.id)
    if not watchlist:
        return False

    result = await db.execute(select(Asset).where(Asset.symbol == symbol))
    asset = result.scalars().first()
    if not asset: return False

    delete_result = await db.execute(
        delete(watchlist_asset_association)
        .where(
            watchlist_asset_association.c.watchlist_id == watchlist.id,
            watchlist_asset_association.c.asset_id == asset.id
        )
    )
    await db.commit()
    return delete_result.rowcount > 0


async def delete_watchlist(db: AsyncSession, watchlist_id: str, user: User) -> bool:
    """Delete an entire watchlist and its asset associations."""
    wl_uuid = _to_uuid(watchlist_id)
    if wl_uuid is None:
        return False
    delete_result = await db.execute(
        delete(Watchlist).where(Watchlist.id == wl_uuid, Watchlist.user_id == user.id)
    )
    await db.commit()
    return delete_result.rowcount > 0


async def search_symbols(query: str) -> List[Dict[str, str]]:
    """
    Search for ticker symbols matching a query string.
    Uses a curated local dictionary for instant results without 
    hitting external APIs (avoids Polygon rate limits per CONVENTIONS §7.1).
    """
    query = query.strip()
    if len(query) < 1:
        return []
    query = query[:40]
    if not re.fullmatch(r"[A-Za-z0-9\-/\.\s]+", query):
        return []

    normalized = query.upper()
    normalized = re.sub(r"[/\.\s]+", "-", normalized)
    normalized = normalized.removesuffix("-USD").removesuffix("-USDT")

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
        if normalized in s["symbol"]
        or normalized.replace("-", "") in s["symbol"].replace("-", "")
        or query.lower() in s["name"].lower()
    ]

    return results[:10]  # Cap at 10 results to keep responses fast


async def search_symbols_db(db: AsyncSession, query: str, limit: int = 15) -> List[Dict[str, str]]:
    """
    Canonical symbol search from local DB (no external API calls).
    Supports exact/prefix symbol and name contains matching.
    """
    query = query.strip()
    if len(query) < 1:
        return []
    query = query[:40]
    if not re.fullmatch(r"[A-Za-z0-9\-/\.\s]+", query):
        return []

    normalized = query.upper()
    normalized = re.sub(r"[/\.\s]+", "-", normalized)
    normalized = normalized.removesuffix("-USD").removesuffix("-USDT")
    compact = normalized.replace("-", "")

    stmt = (
        select(Asset)
        .where(
            or_(
                func.upper(Asset.symbol) == normalized,
                func.upper(Asset.symbol).like(f"{normalized}%"),
                func.replace(func.upper(Asset.symbol), "-", "").like(f"{compact}%"),
                func.upper(Asset.name).like(f"%{query.upper()}%"),
            )
        )
        .order_by(func.length(Asset.symbol).asc(), Asset.symbol.asc())
        .limit(max(1, min(limit, 25)))
    )
    result = await db.execute(stmt)
    assets = result.scalars().all()
    return [{"symbol": a.symbol, "name": a.name, "type": a.asset_type} for a in assets]
