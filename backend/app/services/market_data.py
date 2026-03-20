import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.core.errors import DataNotReadyException, AssetNotFoundException
from app.core.cache import cache_client
from app.models.market import Asset, AssetCandle
from app.utils.limiter import PolygonRateLimiter

logger = logging.getLogger(__name__)

async def get_or_create_asset(db: AsyncSession, symbol: str, name: str = "", asset_type: str = "stock") -> Asset:
    """Helper to verify an asset exists before we attach candles to it."""
    result = await db.execute(select(Asset).where(Asset.symbol == symbol))
    asset = result.scalars().first()
    
    if not asset:
        asset = Asset(symbol=symbol, name=name or symbol, asset_type=asset_type)
        db.add(asset)
        await db.commit()
        await db.refresh(asset)
    return asset

async def sync_asset_history(db: AsyncSession, symbol: str, days: int = 365, timeframe: str = "1d") -> int:
    """
    Fetches historical data from Polygon.io for a specific timeframe and saves it to the DB.
    Enforces global rate limits via PolygonRateLimiter.
    """
    asset = await get_or_create_asset(db, symbol)
    
    # Priority: 1d/1w = Priority 1, 5m/1h = Priority 2
    priority = 1 if timeframe in ["1d", "1w"] else 2
    
    if not await PolygonRateLimiter.acquire_token(priority=priority):
        raise DataNotReadyException(f"Polygon Rate Limit reached. Throttling {timeframe} sync for {symbol}.")

    # Calculate date bounds
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    # Polygon resolution mapping
    multiplier, timespan = 1, "day"
    if timeframe == "1h":
        multiplier, timespan = 1, "hour"
    elif timeframe == "5m":
        multiplier, timespan = 5, "minute"
    elif timeframe == "1w":
        multiplier, timespan = 1, "week"

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start_str}/{end_str}"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url, 
                params={"apiKey": settings.POLYGON_API_KEY, "adjusted": "true"}
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise AssetNotFoundException(f"Asset symbol {symbol} not found on external exchange.")
        elif e.response.status_code == 429:
            raise DataNotReadyException("Rate limit reached for market data. Try again later.")
        logger.error(f"Polygon API Error for {symbol}: {e}")
        raise DataNotReadyException("External market data provider is currently failing.")
    except Exception as e:
        logger.error(f"Network error fetching Polygon data for {symbol}: {e}")
        raise DataNotReadyException("Failed to reach external market data provider.")
        
    results = data.get("results", [])
    if not results:
        return 0
        
    candles = []
    for item in results:
        candle_time = datetime.fromtimestamp(item["t"] / 1000.0, tz=timezone.utc)
        candles.append({
            "asset_id": asset.id,
            "timestamp": candle_time,
            "timeframe": timeframe,
            "open": float(item["o"]),
            "high": float(item["h"]),
            "low": float(item["l"]),
            "close": float(item["c"]),
            "volume": float(item["v"]),
        })

    if not candles:
        return 0

    stmt = insert(AssetCandle).values(candles)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=['asset_id', 'timestamp', 'timeframe']
    )
    
    await db.execute(stmt)
    await db.commit()
    return len(candles)

async def get_live_intraday_history(db: AsyncSession, symbol: str, days: int):
    """
    Fetch high-fidelity intraday candles with Layer 2 "Heat Cache" and Layer 1 "Global Barrier".
    """
    symbol_upper = symbol.upper()
    
    # Layer 2: Intraday Heat Cache (300s)
    cache_key = f"intraday_cache:{symbol_upper}:{days}"
    cached_data = await cache_client.get(cache_key)
    if cached_data:
        # If it's the new tuple format [data, interval], return it
        if isinstance(cached_data, list) and len(cached_data) == 2 and isinstance(cached_data[1], int):
            return cached_data
        # Legacy cache compatibility: default to a reasonable interval if old data found
        return cached_data, 300 if days <= 1 else 3600

    chart_data = []
    interval_seconds = 3600 # default
    try:
        from app.services.coingecko import is_crypto, SYMBOL_TO_BINANCE
        
        # Determine timeframe for DB persistence
        if days <= 1:
            timeframe = "1m"
        elif days <= 7:
            timeframe = "1h"
        else:
            timeframe = "1d"

        if is_crypto(symbol_upper):
            b_id = SYMBOL_TO_BINANCE.get(symbol_upper)
            if not b_id: return [], 0
            
            # Refined Intervals: 1D -> 1m, 1W -> 30m
            if days <= 1:
                interval, limit, interval_seconds = ("1m", 1440, 60)
            elif days <= 7:
                interval, limit, interval_seconds = ("30m", 336, 1800)
            elif days <= 30:
                interval, limit, interval_seconds = ("4h", 180, 14400)
            else:
                interval, limit, interval_seconds = ("1d", min(days, 1000), 86400)

            url = "https://api.binance.us/api/v3/klines"
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url, params={"symbol": b_id, "interval": interval, "limit": limit})
                res.raise_for_status()
                for k in res.json():
                    chart_data.append({"time": int(k[0]) // 1000, "open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4]), "value": float(k[5])})
        else:
            # Layer 1: Polygon Global Barrier
            priority = 2 if days <= 1 else 1
            if not await PolygonRateLimiter.acquire_token(priority=priority):
                logger.warning(f"Throttling live intraday for {symbol_upper} to preserve API tokens.")
                return [], 0

            # Refined Intervals: 1D -> 1m, 1W -> 30m
            if days <= 1:
                multiplier, timespan, lookback, limit_candles, interval_seconds = (1, "minute", 1, 1440, 60)
            elif days <= 7:
                multiplier, timespan, lookback, limit_candles, interval_seconds = (30, "minute", 8, 336, 1800)
            elif days <= 30:
                multiplier, timespan, lookback, limit_candles, interval_seconds = (4, "hour", 40, 180, 14400)
            else:
                multiplier, timespan, lookback, limit_candles, interval_seconds = (1, "day", days + 10, days, 86400)

            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=lookback)
            
            url = f"https://api.polygon.io/v2/aggs/ticker/{symbol_upper}/range/{multiplier}/{timespan}/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url, params={"adjusted": "true", "sort": "asc", "apiKey": settings.POLYGON_API_KEY})
                res.raise_for_status()
                data = res.json()
                results = data.get("results", [])[-limit_candles:] if data.get("results") else []
                
                for item in results:
                    chart_data.append({
                        "time": int(item["t"]) // 1000,
                        "open": float(item["o"]), "high": float(item["h"]), "low": float(item["l"]), "close": float(item["c"]), "value": float(item["v"])
                    })
        
        # Save to DB for permanent high-fidelity fallback
        if chart_data:
            try:
                asset_obj = await get_or_create_asset(db, symbol_upper)
                db_candles = []
                for d in chart_data:
                    db_candles.append({
                        "asset_id": asset_obj.id,
                        "timestamp": datetime.fromtimestamp(d["time"], tz=timezone.utc),
                        "timeframe": timeframe,
                        "open": d["open"],
                        "high": d["high"],
                        "low": d["low"],
                        "close": d["close"],
                        "volume": d["value"],
                    })
                
                if db_candles:
                    stmt = insert(AssetCandle).values(db_candles)
                    stmt = stmt.on_conflict_do_nothing(index_elements=['asset_id', 'timestamp', 'timeframe'])
                    await db.execute(stmt)
                    await db.commit()
                    logger.info(f"Persisted {len(db_candles)} {timeframe} candles to DB for {symbol_upper}")
            except Exception as db_err:
                logger.warning(f"Failed to persist live intraday for {symbol_upper}: {db_err}")

        # Save to Heat Cache
        await cache_client.set(cache_key, [chart_data, interval_seconds], expire_seconds=300)

    except Exception as e:
        logger.error(f"Live Intraday error for {symbol_upper}: {e}")
        return [], 0

    return chart_data, interval_seconds


async def get_asset_history(
    db: AsyncSession, 
    symbol: str, 
    days: int = 365, 
    current_price: Optional[float] = None,
    refresh: bool = False,
    timeframe: Optional[str] = None,
    return_meta: bool = False,
):
    """
    Retrieves historical candlestick data for a given asset from our TimescaleDB.
    Returns it in a structured format ready for TradingView Lightweight charts.
    If refresh=True, triggers a sync with external providers if not on cooldown.
    """
    symbol = symbol.upper()
    
    # 1. Smart Timeframe Selection for DB fallback
    if not timeframe:
        if days <= 1:
            timeframe = "1m"
        elif days <= 7:
            timeframe = "1h"
        else:
            timeframe = "1d"
    
    # --- Rate Limiting Rails ---
    if refresh:
        # (refresh logic stays same...)
        global_bucket_key = "global_external_sync_bucket"
        global_count = await cache_client.get(global_bucket_key) or 0
        asset_cooldown_key = f"asset_sync_cooldown:{symbol}"
        is_on_cooldown = await cache_client.get(asset_cooldown_key)

        if int(global_count) < 4 and not is_on_cooldown:
            try:
                await sync_asset_history(db, symbol, days=max(days, 30), timeframe=timeframe)
            except Exception as e:
                logger.error(f"Failed to sync asset on refresh: {e}")
            else:
                try:
                    await cache_client.set(asset_cooldown_key, "locked", expire_seconds=30)
                    new_count = await cache_client.increment(global_bucket_key)
                    if int(global_count) == 0 or int(new_count) == 1:
                        await cache_client.expire(global_bucket_key, 60)
                except Exception as cache_err:
                    logger.warning(f"Refresh sync for {symbol} succeeded but cache bucket update failed: {cache_err}")

    # 2. Provide Real-time Intraday accuracy 
    live_intraday, interval_seconds = await get_live_intraday_history(db, symbol, days)
    if live_intraday and len(live_intraday) > 0:
        if return_meta:
            latest_ts = live_intraday[-1]["time"] if live_intraday else None
            as_of = datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat() if isinstance(latest_ts, int) else None
            return live_intraday, {
                "source": "live_intraday",
                "as_of": as_of,
                "staleness_seconds": 0,
                "is_stale": False,
                "interval_seconds": interval_seconds,
            }
        return live_intraday
        
    # 3. DB Fallback (with correct timeframe filtering)
    result = await db.execute(select(Asset).where(Asset.symbol == symbol))
    asset = result.scalars().first()
    
    timeframe_map = {"1m": 60, "5m": 300, "1h": 3600, "1d": 86400, "1w": 604800}
    db_interval = timeframe_map.get(timeframe, 86400)
    
    db_candles = []
    stale_db_candles = []
    if asset:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # FIX: Added filtering by timeframe to prevent duplicate points and messy charts
        candles_result = await db.execute(
            select(
                AssetCandle.timestamp,
                AssetCandle.open,
                AssetCandle.high,
                AssetCandle.low,
                AssetCandle.close,
                AssetCandle.volume,
            )
            .where(AssetCandle.asset_id == asset.id)
            .where(AssetCandle.timestamp >= start_date)
            .where(AssetCandle.timeframe == timeframe)
            .order_by(AssetCandle.timestamp.asc())
        )
        db_candles = candles_result.all()

        if not db_candles:
            stale_result = await db.execute(
                select(
                    AssetCandle.timestamp,
                    AssetCandle.open,
                    AssetCandle.high,
                    AssetCandle.low,
                    AssetCandle.close,
                    AssetCandle.volume,
                )
                .where(AssetCandle.asset_id == asset.id)
                .where(AssetCandle.timeframe == timeframe)
                .order_by(AssetCandle.timestamp.desc())
                .limit(min(max(days, 30), 365))
            )
            stale_db_candles = list(reversed(stale_result.all()))
    
    chart_data = []
    
    # Map cleanly to Lightweight Charts expected format: 
    # { time: 'YYYY-MM-DD', open, high, low, close, volume }
    selected_candles = db_candles if db_candles else stale_db_candles
    meta = {"source": "unknown", "as_of": None, "staleness_seconds": None, "is_stale": None}
    if selected_candles:
        for ts, open_, high_, low_, close_, volume_ in selected_candles:
            chart_data.append({
                "time": ts.strftime("%Y-%m-%d"),
                "open": open_,
                "high": high_,
                "low": low_,
                "close": close_,
                "value": volume_,
            })
        latest_ts = selected_candles[-1][0]
        staleness_seconds = max(0, int((datetime.now(timezone.utc) - latest_ts).total_seconds()))
        strict_threshold = 900 if days <= 2 else 86400
        meta = {
            "source": "db_recent" if db_candles else "db_last_known_good",
            "as_of": latest_ts.isoformat(),
            "staleness_seconds": staleness_seconds,
            "is_stale": staleness_seconds > strict_threshold,
            "interval_seconds": db_interval,
        }
    else:
        # Fallback to realistic generated dummy data.
        # CRITICAL: Walk BACKWARD from current_price so the final point matches exactly.
        import random
        rng = random.Random(symbol) # Stable chart for each symbol
        
        if current_price is None:
            # If no price provided, use a reasonable base
            base_prices = {"BTC": 65000, "ETH": 3500, "SOL": 145}
            current_price = base_prices.get(symbol, rng.uniform(50, 500))
        
        volatility = float(current_price) * 0.015
        end_time = datetime.now(timezone.utc)
        
        # We generate data points and then reverse them
        temp_data = []
        walk_price = float(current_price)
        
        for i in range(days):
            candle_date = end_time - timedelta(days=i)
            # Generate candle parameters
            change = rng.uniform(-1.0 * volatility, volatility)
            open_p = walk_price - change
            close_p = walk_price
            high_p = max(open_p, close_p) + rng.uniform(0, volatility * 0.5)
            low_p = min(open_p, close_p) - rng.uniform(0, volatility * 0.5)
            vol = rng.randint(5000, 100000)
            
            unix_ts = int(candle_date.timestamp())
            temp_data.append({
                "time": unix_ts if days <= 30 else candle_date.strftime("%Y-%m-%d"),
                "open": round(float(open_p), 2),
                "high": round(float(high_p), 2),
                "low": round(float(low_p), 2),
                "close": round(float(close_p), 2),
                "value": vol
            })
            walk_price = open_p # Walk backward
            
        # Reverse to get chronological order [oldest -> newest]
        chart_data = list(temp_data)
        chart_data.reverse()
        meta = {
            "source": "synthetic_fallback",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "staleness_seconds": None,
            "is_stale": True,
            "interval_seconds": 86400,
        }

    if return_meta:
        return chart_data, meta
    return chart_data
