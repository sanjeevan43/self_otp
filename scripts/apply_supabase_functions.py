import asyncio
import asyncpg
from app.config import settings

async def apply_sql():
    with open("supabase/migrations/20260905000000_init_schema.sql", "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Convert SQLAlchemy asyncpg URL to pure asyncpg URL (remove +asyncpg)
    raw_url = str(settings.DATABASE_URL).replace("postgresql+asyncpg://", "postgresql://")
    print(f"Connecting to Supabase PostgreSQL at {raw_url.split('@')[-1]}...")

    conn = await asyncpg.connect(raw_url, statement_cache_size=0)
    try:
        print("Executing schema and stored procedures...")
        await conn.execute(sql_content)
        print("SUCCESS! All Supabase tables, indexes, and stored procedures applied successfully!")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(apply_sql())
