import { Redis } from "ioredis";
import { env } from "../config/env.js";

declare global {
  // eslint-disable-next-line no-var
  var redisClient: Redis | undefined;
}

export const redis =
  global.redisClient ||
  new Redis(env.REDIS_URL, {
    maxRetriesPerRequest: null, // Required by BullMQ
    enableReadyCheck: false,
    enableOfflineQueue: false,
    connectTimeout: 1000,
    retryStrategy(times) {
      if (times > 3 && env.NODE_ENV === "test") {
        return null; // Stop reconnecting in test if offline
      }
      return Math.min(times * 100, 2000);
    },
    lazyConnect: true,
  });

redis.on("error", () => {
  // Silently handle connection errors when Redis is offline
});

if (env.NODE_ENV !== "production") {
  global.redisClient = redis;
}
