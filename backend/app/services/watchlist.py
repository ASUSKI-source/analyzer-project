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
from sqlalchemy.exc import IntegrityError
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
        # Ingest new asset metadata
        crypto_symbols = {"BTC", "ETH", "SOL", "DOGE", "ADA", "XRP", "DOT", "AVAX", "MATIC", "LINK", "SHIB", "LTC", "BCH", "UNI", "NEAR", "ATOM", "APT", "ARB", "OP", "TIA", "INJ", "RENDER", "FET", "PEPE", "BONK", "SUI", "SEI", "WIF"}
        is_crypto = symbol.upper() in crypto_symbols or "-" in symbol
        
        name = symbol.upper()
        asset_type = "crypto" if is_crypto else "stock"
        
        # Try a quick metadata lookup if possible
        try:
            from app.services.polygon import search_polygon_tickers
            polygon_matches = await search_polygon_tickers(symbol.upper())
            for match in polygon_matches:
                if match["symbol"] == symbol.upper():
                    name = match["name"]
                    asset_type = match["type"]
                    break
        except Exception:
            pass # Fallback to default name/type

        new_asset = Asset(symbol=symbol.upper(), name=name, asset_type=asset_type)
        db.add(new_asset)
        try:
            await db.flush()
            asset = new_asset
        except IntegrityError:
            await db.rollback()
            result2 = await db.execute(select(Asset).where(Asset.symbol == symbol.upper()))
            asset = result2.scalars().first()

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

    try:
        await db.execute(
            watchlist_asset_association.insert().values(watchlist_id=watchlist.id, asset_id=asset.id)
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Duplicate association inserted concurrently — treat as success.
        return {"symbol": asset.symbol, "name": asset.name, "asset_type": asset.asset_type, "already_existed": True}

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


async def search_symbols(db: AsyncSession, query: str) -> List[Dict[str, str]]:
    """
    Unified search for ticker symbols.
    1. Search local DB first (fast, covers active assets).
    2. Fallback to Polygon reference API if local results are sparse.
    3. Ensure no duplicates and standard formatting.
    """
    query = query.strip()
    if not query:
        return []

    # 1. Search locally in the 'assets' table
    # Match symbols or names that contain the query string (case-insensitive)
    search_pattern = f"%{query}%"
    stmt = (
        select(Asset)
        .where(
            (Asset.symbol.ilike(search_pattern)) | 
            (Asset.name.ilike(search_pattern))
        )
        .limit(10)
    )
    result = await db.execute(stmt)
    db_assets = result.scalars().all()

    results_map = {
        a.symbol: {"symbol": a.symbol, "name": a.name, "type": a.asset_type}
        for a in db_assets
    }

    # 2. Fallback to Polygon if we have few local results (only if API key is present)
    if len(results_map) < 5:
        try:
            from app.services.polygon import search_polygon_tickers
            ext_results = await search_polygon_tickers(query)
            for r in ext_results:
                if r["symbol"] not in results_map:
                    results_map[r["symbol"]] = r
        except ImportError:
            pass # Polygon service might not be fully initialized or module missing in some envs
        except Exception as e:
            # We don't want to crash the whole search if Polygon fails
            pass

    return list(results_map.values())[:15]
