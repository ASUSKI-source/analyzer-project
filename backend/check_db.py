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
            print("Attempting to add column...")
            try:
                await conn.execute(text("ALTER TABLE users ADD COLUMN dismissed_symbols VARCHAR[] DEFAULT '{}';"))
                await conn.commit()
                print("Successfully added column.")
            except Exception as e:
                print(f"Failed to add column: {e}")
        else:
            print("Column 'dismissed_symbols' already exists.")

if __name__ == "__main__":
    asyncio.run(check_schema())
