import asyncio
import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.cache import cache_client
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.ai_analyzer import generate_watchlist_report

logger = logging.getLogger(__name__)


def _job_key(job_id: str) -> str:
    return f"ai_job:{job_id}"


def _job_dedupe_key(user_id: str, symbols: List[str], reason: str) -> str:
    normalized = ",".join(sorted(set(symbols)))
    digest = hashlib.md5(normalized.encode()).hexdigest()[:12]
    return f"ai_job_dedupe:{user_id}:{reason}:{digest}"


def _prewarm_cooldown_key(user_id: str, symbols: List[str]) -> str:
    normalized = ",".join(sorted(set(symbols)))
    digest = hashlib.md5(normalized.encode()).hexdigest()[:12]
    return f"ai_prewarm_cooldown:{user_id}:{digest}"


async def enqueue_analysis_job(
    user_id: str,
    symbols: List[str],
    refresh: bool = True,
    reason: str = "manual",
) -> Dict[str, Any]:
    if not bool(getattr(settings, "AI_ASYNC_JOBS_ENABLED", True)):
        return {"status": "disabled", "error": "AI async jobs disabled"}
    now_iso = datetime.now(timezone.utc).isoformat()
    normalized = [s.upper().strip() for s in symbols if s and s.strip()]
    normalized = normalized[:20]
    if not normalized:
        return {"status": "rejected", "error": "No symbols provided"}

    dedupe_key = _job_dedupe_key(user_id, normalized, reason)
    existing_job_id = await cache_client.get(dedupe_key)
    if isinstance(existing_job_id, str):
        existing = await cache_client.get(_job_key(existing_job_id))
        if isinstance(existing, dict) and existing.get("status") in {"queued", "running"}:
            return {
                "status": "already_running",
                "job_id": existing_job_id,
                "symbols": normalized,
                "reason": reason,
            }

    job_id = str(uuid.uuid4())
    ttl_seconds = max(120, int(getattr(settings, "AI_JOB_TTL_SECONDS", 1200)))
    payload = {
        "job_id": job_id,
        "status": "queued",
        "user_id": user_id,
        "symbols": normalized,
        "refresh": bool(refresh),
        "reason": reason,
        "created_at": now_iso,
        "updated_at": now_iso,
        "queue_wait_ms": 0.0,
        "runtime_ms": 0.0,
    }
    await cache_client.set(_job_key(job_id), payload, expire_seconds=ttl_seconds)
    await cache_client.set(dedupe_key, job_id, expire_seconds=ttl_seconds)
    asyncio.create_task(_run_analysis_job(job_id=job_id))
    return {
        "status": "queued",
        "job_id": job_id,
        "symbols": normalized,
        "reason": reason,
    }


async def _run_analysis_job(job_id: str) -> None:
    key = _job_key(job_id)
    payload = await cache_client.get(key)
    if not isinstance(payload, dict):
        return

    started = time.monotonic()
    created_at = payload.get("created_at")
    queue_wait_ms = 0.0
    if isinstance(created_at, str):
        try:
            created_dt = datetime.fromisoformat(created_at)
            queue_wait_ms = max(0.0, (datetime.now(timezone.utc) - created_dt).total_seconds() * 1000)
        except Exception:
            queue_wait_ms = 0.0

    payload["status"] = "running"
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["queue_wait_ms"] = round(queue_wait_ms, 2)
    await cache_client.set(key, payload, expire_seconds=max(120, int(getattr(settings, "AI_JOB_TTL_SECONDS", 1200))))

    try:
        async with AsyncSessionLocal() as db:
            report = await generate_watchlist_report(
                symbols=payload.get("symbols", []),
                user_id=payload.get("user_id", ""),
                db=db,
                refresh=bool(payload.get("refresh", True)),
                request_id=job_id,
            )
        runtime_ms = (time.monotonic() - started) * 1000
        payload["status"] = "succeeded"
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload["runtime_ms"] = round(runtime_ms, 2)
        payload["result"] = report
        logger.info(
            "[ai_job][%s] status=succeeded queue_wait_ms=%.2f runtime_ms=%.2f symbols=%s",
            job_id,
            payload.get("queue_wait_ms", 0.0),
            payload["runtime_ms"],
            payload.get("symbols", []),
        )
    except Exception as e:
        runtime_ms = (time.monotonic() - started) * 1000
        payload["status"] = "failed"
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload["runtime_ms"] = round(runtime_ms, 2)
        payload["error"] = str(e)[:240]
        logger.warning(
            "[ai_job][%s] status=failed queue_wait_ms=%.2f runtime_ms=%.2f error=%s",
            job_id,
            payload.get("queue_wait_ms", 0.0),
            payload["runtime_ms"],
            payload["error"],
        )

    await cache_client.set(key, payload, expire_seconds=max(120, int(getattr(settings, "AI_JOB_TTL_SECONDS", 1200))))


async def get_analysis_job(job_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    payload = await cache_client.get(_job_key(job_id))
    if not isinstance(payload, dict):
        return None
    if payload.get("user_id") != user_id:
        return None
    return payload


async def maybe_enqueue_login_prewarm(user_id: str, symbols: List[str]) -> Optional[Dict[str, Any]]:
    if not bool(getattr(settings, "AI_LOGIN_PREWARM_ENABLED", True)):
        return None
    normalized = [s.upper().strip() for s in symbols if s and s.strip()]
    if not normalized:
        return None

    cooldown_key = _prewarm_cooldown_key(user_id, normalized)
    ttl = await cache_client.get_ttl(cooldown_key)
    if ttl > 0:
        return None

    cooldown_seconds = max(60, int(getattr(settings, "AI_PREWARM_COOLDOWN_SECONDS", 900)))
    await cache_client.set(cooldown_key, {"active": True}, expire_seconds=cooldown_seconds)
    return await enqueue_analysis_job(
        user_id=user_id,
        symbols=normalized,
        refresh=False,
        reason="login_prewarm",
    )
