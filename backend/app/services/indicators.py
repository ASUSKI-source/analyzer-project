"""
Technical Indicators Service — Computes signals and indicators using pandas and ta.
Future-proofed for automated trading and deep-dive analysis.

Multi-tier caching:
  - get_cached_indicators(symbol) → cached for 4 hours (14,400s)
  - compute_technical_indicators(candles) → raw, uncached computation
"""
import logging
import pandas as pd
import ta
from typing import List, Dict, Any, Optional
from app.schemas.market import TechnicalIndicators, HistoryDataPoint
from app.core.cache import cache_client

logger = logging.getLogger(__name__)

# Cache TTL for technical indicators (4 hours)
_INDICATOR_CACHE_TTL = 14_400


async def get_cached_indicators(
    symbol: str, 
    timeframe: str = "1d", 
    db: Optional[Any] = None
) -> Optional[Dict[str, Any]]:
    """
    Async entry point for the AI analyzer and other services.
    Fetches historical candles for a specific horizon (1h, 1d, 1w),
    computes technical indicators, and caches the result for 4 hours.
    
    Why: Multi-timeframe analysis allows the AI to distinguish between 
    tactical noise and strategic structural trends.
    """
    symbol = symbol.upper().strip()
    cache_key = f"indicators_cache:{symbol}:{timeframe}"

    # 1. Try cache
    cached = await cache_client.get(cache_key)
    if cached:
        return cached

    # 2. Map timeframe to lookback days
    lookback_map = {"5m": 2, "1h": 5, "1d": 365, "1w": 730, "1m": 1460}
    days = lookback_map.get(timeframe, 365)

    # 3. Data Gathering Strategy
    candles = []
    
    # NEW PERFORMANCE RAIL: Use local DB for Daily and Weekly (Strategic) horizons
    # This avoids hitting external API rate limits for larger watchlists.
    if timeframe in ["1d", "1w"] and db:
        try:
            from sqlalchemy import select, and_
            from datetime import datetime, timedelta
            from app.models.market import Asset, AssetCandle
            
            # Find asset ID
            q = select(Asset.id).where(Asset.symbol == symbol)
            res = await db.execute(q)
            asset_id = res.scalar_one_or_none()
            
            if asset_id:
                since = datetime.now() - timedelta(days=days)
                cq = select(
                    AssetCandle.timestamp,
                    AssetCandle.open,
                    AssetCandle.high,
                    AssetCandle.low,
                    AssetCandle.close,
                    AssetCandle.volume,
                ).where(
                    and_(
                        AssetCandle.asset_id == asset_id,
                        AssetCandle.timestamp >= since,
                    )
                ).order_by(AssetCandle.timestamp.asc())

                cres = await db.execute(cq)
                db_rows = cres.all()

                if len(db_rows) >= 40:  # Need enough for SMA 200 checks eventually
                    candles = []
                    for ts, open_, high_, low_, close_, volume_ in db_rows:
                        candles.append(
                            {
                                "time": ts.isoformat(),
                                "open": open_,
                                "high": high_,
                                "low": low_,
                                "close": close_,
                                "volume": volume_,
                            }
                        )
                    logger.info(f"Using DB-backed candles for {symbol} ({timeframe}) - {len(candles)} points")
                    
                    # 4. WEEKLY/MONTHLY RESAMPLING (Strategic Horizons)
                    if timeframe in ["1w", "1m"] and len(candles) > 0:
                        df = pd.DataFrame(candles)
                        df['time'] = pd.to_datetime(df['time'])
                        df.set_index('time', inplace=True)

                        resample_rule = "W-MON" if timeframe == "1w" else "MS"
                        resampled = df.resample(resample_rule).agg({
                            'open': 'first',
                            'high': 'max',
                            'low': 'min',
                            'close': 'last',
                            'volume': 'sum'
                        }).dropna()
                        
                        candles = resampled.reset_index().to_dict('records')
                        for c in candles:
                            c['time'] = c['time'].isoformat()
                        logger.info(f"Resampled to {len(candles)} {timeframe} candles for {symbol}")
        except Exception as db_err:
            logger.error(f"Fallback to live: DB indicator fetch failed for {symbol}: {db_err}")

    # Fallback to Live for 1h or if DB is empty/fails
    if not candles:
        try:
            from app.services.market_data import get_live_intraday_history
            res = await get_live_intraday_history(symbol, days=days)
            if isinstance(res, tuple) and len(res) == 2:
                candles, _ = res
            else:
                candles = res
        except Exception as e:
            logger.warning(f"Failed to fetch candles for cached indicators ({symbol}, {timeframe}): {e}")
            return None

    if not candles or len(candles) < 20:
        return None

    # 4. Compute using existing function
    ti = compute_technical_indicators(candles)

    # 5. Serialize to dict for caching and AI consumption
    result = {
        "symbol": symbol,
        "timeframe": timeframe,
        "rsi_14": ti.rsi,
        "macd_line": ti.macd,
        "macd_signal": ti.macd_signal,
        "macd_histogram": ti.macd_hist,
        "sma_50": ti.sma_50,
        "sma_200": ti.sma_200,
        "ema_9": ti.ema_9,
        "ema_21": ti.ema_21,
        "sma_20": ti.sma_20,
        "bollinger_upper": ti.bollinger_upper,
        "bollinger_lower": ti.bollinger_lower,
        "vwap": ti.vwap,
        "obv": ti.obv,
        "adx": ti.adx,
        "trend_signal": ti.trend_signal,
    }

    # Compute RSI label
    if ti.rsi is not None:
        if ti.rsi >= 70:
            result["rsi_signal"] = "OVERBOUGHT"
        elif ti.rsi <= 30:
            result["rsi_signal"] = "OVERSOLD"
        else:
            result["rsi_signal"] = "NEUTRAL"

    await cache_client.set(cache_key, result, expire_seconds=_INDICATOR_CACHE_TTL)
    logger.info(f"Cached {timeframe} indicators for {symbol} (4h TTL)")
    return result


async def get_batch_indicators(
    symbols: List[str],
    timeframes: List[str],
    db: Any
) -> Dict[str, Dict[str, Any]]:
    """
    Highly optimized batch fetching of indicators.
    1. Checks cache for all pairs.
    2. Performs a SINGLE DB query for all missing historical data.
    3. Computes indicators in parallel.
    
    Returns: Mapping of {symbol: {timeframe: indicator_dict}}
    """
    from sqlalchemy import select, and_
    from datetime import datetime, timedelta
    from app.models.market import Asset, AssetCandle

    results: Dict[str, Dict[str, Any]] = {sym: {} for sym in symbols}
    to_fetch = [] # List of (symbol, tf)

    # 1. Check cache first
    for sym in symbols:
        for tf in timeframes:
            cache_key = f"indicators_cache:{sym}:{tf}"
            cached = await cache_client.get(cache_key)
            if cached:
                results[sym][tf] = cached
            else:
                to_fetch.append((sym, tf))

    if not to_fetch:
        return results

    # 2. Batch DB Lookup for missing ones
    lookback_map = {"5m": 2, "1h": 5, "1d": 365, "1w": 730, "1m": 1460}
    max_days = max(lookback_map.get(tf, 365) for _, tf in to_fetch)
    since = datetime.now() - timedelta(days=max_days)
    fetch_symbols = list(set(s for s, _ in to_fetch))

    try:
        # Get asset IDs mapping
        aq = select(Asset.id, Asset.symbol).where(Asset.symbol.in_(fetch_symbols))
        ares = await db.execute(aq)
        asset_map = {row.symbol: row.id for row in ares.all()}
        id_to_sym = {v: k for k, v in asset_map.items()}

        if asset_map:
            # Batch fetch all relevant candles for these assets
            cq = select(AssetCandle).where(
                and_(
                    AssetCandle.asset_id.in_(asset_map.values()), 
                    AssetCandle.timestamp >= since
                )
            ).order_by(AssetCandle.timestamp.asc())
            
            cres = await db.execute(cq)
            all_candles = cres.scalars().all()

            # Group candles by (asset_id, timeframe)
            candles_by_bucket = {}
            for c in all_candles:
                bucket_key = (c.asset_id, c.timeframe)
                if bucket_key not in candles_by_bucket:
                    candles_by_bucket[bucket_key] = []
                candles_by_bucket[bucket_key].append({
                    "time": c.timestamp.isoformat(),
                    "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume
                })

            # Process missing indicators
            for sym, tf in to_fetch:
                aid = asset_map.get(sym)
                if not aid: continue
                
                asset_candles = candles_by_bucket.get((aid, tf), [])
                
                # Filter/Resample for specific timeframe
                tf_candles = asset_candles
                if tf in ["1w", "1m"]:
                    # Resample logic (copied/compacted from get_cached_indicators)
                    if len(tf_candles) > 0:
                        df = pd.DataFrame(tf_candles)
                        df['time'] = pd.to_datetime(df['time'])
                        df.set_index('time', inplace=True)
                        resample_rule = "W-MON" if tf == "1w" else "MS"
                        resampled = df.resample(resample_rule).agg({
                            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                        }).dropna()
                        tf_candles = resampled.reset_index().to_dict('records')
                        for c in tf_candles: c['time'] = c['time'].isoformat()
                elif tf == "1h":
                    # For 1h we actually want live data usually, but this is a DB batch fallback
                    # Optimization: 1h tactical is usually just 20-50 candles
                    pass 

                if len(tf_candles) >= 20:
                    ti_obj = compute_technical_indicators(tf_candles)
                    # Use existing serialization pattern
                    ti_dict = {
                        "symbol": sym, "timeframe": tf,
                        "rsi_14": ti_obj.rsi, "macd_line": ti_obj.macd, "macd_signal": ti_obj.macd_signal,
                        "macd_histogram": ti_obj.macd_hist, "sma_50": ti_obj.sma_50, "sma_200": ti_obj.sma_200,
                        "ema_9": ti_obj.ema_9, "ema_21": ti_obj.ema_21, "sma_20": ti_obj.sma_20,
                        "bollinger_upper": ti_obj.bollinger_upper, "bollinger_lower": ti_obj.bollinger_lower,
                        "vwap": ti_obj.vwap, "obv": ti_obj.obv, "adx": ti_obj.adx,
                        "trend_signal": ti_obj.trend_signal,
                    }
                    if ti_obj.rsi is not None:
                        ti_dict["rsi_signal"] = "OVERBOUGHT" if ti_obj.rsi >= 70 else ("OVERSOLD" if ti_obj.rsi <= 30 else "NEUTRAL")
                    
                    results[sym][tf] = ti_dict
                    # Cache it back
                    cache_key = f"indicators_cache:{sym}:{tf}"
                    await cache_client.set(cache_key, ti_dict, expire_seconds=_INDICATOR_CACHE_TTL)

    except Exception as e:
        logger.error(f"Batch indicator fetch failed: {e}")

    return results

def compute_technical_indicators(candles: List[dict]) -> TechnicalIndicators:
    """
    Takes a list of candles (dicts) and returns a TechnicalIndicators object.
    Requires at least 20 periods for most indicators, 200 for long-term SMA.
    """
    if not candles or len(candles) < 20:
        logger.warning("Insufficient data to compute technical indicators.")
        return TechnicalIndicators()

    # Convert to DataFrame - supports both dicts and pydantic models
    data = []
    for c in candles:
        if isinstance(c, dict):
            data.append(c)
        elif hasattr(c, "model_dump"):
            data.append(c.model_dump())
        else:
            data.append(c)
    
    df = pd.DataFrame(data)
    
    # Standardize column names for 'ta' library
    close = df['close']
    high = df['high']
    low = df['low']

    # 1. RSI (Relative Strength Index)
    rsi = ta.momentum.RSIIndicator(close=close, window=14).rsi()
    
    # 2. MACD (Moving Average Convergence Divergence)
    macd_indicator = ta.trend.MACD(close=close)
    macd = macd_indicator.macd()
    macd_signal = macd_indicator.macd_signal()
    macd_diff = macd_indicator.macd_diff()

    # 3. Simple Moving Averages (20, 50 and 200)
    sma_20 = ta.trend.SMAIndicator(close=close, window=20).sma_indicator()
    sma_50 = ta.trend.SMAIndicator(close=close, window=50).sma_indicator()
    sma_200 = ta.trend.SMAIndicator(close=close, window=200).sma_indicator()
    
    # 4. Exponential Moving Averages (9 and 21)
    ema_9 = ta.trend.EMAIndicator(close=close, window=9).ema_indicator()
    ema_21 = ta.trend.EMAIndicator(close=close, window=21).ema_indicator()

    # 4. Bollinger Bands
    bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband()
    bb_lower = bb.bollinger_lband()
    
    # 5. Volume Indicators
    # VWAP (Note: Typically used intraday, for daily it's a volume weighted price average)
    vwap_indicator = ta.volume.VolumeWeightedAveragePrice(high=high, low=low, close=close, volume=df['volume'])
    vwap = vwap_indicator.volume_weighted_average_price()
    
    obv = ta.volume.OnBalanceVolumeIndicator(close=close, volume=df['volume']).on_balance_volume()
    
    # 6. Trend Strength (ADX)
    adx_indicator = ta.trend.ADXIndicator(high=high, low=low, close=close)
    adx = adx_indicator.adx()

    # Trend Signal (Simple heuristic)
    last_close = close.iloc[-1]
    last_rsi = rsi.iloc[-1]
    
    signal = "Neutral"
    if last_rsi > 70:
        signal = "Overbought"
    elif last_rsi < 30:
        signal = "Oversold"
    elif last_close > sma_50.iloc[-1] and macd.iloc[-1] > macd_signal.iloc[-1]:
        signal = "Bullish"
    elif last_close < sma_50.iloc[-1] and macd.iloc[-1] < macd_signal.iloc[-1]:
        signal = "Bearish"

    return TechnicalIndicators(
        rsi=round(last_rsi, 2) if not pd.isna(last_rsi) else None,
        macd=round(macd.iloc[-1], 2) if not pd.isna(macd.iloc[-1]) else None,
        macd_signal=round(macd_signal.iloc[-1], 2) if not pd.isna(macd_signal.iloc[-1]) else None,
        macd_hist=round(macd_diff.iloc[-1], 2) if not pd.isna(macd_diff.iloc[-1]) else None,
        sma_20=round(sma_20.iloc[-1], 2) if not pd.isna(sma_20.iloc[-1]) else None,
        sma_50=round(sma_50.iloc[-1], 2) if not pd.isna(sma_50.iloc[-1]) else None,
        sma_200=round(sma_200.iloc[-1], 2) if not pd.isna(sma_200.iloc[-1]) else None,
        ema_9=round(ema_9.iloc[-1], 2) if not pd.isna(ema_9.iloc[-1]) else None,
        ema_21=round(ema_21.iloc[-1], 2) if not pd.isna(ema_21.iloc[-1]) else None,
        bollinger_upper=round(bb_upper.iloc[-1], 2) if not pd.isna(bb_upper.iloc[-1]) else None,
        bollinger_lower=round(bb_lower.iloc[-1], 2) if not pd.isna(bb_lower.iloc[-1]) else None,
        vwap=round(vwap.iloc[-1], 2) if not pd.isna(vwap.iloc[-1]) else None,
        obv=round(obv.iloc[-1], 2) if not pd.isna(obv.iloc[-1]) else None,
        adx=round(adx.iloc[-1], 2) if not pd.isna(adx.iloc[-1]) else None,
        trend_signal=signal
    )
