import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import (
    Asset,
    AssetCoverageSnapshot,
    AssetEventSnapshot,
    AssetFundamentalSnapshot,
    AssetTechnicalSnapshot,
)

logger = logging.getLogger(__name__)


async def get_asset_id_map(db: AsyncSession, symbols: List[str]) -> Dict[str, Any]:
    if not symbols:
        return {}
    res = await db.execute(select(Asset.symbol, Asset.id, Asset.asset_type).where(Asset.symbol.in_(symbols)))
    mapping: Dict[str, Any] = {}
    for sym, asset_id, asset_type in res.all():
        mapping[sym] = {"asset_id": asset_id, "asset_type": asset_type}
    return mapping


async def upsert_technical_snapshot(
    db: AsyncSession,
    asset_id: Any,
    timeframe: str,
    as_of: datetime,
    payload: Dict[str, Any],
    source: str = "derived",
) -> None:
    stmt = insert(AssetTechnicalSnapshot).values(
        asset_id=asset_id,
        timeframe=timeframe,
        as_of=as_of,
        rsi_14=payload.get("rsi_14"),
        macd_line=payload.get("macd_line"),
        macd_signal=payload.get("macd_signal"),
        macd_histogram=payload.get("macd_histogram"),
        ema_9=payload.get("ema_9"),
        ema_21=payload.get("ema_21"),
        sma_20=payload.get("sma_20"),
        sma_50=payload.get("sma_50"),
        sma_200=payload.get("sma_200"),
        trend_signal=payload.get("trend_signal"),
        data_quality=payload.get("data_quality", "ok"),
        source=source,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uix_asset_technical_snapshot",
        set_={
            "rsi_14": payload.get("rsi_14"),
            "macd_line": payload.get("macd_line"),
            "macd_signal": payload.get("macd_signal"),
            "macd_histogram": payload.get("macd_histogram"),
            "ema_9": payload.get("ema_9"),
            "ema_21": payload.get("ema_21"),
            "sma_20": payload.get("sma_20"),
            "sma_50": payload.get("sma_50"),
            "sma_200": payload.get("sma_200"),
            "trend_signal": payload.get("trend_signal"),
            "data_quality": payload.get("data_quality", "ok"),
            "source": source,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    await db.execute(stmt)


async def upsert_fundamental_snapshot(
    db: AsyncSession,
    asset_id: Any,
    as_of: datetime,
    payload: Dict[str, Any],
    source: str = "finnhub",
) -> None:
    stmt = insert(AssetFundamentalSnapshot).values(
        asset_id=asset_id,
        as_of=as_of,
        market_cap=payload.get("market_cap"),
        pe_ratio=payload.get("pe_ratio"),
        dividend_yield=payload.get("dividend_yield"),
        eps=payload.get("eps"),
        high_52week=payload.get("high_52week"),
        low_52week=payload.get("low_52week"),
        beta=payload.get("beta"),
        sector=payload.get("sector"),
        industry=payload.get("industry"),
        description=payload.get("description"),
        source=source,
        confidence=payload.get("confidence"),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uix_asset_fundamental_snapshot",
        set_={
            "market_cap": payload.get("market_cap"),
            "pe_ratio": payload.get("pe_ratio"),
            "dividend_yield": payload.get("dividend_yield"),
            "eps": payload.get("eps"),
            "high_52week": payload.get("high_52week"),
            "low_52week": payload.get("low_52week"),
            "beta": payload.get("beta"),
            "sector": payload.get("sector"),
            "industry": payload.get("industry"),
            "description": payload.get("description"),
            "source": source,
            "confidence": payload.get("confidence"),
            "updated_at": datetime.now(timezone.utc),
        },
    )
    await db.execute(stmt)


async def insert_event_snapshots(
    db: AsyncSession,
    asset_id: Any,
    events: List[Dict[str, Any]],
    source: str = "finnhub",
) -> None:
    if not events:
        return
    rows = []
    for event in events:
        rows.append(
            {
                "asset_id": asset_id,
                "event_time": event.get("event_time") or datetime.now(timezone.utc),
                "event_type": event.get("event_type", "news"),
                "headline": event.get("headline"),
                "sentiment_score": event.get("sentiment_score"),
                "relevance_score": event.get("relevance_score"),
                "payload": event.get("payload"),
                "source": source,
            }
        )
    stmt = insert(AssetEventSnapshot).values(rows)
    stmt = stmt.on_conflict_do_nothing(constraint="uix_asset_event_snapshot")
    await db.execute(stmt)


async def upsert_coverage_snapshot(
    db: AsyncSession,
    asset_id: Any,
    as_of: datetime,
    timeframe: str,
    asset_type: str,
    expected_field_count: int,
    available_field_count: int,
    freshness_seconds: Optional[int],
    anomaly_flags: Optional[Dict[str, Any]] = None,
    source: str = "snapshot_pipeline",
) -> None:
    coverage = 0.0
    if expected_field_count > 0:
        coverage = float(available_field_count) / float(expected_field_count)
    stmt = insert(AssetCoverageSnapshot).values(
        asset_id=asset_id,
        as_of=as_of,
        asset_type=asset_type,
        timeframe=timeframe,
        expected_field_count=expected_field_count,
        available_field_count=available_field_count,
        coverage_score=coverage,
        freshness_seconds=freshness_seconds,
        anomaly_flags=anomaly_flags or {},
        source=source,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uix_asset_coverage_snapshot",
        set_={
            "expected_field_count": expected_field_count,
            "available_field_count": available_field_count,
            "coverage_score": coverage,
            "freshness_seconds": freshness_seconds,
            "anomaly_flags": anomaly_flags or {},
            "source": source,
        },
    )
    await db.execute(stmt)


async def get_latest_technical_snapshots(
    db: AsyncSession,
    asset_id: Any,
) -> Dict[str, Dict[str, Any]]:
    rows = await db.execute(
        select(AssetTechnicalSnapshot)
        .where(AssetTechnicalSnapshot.asset_id == asset_id)
        .order_by(AssetTechnicalSnapshot.timeframe.asc(), desc(AssetTechnicalSnapshot.as_of))
    )
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows.scalars().all():
        if row.timeframe in out:
            continue
        out[row.timeframe] = {
            "as_of": row.as_of.isoformat() if row.as_of else None,
            "rsi_14": row.rsi_14,
            "macd_line": row.macd_line,
            "macd_signal": row.macd_signal,
            "macd_histogram": row.macd_histogram,
            "ema_9": row.ema_9,
            "ema_21": row.ema_21,
            "sma_20": row.sma_20,
            "sma_50": row.sma_50,
            "sma_200": row.sma_200,
            "trend_signal": row.trend_signal,
            "data_quality": row.data_quality,
            "source": row.source,
        }
    return out


async def get_latest_fundamental_snapshot(db: AsyncSession, asset_id: Any) -> Optional[Dict[str, Any]]:
    row = await db.execute(
        select(AssetFundamentalSnapshot)
        .where(AssetFundamentalSnapshot.asset_id == asset_id)
        .order_by(desc(AssetFundamentalSnapshot.as_of))
        .limit(1)
    )
    item = row.scalar_one_or_none()
    if not item:
        return None
    return {
        "as_of": item.as_of.isoformat() if item.as_of else None,
        "market_cap": item.market_cap,
        "pe_ratio": item.pe_ratio,
        "dividend_yield": item.dividend_yield,
        "eps": item.eps,
        "high_52week": item.high_52week,
        "low_52week": item.low_52week,
        "beta": item.beta,
        "sector": item.sector,
        "industry": item.industry,
        "description": item.description,
        "source": item.source,
        "confidence": item.confidence,
    }


async def get_recent_event_snapshots(
    db: AsyncSession,
    asset_id: Any,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    rows = await db.execute(
        select(AssetEventSnapshot)
        .where(AssetEventSnapshot.asset_id == asset_id)
        .order_by(desc(AssetEventSnapshot.event_time))
        .limit(limit)
    )
    items: List[Dict[str, Any]] = []
    for row in rows.scalars().all():
        items.append(
            {
                "event_time": row.event_time.isoformat() if row.event_time else None,
                "event_type": row.event_type,
                "headline": row.headline,
                "sentiment_score": row.sentiment_score,
                "relevance_score": row.relevance_score,
                "payload": row.payload or {},
                "source": row.source,
            }
        )
    return items


async def get_latest_coverage_for_asset(
    db: AsyncSession,
    asset_id: Any,
) -> Dict[str, Dict[str, Any]]:
    rows = await db.execute(
        select(AssetCoverageSnapshot)
        .where(AssetCoverageSnapshot.asset_id == asset_id)
        .order_by(AssetCoverageSnapshot.timeframe.asc(), desc(AssetCoverageSnapshot.as_of))
    )
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows.scalars().all():
        if row.timeframe in out:
            continue
        out[row.timeframe] = {
            "as_of": row.as_of.isoformat() if row.as_of else None,
            "coverage_score": row.coverage_score,
            "freshness_seconds": row.freshness_seconds,
            "expected_field_count": row.expected_field_count,
            "available_field_count": row.available_field_count,
            "anomaly_flags": row.anomaly_flags or {},
            "source": row.source,
        }
    return out
