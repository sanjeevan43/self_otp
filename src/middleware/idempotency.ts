import crypto from "node:crypto";
import { prisma } from "../plugins/prisma.js";
import { redis } from "../plugins/redis.js";
import type { Prisma } from "@prisma/client";

const inMemoryIdempotencyStore = new Map<string, any>();

export function hashRequestBody(bodyData: unknown): string {
  const sortedJson = JSON.stringify(bodyData, Object.keys(bodyData || {}).sort());
  return crypto.createHash("sha256").update(sortedJson, "utf8").digest("hex");
}

export async function getIdempotentResponse(
  applicationId: string,
  idempotencyKey: string,
  endpoint: string
): Promise<any | null> {
  const cacheKey = `idempotency:${applicationId}:${idempotencyKey}`;

  try {
    const cachedJson = await redis.get(cacheKey);
    if (cachedJson) {
      return JSON.parse(cachedJson);
    }
  } catch {
    // Fall back to memory or db
  }

  if (inMemoryIdempotencyStore.has(cacheKey)) {
    return inMemoryIdempotencyStore.get(cacheKey);
  }

  // Database fallback
  try {
    const record = await prisma.idempotency_keys.findFirst({
      where: {
        application_id: applicationId,
        idempotency_key: idempotencyKey,
        endpoint,
      },
    });

    if (record && record.response_body) {
      return record.response_body;
    }
  } catch {
    // Database query failed
  }

  return null;
}

export async function saveIdempotentResponse(
  applicationId: string,
  customerId: string,
  idempotencyKey: string,
  endpoint: string,
  requestBody: unknown,
  responseBody: any,
  statusCode = 200,
  ttlSeconds = 86400,
  txPrisma?: Prisma.TransactionClient
): Promise<void> {
  const cacheKey = `idempotency:${applicationId}:${idempotencyKey}`;
  const reqHash = hashRequestBody(requestBody);

  try {
    await redis.set(cacheKey, JSON.stringify(responseBody), "EX", ttlSeconds);
  } catch {
    // Fall back
  }

  inMemoryIdempotencyStore.set(cacheKey, responseBody);

  const client = txPrisma || prisma;
  try {
    await client.idempotency_keys.create({
      data: {
        customer_id: customerId,
        application_id: applicationId,
        idempotency_key: idempotencyKey,
        endpoint,
        request_hash: reqHash,
        response_status: statusCode,
        response_body: responseBody,
      },
    });
  } catch (err) {
    // Ignore duplicate key collision if already saved
  }
}
