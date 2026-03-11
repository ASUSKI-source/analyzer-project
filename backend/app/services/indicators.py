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


async def get_cached_indicators(symbol: str, timeframe: str = "1d") -> Optional[Dict[str, Any]]:
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
    # 1h: 5 days of data (plenty for intraday RSI/MACD)
    # 1d: 365 days (standard Daily view)
    # 1w: 730 days (Strategic Weekly view)
    lookback_map = {"1h": 5, "1d": 365, "1w": 730}
    days = lookback_map.get(timeframe, 365)

    # 3. Fetch candles
    try:
        from app.services.market_data import get_live_intraday_history
        candles = await get_live_intraday_history(symbol, days=days)
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
        "bollinger_upper": ti.bollinger_upper,
        "bollinger_lower": ti.bollinger_lower,
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
        if hasattr(c, "model_dump"):
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

    # 3. Simple Moving Averages (50 and 200)
    sma_50 = ta.trend.SMAIndicator(close=close, window=50).sma_indicator()
    sma_200 = ta.trend.SMAIndicator(close=close, window=200).sma_indicator()
    
    # 4. Exponential Moving Averages (9 and 21)
    ema_9 = ta.trend.EMAIndicator(close=close, window=9).ema_indicator()
    ema_21 = ta.trend.EMAIndicator(close=close, window=21).ema_indicator()

    # 4. Bollinger Bands
    bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband()
    bb_lower = bb.bollinger_lband()

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
        sma_50=round(sma_50.iloc[-1], 2) if not pd.isna(sma_50.iloc[-1]) else None,
        sma_200=round(sma_200.iloc[-1], 2) if not pd.isna(sma_200.iloc[-1]) else None,
        ema_9=round(ema_9.iloc[-1], 2) if not pd.isna(ema_9.iloc[-1]) else None,
        ema_21=round(ema_21.iloc[-1], 2) if not pd.isna(ema_21.iloc[-1]) else None,
        bollinger_upper=round(bb_upper.iloc[-1], 2) if not pd.isna(bb_upper.iloc[-1]) else None,
        bollinger_lower=round(bb_lower.iloc[-1], 2) if not pd.isna(bb_lower.iloc[-1]) else None,
        trend_signal=signal
    )
