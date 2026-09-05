import { redis } from "../plugins/redis.js";

const inMemoryRateLimits = new Map<string, number[]>();
const inMemoryBlockedPhones = new Map<string, number>();
const inMemoryBlockedCustomers = new Map<string, number>();

/**
 * Sliding window log rate limiter using Redis ZSET with memory fallback.
 * Returns: { isLimited: boolean, remaining: number }
 */
export async function isRateLimited(
  key: string,
  maxRequests: number,
  windowSeconds = 60
): Promise<{ isLimited: boolean; remaining: number }> {
  const now = Date.now() / 1000;
  const clearBefore = now - windowSeconds;

  try {
    const pipeline = redis.pipeline();
    pipeline.zremrangebyscore(key, 0, clearBefore);
    pipeline.zadd(key, now, `${now}-${Math.random()}`);
    pipeline.zcard(key);
    pipeline.expire(key, windowSeconds + 5);
    const results = await pipeline.exec();

    if (results && results[2] && results[2][1] !== undefined) {
      const currentCount = Number(results[2][1]);
      const remaining = Math.max(0, maxRequests - currentCount);
      return {
        isLimited: currentCount > maxRequests,
        remaining,
      };
    }
  } catch {
    // Fall back to in-memory store
  }

  const timestamps = (inMemoryRateLimits.get(key) || []).filter((t) => t > clearBefore);
  timestamps.push(now);
  inMemoryRateLimits.set(key, timestamps);

  const currentCount = timestamps.length;
  const remaining = Math.max(0, maxRequests - currentCount);
  return {
    isLimited: currentCount > maxRequests,
    remaining,
  };
}

export async function blockPhoneNumber(phoneHash: string, durationSeconds = 3600): Promise<void> {
  const key = `phone:blocked:${phoneHash}`;
  try {
    await redis.set(key, "1", "EX", durationSeconds);
    return;
  } catch {
    inMemoryBlockedPhones.set(phoneHash, Date.now() / 1000 + durationSeconds);
  }
}

export async function isPhoneBlocked(phoneHash: string): Promise<boolean> {
  const key = `phone:blocked:${phoneHash}`;
  try {
    const exists = await redis.get(key);
    if (exists) return true;
  } catch {
    // Fall back
  }
  const unblockTime = inMemoryBlockedPhones.get(phoneHash) || 0;
  return Date.now() / 1000 < unblockTime;
}

export async function blockCustomer(customerId: string, durationSeconds = 86400): Promise<void> {
  const key = `customer:blocked:${customerId}`;
  try {
    await redis.set(key, "1", "EX", durationSeconds);
    return;
  } catch {
    inMemoryBlockedCustomers.set(customerId, Date.now() / 1000 + durationSeconds);
  }
}

export async function isCustomerBlocked(customerId: string): Promise<boolean> {
  const key = `customer:blocked:${customerId}`;
  try {
    const exists = await redis.get(key);
    if (exists) return true;
  } catch {
    // Fall back
  }
  const unblockTime = inMemoryBlockedCustomers.get(customerId) || 0;
  return Date.now() / 1000 < unblockTime;
}
