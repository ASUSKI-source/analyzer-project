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
from app.services.finnhub import fetch_fundamentals, fetch_news_sentiment, fetch_institutional_ownership
from app.services.crypto_onchain import get_crypto_onchain_context
from app.services.indicators import compute_technical_indicators, get_cached_indicators
from app.services.market_data import get_asset_history, sync_asset_history
from app.services.snapshot_read_service import get_snapshot_bundle_for_symbols
from app.tasks.snapshot_tasks import (
    backfill_snapshot_universe_task,
    sync_event_snapshots_task,
    sync_fundamental_snapshots_task,
    sync_technical_snapshots_task,
)

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
    symbol_list = list(symbol_list)[:20]
    prices = await fetch_watchlist_prices(symbol_list)
    return prices


@router.get("/assets/{symbol:path}/analysis", response_model=AssetAnalysisResponse)
async def get_asset_analysis(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """
    Deep-Dive: Fetches Price, Technicals, Fundamentals, and Sentiment in parallel.
    Technicals use the proven get_cached_indicators path (same as AI analyzer).
    """
    symbol = symbol.upper()

    price_results = await fetch_watchlist_prices([symbol])
    current_price = price_results[0].get("price") if price_results else None

    # Fetch remaining data concurrently
    fundamentals_task = fetch_fundamentals(symbol, current_price=current_price)
    sentiment_task = fetch_news_sentiment(symbol)
    inst_task = fetch_institutional_ownership(symbol)
    onchain_task = get_crypto_onchain_context(symbol)
    indicators_task = get_cached_indicators(db, symbol, "1d")

    fundamentals, sentiment, inst_data, onchain_data, ind_payload = await asyncio.gather(
        fundamentals_task, sentiment_task, inst_task, onchain_task, indicators_task
    )

    # Extract Quote
    quote_data = price_results[0] if price_results else {"symbol": symbol, "price": 0, "changePercent": 0}
    quote = MarketQuote(**quote_data)

    # Build TechnicalIndicators from the cached indicator payload
    if ind_payload:
        technicals = TechnicalIndicators(
            rsi=ind_payload.get("rsi_14"),
            macd=ind_payload.get("macd_line"),
            macd_signal=ind_payload.get("macd_signal"),
            macd_hist=ind_payload.get("macd_histogram"),
            sma_20=ind_payload.get("sma_20"),
            sma_50=ind_payload.get("sma_50"),
            sma_200=ind_payload.get("sma_200"),
            ema_9=ind_payload.get("ema_9"),
            ema_21=ind_payload.get("ema_21"),
            bollinger_upper=ind_payload.get("bollinger_upper"),
            bollinger_lower=ind_payload.get("bollinger_lower"),
            vwap=ind_payload.get("vwap"),
            obv=ind_payload.get("obv"),
            adx=ind_payload.get("adx"),
            trend_signal=ind_payload.get("trend_signal") or "Neutral",
        )
    else:
        technicals = TechnicalIndicators(trend_signal="Neutral")

    return AssetAnalysisResponse(
        symbol=symbol,
        quote=quote,
        technicals=technicals,
        fundamentals=FundamentalData(**fundamentals),
        sentiment=sentiment,
        institutional=inst_data if isinstance(inst_data, dict) and (inst_data.get("shares_held") or inst_data.get("institution_count")) else None,
        on_chain=onchain_data if isinstance(onchain_data, dict) and onchain_data else None,
        last_updated=datetime.utcnow().isoformat()
    )


@router.get("/assets/{symbol:path}/history", response_model=AssetHistoryResponse)
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
        "interval_seconds": meta.get("interval_seconds"),
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


@router.post("/snapshots/sync")
async def trigger_snapshot_sync(
    _admin_user: User = Depends(get_admin_user),
):
    """
    Trigger canonical snapshot synchronization tasks.
    """
    technical_job = sync_technical_snapshots_task.delay()
    fundamental_job = sync_fundamental_snapshots_task.delay()
    event_job = sync_event_snapshots_task.delay()
    return {
        "status": "queued",
        "jobs": {
            "technical": technical_job.id,
            "fundamental": fundamental_job.id,
            "events": event_job.id,
        },
    }


@router.post("/snapshots/backfill")
async def trigger_snapshot_backfill(
    _admin_user: User = Depends(get_admin_user),
):
    job = backfill_snapshot_universe_task.delay()
    return {"status": "queued", "job_id": job.id}
