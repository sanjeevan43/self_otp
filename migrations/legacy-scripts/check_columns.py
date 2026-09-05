import asyncio
import asyncpg
from app.config import settings

async def check_columns():
    raw_url = str(settings.DATABASE_URL).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(raw_url, statement_cache_size=0)
    try:
        for tbl in ["otp_requests", "wallets", "wallet_transactions", "api_keys", "applications"]:
            cols = await conn.fetch(f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = '{tbl}'
                ORDER BY ordinal_position;
            """)
            print(f"\n--- {tbl} ---")
            for c in cols:
                print(f"  {c['column_name']} ({c['data_type']}) nullable={c['is_nullable']}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_columns())
