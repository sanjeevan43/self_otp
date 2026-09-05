import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { buildApp } from "../../src/app.js";
import { createTestTenant } from "../helpers/test-tenant.js";
import { prisma } from "../../src/plugins/prisma.js";
import { redis } from "../../src/plugins/redis.js";
import type { FastifyInstance } from "fastify";

describe("Tenant Isolation Verification", () => {
  let app: FastifyInstance;

  beforeAll(async () => {
    app = buildApp();
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
    await prisma.$disconnect();
    redis.disconnect();
  });

  it("Tenant 2 cannot query or access Tenant 1's OTP request", async () => {
    const tenant1 = await createTestTenant(app, "tenant1", 100.0);
    const tenant2 = await createTestTenant(app, "tenant2", 100.0);

    // Tenant 1 sends OTP
    const sendResp = await app.inject({
      method: "POST",
      url: "/v1/otp/send",
      headers: {
        "x-api-key": tenant1.rawApiKey,
      },
      payload: {
        phone_number: "+14155550101",
        ttl_seconds: 300,
      },
    });

    expect(sendResp.statusCode).toBe(202);
    const sendData = sendResp.json();
    const requestId = sendData.data.request_id;
    expect(requestId).toBeDefined();

    // Tenant 1 can view status
    const statusResp1 = await app.inject({
      method: "GET",
      url: `/v1/otp/${requestId}`,
      headers: {
        "x-api-key": tenant1.rawApiKey,
      },
    });
    expect(statusResp1.statusCode).toBe(200);

    // Tenant 2 attempts to view Tenant 1's request -> must return 404
    const statusResp2 = await app.inject({
      method: "GET",
      url: `/v1/otp/${requestId}`,
      headers: {
        "x-api-key": tenant2.rawApiKey,
      },
    });
    expect(statusResp2.statusCode).toBe(404);
    expect(statusResp2.json().detail.code).toBe("OTP_NOT_FOUND");
  });

  it("Tenant 2 cannot access or delete Tenant 1's applications", async () => {
    const tenant1 = await createTestTenant(app, "app_t1", 50.0);
    const tenant2 = await createTestTenant(app, "app_t2", 50.0);

    // Tenant 2 tries to GET Tenant 1's application
    const getResp = await app.inject({
      method: "GET",
      url: `/v1/applications/${tenant1.applicationId}`,
      headers: {
        authorization: `Bearer ${tenant2.accessToken}`,
      },
    });
    expect(getResp.statusCode).toBe(404);

    // Tenant 2 tries to DELETE Tenant 1's application
    const deleteResp = await app.inject({
      method: "DELETE",
      url: `/v1/applications/${tenant1.applicationId}`,
      headers: {
        authorization: `Bearer ${tenant2.accessToken}`,
      },
    });
    expect(deleteResp.statusCode).toBe(404);

    // Verify application still exists in DB
    const appStillExists = await prisma.applications.findUnique({
      where: { id: tenant1.applicationId },
    });
    expect(appStillExists).not.toBeNull();
  });

  it("Tenant 2 cannot revoke Tenant 1's API key", async () => {
    const tenant1 = await createTestTenant(app, "key_t1", 50.0);
    const tenant2 = await createTestTenant(app, "key_t2", 50.0);

    const revokeResp = await app.inject({
      method: "DELETE",
      url: `/v1/api-keys/${tenant1.apiKeyId}`,
      headers: {
        authorization: `Bearer ${tenant2.accessToken}`,
      },
    });
    expect(revokeResp.statusCode).toBe(404);

    // Verify API key is still active
    const keyRecord = await prisma.api_keys.findUnique({
      where: { id: tenant1.apiKeyId },
    });
    expect(keyRecord?.status).toBe("active");
  });
});
