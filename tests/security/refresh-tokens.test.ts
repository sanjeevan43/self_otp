import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { buildApp } from "../../src/app.js";
import { prisma } from "../../src/plugins/prisma.js";
import { hashPassword, hashRefreshToken } from "../../src/common/utils/crypto.js";
import crypto from "node:crypto";

describe("Phase 2.1 — JWT Refresh-Token Security & Rotation", () => {
  const app = buildApp();
  let testUser: { id: string; email: string };
  let testCustomer: { id: string };

  beforeEach(async () => {
    // Clean up test users created in these tests
    const uniqueEmail = `test_refresh_${Date.now()}_${crypto.randomInt(1000, 9999)}@example.com`;
    const hashedPassword = await hashPassword("SecurePassword123!");

    testCustomer = await prisma.customers.create({
      data: {
        company_name: "Refresh Security Test Org",
        email: uniqueEmail,
        status: "active",
        country_code: "+91",
      },
    });

    testUser = await prisma.users.create({
      data: {
        email: uniqueEmail,
        password_hash: hashedPassword,
        first_name: "Security",
        last_name: "Tester",
        status: "active",
      },
    });

    await prisma.customer_users.create({
      data: {
        customer_id: testCustomer.id,
        user_id: testUser.id,
        role: "owner",
      },
    });
  });

  afterAll(async () => {
    await app.close();
  });

  it("Login issues a cryptographically secure, hashed refresh token and never stores plaintext", async () => {
    const res = await app.inject({
      method: "POST",
      url: "/v1/auth/login",
      payload: {
        email: testUser.email,
        password: "SecurePassword123!",
      },
    });

    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.access_token).toBeDefined();
    expect(body.refresh_token).toBeDefined();

    // Verify token hash is stored, never plaintext
    const rawToken = body.refresh_token;
    const computedHash = hashRefreshToken(rawToken);

    const record = await prisma.refresh_tokens.findUnique({
      where: { token_hash: computedHash },
    });

    expect(record).not.toBeNull();
    expect(record!.user_id).toBe(testUser.id);
    expect(record!.revoked_at).toBeNull();
    expect(record!.replaced_by_token_id).toBeNull();
    expect(record!.token_hash).not.toContain(rawToken); // Plaintext is never stored
  });

  it("POST /v1/auth/refresh rotates the refresh token and marks previous token as revoked with replacement link", async () => {
    // 1. Login
    const loginRes = await app.inject({
      method: "POST",
      url: "/v1/auth/login",
      payload: {
        email: testUser.email,
        password: "SecurePassword123!",
      },
    });
    const { refresh_token: token1 } = loginRes.json();

    // 2. Rotate token via /refresh
    const refreshRes = await app.inject({
      method: "POST",
      url: "/v1/auth/refresh",
      payload: { refresh_token: token1 },
    });

    expect(refreshRes.statusCode).toBe(200);
    const refreshBody = refreshRes.json();
    const token2 = refreshBody.refresh_token;

    expect(token2).toBeDefined();
    expect(token2).not.toBe(token1);

    // Verify token1 is now revoked and links to token2
    const token1Hash = hashRefreshToken(token1);
    const token2Hash = hashRefreshToken(token2);

    const record1 = await prisma.refresh_tokens.findUnique({
      where: { token_hash: token1Hash },
    });
    const record2 = await prisma.refresh_tokens.findUnique({
      where: { token_hash: token2Hash },
    });

    expect(record1!.revoked_at).not.toBeNull();
    expect(record1!.replaced_by_token_id).toBe(record2!.id);
    expect(record2!.revoked_at).toBeNull();
    expect(record2!.family_id).toBe(record1!.family_id); // In same token family
  });

  it("Reusing an old rotated refresh token triggers reuse detection and revokes the entire token family", async () => {
    // 1. Initial login -> token1
    const loginRes = await app.inject({
      method: "POST",
      url: "/v1/auth/login",
      payload: {
        email: testUser.email,
        password: "SecurePassword123!",
      },
    });
    const { refresh_token: token1 } = loginRes.json();

    // 2. Legitimate user rotates token1 -> token2
    const refreshRes1 = await app.inject({
      method: "POST",
      url: "/v1/auth/refresh",
      payload: { refresh_token: token1 },
    });
    expect(refreshRes1.statusCode).toBe(200);
    const { refresh_token: token2 } = refreshRes1.json();

    // 3. Attacker (or intercepted client) attempts to reuse the already-revoked token1
    const reuseRes = await app.inject({
      method: "POST",
      url: "/v1/auth/refresh",
      payload: { refresh_token: token1 },
    });

    expect(reuseRes.statusCode).toBe(401);
    const reuseBody = reuseRes.json();
    expect(reuseBody.detail.code).toBe("TOKEN_REUSE_DETECTED");

    // 4. Verify family revocation: even token2 (the legitimate active token) must now be invalidated!
    const token2Res = await app.inject({
      method: "POST",
      url: "/v1/auth/refresh",
      payload: { refresh_token: token2 },
    });
    expect(token2Res.statusCode).toBe(401);
  });

  it("Rejects expired refresh tokens with HTTP 401", async () => {
    // Manually create an expired refresh token
    const expiredRawToken = crypto.randomBytes(40).toString("hex");
    const expiredHash = hashRefreshToken(expiredRawToken);

    await prisma.refresh_tokens.create({
      data: {
        user_id: testUser.id,
        token_hash: expiredHash,
        family_id: crypto.randomUUID(),
        expires_at: new Date(Date.now() - 3600 * 1000), // 1 hour ago
      },
    });

    const res = await app.inject({
      method: "POST",
      url: "/v1/auth/refresh",
      payload: { refresh_token: expiredRawToken },
    });

    expect(res.statusCode).toBe(401);
    const body = res.json();
    expect(body.detail.code).toBe("TOKEN_EXPIRED");
  });

  it("POST /v1/auth/logout revokes the entire token family", async () => {
    // 1. Login -> token1
    const loginRes = await app.inject({
      method: "POST",
      url: "/v1/auth/login",
      payload: {
        email: testUser.email,
        password: "SecurePassword123!",
      },
    });
    const { refresh_token: token1 } = loginRes.json();

    // 2. Rotate -> token2
    const refreshRes = await app.inject({
      method: "POST",
      url: "/v1/auth/refresh",
      payload: { refresh_token: token1 },
    });
    const { refresh_token: token2 } = refreshRes.json();

    // 3. Logout with token2
    const logoutRes = await app.inject({
      method: "POST",
      url: "/v1/auth/logout",
      payload: { refresh_token: token2 },
    });
    expect(logoutRes.statusCode).toBe(200);

    // 4. Attempting to refresh with token2 fails
    const postLogoutRefresh = await app.inject({
      method: "POST",
      url: "/v1/auth/refresh",
      payload: { refresh_token: token2 },
    });
    expect(postLogoutRefresh.statusCode).toBe(401);
  });

  it("Protects against concurrent refresh requests using the same valid token (only one succeeds)", async () => {
    // 1. Login -> token1
    const loginRes = await app.inject({
      method: "POST",
      url: "/v1/auth/login",
      payload: {
        email: testUser.email,
        password: "SecurePassword123!",
      },
    });
    const { refresh_token: token1 } = loginRes.json();

    // 2. Fire 3 concurrent refresh requests with the EXACT same token1
    const [res1, res2, res3] = await Promise.all([
      app.inject({ method: "POST", url: "/v1/auth/refresh", payload: { refresh_token: token1 } }),
      app.inject({ method: "POST", url: "/v1/auth/refresh", payload: { refresh_token: token1 } }),
      app.inject({ method: "POST", url: "/v1/auth/refresh", payload: { refresh_token: token1 } }),
    ]);

    const statuses = [res1.statusCode, res2.statusCode, res3.statusCode];
    const successes = statuses.filter((s) => s === 200);

    // Exactly one must succeed, the others must fail (401 due to row lock and reuse detection)
    expect(successes.length).toBe(1);
  });
});
