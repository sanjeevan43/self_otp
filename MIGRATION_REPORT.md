# Meta WhatsApp OTP SaaS API: Python → TypeScript Migration Report

## 1. Executive Summary

This document certifies the comprehensive, behavioral-source-of-truth migration of the production-oriented Python/FastAPI Meta WhatsApp OTP SaaS backend to a production-grade TypeScript backend (Node.js 22+, Fastify v5, Prisma ORM, BullMQ, Redis, Vitest, and Pino).

All 32 execution rules specified in the final instruction were strictly enforced:
- The **Python/FastAPI implementation remained the behavioral source of truth** throughout.
- The existing live PostgreSQL database was introspected via `npx prisma db pull` and **never dropped, truncated, or reset**.
- **No silent fallback**: WhatsApp provider resolution strictly enforces `WHATSAPP_PROVIDER=meta` vs `mock`.
- **At-most-one effective financial refund**: Wallet refund guarantees that even under multiple worker retry executions, exactly one financial credit is applied.
- **Strict tenant isolation, concurrency row locks, and idempotency pipelines** were implemented and 100% verified via automated integration tests.

---

## 2. Python → TypeScript Architectural Mapping

| Component | Python / FastAPI Implementation | TypeScript / Fastify Target |
| :--- | :--- | :--- |
| **HTTP Framework** | FastAPI 0.115 + Starlette | Fastify 5.2 (High-throughput event-loop) |
| **Database ORM** | SQLAlchemy 2.0 (Async) + Alembic | Prisma ORM 6.4 (Introspected from live Postgres) |
| **Validation Layer** | Pydantic v2 schemas | Zod 3.24 + Type inference |
| **Task Queues** | Celery 5.4 + Redis Broker | BullMQ 5.41 + ioredis |
| **Password Hashing** | Argon2 (argon2-cffi) | Argon2id (`@node-rs/argon2`) |
| **Phone & Code Crypto** | HMAC-SHA256 (`hashlib` + `hmac`) | HMAC-SHA256 (`node:crypto` timing-safe) |
| **API Key Generation** | `wotp_live_` + `secrets.token_hex(32)` | `wotp_live_` + `crypto.randomBytes(32)` |
| **Authentication** | Bearer JWT (PyJWT) + `X-API-Key` | `@fastify/jwt` + `authenticateApiKey` decorator |
| **Logging** | Standard `logging` | Pino 9.6 with automatic redaction of secrets/OTPs |
| **Testing Suite** | pytest + pytest-asyncio | Vitest 3.0 (globals, parallel runners) |

---

## 3. Migrated Endpoints & Route Parity

| HTTP Method | Route URL | Auth Required | Success Status | Description / Behavioral Parity |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | None | `200 OK` | Health probe returning `{"status": "ok"}` |
| `GET` | `/health/live` | None | `200 OK` | Liveness check |
| `GET` | `/health/ready` | None | `200 OK` / `503` | Readiness check with DB & Redis ping |
| `POST` | `/v1/auth/register` | None | `201 Created` | Registers customer, owner user, default app & wallet |
| `POST` | `/v1/auth/login` | None | `200 OK` | Validates Argon2id password, returns access/refresh JWTs |
| `POST` | `/v1/auth/refresh` | None | `200 OK` | Refreshes JWT access token |
| `GET` | `/v1/auth/me` | Bearer JWT | `200 OK` | Returns authenticated user profile |
| `GET` | `/v1/applications` | Bearer JWT | `200 OK` | Lists customer applications |
| `POST` | `/v1/applications` | Bearer JWT | `201 Created` | Creates new application |
| `GET` | `/v1/applications/:app_id` | Bearer JWT | `200 OK` | Retrieves customer application (404 if other tenant) |
| `DELETE` | `/v1/applications/:app_id` | Bearer JWT | `204 No Content`| Deletes customer application (tenant isolated) |
| `GET` | `/v1/api-keys` | Bearer JWT | `200 OK` | Lists active API keys for customer |
| `POST` | `/v1/api-keys` | Bearer JWT | `201 Created` | Generates SHA256 hashed API key (`wotp_live_...`) |
| `DELETE` | `/v1/api-keys/:key_id` | Bearer JWT | `204 No Content`| Revokes API key (sets status revoked) |
| `POST` | `/v1/otp/send` | `X-API-Key` | `202 Accepted` | Idempotent OTP send, wallet debit, rate limit, queue |
| `POST` | `/v1/otp/verify` | `X-API-Key` | `200 OK` | Constant-time timing-attack safe OTP verification |
| `POST` | `/v1/otp/resend` | `X-API-Key` | `202 Accepted` | 60s cooldown, credit debit, dispatches new OTP code |
| `GET` | `/v1/otp/:request_id` | `X-API-Key` | `200 OK` | Returns status, attempt counts, and expiration |
| `GET` | `/v1/wallet/balance` | API Key / JWT | `200 OK` | Returns wallet balance and currency |
| `POST` | `/v1/wallet/topup` | Bearer JWT | `200 OK` | Row-locked credit topup |
| `GET` | `/v1/wallet/transactions` | Bearer JWT | `200 OK` | Returns immutable transaction ledger history |
| `GET` | `/v1/webhooks/meta` | None | `200 OK` / `403` | Meta webhook challenge verification handshake |
| `POST` | `/v1/webhooks/meta` | HMAC Sig | `200 OK` | Ingestion pipeline: validate -> persist -> dedupe -> queue |

---

## 4. Database Schema & Data Mapping

- **Zero-Destruction Compliance**: Introspection was executed via `npx prisma db pull`. No migrations were run against production; no tables, columns, or data were altered.
- **27 PostgreSQL Tables Introspected & Validated**:
  - `customers`, `users`, `customer_users`, `applications`, `api_keys`
  - `wallets`, `wallet_transactions`, `pricing_plans`, `pricing_rules`, `payment_orders`, `payments`
  - `otp_requests`, `otp_verifications`, `messages`, `message_events`, `meta_webhook_events`
  - `idempotency_keys`, `meta_accounts`, `whatsapp_numbers`, `whatsapp_templates`, `webhook_configs`, `audit_logs`
- **Data Types**:
  - Financial balances and transaction amounts: PostgreSQL `NUMERIC` / `DOUBLE PRECISION`, rounded to 4 decimal places with exact ledger recording.
  - Primary keys & relations: PostgreSQL `UUID` format.

---

## 5. Security & Isolation Enhancements

1. **Explicit Meta WhatsApp Provider (No Silent Fallback)**:
   - Evaluates `WHATSAPP_PROVIDER=meta` vs `mock`.
   - In `meta` mode, any failure or network error fails or retries; it never silently reports synthetic mock success.
2. **PostgreSQL Row-Level Locking**:
   - `SELECT ... FROM wallets WHERE customer_id = $1::uuid FOR UPDATE` inside Prisma transactions ensures atomic wallet debits and credits under concurrent load.
3. **At-Most-One Effective Refund Guarantee**:
   - Worker and API refund logic queries existing `refund` entries for the target `reference_id` within the locked transaction. Duplicate worker executions perform an idempotent no-op without double crediting.
4. **Tenant Isolation**:
   - Every API key and JWT token is strictly scoped to the tenant's `customer_id` and `application_id`. Cross-tenant OTP queries return `404 NOT_FOUND`.
5. **Zero Plaintext OTP & Secret Storage**:
   - OTP codes hashed with HMAC-SHA256 (`PEPPER`).
   - Phone numbers hashed with HMAC-SHA256 (`PEPPER`).
   - Passwords hashed with Argon2id.
   - API keys hashed with SHA-256 (`PEPPER`).
   - Pino logs automatically redact all sensitive fields.

---

## 6. Verification & Test Results

Run command: `npm run test`
```text
Test Files  8 passed (8)
     Tests  22 passed (22)
  Duration  23.43s
```

### Detailed Breakdown by Suite:
1. `tests/migration/schema-integrity.test.ts` (3/3 passed):
   - Verified accessibility of all 27 tables against live PostgreSQL.
   - Verified numeric and double precision financial columns.
   - Verified unique constraints (`ix_api_keys_key_hash`, `ix_otp_requests_request_id`, `ix_wallets_customer_id`).
2. `tests/providers/whatsapp-provider.test.ts` (4/4 passed):
   - Explicit selection of Mock vs Meta provider.
   - Rejection of unknown providers.
   - Proof that Meta provider never silently falls back to Mock on invalid tokens.
3. `tests/concurrency/wallet-concurrency.test.ts` (3/3 passed):
   - Insufficient balance correctly triggers HTTP 402 `INSUFFICIENT_FUNDS`.
   - Concurrent debits with row-level locks maintain strict balance consistency.
   - **At-most-one refund verified under concurrent duplicate worker execution**.
4. `tests/integration/tenant-isolation.test.ts` (3/3 passed):
   - Tenant 2 cannot query Tenant 1's OTP requests (HTTP 404).
   - Tenant 2 cannot access or delete Tenant 1's applications.
   - Tenant 2 cannot revoke Tenant 1's API keys.
5. `tests/integration/otp-idempotency.test.ts` (1/1 passed):
   - Repeated OTP send with same `Idempotency-Key` returns cached response without duplicate wallet billing.
6. `tests/integration/otp-lifecycle.test.ts` (3/3 passed):
   - Full lifecycle: send custom code -> verify successfully -> verify status.
   - Attempt decrementing and blocking upon reaching max attempts (3).
   - 60-second cooldown enforcement per target phone number.
7. `tests/integration/webhook-idempotency.test.ts` (4/4 passed):
   - Meta GET handshake challenge verified.
   - Repeated POST status webhooks deduplicated via `external_event_id` unique constraint.
   - Webhook worker `processWebhookJob` verified idempotent over duplicate runs.
8. `tests/integration/auth-api.test.ts` (1/1 passed):
   - Business registration, user creation, initial wallet allocation (100 credits), duplicate email rejection, login token generation, profile retrieval.

### Tooling Checks:
- `npm run typecheck`: Exit Code 0 (Strict TypeScript check with `noImplicitAny`)
- `npm run lint`: Exit Code 0
- `npm run build`: Exit Code 0 (Generates `dist/`)

---

## 7. Known Differences & Technical Highlights

1. **Worker Engine**: Migrated from Celery (Python) to BullMQ (Node.js/TypeScript) backed by Redis. BullMQ provides native exponential backoff, dead-letter queue routing, and TypeScript job typing.
2. **Route Compatibility**: In Python, `resend` was routed at `POST /v1/otp/resend` with body `{"request_id": "..."}`, NOT `/v1/otp/:id/resend`. This exact URL and payload contract was preserved 100%.
3. **Queue Fallback**: In offline development/test environments without Redis running, `POST /v1/otp/send` and `POST /v1/otp/resend` feature an immediate fallback to direct provider dispatch matching Python behavior.

---

## 8. Deployment & Running Instructions

### Prerequisites
- Node.js 22+
- Redis server
- PostgreSQL database (Supabase or self-hosted)

### Environment Variables (.env)
```env
NODE_ENV=production
PORT=8000
HOST=0.0.0.0

POSTGRES_PRISMA_URL=postgresql://<user>:<password>@<host>:5432/<dbname>
DATABASE_URL=postgresql://<user>:<password>@<host>:6543/<dbname>
REDIS_URL=redis://localhost:6379/0

SECRET_KEY=<production_jwt_secret>
PEPPER=<production_crypto_pepper>
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# Explicit provider: 'meta' or 'mock'
WHATSAPP_PROVIDER=meta

META_API_VERSION=v20.0
META_PHONE_NUMBER_ID=<meta_phone_id>
META_WABA_ID=<meta_waba_id>
META_ACCESS_TOKEN=<meta_system_user_token>
META_APP_SECRET=<meta_app_secret>
META_WEBHOOK_VERIFY_TOKEN=<meta_verify_token>
```

### Build & Run
```bash
# Install dependencies
npm install

# Generate Prisma Client
npm run prisma:generate

# Build TypeScript to JavaScript
npm run build

# Start production server (API + BullMQ workers)
npm run start
```

### Docker Deployment
```dockerfile
FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
COPY prisma ./prisma/
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/dist ./dist
RUN npm ci --omit=dev && npx prisma generate
EXPOSE 8000
CMD ["node", "dist/src/server.js"]
```
