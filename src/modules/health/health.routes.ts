import type { FastifyPluginAsync } from "fastify";
import { prisma } from "../../plugins/prisma.js";
import { redis } from "../../plugins/redis.js";

export const healthRoutes: FastifyPluginAsync = async (fastify) => {
  // GET /health - Exact Python match
  fastify.get(
    "/health",
    {
      schema: {
        tags: ["Health"],
        summary: "System health check",
        description: "Returns basic service status ok for load balancers.",
      },
    },
    async (_request, reply) => {
      return reply.status(200).send({ status: "ok" });
    }
  );

  // GET /health/live
  fastify.get(
    "/health/live",
    {
      schema: {
        tags: ["Health"],
        summary: "Kubernetes liveness probe",
        description: "Returns live when the application process is running.",
      },
    },
    async (_request, reply) => {
      return reply.status(200).send({ status: "live" });
    }
  );

  // GET /health/ready
  fastify.get(
    "/health/ready",
    {
      schema: {
        tags: ["Health"],
        summary: "Readiness probe",
        description: "Verifies active database and Redis connectivity before routing traffic.",
      },
    },
    async (_request, reply) => {
      let dbOk = false;
      let redisOk = false;

      try {
        await prisma.$queryRaw`SELECT 1`;
        dbOk = true;
      } catch {}

      try {
        await redis.ping();
        redisOk = true;
      } catch {}

      const isReady = dbOk && redisOk;
      return reply.status(isReady ? 200 : 503).send({
        status: isReady ? "ready" : "unhealthy",
        database: dbOk ? "connected" : "disconnected",
        redis: redisOk ? "connected" : "disconnected",
      });
    }
  );
};
