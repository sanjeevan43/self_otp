import type { FastifyPluginAsync } from "fastify";
import { z } from "zod";
import { WalletService } from "./wallet.service.js";
import { prisma } from "../../plugins/prisma.js";

import { toJsonSchema } from "../../common/utils/schema.js";

const topupSchema = z.object({
  amount: z.number().positive().describe("Positive credit amount to add to wallet (e.g. 50.0)"),
  reference_id: z.string().min(1).describe("Payment gateway reference or transaction ID"),
});

export const walletRoutes: FastifyPluginAsync = async (fastify) => {
  // GET /v1/wallet/balance (supports both API key and JWT)
  fastify.get(
    "/balance",
    {
      schema: {
        tags: ["Wallet & Credits"],
        summary: "Get wallet balance",
        description: "Returns the current credit balance, currency, and active status. Accessible via X-API-Key header or Bearer JWT token.",
        security: [{ ApiKeyAuth: [] }, { BearerAuth: [] }],
      },
    },
    async (request, reply) => {
      // Try API key first, then JWT
      if (request.headers["x-api-key"]) {
        await fastify.authenticateApiKey(request, reply);
      } else {
        await fastify.authenticateJwt(request, reply);
      }

      const customer = request.customer!;
      const wallet = await WalletService.getOrCreateWallet(customer.id);

      return reply.status(200).send({
        status: "success",
        data: {
          balance: Number(wallet.balance),
          currency: wallet.currency,
          status: wallet.status,
          updated_at: wallet.updated_at.toISOString(),
        },
      });
    }
  );

  // POST /v1/wallet/topup (JWT required)
  fastify.post(
    "/topup",
    {
      preHandler: fastify.authenticateJwt,
      schema: {
        tags: ["Wallet & Credits"],
        summary: "Top up wallet credits",
        description: "Adds credits to the customer organization wallet with an idempotent transaction reference.",
        security: [{ BearerAuth: [] }],
        body: toJsonSchema(topupSchema),
      },
    },
    async (request, reply) => {
      const parseResult = topupSchema.safeParse(request.body || {});
      if (!parseResult.success) {
        throw parseResult.error;
      }
      const body = parseResult.data;
      const customer = request.customer!;

      const newBalance = await WalletService.topupWallet(
        customer.id,
        body.amount,
        body.reference_id
      );

      const wallet = await WalletService.getOrCreateWallet(customer.id);

      return reply.status(200).send({
        status: "success",
        data: {
          balance: newBalance,
          currency: wallet.currency,
          status: wallet.status,
          updated_at: wallet.updated_at.toISOString(),
        },
      });
    }
  );

  // GET /v1/wallet/transactions (JWT required)
  fastify.get(
    "/transactions",
    {
      preHandler: fastify.authenticateJwt,
      schema: {
        tags: ["Wallet & Credits"],
        summary: "Get wallet transaction history",
        description: "Returns the 100 most recent credit debit and top-up ledger entries.",
        security: [{ BearerAuth: [] }],
      },
    },
    async (request, reply) => {
      const customer = request.customer!;
      const wallet = await WalletService.getOrCreateWallet(customer.id);

      const txs = await prisma.wallet_transactions.findMany({
        where: { wallet_id: wallet.id },
        orderBy: { created_at: "desc" },
        take: 100,
      });

      return reply.status(200).send(
        txs.map((t) => ({
          id: t.id,
          transaction_type: t.transaction_type,
          amount: Number(t.amount),
          balance_before: Number(t.balance_before),
          balance_after: Number(t.balance_after),
          reference_type: t.reference_type,
          reference_id: t.reference_id,
          description: t.description,
          created_at: t.created_at.toISOString(),
        }))
      );
    }
  );
};
