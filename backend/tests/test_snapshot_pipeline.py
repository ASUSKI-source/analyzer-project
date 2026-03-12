import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from app.services.snapshot_read_service import get_snapshot_bundle_for_symbols
from app.core.celery_app import _parse_cron


def test_parse_cron_fallback_on_invalid():
    schedule = _parse_cron("invalid")
    assert schedule is not None


@pytest.mark.asyncio
async def test_snapshot_bundle_handles_missing_assets(monkeypatch):
    async def fake_get_asset_id_map(db, symbols):
        return {}

    monkeypatch.setattr("app.services.snapshot_read_service.get_asset_id_map", fake_get_asset_id_map)
    out = await get_snapshot_bundle_for_symbols(db=None, symbols=["AAPL"])
    assert "AAPL" in out
    assert out["AAPL"]["asset_type"] == "unknown"
    assert out["AAPL"]["technicals_by_timeframe"] == {}
