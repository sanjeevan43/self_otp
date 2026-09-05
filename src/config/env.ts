import "dotenv/config";
import { z } from "zod";

const envSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  PORT: z.coerce.number().default(8000),
  HOST: z.string().default("0.0.0.0"),
  
  // Database & Redis
  DATABASE_URL: z.string().min(1),
  POSTGRES_PRISMA_URL: z.string().optional(),
  REDIS_URL: z.string().default("redis://localhost:6379/0"),

  // Security & JWT
  SECRET_KEY: z.string().default("super_secret_dev_key_1234567890_1234567890_1234567890"),
  PEPPER: z.string().default("dev_pepper_secret_12345"),
  ACCESS_TOKEN_EXPIRE_MINUTES: z.coerce.number().default(15),
  REFRESH_TOKEN_EXPIRE_DAYS: z.coerce.number().default(7),

  // Provider configuration - Explicit, no silent fallback
  WHATSAPP_PROVIDER: z.enum(["meta", "mock"]).default("meta"),

  // Meta WhatsApp Cloud API
  META_API_VERSION: z.string().default("v20.0"),
  META_PHONE_NUMBER_ID: z.string().default("100000000000000"),
  META_WABA_ID: z.string().default("200000000000000"),
  META_ACCESS_TOKEN: z.string().default("mock_meta_access_token"),
  META_APP_SECRET: z.string().default("mock_meta_app_secret"),
  META_WEBHOOK_VERIFY_TOKEN: z.string().default("mock_verify_token"),

  // OTP & Rate Limiting Defaults
  DEFAULT_API_KEY_RATE_LIMIT_RPS: z.coerce.number().default(60),
  OTP_EXPIRY_SECONDS: z.coerce.number().default(300),
  OTP_COOLDOWN_SECONDS: z.coerce.number().default(60),
  OTP_MAX_VERIFY_ATTEMPTS: z.coerce.number().default(3),
  OTP_CREDIT_COST: z.coerce.number().default(1.0000),
});

export type Env = z.infer<typeof envSchema>;

function loadEnv(): Env {
  const parsed = envSchema.safeParse(process.env);
  if (!parsed.success) {
    console.error("Invalid environment variables:", parsed.error.format());
    throw new Error("Invalid environment variables");
  }
  return parsed.data;
}

export const env = loadEnv();
