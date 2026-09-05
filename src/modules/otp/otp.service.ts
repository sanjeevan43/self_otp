import crypto from "node:crypto";
import { prisma } from "../../plugins/prisma.js";
import { redis } from "../../plugins/redis.js";
import { env } from "../../config/env.js";
import {
  hashOtpCode,
  hashPhoneNumber,
  maskPhoneNumber,
  verifyOtpCode,
} from "../../common/utils/crypto.js";
import { AppError } from "../../common/errors/app-error.js";
import { blockPhoneNumber } from "../../middleware/rate-limit.js";

const inMemoryOtpStore = new Map<string, any>();
const inMemoryCooldownStore = new Map<string, number>();

export class OTPService {
  static generateOtpDigits(length = 6): string {
    const min = 10 ** (length - 1);
    const max = 10 ** length - 1;
    return crypto.randomInt(min, max + 1).toString();
  }

  static generateRequestId(): string {
    return `req_${crypto.randomBytes(12).toString("hex")}`;
  }

  static async checkPhoneCooldown(phoneHash: string): Promise<boolean> {
    const key = `otp:cooldown:${phoneHash}`;
    try {
      const exists = await redis.get(key);
      if (exists) return true;
    } catch {
      // Fall back
    }
    const lastTime = inMemoryCooldownStore.get(phoneHash) || 0;
    return Date.now() / 1000 - lastTime < env.OTP_COOLDOWN_SECONDS;
  }

  static async setPhoneCooldown(phoneHash: string): Promise<void> {
    const key = `otp:cooldown:${phoneHash}`;
    try {
      await redis.set(key, "1", "EX", env.OTP_COOLDOWN_SECONDS);
      return;
    } catch {
      // Fall back
    }
    inMemoryCooldownStore.set(phoneHash, Date.now() / 1000);
  }

  static async storeOtp(
    phoneHash: string,
    otpCode: string,
    requestId: string,
    applicationId: string,
    ttlSeconds: number
  ): Promise<void> {
    const key = `otp:store:${applicationId}:${phoneHash}`;
    const hashedOtp = hashOtpCode(otpCode);
    const data = {
      otp_hash: hashedOtp,
      request_id: requestId,
      attempts: 0,
      created_at: Date.now() / 1000,
    };

    try {
      await redis.set(key, JSON.stringify(data), "EX", ttlSeconds);
      return;
    } catch {
      // Fall back
    }

    inMemoryOtpStore.set(key, {
      ...data,
      expires_at: Date.now() / 1000 + ttlSeconds,
    });
  }

  static async verifyOtp(
    phoneNumber: string,
    submittedCode: string,
    applicationId: string,
    ipAddress?: string | null,
    userAgent?: string | null
  ) {
    const phoneHash = hashPhoneNumber(phoneNumber);
    const key = `otp:store:${applicationId}:${phoneHash}`;

    let storedData: any = null;

    try {
      const rawJson = await redis.get(key);
      if (rawJson) {
        storedData = JSON.parse(rawJson);
      }
    } catch {
      // Fall back
    }

    if (!storedData) {
      const data = inMemoryOtpStore.get(key);
      if (data && Date.now() / 1000 <= data.expires_at) {
        storedData = data;
      }
    }

    if (!storedData) {
      throw new AppError(
        400,
        "The verification code has expired or was not requested.",
        "OTP_EXPIRED"
      );
    }

    const storedOtpHash = storedData.otp_hash;
    const requestId = storedData.request_id;
    const attempts = (storedData.attempts || 0) + 1;

    // Fetch DB record
    const otpRecord = await prisma.otp_requests.findFirst({
      where: {
        request_id: requestId,
        application_id: applicationId,
      },
    });

    const isValid = verifyOtpCode(submittedCode, storedOtpHash);

    if (!isValid) {
      storedData.attempts = attempts;

      if (otpRecord) {
        await prisma.otp_requests.update({
          where: { id: otpRecord.id },
          data: { attempts },
        });

        await prisma.otp_verifications.create({
          data: {
            otp_request_id: otpRecord.id,
            attempt_number: attempts,
            result: "incorrect",
            ip_address: ipAddress || null,
            user_agent: userAgent || null,
          },
        });
      }

      if (attempts >= env.OTP_MAX_VERIFY_ATTEMPTS) {
        if (otpRecord) {
          await prisma.otp_requests.update({
            where: { id: otpRecord.id },
            data: { status: "expired" },
          });
        }

        // Auto-block phone number for 1 hour
        await blockPhoneNumber(phoneHash, 3600);

        try {
          await redis.del(key);
        } catch {}
        inMemoryOtpStore.delete(key);

        throw new AppError(
          400,
          "Maximum verification attempts exceeded. Please request a new OTP.",
          "MAX_ATTEMPTS_EXCEEDED"
        );
      }

      // Update remaining attempts in Redis
      try {
        const ttl = await redis.ttl(key);
        if (ttl > 0) {
          await redis.set(key, JSON.stringify(storedData), "EX", ttl);
        }
      } catch {}

      const remaining = env.OTP_MAX_VERIFY_ATTEMPTS - attempts;
      throw new AppError(
        400,
        "The verification code is incorrect.",
        "INVALID_OTP",
        { remaining_attempts: remaining }
      );
    }

    // Verification Successful!
    try {
      await redis.del(key);
    } catch {}
    inMemoryOtpStore.delete(key);

    const verifiedTime = new Date();
    if (otpRecord) {
      await prisma.otp_requests.update({
        where: { id: otpRecord.id },
        data: {
          status: "verified",
          attempts,
          verified_at: verifiedTime,
        },
      });

      await prisma.otp_verifications.create({
        data: {
          otp_request_id: otpRecord.id,
          attempt_number: attempts,
          result: "correct",
          ip_address: ipAddress || null,
          user_agent: userAgent || null,
        },
      });
    }

    return {
      verified: true,
      request_id: requestId,
      phone_number: maskPhoneNumber(phoneNumber),
      verified_at: verifiedTime.toISOString(),
      message: "OTP verified successfully",
    };
  }

  static async getOtpStatus(requestId: string, applicationId: string) {
    const otpRecord = await prisma.otp_requests.findFirst({
      where: {
        request_id: requestId,
        application_id: applicationId,
      },
    });

    if (!otpRecord) {
      throw new AppError(
        404,
        `OTP request with ID '${requestId}' was not found.`,
        "OTP_NOT_FOUND"
      );
    }

    const now = new Date();
    let currentStatus = otpRecord.status;

    if (
      currentStatus !== "verified" &&
      currentStatus !== "expired" &&
      currentStatus !== "failed" &&
      now > otpRecord.expires_at
    ) {
      currentStatus = "expired";
      await prisma.otp_requests.update({
        where: { id: otpRecord.id },
        data: { status: "expired" },
      });
    }

    return {
      request_id: otpRecord.request_id,
      phone_number: maskPhoneNumber(otpRecord.phone_number),
      status: currentStatus,
      attempts: otpRecord.attempts,
      max_attempts: otpRecord.max_attempts,
      expires_at: otpRecord.expires_at.toISOString(),
      created_at: otpRecord.created_at.toISOString(),
      verified_at: otpRecord.verified_at ? otpRecord.verified_at.toISOString() : null,
    };
  }
}
