import type { FastifyPluginAsync, FastifyReply, FastifyRequest } from "fastify";
import fp from "fastify-plugin";
import { prisma } from "./prisma.js";
import { hashApiKey } from "../common/utils/crypto.js";
import { isRateLimited } from "../middleware/rate-limit.js";
import { UnauthorizedError, ForbiddenError, RateLimitError } from "../common/errors/app-error.js";
import type { api_keys, applications, customers, users } from "@prisma/client";

declare module "fastify" {
  interface FastifyRequest {
    apiKey?: api_keys;
    application?: applications;
    customer?: customers;
    authUser?: users;
  }
  interface FastifyInstance {
    authenticateApiKey: (req: FastifyRequest, reply: FastifyReply) => Promise<void>;
    authenticateJwt: (req: FastifyRequest, reply: FastifyReply) => Promise<void>;
  }
}

const authPluginCallback: FastifyPluginAsync = async (fastify) => {
  fastify.decorate(
    "authenticateApiKey",
    async (request: FastifyRequest, _reply: FastifyReply) => {
      const rawApiKey = request.headers["x-api-key"] as string | undefined;
      if (!rawApiKey) {
        throw new UnauthorizedError("API key required in 'X-API-Key' header.", "UNAUTHORIZED");
      }

      const keyHash = hashApiKey(rawApiKey);

      const apiKeyRecord = await prisma.api_keys.findFirst({
        where: {
          key_hash: keyHash,
          status: "active",
        },
        include: {
          applications: true,
          customers: true,
        },
      });

      if (!apiKeyRecord) {
        throw new UnauthorizedError("Invalid or revoked API key.", "UNAUTHORIZED");
      }

      if (apiKeyRecord.customers.status !== "active") {
        throw new ForbiddenError("Customer account is suspended or disabled.", "FORBIDDEN");
      }

      // Check API key rate limit (60 req/min default)
      const { isLimited } = await isRateLimited(`ratelimit:apikey:${apiKeyRecord.id}`, 60, 60);
      if (isLimited) {
        throw new RateLimitError("API key rate limit exceeded.", "RATE_LIMIT_EXCEEDED");
      }

      // Update last_used_at asynchronously
      prisma.api_keys
        .update({
          where: { id: apiKeyRecord.id },
          data: { last_used_at: new Date() },
        })
        .catch(() => {});

      request.apiKey = apiKeyRecord;
      request.application = apiKeyRecord.applications;
      request.customer = apiKeyRecord.customers;
    }
  );

  fastify.decorate(
    "authenticateJwt",
    async (request: FastifyRequest, _reply: FastifyReply) => {
      try {
        const decoded = await request.jwtVerify<{ sub: string; type: string }>();
        if (decoded.type !== "access" || !decoded.sub) {
          throw new UnauthorizedError("Invalid token payload.", "UNAUTHORIZED");
        }

        const user = await prisma.users.findUnique({
          where: { id: decoded.sub },
        });

        if (!user || user.status !== "active") {
          throw new UnauthorizedError("User not found or inactive.", "UNAUTHORIZED");
        }

        const customerUser = await prisma.customer_users.findFirst({
          where: { user_id: user.id },
          include: { customers: true },
        });

        if (!customerUser || customerUser.customers.status !== "active") {
          throw new ForbiddenError("Customer account is suspended or inactive.", "FORBIDDEN");
        }

        request.authUser = user;
        request.customer = customerUser.customers;
      } catch (err: any) {
        if (err instanceof UnauthorizedError || err instanceof ForbiddenError) {
          throw err;
        }
        throw new UnauthorizedError("Could not validate credentials.", "UNAUTHORIZED");
      }
    }
  );
};

export const authPlugin = fp(authPluginCallback, {
  name: "auth-plugin",
});
