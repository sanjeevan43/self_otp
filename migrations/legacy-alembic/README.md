# Legacy Alembic Database Migration History

## Purpose
This directory preserves the historical Alembic database migrations from the initial Python/FastAPI backend of the Meta WhatsApp OTP SaaS platform.

## Why This Is Retained
- The PostgreSQL database was initially provisioned and tracked via Alembic (revision hashes recorded in PostgreSQL `alembic_version` table, e.g., `20260905_e0c35f72c87d`).
- Preserves migration history for audit, historical lineage, rollback reference, and database schema tracking.
- The active runtime has transitioned to TypeScript with Prisma (`prisma/schema.prisma`), but this migration history is retained to maintain provenance and prevent blind deletion of schema evolution history.

## Structure
- `alembic/`: Contains `env.py`, `script.py.mako`, and `versions/` tracking schema changes.
- `alembic.ini`: Configuration used for historical Alembic operations.
