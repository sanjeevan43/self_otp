import type { FastifyPluginAsync } from "fastify";
import { prisma } from "../../plugins/prisma.js";
import { WalletService } from "../wallet/wallet.service.js";
import { env } from "../../config/env.js";

export const accountRoutes: FastifyPluginAsync = async (fastify) => {
  const authenticate = async (request: any, reply: any) => {
    if (request.headers["x-api-key"]) {
      await fastify.authenticateApiKey(request, reply);
    } else {
      await fastify.authenticateJwt(request, reply);
    }
  };

  // GET /v1/account
  fastify.get(
    "",
    {
      preHandler: authenticate,
      schema: {
        tags: ["Account"],
        summary: "Get customer company account details",
        description: "Returns organization details, company profile, status, and credit balance.",
        security: [{ BearerAuth: [] }, { ApiKeyAuth: [] }],
      },
    },
    async (request, reply) => {
      const customer = request.customer!;
      const wallet = await WalletService.getOrCreateWallet(customer.id);

      return reply.status(200).send({
        id: customer.id,
        company_name: customer.company_name,
        email: customer.email,
        phone: customer.phone,
        status: customer.status,
        country_code: customer.country_code,
        wallet: {
          balance: Number(wallet.balance),
          currency: wallet.currency,
          status: wallet.status,
        },
        created_at: customer.created_at.toISOString(),
        updated_at: customer.updated_at.toISOString(),
      });
    }
  );

  // GET /v1/account/usage
  fastify.get(
    "/usage",
    {
      preHandler: authenticate,
      schema: {
        tags: ["Account"],
        summary: "Get account usage statistics",
        description: "Returns aggregated OTP request counts and delivery metrics for this customer.",
        security: [{ BearerAuth: [] }, { ApiKeyAuth: [] }],
      },
    },
    async (request, reply) => {
      const customer = request.customer!;

      const [total, verified, failed] = await Promise.all([
        prisma.otp_requests.count({ where: { customer_id: customer.id } }),
        prisma.otp_requests.count({ where: { customer_id: customer.id, status: "verified" } }),
        prisma.otp_requests.count({ where: { customer_id: customer.id, status: "failed" } }),
      ]);

      return reply.status(200).send({
        customer_id: customer.id,
        metrics: {
          total_otp_requests: total,
          verified_otps: verified,
          failed_otps: failed,
          pending_or_sent: Math.max(0, total - verified - failed),
        },
      });
    }
  );

  // GET /v1/account/limits
  fastify.get(
    "/limits",
    {
      preHandler: authenticate,
      schema: {
        tags: ["Account"],
        summary: "Get account rate limits and concurrency quotas",
        description: "Returns system rate limits, daily quotas, and verification attempt limits.",
        security: [{ BearerAuth: [] }, { ApiKeyAuth: [] }],
      },
    },
    async (_request, reply) => {
      return reply.status(200).send({
        api_rate_limit_rps: env.DEFAULT_API_KEY_RATE_LIMIT_RPS,
        otp_max_verify_attempts: env.OTP_MAX_VERIFY_ATTEMPTS,
        otp_expiry_seconds: env.OTP_EXPIRY_SECONDS,
        otp_cooldown_seconds: env.OTP_COOLDOWN_SECONDS,
        credit_cost_per_otp: env.OTP_CREDIT_COST,
      });
    }
  );
};
