import crypto from "node:crypto";
import type { FastifyPluginAsync } from "fastify";
import { z } from "zod";
import { prisma } from "../../plugins/prisma.js";
import { NotFoundError } from "../../common/errors/app-error.js";

import { toJsonSchema } from "../../common/utils/schema.js";

const createApplicationSchema = z.object({
  name: z.string().min(1).max(100).describe("Human-readable application name (e.g. My Website Auth)"),
  description: z.string().optional().describe("Optional description of the application environment"),
});

export const applicationRoutes: FastifyPluginAsync = async (fastify) => {
  fastify.addHook("preHandler", fastify.authenticateJwt);

  // GET /v1/applications
  fastify.get(
    "",
    {
      schema: {
        tags: ["Applications"],
        summary: "List applications",
        description: "Returns all registered application workspaces for the authenticated customer organization.",
        security: [{ BearerAuth: [] }],
      },
    },
    async (request, reply) => {
      const customer = request.customer!;
      const apps = await prisma.applications.findMany({
        where: { customer_id: customer.id },
        orderBy: { created_at: "desc" },
      });

      return reply.status(200).send(apps);
    }
  );

  // GET /v1/applications/:app_id
  fastify.get(
    "/:app_id",
    {
      schema: {
        tags: ["Applications"],
        summary: "Get application details",
        description: "Retrieves details of a specific application workspace.",
        security: [{ BearerAuth: [] }],
        params: {
          type: "object",
          properties: {
            app_id: {
              type: "string",
              description: "The unique application UUID",
            },
          },
          required: ["app_id"],
        },
      },
    },
    async (request, reply) => {
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
    }
  );

  // POST /v1/applications
  fastify.post(
    "",
    {
      schema: {
        tags: ["Applications"],
        summary: "Create application",
        description: "Creates a new application workspace for organizing API keys and OTP logs.",
        security: [{ BearerAuth: [] }],
        body: toJsonSchema(createApplicationSchema),
      },
    },
    async (request, reply) => {
      const parseResult = createApplicationSchema.safeParse(request.body || {});
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
    }
  );

  // DELETE /v1/applications/:app_id
  fastify.delete(
    "/:app_id",
    {
      schema: {
        tags: ["Applications"],
        summary: "Delete application",
        description: "Permanently deletes an application workspace.",
        security: [{ BearerAuth: [] }],
        params: {
          type: "object",
          properties: {
            app_id: {
              type: "string",
              description: "The unique application UUID",
            },
          },
          required: ["app_id"],
        },
      },
    },
    async (request, reply) => {
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
    }
  );
};
