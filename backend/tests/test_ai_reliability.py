import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from app.services.ai_analyzer import (
    _assess_report_quality,
    _decorate_last_good_report,
    _enforce_report_schema,
    _parse_ai_json_response,
    _parse_ai_json_response_with_mode,
)
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


def test_parse_ai_json_reports_parse_mode():
    text = '{"market_summary":"ok","watchlist_health":"MIXED","risk_level":"MODERATE","tactical_outlook":"x","strategic_horizon":"y","assets":[],"overall_insight":"z"}'
    parsed, mode = _parse_ai_json_response_with_mode(text=text, parse_budget_seconds=1.5, log_prefix="[test]")
    assert isinstance(parsed, dict)
    assert mode == "direct"


def test_decorate_last_good_marks_fallback():
    report = {"market_summary": "cached", "assets": []}
    out = _decorate_last_good_report(report, "route_timeout")
    assert out["from_cache"] is True
    assert out["source_status"] == "last_good_fallback"
    assert out["_served_last_good"] is True
    assert out["_analysis_origin"]["path"] == "last_good_fallback"
    assert out["_analysis_origin"]["reason"] == "route_timeout"


def test_assess_report_quality_flags_low_confidence_claim():
    report = {
        "assets": [
            {"symbol": "MSFT", "verdict": "NEUTRAL"},
            {"symbol": "NVDA", "verdict": "NEUTRAL"},
        ],
        "overall_insight": "Without robust technical indicators, conviction remains limited.",
    }
    data_context = {
        "assets": [
            {"symbol": "MSFT", "technicals": {"1d": {"rsi_14": 52.0, "trend_signal": "Bullish"}}},
            {"symbol": "NVDA", "technicals": {"1h": {"ema_9": 100.0, "ema_21": 99.0}}},
        ]
    }
    quality = _assess_report_quality(report, data_context)
    assert quality["reject_as_low_confidence"] is True
    assert quality["reason"] == "all_neutral_with_missing_data_claim"


def test_assess_report_quality_accepts_non_uniform_verdicts():
    report = {
        "assets": [
            {"symbol": "MSFT", "verdict": "BULLISH"},
            {"symbol": "NVDA", "verdict": "NEUTRAL"},
        ],
        "overall_insight": "Signals are mixed across timeframes.",
    }
    data_context = {
        "assets": [
            {"symbol": "MSFT", "technicals": {"1d": {"rsi_14": 52.0, "trend_signal": "Bullish"}}},
            {"symbol": "NVDA", "technicals": {"1h": {"ema_9": 100.0, "ema_21": 99.0}}},
        ]
    }
    quality = _assess_report_quality(report, data_context)
    assert quality["reject_as_low_confidence"] is False


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
