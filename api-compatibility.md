# API Compatibility Specification: Python FastAPI vs TypeScript Fastify

This document serves as the **behavioral and contract compatibility baseline** for migrating the Meta WhatsApp OTP SaaS platform from Python to TypeScript. 

Per the Migration Source of Truth, **all existing Python endpoint URLs, HTTP methods, status codes, request schemas, response envelopes, error codes, and side-effects are preserved exactly**.

---

## Global Response Contract

### Success Envelope (OTP & Wallet Endpoints)
```json
{
  "status": "success",
  "data": { ... }
}
```

### Standard Entity Response (Auth, Applications, API Keys)
Returns the created or retrieved JSON entity directly (with `id`, timestamps, and relation references).

### Standard Error Envelope
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description"
  }
}
```
*(FastAPI `HTTPException(detail={"code": ..., "message": ...})` returns `{"detail": {"code": ..., "message": ...}}`; TypeScript Fastify error handler preserves `{ error: { code, message } }` with backward compatibility).*

---

## Complete Endpoint Compatibility Matrix

| Python Endpoint | Method | TypeScript Target | Auth Guard | Request Body / Params | Response Data | Status Codes | Side Effects |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `/v1/auth/register` | `POST` | `/v1/auth/register` | Public | `UserCreate`<br>`company_name`, `email`, `password`, `first_name?`, `last_name?`, `phone?` | `UserResponse`<br>`id`, `email`, `status`, `customer_id`, `created_at` | `201 Created`<br>`400 Bad Request` (`EMAIL_EXISTS`) | Creates `Customer`, `User` (Argon2id), `CustomerUser` (`OWNER`), `Application` (Default), `Wallet` (100.0 initial credits). |
| `/v1/auth/login` | `POST` | `/v1/auth/login` | Public | `UserLogin`<br>`email`, `password` | `Token`<br>`access_token`, `refresh_token`, `token_type: "bearer"` | `200 OK`<br>`401 Unauthorized` (`INVALID_CREDENTIALS`) | Verifies Argon2id password hash; generates JWTs containing `sub: user.id` and `customer_id`. |
| `/v1/auth/me` | `GET` | `/v1/auth/me` | Bearer JWT | None | `UserResponse`<br>`id`, `email`, `customer_id`, `role` | `200 OK`<br>`401 Unauthorized` | Resolves user profile and linked customer. |
| `/v1/applications` | `GET` | `/v1/applications` | Bearer JWT | None | `ApplicationResponse[]`<br>`id`, `customer_id`, `name`, `description`, `created_at` | `200 OK`<br>`401 Unauthorized` | Filters `applications` by authenticated `customer.id`. |
| `/v1/applications` | `POST` | `/v1/applications` | Bearer JWT | `ApplicationCreate`<br>`name`, `description?` | `ApplicationResponse` | `201 Created`<br>`401 Unauthorized` | Creates new isolated project environment. |
| `/v1/applications/{app_id}`| `GET` | `/v1/applications/:app_id`| Bearer JWT | Path: `app_id` (UUID) | `ApplicationResponse` | `200 OK`<br>`404 Not Found` | Verifies tenant ownership (`customer_id == customer.id`). |
| `/v1/applications/{app_id}`| `DELETE`| `/v1/applications/:app_id`| Bearer JWT| Path: `app_id` (UUID) | None | `204 No Content`<br>`404 Not Found` | Cascading delete of application and child API keys. |
| `/v1/api-keys` | `POST` | `/v1/api-keys` | Bearer JWT | `APIKeyCreate`<br>`name`, `application_id` | `APIKeyCreatedResponse`<br>`id`, `key_prefix`, `raw_secret_key`, `created_at` | `201 Created`<br>`401 Unauthorized`<br>`404 Not Found` | Generates `wotp_live_<32_bytes_hex>`, calculates SHA-256 with `PEPPER`, stores hash and prefix. Returns raw secret ONCE. |
| `/v1/api-keys` | `GET` | `/v1/api-keys` | Bearer JWT | None | `APIKeyResponse[]` (active keys only) | `200 OK`<br>`401 Unauthorized` | Returns prefix and metadata. Raw secret is NEVER returned. |
| `/v1/api-keys/{key_id}` | `DELETE`| `/v1/api-keys/:key_id`| Bearer JWT | Path: `key_id` (UUID) | None | `204 No Content`<br>`404 Not Found` (`KEY_NOT_FOUND`) | Sets key status to `revoked`. |
| `/v1/otp/send` | `POST` | `/v1/otp/send` | `x-api-key` | `OTPSendRequest`<br>`phone_number` (E.164), `otp?`, `ttl_seconds?` (300), `template_name?`, `language_code?`<br>Header: `idempotency-key?` | `OTPSendResponse`<br>`status: "success"`, `data: { request_id, phone_number (masked), delivery_status, expires_at, cost_credits: 1.0 }` | `202 Accepted`<br>`400 Validation Error`<br>`402 Payment Required`<br>`403 Forbidden` (`CUSTOMER_BLOCKED`, `PHONE_BLOCKED`)<br>`429 Too Many Requests` (`IP_RATE_LIMITED`, `PHONE_RATE_LIMITED`, `CUSTOMER_RATE_LIMITED`, `API_KEY_RATE_LIMITED`, `COOLDOWN_ACTIVE`) | 1. Idempotency cache check<br>2. Rate limits & block checks<br>3. Atomic wallet debit (`FOR UPDATE`)<br>4. Cryptographic random 6-digit OTP<br>5. HMAC-SHA256 hash storage<br>6. BullMQ `otp_messages` queue dispatch<br>7. 60s phone cooldown set in Redis |
| `/v1/otp/verify` | `POST` | `/v1/otp/verify` | `x-api-key` | `OTPVerifyRequest`<br>`phone_number` (E.164), `code` (numeric) | `OTPVerifyResponse`<br>`status: "success"`, `data: { verified: true, request_id, phone_number, verified_at, message }` | `200 OK`<br>`400 Bad Request` (`INVALID_CODE`, `ALREADY_VERIFIED`, `OTP_EXPIRED`, `MAX_ATTEMPTS_EXCEEDED`)<br>`404 Not Found` (`OTP_NOT_FOUND`) | Constant-time HMAC comparison, atomically increments verification attempts, locks after max attempts. |
| `/v1/otp/resend` | `POST` | `/v1/otp/resend` | `x-api-key` | `OTPResendRequest`<br>`request_id` | `OTPResendResponse`<br>`status: "success"`, `data: { request_id, phone_number, delivery_status, expires_at, cost_credits, resend_count }` | `202 Accepted`<br>`400 Bad Request` (`ALREADY_VERIFIED`, `OTP_EXPIRED`)<br>`404 Not Found` (`OTP_NOT_FOUND`)<br>`429 Too Many Requests` (`COOLDOWN_ACTIVE`) | Enforces 60-second cooldown window, generates new 6-digit code, resets TTL (+300s), debits wallet, queues dispatch. |
| `/v1/otp/{request_id}` | `GET` | `/v1/otp/:request_id` | `x-api-key` | Path: `request_id` | `OTPStatusResponse`<br>`status: "success"`, `data: { request_id, phone_number, status, attempts, max_attempts, expires_at, created_at, verified_at }` | `200 OK`<br>`404 Not Found` (`OTP_NOT_FOUND`) | Scoped strictly to authenticated `application.id`. |
| `/v1/wallet` | `GET` | `/v1/wallet` | Bearer JWT / `x-api-key` | None | `WalletBalanceResponse`<br>`status: "success"`, `data: { balance, currency, status, updated_at }` | `200 OK`<br>`401 Unauthorized` | Queries customer wallet. |
| `/v1/wallet/transactions` | `GET` | `/v1/wallet/transactions` | Bearer JWT | Query: `limit?`, `offset?` | `WalletTransactionResponse[]`<br>`id`, `transaction_type`, `amount`, `balance_before`, `balance_after`, `reference_type`, `description`, `created_at` | `200 OK`<br>`401 Unauthorized` | Immutable audit ledger history. |
| `/v1/wallet/topup` | `POST` | `/v1/wallet/topup` | Bearer JWT | `WalletTopupRequest`<br>`amount`, `reference_id` | `WalletBalanceResponse` | `200 OK`<br>`400 Bad Request` | Atomic wallet credit with row lock. |
| `/v1/webhooks/meta` | `GET` | `/v1/webhooks/meta` | Public | Query: `hub.mode`, `hub.verify_token`, `hub.challenge` | Plain text: `hub.challenge` | `200 OK`<br>`403 Forbidden` | Meta Webhook registration challenge handshake. |
| `/v1/webhooks/meta` | `POST` | `/v1/webhooks/meta` | Signature | Raw payload; Header: `x-hub-signature-256` | `{"status": "received"}` | `200 OK`<br>`401 Unauthorized` (`INVALID_SIGNATURE`) | 1. Validates HMAC signature<br>2. Deduplicates by event ID<br>3. Saves raw event<br>4. Queues BullMQ job<br>5. Returns 200 immediately |
| `/v1/webhooks/configs` | `GET` | `/v1/webhooks/configs` | Bearer JWT | None | `WebhookResponse[]` | `200 OK` | Lists customer notification webhooks. |
| `/v1/webhooks/configs` | `POST` | `/v1/webhooks/configs` | Bearer JWT | `WebhookCreate`<br>`url`, `application_id`, `subscribed_events` | `WebhookResponse` | `201 Created` | Registers customer outbound webhook receiver. |
| `/health` | `GET` | `/health` | Public | None | `{"status": "ok"}` | `200 OK` | Liveness probe. |

---

## Preserved Error Codes

| Error Code | HTTP Status | Trigger Condition |
| :--- | :--- | :--- |
| `EMAIL_EXISTS` | `400 Bad Request` | Customer registration with already registered email. |
| `INVALID_CREDENTIALS` | `401 Unauthorized` | Login failure (email not found or Argon2 mismatch). |
| `UNAUTHORIZED` | `401 Unauthorized` | Missing, malformed, or expired JWT / API key. |
| `FORBIDDEN` | `403 Forbidden` | Inactive/suspended customer or cross-tenant access attempt. |
| `CUSTOMER_BLOCKED` | `403 Forbidden` | Customer flagged for abuse in Redis. |
| `PHONE_BLOCKED` | `403 Forbidden` | Recipient phone flagged for abuse or excessive failures. |
| `IP_RATE_LIMITED` | `429 Too Many Requests` | More than 10 OTP requests from IP in 60 seconds. |
| `PHONE_RATE_LIMITED` | `429 Too Many Requests` | More than 3 OTP requests to phone in 10 minutes. |
| `CUSTOMER_RATE_LIMITED`| `429 Too Many Requests` | More than 60 OTP requests for customer in 60 seconds. |
| `API_KEY_RATE_LIMITED` | `429 Too Many Requests` | Key exceeded configured RPS limit. |
| `COOLDOWN_ACTIVE` | `429 Too Many Requests` | New OTP requested to same phone within 60 seconds. |
| `INSUFFICIENT_FUNDS` | `402 Payment Required` | Wallet balance below credit cost (1.00). |
| `OTP_NOT_FOUND` | `404 Not Found` | Request ID does not exist in application scope. |
| `ALREADY_VERIFIED` | `400 Bad Request` | Attempting to verify or resend an already verified OTP. |
| `OTP_EXPIRED` | `400 Bad Request` | Attempting to verify or resend after `expires_at`. |
| `INVALID_CODE` | `400 Bad Request` | HMAC mismatch on submitted verification code. |
| `MAX_ATTEMPTS_EXCEEDED`| `400 Bad Request` | Reached maximum verification attempts (3). |
| `INVALID_SIGNATURE` | `401 Unauthorized` | Meta webhook HMAC-SHA256 signature validation failed. |
| `KEY_NOT_FOUND` | `404 Not Found` | API key revocation target does not exist. |
