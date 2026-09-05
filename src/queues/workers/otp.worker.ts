import { Worker, type Job } from "bullmq";
import { redis } from "../../plugins/redis.js";
import { prisma } from "../../plugins/prisma.js";
import { logger } from "../../plugins/logger.js";
import { whatsappProvider } from "../../providers/whatsapp/provider-factory.js";
import { WalletService } from "../../modules/wallet/wallet.service.js";
import { deadLetterQueue } from "../queue.js";

export interface SendOtpJobData {
  otpRequestDbId: string;
  requestId: string;
  phoneNumber: string;
  otpCode: string;
  templateName?: string;
  languageCode?: string;
  customerId: string;
  costCredits: number;
}

export class TemporaryDeliveryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TemporaryDeliveryError";
  }
}

export class PermanentDeliveryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PermanentDeliveryError";
  }
}

export async function processSendOtpJob(job: Job<SendOtpJobData>) {
  const {
    otpRequestDbId,
    requestId,
    phoneNumber,
    otpCode,
    templateName = "otp_auth_v1",
    languageCode = "en_US",
    customerId,
    costCredits,
  } = job.data;

  try {
    const res = await whatsappProvider.sendOtp(
      phoneNumber,
      otpCode,
      templateName,
      languageCode
    );

    // Persist message record
    const messageRecord = await prisma.messages.create({
      data: {
        customer_id: customerId,
        otp_request_id: otpRequestDbId,
        phone_number: phoneNumber,
        provider: "meta",
        provider_message_id: res.providerMessageId || null,
        status: res.success ? "sent" : "failed",
        error_message: !res.success ? res.errorMessage || "Delivery failed" : null,
        sent_at: res.success ? new Date() : null,
        failed_at: !res.success ? new Date() : null,
        updated_at: new Date(),
      },
    });

    // Record MessageEvent
    await prisma.message_events.create({
      data: {
        message_id: messageRecord.id,
        event_type: res.success ? "sent" : "failed",
        provider_message_id: res.providerMessageId || null,
      },
    });

    if (res.success) {
      await prisma.otp_requests.update({
        where: { id: otpRequestDbId },
        data: { status: "sent" },
      });
      return { success: true, requestId, providerMessageId: res.providerMessageId };
    }

    // Handled failure cases
    if (res.isTemporaryError) {
      throw new TemporaryDeliveryError(res.errorMessage || "Temporary delivery failure");
    } else {
      // Permanent failure - update status and refund immediately
      await prisma.otp_requests.update({
        where: { id: otpRequestDbId },
        data: { status: "failed" },
      });

      await WalletService.refundCredits(
        customerId,
        costCredits,
        "otp_request_failure",
        requestId,
        res.errorMessage || "Permanent Meta delivery failure"
      );

      await deadLetterQueue.add("terminal_failure", {
        jobId: job.id,
        requestId,
        customerId,
        reason: res.errorMessage || "Permanent Meta delivery rejection",
      });

      return { success: false, permanent: true, error: res.errorMessage };
    }
  } catch (err: any) {
    const currentAttempt = job.attemptsMade + 1;
    const maxRetries = job.opts.attempts || 3;

    if (currentAttempt >= maxRetries) {
      logger.error(
        { requestId, attemptsMade: currentAttempt, err: err.message },
        "[DLQ] OTP job reached max retries. Routing to dead-letter queue and executing idempotent refund"
      );

      await prisma.otp_requests
        .update({
          where: { id: otpRequestDbId },
          data: { status: "failed" },
        })
        .catch(() => {});

      await WalletService.refundCredits(
        customerId,
        costCredits,
        "otp_request_failure",
        requestId,
        `Max retries exceeded: ${err.message}`
      ).catch((refundErr) => {
        logger.error({ refundErr }, "Error executing refund on max retries");
      });

      await deadLetterQueue
        .add("max_retries_exceeded", {
          jobId: job.id,
          requestId,
          customerId,
          reason: `Max retries exceeded: ${err.message}`,
        })
        .catch(() => {});
    }

    throw err;
  }
}

export function createOtpWorker() {
  const worker = new Worker<SendOtpJobData>(
    "otp_messages",
    async (job) => {
      return await processSendOtpJob(job);
    },
    {
      connection: redis,
      concurrency: 5,
    }
  );

  worker.on("failed", (job, err) => {
    logger.warn({ jobId: job?.id, err: err.message }, "OTP worker job attempt failed");
  });

  return worker;
}
