import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { buildApp } from "../../src/app.js";
import { createTestTenant } from "../helpers/test-tenant.js";
import { prisma } from "../../src/plugins/prisma.js";
import { redis } from "../../src/plugins/redis.js";
import type { FastifyInstance } from "fastify";

describe("OTP Lifecycle Verification (Send, Verify, Attempt Limits, Cooldown)", () => {
  let app: FastifyInstance;

  beforeAll(async () => {
    process.env.WHATSAPP_PROVIDER = "mock";
    app = buildApp();
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
    await prisma.$disconnect().catch(() => {});
    redis.disconnect();
  });

  it("Full OTP lifecycle: send custom code -> verify successfully -> verify status", async () => {
    const tenant = await createTestTenant(app, "lifecycle_t1", 50.0);
    const phone = "+14155550701";
    const customCode = "654321";

    // 1. Send OTP
    const sendResp = await app.inject({
      method: "POST",
      url: "/v1/otp/send",
      headers: { "x-api-key": tenant.rawApiKey },
      payload: {
        phone_number: phone,
        otp: customCode,
        ttl_seconds: 300,
      },
    });

    expect(sendResp.statusCode).toBe(202);
    const sendData = sendResp.json();
    const requestId = sendData.data.request_id;
    expect(requestId).toBeDefined();

    // 2. Verify with correct code
    const verifyResp = await app.inject({
      method: "POST",
      url: "/v1/otp/verify",
      headers: { "x-api-key": tenant.rawApiKey },
      payload: {
        phone_number: phone,
        code: customCode,
      },
    });

    expect(verifyResp.statusCode).toBe(200);
    const verifyData = verifyResp.json();
    expect(verifyData.data.verified).toBe(true);
    expect(verifyData.data.request_id).toBe(requestId);

    // 3. Query status
    const statusResp = await app.inject({
      method: "GET",
      url: `/v1/otp/${requestId}`,
      headers: { "x-api-key": tenant.rawApiKey },
    });

    expect(statusResp.statusCode).toBe(200);
    const statusData = statusResp.json().data;
    expect(statusData.status).toBe("verified");
    expect(statusData.attempts).toBe(1);
    expect(statusData.verified_at).not.toBeNull();
  });

  it("Invalid OTP attempts decrement remaining attempts and exceed limit at max attempts", async () => {
    const tenant = await createTestTenant(app, "lifecycle_t2", 50.0);
    const phone = "+14155550702";
    const customCode = "123456";

    // Send OTP
    const sendResp = await app.inject({
      method: "POST",
      url: "/v1/otp/send",
      headers: { "x-api-key": tenant.rawApiKey },
      payload: {
        phone_number: phone,
        otp: customCode,
        ttl_seconds: 300,
      },
    });
    expect(sendResp.statusCode).toBe(202);

    // Attempt 1: wrong code
    const wrong1 = await app.inject({
      method: "POST",
      url: "/v1/otp/verify",
      headers: { "x-api-key": tenant.rawApiKey },
      payload: {
        phone_number: phone,
        code: "000000",
      },
    });
    expect(wrong1.statusCode).toBe(400);
    expect(wrong1.json().detail.code).toBe("INVALID_OTP");
    expect(wrong1.json().detail.details.remaining_attempts).toBe(2);

    // Attempt 2: wrong code
    const wrong2 = await app.inject({
      method: "POST",
      url: "/v1/otp/verify",
      headers: { "x-api-key": tenant.rawApiKey },
      payload: {
        phone_number: phone,
        code: "000000",
      },
    });
    expect(wrong2.statusCode).toBe(400);
    expect(wrong2.json().detail.details.remaining_attempts).toBe(1);

    // Attempt 3: max attempts reached
    const wrong3 = await app.inject({
      method: "POST",
      url: "/v1/otp/verify",
      headers: { "x-api-key": tenant.rawApiKey },
      payload: {
        phone_number: phone,
        code: "000000",
      },
    });
    expect(wrong3.statusCode).toBe(400);
    expect(wrong3.json().detail.code).toBe("MAX_ATTEMPTS_EXCEEDED");
  });

  it("Cooldown prevents immediate re-send to same phone number", async () => {
    const tenant = await createTestTenant(app, "cooldown_t3", 50.0);
    const phone = "+14155550703";

    // First send -> 202 Accepted
    const resp1 = await app.inject({
      method: "POST",
      url: "/v1/otp/send",
      headers: { "x-api-key": tenant.rawApiKey },
      payload: {
        phone_number: phone,
        ttl_seconds: 300,
      },
    });
    expect(resp1.statusCode).toBe(202);

    // Immediate second send to same phone -> 429 COOLDOWN_ACTIVE
    const resp2 = await app.inject({
      method: "POST",
      url: "/v1/otp/send",
      headers: { "x-api-key": tenant.rawApiKey },
      payload: {
        phone_number: phone,
        ttl_seconds: 300,
      },
    });
    expect(resp2.statusCode).toBe(429);
    expect(resp2.json().detail.code).toBe("COOLDOWN_ACTIVE");
  });
});
