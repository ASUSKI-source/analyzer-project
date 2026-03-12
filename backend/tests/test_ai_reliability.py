import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from app.services.ai_analyzer import _decorate_last_good_report, _enforce_report_schema, _parse_ai_json_response
from app.services.ai_jobs import maybe_enqueue_login_prewarm
from app.core.cache import cache_client


def test_enforce_report_schema_repairs_missing_fields():
    raw = {"market_summary": "Only one field"}
    repaired = _enforce_report_schema(raw, symbols=["AAPL", "BTC"], strict=True)
    assert repaired["market_summary"] == "Only one field"
    assert repaired["watchlist_health"] == "MIXED"
    assert isinstance(repaired["assets"], list)
    assert len(repaired["assets"]) == 2
    assert repaired["assets"][0]["symbol"] == "AAPL"


def test_parse_ai_json_handles_markdown_fences():
    text = 'Summary: ```json {"market_summary":"ok","watchlist_health":"MIXED","risk_level":"MODERATE","tactical_outlook":"x","strategic_horizon":"y","assets":[],"overall_insight":"z"}```'
    parsed = _parse_ai_json_response(text=text, parse_budget_seconds=1.5, log_prefix="[test]")
    assert isinstance(parsed, dict)
    assert parsed["market_summary"] == "ok"


def test_decorate_last_good_marks_fallback():
    report = {"market_summary": "cached", "assets": []}
    out = _decorate_last_good_report(report, "route_timeout")
    assert out["from_cache"] is True
    assert out["source_status"] == "last_good_fallback"
    assert out["_served_last_good"] is True


@pytest.mark.asyncio
async def test_login_prewarm_respects_cooldown(monkeypatch):
    await cache_client.flush()

    async def fake_enqueue_analysis_job(user_id, symbols, refresh=True, reason="manual"):
        return {"status": "queued", "job_id": "job-123", "symbols": symbols, "reason": reason}

    monkeypatch.setattr("app.services.ai_jobs.enqueue_analysis_job", fake_enqueue_analysis_job)

    first = await maybe_enqueue_login_prewarm("user1", ["AAPL", "BTC"])
    second = await maybe_enqueue_login_prewarm("user1", ["AAPL", "BTC"])
    assert first is not None
    assert first["job_id"] == "job-123"
    assert second is None
