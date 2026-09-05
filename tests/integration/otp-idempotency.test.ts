import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { buildApp } from "../../src/app.js";
import { createTestTenant } from "../helpers/test-tenant.js";
import { WalletService } from "../../src/modules/wallet/wallet.service.js";
import { prisma } from "../../src/plugins/prisma.js";
import { redis } from "../../src/plugins/redis.js";
import crypto from "node:crypto";
import type { FastifyInstance } from "fastify";

describe("OTP Send Idempotency Verification", () => {
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

  it("Repeated OTP send with same Idempotency-Key returns cached response without double billing", async () => {
    const tenant = await createTestTenant(app, "idempotency_tenant", 50.0);
    const idempotencyKey = `idem_${crypto.randomBytes(8).toString("hex")}`;
    const payload = {
      phone_number: "+14155550301",
      ttl_seconds: 300,
    };

    // First submission
    const resp1 = await app.inject({
      method: "POST",
      url: "/v1/otp/send",
      headers: {
        "x-api-key": tenant.rawApiKey,
        "idempotency-key": idempotencyKey,
      },
      payload,
    });

    expect(resp1.statusCode).toBe(202);
    const body1 = resp1.json();
    const requestId1 = body1.data.request_id;
    expect(requestId1).toBeDefined();

    // Check balance after first send -> should be 49.0 (50 - 1.0)
    const bal1 = await WalletService.getBalance(tenant.customerId);
    expect(bal1.balance).toBe(49.0);

    // Second submission with exact same idempotency key
    const resp2 = await app.inject({
      method: "POST",
      url: "/v1/otp/send",
      headers: {
        "x-api-key": tenant.rawApiKey,
        "idempotency-key": idempotencyKey,
      },
      payload,
    });

    // Should return 200 or 202 with identical body and request_id
    expect([200, 202]).toContain(resp2.statusCode);
    const body2 = resp2.json();
    expect(body2.data.request_id).toBe(requestId1);

    // Balance after second send MUST STILL BE 49.0 (NO DUPLICATE BILLING)
    const bal2 = await WalletService.getBalance(tenant.customerId);
    expect(bal2.balance).toBe(49.0);

    // Idempotency table contains the record
    const idemRecord = await prisma.idempotency_keys.findFirst({
      where: {
        application_id: tenant.applicationId,
        idempotency_key: idempotencyKey,
      },
    });
    expect(idemRecord).not.toBeNull();
  });
});
