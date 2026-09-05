import type { FastifyPluginAsync } from "fastify";
import { z } from "zod";
import { prisma } from "../../plugins/prisma.js";
import { generateApiKey } from "../../common/utils/crypto.js";
import { NotFoundError } from "../../common/errors/app-error.js";

const createApiKeySchema = z.object({
  application_id: z.string().uuid(),
  name: z.string().min(1).max(100),
});

export const apiKeyRoutes: FastifyPluginAsync = async (fastify) => {
  fastify.addHook("preHandler", fastify.authenticateJwt);

  // POST /v1/api-keys (201 Created)
  fastify.post("", async (request, reply) => {
    const parseResult = createApiKeySchema.safeParse(request.body);
    if (!parseResult.success) {
      throw parseResult.error;
    }
    const body = parseResult.data;
    const customer = request.customer!;

    const { rawKey, keyPrefix, keyHash } = generateApiKey();
    const now = new Date();

    const apiKeyRecord = await prisma.api_keys.create({
      data: {
        customer_id: customer.id,
        application_id: body.application_id,
        name: body.name,
        key_prefix: keyPrefix,
        key_hash: keyHash,
        status: "active",
        created_at: now,
        updated_at: now,
      },
    });

    return reply.status(201).send({
      id: apiKeyRecord.id,
      customer_id: apiKeyRecord.customer_id,
      application_id: apiKeyRecord.application_id,
      name: apiKeyRecord.name,
      key_prefix: apiKeyRecord.key_prefix,
      status: apiKeyRecord.status,
      expires_at: apiKeyRecord.expires_at ? apiKeyRecord.expires_at.toISOString() : null,
      last_used_at: apiKeyRecord.last_used_at ? apiKeyRecord.last_used_at.toISOString() : null,
      created_at: apiKeyRecord.created_at.toISOString(),
      raw_secret_key: rawKey,
    });
  });

  // GET /v1/api-keys (200 OK)
  fastify.get("", async (request, reply) => {
    const customer = request.customer!;

    const keys = await prisma.api_keys.findMany({
      where: {
        customer_id: customer.id,
        status: "active",
      },
      orderBy: { created_at: "desc" },
    });

    return reply.status(200).send(
      keys.map((k) => ({
        id: k.id,
        customer_id: k.customer_id,
        name: k.name,
        key_prefix: k.key_prefix,
        status: k.status,
        expires_at: k.expires_at ? k.expires_at.toISOString() : null,
        last_used_at: k.last_used_at ? k.last_used_at.toISOString() : null,
        created_at: k.created_at.toISOString(),
      }))
    );
  });

  // DELETE /v1/api-keys/:key_id (204 No Content)
  fastify.delete("/:key_id", async (request, reply) => {
    const { key_id } = request.params as { key_id: string };
    const customer = request.customer!;

    const apiKey = await prisma.api_keys.findFirst({
      where: {
        id: key_id,
        customer_id: customer.id,
      },
    });

    if (!apiKey) {
      throw new NotFoundError("API key not found.", "KEY_NOT_FOUND");
    }

    await prisma.api_keys.update({
      where: { id: apiKey.id },
      data: {
        status: "revoked",
        revoked_at: new Date(),
        updated_at: new Date(),
      },
    });

    return reply.status(204).send();
  });
};
