import asyncio
import os
from sqlalchemy import text
from app.core.database import engine

async def check_schema():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users';"))
        columns = [row[0] for row in result]
        print(f"Columns in 'users' table: {columns}")
        if 'dismissed_symbols' not in columns:
            print("MISSING COLUMN: dismissed_symbols")
            print("Schema mutation is intentionally disabled in this helper.")
            print("Use Alembic migrations to add missing columns.")
        else:
            print("Column 'dismissed_symbols' already exists.")

if __name__ == "__main__":
    asyncio.run(check_schema())
