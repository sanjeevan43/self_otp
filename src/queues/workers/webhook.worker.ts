import { Worker, type Job } from "bullmq";
import { redis } from "../../plugins/redis.js";
import { prisma } from "../../plugins/prisma.js";
import { logger } from "../../plugins/logger.js";
import type { message_status, message_event_type, otp_status } from "@prisma/client";

export interface ProcessWebhookJobData {
  eventId: string;
  wamid: string;
  statusStr: string;
}

export async function processWebhookJob(job: Job<ProcessWebhookJobData>) {
  const { eventId, wamid, statusStr } = job.data;
  const normalizedStatus = statusStr.toLowerCase();

  // Find linked message
  const message = await prisma.messages.findFirst({
    where: { provider_message_id: wamid },
  });

  const statusMap: Record<string, message_status> = {
    sent: "sent",
    delivered: "delivered",
    read: "read",
    failed: "failed",
  };

  const eventTypeMap: Record<string, message_event_type> = {
    sent: "sent",
    delivered: "delivered",
    read: "read",
    failed: "failed",
  };

  const newStatus = statusMap[normalizedStatus] || "sent";
  const newEventType = eventTypeMap[normalizedStatus] || "sent";

  if (message) {
    // Check if this event was already recorded (idempotency check)
    const existingEvent = await prisma.message_events.findFirst({
      where: {
        message_id: message.id,
        event_type: newEventType,
      },
    });

    if (!existingEvent) {
      const updateData: any = {
        status: newStatus,
        updated_at: new Date(),
      };
      if (newStatus === "delivered") updateData.delivered_at = new Date();
      if (newStatus === "read") updateData.read_at = new Date();
      if (newStatus === "failed") updateData.failed_at = new Date();

      await prisma.messages.update({
        where: { id: message.id },
        data: updateData,
      });

      await prisma.message_events.create({
        data: {
          message_id: message.id,
          event_type: newEventType,
          provider_message_id: wamid,
        },
      });
    }

    // Update linked OTPRequest status (unless already verified)
    if (message.otp_request_id) {
      const otpRecord = await prisma.otp_requests.findUnique({
        where: { id: message.otp_request_id },
      });

      if (otpRecord && otpRecord.status !== "verified") {
        const otpStatusMap: Record<string, otp_status> = {
          sent: "sent",
          delivered: "delivered",
          failed: "failed",
        };

        if (otpStatusMap[normalizedStatus]) {
          await prisma.otp_requests.update({
            where: { id: message.otp_request_id },
            data: { status: otpStatusMap[normalizedStatus] },
          });
        }
      }
    }
  }

  // Update webhook_events record status to processed
  await prisma.webhook_events
    .update({
      where: { id: eventId },
      data: {
        processing_status: "processed",
        processed_at: new Date(),
      },
    })
    .catch(() => {});

  return { success: true, eventId, wamid, status: normalizedStatus };
}

export function createWebhookWorker() {
  const worker = new Worker<ProcessWebhookJobData>(
    "webhooks",
    async (job) => {
      return await processWebhookJob(job);
    },
    {
      connection: redis,
      concurrency: 5,
    }
  );

  worker.on("failed", (job, err) => {
    logger.error({ jobId: job?.id, err: err.message }, "Webhook worker job failed");
  });

  return worker;
}
