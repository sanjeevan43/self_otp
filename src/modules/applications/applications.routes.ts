import crypto from "node:crypto";
import type { FastifyPluginAsync } from "fastify";
import { z } from "zod";
import { prisma } from "../../plugins/prisma.js";
import { NotFoundError } from "../../common/errors/app-error.js";

const createApplicationSchema = z.object({
  name: z.string().min(1).max(100),
  description: z.string().optional(),
});

export const applicationRoutes: FastifyPluginAsync = async (fastify) => {
  fastify.addHook("preHandler", fastify.authenticateJwt);

  // GET /v1/applications
  fastify.get("", async (request, reply) => {
    const customer = request.customer!;
    const apps = await prisma.applications.findMany({
      where: { customer_id: customer.id },
      orderBy: { created_at: "desc" },
    });

    return reply.status(200).send(apps);
  });

  // GET /v1/applications/:app_id
  fastify.get("/:app_id", async (request, reply) => {
    const { app_id } = request.params as { app_id: string };
    const customer = request.customer!;

    const app = await prisma.applications.findFirst({
      where: {
        id: app_id,
        customer_id: customer.id,
      },
    });

    if (!app) {
      throw new NotFoundError("Application not found");
    }

    return reply.status(200).send(app);
  });

  // POST /v1/applications
  fastify.post("", async (request, reply) => {
    const parseResult = createApplicationSchema.safeParse(request.body);
    if (!parseResult.success) {
      throw parseResult.error;
    }
    const body = parseResult.data;
    const customer = request.customer!;
    const now = new Date();

    const app = await prisma.applications.create({
      data: {
        id: crypto.randomUUID(),
        customer_id: customer.id,
        name: body.name,
        description: body.description || null,
        created_at: now,
        updated_at: now,
      },
    });

    return reply.status(201).send(app);
  });

  // DELETE /v1/applications/:app_id
  fastify.delete("/:app_id", async (request, reply) => {
    const { app_id } = request.params as { app_id: string };
    const customer = request.customer!;

    const app = await prisma.applications.findFirst({
      where: {
        id: app_id,
        customer_id: customer.id,
      },
    });

    if (!app) {
      throw new NotFoundError("Application not found");
    }

    await prisma.applications.delete({
      where: { id: app.id },
    });

    return reply.status(204).send();
  });
};
