# Complete Architecture & Migration Analysis: Python to TypeScript

This document provides a comprehensive technical audit of the existing Python/FastAPI Meta WhatsApp OTP SaaS backend, mapping all endpoints, data models, state flows, security mechanisms, background queues, and technical debt to prepare for a 100% contract-compatible migration to **Node.js 22+, TypeScript, Fastify, Prisma ORM, and BullMQ**.

---

## 1. Python Architecture Overview

The existing backend is built using:
- **Web Framework:** FastAPI 0.115+ (ASGI on Uvicorn)
- **Database Access:** SQLAlchemy 2.0 (AsyncIO with `asyncpg` for PostgreSQL and `aiosqlite` for local dev/testing)
- **Database Migrations:** Alembic (revision `20260905_e0c35f72c87d_architecture_security_upgrades`)
- **Cache & Ephemeral Store:** Redis 7+ (`aioredis` for rate limits, cooldowns, idempotency, phone block lists)
- **Background Worker:** Celery 5.4+ with Kombu exchanges (`otp`, `webhooks`, `dead_letter`) backed by Redis
- **Security & Cryptography:** 
  - Argon2id password hashing (`passlib[argon2]`)
  - HMAC-SHA256 with server-side `PEPPER` for deterministic phone hashing and timing-safe OTP hashing
  - PyJWT for customer dashboard access and refresh tokens
- **HTTP Client:** HTTPX (async) with mock fallbacks for Meta WhatsApp Cloud API (v20.0)

---

## 2. Existing Endpoints Map

### Customer & Management API (`/v1/...`)
| Method | Route | Auth Guard | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/v1/auth/register` | Public | Registers tenant Customer, User, CustomerUser link, default Application, and funded Wallet. |
| `POST` | `/v1/auth/login` | Public | Verifies Argon2 password hash; issues JWT `access_token` and `refresh_token`. |
| `GET` | `/v1/auth/me` | JWT Bearer | Returns active authenticated user profile and customer ID. |
| `GET` | `/v1/applications` | JWT Bearer | Lists all applications belonging to customer. |
| `POST` | `/v1/applications` | JWT Bearer | Creates isolated project application. |
| `GET` | `/v1/applications/{id}` | JWT Bearer | Retrieves single application; verifies tenant ownership. |
| `DELETE` | `/v1/applications/{id}` | JWT Bearer | Cascading delete of application and child keys. |
| `POST` | `/v1/api-keys` | JWT Bearer | Generates `wotp_live_<hex>` key; stores prefix + SHA-256 hash. |
| `GET` | `/v1/api-keys` | JWT Bearer | Lists active keys for tenant. |
| `DELETE` | `/v1/api-keys/{id}` | JWT Bearer | Revokes key. |
| `GET` | `/v1/wallet` | JWT / API Key | Returns wallet balance and status. |
| `GET` | `/v1/wallet/transactions` | JWT Bearer | Returns paginated immutable transaction ledger. |
| `POST` | `/v1/wallet/topup` | JWT Bearer | Adds balance to customer wallet with atomic lock. |

### Core OTP Public Contract (`/v1/otp/...`)
| Method | Route | Auth Guard | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/v1/otp/send` | `x-api-key` | Enforces 8-tier security & rate limits, atomically debits wallet, creates OTPRequest, and queues async delivery via Celery. |
| `POST` | `/v1/otp/verify` | `x-api-key` | Timing-attack safe comparison against HMAC hash; enforces 3 max attempts and TTL expiry. |
| `POST` | `/v1/otp/resend` | `x-api-key` | Enforces 60-second cooldown per phone; resets OTP expiry (+300s) and triggers re-dispatch. |
| `GET` | `/v1/otp/{request_id}` | `x-api-key` | Queries real-time delivery status (`created`, `queued`, `sent`, `delivered`, `verified`, `expired`, `failed`). |

### Webhooks & Health
| Method | Route | Auth Guard | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/v1/webhooks/meta` | Public | Meta challenge verification (`hub.mode=subscribe` & `hub.verify_token`). |
| `POST` | `/v1/webhooks/meta` | HMAC Signature | Validates `X-Hub-Signature-256`, logs event, queues async processing, auto-refunds on failure. |
| `GET` | `/v1/webhooks/configs`| JWT Bearer | Lists registered customer webhook receivers. |
| `POST` | `/v1/webhooks/configs`| JWT Bearer | Registers new customer webhook receiver. |
| `GET` | `/health` | Public | Health probe returning `{"status": "ok"}`. |

---

## 3. Database Schema & Tables (PostgreSQL)

The database consists of **26 tables** in PostgreSQL:
1. `customers`: Multi-tenant root entity (`id UUID`, `company_name`, `email`, `phone`, `status`, `country_code`, timestamps).
2. `users`: Identity accounts (`id UUID`, `email`, `password_hash`, `first_name`, `last_name`, `status`, `email_verified`).
3. `customer_users`: Many-to-many link between customers and users (`customer_id`, `user_id`, `role: owner/admin/developer/member/billing`).
4. `applications`: Multi-project isolation (`id UUID`, `customer_id`, `name`, `description`, timestamps).
5. `api_keys`: Scoped credentials (`id UUID`, `customer_id`, `application_id`, `name`, `key_prefix`, `key_hash`, `status`, `environment: DEVELOPMENT/PRODUCTION`, `rate_limit_rps`, `expires_at`, `last_used_at`).
6. `wallets`: Prepaid credit ledger (`id UUID`, `customer_id`, `currency`, `balance: NUMERIC/Float`, `status`).
7. `wallet_transactions`: Immutable double-entry records (`id UUID`, `wallet_id`, `transaction_type: credit/debit/refund/adjustment`, `amount`, `balance_before`, `balance_after`, `reference_type`, `reference_id`, `description`).
8. `otp_requests`: Core OTP lifecycle (`id UUID`, `customer_id`, `application_id`, `api_key_id`, `request_id`, `phone_number`, `otp_hash`, `status`, `expires_at`, `attempts`, `max_attempts`, `verified_at`).
9. `otp_verifications`: Audit log of each verification attempt (`id UUID`, `otp_request_id`, `attempt_number`, `result: correct/incorrect/expired/locked`, `ip_address`).
10. `messages`: Provider-agnostic message tracking (`id UUID`, `customer_id`, `otp_request_id`, `provider: meta`, `provider_message_id`, `phone_number`, `message_type`, `status`).
11. `message_events`: Status transitions (`sent`, `delivered`, `read`, `failed`).
12. `meta_accounts`: WhatsApp Business Account (WABA) credentials and bindings.
13. `whatsapp_numbers`: Verified sender phone number IDs.
14. `whatsapp_templates`: Approved Meta message templates (`authentication`, `utility`, `marketing`).
15. `meta_webhook_events`: Raw webhook deduplication and event store.
16. `webhook_configs`: Customer outbound webhook endpoints and secrets.
17. `webhook_events`: Outbound dispatch log with retry states.
18. `idempotency_keys`: Atomic cache for duplicate request suppression (`customer_id`, `application_id`, `key`, `response_code`, `response_body`).
19. `rate_limit_records`: Persistent rate-limiting state.
20. `audit_logs`: Immutable compliance audit trail.
21. `pricing_plans`: Subscription tiers.
22. `pricing_rules`: Dynamic channel and destination pricing.
23. `payment_orders`: Top-up orders.
24. `payments`: Payment gateway transaction proofs.
25. `notifications`: Platform alerts.
26. `alembic_version`: Migration tracking.

---

## 4. Key Flows & State Transitions

### A. Authentication & API Key Flow
```
Client Request
  ├── Dashboard / Admin -> Header: Authorization: Bearer <JWT>
  │     └── Resolves User -> CustomerUser -> Customer
  └── API Integration -> Header: x-api-key: wotp_live_<secret>
        └── Computes SHA-256(raw_key + PEPPER)
        └── Queries api_keys WHERE key_hash = :hash
        └── Resolves: APIKey -> Application -> Customer
        └── Verifies: customer.status == 'active' && key.status == 'active'
```

### B. OTP Dispatch Flow (`POST /v1/otp/send`)
1. **Security Guard Checks (Redis-backed):**
   - Customer blocked check
   - Target phone blocked check
   - Idempotency key lookup (returns cached response if hit)
   - IP rate limit (10 req/min)
   - Phone rate limit (3 req/10 min)
   - Customer rate limit (60 req/min)
   - API key rate limit (configured RPS, default 60 req/sec)
   - Cooldown timer check (60s window per phone number)
2. **Atomic Wallet Debit (PostgreSQL):**
   - Row-level lock (`SELECT ... FOR UPDATE`) on `wallets`
   - Checks `balance >= 1.00`
   - Decrements balance and writes `wallet_transactions` ledger entry
3. **Cryptographic Generation & Storage:**
   - 6-digit cryptographically secure random number (`secrets.choice`)
   - Computes HMAC-SHA256 with `PEPPER`
   - Saves `otp_requests` row with status `CREATED`
4. **Queue Dispatch:**
   - Enqueues job to `otp_messages` queue
   - Worker calls Meta WhatsApp Cloud API (`POST /v20.0/{phone_number_id}/messages`)
   - Updates status to `SENT` or auto-refunds wallet on failure

### C. Meta Webhook & Customer Notification Flow
```
Meta WhatsApp Server
  ↓ POST /v1/webhooks/meta
Validate HMAC Signature (X-Hub-Signature-256)
  ↓
Check duplicate event (meta_webhook_events.meta_message_id)
  ↓
Save raw payload & enqueues to 'webhooks' queue
  ↓
Return HTTP 200 immediately
  ↓
Worker processes status (delivered / read / failed)
  ↓
If 'failed' -> Auto-refund 1.00 credit to customer wallet
  ↓
If customer webhook registered -> Enqueue outbound notification with HMAC signature
```

---

## 5. Technical Debt & Defects in Python Codebase

1. **Floating-point money in Wallet:** `balance: Mapped[float]` in `app/models/wallet.py` uses floating-point numbers instead of PostgreSQL `NUMERIC(14, 4)` / Prisma `Decimal`.
2. **Celery Redis fallback:** In `app/api/v1/otp.py`, Celery failure falls back to synchronous inline HTTP calls, which blocks the event loop.
3. **Mixed Enum Casing:** Some SQLAlchemy enums used lowercase while migrations had uppercase, causing datatype mismatch issues during manual raw SQL inserts.
4. **Inconsistent Request IDs:** Request IDs were generated inconsistently (`req_` vs `wotp_`).

---

## 6. Target TypeScript Architecture (Fastify + Prisma + BullMQ)

The migrated TypeScript platform will follow a modular Clean Architecture:

```
src/
├── app.ts                         # Fastify application factory, plugins, global hooks
├── server.ts                      # Entry point, graceful shutdown, cluster/port binding
│
├── config/
│   ├── env.ts                     # Zod-validated environment schema
│   └── constants.ts              # Business constants (cooldown, TTL, rate limits)
│
├── plugins/
│   ├── prisma.ts                  # Prisma Client connection pool lifecycle
│   ├── redis.ts                   # ioredis client singleton
│   ├── auth.ts                    # JWT and API-key Fastify decorators
│   └── logger.ts                  # Pino logger configuration
│
├── common/
│   ├── errors/                    # Custom AppError classes matching existing codes
│   ├── types/                     # Shared TypeScript interfaces
│   ├── utils/                     # Cryptography (HMAC, Argon2id, secure random)
│   └── constants/                 # Error codes, Enum constants
│
├── modules/
│   ├── auth/                      # routes, controller, service, zod schemas
│   ├── applications/              # project isolation routes & services
│   ├── api-keys/                  # key generation, prefixing, rotation, revocation
│   ├── otp/                       # send, verify, resend, status, cancel, cooldown
│   ├── wallet/                    # atomic debit/credit transactions with Decimal precision
│   ├── payments/                  # topup orders & provider webhook handlers
│   ├── pricing/                   # pricing calculation & tiers
│   ├── usage/                     # delivery analytics & daily aggregation
│   ├── webhooks/                  # Meta inbound webhook & customer outbound dispatcher
│   └── health/                    # /health, /health/live, /health/ready
│
├── providers/
│   ├── whatsapp/
│   │   ├── whatsapp-provider.interface.ts
│   │   └── meta-whatsapp-provider.ts
│   └── payments/
│       └── payment-provider.interface.ts
│
├── queues/
│   ├── queue.ts                   # BullMQ connection & queue definitions
│   ├── otp.queue.ts               # OTP dispatch queue
│   ├── webhook.queue.ts           # Webhook processing queue
│   └── workers/
│       ├── otp.worker.ts          # Processes OTP sending with exponential backoff
│       └── webhook.worker.ts      # Processes Meta events & customer webhook pings
│
├── middleware/
│   ├── request-id.ts              # Fastify hook injecting req.id into context and headers
│   ├── error-handler.ts           # Formats errors into { success: false, error: {...}, request_id }
│   └── rate-limit.ts              # Redis sliding-window rate limiting hook
│
└── routes/
    └── index.ts                   # Mounts /v1 router tree
```

---

## 7. Migration Risks & Mitigation Strategy

| Risk | Mitigation |
| :--- | :--- |
| **Data incompatibility with existing PostgreSQL database** | Map Prisma schema 1:1 with existing Alembic PostgreSQL tables using `@map` and `@@map`. Never run `prisma migrate reset`. |
| **Wallet balance concurrency race conditions** | Use Prisma `$transaction` with interactive transaction isolation and raw row-level locking (`SELECT ... FOR UPDATE`) to preserve atomic debit guarantees. |
| **API response shape mismatch** | Enforce unified Fastify response serializer and Zod response schemas matching exact `{ success, data, request_id }` contracts. |
| **Loss of Celery queue tasks** | Use BullMQ with Redis persistence, configuring dead-letter queues (`dlq`) and exponential backoff retry policies. |
| **Security / Multi-tenancy leak** | Strict Fastify preHandler hook resolving authenticated `customer_id` and `application_id` solely from the database, never from client body/headers. |
