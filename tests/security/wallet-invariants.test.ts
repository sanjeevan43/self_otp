import { describe, it, expect, beforeEach } from "vitest";
import { prisma } from "../../src/plugins/prisma.js";
import { WalletService } from "../../src/modules/wallet/wallet.service.js";
import crypto from "node:crypto";

describe("Phase 2.2 — Wallet Financial Invariants & At-Most-One Refund", () => {
  let customerId: string;
  let walletId: string;

  beforeEach(async () => {
    customerId = crypto.randomUUID();
    const uniqueEmail = `wallet_test_${Date.now()}_${crypto.randomInt(1000, 9999)}@example.com`;

    await prisma.customers.create({
      data: {
        id: customerId,
        company_name: "Wallet Invariant Test Org",
        email: uniqueEmail,
        status: "active",
        country_code: "+91",
      },
    });

    const wallet = await WalletService.getOrCreateWallet(customerId);
    walletId = wallet.id;

    // Reset balance to known initial amount (100.0)
    await prisma.wallets.update({
      where: { id: walletId },
      data: { balance: 100.0 },
    });
  });

  it("Normal debit atomically deducts credits and generates exactly one transaction ledger entry", async () => {
    const refId = crypto.randomUUID();
    const balanceAfter = await WalletService.deductCreditsAtomic(customerId, 1.0, "otp_send", refId);

    expect(balanceAfter).toBe(99.0);

    const txns = await prisma.wallet_transactions.findMany({
      where: { wallet_id: walletId, reference_id: refId },
    });

    expect(txns.length).toBe(1);
    expect(txns[0].transaction_type).toBe("debit");
    expect(Number(txns[0].amount)).toBe(1.0);
    expect(Number(txns[0].balance_after)).toBe(99.0);
  });

  it("Insufficient balance throws HTTP 402 and does NOT modify wallet balance or ledger", async () => {
    // Current balance is 100.0; attempt to debit 150.0
    const refId = crypto.randomUUID();

    await expect(
      WalletService.deductCreditsAtomic(customerId, 150.0, "otp_send", refId)
    ).rejects.toThrow("Wallet balance is insufficient.");

    const wallet = await prisma.wallets.findUnique({ where: { id: walletId } });
    expect(Number(wallet!.balance)).toBe(100.0);

    const txns = await prisma.wallet_transactions.findMany({
      where: { wallet_id: walletId, reference_id: refId },
    });
    expect(txns.length).toBe(0);
  });

  it("Zero balance edge case: debiting when balance is exactly 0.0 throws HTTP 402", async () => {
    // Set wallet balance to 0.0
    await prisma.wallets.update({
      where: { id: walletId },
      data: { balance: 0.0 },
    });

    const refId = crypto.randomUUID();
    await expect(
      WalletService.deductCreditsAtomic(customerId, 1.0, "otp_send", refId)
    ).rejects.toThrow("Wallet balance is insufficient.");

    const wallet = await prisma.wallets.findUnique({ where: { id: walletId } });
    expect(Number(wallet!.balance)).toBe(0.0);
  });

  it("Database engine strictly rejects negative balance via chk_wallets_balance_non_negative CHECK constraint", async () => {
    // Direct raw SQL update attempting to bypass application layer into negative balance
    await expect(
      prisma.$executeRaw`
        UPDATE public.wallets 
        SET balance = -50.0000 
        WHERE id = ${walletId}::uuid
      `
    ).rejects.toThrow();

    // Verify balance was untouched
    const wallet = await prisma.wallets.findUnique({ where: { id: walletId } });
    expect(Number(wallet!.balance)).toBeGreaterThanOrEqual(0);
  });

  it("Guarantees AT-MOST-ONE effective refund per reference_id under duplicate sequential calls", async () => {
    const refId = crypto.randomUUID();

    // 1. Initial debit of 1.0 -> balance becomes 99.0
    await WalletService.deductCreditsAtomic(customerId, 1.0, "otp_send", refId);

    // 2. First refund -> balance restored to 100.0
    const balanceAfterRefund1 = await WalletService.refundCredits(
      customerId,
      1.0,
      "otp_send",
      refId,
      "Delivery failure"
    );
    expect(balanceAfterRefund1).toBe(100.0);

    // 3. Duplicate second refund attempt with identical reference_id (worker retry scenario)
    const balanceAfterRefund2 = await WalletService.refundCredits(
      customerId,
      1.0,
      "otp_send",
      refId,
      "Delivery failure retry"
    );

    // Must NOT increase balance again!
    expect(balanceAfterRefund2).toBe(100.0);

    // Verify exactly ONE refund transaction exists in the ledger
    const refundTxns = await prisma.wallet_transactions.findMany({
      where: {
        wallet_id: walletId,
        reference_id: refId,
        transaction_type: "refund",
      },
    });

    expect(refundTxns.length).toBe(1);
  });

  it("Guarantees AT-MOST-ONE effective refund under concurrent worker execution", async () => {
    const refId = crypto.randomUUID();

    // 1. Debit 1.0 -> balance 99.0
    await WalletService.deductCreditsAtomic(customerId, 1.0, "otp_send", refId);

    // 2. Simulate 4 workers executing refundCredits concurrently for the exact same refId
    const results = await Promise.all([
      WalletService.refundCredits(customerId, 1.0, "otp_send", refId, "Concurrent failure retry 1"),
      WalletService.refundCredits(customerId, 1.0, "otp_send", refId, "Concurrent failure retry 2"),
      WalletService.refundCredits(customerId, 1.0, "otp_send", refId, "Concurrent failure retry 3"),
      WalletService.refundCredits(customerId, 1.0, "otp_send", refId, "Concurrent failure retry 4"),
    ]);

    // All return final balance of 100.0 (never 101, 102, 103)
    results.forEach((b) => expect(b).toBe(100.0));

    const wallet = await prisma.wallets.findUnique({ where: { id: walletId } });
    expect(Number(wallet!.balance)).toBe(100.0);

    const refundTxns = await prisma.wallet_transactions.findMany({
      where: {
        wallet_id: walletId,
        reference_id: refId,
        transaction_type: "refund",
      },
    });

    // Exactly one ledger refund entry
    expect(refundTxns.length).toBe(1);
  });

  it("Row-level locking handles concurrent debits without balance corruption or double-spend", async () => {
    // Initial balance: 100.0. Run 10 concurrent debits of 10.0 each (total: 100.0)
    const promises = Array.from({ length: 10 }).map(() =>
      WalletService.deductCreditsAtomic(customerId, 10.0, "otp_send", crypto.randomUUID())
    );

    await Promise.all(promises);

    const wallet = await prisma.wallets.findUnique({ where: { id: walletId } });
    expect(Number(wallet!.balance)).toBe(0.0);

    const txns = await prisma.wallet_transactions.findMany({
      where: { wallet_id: walletId, transaction_type: "debit" },
    });
    expect(txns.length).toBe(10);
  });
});
