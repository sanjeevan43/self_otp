import asyncio
import asyncpg
from app.config import settings

async def check_enums():
    raw_url = str(settings.DATABASE_URL).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(raw_url, statement_cache_size=0)
    try:
        enums = await conn.fetch("""
            SELECT t.typname, e.enumlabel
            FROM pg_type t 
            JOIN pg_enum e ON t.oid = e.enumtypid
            ORDER BY t.typname, e.enumsortorder;
        """)
        curr = None
        for r in enums:
            if r["typname"] != curr:
                curr = r["typname"]
                print(f"\nEnum {curr}:")
            print(f"  - {r['enumlabel']}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_enums())
