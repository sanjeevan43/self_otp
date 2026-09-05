import crypto from "node:crypto";
import * as argon2 from "@node-rs/argon2";
import { env } from "../../config/env.js";

/**
 * Validates international E.164 phone format (+123456789012).
 */
export function validateE164Phone(phoneNumber: string): boolean {
  const pattern = /^\+[1-9]\d{1,14}$/;
  return pattern.test(phoneNumber.trim());
}

/**
 * Masks an E.164 phone number for logging and UI display.
 * Example: +14155552671 -> +1415***2671
 */
export function maskPhoneNumber(phoneNumber: string): string {
  const cleanPhone = phoneNumber.trim();
  if (cleanPhone.length <= 7) {
    return cleanPhone.slice(0, 3) + "***";
  }
  const prefix = cleanPhone.slice(0, 5);
  const suffix = cleanPhone.slice(-4);
  return `${prefix}***${suffix}`;
}

/**
 * Computes a deterministic HMAC-SHA256 hash of an E.164 phone number.
 */
export function hashPhoneNumber(phoneNumber: string): string {
  return crypto
    .createHmac("sha256", env.PEPPER)
    .update(phoneNumber.trim(), "utf8")
    .digest("hex");
}

/**
 * Computes HMAC-SHA256 of an OTP code.
 */
export function hashOtpCode(otpCode: string): string {
  return crypto
    .createHmac("sha256", env.PEPPER)
    .update(otpCode.trim(), "utf8")
    .digest("hex");
}

/**
 * Constant-time timing-attack safe comparison of OTP hashes.
 */
export function verifyOtpCode(submittedOtp: string, storedOtpHash: string): boolean {
  const submittedHash = hashOtpCode(submittedOtp);
  if (submittedHash.length !== storedOtpHash.length) {
    return false;
  }
  return crypto.timingSafeEqual(
    Buffer.from(submittedHash, "hex"),
    Buffer.from(storedOtpHash, "hex")
  );
}

/**
 * Generates a secure numeric OTP of given length (default: 6 digits).
 */
export function generateOtpCode(length = 6): string {
  const min = 10 ** (length - 1);
  const max = 10 ** length - 1;
  const num = crypto.randomInt(min, max + 1);
  return num.toString();
}

/**
 * Hash an API key using SHA-256 with pepper: SHA256(rawKey:pepper).
 */
export function hashApiKey(rawKey: string): string {
  const combined = `${rawKey}:${env.PEPPER}`;
  return crypto.createHash("sha256").update(combined, "utf8").digest("hex");
}

/**
 * Hash a refresh token using SHA-256 with pepper: SHA256(rawToken:pepper).
 */
export function hashRefreshToken(rawToken: string): string {
  const combined = `${rawToken}:${env.PEPPER}`;
  return crypto.createHash("sha256").update(combined, "utf8").digest("hex");
}

/**
 * Generates a new API key.
 * Format: wotp_live_<32_random_bytes_hex>
 */
export function generateApiKey(): {
  rawKey: string;
  keyPrefix: string;
  keyHash: string;
} {
  const rawSecret = crypto.randomBytes(32).toString("hex");
  const keyPrefix = `wotp_live_${rawSecret.slice(0, 6)}`;
  const rawKey = `wotp_live_${rawSecret}`;
  const keyHash = hashApiKey(rawKey);
  return { rawKey, keyPrefix, keyHash };
}

/**
 * Hash password using Argon2id.
 */
export async function hashPassword(password: string): Promise<string> {
  return argon2.hash(password, {
    memoryCost: 65536,
    timeCost: 3,
    parallelism: 4,
    algorithm: argon2.Algorithm.Argon2id,
  });
}

/**
 * Verify password against Argon2id hash.
 */
export async function verifyPassword(password: string, hash: string): Promise<boolean> {
  try {
    return await argon2.verify(hash, password);
  } catch {
    return false;
  }
}

/**
 * Validates Meta Webhook HMAC-SHA256 signature from 'x-hub-signature-256' header.
 * Header format: "sha256=<signature>"
 */
export function verifyMetaSignature(
  rawBody: string | Buffer,
  signatureHeader: string | undefined,
  appSecret: string
): boolean {
  if (!signatureHeader || !signatureHeader.startsWith("sha256=")) {
    return false;
  }
  const signature = signatureHeader.slice(7);
  const expectedSignature = crypto
    .createHmac("sha256", appSecret)
    .update(rawBody)
    .digest("hex");

  if (signature.length !== expectedSignature.length) {
    return false;
  }

  return crypto.timingSafeEqual(
    Buffer.from(signature, "hex"),
    Buffer.from(expectedSignature, "hex")
  );
}
