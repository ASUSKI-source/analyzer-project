import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from celery import Task
from sqlalchemy import select

from app.core.cache import cache_client
from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.market import Asset
from app.services.finnhub import (
    fetch_fundamentals,
    fetch_news_sentiment,
    get_batch_earnings_events,
)
from app.services.indicators import get_cached_indicators
from app.services.snapshot_store import (
    get_asset_id_map,
    insert_event_snapshots,
    upsert_coverage_snapshot,
    upsert_fundamental_snapshot,
    upsert_technical_snapshot,
)

logger = logging.getLogger(__name__)


class RobustTask(Task):
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True
    max_retries = 5


async def _fetch_active_symbols() -> List[str]:
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Asset.symbol))
        rows = res.all()
        return [row[0] for row in rows if row and row[0]]


async def _acquire_lock(key: str, ttl_seconds: int = 1200) -> bool:
    existing = await cache_client.get(key)
    if existing:
        return False
    await cache_client.set(key, {"started_at": datetime.now(timezone.utc).isoformat()}, expire_seconds=ttl_seconds)
    return True


async def _release_lock(key: str) -> None:
    await cache_client.set(key, None, expire_seconds=1)


async def _run_technical_snapshot_job() -> Dict[str, Any]:
    lock_key = "snapshot_job_lock:technical"
    if not await _acquire_lock(lock_key):
        return {"status": "skipped", "reason": "lock_active"}
    started = datetime.now(timezone.utc)
    processed = 0
    try:
        symbols = await _fetch_active_symbols()
        async with AsyncSessionLocal() as db:
            asset_map = await get_asset_id_map(db, symbols)
            for sym in symbols:
                asset_entry = asset_map.get(sym)
                if not asset_entry:
                    continue
                aid = asset_entry["asset_id"]
                asset_type = asset_entry["asset_type"]
                for tf in ["1h", "1d", "1w", "1m"]:
                    indicator = await get_cached_indicators(sym, timeframe=tf, db=db)
                    if not indicator:
                        continue
                    as_of = datetime.now(timezone.utc)
                    payload = {
                        "rsi_14": indicator.get("rsi_14"),
                        "macd_line": indicator.get("macd_line"),
                        "macd_signal": indicator.get("macd_signal"),
                        "macd_histogram": indicator.get("macd_histogram"),
                        "ema_9": indicator.get("ema_9"),
                        "ema_21": indicator.get("ema_21"),
                        "sma_20": indicator.get("sma_20"),
                        "sma_50": indicator.get("sma_50"),
                        "sma_200": indicator.get("sma_200"),
                        "trend_signal": indicator.get("trend_signal"),
                        "data_quality": "ok",
                    }
                    await upsert_technical_snapshot(db, aid, tf, as_of, payload, source="indicator_service")
                    expected = 9
                    available = len([v for v in [payload.get("rsi_14"), payload.get("macd_line"), payload.get("macd_signal"), payload.get("macd_histogram"), payload.get("ema_9"), payload.get("ema_21"), payload.get("sma_20"), payload.get("sma_50"), payload.get("sma_200")] if v is not None])
                    await upsert_coverage_snapshot(
                        db=db,
                        asset_id=aid,
                        as_of=as_of,
                        timeframe=tf,
                        asset_type=asset_type,
                        expected_field_count=expected,
                        available_field_count=available,
                        freshness_seconds=0,
                        anomaly_flags={},
                    )
                    processed += 1
            await db.commit()
        return {
            "status": "success",
            "processed_snapshots": processed,
            "duration_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
        }
    finally:
        await _release_lock(lock_key)


async def _run_fundamental_snapshot_job() -> Dict[str, Any]:
    lock_key = "snapshot_job_lock:fundamental"
    if not await _acquire_lock(lock_key):
        return {"status": "skipped", "reason": "lock_active"}
    started = datetime.now(timezone.utc)
    processed = 0
    try:
        symbols = await _fetch_active_symbols()
        async with AsyncSessionLocal() as db:
            asset_map = await get_asset_id_map(db, symbols)
            for sym in symbols:
                asset_entry = asset_map.get(sym)
                if not asset_entry:
                    continue
                aid = asset_entry["asset_id"]
                asset_type = asset_entry["asset_type"]
                fundamentals = await fetch_fundamentals(sym)
                as_of = datetime.now(timezone.utc)
                await upsert_fundamental_snapshot(db, aid, as_of, fundamentals, source="finnhub")
                expected = 7 if asset_type.lower() != "crypto" else 0
                available = len([v for k, v in fundamentals.items() if k in {"market_cap", "pe_ratio", "dividend_yield", "eps", "high_52week", "low_52week", "beta"} and v is not None])
                anomaly_flags = {}
                hi = fundamentals.get("high_52week")
                lo = fundamentals.get("low_52week")
                pe = fundamentals.get("pe_ratio")
                if hi is not None and lo is not None and lo > hi:
                    anomaly_flags["range_inverted"] = True
                if pe is not None and float(pe) < 0:
                    anomaly_flags["negative_pe"] = True
                await upsert_coverage_snapshot(
                    db=db,
                    asset_id=aid,
                    as_of=as_of,
                    timeframe="fundamentals",
                    asset_type=asset_type,
                    expected_field_count=expected,
                    available_field_count=available,
                    freshness_seconds=0,
                    anomaly_flags=anomaly_flags,
                )
                processed += 1
            await db.commit()
        return {
            "status": "success",
            "processed_snapshots": processed,
            "duration_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
        }
    finally:
        await _release_lock(lock_key)


async def _run_event_snapshot_job() -> Dict[str, Any]:
    lock_key = "snapshot_job_lock:event"
    if not await _acquire_lock(lock_key):
        return {"status": "skipped", "reason": "lock_active"}
    started = datetime.now(timezone.utc)
    processed = 0
    try:
        symbols = await _fetch_active_symbols()
        earnings_batches = await get_batch_earnings_events(symbols)
        async with AsyncSessionLocal() as db:
            asset_map = await get_asset_id_map(db, symbols)
            for idx, sym in enumerate(symbols):
                asset_entry = asset_map.get(sym)
                if not asset_entry:
                    continue
                aid = asset_entry["asset_id"]
                asset_type = asset_entry["asset_type"]

                sentiment = await fetch_news_sentiment(sym)
                news_topics = sentiment.get("trending_topics", []) if isinstance(sentiment, dict) else []
                news_events = [
                    {
                        "event_time": datetime.now(timezone.utc),
                        "event_type": "news",
                        "headline": t if isinstance(t, str) else None,
                        "sentiment_score": sentiment.get("sentiment_score") if isinstance(sentiment, dict) else None,
                        "relevance_score": 0.6,
                        "payload": {"symbol": sym},
                    }
                    for t in news_topics[:5]
                ]
                earnings = earnings_batches[idx] if idx < len(earnings_batches) else []
                await insert_event_snapshots(db, aid, earnings + news_events, source="finnhub")
                await upsert_coverage_snapshot(
                    db=db,
                    asset_id=aid,
                    as_of=datetime.now(timezone.utc),
                    timeframe="events",
                    asset_type=asset_type,
                    expected_field_count=1,
                    available_field_count=1 if (earnings or news_events) else 0,
                    freshness_seconds=0,
                    anomaly_flags={},
                )
                processed += 1
            await db.commit()
        return {
            "status": "success",
            "processed_snapshots": processed,
            "duration_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
        }
    finally:
        await _release_lock(lock_key)


@celery_app.task(name="app.tasks.snapshot_tasks.sync_technical_snapshots_task", bind=True, base=RobustTask)
def sync_technical_snapshots_task(self):
    return asyncio.run(_run_technical_snapshot_job())


@celery_app.task(name="app.tasks.snapshot_tasks.sync_fundamental_snapshots_task", bind=True, base=RobustTask)
def sync_fundamental_snapshots_task(self):
    return asyncio.run(_run_fundamental_snapshot_job())


@celery_app.task(name="app.tasks.snapshot_tasks.sync_event_snapshots_task", bind=True, base=RobustTask)
def sync_event_snapshots_task(self):
    return asyncio.run(_run_event_snapshot_job())


@celery_app.task(name="app.tasks.snapshot_tasks.backfill_snapshot_universe_task", bind=True, base=RobustTask)
def backfill_snapshot_universe_task(self):
    """
    Full backfill orchestration task for enterprise rollout.
    """
    tech = asyncio.run(_run_technical_snapshot_job())
    fund = asyncio.run(_run_fundamental_snapshot_job())
    events = asyncio.run(_run_event_snapshot_job())
    return {"status": "success", "technical": tech, "fundamental": fund, "events": events}
