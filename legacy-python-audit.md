# Legacy Python Backend Audit

This document inventories every Python, Alembic, Celery, and legacy dependency file remaining in the repository, analyzing its functionality, its TypeScript replacement, whether it is safe to remove, and the recommended action.

---

## 1. Application Runtime Code (`app/`)

| File Path | Description / Responsibility | TypeScript Replacement | Safe to Delete? | Recommended Action |
| :--- | :--- | :--- | :--- | :--- |
| `app/__init__.py` | Package marker | N/A (ES Modules) | Yes | **DELETE** |
| `app/main.py` | FastAPI application entrypoint, CORS, exception handlers, router inclusion | `src/app.ts`, `src/server.ts` | Yes | **DELETE** |
| `app/config.py` | Pydantic BaseSettings loading `.env` | `src/config/env.ts` (Zod validation) | Yes | **DELETE** |
| `app/database.py` | SQLAlchemy async engine & session factory | `src/plugins/prisma.ts` (PrismaClient) | Yes | **DELETE** |
| `app/redis.py` | aioredis connection manager | `src/plugins/redis.ts` (ioredis singleton) | Yes | **DELETE** |

### `app/core/` (Core Utilities & Security)
| File Path | Description / Responsibility | TypeScript Replacement | Safe to Delete? | Recommended Action |
| :--- | :--- | :--- | :--- | :--- |
| `app/core/__init__.py` | Package marker | N/A | Yes | **DELETE** |
| `app/core/security.py` | Argon2 password hashing, JWT encode/decode, API key generator | `src/common/utils/crypto.ts`, `src/plugins/auth.ts` | Yes | **DELETE** |
| `app/core/hashing.py` | Phone & OTP HMAC-SHA256, timingSafeEqual, phone masking | `src/common/utils/crypto.ts` | Yes | **DELETE** |
| `app/core/rate_limit.py` | Redis sliding window rate limiter & phone/customer blocking | `src/middleware/rate-limit.ts` | Yes | **DELETE** |
| `app/core/idempotency.py` | Idempotency response caching in Redis/DB | `src/middleware/idempotency.ts` | Yes | **DELETE** |
| `app/core/circuit_breaker.py` | Meta API circuit breaker | `src/providers/whatsapp/meta-whatsapp-provider.ts` | Yes | **DELETE** |

### `app/models/` (SQLAlchemy ORM Models)
| File Path | Description / Responsibility | TypeScript Replacement | Safe to Delete? | Recommended Action |
| :--- | :--- | :--- | :--- | :--- |
| `app/models/__init__.py` | Exports all SQLAlchemy models | `prisma/schema.prisma` (@prisma/client) | Yes | **DELETE** |
| `app/models/base.py` | UUIDMixin & TimestampMixin | `prisma/schema.prisma` | Yes | **DELETE** |
| `app/models/enums.py` | SQLAlchemy Python Enum declarations | Introspected enums in `prisma/schema.prisma` | Yes | **DELETE** |
| `app/models/customer.py` | Customer & CustomerUser models | `prisma.customers`, `prisma.customer_users` | Yes | **DELETE** |
| `app/models/user.py` | User model | `prisma.users` | Yes | **DELETE** |
| `app/models/application.py` | Application model | `prisma.applications` | Yes | **DELETE** |
| `app/models/api_key.py` | APIKey model | `prisma.api_keys` | Yes | **DELETE** |
| `app/models/wallet.py` | Wallet, WalletTransaction, Pricing models | `prisma.wallets`, `prisma.wallet_transactions`, etc. | Yes | **DELETE** |
| `app/models/otp.py` | OTPRequest, OTPVerification models | `prisma.otp_requests`, `prisma.otp_verifications` | Yes | **DELETE** |
| `app/models/messaging.py` | Message, MessageEvent, WebhookEvent models | `prisma.messages`, `prisma.message_events`, `prisma.webhook_events` | Yes | **DELETE** |
| `app/models/meta.py` | MetaAccount, WhatsAppNumber models | `prisma.meta_accounts`, `prisma.whatsapp_numbers` | Yes | **DELETE** |
| `app/models/notification.py` | Notification model | `prisma.notifications` | Yes | **DELETE** |
| `app/models/request_log.py` | ApiRequestLog model | `prisma.api_request_logs` | Yes | **DELETE** |
| `app/models/security_ops.py` | IdempotencyKey model | `prisma.idempotency_keys` | Yes | **DELETE** |
| `app/models/webhook.py` | WebhookConfig model | `prisma.webhook_configs` | Yes | **DELETE** |

### `app/schemas/` (Pydantic Schemas)
| File Path | Description / Responsibility | TypeScript Replacement | Safe to Delete? | Recommended Action |
| :--- | :--- | :--- | :--- | :--- |
| `app/schemas/__init__.py` | Package marker | N/A | Yes | **DELETE** |
| `app/schemas/auth.py` | Register, Login, Token, UserResponse schemas | Zod schemas in `src/modules/auth/auth.routes.ts` | Yes | **DELETE** |
| `app/schemas/otp.py` | OTPSend, OTPVerify, OTPResend schemas | Zod schemas in `src/modules/otp/otp.routes.ts` | Yes | **DELETE** |
| `app/schemas/wallet.py` | WalletBalance, Topup, Transaction schemas | Zod schemas in `src/modules/wallet/wallet.routes.ts` | Yes | **DELETE** |
| `app/schemas/application.py` | ApplicationCreate, ApplicationResponse schemas | Zod schemas in `src/modules/applications/applications.routes.ts` | Yes | **DELETE** |
| `app/schemas/api_key.py` | APIKeyCreate, APIKeyResponse schemas | Zod schemas in `src/modules/api-keys/api-keys.routes.ts` | Yes | **DELETE** |
| `app/schemas/notification.py` | Notification schemas | N/A | Yes | **DELETE** |
| `app/schemas/team.py` | Team member schemas | N/A | Yes | **DELETE** |
| `app/schemas/usage.py` | Usage metric schemas | N/A | Yes | **DELETE** |
| `app/schemas/webhook.py` | WebhookConfig schemas | N/A | Yes | **DELETE** |
| `app/schemas/audit_log.py` | AuditLog schemas | N/A | Yes | **DELETE** |

### `app/services/` (Business Services & Providers)
| File Path | Description / Responsibility | TypeScript Replacement | Safe to Delete? | Recommended Action |
| :--- | :--- | :--- | :--- | :--- |
| `app/services/__init__.py` | Package marker | N/A | Yes | **DELETE** |
| `app/services/otp_service.py` | OTP code generation, cooldown, verify, status | `src/modules/otp/otp.service.ts` | Yes | **DELETE** |
| `app/services/wallet_service.py` | Row-locked debit, refund, topup | `src/modules/wallet/wallet.service.ts` | Yes | **DELETE** |
| `app/services/whatsapp_service.py` | Dispatcher to WhatsApp provider | `src/providers/whatsapp/provider-factory.ts` | Yes | **DELETE** |
| `app/services/meta_service.py` | Meta Cloud API dispatcher | `src/providers/whatsapp/meta-whatsapp-provider.ts` | Yes | **DELETE** |
| `app/services/worker_monitoring.py` | Worker monitoring metrics | BullMQ built-in metrics and events | Yes | **DELETE** |
| `app/services/providers/base.py` | WhatsAppProvider abstract class | `src/providers/whatsapp/whatsapp-provider.interface.ts` | Yes | **DELETE** |
| `app/services/providers/meta_provider.py` | Meta Cloud API HTTP provider | `src/providers/whatsapp/meta-whatsapp-provider.ts` | Yes | **DELETE** |
| `app/services/providers/__init__.py` | Package marker | N/A | Yes | **DELETE** |

### `app/tasks/` (Celery Tasks)
| File Path | Description / Responsibility | TypeScript Replacement | Safe to Delete? | Recommended Action |
| :--- | :--- | :--- | :--- | :--- |
| `app/tasks/__init__.py` | Package marker | N/A | Yes | **DELETE** |
| `app/tasks/celery_app.py` | Celery application instance & configuration | `src/queues/queue.ts` (BullMQ Queue) | Yes | **DELETE** |
| `app/tasks/otp_tasks.py` | Celery async worker tasks (send, retry, dlq, webhook) | `src/queues/workers/otp.worker.ts`, `src/queues/workers/webhook.worker.ts` | Yes | **DELETE** |

### `app/api/` (FastAPI Routers & Dependencies)
| File Path | Description / Responsibility | TypeScript Replacement | Safe to Delete? | Recommended Action |
| :--- | :--- | :--- | :--- | :--- |
| `app/api/__init__.py` | Package marker | N/A | Yes | **DELETE** |
| `app/api/deps.py` | Dependency injection (JWT auth, API key auth, get_db) | `src/plugins/auth.ts`, `src/plugins/prisma.ts` | Yes | **DELETE** |
| `app/api/v1/__init__.py` | Aggregates all v1 routers | `src/app.ts` route registration | Yes | **DELETE** |
| `app/api/v1/auth.py` | `/v1/auth` endpoints | `src/modules/auth/auth.routes.ts` | Yes | **DELETE** |
| `app/api/v1/otp.py` | `/v1/otp` endpoints (send, verify, resend, status) | `src/modules/otp/otp.routes.ts` | Yes | **DELETE** |
| `app/api/v1/wallet.py` | `/v1/wallet` endpoints (balance, topup, transactions) | `src/modules/wallet/wallet.routes.ts` | Yes | **DELETE** |
| `app/api/v1/applications.py`| `/v1/applications` endpoints | `src/modules/applications/applications.routes.ts` | Yes | **DELETE** |
| `app/api/v1/api_keys.py` | `/v1/api-keys` endpoints | `src/modules/api-keys/api-keys.routes.ts` | Yes | **DELETE** |
| `app/api/v1/webhooks.py` | `/v1/webhooks` endpoints (Meta GET & POST) | `src/modules/webhooks/webhooks.routes.ts` | Yes | **DELETE** |
| `app/api/v1/billing.py` | `/v1/billing` endpoints | Integrated into wallet | Yes | **DELETE** |
| `app/api/v1/team.py` | `/v1/team` endpoints | Handled via customer users | Yes | **DELETE** |
| `app/api/v1/notifications.py`| `/v1/notifications` endpoints | N/A | Yes | **DELETE** |
| `app/api/v1/integrations.py` | `/v1/integrations` endpoints | N/A | Yes | **DELETE** |
| `app/api/v1/logs.py` | `/v1/logs` endpoints | N/A | Yes | **DELETE** |
| `app/api/v1/monitoring.py` | `/v1/monitoring` endpoints | `src/modules/health/health.routes.ts` | Yes | **DELETE** |

---

## 2. Database Migrations (`alembic/` and `alembic.ini`)

| File Path | Description / Responsibility | Safe to Delete? | Recommended Action |
| :--- | :--- | :--- | :--- |
| `alembic.ini` | Alembic configuration file | **DO NOT DELETE BLINDLY** | **MIGRATE / PRESERVE** to `migrations/legacy-alembic/alembic.ini` |
| `alembic/env.py` | Alembic runner environment | **DO NOT DELETE BLINDLY** | **MIGRATE / PRESERVE** to `migrations/legacy-alembic/env.py` |
| `alembic/script.py.mako` | Migration template | **DO NOT DELETE BLINDLY** | **MIGRATE / PRESERVE** to `migrations/legacy-alembic/script.py.mako` |
| `alembic/versions/*` | Historical migration versions (e.g. `20260905_e0c35f72c87d_architecture_security_upgrades.py`) | **DO NOT DELETE BLINDLY** | **MIGRATE / PRESERVE** to `migrations/legacy-alembic/versions/` |

**Decision on Alembic**:
Per Instruction 2 ("DO NOT delete database migrations: Determine whether Alembic history is still required for existing deployments, rollback/history, database version tracking"), Alembic history is permanently archived into `migrations/legacy-alembic/`. It serves as the authoritative historical record of database migrations and revision hashes (recorded in the PostgreSQL `alembic_version` table) without polluting the active TypeScript application directory.

---

## 3. Legacy Tests (`tests/*.py`)

| File Path | Description / Responsibility | TypeScript Replacement | Safe to Delete? | Recommended Action |
| :--- | :--- | :--- | :--- | :--- |
| `tests/conftest.py` | pytest fixtures | `tests/helpers/test-tenant.ts` | Yes | **DELETE** |
| `tests/test_api_keys.py` | API key tests | `tests/integration/tenant-isolation.test.ts` | Yes | **DELETE** |
| `tests/test_auth.py` | Auth tests | `tests/integration/auth-api.test.ts` | Yes | **DELETE** |
| `tests/test_database_models.py` | Model integrity tests | `tests/migration/schema-integrity.test.ts` | Yes | **DELETE** |
| `tests/test_health.py` | Health check tests | `tests/migration/schema-integrity.test.ts` | Yes | **DELETE** |
| `tests/test_meta_provider.py` | Meta provider tests | `tests/providers/whatsapp-provider.test.ts` | Yes | **DELETE** |
| `tests/test_otp.py` | OTP tests | `tests/integration/otp-lifecycle.test.ts` | Yes | **DELETE** |
| `tests/test_p0_verification.py` | Isolation & concurrency tests | `tests/integration/tenant-isolation.test.ts`, `tests/concurrency/wallet-concurrency.test.ts` | Yes | **DELETE** |
| `tests/test_queue_worker.py` | Celery worker tests | `tests/integration/webhook-idempotency.test.ts` | Yes | **DELETE** |
| `tests/test_rate_limiting.py` | Rate limit tests | `tests/integration/otp-lifecycle.test.ts` | Yes | **DELETE** |
| `tests/test_security.py` | Security hashing tests | `tests/providers/whatsapp-provider.test.ts` | Yes | **DELETE** |
| `tests/test_wallet.py` | Wallet tests | `tests/concurrency/wallet-concurrency.test.ts` | Yes | **DELETE** |
| `tests/test_webhooks.py` | Webhook tests | `tests/integration/webhook-idempotency.test.ts` | Yes | **DELETE** |

---

## 4. Scripts & Scratch Files

| File Path | Description / Responsibility | TypeScript Status / Relevance | Recommended Action |
| :--- | :--- | :--- | :--- |
| `serve_docs.py` | Local HTTP doc server | Swagger/OpenAPI docs served via Fastify or static | **DELETE** |
| `scripts/*.py` | Ad-hoc setup and DB inspection scripts | All schema verified and introspected via Prisma | **ARCHIVE / DELETE** |
| `scratch/*.py` | Scratch exploration scripts | Replaced by Prisma automated tests | **DELETE** |

---

## 5. Python Dependency Files

| File Path | Description / Responsibility | Safe to Delete? | Recommended Action |
| :--- | :--- | :--- | :--- |
| `pyproject.toml` | Python project & dependency configuration | Yes (Node.js uses `package.json`) | **DELETE** |

---

## 6. Infrastructure & Deployment Files

| File Path | Description / Responsibility | Recommended Action |
| :--- | :--- | :--- |
| `Dockerfile` | Python 3.12 Dockerfile with Uvicorn | **REPLACE** with multi-stage Node.js 22 TypeScript Dockerfile |
| `docker-compose.yml` | Services with uvicorn and celery worker | **REPLACE** with Node.js Fastify API + BullMQ Worker services |
| `.env.example` | Contains Celery & asyncpg variables | **REPLACE** with TypeScript environment variables |
