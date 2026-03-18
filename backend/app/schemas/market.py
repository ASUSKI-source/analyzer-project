from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, Field

class MarketQuote(BaseModel):
    """
    Standardized real-time or simulated quote for any asset.
    """
    symbol: str
    price: float = Field(..., description="Current asset price")
    changePercent: float = Field(..., description="Percent change over 24 hours")
    as_of: Optional[str] = Field(default=None, description="ISO timestamp for quote freshness")
    is_stale: Optional[bool] = Field(default=None, description="Whether this quote is stale")
    source: Optional[str] = Field(default=None, description="Data source or fallback layer")

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
    generated_at: Optional[str] = None
    served_at: Optional[str] = None
    staleness_seconds: Optional[int] = None
    is_stale: Optional[bool] = None

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
    source: Optional[str] = None
    as_of: Optional[str] = None
    staleness_seconds: Optional[int] = None
    is_stale: Optional[bool] = None
    interval_seconds: Optional[int] = None

class TechnicalIndicators(BaseModel):
    """
    Computed technical metrics for automated trading logic or UI insight.
    """
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_9: Optional[float] = None
    ema_21: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_lower: Optional[float] = None
    vwap: Optional[float] = None
    obv: Optional[float] = None
    adx: Optional[float] = None
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
    short_interest: Optional[float] = None
    short_ratio: Optional[float] = None
    shares_float: Optional[float] = None
    free_float: Optional[float] = None
    description: Optional[str] = None


class InstitutionalOwnership(BaseModel):
    shares_held: Optional[float] = None
    institution_count: Optional[int] = None
    top_holder: Optional[str] = None

class CryptoOnChain(BaseModel):
    fear_and_greed_score: Optional[int] = None
    fear_and_greed_label: Optional[str] = None
    long_short_ratio: Optional[float] = None
    open_interest: Optional[float] = None
    funding_rate: Optional[float] = None

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
    institutional: Optional[InstitutionalOwnership] = None
    on_chain: Optional[CryptoOnChain] = None
    last_updated: str
