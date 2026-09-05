import { prisma } from "../../plugins/prisma.js";
import { AppError } from "../../common/errors/app-error.js";
import type { Prisma, wallets } from "@prisma/client";

function toValidUuidOrNull(val?: string | null): string | null {
  if (!val) return null;
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(val) ? val : null;
}

export class WalletService {
  /**
   * Retrieves or initializes wallet for customer.
   */
  static async getOrCreateWallet(
    customerId: string,
    txClient?: Prisma.TransactionClient
  ): Promise<wallets> {
    const client = txClient || prisma;
    let wallet = await client.wallets.findUnique({
      where: { customer_id: customerId },
    });

    if (!wallet) {
      wallet = await client.wallets.create({
        data: {
          customer_id: customerId,
          balance: 100.0, // 100 free initial credits
          currency: "INR",
          status: "active",
        },
      });
    }

    return wallet;
  }

  /**
   * Atomic wallet deduction using PostgreSQL row-level locking (SELECT FOR UPDATE).
   * Throws HTTP 402 INSUFFICIENT_FUNDS if balance is inadequate.
   */
  static async deductCreditsAtomic(
    customerId: string,
    cost: number,
    referenceType: string,
    referenceId: string
  ): Promise<number> {
    return await prisma.$transaction(
      async (tx) => {
        await WalletService.getOrCreateWallet(customerId, tx);

        // Acquire exclusive row-level lock
        const lockedRows = await tx.$queryRaw<wallets[]>`
          SELECT * FROM wallets 
          WHERE customer_id = ${customerId}::uuid 
          FOR UPDATE
        `;

        if (!lockedRows || lockedRows.length === 0) {
          throw new AppError(404, "Wallet not found", "WALLET_NOT_FOUND");
        }

        const wallet = lockedRows[0];
        const balanceBefore = Number(wallet.balance);

        if (balanceBefore < cost) {
          throw new AppError(
            402,
            "Wallet balance is insufficient.",
            "INSUFFICIENT_FUNDS",
            {
              current_balance: balanceBefore,
              required_credits: cost,
            }
          );
        }

        const balanceAfter = Math.round((balanceBefore - cost) * 10000) / 10000;

        await tx.wallets.update({
          where: { id: wallet.id },
          data: {
            balance: balanceAfter,
            updated_at: new Date(),
          },
        });

        await tx.wallet_transactions.create({
          data: {
            wallet_id: wallet.id,
            transaction_type: "debit",
            amount: cost,
            balance_before: balanceBefore,
            balance_after: balanceAfter,
            reference_type: referenceType,
            reference_id: toValidUuidOrNull(referenceId),
            description: "OTP Dispatch Debit",
          },
        });

        return balanceAfter;
      },
      { maxWait: 15000, timeout: 20000 }
    );
  }

  /**
   * At-most-one effective refund per referenceId using row-level locking.
   * Guarantees that even if workers execute this concurrently or multiply,
   * exactly one financial credit is applied to the balance.
   */
  static async refundCredits(
    customerId: string,
    cost: number,
    referenceType: string,
    referenceId: string,
    reason = "Meta delivery failure"
  ): Promise<number> {
    return await prisma.$transaction(
      async (tx) => {
        await WalletService.getOrCreateWallet(customerId, tx);

        // Acquire exclusive row-level lock
        const lockedRows = await tx.$queryRaw<wallets[]>`
          SELECT * FROM wallets 
          WHERE customer_id = ${customerId}::uuid 
          FOR UPDATE
        `;

        if (!lockedRows || lockedRows.length === 0) {
          throw new AppError(404, "Wallet not found", "WALLET_NOT_FOUND");
        }

        const wallet = lockedRows[0];
        const validRefId = toValidUuidOrNull(referenceId);

        // Idempotency check: verify if a refund has already been granted for this reference_id
        const existingRefund = await tx.wallet_transactions.findFirst({
          where: {
            wallet_id: wallet.id,
            reference_type: referenceType,
            reference_id: validRefId,
            transaction_type: "refund",
          },
        });

        if (existingRefund) {
          // Refund already processed for this referenceId. Return current balance without modifying.
          return Number(wallet.balance);
        }

        const balanceBefore = Number(wallet.balance);
        const balanceAfter = Math.round((balanceBefore + cost) * 10000) / 10000;

        await tx.wallets.update({
          where: { id: wallet.id },
          data: {
            balance: balanceAfter,
            updated_at: new Date(),
          },
        });

        await tx.wallet_transactions.create({
          data: {
            wallet_id: wallet.id,
            transaction_type: "refund",
            amount: cost,
            balance_before: balanceBefore,
            balance_after: balanceAfter,
            reference_type: referenceType,
            reference_id: validRefId,
            description: `Refund: ${reason}`,
          },
        });

        return balanceAfter;
      },
      { maxWait: 15000, timeout: 20000 }
    );
  }

  /**
   * Topup credits to wallet on payment success using row-level locking.
   */
  static async topupWallet(
    customerId: string,
    amount: number,
    referenceId: string
  ): Promise<number> {
    return await prisma.$transaction(async (tx) => {
      await WalletService.getOrCreateWallet(customerId, tx);

      const lockedRows = await tx.$queryRaw<wallets[]>`
        SELECT * FROM wallets 
        WHERE customer_id = ${customerId}::uuid 
        FOR UPDATE
      `;

      if (!lockedRows || lockedRows.length === 0) {
        throw new AppError(404, "Wallet not found", "WALLET_NOT_FOUND");
      }

      const wallet = lockedRows[0];
      const balanceBefore = Number(wallet.balance);
      const balanceAfter = Math.round((balanceBefore + amount) * 10000) / 10000;

      await tx.wallets.update({
        where: { id: wallet.id },
        data: {
          balance: balanceAfter,
          updated_at: new Date(),
        },
      });

      await tx.wallet_transactions.create({
        data: {
          wallet_id: wallet.id,
          transaction_type: "credit",
          amount,
          balance_before: balanceBefore,
          balance_after: balanceAfter,
          reference_type: "payment",
          reference_id: toValidUuidOrNull(referenceId),
          description: "Wallet Topup Credit",
        },
      });

      return balanceAfter;
    });
  }

  /**
   * Get current balance for customer.
   */
  static async getBalance(customerId: string): Promise<{ balance: number; currency: string }> {
    const wallet = await WalletService.getOrCreateWallet(customerId);
    return {
      balance: Number(wallet.balance),
      currency: wallet.currency,
    };
  }

  /**
   * Get transaction history with pagination.
   */
  static async listTransactions(customerId: string, page = 1, pageSize = 20) {
    const wallet = await WalletService.getOrCreateWallet(customerId);
    const skip = (page - 1) * pageSize;

    const [transactions, total] = await Promise.all([
      prisma.wallet_transactions.findMany({
        where: { wallet_id: wallet.id },
        orderBy: { created_at: "desc" },
        skip,
        take: pageSize,
      }),
      prisma.wallet_transactions.count({
        where: { wallet_id: wallet.id },
      }),
    ]);

    return {
      transactions: transactions.map((t) => ({
        id: t.id,
        transaction_type: t.transaction_type,
        amount: Number(t.amount),
        balance_before: Number(t.balance_before),
        balance_after: Number(t.balance_after),
        reference_type: t.reference_type,
        reference_id: t.reference_id,
        description: t.description,
        created_at: t.created_at,
      })),
      total,
      page,
      page_size: pageSize,
      total_pages: Math.ceil(total / pageSize),
    };
  }
}
