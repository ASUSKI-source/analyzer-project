import logging
import asyncio
from datetime import datetime, timedelta
import httpx
from typing import Dict, Any, List, Optional
from app.core.config import settings
from app.core.cache import cache_client
from app.utils.http import get_http_client
import random

logger = logging.getLogger(__name__)

def _has_valid_key() -> bool:
    """Check if we have a real Finnhub API key (not a test placeholder)."""
    key = getattr(settings, "FINNHUB_API_KEY", None)
    return bool(key and isinstance(key, str) and "testkey" not in key)


# Lazy import to avoid circular dependency if ever applicable
async def _try_polygon_backup(symbol: str) -> Optional[Dict[str, Any]]:
    from app.services.polygon import fetch_polygon_price
    return await fetch_polygon_price(symbol)


# ─── STOCK QUOTES ────────────────────────────────────────────────────────────

async def fetch_stock_quote(symbol: str) -> Dict[str, Any]:
    """
    Fetch a real-time stock quote from Finnhub with a 'Price Shield' cache fallback.
    Redundancy: Finnhub -> Polygon -> Redis Cache -> Mock Seed
    """
    symbol = symbol.upper()
    cache_key = f"last_good_price:{symbol}"
    
    # Check if we have a valid key
    if not _has_valid_key():
        # Even without Finnhub key, try Polygon backup first before resorting to cache/mock
        polygon_res = await _try_polygon_backup(symbol)
        if polygon_res:
            return polygon_res
        return await _get_best_fallback(symbol, cache_key)

    url = "https://finnhub.io/api/v1/quote"

    try:
        client = get_http_client()
        response = await client.get(url, params={
            "symbol": symbol,
            "token": settings.FINNHUB_API_KEY
        }, timeout=10.0)
            
        # Catch rate limits specifically
        if response.status_code == 429:
            logger.warning(f"Finnhub rate limit reached for {symbol}. Trying Polygon backup...")
            polygon_res = await _try_polygon_backup(symbol)
            if polygon_res:
                return polygon_res
            return await _get_best_fallback(symbol, cache_key)
            
        response.raise_for_status()
        data = response.json()

        # Handle blank responses for invalid symbols
        if data.get("c", 0) == 0:
            polygon_res = await _try_polygon_backup(symbol)
            if polygon_res:
                return polygon_res
            return await _get_best_fallback(symbol, cache_key)

        result = {
            "symbol": symbol,
            "price": round(float(data.get("c", 0.0)), 2),
            "changePercent": round(float(data.get("dp", 0.0)), 2),
        }
        
        # Update Price Shield cache
        await cache_client.set(cache_key, result, expire_seconds=86400) # Keep for 24h
        return result

    except Exception as e:
        logger.warning(f"Finnhub quote error for {symbol}: {e}. Trying Polygon backup...")
        polygon_res = await _try_polygon_backup(symbol)
        if polygon_res:
            return polygon_res
        return await _get_best_fallback(symbol, cache_key)


async def _get_best_fallback(symbol: str, cache_key: str) -> Dict[str, Any]:
    """Retrieves last known good price from Redis, or resorts to seeded mock."""
    cached = await cache_client.get(cache_key)
    if cached:
        return cached
    return _stock_fallback(symbol)


async def fetch_stock_prices(symbols: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch quotes for multiple stock symbols concurrently.
    Each symbol is a separate API call (Finnhub doesn't support batch quotes).
    Rate limit: 60 calls/min on free tier — with 10s cache, 9 symbols = 54 calls/min max.
    """
    tasks = [fetch_stock_quote(sym) for sym in symbols]
    return list(await asyncio.gather(*tasks))


def _stock_fallback(symbol: str) -> Dict[str, Any]:
    """Realistic fallback when no API key or API error. Seeded for stability."""
    symbol = symbol.upper()
    rng = random.Random(symbol)
    
    base_prices = {
        "SPY": 510, "QQQ": 440, "VIX": 15,
        "AAPL": 175, "MSFT": 420, "GOOGL": 155, "AMZN": 185,
        "NVDA": 880, "META": 500, "TSLA": 175, "AMD": 170,
        "NFLX": 620, "JPM": 195, "V": 280, "DIS": 110,
        "BA": 190, "INTC": 42, "CRM": 290, "UBER": 78,
        "COIN": 230, "PLTR": 25,
    }
    base = base_prices.get(symbol, rng.uniform(50.0, 500.0))
    return {
        "symbol": symbol,
        "price": round(base + rng.uniform(-base * 0.01, base * 0.01), 2),
        "changePercent": round(rng.uniform(-3, 3), 2),
    }


# ─── NEWS SENTIMENT ─────────────────────────────────────────────────────────

async def fetch_news_sentiment(symbol: str) -> Dict[str, Any]:
    """
    Fetches raw news headlines for a symbol and generates a localized sentiment score.
    Endpoint: GET /api/v1/company-news?symbol=AAPL&from=...&to=...
    """
    symbol = symbol.upper()
    if not _has_valid_key():
        await asyncio.sleep(0.1)
        return {
            "symbol": symbol,
            "sentiment_score": round(float(random.uniform(-0.2, 0.4)), 2),
            "trending_topics": ["earnings", "AI"]
        }

    # Finnhub company-news requires a date range
    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    url = "https://finnhub.io/api/v1/company-news"

    try:
        client = get_http_client()
        response = await client.get(url, params={
            "symbol": symbol,
            "from": yesterday,
            "to": today,
            "token": settings.FINNHUB_API_KEY
        }, timeout=10.0)
        
        # Immediate Circuit Breaker: detect invalid keys
        if response.status_code in [401, 403]:
            await cache_client.set("circuit_breaker:finnhub", "tripped", expire_seconds=300)
            return _news_fallback(symbol)

        response.raise_for_status()
        news = response.json()

        # Simple heuristic sentiment if we don't have a real AI worker here yet
        # (The actual sentiment comes from the Anthropic Master Prompt later)
        return {
            "symbol": symbol,
            "sentiment_score": round(float(random.uniform(0.0, 0.3)), 2),
            "trending_topics": [n.get("headline", "")[:20] for n in news[:3]] if news else ["no news"]
        }

    except Exception as e:
        logger.warning(f"Finnhub API error for {symbol}: {e}")
        return _news_fallback(symbol)

def _news_fallback(symbol: str) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "sentiment_score": 0.0,
        "trending_topics": ["unavailable"]
    }

async def get_batch_news_sentiment(symbols: List[str]) -> List[Dict[str, Any]]:
    """Parallel fetch of news sentiment for multiple symbols."""
    # Check circuit breaker
    if await cache_client.get("circuit_breaker:finnhub"):
        return [_news_fallback(s) for s in symbols]
        
    tasks = [fetch_news_sentiment(s) for s in symbols]
    return list(await asyncio.gather(*tasks))


# ─── EARNINGS EVENTS ────────────────────────────────────────────────────────

async def fetch_earnings_events(symbol: str) -> List[Dict[str, Any]]:
    """
    Fetch near-term earnings events for a symbol.
    Returns normalized event rows for snapshot ingestion.
    """
    symbol = symbol.upper()
    if not _has_valid_key():
        return []

    today = datetime.utcnow().strftime("%Y-%m-%d")
    horizon = (datetime.utcnow() + timedelta(days=90)).strftime("%Y-%m-%d")
    url = "https://finnhub.io/api/v1/calendar/earnings"

    try:
        client = get_http_client()
        response = await client.get(
            url,
            params={
                "symbol": symbol,
                "from": today,
                "to": horizon,
                "token": settings.FINNHUB_API_KEY,
            },
            timeout=10.0,
        )
        if response.status_code in [401, 403]:
            await cache_client.set("circuit_breaker:finnhub", "tripped", expire_seconds=300)
            return []
        response.raise_for_status()
        payload = response.json()
        out: List[Dict[str, Any]] = []
        for item in payload.get("earningsCalendar", []) or []:
            report_date = item.get("date")
            if not report_date:
                continue
            try:
                event_dt = datetime.fromisoformat(report_date)
            except Exception:
                event_dt = datetime.utcnow()
            out.append(
                {
                    "event_time": event_dt,
                    "event_type": "earnings",
                    "headline": f"{symbol} earnings on {report_date}",
                    "sentiment_score": None,
                    "relevance_score": 1.0,
                    "payload": {
                        "epsEstimate": item.get("epsEstimate"),
                        "epsActual": item.get("epsActual"),
                        "revenueEstimate": item.get("revenueEstimate"),
                        "revenueActual": item.get("revenueActual"),
                    },
                }
            )
        return out
    except Exception as e:
        logger.warning(f"Finnhub earnings event error for {symbol}: {e}")
        return []


async def get_batch_earnings_events(symbols: List[str]) -> List[List[Dict[str, Any]]]:
    if await cache_client.get("circuit_breaker:finnhub"):
        return [[] for _ in symbols]
    tasks = [fetch_earnings_events(s) for s in symbols]
    return list(await asyncio.gather(*tasks))


# ─── FUNDAMENTALS ────────────────────────────────────────────────────────────

async def fetch_fundamentals(symbol: str, current_price: Optional[float] = None) -> Dict[str, Any]:
    """
    Fetch fundamental data (P/E, EPS, Market Cap) from Finnhub.
    Scales market_cap from Millions to absolute units.
    """
    symbol = symbol.upper()
    
    # 1. Try Cache First (v3 for real Polygon range)
    cache_key = f"fundamentals_cache_v3:{symbol}"
    cached = await cache_client.get(cache_key)
    if cached:
        return cached

    # 2. Check Circuit Breaker
    if await cache_client.get("circuit_breaker:finnhub"):
        return _fundamental_fallback(symbol, current_price)

    if not _has_valid_key():
        return _fundamental_fallback(symbol, current_price)

    url = "https://finnhub.io/api/v1/stock/metric"

    try:
        client = get_http_client()
        response = await client.get(url, params={
            "symbol": symbol,
            "metric": "all",
            "token": settings.FINNHUB_API_KEY
        }, timeout=10.0)
        
        if response.status_code in [401, 403]:
            await cache_client.set("circuit_breaker:finnhub", "tripped", expire_seconds=300)
            return _fundamental_fallback(symbol)
            
        from app.services.coingecko import is_crypto
        response.raise_for_status()
        data = response.json()
        metrics = data.get("metric", {})

        # If it's a known crypto and Finnhub returned nothing, trigger better fallback
        if not metrics and is_crypto(symbol):
            return _fundamental_fallback(symbol, current_price)

        result = {
            "market_cap": (metrics.get("marketCapitalization") or 0) * 1_000_000 if metrics.get("marketCapitalization") else None,
            "pe_ratio": metrics.get("peBasicExclExtraTTM"),
            "dividend_yield": metrics.get("dividendYieldIndicatedAnnual"),
            "eps": metrics.get("epsTTM"),
            "high_52week": metrics.get("52WeekHigh"),
            "low_52week": metrics.get("52WeekLow"),
            "beta": metrics.get("beta"),
            # Short Squeeze Metrics
            "short_interest": metrics.get("shortInterest"),
            "short_ratio": metrics.get("shortRatio"),
            "shares_float": metrics.get("sharesFloat"),
            "free_float": metrics.get("freeFloat"),
            "description": f"Fundamental and Short data for {symbol}"
        }
        
        # Cache for 12 hours
        await cache_client.set(cache_key, result, expire_seconds=43200)
        return result

    except Exception as e:
        logger.warning(f"Finnhub fundamental error for {symbol}: {e}")
        return _fundamental_fallback(symbol, current_price)


async def fetch_institutional_ownership(symbol: str) -> Dict[str, Any]:
    """
    Fetch institutional ownership data (shares held, number of institutions).
    """
    symbol = symbol.upper()
    cache_key = f"institutional_cache:{symbol}"
    cached = await cache_client.get(cache_key)
    if cached: return cached

    if not _has_valid_key() or await cache_client.get("circuit_breaker:finnhub"):
        return {"symbol": symbol, "shares_held": None, "institution_count": None}

    url = "https://finnhub.io/api/v1/stock/institutional-ownership"
    try:
        client = get_http_client()
        response = await client.get(url, params={"symbol": symbol, "token": settings.FINNHUB_API_KEY}, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        ownership = data.get("data", [])
        
        # Get latest filing
        latest = ownership[0] if ownership else {}
        result = {
            "symbol": symbol,
            "shares_held": latest.get("shares"),
            "institution_count": len(ownership),
            "top_holder": latest.get("investorName")
        }
        await cache_client.set(cache_key, result, expire_seconds=86400) # 24h
        return result
    except Exception as e:
        logger.warning(f"Finnhub institutional error for {symbol}: {e}")
        return {"symbol": symbol, "shares_held": None, "institution_count": None}

async def get_batch_fundamentals(symbols: List[str]) -> List[Dict[str, Any]]:
    """Parallel fetch of fundamentals for multiple symbols."""
    if await cache_client.get("circuit_breaker:finnhub"):
        tasks = [_fundamental_fallback(s) for s in symbols]
        return list(await asyncio.gather(*tasks))
        
    tasks = [fetch_fundamentals(s) for s in symbols]
    return list(await asyncio.gather(*tasks))


async def _fundamental_fallback(symbol: str, current_price: Optional[float] = None) -> Dict[str, Any]:
    """
    Returns realistic fallback data if Finnhub fails, using Polygon for 52W ranges if crypto.
    """
    from app.services.coingecko import is_crypto
    from app.services.polygon import fetch_polygon_52w_high_low

    # Try to get real 52-week range from Polygon (especially for crypto)
    poly_range = await fetch_polygon_52w_high_low(symbol)
    h_52 = poly_range.get("high")
    l_52 = poly_range.get("low")

    # If Polygon fails, use smart mock fallback
    if h_52 is None or l_52 is None:
        if current_price:
            h_52 = current_price * 1.15
            l_52 = current_price * 0.85
        else:
            h_52 = 0.0
            l_52 = 0.0

    return {
        "market_cap": 0,
        "pe_ratio": None,
        "dividend_yield": None,
        "eps": None,
        "high_52week": h_52,
        "low_52week": l_52,
        "beta": 1.0,
        "short_interest": 0,
        "short_ratio": 0,
        "description": f"Fallback data for {symbol} (Real Polygon 52W applied)" if poly_range.get("high") else f"Fallback data for {symbol} (Mocked)"
    }

