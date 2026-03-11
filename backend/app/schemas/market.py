from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field

class MarketQuote(BaseModel):
    """
    Standardized real-time or simulated quote for any asset.
    """
    symbol: str
    price: float = Field(..., description="Current asset price")
    changePercent: float = Field(..., description="Percent change over 24 hours")

    model_config = ConfigDict(from_attributes=True)

class NewsSentiment(BaseModel):
    """
    Aggregated AI sentiment derived from global news on a specific asset.
    """
    symbol: str
    sentiment_score: float = Field(..., description="Normalized AI sentiment score from -1.0 to 1.0")
    trending_topics: List[str] = Field(default_factory=list, description="Top keywords in breaking news")

    model_config = ConfigDict(from_attributes=True)

class DashboardPulseResponse(BaseModel):
    """
    God-tier payload containing synchronized streams of market and AI data.
    """
    market_overview: List[MarketQuote]
    sentiment: NewsSentiment

    model_config = ConfigDict(from_attributes=True)

from typing import Union

class HistoryDataPoint(BaseModel):
    """
    Cleanly formatted timeframe tick for TV Lightweight Charts.
    """
    time: Union[str, int]
    open: float
    high: float
    low: float
    close: float
    value: float  # Renamed volume for lightweight-charts compatibility

class AssetHistoryResponse(BaseModel):
    """
    Payload protecting against malformed historical arrays.
    """
    status: str
    symbol: str
    data: List[HistoryDataPoint]

class TechnicalIndicators(BaseModel):
    """
    Computed technical metrics for automated trading logic or UI insight.
    """
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_lower: Optional[float] = None
    trend_signal: str = "Neutral" # Bullish, Bearish, or Neutral

class FundamentalData(BaseModel):
    """
    Core financial health metrics for an asset.
    """
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    eps: Optional[float] = None
    high_52week: Optional[float] = None
    low_52week: Optional[float] = None
    beta: Optional[float] = None
    description: Optional[str] = None

class AssetAnalysisResponse(BaseModel):
    """
    The ultimate deep-dive payload for a single asset.
    Combines price, technicals, fundamentals, and sentiment.
    """
    symbol: str
    quote: MarketQuote
    technicals: TechnicalIndicators
    fundamentals: FundamentalData
    sentiment: NewsSentiment
    last_updated: str
