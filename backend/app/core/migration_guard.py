import logging
from typing import Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

REQUIRED_TABLES: List[str] = [
    "assets",
    "asset_candles",
    "asset_technical_snapshots",
    "asset_fundamental_snapshots",
    "asset_event_snapshots",
    "asset_coverage_snapshots",
]

REQUIRED_COLUMNS: Dict[str, List[str]] = {
    "asset_candles": ["asset_id", "timestamp", "timeframe", "open", "high", "low", "close", "volume"],
}


async def assert_required_schema(engine: AsyncEngine) -> None:
    """
    Fail fast on startup if required enterprise migration baseline is missing.
    """
    async with engine.connect() as conn:
        missing_tables: List[str] = []
        for table_name in REQUIRED_TABLES:
            res = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name=:table_name"
                ),
                {"table_name": table_name},
            )
            if res.scalar_one_or_none() is None:
                missing_tables.append(table_name)

        if missing_tables:
            raise RuntimeError(
                f"Required migration baseline is missing tables: {missing_tables}. "
                "Run alembic upgrade head before starting the API."
            )

        for table_name, columns in REQUIRED_COLUMNS.items():
            res = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=:table_name"
                ),
                {"table_name": table_name},
            )
            existing = {row[0] for row in res.all()}
            missing_columns = [c for c in columns if c not in existing]
            if missing_columns:
                raise RuntimeError(
                    f"Required migration baseline is missing columns in {table_name}: {missing_columns}. "
                    "Run alembic upgrade head before starting the API."
                )

    logger.info("Migration baseline validation passed.")
