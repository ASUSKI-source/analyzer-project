import logging
from typing import Any, Dict, List

from app.services.snapshot_store import (
    get_asset_id_map,
    get_latest_coverage_for_asset,
    get_latest_fundamental_snapshot,
    get_latest_technical_snapshots,
    get_recent_event_snapshots,
)

logger = logging.getLogger(__name__)


def _capabilities_for_asset_type(asset_type: str) -> Dict[str, bool]:
    kind = (asset_type or "").lower()
    if kind == "crypto":
        return {"fundamentals": False, "earnings": False, "news": True}
    if kind == "etf":
        return {"fundamentals": True, "earnings": False, "news": True}
    return {"fundamentals": True, "earnings": True, "news": True}


def _extract_earnings_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [e for e in events if (e.get("event_type") or "").lower() == "earnings"]


def _extract_news_topics(events: List[Dict[str, Any]]) -> List[str]:
    topics: List[str] = []
    for e in events:
        headline = e.get("headline")
        if isinstance(headline, str) and headline.strip():
            topics.append(headline[:90])
    return topics[:6]


async def get_snapshot_bundle_for_symbols(
    db: Any,
    symbols: List[str],
) -> Dict[str, Dict[str, Any]]:
    """
    Unified snapshot read contract for AI and future features.
    Returns per-symbol snapshot bundle with capability and coverage metadata.
    """
    normalized = [s.upper().strip() for s in symbols if s and s.strip()]
    asset_map = await get_asset_id_map(db, normalized)
    out: Dict[str, Dict[str, Any]] = {}

    for sym in normalized:
        asset_entry = asset_map.get(sym)
        if not asset_entry:
            out[sym] = {
                "symbol": sym,
                "asset_type": "unknown",
                "capabilities": {"fundamentals": False, "earnings": False, "news": False},
                "technicals_by_timeframe": {},
                "fundamentals_snapshot": {},
                "events_and_news_snapshot": {"earnings": [], "news_topics": [], "events": []},
                "coverage": {},
            }
            continue

        aid = asset_entry["asset_id"]
        asset_type = asset_entry["asset_type"]
        capabilities = _capabilities_for_asset_type(asset_type)
        technicals = await get_latest_technical_snapshots(db, aid)
        fundamentals = await get_latest_fundamental_snapshot(db, aid)
        events = await get_recent_event_snapshots(db, aid)
        coverage = await get_latest_coverage_for_asset(db, aid)

        out[sym] = {
            "symbol": sym,
            "asset_type": asset_type,
            "capabilities": capabilities,
            "technicals_by_timeframe": technicals,
            "fundamentals_snapshot": fundamentals or {},
            "events_and_news_snapshot": {
                "earnings": _extract_earnings_events(events) if capabilities.get("earnings", False) else [],
                "news_topics": _extract_news_topics(events) if capabilities.get("news", False) else [],
                "events": events,
            },
            "coverage": coverage,
        }

    return out
