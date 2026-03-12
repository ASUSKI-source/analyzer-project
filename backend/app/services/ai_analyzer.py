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
from typing import Any, Dict, List, Optional

import httpx

from app.core.cache import cache_client
from app.core.config import settings
from app.utils.http import get_http_client

logger = logging.getLogger(__name__)

# ─── Cache TTLs ──────────────────────────────────────────────────────────────
_REPORT_CACHE_TTL = 28_800       # 8 hours  — full AI report
_FUNDAMENTALS_CACHE_TTL = 43_200 # 12 hours — Finnhub fundamentals

# ─── Anthropic Config ────────────────────────────────────────────────────────
_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4-5"  # Correct model ID provided by user


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

    # ── 3. Call Anthropic ────────────────────────────────────────────────────
    # PRUNE CONTEXT: Ensure we don't send a massive payload that causes timeouts
    pruned_context = _prune_context(data_context)

    remaining_before_model = _seconds_remaining(deadline)
    if remaining_before_model <= 0:
        raise asyncio.TimeoutError("No budget left before model stage")
    effective_model_budget = min(model_budget, remaining_before_model)

    start_ai = time.monotonic()
    report = await _call_anthropic(
        symbols,
        pruned_context,
        timeout_seconds=effective_model_budget,
        parse_budget_seconds=parse_budget,
        log_prefix=log_prefix,
    )
    ai_duration = time.monotonic() - start_ai
    total_duration = time.monotonic() - pipeline_start

    logger.info(
        f"{log_prefix} Anthropic call completed in {ai_duration:.2f}s; "
        f"end-to-end report generation took {total_duration:.2f}s."
    )

    # ── 4. Cache & Return ────────────────────────────────────────────────────
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["symbols_analyzed"] = symbols
    report["from_cache"] = False

    if getattr(settings, "AI_DEBUG_TIMING", False):
        report["_debug_timing"] = {
            "request_id": request_id,
            "cache_gate_seconds": round(cache_gate_seconds, 3),
            "assembly_seconds": round(assembly_duration, 3),
            "assembly_metrics": assembly_metrics,
            "ai_seconds": round(ai_duration, 3),
            "total_seconds": round(total_duration, 3),
            "symbol_count": len(symbols),
            "budgets": {
                "total": total_budget,
                "assembly": assembly_budget,
                "model": model_budget,
                "parse": parse_budget,
            },
        }

    await cache_client.set(cache_key, report, expire_seconds=_REPORT_CACHE_TTL)
    logger.info(f"{log_prefix} AI report cached (8h TTL) for cache_key={cache_key}")

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# MULTI-TIER DATA ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════════

async def _assemble_data_context(
    symbols: List[str],
    db: Any,
    budget_seconds: float,
    log_prefix: str = "[ai_report]",
) -> tuple[Dict[str, Any], Dict[str, float]]:
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
    from app.services.finnhub import get_batch_fundamentals, get_batch_news_sentiment

    stage_metrics: Dict[str, float] = {}

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

    # 1. Start all batch tasks
    wrapped_tasks = [
        _timed_step("quotes", get_broker().fetch_quotes(symbols)),
        _timed_step("indicators", get_batch_indicators(symbols, ["1h", "1d", "1w"], db)),
        _timed_step("fundamentals", get_batch_fundamentals(symbols)),
        _timed_step("news", get_batch_news_sentiment(symbols)),
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

        # Technicals
        asset["technicals"] = ti_batch.get(sym, {
            "1h": {}, "1d": {}, "1w": {}
        }) if isinstance(ti_batch, dict) else {"1h": {}, "1d": {}, "1w": {}}

        # Fundamentals (Optimistic collation)
        fund = {}
        if isinstance(fundamentals_batch, list) and i < len(fundamentals_batch):
            f_item = fundamentals_batch[i]
            if isinstance(f_item, dict):
                fund = f_item
        asset["fundamentals"] = fund

        # News (Optimistic collation)
        news = {}
        if isinstance(news_batch, list) and i < len(news_batch):
            n_item = news_batch[i]
            if isinstance(n_item, dict):
                news = n_item
        asset["news_sentiment"] = news

        assets.append(asset)

    stage_metrics["resolved_price_count"] = float(len(price_map))
    stage_metrics["stale_price_count"] = float(stale_price_count)
    stage_metrics["asset_count"] = float(len(assets))
    logger.info(
        f"{log_prefix} assembly summary assets={len(assets)} resolved_prices={len(price_map)} "
        f"stale_prices={stale_price_count}"
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


# ═══════════════════════════════════════════════════════════════════════════════
# ANTHROPIC INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

_MASTER_PROMPT = """You are the ultimate Hybrid Financial Analyst: a neutral, data-driven strategist with an "institutional investigator" rigor and a down-to-earth, plain-English communication style.

Your mission is to bridge the gap between complex institutional data and actionable, human-readable insights. You don't just report numbers; you connect dots between technical signals, fundamental health, and the broader "market pulse."

## Core Focus Areas:
1. **Institutional Activity & Sentiment:** Look for clues in the news and price action that suggest institutional positioning.
2. **Multi-Horizon Technicals:** Match RSI/MACD with SMA_50/200 for structural trend and EMA_9/21 for high-velocity momentum.
3. **Macro/Fundamental Hybrid:** Balance technical breakouts with valuation (P/E, EPS) and catalysts.

## Your Analysis Guidelines
- **Be direct and honest:** No fluff, no hype. If the data looks weak, say so plainly.
- **Evidence-Based:** Ground every observation in the DATA provided below.
- **Three-Horizon Nuance:** Contrast the three timeframes provided (1h, 1d, 1w). 
  - *Tactical (1h):* Use EMA_9/EMA_21 crossovers for immediate entry/exit signals.
  - *Trend (1d):* The medium-term directional flow and SMA_50 support.
  - *Strategic (1w):* High-timeframe structural health and major cycles.
- **Highlight Conflicts:** If an asset is bullish on the Weekly but overextended on the 1h, flag it as a "Tactical Caution."
- **Institutional Context:** Connect technical multi-timeframe signals to fundamental valuation and macro catalysts.

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

    if not api_key or "testkey" in api_key:
        logger.warning("No valid Anthropic API key. Generating mock AI report.")
        return _generate_mock_report(symbols, data_context)

    # Build the user message with all the data
    user_message = f"""Analyze the following watchlist as of {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.

## Watchlist Data Context
{json.dumps(data_context, indent=2, default=str)}

Provide your analysis following the output format specified in your system instructions."""

    try:
        client = get_http_client()
        response = await client.post(
            _ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": _MODEL,
                "max_tokens": 2048,
                "system": _MASTER_PROMPT,
                "messages": [
                    {"role": "user", "content": user_message}
                ],
            },
            timeout=max(1.0, timeout_seconds),
        )
        response.raise_for_status()
        result = response.json()

        # Extract the text content from Anthropic's response
        text = result.get("content", [{}])[0].get("text", "")

        parsed = _parse_ai_json_response(
            text=text,
            parse_budget_seconds=parse_budget_seconds,
            log_prefix=log_prefix,
        )
        if parsed is not None:
            return parsed

        logger.error(
            "%s failed to parse AI response as JSON. Raw length=%s first_200=%s",
            log_prefix,
            len(text),
            text[:200],
        )

        # Best-effort fallback: preserve the real AI text in a structured envelope
        # rather than discarding it or substituting a full mock.
        max_len = 4000
        truncated = text[:max_len] if isinstance(text, str) else ""
        return {
            "market_summary": "The AI engine returned an analysis that was not valid JSON. Showing the raw narrative instead.",
            "watchlist_health": "MIXED",
            "risk_level": "MODERATE",
            "tactical_outlook": "See the detailed AI narrative for short-term context.",
            "strategic_horizon": "See the detailed AI narrative for long-term context.",
            "assets": [],
            "overall_insight": truncated,
            "_mock": False,
            "parse_error": "Anthropic returned non-JSON response; using best-effort envelope.",
            "raw_text": truncated,
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"Anthropic API error: {e.response.status_code} - {e.response.text[:200]}")
        return _generate_mock_report(symbols, data_context, error_reason=f"Anthropic API Error {e.response.status_code}: {e.response.text[:100]}")
    except Exception as e:
        logger.error(f"Anthropic call failed: {e}")
        return _generate_mock_report(symbols, data_context, error_reason=f"Network/Internal Error: {str(e)}")


def _seconds_remaining(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _parse_ai_json_response(
    text: str,
    parse_budget_seconds: float,
    log_prefix: str,
) -> Optional[Dict[str, Any]]:
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
        return direct
    if _seconds_remaining(parse_deadline) <= 0:
        return None

    # Attempt 2: markdown fenced JSON
    import re

    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fenced:
        parsed_fenced = _try_load(fenced.group(1))
        if parsed_fenced is not None:
            return parsed_fenced
    if _seconds_remaining(parse_deadline) <= 0:
        return None

    # Attempt 3: bracket window extraction
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        window = text[start_idx : end_idx + 1]
        parsed_window = _try_load(window)
        if parsed_window is not None:
            return parsed_window

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
            return parsed_normalized

    return None


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
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

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
            for timeframe in ["1h", "1d", "1w"]:
                tf_data = technicals.get(timeframe, {})
                if tf_data:
                    # Keep core trend indicators, lose volatility/secondary ones
                    slim_tf = {
                        "trend_signal": tf_data.get("trend_signal"),
                        "rsi_14": tf_data.get("rsi_14"),
                        "ema_9": tf_data.get("ema_9"),
                        "ema_21": tf_data.get("ema_21"),
                        "sma_50": tf_data.get("sma_50") if timeframe == "1d" else None
                    }
                    technicals[timeframe] = {k: v for k, v in slim_tf.items() if v is not None}
        
        pruned_assets.append(p_asset)
        
    return {
        "assets": pruned_assets,
        "timestamp": context.get("timestamp"),
        "watchlist_size": symbol_count
    }
