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
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import httpx

from app.core.cache import cache_client
from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Cache TTLs ──────────────────────────────────────────────────────────────
_REPORT_CACHE_TTL = 28_800       # 8 hours  — full AI report
_FUNDAMENTALS_CACHE_TTL = 43_200 # 12 hours — Finnhub fundamentals

# ─── Anthropic Config ────────────────────────────────────────────────────────
_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4-5"  # Fast, cheap, smart enough for financial summaries


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

async def generate_watchlist_report(
    symbols: List[str],
    user_id: str,
    refresh: bool = False,
) -> Dict[str, Any]:
    """
    Assemble a comprehensive AI analysis report for the given watchlist symbols.

    Steps:
      1. Check 8-hour report cache.
      2. Gather Tier-1 (prices), Tier-2 (technicals), Tier-3 (fundamentals).
      3. Inject into master prompt → send to Anthropic.
      4. Parse structured JSON response, cache, and return.
    """
    symbols = [s.upper().strip() for s in symbols if s.strip()]
    if not symbols:
        return {"error": "No symbols provided", "assets": []}

    # ── 1. Check Report Cache (Skip if refresh=True) ─────────────────────────
    cache_key = _report_cache_key(user_id, symbols)
    if not refresh:
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

    # ── 2. Security: Global 5-minute AI Generation Cooldown ─────────────────
    cooldown_key = f"ai_generation_cooldown:{user_id}"
    cooldown_ttl = await cache_client.get_ttl(cooldown_key)
    if cooldown_ttl > 0:
        logger.warning(f"AI generation cooldown active for user {user_id} ({cooldown_ttl}s remaining)")
        return {
            "error": "Engine cooling down. You can generate a new analysis once every 5 minutes.",
            "cooldown_remaining": cooldown_ttl,
            "assets": []
        }
        
    logger.info(f"AI report cache {'BYPASS (force)' if refresh else 'MISS'} for user {user_id}. Generating report for {symbols}...")
    # Set generation cooldown (300s = 5m)
    await cache_client.set(cooldown_key, "active", expire_seconds=300)

    # ── 2. Multi-Tier Data Assembly ──────────────────────────────────────────
    data_context = await _assemble_data_context(symbols)

    # ── 3. Call Anthropic ────────────────────────────────────────────────────
    report = await _call_anthropic(symbols, data_context)

    # ── 4. Cache & Return ────────────────────────────────────────────────────
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["symbols_analyzed"] = symbols
    report["from_cache"] = False

    await cache_client.set(cache_key, report, expire_seconds=_REPORT_CACHE_TTL)
    logger.info(f"AI report cached for user {user_id} (8h TTL)")

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# MULTI-TIER DATA ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════════

async def _assemble_data_context(symbols: List[str]) -> Dict[str, Any]:
    """
    Gathers data from three tiers concurrently:
      Tier 1: Live prices (DataBroker, 10s cache)
      Tier 2: Technical indicators (indicators.py, 4h cache)
      Tier 3: Fundamentals + News (Finnhub, 12h cache)
    
    Has a strict 15-second timeout to prevent Railway proxy kills.
    """
    from app.services.providers.broker import get_broker
    from app.services.indicators import get_cached_indicators
    from app.services.finnhub import fetch_fundamentals, fetch_news_sentiment

    # Tier 1: Live prices
    price_task = get_broker().fetch_quotes(symbols)

    # Tier 2: Technical indicators (3 horizons per symbol, independently cached)
    indicator_tasks = []
    for sym in symbols:
        indicator_tasks.append(get_cached_indicators(sym, "1h"))
        indicator_tasks.append(get_cached_indicators(sym, "1d"))
        indicator_tasks.append(get_cached_indicators(sym, "1w"))

    # Tier 3: Fundamentals (individually cached for 12h)
    fundamental_tasks = [_get_cached_fundamentals(sym) for sym in symbols]

    # Tier 3b: News sentiment
    news_tasks = [fetch_news_sentiment(sym) for sym in symbols]

    # Execute all tiers with a strict timeout.
    # Total tasks: price (1) + TI (3*n) + Fund (n) + News (n) = 1 + 5n tasks
    n = len(symbols)
    try:
        all_results = await asyncio.wait_for(
            asyncio.gather(
                price_task,
                *indicator_tasks,
                *fundamental_tasks,
                *news_tasks,
                return_exceptions=True,
            ),
            timeout=15.0,
        )
        prices = all_results[0]
        ti_results = list(all_results[1 : 3 * n + 1])
        fundamentals_raw = list(all_results[3 * n + 1 : 4 * n + 1])
        news_raw = list(all_results[4 * n + 1 : 5 * n + 1])
    except asyncio.TimeoutError:
        logger.warning("Data assembly timed out after 15s. Proceeding with empty data context.")
        prices = []
        ti_results = [None] * (3 * n)
        fundamentals_raw = [None] * n
        news_raw = [None] * n

    # Build per-asset context
    price_map = {}
    if isinstance(prices, list):
        price_map = {p["symbol"]: p for p in prices}

    assets = []
    for i, sym in enumerate(symbols):
        asset: Dict[str, Any] = {"symbol": sym}

        # Price
        price_data = price_map.get(sym, {})
        asset["price"] = price_data.get("price", 0)
        asset["change_percent"] = price_data.get("changePercent", 0)

        # Multi-Horizon Technicals
        # Order in ti_results is sym0_1h, sym0_1d, sym0_1w, sym1_1h...
        offset = i * 3
        asset["technicals"] = {
            "1h": ti_results[offset] if not isinstance(ti_results[offset], Exception) else {},
            "1d": ti_results[offset+1] if not isinstance(ti_results[offset+1], Exception) else {},
            "1w": ti_results[offset+2] if not isinstance(ti_results[offset+2], Exception) else {}
        }

        # Fundamentals
        fund = fundamentals_raw[i] if i < len(fundamentals_raw) and not isinstance(fundamentals_raw[i], Exception) else None
        asset["fundamentals"] = fund if fund else {}

        # News sentiment
        news = news_raw[i] if i < len(news_raw) and not isinstance(news_raw[i], Exception) else None
        asset["news_sentiment"] = news if news else {}

        assets.append(asset)

    return {"assets": assets, "timestamp": datetime.now(timezone.utc).isoformat()}


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

IMPORTANT: Return ONLY the JSON object. No markdown, no code fences, no explanation outside the JSON."""


async def _call_anthropic(
    symbols: List[str],
    data_context: Dict[str, Any],
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
        async with httpx.AsyncClient(timeout=30.0) as client:
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
            )
            response.raise_for_status()
            result = response.json()

            # Extract the text content from Anthropic's response
            text = result.get("content", [{}])[0].get("text", "")

            # Parse JSON from the response
            try:
                report = json.loads(text)
                return report
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code fences
                import re
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
                if json_match:
                    report = json.loads(json_match.group(1))
                    return report
                logger.error(f"Failed to parse AI response as JSON: {text[:200]}")
                return {"error": "AI returned non-JSON response", "raw_text": text[:500]}

    except httpx.HTTPStatusError as e:
        logger.error(f"Anthropic API error: {e.response.status_code} - {e.response.text[:200]}")
        return _generate_mock_report(symbols, data_context, error_reason=f"Anthropic API Error {e.response.status_code}: {e.response.text[:100]}")
    except Exception as e:
        logger.error(f"Anthropic call failed: {e}")
        return _generate_mock_report(symbols, data_context, error_reason=f"Network/Internal Error: {str(e)}")


def _generate_mock_report(symbols: List[str], data_context: Dict[str, Any], error_reason: str = None) -> Dict[str, Any]:
    """Generate a realistic mock report when no API key is available or the API call fails."""
    assets = []
    for asset_data in data_context.get("assets", []):
        sym = asset_data.get("symbol", "???")
        ti = asset_data.get("technicals", {})
        fund = asset_data.get("fundamentals", {})

        ti_all = asset_data.get("technicals", {})
        ti_1h = ti_all.get("1h", {})
        ti_1d = ti_all.get("1d", {})
        ti_1w = ti_all.get("1w", {})

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
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _report_cache_key(user_id: str, symbols: List[str]) -> str:
    """Generate a deterministic cache key based on user + sorted symbols."""
    sym_hash = hashlib.md5(",".join(sorted(symbols)).encode()).hexdigest()[:12]
    return f"ai_report:{user_id}:{sym_hash}"
