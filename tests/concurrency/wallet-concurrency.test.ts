import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { buildApp } from "../../src/app.js";
import { createTestTenant } from "../helpers/test-tenant.js";
import { WalletService } from "../../src/modules/wallet/wallet.service.js";
import { prisma } from "../../src/plugins/prisma.js";
import { redis } from "../../src/plugins/redis.js";
import crypto from "node:crypto";
import type { FastifyInstance } from "fastify";

describe("Wallet Row-Level Locking & At-Most-One Refund Guarantee", () => {
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

  it("Insufficient balance prevents debit with HTTP 402", async () => {
    const tenant = await createTestTenant(app, "broke", 0.0);

    const sendResp = await app.inject({
      method: "POST",
      url: "/v1/otp/send",
      headers: {
        "x-api-key": tenant.rawApiKey,
      },
      payload: {
        phone_number: "+14155550201",
        ttl_seconds: 300,
      },
    });

    expect(sendResp.statusCode).toBe(402);
    const body = sendResp.json();
    expect(body.detail.code).toBe("INSUFFICIENT_FUNDS");
  });

  it("Row-level locking handles concurrent debits without balance corruption", async () => {
    const tenant = await createTestTenant(app, "concurrent_debit", 10.0);

    // Run 5 debits in parallel
    const debitPromises = Array.from({ length: 5 }, () =>
      WalletService.deductCreditsAtomic(
        tenant.customerId,
        1.0,
        "otp_request",
        crypto.randomUUID()
      )
    );

    const results = await Promise.all(debitPromises);
    expect(results).toHaveLength(5);

    const finalBalance = await WalletService.getBalance(tenant.customerId);
    expect(finalBalance.balance).toBe(5.0);
  });

  it("Guarantees AT-MOST-ONE effective refund per reference_id under duplicate concurrent execution", async () => {
    const tenant = await createTestTenant(app, "refund_concurrency", 50.0);
    const sharedReferenceId = crypto.randomUUID();

    // Execute refund concurrently 5 times with the exact same reference_id
    const refundPromises = Array.from({ length: 5 }, () =>
      WalletService.refundCredits(
        tenant.customerId,
        1.0,
        "otp_request_failure",
        sharedReferenceId,
        "Meta delivery failure"
      )
    );

    await Promise.all(refundPromises);

    // The balance should have increased by EXACTLY 1.0 (from 50.0 to 51.0), NOT by 10.0!
    const finalBalance = await WalletService.getBalance(tenant.customerId);
    expect(finalBalance.balance).toBe(51.0);

    // Verify database transaction ledger contains EXACTLY ONE refund transaction for this reference_id
    const wallet = await WalletService.getOrCreateWallet(tenant.customerId);
    const refundTransactions = await prisma.wallet_transactions.findMany({
      where: {
        wallet_id: wallet.id,
        reference_id: sharedReferenceId,
        transaction_type: "refund",
      },
    });
    expect(refundTransactions).toHaveLength(1);
    expect(refundTransactions[0].amount).toBe(1.0);
  });
});
