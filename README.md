# WhatsApp OTP API SaaS Platform

A production-ready, high-performance WhatsApp OTP API SaaS platform that abstracts Meta's WhatsApp Cloud API complexity behind a clean, developer-friendly REST interface.

---

## Architecture & Technology Stack

- **Backend Framework**: Python 3.12+, FastAPI, Pydantic v2
- **Database & ORM**: PostgreSQL 16, SQLAlchemy 2.0 (Async), Alembic migrations
- **Caching & Rate Limiting**: Redis 7+ (Sliding Window rate limiting, hashed OTP storage)
- **Asynchronous Task Queue**: Celery + Redis broker
- **Authentication & Security**:
  - Dashboard: JWT with Argon2id password hashing
  - Customer API: `X-API-Key` with SHA-256 hashed storage & pepper
  - Crypto Safeguards: HMAC-SHA256 hashed phone numbers & OTP codes; constant-time string comparisons (`hmac.compare_digest`)
- **Resilience**: Redis-backed Circuit Breaker for Meta Graph API calls; atomic SQL wallet credit debits
- **Infrastructure**: Docker, Docker Compose, Nginx (SSL & rate limiting), GitHub Actions

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
          | FastAPI Node 1     |                           | FastAPI Node 2     |
          | (Uvicorn ASGI)     |                           | (Uvicorn ASGI)     |
          +--------------------+                           +--------------------+
                     |                                               |
         +-----------+-----------------------+-----------------------+-----------+
         |                                   |                                   |
         v                                   v                                   v
+------------------+                +------------------+                +------------------+
| PostgreSQL 16    |                | Redis 7          |                | Celery Workers   |
| (Primary DB &    |                | (Rate Limit, OTP |                | (Meta Dispatch & |
|  Ledger Storage) |                |  Cache, Broker)  |                |  Webhook Engine) |
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
Ensure Python 3.12+ and `uv` are installed.

```bash
# Clone repository
cd /Users/sanjeev/Project/self_otp

# Install dependencies into virtualenv
uv pip install -e ".[dev]"

# Copy environment settings
cp .env.example .env
```

### 2. Run Test Suite & Quality Checks

```bash
# Run pytest with coverage
export PATH="$HOME/.local/bin:$PATH"
uv run pytest --cov=app

# Run Ruff code linter
uv run ruff check .

# Run mypy static type analyzer
uv run mypy app
```

### 3. Run FastAPI Application Locally

```bash
uv run uvicorn app.main:app --reload --port 8000
```
Interactive API Documentation will be available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## Customer Integration Flow

### Step 1: Register Account & Create API Key
1. POST `/v1/auth/register` to register your business organization.
2. POST `/v1/auth/login` to receive JWT access token.
3. POST `/v1/api-keys` with header `Authorization: Bearer <token>` to generate an API key (`wotp_live_...`).

### Step 2: Send WhatsApp OTP
POST `/v1/otp/send`
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

Response (HTTP 202 Accepted):
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
POST `/v1/otp/verify`
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

Response (HTTP 200 OK):
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

## Production Deployment (Docker Compose & VPS)

Deploy to Ubuntu VPS using Docker Compose:

```bash
# Build and run containers in detached mode
docker compose up -d --build

# Run Alembic migrations inside web container
docker compose exec web alembic upgrade head
```
