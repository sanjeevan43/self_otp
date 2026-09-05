import asyncio
import asyncpg
from app.config import settings

async def check_webhook_table():
    raw_url = str(settings.DATABASE_URL).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(raw_url, statement_cache_size=0)
    try:
        cols = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'meta_webhook_events'
            ORDER BY ordinal_position;
        """)
        print("\n--- meta_webhook_events ---")
        for c in cols:
            print(f"  {c['column_name']} ({c['data_type']}) nullable={c['is_nullable']}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_webhook_table())
