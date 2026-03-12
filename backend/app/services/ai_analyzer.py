"""
AI Watchlist Analyzer — Multi-tier data assembly + Anthropic Master Prompt.

Cache strategy:
  - Live Prices:    10s  (via DataBroker / dashboard pulse)
  - Technicals:     4h   (via indicators.py)
  - Fundamentals:  12h   (via finnhub.fetch_fundamentals)
  - Full AI Report: 8h   (final assembled output)
"""

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import httpx

from app.core.cache import cache_client
from app.core.config import settings
from app.utils.http import get_llm_http_client

logger = logging.getLogger(__name__)

# ─── Cache TTLs ──────────────────────────────────────────────────────────────
_REPORT_CACHE_TTL = 28_800       # 8 hours  — full AI report
_FUNDAMENTALS_CACHE_TTL = 43_200 # 12 hours — Finnhub fundamentals

# ─── Anthropic Config ────────────────────────────────────────────────────────
_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4-5"  # Correct model ID provided by user
_REPORT_REQUIRED_KEYS = {
    "market_summary",
    "watchlist_health",
    "risk_level",
    "tactical_outlook",
    "strategic_horizon",
    "assets",
    "overall_insight",
}


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

async def generate_watchlist_report(
    symbols: List[str],
    user_id: str,
    db: Any,
    refresh: bool = False,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Assemble a comprehensive AI analysis report for the given watchlist symbols.
    """
    symbols = [s.upper().strip() for s in symbols if s.strip()]
    if not symbols:
        return {"error": "No symbols provided", "assets": []}

    # ── 1. Check Report Cache (Skip if refresh=True) ─────────────────────────
    pipeline_start = time.monotonic()
    cache_gate_seconds = 0.0
    cache_key = _report_cache_key(user_id, symbols)
    last_good_key = _last_good_report_key(user_id, symbols)
    attempt_meta_key = _last_attempt_meta_key(user_id, symbols)
    last_good_cached = await cache_client.get(last_good_key)
    if not refresh:
        cache_gate_start = time.monotonic()
        # ── 2. Security: Global 5-minute AI Generation Cooldown ─────────────────
        cooldown_key = f"ai_generation_cooldown:{user_id}"
        cooldown_ttl = await cache_client.get_ttl(cooldown_key)
        if cooldown_ttl > 0:
            logger.warning(f"AI generation cooldown active for user {user_id} ({cooldown_ttl}s remaining)")
            return {
                "error": "Engine cooling down. You can generate a new analysis once every 5 minutes.",
                "cooldown_remaining": cooldown_ttl,
                "assets": [],
                "_mock": False,
            }
        
        cached = await cache_client.get(cache_key)
        if cached:
            # Smart Cache: Upgrade Mock -> Real if API key is now valid
            api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
            has_valid_key = api_key and "testkey" not in api_key
            
            if cached.get("_mock") and has_valid_key:
                logger.info(f"Cached mock found, but valid API key is present. Upgrading to real report for user {user_id}")
            else:
                logger.info(f"AI report cache HIT for user {user_id}")
                cached["from_cache"] = True
                cached["source_status"] = "cache_hit"
                return cached
        cache_gate_seconds = time.monotonic() - cache_gate_start

    # ── 2. Security: Global 5-minute AI Generation Cooldown ─────────────────
    # This block is now only reached if refresh=True or cache missed.
    # The cooldown check for non-refresh requests is handled above.
    cooldown_key = f"ai_generation_cooldown:{user_id}"
    cooldown_ttl = await cache_client.get_ttl(cooldown_key)
    if cooldown_ttl > 0:
        logger.warning(f"AI generation cooldown active for user {user_id} ({cooldown_ttl}s remaining)")
        return {
            "error": "Engine cooling down. You can generate a new analysis once every 5 minutes.",
            "cooldown_remaining": cooldown_ttl,
            "assets": [],
            "_mock": False,
        }
        
    log_prefix = f"[ai_report][user={user_id}][req={request_id or '-'}]"
    logger.info(
        f"{log_prefix} cache {'BYPASS (force)' if refresh else 'MISS'}. "
        f"Generating report for symbols={symbols}."
    )

    total_budget = max(1.0, float(getattr(settings, "AI_TOTAL_BUDGET_SECONDS", 24.0)))
    assembly_budget = max(1.0, float(getattr(settings, "AI_ASSEMBLY_BUDGET_SECONDS", 10.0)))
    model_budget = max(1.0, float(getattr(settings, "AI_MODEL_BUDGET_SECONDS", 12.0)))
    parse_budget = max(0.2, float(getattr(settings, "AI_PARSE_BUDGET_SECONDS", 1.5)))
    deadline = pipeline_start + total_budget

    # ── 2. Multi-Tier Data Assembly ──────────────────────────────────────────
    remaining_before_assembly = _seconds_remaining(deadline)
    if remaining_before_assembly <= 0:
        raise asyncio.TimeoutError("No budget left before assembly stage")
    effective_assembly_budget = min(assembly_budget, remaining_before_assembly)

    try:
        start_assembly = time.monotonic()
        data_context, assembly_metrics = await _assemble_data_context(
            symbols,
            db,
            budget_seconds=effective_assembly_budget,
            log_prefix=log_prefix,
        )
        assembly_duration = time.monotonic() - start_assembly
        logger.info(
            f"{log_prefix} data assembly completed in {assembly_duration:.2f}s "
            f"for symbols={symbols}."
        )

        # ── 3. Call Anthropic ────────────────────────────────────────────────
        # PRUNE CONTEXT: Ensure we don't send a massive payload that causes timeouts
        pruned_context = _prune_context(data_context)

        remaining_before_model = _seconds_remaining(deadline)
        if remaining_before_model <= 0:
            raise asyncio.TimeoutError("No budget left before model stage")
        effective_model_budget = min(model_budget, remaining_before_model)

        start_ai = time.monotonic()
        raw_report = await _call_anthropic(
            symbols,
            pruned_context,
            timeout_seconds=effective_model_budget,
            parse_budget_seconds=parse_budget,
            log_prefix=log_prefix,
        )
        model_meta = raw_report.pop("_model_meta", {}) if isinstance(raw_report, dict) else {}
        report = raw_report
        ai_duration = time.monotonic() - start_ai
        total_duration = time.monotonic() - pipeline_start

        logger.info(
            f"{log_prefix} Anthropic call completed in {ai_duration:.2f}s; "
            f"end-to-end report generation took {total_duration:.2f}s."
        )
    except asyncio.TimeoutError as timeout_error:
        await cache_client.set(
            attempt_meta_key,
            {
                "status": "timeout",
                "request_id": request_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "detail": str(timeout_error),
            },
            expire_seconds=max(60, int(getattr(settings, "AI_LAST_ATTEMPT_TTL_SECONDS", 21_600))),
        )
        if isinstance(last_good_cached, dict):
            logger.warning("%s serving last-good report due to timeout", log_prefix)
            return _decorate_last_good_report(last_good_cached, "fresh_analysis_timed_out")
        raise
    except Exception as e:
        await cache_client.set(
            attempt_meta_key,
            {
                "status": "error",
                "request_id": request_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "detail": _sanitize_error_message(str(e)),
            },
            expire_seconds=max(60, int(getattr(settings, "AI_LAST_ATTEMPT_TTL_SECONDS", 21_600))),
        )
        if isinstance(last_good_cached, dict):
            logger.warning("%s serving last-good report due to pipeline error", log_prefix)
            return _decorate_last_good_report(last_good_cached, "fresh_analysis_error")
        raise

    # ── 4. Cache & Return ────────────────────────────────────────────────────
    report = _enforce_report_schema(
        report=report,
        symbols=symbols,
        strict=bool(getattr(settings, "AI_STRICT_JSON_ENFORCEMENT", True)),
    )
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["symbols_analyzed"] = symbols
    report["from_cache"] = False
    report["source_status"] = "fresh"
    report["_analysis_origin"] = {
        "is_mock": bool(report.get("_mock", False)),
        "path": "fresh_generation",
    }

    quality = _assess_report_quality(report, data_context)
    report["_quality_gate"] = quality

    if getattr(settings, "AI_DEBUG_TIMING", False):
        report["_debug_timing"] = {
            "request_id": request_id,
            "cache_gate_seconds": round(cache_gate_seconds, 3),
            "assembly_seconds": round(assembly_duration, 3),
            "assembly_metrics": assembly_metrics,
            "news_sentiment_included": bool(assembly_metrics.get("news_included", False)),
            "ai_seconds": round(ai_duration, 3),
            "total_seconds": round(total_duration, 3),
            "symbol_count": len(symbols),
            "model_meta": model_meta if isinstance(model_meta, dict) else {},
            "budgets": {
                "total": total_budget,
                "assembly": assembly_budget,
                "model": model_budget,
                "parse": parse_budget,
            },
        }

    await cache_client.set(
        attempt_meta_key,
        {
            "status": "success",
            "request_id": request_id,
            "generated_at": report["generated_at"],
        },
        expire_seconds=max(60, int(getattr(settings, "AI_LAST_ATTEMPT_TTL_SECONDS", 21_600))),
    )

    if not bool(report.get("_mock")):
        if quality.get("reject_as_low_confidence") and isinstance(last_good_cached, dict):
            logger.warning(
                "%s replacing low-confidence fresh report with last-good fallback (%s)",
                log_prefix,
                quality.get("reason", "unspecified"),
            )
            return _decorate_last_good_report(last_good_cached, "fresh_low_confidence")

        if quality.get("reject_as_low_confidence"):
            report["source_status"] = "fresh_low_confidence"
            report["_low_confidence"] = True

        await cache_client.set(cache_key, report, expire_seconds=_REPORT_CACHE_TTL)
        await cache_client.set(
            last_good_key,
            report,
            expire_seconds=max(300, int(getattr(settings, "AI_LAST_GOOD_TTL_SECONDS", 86_400))),
        )
        logger.info(f"{log_prefix} AI report cached (8h TTL) for cache_key={cache_key}")
    elif isinstance(last_good_cached, dict):
        logger.warning("%s serving last-good report due to mock fallback", log_prefix)
        return _decorate_last_good_report(last_good_cached, "fresh_analysis_mock_fallback")

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# MULTI-TIER DATA ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════════

async def _assemble_data_context(
    symbols: List[str],
    db: Any,
    budget_seconds: float,
    log_prefix: str = "[ai_report]",
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Gathers data from three tiers concurrently using batch methods.
      Tier 1: Live prices (DataBroker, 10s cache)
      Tier 2: Technical indicators (indicators.py, 4h cache)
      Tier 3: Batch Fundamentals + Batch News (Finnhub, 12h cache)
    
    Uses 'Optimistic Assembly': If sub-batches fail or lag, we ship partial data 
    rather than timing out the entire report.
    """
    from app.services.providers.broker import get_broker
    from app.services.indicators import get_batch_indicators
    from app.services.finnhub import get_batch_fundamentals
    from app.services.snapshot_read_service import get_snapshot_bundle_for_symbols

    stage_metrics: Dict[str, Any] = {}
    include_news = bool(getattr(settings, "AI_INCLUDE_NEWS_SENTIMENT", False))
    provider_fallback_enabled = bool(getattr(settings, "AI_PROVIDER_FALLBACK_ENABLED", True))
    snapshot_reads_enabled = bool(getattr(settings, "AI_SNAPSHOT_READS_ENABLED", True))
    stage_metrics["news_included"] = include_news
    stage_metrics["provider_fallback_enabled"] = provider_fallback_enabled
    stage_metrics["snapshot_reads_enabled"] = snapshot_reads_enabled

    async def _timed_step(name: str, coroutine: Any) -> Any:
        started = time.monotonic()
        try:
            result = await coroutine
            elapsed = time.monotonic() - started
            stage_metrics[f"{name}_seconds"] = round(elapsed, 3)
            logger.info(f"{log_prefix} assembly step={name} status=ok duration={elapsed:.2f}s")
            return result
        except Exception as e:
            elapsed = time.monotonic() - started
            stage_metrics[f"{name}_seconds"] = round(elapsed, 3)
            logger.warning(
                f"{log_prefix} assembly step={name} status=error duration={elapsed:.2f}s error={e}"
            )
            return e

    async def _constant(value: Any) -> Any:
        return value

    required_timeframes = ["1h", "1d", "1w", "1m"]

    if snapshot_reads_enabled:
        snapshot_bundle = await _timed_step("snapshot_read", get_snapshot_bundle_for_symbols(db, symbols))
        if not isinstance(snapshot_bundle, dict):
            snapshot_bundle = {}
    else:
        snapshot_bundle = {}

    missing_indicator_symbols = []
    for sym in symbols:
        sym_bundle = snapshot_bundle.get(sym, {})
        tf_map = sym_bundle.get("technicals_by_timeframe", {}) if isinstance(sym_bundle, dict) else {}
        if any(tf not in tf_map for tf in required_timeframes):
            missing_indicator_symbols.append(sym)

    news_coro: Any
    if include_news and provider_fallback_enabled:
        from app.services.finnhub import get_batch_news_sentiment
        news_coro = get_batch_news_sentiment(symbols)
    else:
        news_coro = _empty_news_batch(symbols)

    # 1. Start all batch tasks
    indicator_symbols = missing_indicator_symbols if missing_indicator_symbols else symbols
    indicator_coro = (
        get_batch_indicators(indicator_symbols, required_timeframes, db)
        if provider_fallback_enabled
        else _constant({})
    )
    fundamentals_coro = (
        get_batch_fundamentals(symbols)
        if provider_fallback_enabled
        else _constant([{} for _ in symbols])
    )

    wrapped_tasks = [
        _timed_step("quotes", get_broker().fetch_quotes(symbols)),
        _timed_step("indicators", indicator_coro),
        _timed_step("fundamentals", fundamentals_coro),
        _timed_step("news", news_coro),
    ]

    # 2. Execute with strict assembly budget
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*wrapped_tasks, return_exceptions=True),
            timeout=max(0.5, budget_seconds),
        )
        prices = results[0] if not isinstance(results[0], Exception) else []
        ti_batch = results[1] if not isinstance(results[1], Exception) else {}
        fundamentals_batch = results[2] if not isinstance(results[2], Exception) else []
        news_batch = results[3] if not isinstance(results[3], Exception) else []
    except asyncio.TimeoutError:
        logger.warning(
            f"{log_prefix} assembly timed out at {budget_seconds:.2f}s for symbols={symbols}. "
            "Collating partial data."
        )
        stage_metrics["assembly_timeout"] = 1.0
        prices, ti_batch, fundamentals_batch, news_batch = [], {}, [], []

    # 3. Collate per-asset context
    price_map = {p["symbol"]: p for p in prices if isinstance(p, dict) and "symbol" in p} if isinstance(prices, list) else {}
    stale_price_count = 0
    
    assets = []
    for i, sym in enumerate(symbols):
        asset: Dict[str, Any] = {"symbol": sym}

        # Price
        price_data = price_map.get(sym, {})
        asset["price"] = price_data.get("price", 0)
        asset["change_percent"] = price_data.get("changePercent", 0)
        if price_data.get("is_stale") or str(price_data.get("source", "")).startswith("db_"):
            stale_price_count += 1

        # Technicals: snapshot-first + provider fallback merge
        snapshot_for_symbol = snapshot_bundle.get(sym, {}) if isinstance(snapshot_bundle, dict) else {}
        snapshot_technicals = snapshot_for_symbol.get("technicals_by_timeframe", {}) if isinstance(snapshot_for_symbol, dict) else {}
        fallback_technicals = ti_batch.get(sym, {}) if isinstance(ti_batch, dict) else {}

        merged_technicals: Dict[str, Any] = {}
        for tf in required_timeframes:
            snap_tf = snapshot_technicals.get(tf, {}) if isinstance(snapshot_technicals, dict) else {}
            fb_tf = fallback_technicals.get(tf, {}) if isinstance(fallback_technicals, dict) else {}
            merged = dict(fb_tf or {})
            merged.update(snap_tf or {})
            merged_technicals[tf] = merged if merged else {}
        asset["technicals"] = merged_technicals

        # Fundamentals: snapshot-first + fallback provider collation
        fund = snapshot_for_symbol.get("fundamentals_snapshot", {}) if isinstance(snapshot_for_symbol, dict) else {}
        if not isinstance(fund, dict):
            fund = {}
        if isinstance(fundamentals_batch, list) and i < len(fundamentals_batch):
            f_item = fundamentals_batch[i]
            if isinstance(f_item, dict):
                merged_fund = dict(f_item)
                merged_fund.update(fund)
                fund = merged_fund
        asset["fundamentals"] = fund

        # Events/News: snapshot-first with fallback news sentiment merge
        events_snapshot = snapshot_for_symbol.get("events_and_news_snapshot", {}) if isinstance(snapshot_for_symbol, dict) else {}
        news = {
            "trending_topics": events_snapshot.get("news_topics", []) if isinstance(events_snapshot, dict) else [],
            "earnings_events": events_snapshot.get("earnings", []) if isinstance(events_snapshot, dict) else [],
        }
        if isinstance(news_batch, list) and i < len(news_batch):
            n_item = news_batch[i]
            if isinstance(n_item, dict):
                merged_news = dict(n_item)
                merged_news.update(news)
                news = merged_news
        asset["news_sentiment"] = news
        asset["coverage"] = snapshot_for_symbol.get("coverage", {}) if isinstance(snapshot_for_symbol, dict) else {}

        assets.append(asset)

    stage_metrics["resolved_price_count"] = float(len(price_map))
    stage_metrics["stale_price_count"] = float(stale_price_count)
    stage_metrics["asset_count"] = float(len(assets))
    if assets:
        coverage_by_symbol: Dict[str, float] = {}
        covered_timeframes = 0
        expected_timeframes = len(assets) * len(required_timeframes)
        for a in assets:
            technicals = a.get("technicals", {})
            symbol = str(a.get("symbol", "UNKNOWN"))
            symbol_covered = 0
            for tf in required_timeframes:
                tf_payload = technicals.get(tf, {}) if isinstance(technicals, dict) else {}
                if isinstance(tf_payload, dict) and any(
                    tf_payload.get(k) is not None
                    for k in ("trend_signal", "rsi_14", "ema_9", "ema_21", "sma_50", "sma_200")
                ):
                    symbol_covered += 1
            coverage_by_symbol[symbol] = round(symbol_covered / max(1, len(required_timeframes)), 3)
            covered_timeframes += symbol_covered
        stage_metrics["technical_timeframe_coverage_ratio"] = round(
            covered_timeframes / max(1, expected_timeframes), 3
        )
        stage_metrics["technical_coverage_by_symbol"] = coverage_by_symbol
    if assets:
        coverage_scores = []
        for a in assets:
            cov = a.get("coverage", {})
            if isinstance(cov, dict):
                for tf, details in cov.items():
                    if isinstance(details, dict):
                        score = details.get("coverage_score")
                        if isinstance(score, (int, float)):
                            coverage_scores.append(float(score))
        if coverage_scores:
            stage_metrics["avg_coverage_score"] = round(sum(coverage_scores) / len(coverage_scores), 3)
    logger.info(
        f"{log_prefix} assembly summary assets={len(assets)} resolved_prices={len(price_map)} "
        f"stale_prices={stale_price_count} news_included={include_news}"
    )

    return {"assets": assets, "timestamp": datetime.now(timezone.utc).isoformat()}, stage_metrics



async def _get_cached_fundamentals(symbol: str) -> Dict[str, Any]:
    """Fetch fundamentals with a 12-hour cache."""
    cache_key = f"fundamentals_cache:{symbol}"
    cached = await cache_client.get(cache_key)
    if cached:
        return cached

    from app.services.finnhub import fetch_fundamentals
    result = await fetch_fundamentals(symbol)
    await cache_client.set(cache_key, result, expire_seconds=_FUNDAMENTALS_CACHE_TTL)
    return result


async def _empty_news_batch(symbols: List[str]) -> List[Dict[str, Any]]:
    """
    Returns placeholder news payloads to preserve context shape when news sentiment
    is intentionally disabled for latency/reliability.
    """
    return [{} for _ in symbols]


# ═══════════════════════════════════════════════════════════════════════════════
# ANTHROPIC INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

_MASTER_PROMPT = """You are the ultimate Hybrid Financial Analyst: a neutral, data-driven strategist with an "institutional investigator" rigor and a down-to-earth, plain-English communication style.

Your mission is to bridge the gap between complex market data and actionable, human-readable insights. You don't just report numbers; you connect dots between technical signals and fundamental health across multiple horizons.

## Core Focus Areas:
1. **Multi-Horizon Technicals:** Match RSI/MACD with SMA/EMA structure for tactical and strategic trend quality.
2. **Fundamental Health:** Use valuation/profitability metrics (P/E, EPS, etc.) as context for quality and risk.
3. **Technical-Fundamental Synthesis:** Balance momentum/trend behavior with business quality and valuation signals.

## Your Analysis Guidelines
- **Be direct and honest:** No fluff, no hype. If the data looks weak, say so plainly.
- **Evidence-Based:** Ground every observation in the DATA provided below.
- **Multi-Horizon Nuance:** Contrast the provided timeframes (1h, 1d, 1w, 1m when available). 
  - *Tactical (1h):* Use EMA_9/EMA_21 crossovers for immediate entry/exit signals.
  - *Trend (1d):* The medium-term directional flow and SMA_50 support.
  - *Strategic (1w):* High-timeframe structural health and major cycles.
  - *Regime (1m):* Monthly structure should inform valuation/risk framing when present.
- **Highlight Conflicts:** If an asset is bullish on the Weekly but overextended on the 1h, flag it as a "Tactical Caution."
- **No external news dependence required:** Base conclusions on provided technical/fundamental fields even when news sentiment is missing.

## Output Format
Return a valid JSON object with this EXACT structure:
{
  "market_summary": "1-2 sentence macro overview of current conditions",
  "watchlist_health": "STRONG" | "MODERATE" | "WEAK" | "MIXED",
  "risk_level": "LOW" | "MODERATE" | "HIGH",
  "tactical_outlook": "Summary of immediate 1-5 day market momentum",
  "strategic_horizon": "Summary of long-term structural trends and macro positioning",
  "assets": [
    {
      "symbol": "TICKER",
      "verdict": "BULLISH" | "BEARISH" | "NEUTRAL" | "CAUTION",
      "timeframe_signals": {
        "tactical_1h": "Bullish" | "Bearish" | "Neutral",
        "trend_1d": "Bullish" | "Bearish" | "Neutral",
        "strategic_1w": "Bullish" | "Bearish" | "Neutral"
      },
      "key_metrics": {
        "rsi_daily": 45.2,
        "pe_ratio": 22.5,
        "macd_signal": "Bullish" | "Bearish" | "Neutral"
      },
      "analysis_bullets": [
        "Tactical: [1h observation]",
        "Trend: [Daily observation]",
        "Strategic: [Weekly observation]",
        "Fundamental/Catalyst: [Observation]"
      ],
      "catalyst": "Brief upcoming event or news",
      "action_note": "Brief, neutral, educational observation"
    }
  ],
  "overall_insight": "2-3 sentence portfolio-level takeaway"
}

IMPORTANT: Return ONLY the JSON object. 
- DO NOT include markdown code fences (```json).
- DO NOT include any conversational preamble (e.g., "Certainly," or "Here is...").
- DO NOT include any post-analysis commentary.
- Your entire response MUST start with '{' and end with '}'.
- Ensure the JSON is valid and strictly follows the schema above.
"""


async def _call_anthropic(
    symbols: List[str],
    data_context: Dict[str, Any],
    timeout_seconds: float = 12.0,
    parse_budget_seconds: float = 1.5,
    log_prefix: str = "[ai_report]",
) -> Dict[str, Any]:
    """Send the assembled data to Anthropic and parse the structured response."""
    api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
    simulated_allowed = bool(getattr(settings, "AI_ALLOW_SIMULATED_FALLBACK", False))
    model_meta: Dict[str, Any] = {"parse_outcome": "not_attempted", "steps": []}

    def _fallback_or_raise(reason: str, *, is_configuration: bool = False) -> Dict[str, Any]:
        model_meta["failure_reason"] = reason
        model_meta["parse_outcome"] = model_meta.get("parse_outcome") or "failed"
        if simulated_allowed:
            payload = _generate_mock_report(symbols, data_context, error_reason=reason)
            payload["_model_meta"] = dict(model_meta)
            return payload
        if is_configuration:
            raise RuntimeError(reason)
        raise ValueError(reason)

    if not api_key or "testkey" in api_key:
        reason = "No valid Anthropic API key configured"
        logger.warning("%s. Simulated fallback enabled=%s", reason, simulated_allowed)
        return _fallback_or_raise(reason, is_configuration=True)

    call_deadline = time.monotonic() + max(1.0, timeout_seconds)

    async def _post_messages(
        *,
        system_prompt: str,
        content: str,
        max_tokens: int,
        step_name: str,
    ) -> str:
        remaining = _seconds_remaining(call_deadline)
        if remaining <= 0:
            raise asyncio.TimeoutError(f"No model budget left before step={step_name}")
        client = get_llm_http_client()
        request_payload = {
            "model": _MODEL,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": content}],
        }
        for attempt in range(2):
            try:
                response = await client.post(
                    _ANTHROPIC_API_URL,
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=request_payload,
                    timeout=httpx.Timeout(connect=5.0, read=max(1.0, remaining), write=8.0, pool=5.0),
                )
                response.raise_for_status()
                payload = response.json()
                text = payload.get("content", [{}])[0].get("text", "")
                model_meta["steps"].append(
                    {"step": step_name, "attempt": attempt + 1, "status": "ok"}
                )
                if not isinstance(text, str):
                    return ""
                return text
            except httpx.ReadTimeout:
                model_meta["steps"].append(
                    {"step": step_name, "attempt": attempt + 1, "status": "read_timeout"}
                )
                if attempt == 0 and _seconds_remaining(call_deadline) > 3.0:
                    continue
                raise

    try:
        symbol_count = len(symbols)

        # ── Small watchlists (<=2): use existing single-stage flow ────────────
        if symbol_count <= 2:
            user_message = f"""Analyze the following watchlist as of {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.

## Watchlist Data Context
{json.dumps(data_context, indent=2, default=str)}

Provide your analysis following the output format specified in your system instructions."""

            text = await _post_messages(
                system_prompt=_MASTER_PROMPT,
                content=user_message,
                max_tokens=1200,
                step_name="primary",
            )

            parsed, parse_mode = _parse_ai_json_response_with_mode(
                text=text,
                parse_budget_seconds=parse_budget_seconds,
                log_prefix=log_prefix,
            )
            if parsed is not None:
                model_meta["parse_outcome"] = parse_mode
                parsed["_model_meta"] = dict(model_meta)
                return parsed

            logger.warning(
                "%s primary model output was not valid JSON. len=%s first_200=%s",
                log_prefix,
                len(text),
                text[:200],
            )

            # Formatter retry: convert narrative output into strict JSON schema.
            remaining = _seconds_remaining(call_deadline)
            if remaining > 1.0:
                formatter_prompt = (
                    "Convert the following analysis text into VALID JSON using this schema keys only: "
                    "market_summary, watchlist_health, risk_level, tactical_outlook, strategic_horizon, assets, overall_insight. "
                    "For each asset include: symbol, verdict, timeframe_signals, key_metrics, analysis_bullets, catalyst, action_note. "
                    "Return JSON only, no markdown, no prose."
                )
                formatted_text = await _post_messages(
                    system_prompt="You are a strict JSON formatter.",
                    content=f"{formatter_prompt}\n\nANALYSIS_TEXT:\n{text}",
                    max_tokens=900,
                    step_name="formatter_retry",
                )
                parsed_retry, retry_parse_mode = _parse_ai_json_response_with_mode(
                    text=formatted_text,
                    parse_budget_seconds=min(parse_budget_seconds, 1.0),
                    log_prefix=log_prefix,
                )
                if parsed_retry is not None:
                    logger.info("%s formatter retry recovered valid JSON output", log_prefix)
                    model_meta["parse_outcome"] = f"formatter_retry:{retry_parse_mode}"
                    parsed_retry["_model_meta"] = dict(model_meta)
                    return parsed_retry

            model_meta["parse_outcome"] = "failed"
            return _fallback_or_raise("Anthropic returned non-JSON output after formatter retry")

        # ── Larger watchlists: two-stage per-asset + portfolio synthesis ──────
        assets = data_context.get("assets", [])

        async def _per_asset_summary(asset: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            sym = asset.get("symbol", "UNKNOWN")
            core_payload = {
                "symbol": sym,
                "price": asset.get("price"),
                "change_percent": asset.get("change_percent"),
                "technicals": asset.get("technicals", {}),
                "fundamentals": asset.get("fundamentals", {}),
            }
            mini_prompt = (
                "Given the following single-asset snapshot (price, 1h/1d/1w technicals, and fundamentals), "
                "return a compact JSON object ONLY with these keys: "
                "symbol, verdict, timeframe_signals, key_metrics, analysis_bullets, catalyst, action_note. "
                "Do not include any other keys or wrapper objects. JSON only, no markdown, no prose."
            )
            content = f"{mini_prompt}\n\nASSET_SNAPSHOT:\n{json.dumps(core_payload, indent=2, default=str)}"

            try:
                text = await _post_messages(
                    system_prompt="You are a concise, strictly-JSON-generating single-asset analyst.",
                    content=content,
                    max_tokens=320,
                    step_name=f"asset_{sym}",
                )
                parsed, parse_mode = _parse_ai_json_response_with_mode(
                    text=text,
                    parse_budget_seconds=min(parse_budget_seconds, 0.8),
                    log_prefix=f"{log_prefix}[asset={sym}]",
                )
                if parsed is None:
                    return None
                parsed["symbol"] = parsed.get("symbol") or sym
                return parsed
            except Exception as e:
                logger.warning(
                    "%s per-asset summary failed for %s: %s",
                    log_prefix,
                    sym,
                    _sanitize_error_message(str(e)),
                )
                return None

        per_asset_tasks = [_per_asset_summary(a) for a in assets]
        per_asset_results = await asyncio.gather(*per_asset_tasks, return_exceptions=True)

        mini_summaries: List[Dict[str, Any]] = []
        for asset, result in zip(assets, per_asset_results):
            if isinstance(result, Exception) or result is None:
                mini_summaries.append(
                    {
                        "symbol": asset.get("symbol", "UNKNOWN"),
                        "verdict": "NEUTRAL",
                        "timeframe_signals": {
                            "tactical_1h": asset.get("technicals", {}).get("1h", {}).get("trend_signal", "Neutral"),
                            "trend_1d": asset.get("technicals", {}).get("1d", {}).get("trend_signal", "Neutral"),
                            "strategic_1w": asset.get("technicals", {}).get("1w", {}).get("trend_signal", "Neutral"),
                        },
                        "key_metrics": {
                            "rsi_daily": asset.get("technicals", {}).get("1d", {}).get("rsi_14"),
                            "pe_ratio": asset.get("fundamentals", {}).get("pe_ratio"),
                            "macd_signal": asset.get("technicals", {}).get("1d", {}).get("trend_signal", "Neutral"),
                        },
                        "analysis_bullets": [
                            "AI mini-summary unavailable; using raw trend and fundamental hints instead."
                        ],
                        "catalyst": "No specific catalyst identified.",
                        "action_note": "Use this asset as part of the broader portfolio context.",
                    }
                )
            else:
                mini_summaries.append(result)

        remaining = _seconds_remaining(call_deadline)
        if remaining <= 0:
            raise asyncio.TimeoutError("No model budget left before portfolio synthesis")

        portfolio_prompt = (
            "You are a portfolio-level analyst. You are given a list of per-asset mini summaries that already contain "
            "verdicts, timeframe_signals, and key_metrics. Using ONLY these summaries, produce a SINGLE JSON object "
            "matching the schema: market_summary, watchlist_health, risk_level, tactical_outlook, strategic_horizon, "
            "assets, overall_insight. For each asset in 'assets', you may reuse or refine the provided fields, but do "
            "not invent symbols that are not present. JSON only, no markdown, no prose."
        )
        user_message = f"""As of {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}, analyze this portfolio based on mini summaries:

PER_ASSET_MINI_SUMMARIES:
{json.dumps(mini_summaries, indent=2, default=str)}

Follow the output schema described in your system instructions."""

        text = await _post_messages(
            system_prompt=_MASTER_PROMPT,
            content=user_message,
            max_tokens=900,
            step_name="portfolio_synthesis",
        )

        parsed, parse_mode = _parse_ai_json_response_with_mode(
            text=text,
            parse_budget_seconds=parse_budget_seconds,
            log_prefix=f"{log_prefix}[portfolio]",
        )
        if parsed is not None:
            model_meta["parse_outcome"] = parse_mode
            assets_by_symbol = {a.get("symbol"): a for a in mini_summaries if isinstance(a, dict)}
            parsed_assets = parsed.get("assets")
            if isinstance(parsed_assets, list) and parsed_assets:
                normalized_assets: List[Dict[str, Any]] = []
                for sym in symbols:
                    for pa in parsed_assets:
                        if isinstance(pa, dict) and (pa.get("symbol") or "").upper() == sym.upper():
                            normalized_assets.append(pa)
                            break
                    else:
                        if sym in assets_by_symbol:
                            normalized_assets.append(assets_by_symbol[sym])
                if normalized_assets:
                    parsed["assets"] = normalized_assets
            parsed["_model_meta"] = dict(model_meta)
            return parsed

        logger.warning(
            "%s portfolio synthesis output was not valid JSON. Falling back to mock report.",
            f"{log_prefix}[portfolio]",
        )
        model_meta["parse_outcome"] = "failed"
        return _fallback_or_raise("Portfolio synthesis returned non-JSON output")

    except httpx.ReadTimeout as e:
        # Treat read timeouts as a hard pipeline timeout so the outer route-level
        # timeout handler can return a consistent timeout message instead of a
        # simulated fallback report.
        logger.warning(
            "%s Anthropic ReadTimeout after %.2fs: %s",
            log_prefix,
            timeout_seconds,
            _sanitize_error_message(str(e)),
        )
        raise asyncio.TimeoutError("Anthropic ReadTimeout") from e
    except httpx.HTTPStatusError as e:
        endpoint = _sanitize_url_for_logs(str(e.request.url)) if e.request else _ANTHROPIC_API_URL
        body_preview = _sanitize_error_message(e.response.text[:200] if e.response and e.response.text else "")
        logger.error(
            "%s Anthropic API error status=%s endpoint=%s body=%s",
            log_prefix,
            e.response.status_code if e.response else "unknown",
            endpoint,
            body_preview,
        )
        reason = f"Anthropic API Error {e.response.status_code if e.response else 'unknown'}"
        if body_preview:
            reason = f"{reason}: {body_preview[:120]}"
        return _fallback_or_raise(reason)
    except Exception as e:
        sanitized = _sanitize_error_message(str(e))
        if not sanitized:
            sanitized = _sanitize_error_message(repr(e))
        logger.error(
            "%s Anthropic call failed type=%s detail=%s",
            log_prefix,
            type(e).__name__,
            sanitized or "no_message",
        )
        detail = sanitized or "no_message"
        return _fallback_or_raise(f"Network/Internal Error ({type(e).__name__}): {detail}")


def _seconds_remaining(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _parse_ai_json_response(
    text: str,
    parse_budget_seconds: float,
    log_prefix: str,
) -> Optional[Dict[str, Any]]:
    parsed, _ = _parse_ai_json_response_with_mode(
        text=text,
        parse_budget_seconds=parse_budget_seconds,
        log_prefix=log_prefix,
    )
    return parsed


def _parse_ai_json_response_with_mode(
    text: str,
    parse_budget_seconds: float,
    log_prefix: str,
) -> Tuple[Optional[Dict[str, Any]], str]:
    parse_deadline = time.monotonic() + max(0.1, parse_budget_seconds)

    def _try_load(payload: str) -> Optional[Dict[str, Any]]:
        if not payload:
            return None
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
        return None

    # Attempt 1: direct parse
    direct = _try_load(text)
    if direct is not None:
        return direct, "direct"
    if _seconds_remaining(parse_deadline) <= 0:
        return None, "budget_exhausted"

    # Attempt 2: markdown fenced JSON
    import re

    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fenced:
        parsed_fenced = _try_load(fenced.group(1))
        if parsed_fenced is not None:
            return parsed_fenced, "fenced"
    if _seconds_remaining(parse_deadline) <= 0:
        return None, "budget_exhausted"

    # Attempt 3: bracket window extraction
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        window = text[start_idx : end_idx + 1]
        parsed_window = _try_load(window)
        if parsed_window is not None:
            return parsed_window, "window"

        # Attempt 4: deterministic normalization for common model artifacts
        normalized = (
            window.replace("\u201c", '"')
            .replace("\u201d", '"')
            .replace("\u2018", "'")
            .replace("\u2019", "'")
        )
        normalized = re.sub(r"\bTrue\b", "true", normalized)
        normalized = re.sub(r"\bFalse\b", "false", normalized)
        normalized = re.sub(r"\bNone\b", "null", normalized)
        normalized = re.sub(r",\s*([}\]])", r"\1", normalized)  # trailing commas

        parsed_normalized = _try_load(normalized)
        if parsed_normalized is not None:
            logger.info("%s recovered non-JSON AI output via normalization", log_prefix)
            return parsed_normalized, "normalized"

    return None, "failed"


def _sanitize_url_for_logs(url: str) -> str:
    """
    Remove query strings from URLs to avoid leaking tokens in logs.
    """
    try:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}{parts.path}"
    except Exception:
        return _ANTHROPIC_API_URL


def _sanitize_error_message(message: str) -> str:
    """
    Best-effort sanitization for logs and user-safe error metadata.
    """
    if not message:
        return ""
    import re

    sanitized = message
    # remove obvious token/api-key style query params
    sanitized = re.sub(r"([?&](?:token|api[_-]?key|x-api-key)=)[^&\\s]+", r"\1<redacted>", sanitized, flags=re.I)
    # collapse whitespace for concise logging
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized[:400]


def _generate_mock_report(symbols: List[str], data_context: Dict[str, Any], error_reason: Optional[str] = None) -> Dict[str, Any]:
    """Generate a realistic mock report when no API key is available or the API call fails."""
    assets = []
    for asset_data in data_context.get("assets", []):
        sym = asset_data.get("symbol", "???")
        ti = asset_data.get("technicals", {})
        fund = asset_data.get("fundamentals", {})

        ti_all = asset_data.get("technicals", {})
        ti_1h = ti_all.get("1h", {}) or {}
        ti_1d = ti_all.get("1d", {}) or {}
        ti_1w = ti_all.get("1w", {}) or {}

        rsi_1d = ti_1d.get("rsi_14")
        trend_1d = ti_1d.get("trend_signal", "Neutral")
        pe = fund.get("pe_ratio")
        
        # Mock EMA logic (heuristic)
        ema_9 = ti_1h.get("ema_9")
        ema_21 = ti_1h.get("ema_21")
        ema_sig = "Neutral"
        if ema_9 and ema_21:
            ema_sig = "Bullish" if ema_9 > ema_21 else "Bearish"
        
        # Build key metrics
        key_metrics = {
            "rsi_daily": round(rsi_1d, 1) if rsi_1d is not None else None,
            "pe_ratio": round(pe, 1) if pe is not None else None,
            "macd_signal": trend_1d,
            "ema_signal": ema_sig
        }

        # Build bullet points
        analysis_bullets = [
            f"Tactical: {ti_1h.get('trend_signal', 'Neutral')} momentum on 1h timeframe.",
            f"Trend: Daily structure is {trend_1d.lower()} with RSI at {rsi_1d if rsi_1d else 'N/A'}.",
            f"Strategic: Weekly health is currently {ti_1w.get('trend_signal', 'Neutral').lower()}.",
            f"Fundamental: P/E Ratio at {pe:.1f}" if pe is not None else "Fundamental data limited."
        ]

        assets.append({
            "symbol": sym,
            "verdict": "BULLISH" if trend_1d == "Bullish" else "NEUTRAL",
            "timeframe_signals": {
                "tactical_1h": ti_1h.get("trend_signal", "Neutral"),
                "trend_1d": trend_1d,
                "strategic_1w": ti_1w.get("trend_signal", "Neutral")
            },
            "key_metrics": key_metrics,
            "analysis_bullets": analysis_bullets,
            "catalyst": "Earnings season approaching — watch for guidance updates.",
            "action_note": "Simulated report based on triple-horizon technical snapshots."
        })

    insight_text = "This is a simulated analysis. To enable real AI-powered analysis, add your ANTHROPIC_API_KEY to the backend environment variables."
    if error_reason:
        insight_text = f"Simulated Analysis. AI engine fallback triggered: {error_reason}"

    return {
        "market_summary": "Markets are showing mixed signals. Monitor key support levels across major indices.",
        "watchlist_health": "MIXED",
        "risk_level": "MODERATE",
        "tactical_outlook": "Immediate sentiment is cautious following recent volatility.",
        "strategic_horizon": "Long-term bullish structure remains intact despite short-term pullbacks.",
        "assets": assets,
        "overall_insight": insight_text,
        "_mock": True,
        "mock_reason": error_reason or "Missing or invalid ANTHROPIC_API_KEY; using local fallback synthesis.",
        "source_status": "mock_fallback",
        "_analysis_origin": {
            "is_mock": True,
            "path": "mock_fallback",
            "reason": error_reason or "missing_or_invalid_api_key",
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

async def get_last_good_report(user_id: str, symbols: List[str]) -> Optional[Dict[str, Any]]:
    key = _last_good_report_key(user_id, symbols)
    cached = await cache_client.get(key)
    return cached if isinstance(cached, dict) else None


def _last_good_report_key(user_id: str, symbols: List[str]) -> str:
    return f"{_report_cache_key(user_id, symbols)}:last_good"


def _last_attempt_meta_key(user_id: str, symbols: List[str]) -> str:
    return f"{_report_cache_key(user_id, symbols)}:last_attempt"


def _decorate_last_good_report(report: Dict[str, Any], reason: str) -> Dict[str, Any]:
    safe = dict(report)
    safe["from_cache"] = True
    safe["source_status"] = "last_good_fallback"
    safe["_served_last_good"] = True
    safe["_fallback_reason"] = reason
    safe["_analysis_origin"] = {
        "is_mock": bool(safe.get("_mock", False)),
        "path": "last_good_fallback",
        "reason": reason,
        "generated_at": safe.get("generated_at"),
    }
    return safe


def _assess_report_quality(report: Dict[str, Any], data_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detect obvious low-confidence outputs so they do not replace stronger last-good reports.
    We intentionally keep this conservative to avoid suppressing legitimate neutral analysis.
    """
    assets = report.get("assets")
    if not isinstance(assets, list) or not assets:
        return {"reject_as_low_confidence": False, "reason": "no_assets"}

    verdicts = [
        str(a.get("verdict", "")).upper()
        for a in assets
        if isinstance(a, dict)
    ]
    all_neutral = bool(verdicts) and all(v == "NEUTRAL" for v in verdicts)

    context_assets = data_context.get("assets", [])
    technical_ready_count = 0
    for c_asset in context_assets if isinstance(context_assets, list) else []:
        if not isinstance(c_asset, dict):
            continue
        technicals = c_asset.get("technicals", {})
        if not isinstance(technicals, dict):
            continue
        has_any_core = False
        for tf in ("1h", "1d", "1w", "1m"):
            tf_payload = technicals.get(tf, {})
            if not isinstance(tf_payload, dict):
                continue
            if any(
                tf_payload.get(k) is not None
                for k in ("rsi_14", "trend_signal", "ema_9", "ema_21", "sma_50", "sma_200")
            ):
                has_any_core = True
                break
        if has_any_core:
            technical_ready_count += 1

    total_assets = len(assets)
    technical_coverage_ratio = technical_ready_count / max(1, total_assets)
    insight = str(report.get("overall_insight", "")).lower()
    missing_data_phrase = (
        "without robust technical" in insight
        or "absence of" in insight
        or "missing hourly" in insight
    )

    reject = all_neutral and technical_coverage_ratio >= 0.8 and missing_data_phrase
    return {
        "reject_as_low_confidence": reject,
        "reason": "all_neutral_with_missing_data_claim" if reject else "accepted",
        "all_neutral": all_neutral,
        "technical_coverage_ratio": round(technical_coverage_ratio, 3),
    }


def _safe_text(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _normalize_asset(asset: Dict[str, Any]) -> Dict[str, Any]:
    timeframe_signals = asset.get("timeframe_signals")
    if not isinstance(timeframe_signals, dict):
        timeframe_signals = {}
    key_metrics = asset.get("key_metrics")
    if not isinstance(key_metrics, dict):
        key_metrics = {}
    analysis_bullets = asset.get("analysis_bullets")
    if not isinstance(analysis_bullets, list):
        analysis_bullets = []
    analysis_bullets = [str(item) for item in analysis_bullets[:6] if item is not None]
    if not analysis_bullets:
        analysis_bullets = ["Insufficient structured data to generate detailed bullet analysis."]

    return {
        "symbol": _safe_text(asset.get("symbol"), "UNKNOWN"),
        "verdict": _safe_text(asset.get("verdict"), "NEUTRAL").upper(),
        "timeframe_signals": {
            "tactical_1h": _safe_text(timeframe_signals.get("tactical_1h"), "Neutral"),
            "trend_1d": _safe_text(timeframe_signals.get("trend_1d"), "Neutral"),
            "strategic_1w": _safe_text(timeframe_signals.get("strategic_1w"), "Neutral"),
        },
        "key_metrics": {
            "rsi_daily": key_metrics.get("rsi_daily"),
            "pe_ratio": key_metrics.get("pe_ratio"),
            "macd_signal": _safe_text(key_metrics.get("macd_signal"), "Neutral"),
        },
        "analysis_bullets": analysis_bullets,
        "catalyst": _safe_text(asset.get("catalyst"), "No immediate catalyst identified."),
        "action_note": _safe_text(asset.get("action_note"), "Maintain disciplined risk management."),
    }


def _enforce_report_schema(report: Dict[str, Any], symbols: List[str], strict: bool) -> Dict[str, Any]:
    payload = report if isinstance(report, dict) else {}
    keys_present = set(payload.keys())
    missing = _REPORT_REQUIRED_KEYS - keys_present

    assets_raw = payload.get("assets")
    assets: List[Dict[str, Any]] = []
    if isinstance(assets_raw, list):
        assets = [_normalize_asset(item) for item in assets_raw if isinstance(item, dict)]

    if strict and missing:
        logger.warning("strict schema repair engaged missing_keys=%s", sorted(missing))

    if not assets and symbols:
        assets = [{"symbol": s, "verdict": "NEUTRAL", "timeframe_signals": {"tactical_1h": "Neutral", "trend_1d": "Neutral", "strategic_1w": "Neutral"}, "key_metrics": {"rsi_daily": None, "pe_ratio": None, "macd_signal": "Neutral"}, "analysis_bullets": ["Data was incomplete during generation."], "catalyst": "No catalyst available.", "action_note": "Wait for a refreshed analysis."} for s in symbols]

    return {
        "market_summary": _safe_text(payload.get("market_summary"), "Markets are mixed and require selective positioning."),
        "watchlist_health": _safe_text(payload.get("watchlist_health"), "MIXED").upper(),
        "risk_level": _safe_text(payload.get("risk_level"), "MODERATE").upper(),
        "tactical_outlook": _safe_text(payload.get("tactical_outlook"), "Short-term conditions are mixed; wait for confirmation."),
        "strategic_horizon": _safe_text(payload.get("strategic_horizon"), "Long-term positioning remains data-dependent."),
        "assets": assets,
        "overall_insight": _safe_text(payload.get("overall_insight"), "Use risk controls and refresh analysis as conditions evolve."),
        "_mock": bool(payload.get("_mock", False)),
        "mock_reason": payload.get("mock_reason"),
    }


def _report_cache_key(user_id: str, symbols: List[str]) -> str:
    """Generate a deterministic cache key based on user + sorted symbols."""
    sorted_syms = sorted(list(set(symbols)))
    sym_hash = hashlib.md5(",".join(sorted_syms).encode()).hexdigest()[:12]
    return f"ai_report:{user_id}:{sym_hash}"


def _prune_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trims the data context to prevent massive payloads and AI token bloat.
    - Limits news headlines to top 2 per symbol.
    - Removes secondary technical signals (Bollinger, etc.) for large watchlists.
    """
    assets = context.get("assets", [])
    symbol_count = len(assets)
    
    pruned_assets = []
    for asset in assets:
        p_asset = asset.copy()
        
        # 1. Truncate News (Finnhub can return 50+ headlines)
        news = p_asset.get("news_sentiment", {})
        if "trending_topics" in news:
            news["trending_topics"] = news["trending_topics"][:2]
        
        # 2. Strategic technical pruning for large lists
        if symbol_count > 5:
            technicals = p_asset.get("technicals", {})
            for timeframe in ["1h", "1d", "1w", "1m"]:
                tf_data = technicals.get(timeframe, {})
                if tf_data:
                    # Keep core trend indicators, lose volatility/secondary ones
                    slim_tf = {
                        "trend_signal": tf_data.get("trend_signal"),
                        "rsi_14": tf_data.get("rsi_14"),
                        "ema_9": tf_data.get("ema_9"),
                        "ema_21": tf_data.get("ema_21"),
                        "sma_50": tf_data.get("sma_50") if timeframe in ["1d", "1m"] else None,
                        "sma_200": tf_data.get("sma_200") if timeframe == "1m" else None,
                    }
                    technicals[timeframe] = {k: v for k, v in slim_tf.items() if v is not None}
        
        pruned_assets.append(p_asset)
        
    return {
        "assets": pruned_assets,
        "timestamp": context.get("timestamp"),
        "watchlist_size": symbol_count
    }
