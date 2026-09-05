import type { FastifyPluginAsync } from "fastify";
import { z } from "zod";
import { prisma } from "../../plugins/prisma.js";
import { env } from "../../config/env.js";
import {
  hashOtpCode,
  hashPhoneNumber,
  maskPhoneNumber,
  validateE164Phone,
} from "../../common/utils/crypto.js";
import {
  isCustomerBlocked,
  isPhoneBlocked,
  isRateLimited,
} from "../../middleware/rate-limit.js";
import {
  getIdempotentResponse,
  saveIdempotentResponse,
} from "../../middleware/idempotency.js";
import { OTPService } from "./otp.service.js";
import { WalletService } from "../wallet/wallet.service.js";
import { otpQueue } from "../../queues/queue.js";
import { whatsappProvider } from "../../providers/whatsapp/provider-factory.js";
import {
  AppError,
  ForbiddenError,
  RateLimitError,
} from "../../common/errors/app-error.js";

import { toJsonSchema } from "../../common/utils/schema.js";

const sendOtpSchema = z.object({
  phone_number: z
    .string()
    .trim()
    .describe("Target phone number in E.164 international format (e.g. +14155552671)")
    .refine((val) => validateE164Phone(val), {
      message: "Phone number must be in valid E.164 format (e.g. +14155552671)",
    }),
  otp: z
    .string()
    .trim()
    .describe("Optional custom numeric OTP (4-8 digits). If omitted, a cryptographically secure 6-digit OTP is generated.")
    .refine((val) => /^\d{4,8}$/.test(val), {
      message: "Custom OTP must be numeric and between 4 and 8 digits.",
    })
    .optional(),
  ttl_seconds: z.coerce
    .number()
    .min(60)
    .max(3600)
    .default(300)
    .describe("OTP expiry duration in seconds (between 60 and 3600, default: 300)"),
  template_name: z
    .string()
    .default("otp_auth_v1")
    .describe("Meta WhatsApp registered template name (default: otp_auth_v1)"),
  language_code: z
    .string()
    .default("en_US")
    .describe("Language code for Meta template (default: en_US)"),
});

const verifyOtpSchema = z.object({
  phone_number: z
    .string()
    .trim()
    .describe("Phone number in E.164 format that received the OTP")
    .refine((val) => validateE164Phone(val), {
      message: "Phone number must be in valid E.164 format",
    }),
  code: z
    .string()
    .trim()
    .describe("Numeric OTP code to verify")
    .refine((val) => /^\d+$/.test(val), {
      message: "OTP code must be numeric",
    }),
});

const resendOtpSchema = z.object({
  request_id: z
    .string()
    .min(1, { message: "Unique OTP request ID to resend" })
    .describe("Original OTP request ID to resend"),
});

export const otpRoutes: FastifyPluginAsync = async (fastify) => {
  // All OTP endpoints require API key auth
  fastify.addHook("preHandler", fastify.authenticateApiKey);

  // POST /v1/otp/send (202 Accepted)
  fastify.post(
    "/send",
    {
      schema: {
        tags: ["OTP Verification"],
        summary: "Send WhatsApp OTP",
        description: "Generates, debits wallet credits, and queues a WhatsApp OTP message to the recipient.",
        security: [{ ApiKeyAuth: [] }],
        headers: {
          type: "object",
          properties: {
            "x-api-key": {
              type: "string",
              description: "Customer API Key (e.g. wotp_live_...)",
            },
            "idempotency-key": {
              type: "string",
              description: "Optional idempotency key to prevent duplicate sends",
            },
          },
          required: ["x-api-key"],
        },
        body: toJsonSchema(sendOtpSchema),
      },
    },
    async (request, reply) => {
      const parseResult = sendOtpSchema.safeParse(request.body || {});
      if (!parseResult.success) {
        throw parseResult.error;
      }
      const body = parseResult.data;

      const apiKey = request.apiKey!;
      const application = request.application!;
      const customer = request.customer!;

    const phoneHash = hashPhoneNumber(body.phone_number);
    const maskedPhone = maskPhoneNumber(body.phone_number);
    const clientIp = request.ip || "127.0.0.1";
    const idempotencyKey = request.headers["idempotency-key"] as string | undefined;

    // 1. Customer Abuse Protection
    const customerBlocked = await isCustomerBlocked(customer.id);
    if (customerBlocked || customer.status !== "active") {
      throw new ForbiddenError(
        "Customer account is suspended or blocked due to policy violations.",
        "CUSTOMER_BLOCKED"
      );
    }

    // 2. Temporary Phone Blocking
    const phoneBlocked = await isPhoneBlocked(phoneHash);
    if (phoneBlocked) {
      throw new ForbiddenError(
        "This phone number is temporarily blocked due to excessive failed attempts or abuse.",
        "PHONE_BLOCKED"
      );
    }

    // 3. Duplicate Request / Idempotency Check
    if (idempotencyKey) {
      const cached = await getIdempotentResponse(
        application.id,
        idempotencyKey,
        "/v1/otp/send"
      );
      if (cached) {
        return reply.status(200).send(cached);
      }
    }

    // 4. IP Rate Limiting - Max 10 per minute
    const { isLimited: ipLimited } = await isRateLimited(
      `ip:${clientIp}:otp:send`,
      10,
      60
    );
    if (ipLimited) {
      throw new RateLimitError(
        "Too many requests from this IP address. Please slow down.",
        "IP_RATE_LIMITED"
      );
    }

    // 5. Phone-Number Rate Limiting - Max 3 per 10 minutes
    const { isLimited: phoneLimited } = await isRateLimited(
      `phone:${phoneHash}:otp:send`,
      3,
      600
    );
    if (phoneLimited) {
      throw new RateLimitError(
        "Too many OTP requests for this phone number. Please wait.",
        "PHONE_RATE_LIMITED"
      );
    }

    // 6. Customer Rate Limiting - Max 60 per minute
    const { isLimited: custLimited } = await isRateLimited(
      `customer:${customer.id}:otp:send`,
      60,
      60
    );
    if (custLimited) {
      throw new RateLimitError("Customer rate limit exceeded.", "CUSTOMER_RATE_LIMITED");
    }

    // 7. API-Key Rate Limiting
    const { isLimited: keyLimited } = await isRateLimited(
      `api_key:${apiKey.id}:otp:send`,
      env.DEFAULT_API_KEY_RATE_LIMIT_RPS,
      1
    );
    if (keyLimited) {
      throw new RateLimitError("API key rate limit exceeded.", "API_KEY_RATE_LIMITED");
    }

    // 8. 60-second cooldown per target phone number
    const inCooldown = await OTPService.checkPhoneCooldown(phoneHash);
    if (inCooldown) {
      throw new RateLimitError(
        "An OTP was recently requested for this phone number. Please wait 60 seconds.",
        "COOLDOWN_ACTIVE"
      );
    }

    // Determine OTP code and request_id
    const otpCode = body.otp || OTPService.generateOtpDigits(6);
    const requestId = OTPService.generateRequestId();
    const cost = env.OTP_CREDIT_COST;
    const expiresAt = new Date(Date.now() + body.ttl_seconds * 1000);

    // Create OTPRequest record in DB
    const otpRecord = await prisma.otp_requests.create({
      data: {
        customer_id: customer.id,
        application_id: application.id,
        api_key_id: apiKey.id,
        request_id: requestId,
        phone_number: body.phone_number,
        otp_hash: hashOtpCode(otpCode),
        status: "created",
        expires_at: expiresAt,
        attempts: 0,
        max_attempts: env.OTP_MAX_VERIFY_ATTEMPTS,
      },
    });

    // Atomic Wallet Debit (Throws HTTP 402 if balance insufficient)
    await WalletService.deductCreditsAtomic(
      customer.id,
      cost,
      "otp_request",
      otpRecord.id
    );

    // Store OTP in Redis/Memory
    await OTPService.storeOtp(
      phoneHash,
      otpCode,
      requestId,
      application.id,
      body.ttl_seconds
    );

    // Set 60-second phone cooldown
    await OTPService.setPhoneCooldown(phoneHash);

    // Dispatch to BullMQ Queue (with async fallback if broker is offline)
    try {
      await otpQueue.add("send_whatsapp_otp", {
        otpRequestDbId: otpRecord.id,
        requestId,
        phoneNumber: body.phone_number,
        otpCode,
        templateName: body.template_name,
        languageCode: body.language_code,
        customerId: customer.id,
        costCredits: cost,
      });
    } catch {
      // Fallback matching Python app/api/v1/otp.py line 230
      const res = await whatsappProvider.sendOtp(
        body.phone_number,
        otpCode,
        body.template_name,
        body.language_code
      );
      if (res.success) {
        await prisma.otp_requests.update({
          where: { id: otpRecord.id },
          data: { status: "sent" },
        });
      } else {
        await prisma.otp_requests.update({
          where: { id: otpRecord.id },
          data: { status: "failed" },
        });
        await WalletService.refundCredits(
          customer.id,
          cost,
          "otp_request_failure",
          requestId,
          res.errorMessage || "Delivery failed"
        );
      }
    }

    const responseData = {
      status: "success",
      data: {
        request_id: requestId,
        phone_number: maskedPhone,
        delivery_status: "created",
        expires_at: expiresAt.toISOString(),
        cost_credits: cost,
      },
    };

    if (idempotencyKey) {
      await saveIdempotentResponse(
        application.id,
        customer.id,
        idempotencyKey,
        "/v1/otp/send",
        body,
        responseData,
        202
      );
    }

    return reply.status(202).send(responseData);
  });

  // POST /v1/otp/verify (200 OK)
  fastify.post(
    "/verify",
    {
      schema: {
        tags: ["OTP Verification"],
        summary: "Verify WhatsApp OTP",
        description: "Validates the numeric OTP code against Redis/database, tracking verification attempts and status.",
        security: [{ ApiKeyAuth: [] }],
        headers: {
          type: "object",
          properties: {
            "x-api-key": {
              type: "string",
              description: "Customer API Key (e.g. wotp_live_...)",
            },
          },
          required: ["x-api-key"],
        },
        body: toJsonSchema(verifyOtpSchema),
      },
    },
    async (request, reply) => {
      const parseResult = verifyOtpSchema.safeParse(request.body || {});
      if (!parseResult.success) {
        throw parseResult.error;
      }
      const body = parseResult.data;
      const application = request.application!;

      const result = await OTPService.verifyOtp(
        body.phone_number,
        body.code,
        application.id,
        request.ip,
        request.headers["user-agent"]
      );

      return reply.status(200).send({
        status: "success",
        data: result,
      });
    }
  );

  // POST /v1/otp/resend (202 Accepted)
  fastify.post(
    "/resend",
    {
      schema: {
        tags: ["OTP Verification"],
        summary: "Resend WhatsApp OTP",
        description: "Resends a fresh OTP code for an existing active OTP request subject to a 60-second cooldown.",
        security: [{ ApiKeyAuth: [] }],
        headers: {
          type: "object",
          properties: {
            "x-api-key": {
              type: "string",
              description: "Customer API Key (e.g. wotp_live_...)",
            },
          },
          required: ["x-api-key"],
        },
        body: toJsonSchema(resendOtpSchema),
      },
    },
    async (request, reply) => {
      const parseResult = resendOtpSchema.safeParse(request.body || {});
      if (!parseResult.success) {
        throw parseResult.error;
      }
      const body = parseResult.data;
      const application = request.application!;
      const customer = request.customer!;

      const otpRecord = await prisma.otp_requests.findFirst({
        where: {
          request_id: body.request_id,
          application_id: application.id,
        },
      });

      if (!otpRecord) {
        throw new AppError(
          404,
          `OTP request with ID '${body.request_id}' was not found.`,
          "OTP_NOT_FOUND"
        );
      }

      if (otpRecord.status === "verified") {
        throw new AppError(
          400,
          "This OTP has already been successfully verified.",
          "ALREADY_VERIFIED"
        );
      }

      const now = new Date();
      if (now > otpRecord.expires_at) {
        await prisma.otp_requests.update({
          where: { id: otpRecord.id },
          data: { status: "expired" },
        });
        throw new AppError(
          400,
          "The OTP request has expired. Please request a new OTP.",
          "OTP_EXPIRED"
        );
      }

      // Check phone cooldown
      const phoneHash = hashPhoneNumber(otpRecord.phone_number);
      const inCooldown = await OTPService.checkPhoneCooldown(phoneHash);
      if (inCooldown) {
        throw new RateLimitError(
          "An OTP was recently sent to this phone number. Please wait 60 seconds.",
          "COOLDOWN_ACTIVE"
        );
      }

      const newOtpCode = OTPService.generateOtpDigits(6);
      const cost = env.OTP_CREDIT_COST;

      // Deduct wallet credits for resend
      await WalletService.deductCreditsAtomic(
        customer.id,
        cost,
        "otp_resend",
        otpRecord.request_id
      );

      let ttlSeconds = Math.floor((otpRecord.expires_at.getTime() - now.getTime()) / 1000);
      let newExpiresAt = otpRecord.expires_at;
      if (ttlSeconds < 60) {
        ttlSeconds = 300;
        newExpiresAt = new Date(now.getTime() + 300 * 1000);
      }

      await prisma.otp_requests.update({
        where: { id: otpRecord.id },
        data: {
          otp_hash: hashOtpCode(newOtpCode),
          expires_at: newExpiresAt,
        },
      });

      await OTPService.storeOtp(
        phoneHash,
        newOtpCode,
        otpRecord.request_id,
        application.id,
        ttlSeconds
      );
      await OTPService.setPhoneCooldown(phoneHash);

      // Queue resend message (with async fallback if broker is offline)
      try {
        await otpQueue.add("send_whatsapp_otp", {
          otpRequestDbId: otpRecord.id,
          requestId: otpRecord.request_id,
          phoneNumber: otpRecord.phone_number,
          otpCode: newOtpCode,
          templateName: "otp_auth_v1",
          languageCode: "en_US",
          customerId: customer.id,
          costCredits: cost,
        });
      } catch {
        const res = await whatsappProvider.sendOtp(
          otpRecord.phone_number,
          newOtpCode,
          "otp_auth_v1",
          "en_US"
        );
        if (res.success) {
          await prisma.otp_requests.update({
            where: { id: otpRecord.id },
            data: { status: "sent" },
          });
        }
      }

      return reply.status(202).send({
        status: "success",
        data: {
          request_id: otpRecord.request_id,
          phone_number: maskPhoneNumber(otpRecord.phone_number),
          delivery_status: otpRecord.status,
          expires_at: newExpiresAt.toISOString(),
          cost_credits: cost,
          resend_count: 1,
        },
      });
    }
  );

  // GET /v1/otp/:request_id (200 OK)
  fastify.get(
    "/:request_id",
    {
      schema: {
        tags: ["OTP Verification"],
        summary: "Get OTP request status",
        description: "Retrieves status, timestamps, and delivery details for a given OTP request ID.",
        security: [{ ApiKeyAuth: [] }],
        params: {
          type: "object",
          properties: {
            request_id: {
              type: "string",
              description: "The unique OTP request ID",
            },
          },
          required: ["request_id"],
        },
        headers: {
          type: "object",
          properties: {
            "x-api-key": {
              type: "string",
              description: "Customer API Key (e.g. wotp_live_...)",
            },
          },
          required: ["x-api-key"],
        },
      },
    },
    async (request, reply) => {
      const { request_id } = request.params as { request_id: string };
      const application = request.application!;

      const result = await OTPService.getOtpStatus(request_id, application.id);
      return reply.status(200).send({
        status: "success",
        data: result,
      });
    }
  );
};
