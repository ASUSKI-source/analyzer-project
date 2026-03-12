import asyncio
from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_admin_user, get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.market import (
    AssetAnalysisResponse,
    AssetHistoryResponse,
    DashboardPulseResponse,
    FundamentalData,
    MarketQuote,
    NewsSentiment,
    TechnicalIndicators,
)
from app.services.aggregator import fetch_watchlist_prices, generate_dashboard_pulse
from app.services.finnhub import fetch_fundamentals, fetch_news_sentiment
from app.services.indicators import compute_technical_indicators
from app.services.market_data import get_asset_history, sync_asset_history

router = APIRouter()


@router.get("/dashboard-pulse", response_model=DashboardPulseResponse)
async def get_dashboard_pulse():
    """
    God-Tier endpoint for the frontend.
    Returns Market Overview, Watchlist Data, and AI Sentiment concurrently.
    Powered by an underlying Redis 10-second cache.
    """
    pulse_data = await generate_dashboard_pulse()
    return pulse_data


@router.get("/prices", response_model=List[MarketQuote])
async def get_prices(symbols: str = Query(..., description="Comma-separated symbols")):
    """
    Fetch live prices for any list of symbols.
    Used by the frontend to get prices for user-added watchlist symbols.
    """
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return []
    symbol_list = symbol_list[:20]
    prices = await fetch_watchlist_prices(symbol_list)
    return prices


@router.get("/assets/{symbol}/analysis", response_model=AssetAnalysisResponse)
async def get_asset_analysis(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """
    Ultimate Deep-Dive: Fetches Price, Technicals, Fundamentals, and Sentiment in parallel.
    Future-proofed for predictive modules and advanced UI widgets.
    """
    symbol = symbol.upper()
    
    # Fetch data concurrently to minimize latency
    prices_task = fetch_watchlist_prices([symbol])
    history_task = get_asset_history(db=db, symbol=symbol, days=250)
    fundamentals_task = fetch_fundamentals(symbol)
    sentiment_task = fetch_news_sentiment(symbol)

    price_results, history, fundamentals, sentiment = await asyncio.gather(
        prices_task, history_task, fundamentals_task, sentiment_task
    )

    # Extract Quote
    quote_data = price_results[0] if price_results else {"symbol": symbol, "price": 0, "changePercent": 0}
    quote = MarketQuote(**quote_data)

    # Re-fetch history if quote price is available to align chart
    # (The first task might have been mock, but we use the best available price here)
    history = await get_asset_history(db=db, symbol=symbol, days=250, current_price=quote.price)

    # Compute Technicals
    technicals = compute_technical_indicators(history)

    return AssetAnalysisResponse(
        symbol=symbol,
        quote=quote,
        technicals=technicals,
        fundamentals=FundamentalData(**fundamentals),
        sentiment=sentiment,
        last_updated=datetime.utcnow().isoformat()
    )


@router.get("/assets/{symbol}/history", response_model=AssetHistoryResponse)
async def get_history(
    symbol: str, 
    days: int = 365, 
    refresh: bool = Query(False, description="Force a fresh data sync from external providers"),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve formatted historical candlestick data from TimescaleDB.
    Auto-aligns with real-time price to ensure chart consistency.
    Supports 'refresh=true' to bypass cache and force a fresh sync with external provider.
    """
    symbol = symbol.upper()
    
    # 1. Handle Refresh Logic and fetch current price
    price_results = await fetch_watchlist_prices([symbol])
    current_price = price_results[0].get("price") if price_results else None

    chart_data, meta = await get_asset_history(
        db=db, 
        symbol=symbol, 
        days=days, 
        current_price=current_price,
        refresh=refresh,
        return_meta=True,
    )
    return {
        "status": "success",
        "symbol": symbol,
        "data": chart_data,
        "source": meta.get("source"),
        "as_of": meta.get("as_of"),
        "staleness_seconds": meta.get("staleness_seconds"),
        "is_stale": meta.get("is_stale"),
    }


@router.post("/assets/{symbol}/sync")
async def sync_asset(
    symbol: str,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    _admin_user: User = Depends(get_admin_user),
):
    """
    Manually trigger a data pull from external providers.
    Restricted to admin users.
    """
    symbol = symbol.upper()
    candles_count = await sync_asset_history(db=db, symbol=symbol, days=days)
    return {
        "status": "success",
        "symbol": symbol,
        "message": "Successfully fetched and upserted historical candle data.",
        "processed_records": candles_count,
    }


@router.get("/assets/{symbol}/sentiment", response_model=NewsSentiment)
async def get_asset_sentiment(symbol: str):
    """
    Fetch AI-powered news sentiment for any asset symbol.
    """
    symbol = symbol.upper()
    sentiment = await fetch_news_sentiment(symbol)
    return sentiment
