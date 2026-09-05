# WhatsApp OTP API SaaS Platform

A production-grade, high-performance WhatsApp OTP API SaaS platform built on **Node.js, TypeScript, Fastify, Prisma, and BullMQ** that abstracts Meta's WhatsApp Cloud API complexity behind a clean, developer-friendly REST interface.

---

## Architecture & Technology Stack

- **Runtime & Language**: Node.js 22 (ES Modules) + TypeScript 5.7+ (strict mode)
- **Web Framework**: Fastify 5.x (high performance, schema-driven with Zod)
- **Database & ORM**: PostgreSQL 16 + Prisma ORM 6.4 (introspected models, schema integrity)
- **Caching & Rate Limiting**: Redis 7+ via `ioredis` (sliding window rate limiting, idempotency caches)
- **Asynchronous Task Queue**: BullMQ 5.4+ (decoupled worker processes for OTP delivery & webhook dispatch)
- **Authentication & Security**:
  - Dashboard: JWT with Argon2id password hashing via `@node-rs/argon2`
  - Customer API: `X-API-Key` with SHA-256 hashed storage & pepper
  - Crypto Safeguards: HMAC-SHA256 hashed phone numbers & OTP codes; constant-time string comparisons (`crypto.timingSafeEqual`)
- **Resilience**: Circuit Breaker for Meta Graph API calls; atomic SQL wallet credit debits
- **Infrastructure**: Docker multi-stage builds, Docker Compose (`api`, `worker`, `postgres`, `redis`), Nginx reverse proxy

---

## Architecture Blueprint

```
                                  [ Internet / Clients ]
                                             |
                                             v
                                   +-------------------+
                                   |   Nginx Reverse   | (SSL Termination, Rate Limiting)
                                   |   Proxy / Router  |
                                   +-------------------+
                                             |
                     +-----------------------+-----------------------+
                     |                                               |
                     v                                               v
          +--------------------+                           +--------------------+
          | Fastify API Node 1 |                           | Fastify API Node 2 |
          | (TypeScript)       |                           | (TypeScript)       |
          +--------------------+                           +--------------------+
                     |                                               |
         +-----------+-----------------------+-----------------------+-----------+
         |                                   |                                   |
         v                                   v                                   v
+------------------+                +------------------+                +------------------+
| PostgreSQL 16    |                | Redis 7          |                | BullMQ Workers   |
| (Primary DB &    |                | (Rate Limit, OTP |                | (Independent     |
|  Ledger Storage) |                |  Cache, BullMQ)  |                |  Worker Service) |
+------------------+                +------------------+                +------------------+
                                                                                 |
                                                                                 v
                                                                        +------------------+
                                                                        | Meta WhatsApp    |
                                                                        | Cloud API        |
                                                                        +------------------+
```

---

## Quickstart & Local Development

### 1. Requirements & Setup
Ensure Node.js 22+ and npm are installed.

```bash
# Install dependencies
npm install

# Generate Prisma Client
npm run prisma:generate

# Copy environment settings
cp .env.example .env
```

### 2. Run Test Suite & Quality Checks

```bash
# Run full Vitest suite (integration, concurrency, provider, schema tests)
npm run test

# Type-check TypeScript codebase
npm run typecheck

# Lint codebase
npm run lint

# Build production bundle
npm run build
```

### 3. Run Application Locally

```bash
# Start Fastify API server with live reloading
npm run dev

# In a separate terminal, start the BullMQ worker
npm run worker:dev
```

The API will be available at `http://localhost:8000`.
Health endpoint: `http://localhost:8000/health`.

---

## Customer Integration Flow

### Step 1: Register Account & Create API Key
1. `POST /v1/auth/register` to register your business organization.
2. `POST /v1/auth/login` to receive JWT access token.
3. `POST /v1/api-keys` with header `Authorization: Bearer <token>` to generate an API key (`wotp_live_...`).

### Step 2: Send WhatsApp OTP
`POST /v1/otp/send`
```http
POST /v1/otp/send HTTP/1.1
Host: api.yourdomain.com
X-API-Key: wotp_live_a1b2c3d4e5f678901234567890abcdef
Content-Type: application/json

{
  "phone_number": "+14155552671",
  "ttl_seconds": 300,
  "template_name": "otp_auth_v1"
}
```

Response (`HTTP 202 Accepted`):
```json
{
  "status": "success",
  "data": {
    "otp_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "phone_number": "+1415***2671",
    "delivery_status": "QUEUED",
    "expires_at": "2026-09-03T16:02:14Z",
    "cost_credits": 1.0
  }
}
```

### Step 3: Verify Received OTP
`POST /v1/otp/verify`
```http
POST /v1/otp/verify HTTP/1.1
Host: api.yourdomain.com
X-API-Key: wotp_live_a1b2c3d4e5f678901234567890abcdef
Content-Type: application/json

{
  "phone_number": "+14155552671",
  "code": "839201"
}
```

Response (`HTTP 200 OK`):
```json
{
  "status": "success",
  "data": {
    "verified": true,
    "phone_number": "+1415***2671",
    "verified_at": "2026-09-03T15:58:30Z",
    "message": "OTP verified successfully"
  }
}
```

---

## Production Deployment (Docker Compose)

Deploy using Docker Compose with dedicated `api` and `worker` services:

```bash
# Build and run containers in detached mode
docker compose up -d --build

# View logs of API and Worker
docker compose logs -f api worker
```

---

## Migration History Note
This repository was successfully migrated from an initial Python/FastAPI/Celery architecture to TypeScript/Fastify/BullMQ.
- Historical database migrations are preserved under `migrations/legacy-alembic/`.
- Full migration analysis and contract compatibility verifications are detailed in `migration-analysis.md`, `api-compatibility.md`, and `MIGRATION_REPORT.md`.
