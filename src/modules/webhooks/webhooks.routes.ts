import type { FastifyPluginAsync } from "fastify";
import { prisma } from "../../plugins/prisma.js";
import { env } from "../../config/env.js";
import { logger } from "../../plugins/logger.js";
import { verifyMetaSignature } from "../../common/utils/crypto.js";
import { webhookQueue } from "../../queues/queue.js";
import { ForbiddenError, UnauthorizedError } from "../../common/errors/app-error.js";
import { Prisma } from "@prisma/client";

export const webhookRoutes: FastifyPluginAsync = async (fastify) => {
  // GET /v1/webhooks/meta - Handshake challenge
  fastify.get("/meta", async (request, reply) => {
    const query = request.query as Record<string, string | undefined>;
    const mode = query["hub.mode"];
    const token = query["hub.verify_token"];
    const challenge = query["hub.challenge"];

    if (mode === "subscribe" && token === env.META_WEBHOOK_VERIFY_TOKEN) {
      logger.info("Meta webhook verification challenge succeeded.");
      return reply.status(200).type("text/plain").send(challenge);
    }

    logger.warn("Meta webhook verification challenge failed: token mismatch.");
    throw new ForbiddenError("Verification token mismatch.", "FORBIDDEN");
  });

  // POST /v1/webhooks/meta - Inbound webhook ingestion
  fastify.post("/meta", async (request, reply) => {
    const rawBody = (request as any).rawBody || JSON.stringify(request.body);
    const signatureHeader = request.headers["x-hub-signature-256"] as string | undefined;

    // 1. Validate signature if configured and signature present
    if (
      env.META_APP_SECRET &&
      !env.META_APP_SECRET.startsWith("mock_") &&
      signatureHeader
    ) {
      const isValid = verifyMetaSignature(rawBody, signatureHeader, env.META_APP_SECRET);
      if (!isValid) {
        logger.error("Meta webhook signature mismatch!");
        throw new UnauthorizedError("Invalid webhook signature.", "UNAUTHORIZED");
      }
    }

    // 2. Parse payload
    const payload = request.body as any;
    if (!payload || !payload.entry) {
      return reply.status(200).send({ status: "ignored" });
    }

    const entries = payload.entry || [];
    for (const entry of entries) {
      const changes = entry.changes || [];
      for (const change of changes) {
        const value = change.value || {};
        const statuses = value.statuses || [];
        for (const statusItem of statuses) {
          const wamid = statusItem.id;
          const statusStr = statusItem.status;

          if (wamid && statusStr) {
            const eventIdempotencyKey = `${wamid}_${statusStr}`;

            try {
              // Persist and deduplicate via external_event_id unique constraint
              const webhookEvent = await prisma.webhook_events.create({
                data: {
                  provider: "meta",
                  event_type: statusStr,
                  external_event_id: eventIdempotencyKey,
                  payload: statusItem,
                  processing_status: "received",
                },
              });

              // Queue to BullMQ
              await webhookQueue.add("process_meta_webhook", {
                eventId: webhookEvent.id,
                wamid,
                statusStr,
              });
            } catch (err: any) {
              if (
                err instanceof Prisma.PrismaClientKnownRequestError &&
                err.code === "P2002"
              ) {
                logger.info(
                  { eventIdempotencyKey },
                  "Duplicate webhook event ignored (idempotency deduplication)"
                );
              } else {
                logger.error({ err }, "Error ingesting webhook event");
              }
            }
          }
        }
      }
    }

    return reply.status(200).send({ status: "ok" });
  });
};
