import asyncio
import logging
from typing import Dict, Any, List
from app.core.cache import cache_client

logger = logging.getLogger(__name__)

# Smart Data Broker — replaces direct provider imports
from app.services.providers.broker import get_broker
from app.services.finnhub import fetch_news_sentiment  # Sentiment stays direct (only Finnhub provides it)
import random

def apply_dev_shimmer(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Applies a high-precision micro-offset without mutating original cache data."""
    shimmered = []
    for item in items:
        # Create a shallow copy to avoid mutating the cached object
        new_item = item.copy()
        offset = random.choice([-0.0001, -0.00005, 0.00005, 0.0001])
        new_item["price"] = round(new_item.get("price", 0) + offset, 4)
        shimmered.append(new_item)
    return shimmered


async def fetch_watchlist_prices(symbols: List[str]) -> List[Dict[str, Any]]:
    """
    Smart-routed price fetcher.
    Delegates to the DataBroker which scores all providers and picks
    the optimal one per symbol, with automatic fallback on failure.
    """
    if not symbols:
        return []

    broker = get_broker()
    results = await broker.fetch_quotes(symbols)

    # Apply shimmer right before returning to ensure every call is unique
    return apply_dev_shimmer(results)


async def _empty() -> List[Dict[str, Any]]:
    """Helper coroutine that returns an empty list."""
    return []


async def generate_dashboard_pulse() -> Dict[str, Any]:
    """
    The 'God-Tier' Endpoint method.
    Fetches all necessary data for the frontend dashboard concurrently,
    caches the result in Redis for fast repeated access, and returns life-blood data.
    
    Data sources:
      - Stocks (SPY, QQQ, VIX, NVDA, MSFT, TSLA, AMD) → Finnhub
      - Crypto (BTC, ETH) → CoinGecko
      - Sentiment → Finnhub news API
    """
    cache_key = "dashboard_pulse_global"
    cached_data = await cache_client.get(cache_key)
    if cached_data:
        # Crucial: Apply shimmer AFTER cache retrieval so every poll is unique
        cached_data["market_overview"] = apply_dev_shimmer(cached_data["market_overview"])
        return cached_data

    logger.info("Cache miss for Dashboard Pulse. Fetching from Finnhub + CoinGecko...")

    overview_symbols = ["SPY", "QQQ", "BTC", "VIX"]

    # Execute everything in a single batch to prevent API "429 Rate Limit" from concurrent requests
    all_results_tuple = await asyncio.gather(
        fetch_watchlist_prices(overview_symbols),
        fetch_news_sentiment("BTC")
    )
    
    all_prices_list = all_results_tuple[0]
    btc_sentiment = all_results_tuple[1]

    overview_results = all_results_tuple[0]

    payload = {
        "market_overview": overview_results,
        "sentiment": btc_sentiment
    }

    # Save to Redis for 10 seconds (aligned with frontend pollers)
    await cache_client.set(cache_key, payload, expire_seconds=10)

    # Apply shimmer to the final outgoing payload (after cache storage)
    # This ensures even cached responses have a unique pulsatile jitter.
    payload["market_overview"] = apply_dev_shimmer(payload["market_overview"])

    return payload
