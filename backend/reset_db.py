import asyncio
import os
from sqlalchemy import text
from app.core.database import engine

async def main():
    if os.getenv("ALLOW_SCHEMA_RESET", "").lower() != "true":
        raise RuntimeError(
            "Refusing to reset schema. Set ALLOW_SCHEMA_RESET=true for intentional local-only resets."
        )
    async with engine.begin() as conn:
        await conn.execute(text('DROP TABLE IF EXISTS alembic_version CASCADE'))
        await conn.execute(text('DROP TABLE IF EXISTS portfolios CASCADE'))
        await conn.execute(text('DROP TABLE IF EXISTS users CASCADE'))

asyncio.run(main())
