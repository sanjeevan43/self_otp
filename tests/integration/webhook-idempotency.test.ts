import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { buildApp } from "../../src/app.js";
import { prisma } from "../../src/plugins/prisma.js";
import { redis } from "../../src/plugins/redis.js";
import { processWebhookJob } from "../../src/queues/workers/webhook.worker.js";
import crypto from "node:crypto";
import type { FastifyInstance } from "fastify";
import type { Job } from "bullmq";

describe("Webhook Ingestion & Idempotent Processing", () => {
  let app: FastifyInstance;

  beforeAll(async () => {
    app = buildApp();
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
    await prisma.$disconnect().catch(() => {});
    redis.disconnect();
  });

  it("Meta webhook GET verification challenge succeeds with correct verify token", async () => {
    const resp = await app.inject({
      method: "GET",
      url: "/v1/webhooks/meta?hub.mode=subscribe&hub.verify_token=mock_verify_token&hub.challenge=my_challenge_code_999",
    });

    expect(resp.statusCode).toBe(200);
    expect(resp.body).toBe("my_challenge_code_999");
  });

  it("Meta webhook GET verification challenge fails with invalid token", async () => {
    const resp = await app.inject({
      method: "GET",
      url: "/v1/webhooks/meta?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=my_challenge_code_999",
    });

    expect(resp.statusCode).toBe(403);
  });

  it("POST /v1/webhooks/meta ingests and deduplicates repeated status webhooks", async () => {
    const uniqueWamid = `wamid.HBgL${crypto.randomBytes(8).toString("hex")}`;
    const payload = {
      object: "whatsapp_business_account",
      entry: [
        {
          id: "WABA_ID_TEST",
          changes: [
            {
              value: {
                messaging_product: "whatsapp",
                statuses: [
                  {
                    id: uniqueWamid,
                    status: "delivered",
                    timestamp: "1693526400",
                    recipient_id: "14155550999",
                  },
                ],
              },
              field: "messages",
            },
          ],
        },
      ],
    };

    // First ingestion -> 200 OK
    const resp1 = await app.inject({
      method: "POST",
      url: "/v1/webhooks/meta",
      payload,
    });
    expect(resp1.statusCode).toBe(200);
    expect(resp1.json()).toEqual({ status: "ok" });

    // Second ingestion with identical payload -> 200 OK (deduplicated)
    const resp2 = await app.inject({
      method: "POST",
      url: "/v1/webhooks/meta",
      payload,
    });
    expect(resp2.statusCode).toBe(200);
    expect(resp2.json()).toEqual({ status: "ok" });

    // Verify only 1 record exists in webhook_events for this external_event_id
    const events = await prisma.webhook_events.findMany({
      where: {
        external_event_id: `${uniqueWamid}_delivered`,
      },
    });
    expect(events).toHaveLength(1);
    expect(events[0].provider).toBe("meta");
    expect(events[0].event_type).toBe("delivered");
  });

  it("Webhook worker processWebhookJob is idempotent across multiple executions", async () => {
    // Create customer and message record
    const customer = await prisma.customers.create({
      data: {
        company_name: "WebhookTest",
        email: `webhook_test_${Date.now()}@example.com`,
        status: "active",
        country_code: "+91",
      },
    });

    const wamid = `wamid.test_${Date.now()}`;
    const message = await prisma.messages.create({
      data: {
        customer_id: customer.id,
        phone_number: "+14155550888",
        provider: "meta",
        provider_message_id: wamid,
        status: "sent",
      },
    });

    const webhookEvent = await prisma.webhook_events.create({
      data: {
        provider: "meta",
        event_type: "delivered",
        external_event_id: `${wamid}_delivered`,
        payload: { id: wamid, status: "delivered" },
        processing_status: "received",
      },
    });

    const fakeJob = {
      id: "job-1",
      data: {
        eventId: webhookEvent.id,
        wamid,
        statusStr: "delivered",
      },
    } as unknown as Job;

    // Run 1st execution
    await processWebhookJob(fakeJob);

    // Run 2nd execution (duplicate worker run)
    await processWebhookJob(fakeJob);

    // Message status must be delivered
    const updatedMessage = await prisma.messages.findUnique({
      where: { id: message.id },
    });
    expect(updatedMessage?.status).toBe("delivered");

    // MessageEvents must contain only ONE 'delivered' event (no duplicates)
    const messageEvents = await prisma.message_events.findMany({
      where: {
        message_id: message.id,
        event_type: "delivered",
      },
    });
    expect(messageEvents).toHaveLength(1);

    // Webhook event is marked processed
    const updatedEvent = await prisma.webhook_events.findUnique({
      where: { id: webhookEvent.id },
    });
    expect(updatedEvent?.processing_status).toBe("processed");
  });
});
