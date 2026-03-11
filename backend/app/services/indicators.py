"""
Technical Indicators Service — Computes signals and indicators using pandas and ta.
Future-proofed for automated trading and deep-dive analysis.
"""
import logging
import pandas as pd
import ta
from typing import List, Optional
from app.schemas.market import TechnicalIndicators, HistoryDataPoint

logger = logging.getLogger(__name__)

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
        bollinger_upper=round(bb_upper.iloc[-1], 2) if not pd.isna(bb_upper.iloc[-1]) else None,
        bollinger_lower=round(bb_lower.iloc[-1], 2) if not pd.isna(bb_lower.iloc[-1]) else None,
        trend_signal=signal
    )
