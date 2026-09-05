import asyncio
import asyncpg
from app.config import settings

async def check_tables():
    raw_url = str(settings.DATABASE_URL).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(raw_url, statement_cache_size=0)
    try:
        rows = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        print("Existing tables in Supabase public schema:")
        for r in rows:
            print(" -", r["table_name"])
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_tables())
