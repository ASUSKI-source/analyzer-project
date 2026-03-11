import asyncio
from sqlalchemy import text
from app.core.database import engine

async def main():
    async with engine.begin() as conn:
        await conn.execute(text('DROP TABLE IF EXISTS alembic_version CASCADE'))
        await conn.execute(text('DROP TABLE IF EXISTS portfolios CASCADE'))
        await conn.execute(text('DROP TABLE IF EXISTS users CASCADE'))

asyncio.run(main())
