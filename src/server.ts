import { buildApp } from "./app.js";
import { env } from "./config/env.js";
import { logger } from "./plugins/logger.js";
import { prisma } from "./plugins/prisma.js";
import { redis } from "./plugins/redis.js";
import { createOtpWorker } from "./queues/workers/otp.worker.js";
import { createWebhookWorker } from "./queues/workers/webhook.worker.js";

async function start() {
  const app = buildApp();

  let otpWorker: ReturnType<typeof createOtpWorker> | undefined;
  let webhookWorker: ReturnType<typeof createWebhookWorker> | undefined;

  try {
    // Start BullMQ workers in production/dev
    // If explicitly enabled, start embedded workers alongside API
    if (env.NODE_ENV !== "test" && process.env.START_EMBEDDED_WORKER === "true") {
      try {
        otpWorker = createOtpWorker();
        webhookWorker = createWebhookWorker();
        logger.info("BullMQ background workers initialized");
      } catch (workerErr: any) {
        logger.warn({ workerErr: workerErr.message }, "BullMQ worker startup warning");
      }
    }

    await app.listen({ port: env.PORT, host: env.HOST });
    logger.info(`Server listening on http://${env.HOST}:${env.PORT}`);
  } catch (err) {
    logger.error({ err }, "Fatal error starting server");
    process.exit(1);
  }

  const signals = ["SIGINT", "SIGTERM"] as const;
  for (const signal of signals) {
    process.on(signal, async () => {
      logger.info(`Received ${signal}, shutting down gracefully...`);
      await app.close();
      if (otpWorker) await otpWorker.close();
      if (webhookWorker) await webhookWorker.close();
      await prisma.$disconnect();
      redis.disconnect();
      process.exit(0);
    });
  }
}

start();
