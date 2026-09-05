import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { buildApp } from "../../src/app.js";
import { prisma } from "../../src/plugins/prisma.js";
import { redis } from "../../src/plugins/redis.js";
import crypto from "node:crypto";
import type { FastifyInstance } from "fastify";

describe("Authentication API Contracts & Flow", () => {
  let app: FastifyInstance;

  beforeAll(async () => {
    app = buildApp();
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
    await prisma.$disconnect().catch(() => {});
    redis.disconnect();
  });

  it("Registers a new business customer, owner user, default app, and wallet", async () => {
    const unique = crypto.randomBytes(6).toString("hex");
    const email = `auth_test_${unique}@example.com`;

    const registerResp = await app.inject({
      method: "POST",
      url: "/v1/auth/register",
      payload: {
        email,
        password: "SuperSecretPassword123!",
        first_name: "John",
        last_name: "Doe",
        phone: "+919876543210",
        company_name: `Acme Corp ${unique}`,
      },
    });

    expect(registerResp.statusCode).toBe(201);
    const body = registerResp.json();
    expect(body.email).toBe(email);
    expect(body.customer_id).toBeDefined();
    expect(body.id).toBeDefined();

    // Verify wallet was initialized with 100 credits
    const wallet = await prisma.wallets.findUnique({
      where: { customer_id: body.customer_id },
    });
    expect(wallet).not.toBeNull();
    expect(Number(wallet?.balance)).toBe(100.0);

    // Verify duplicate registration rejection
    const dupResp = await app.inject({
      method: "POST",
      url: "/v1/auth/register",
      payload: {
        email,
        password: "AnotherPassword123!",
        first_name: "Jane",
        last_name: "Doe",
        company_name: "Duplicate Co",
      },
    });
    expect(dupResp.statusCode).toBe(400);
    expect(dupResp.json().detail.code).toBe("EMAIL_EXISTS");

    // Login with valid credentials
    const loginResp = await app.inject({
      method: "POST",
      url: "/v1/auth/login",
      payload: {
        email,
        password: "SuperSecretPassword123!",
      },
    });
    expect(loginResp.statusCode).toBe(200);
    const tokens = loginResp.json();
    expect(tokens.access_token).toBeDefined();
    expect(tokens.refresh_token).toBeDefined();
    expect(tokens.token_type).toBe("bearer");

    // Login with invalid credentials
    const wrongLogin = await app.inject({
      method: "POST",
      url: "/v1/auth/login",
      payload: {
        email,
        password: "WrongPassword!",
      },
    });
    expect(wrongLogin.statusCode).toBe(401);
    expect(wrongLogin.json().detail.code).toBe("INVALID_CREDENTIALS");

    // GET /me
    const meResp = await app.inject({
      method: "GET",
      url: "/v1/auth/me",
      headers: {
        authorization: `Bearer ${tokens.access_token}`,
      },
    });
    expect(meResp.statusCode).toBe(200);
    expect(meResp.json().email).toBe(email);

    // Refresh token
    const refreshResp = await app.inject({
      method: "POST",
      url: "/v1/auth/refresh",
      payload: {
        refresh_token: tokens.refresh_token,
      },
    });
    expect(refreshResp.statusCode).toBe(200);
    expect(refreshResp.json().access_token).toBeDefined();
  });
});
