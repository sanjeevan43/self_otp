import crypto from "node:crypto";
import type { FastifyPluginAsync } from "fastify";
import fp from "fastify-plugin";

const requestIdPluginCallback: FastifyPluginAsync = async (fastify) => {
  fastify.addHook("onRequest", async (request, reply) => {
    const existingId = request.headers["x-request-id"] as string | undefined;
    const reqId = existingId || crypto.randomUUID();
    request.id = reqId;
    reply.header("x-request-id", reqId);
  });
};

export const requestIdPlugin = fp(requestIdPluginCallback, {
  name: "request-id-plugin",
});
