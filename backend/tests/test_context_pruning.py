import os

# Ensure settings can initialize during import in isolated test environments.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from app.services.ai_analyzer import _prune_context


def _make_asset(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "news_sentiment": {
            "trending_topics": ["topic1", "topic2", "topic3", "topic4", "topic5"],
        },
        "technicals": {
            "1d": {
                "trend_signal": "Bullish",
                "rsi_14": 55,
                "ema_9": 101,
                "ema_21": 99,
                "bollinger_upper": 120,
                "bollinger_lower": 100,
                "sma_200": 110,
                "sma_50": 105,
            },
            "1h": {
                "trend_signal": "Bullish",
                "rsi_14": 40,
                "ema_9": 102,
                "ema_21": 100,
            },
            "1w": {
                "trend_signal": "Bullish",
                "rsi_14": 60,
                "ema_9": 103,
                "ema_21": 98,
            },
        },
    }


def test_prune_context_truncates_news_and_prunes_secondary_technicals_for_large_watchlists():
    context = {
        "assets": [_make_asset(f"STOCK{i}") for i in range(10)],
        "timestamp": "2024-01-01T00:00:00",
    }

    pruned = _prune_context(context)
    first_asset = pruned["assets"][0]

    assert pruned["watchlist_size"] == 10
    assert pruned["timestamp"] == "2024-01-01T00:00:00"
    assert len(first_asset["news_sentiment"]["trending_topics"]) == 2

    keys_1d = set(first_asset["technicals"]["1d"].keys())
    assert "bollinger_upper" not in keys_1d
    assert "bollinger_lower" not in keys_1d
    assert "sma_200" not in keys_1d
    assert "sma_50" in keys_1d
    assert "ema_9" in keys_1d
    assert "ema_21" in keys_1d
