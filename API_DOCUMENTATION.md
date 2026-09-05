# Meta WhatsApp OTP API Platform — Complete API Documentation

> **Version:** 1.0.0  
> **Runtime:** Node.js, Fastify, TypeScript, Prisma, BullMQ, Redis  
> **Database:** PostgreSQL (Supabase) with Row-Level Invariants & Locking  
> **Interactive Swagger UI:** [`/docs`](http://localhost:8000/docs)  
> **OpenAPI 3.0 Specification:** [`/docs/json`](http://localhost:8000/docs/json)  

---

## 1. Overview & Architecture

The Meta WhatsApp OTP SaaS platform provides high-throughput, multi-tenant, financial-grade WhatsApp OTP delivery and verification backed by the official **Meta WhatsApp Cloud API**.

```text
Client Application / Mobile App
               ↓ (X-API-Key / Bearer JWT)
         Fastify Gateway (Port 8000)
        ├── Rate Limiting & Cooldown Engine (Redis)
        ├── Row-Level Wallet Deductions (PostgreSQL)
        └── Asynchronous Queue Dispatch (BullMQ)
               ↓
        BullMQ Background Workers
               ↓
    Meta WhatsApp Cloud API (Graph API v20.0)
```

---

## 2. Base URLs & Environments

| Environment | Base URL | Description |
| :--- | :--- | :--- |
| **Local Machine** | `http://localhost:8000` | Local Fastify development and testing server |
| **Local LAN** | `http://192.168.1.38:8000` | Local network access for mobile devices on same Wi-Fi |
| **Public Live Tunnel** | `https://louise-motherboard-lookup-rebate.trycloudflare.com` | Public HTTPS Cloudflare tunnel for external integrations |
| **Interactive Docs** | `/docs` | Full interactive Swagger UI with execution & pre-filled schemas |
| **OpenAPI Schema** | `/docs/json` | Raw OpenAPI 3.0 JSON specification |

---

## 3. Authentication & Security

The platform supports two complementary security models depending on the operation:

### A. Customer API Key Authentication (`ApiKeyAuth`)
Used by client backend servers, microservices, and mobile backends to dispatch OTPs and query delivery status.
* **Header:** `X-API-Key: wotp_live_<64_hex_chars>`
* **Format:** `wotp_live_` prefix followed by 32 cryptographically secure bytes.
* **Storage:** Raw keys are shown only once upon creation. Keys are stored as SHA-256 hashes in the database.

### B. User Dashboard Bearer JWT Authentication (`BearerAuth`)
Used by developers, owners, and dashboard users to manage application workspaces, rotate API keys, top up credits, and inspect billing transactions.
* **Header:** `Authorization: Bearer <jwt_access_token>`
* **Token Lifetime:** 60 minutes (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`).
* **Refresh Tokens:** Opaque, single-use tokens rotated atomically with **reuse detection** and family revocation.

---

## 4. Rate Limiting, Cooldowns & Abuse Protection

| Protection Tier | Limit | Window | Action on Violation |
| :--- | :--- | :--- | :--- |
| **Phone Number Cooldown** | 1 request | 60 seconds | `429 Too Many Requests` (`COOLDOWN_ACTIVE`) |
| **Phone Target Quota** | 3 requests | 10 minutes | `429 Too Many Requests` (`PHONE_RATE_LIMITED`) |
| **IP Address Limit** | 10 requests | 60 seconds | `429 Too Many Requests` (`IP_RATE_LIMITED`) |
| **Customer Tenant Limit** | 60 requests | 60 seconds | `429 Too Many Requests` (`CUSTOMER_RATE_LIMITED`) |
| **API Key Concurrency** | 20 requests | 1 second | `429 Too Many Requests` (`API_KEY_RATE_LIMITED`) |
| **Max Verification Attempts**| 3 failed codes | Per OTP request | Code is permanently invalidated (`MAX_ATTEMPTS_EXCEEDED`) |

---

## 5. Wallet & Financial Safety Invariants

1. **Credit Cost:** Each OTP request debits `1.0` credit (configurable).
2. **Database CHECK Invariant:** `ALTER TABLE wallets ADD CONSTRAINT chk_wallets_balance_non_negative CHECK (balance >= 0.0000);` strictly enforces non-negative balance at the database engine level.
3. **Atomic Debit:** Debits execute inside isolated database transactions with `SELECT ... FOR UPDATE` row-level locks to prevent double-spending under concurrent workloads.
4. **Insufficient Balance:** If balance is lower than credit cost, the API immediately throws `402 Payment Required` (`INSUFFICIENT_FUNDS`) without altering balance or queuing messages.
5. **Idempotent Refunds:** Delivery failures trigger refunds that are deduplicated by `reference_id` ensuring **at-most-one refund** even under retries.

---

## 6. Complete API Reference

### 6.1 System Health

#### `GET /health`
Basic service liveness check for load balancers.
* **Authentication:** None
* **Response `200 OK`:**
  ```json
  {
    "status": "ok"
  }
  ```

#### `GET /health/live`
Kubernetes liveness probe.
* **Authentication:** None
* **Response `200 OK`:**
  ```json
  {
    "status": "live"
  }
  ```

#### `GET /health/ready`
Deep readiness probe validating active PostgreSQL and Redis connections.
* **Authentication:** None
* **Response `200 OK` (Healthy):**
  ```json
  {
    "status": "ready",
    "database": "connected",
    "redis": "connected"
  }
  ```
* **Response `503 Service Unavailable` (Degraded):**
  ```json
  {
    "status": "unhealthy",
    "database": "disconnected",
    "redis": "connected"
  }
  ```

---

### 6.2 Authentication

#### `POST /v1/auth/register`
Registers a new customer organization, initial owner user, default application workspace, and initializes a credit wallet with 100 free credits.

* **Authentication:** None
* **Request Body (`application/json`):**
  ```json
  {
    "email": "owner@company.com",
    "password": "SecurePassword123!",
    "first_name": "Jane",
    "last_name": "Doe",
    "company_name": "Acme Corp",
    "phone": "+14155552671"
  }
  ```
* **Response `201 Created`:**
  ```json
  {
    "id": "f0b378e7-51f9-4835-9daf-e1c9b38346c4",
    "email": "owner@company.com",
    "first_name": "Jane",
    "last_name": "Doe",
    "phone": "+14155552671",
    "status": "active",
    "customer_id": "3c9bd024-c29d-48aa-b229-2ed5c851c15e",
    "created_at": "2026-09-05T15:55:33.966Z"
  }
  ```

---

#### `POST /v1/auth/login`
Authenticates email and password using Argon2id, returning a short-lived JWT access token and a persisted refresh token.

* **Authentication:** None
* **Request Body (`application/json`):**
  ```json
  {
    "email": "owner@company.com",
    "password": "SecurePassword123!"
  }
  ```
* **Response `200 OK`:**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "88630cafabb9857b7cc0ee3132bc04a0fd39634f29210ded75384a3dcbd161fb557c02a93a6780a1",
    "token_type": "bearer"
  }
  ```

---

#### `POST /v1/auth/refresh`
Rotates the refresh token. The submitted refresh token is immediately revoked and linked to the newly generated replacement token. If a revoked token is reused, the entire token family is invalidated.

* **Authentication:** None
* **Request Body (`application/json`):**
  ```json
  {
    "refresh_token": "88630cafabb9857b7cc0ee3132bc04a0fd39634f29210ded75384a3dcbd161fb557c02a93a6780a1"
  }
  ```
* **Response `200 OK`:**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "e4a2d8102b542036495819ef3879a8bc43d04347714859a19c5c16383bca9082",
    "token_type": "bearer"
  }
  ```
* **Error `401 Unauthorized` (Reused/Revoked token):**
  ```json
  {
    "detail": {
      "code": "REFRESH_TOKEN_REUSED",
      "message": "Refresh token was already used. Session has been revoked for security."
    }
  }
  ```

---

#### `POST /v1/auth/logout`
Revokes the refresh token and all associated sessions for the user.

* **Authentication:** None (or Bearer JWT)
* **Request Body (`application/json`):**
  ```json
  {
    "refresh_token": "e4a2d8102b542036495819ef3879a8bc43d04347714859a19c5c16383bca9082"
  }
  ```
* **Response `200 OK`:**
  ```json
  {
    "message": "Logged out successfully"
  }
  ```

---

#### `GET /v1/auth/me`
Retrieves authenticated user profile and customer organization ID.

* **Authentication:** `BearerAuth` (`Authorization: Bearer <JWT>`)
* **Response `200 OK`:**
  ```json
  {
    "id": "f0b378e7-51f9-4835-9daf-e1c9b38346c4",
    "email": "owner@company.com",
    "first_name": "Jane",
    "last_name": "Doe",
    "phone": "+14155552671",
    "status": "active",
    "customer_id": "3c9bd024-c29d-48aa-b229-2ed5c851c15e",
    "created_at": "2026-09-05T15:55:33.966Z"
  }
  ```

---

### 6.3 Account & Organization

#### `GET /v1/account`
Returns organization profile, tenant ID, currency, and real-time wallet balance.

* **Authentication:** `BearerAuth` OR `ApiKeyAuth`
* **Headers:** `X-API-Key: wotp_live_...` OR `Authorization: Bearer <JWT>`
* **Response `200 OK`:**
  ```json
  {
    "id": "3c9bd024-c29d-48aa-b229-2ed5c851c15e",
    "company_name": "Acme Corp",
    "email": "owner@company.com",
    "phone": "+14155552671",
    "status": "active",
    "country_code": "+91",
    "wallet": {
      "balance": 100,
      "currency": "INR",
      "status": "active"
    },
    "created_at": "2026-09-05T15:55:33.685Z",
    "updated_at": "2026-09-05T15:55:33.685Z"
  }
  ```

---

#### `GET /v1/account/usage`
Returns total, verified, and failed OTP volume metrics for the customer organization.

* **Authentication:** `BearerAuth` OR `ApiKeyAuth`
* **Response `200 OK`:**
  ```json
  {
    "customer_id": "3c9bd024-c29d-48aa-b229-2ed5c851c15e",
    "metrics": {
      "total_otp_requests": 240,
      "verified_otps": 218,
      "failed_otps": 12,
      "pending_or_sent": 10
    }
  }
  ```

---

#### `GET /v1/account/limits`
Returns account rate limits, attempt thresholds, and TTL configurations.

* **Authentication:** `BearerAuth` OR `ApiKeyAuth`
* **Response `200 OK`:**
  ```json
  {
    "api_rate_limit_rps": 20,
    "otp_max_verify_attempts": 3,
    "otp_expiry_seconds": 300,
    "otp_cooldown_seconds": 60,
    "credit_cost_per_otp": 1.0
  }
  ```

---

### 6.4 Applications

#### `GET /v1/applications`
Lists all application workspaces belonging to the customer organization.

* **Authentication:** `BearerAuth`
* **Response `200 OK`:**
  ```json
  [
    {
      "id": "1c0cc1f2-bf4d-4350-8ce1-78804f6a2f0c",
      "customer_id": "3c9bd024-c29d-48aa-b229-2ed5c851c15e",
      "name": "Production Web App",
      "description": "Customer facing authentication portal",
      "created_at": "2026-09-05T15:55:33.551Z",
      "updated_at": "2026-09-05T15:55:33.551Z"
    }
  ]
  ```

---

#### `POST /v1/applications`
Creates a new application workspace for grouping API keys and logs.

* **Authentication:** `BearerAuth`
* **Request Body (`application/json`):**
  ```json
  {
    "name": "iOS Mobile Client",
    "description": "Production iOS application backend"
  }
  ```
* **Response `201 Created`:**
  ```json
  {
    "id": "a93b47c1-23d9-4820-b420-7f284bb10294",
    "customer_id": "3c9bd024-c29d-48aa-b229-2ed5c851c15e",
    "name": "iOS Mobile Client",
    "description": "Production iOS application backend",
    "created_at": "2026-09-05T16:05:12.102Z",
    "updated_at": "2026-09-05T16:05:12.102Z"
  }
  ```

---

#### `DELETE /v1/applications/:app_id`
Permanently deletes an application workspace.

* **Authentication:** `BearerAuth`
* **Response `204 No Content`**

---

### 6.5 API Keys

#### `POST /v1/api-keys`
Generates a new production API key (`wotp_live_...`).  
> **Note:** The `raw_secret_key` is returned **only once** in this response. Store it securely.

* **Authentication:** `BearerAuth`
* **Request Body (`application/json`):**
  ```json
  {
    "application_id": "1c0cc1f2-bf4d-4350-8ce1-78804f6a2f0c",
    "name": "Backend Server Key"
  }
  ```
* **Response `201 Created`:**
  ```json
  {
    "id": "1de8003e-34f2-4a4c-b843-9648a1291f53",
    "customer_id": "3c9bd024-c29d-48aa-b229-2ed5c851c15e",
    "application_id": "1c0cc1f2-bf4d-4350-8ce1-78804f6a2f0c",
    "name": "Backend Server Key",
    "key_prefix": "wotp_live_a0427c",
    "status": "active",
    "expires_at": null,
    "last_used_at": null,
    "created_at": "2026-09-05T15:55:57.609Z",
    "raw_secret_key": "wotp_live_a0427c95d44dd6b2942dc38cd2330fba2d00e942e6fb4f8cd45afbaa3fa2c02c"
  }
  ```

---

#### `GET /v1/api-keys`
Lists active API keys (hashes remain hidden).

* **Authentication:** `BearerAuth`
* **Response `200 OK`:**
  ```json
  [
    {
      "id": "1de8003e-34f2-4a4c-b843-9648a1291f53",
      "customer_id": "3c9bd024-c29d-48aa-b229-2ed5c851c15e",
      "name": "Backend Server Key",
      "key_prefix": "wotp_live_a0427c",
      "status": "active",
      "expires_at": null,
      "last_used_at": "2026-09-05T16:10:00.000Z",
      "created_at": "2026-09-05T15:55:57.609Z"
    }
  ]
  ```

---

#### `DELETE /v1/api-keys/:key_id`
Immediately revokes an API key and purges it from cache.

* **Authentication:** `BearerAuth`
* **Response `204 No Content`**

---

### 6.6 Wallet & Credits

#### `GET /v1/wallet/balance`
Returns real-time credit balance and status.

* **Authentication:** `ApiKeyAuth` OR `BearerAuth`
* **Response `200 OK`:**
  ```json
  {
    "status": "success",
    "data": {
      "balance": 100,
      "currency": "INR",
      "status": "active",
      "updated_at": "2026-09-05T15:55:33.685Z"
    }
  }
  ```

---

#### `POST /v1/wallet/topup`
Adds credits to the organization wallet with an idempotent transaction reference.

* **Authentication:** `BearerAuth`
* **Request Body (`application/json`):**
  ```json
  {
    "amount": 500.0,
    "reference_id": "pay_stripe_order_9812401824"
  }
  ```
* **Response `200 OK`:**
  ```json
  {
    "status": "success",
    "data": {
      "balance": 600,
      "currency": "INR",
      "status": "active",
      "updated_at": "2026-09-05T16:15:22.000Z"
    }
  }
  ```

---

#### `GET /v1/wallet/transactions`
Returns the 100 most recent ledger entries showing balance before, balance after, debits, top-ups, and refunds.

* **Authentication:** `BearerAuth`
* **Response `200 OK`:**
  ```json
  [
    {
      "id": "2b8a7c10-91b4-4e2a-89a1-59124018a102",
      "transaction_type": "topup",
      "amount": 500,
      "balance_before": 100,
      "balance_after": 600,
      "reference_type": "payment",
      "reference_id": "pay_stripe_order_9812401824",
      "description": "Wallet topup via pay_stripe_order_9812401824",
      "created_at": "2026-09-05T16:15:22.000Z"
    },
    {
      "id": "1a7b6c09-80a3-4d19-7890-48013907a091",
      "transaction_type": "debit",
      "amount": -1,
      "balance_before": 101,
      "balance_after": 100,
      "reference_type": "otp_request",
      "reference_id": "req_8f1b2c3d4e5f",
      "description": "Debit for OTP request req_8f1b2c3d4e5f",
      "created_at": "2026-09-05T16:12:05.000Z"
    }
  ]
  ```

---

### 6.7 OTP Core API

#### `POST /v1/otp/send`
Generates an OTP code, debits wallet credits, stores the hash with expiry in Redis, and dispatches the message via Meta WhatsApp Cloud API.

* **Authentication:** `ApiKeyAuth` (`X-API-Key`)
* **Headers:**
  * `X-API-Key: wotp_live_...` (Required)
  * `Idempotency-Key: <unique_client_uuid>` (Optional, prevents double billing on network retry)
* **Request Body (`application/json`):**
  ```json
  {
    "phone_number": "+919876543210",
    "otp": "492810",
    "ttl_seconds": 300,
    "template_name": "otp_auth_v1",
    "language_code": "en_US"
  }
  ```
  * `phone_number`: Must be valid E.164 international format.
  * `otp`: Optional 4-8 digit numeric code. If omitted, a cryptographically secure 6-digit code is generated.
  * `ttl_seconds`: Duration in seconds (60 to 3600, default: `300`).
  * `template_name`: Registered Meta WhatsApp authentication template name.
* **Response `202 Accepted`:**
  ```json
  {
    "status": "success",
    "data": {
      "request_id": "req_a1b2c3d4e5f67890",
      "phone_number": "+91 98765 ****0",
      "delivery_status": "created",
      "expires_at": "2026-09-05T16:25:00.000Z",
      "cost_credits": 1.0
    }
  }
  ```
* **Error `402 Payment Required` (Insufficient Wallet Credits):**
  ```json
  {
    "detail": {
      "code": "INSUFFICIENT_FUNDS",
      "message": "Insufficient wallet balance. Required: 1 credits."
    }
  }
  ```
* **Error `429 Too Many Requests` (Active 60-Second Cooldown):**
  ```json
  {
    "detail": {
      "code": "COOLDOWN_ACTIVE",
      "message": "An OTP was recently requested for this phone number. Please wait 60 seconds."
    }
  }
  ```

---

#### `POST /v1/otp/verify`
Verifies a submitted numeric OTP code against Redis/database, tracking attempt limits.

* **Authentication:** `ApiKeyAuth` (`X-API-Key`)
* **Request Body (`application/json`):**
  ```json
  {
    "phone_number": "+919876543210",
    "code": "492810"
  }
  ```
* **Response `200 OK` (Successful Verification):**
  ```json
  {
    "status": "success",
    "data": {
      "verified": true,
      "phone_number": "+91 98765 ****0",
      "request_id": "req_a1b2c3d4e5f67890",
      "message": "OTP verified successfully."
    }
  }
  ```
* **Response `400 Bad Request` (Invalid Code):**
  ```json
  {
    "detail": {
      "code": "INVALID_OTP",
      "message": "Incorrect OTP code. 2 attempts remaining."
    }
  }
  ```
* **Response `400 Bad Request` (Max Attempts Exceeded):**
  ```json
  {
    "detail": {
      "code": "MAX_ATTEMPTS_EXCEEDED",
      "message": "Maximum verification attempts exceeded. Please request a new OTP."
    }
  }
  ```

---

#### `POST /v1/otp/resend`
Resends a new OTP code for an active request subject to the 60-second cooldown rule. Debits wallet credits.

* **Authentication:** `ApiKeyAuth` (`X-API-Key`)
* **Request Body (`application/json`):**
  ```json
  {
    "request_id": "req_a1b2c3d4e5f67890"
  }
  ```
* **Response `202 Accepted`:**
  ```json
  {
    "status": "success",
    "data": {
      "request_id": "req_a1b2c3d4e5f67890",
      "phone_number": "+91 98765 ****0",
      "delivery_status": "sent",
      "expires_at": "2026-09-05T16:30:00.000Z",
      "cost_credits": 1.0,
      "resend_count": 1
    }
  }
  ```

---

#### `GET /v1/otp/:request_id`
Queries current delivery status, attempt counts, and timestamps for an OTP request.

* **Authentication:** `ApiKeyAuth` (`X-API-Key`)
* **Response `200 OK`:**
  ```json
  {
    "status": "success",
    "data": {
      "request_id": "req_a1b2c3d4e5f67890",
      "phone_number": "+91 98765 ****0",
      "status": "verified",
      "attempts": 1,
      "max_attempts": 3,
      "created_at": "2026-09-05T16:20:00.000Z",
      "expires_at": "2026-09-05T16:25:00.000Z",
      "verified_at": "2026-09-05T16:21:14.000Z"
    }
  }
  ```

---

### 6.8 Webhooks

#### `GET /v1/webhooks/meta`
Responds to the Meta WhatsApp Cloud API verification handshake challenge.

* **Authentication:** None (Meta Challenge)
* **Query Parameters:**
  * `hub.mode`: `subscribe`
  * `hub.verify_token`: Verified against `META_WEBHOOK_VERIFY_TOKEN`
  * `hub.challenge`: Echoed challenge string
* **Response `200 OK`:** `text/plain` containing `hub.challenge`.

---

#### `POST /v1/webhooks/meta`
Ingests delivery receipt statuses (`sent`, `delivered`, `read`, `failed`) from Meta. Deduplicates repeated events and dispatches status updates to the database and BullMQ.

* **Headers:** `X-Hub-Signature-256: sha256=...` (Validated with `META_APP_SECRET`)
* **Response `200 OK`:**
  ```json
  {
    "status": "ok"
  }
  ```

---

## 7. SDK & Integration Code Examples

### JavaScript / TypeScript (Node.js Fetch)

```typescript
// 1. Send WhatsApp OTP
const response = await fetch("https://louise-motherboard-lookup-rebate.trycloudflare.com/v1/otp/send", {
  method: "POST",
  headers: {
    "X-API-Key": "wotp_live_a0427c95d44dd6b2942dc38cd2330fba2d00e942e6fb4f8cd45afbaa3fa2c02c",
    "Content-Type": "application/json",
    "Idempotency-Key": crypto.randomUUID(),
  },
  body: JSON.stringify({
    phone_number: "+919876543210",
    ttl_seconds: 300,
  }),
});

const data = await response.json();
console.log("OTP Request ID:", data.data.request_id);

// 2. Verify WhatsApp OTP
const verifyResponse = await fetch("https://louise-motherboard-lookup-rebate.trycloudflare.com/v1/otp/verify", {
  method: "POST",
  headers: {
    "X-API-Key": "wotp_live_a0427c95d44dd6b2942dc38cd2330fba2d00e942e6fb4f8cd45afbaa3fa2c02c",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    phone_number: "+919876543210",
    code: "492810",
  }),
});

const verifyResult = await verifyResponse.json();
console.log("Verified successfully:", verifyResult.data.verified);
```

---

### Python (`requests`)

```python
import uuid
import requests

API_KEY = "wotp_live_a0427c95d44dd6b2942dc38cd2330fba2d00e942e6fb4f8cd45afbaa3fa2c02c"
BASE_URL = "https://louise-motherboard-lookup-rebate.trycloudflare.com"

# 1. Send OTP
send_res = requests.post(
    f"{BASE_URL}/v1/otp/send",
    headers={
        "X-API-Key": API_KEY,
        "Idempotency-Key": str(uuid.uuid4()),
        "Content-Type": "application/json"
    },
    json={
        "phone_number": "+919876543210",
        "ttl_seconds": 300
    }
)
request_id = send_res.json()["data"]["request_id"]
print(f"Sent OTP! Request ID: {request_id}")

# 2. Verify OTP
verify_res = requests.post(
    f"{BASE_URL}/v1/otp/verify",
    headers={
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    },
    json={
        "phone_number": "+919876543210",
        "code": "492810"
    }
)
print("Verification Result:", verify_res.json())
```

---

### cURL

```bash
# Check Server Health
curl -X GET 'https://louise-motherboard-lookup-rebate.trycloudflare.com/health'

# Send OTP
curl -X POST 'https://louise-motherboard-lookup-rebate.trycloudflare.com/v1/otp/send' \
  -H 'X-API-Key: wotp_live_a0427c95d44dd6b2942dc38cd2330fba2d00e942e6fb4f8cd45afbaa3fa2c02c' \
  -H 'Content-Type: application/json' \
  -d '{
    "phone_number": "+919876543210",
    "ttl_seconds": 300
  }'

# Verify OTP
curl -X POST 'https://louise-motherboard-lookup-rebate.trycloudflare.com/v1/otp/verify' \
  -H 'X-API-Key: wotp_live_a0427c95d44dd6b2942dc38cd2330fba2d00e942e6fb4f8cd45afbaa3fa2c02c' \
  -H 'Content-Type: application/json' \
  -d '{
    "phone_number": "+919876543210",
    "code": "492810"
  }'

# Check Account Balance
curl -X GET 'https://louise-motherboard-lookup-rebate.trycloudflare.com/v1/account' \
  -H 'X-API-Key: wotp_live_a0427c95d44dd6b2942dc38cd2330fba2d00e942e6fb4f8cd45afbaa3fa2c02c'
```

---

## 8. HTTP Error Status Summary

| HTTP Status | Code | Description |
| :--- | :--- | :--- |
| `400 Bad Request` | `INVALID_OTP` / `MAX_ATTEMPTS_EXCEEDED` | Malformed parameters, wrong verification code, or expired request |
| `401 Unauthorized` | `UNAUTHORIZED` / `INVALID_CREDENTIALS` | Invalid API key, expired JWT, or missing credentials |
| `402 Payment Required` | `INSUFFICIENT_FUNDS` | Wallet credit balance is insufficient to dispatch the message |
| `403 Forbidden` | `CUSTOMER_BLOCKED` / `PHONE_BLOCKED` | Account suspended or target phone number blacklisted for abuse |
| `404 Not Found` | `OTP_NOT_FOUND` / `KEY_NOT_FOUND` | Resource ID does not exist or belongs to another customer organization |
| `422 Unprocessable` | `VALIDATION_ERROR` | Schema validation error (missing required fields or invalid phone format) |
| `429 Too Many Requests` | `COOLDOWN_ACTIVE` / `PHONE_RATE_LIMITED` | Cooldown period active (60s) or quota rate limit exceeded |
| `500 Internal Server Error` | `INTERNAL_SERVER_ERROR` | Unexpected application exception |
