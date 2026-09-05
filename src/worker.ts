import { logger } from "./plugins/logger.js";
import { prisma } from "./plugins/prisma.js";
import { redis } from "./plugins/redis.js";
import { createOtpWorker } from "./queues/workers/otp.worker.js";
import { createWebhookWorker } from "./queues/workers/webhook.worker.js";

async function startWorker() {
  logger.info("Initializing standalone BullMQ workers...");

  const otpWorker = createOtpWorker();
  const webhookWorker = createWebhookWorker();

  logger.info("BullMQ standalone workers started and listening for jobs (OTP, Webhook)");

  const shutdown = async (signal: string) => {
    logger.info(`Received ${signal}, gracefully shutting down workers...`);
    try {
      await Promise.all([
        otpWorker.close(),
        webhookWorker.close(),
      ]);
      await prisma.$disconnect();
      redis.disconnect();
      logger.info("BullMQ workers shut down cleanly.");
      process.exit(0);
    } catch (err) {
      logger.error({ err }, "Error during worker shutdown");
      process.exit(1);
    }
  };

  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));
}

startWorker().catch((err) => {
  logger.error({ err }, "Fatal error starting standalone BullMQ workers");
  process.exit(1);
});
