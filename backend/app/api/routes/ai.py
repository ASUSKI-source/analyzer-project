"""
AI Analysis Routes — Serves AI-powered watchlist reports.
"""
import asyncio
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.services.ai_analyzer import generate_watchlist_report, get_last_good_report
from app.services.ai_jobs import enqueue_analysis_job, get_analysis_job, maybe_enqueue_login_prewarm
from app.services.watchlist import get_watchlist_symbols

logger = logging.getLogger(__name__)

router = APIRouter()

# Railway's proxy kills connections after ~30s with no response.
# We MUST respond before that, or the proxy drops the connection
# and the browser interprets the missing headers as a CORS failure.
_ENDPOINT_TIMEOUT = 25.0  # seconds


class AnalysisJobCreateRequest(BaseModel):
    symbols: Optional[list[str]] = None
    refresh: bool = False
    reason: str = Field(default="manual", max_length=40)


class AnalysisPrewarmRequest(BaseModel):
    symbols: Optional[list[str]] = None


async def _resolve_symbols(
    current_user: User,
    db: AsyncSession,
    symbols: Optional[str] = None,
    symbol_list: Optional[list[str]] = None,
) -> list[str]:
    if symbol_list is not None:
        resolved = [s.strip().upper() for s in symbol_list if isinstance(s, str) and s.strip()]
    elif symbols:
        resolved = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        # Fetch the first watchlist for the user if none specified
        from app.services.watchlist import get_watchlist_headers
        headers = await get_watchlist_headers(db, current_user)
        if headers:
            symbol_data = await get_watchlist_symbols(db, headers[0]["id"], current_user)
            resolved = [item["symbol"] for item in (symbol_data or []) if isinstance(item, dict) and item.get("symbol")]
        else:
            resolved = []
    return resolved[:20]


@router.get("/watchlist-analysis")
async def get_watchlist_analysis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    symbols: Optional[str] = Query(None, description="Comma-separated symbols to analyze (overrides watchlist)"),
    refresh: bool = Query(False, description="Force a fresh analysis by bypassing the cache")
):
    """
    Generate an AI-powered analysis of the user's watchlist.
    
    - Authenticated users only (401 for guests).
    - Override: pass ?symbols=AAPL,BTC,SPY to analyze specific symbols.
    - Reports are cached for 8 hours (open/close scanning).
    """
    symbol_list = await _resolve_symbols(current_user=current_user, db=db, symbols=symbols)

    if not symbol_list:
        return {
            "error": "No symbols to analyze. Add items to your watchlist first.",
            "assets": []
        }

    user_id = str(current_user.id)

    request_id = str(uuid.uuid4())
    route_started = time.monotonic()
    log_prefix = f"[ai_report][user={user_id}][req={request_id}]"
    logger.info(f"{log_prefix} route accepted symbols={symbol_list} refresh={refresh}")

    # Global timeout: Railway's proxy will kill our connection at ~30s.
    # We enforce 25s so we ALWAYS return a response (even a partial one)
    # before the proxy drops us — preventing the phantom CORS error.
    try:
        report = await asyncio.wait_for(
            generate_watchlist_report(
                symbols=symbol_list,
                user_id=user_id,
                db=db,
                refresh=refresh,
                request_id=request_id,
            ),
            timeout=_ENDPOINT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(
            f"{log_prefix} timed out after {_ENDPOINT_TIMEOUT}s for symbols={symbol_list}"
        )
        last_good = await get_last_good_report(user_id=user_id, symbols=symbol_list)
        if isinstance(last_good, dict):
            last_good["from_cache"] = True
            last_good["source_status"] = "last_good_fallback"
            last_good["_served_last_good"] = True
            last_good["_fallback_reason"] = "route_timeout"
            last_good["_analysis_origin"] = {
                "is_mock": bool(last_good.get("_mock", False)),
                "path": "last_good_fallback",
                "reason": "route_timeout",
            }
            return last_good
        timeout_response = {
            "market_summary": "Analysis timed out. This often happens if the data provider (Finnhub) is under heavy load or rate-limiting. We are currently optimizing data assembly to be more resilient.",
            "watchlist_health": "MIXED",
            "risk_level": "MODERATE",
            "sector_exposure": f"Attempted analysis of {len(symbol_list)} assets.",
            "assets": [],
            "overall_insight": "The engine timed out gathering live data. Try again in a few moments — cached data from this attempt will make the next one significantly faster.",
            "_timeout": True,
            "_mock": False,
            "_analysis_origin": {
                "is_mock": False,
                "path": "route_timeout_no_last_good",
                "reason": "route_timeout",
            },
        }
        if getattr(settings, "AI_DEBUG_TIMING", False):
            timeout_response["_debug_timing"] = {
                "request_id": request_id,
                "route_seconds": round(time.monotonic() - route_started, 3),
                "endpoint_timeout_seconds": _ENDPOINT_TIMEOUT,
            }
        return timeout_response
    except Exception as e:
        logger.error(f"AI report generation crashed: {e}", exc_info=True)
        last_good = await get_last_good_report(user_id=user_id, symbols=symbol_list)
        if isinstance(last_good, dict):
            last_good["from_cache"] = True
            last_good["source_status"] = "last_good_fallback"
            last_good["_served_last_good"] = True
            last_good["_fallback_reason"] = "route_error"
            last_good["_analysis_origin"] = {
                "is_mock": bool(last_good.get("_mock", False)),
                "path": "last_good_fallback",
                "reason": "route_error",
            }
            return last_good
        return {
            "error": f"Analysis failed: {str(e)[:200]}",
            "assets": [],
            "_mock": False,
        }

    route_elapsed = time.monotonic() - route_started
    logger.info(f"{log_prefix} route completed in {route_elapsed:.2f}s")
    if getattr(settings, "AI_DEBUG_TIMING", False):
        report.setdefault("_debug_timing", {})
        report["_debug_timing"]["route_seconds"] = round(route_elapsed, 3)
        report["_debug_timing"]["request_id"] = request_id
        report["_debug_timing"]["reliability_summary"] = {
            "source_status": report.get("source_status", "unknown"),
            "is_mock": bool(report.get("_mock", False)),
            "served_last_good": bool(report.get("_served_last_good", False)),
            "fallback_reason": report.get("_fallback_reason"),
            "analysis_origin": report.get("_analysis_origin", {}),
            "asset_count": len(report.get("assets", [])) if isinstance(report.get("assets"), list) else 0,
        }
    return report


@router.post("/watchlist-analysis/jobs")
async def create_watchlist_analysis_job(
    payload: AnalysisJobCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    symbol_list = await _resolve_symbols(
        current_user=current_user,
        db=db,
        symbol_list=payload.symbols,
    )
    if not symbol_list:
        return {"error": "No symbols to analyze", "status": "rejected"}
    user_id = str(current_user.id)
    job = await enqueue_analysis_job(
        user_id=user_id,
        symbols=symbol_list,
        refresh=bool(payload.refresh),
        reason=payload.reason or "manual",
    )
    return job


@router.get("/watchlist-analysis/jobs/{job_id}")
async def get_watchlist_analysis_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    job = await get_analysis_job(job_id=job_id, user_id=str(current_user.id))
    if job is None:
        return {"status": "not_found", "job_id": job_id}
    return job


@router.post("/watchlist-analysis/prewarm")
async def prewarm_watchlist_analysis(
    payload: AnalysisPrewarmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    symbol_list = await _resolve_symbols(
        current_user=current_user,
        db=db,
        symbol_list=payload.symbols,
    )
    if not symbol_list:
        return {"status": "noop", "reason": "no_symbols"}
    job = await maybe_enqueue_login_prewarm(
        user_id=str(current_user.id),
        symbols=symbol_list,
    )
    if job is None:
        return {"status": "skipped", "reason": "feature_disabled_or_cooldown"}
    return {"status": "queued", "job_id": job.get("job_id")}
