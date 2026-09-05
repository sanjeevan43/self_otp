import { handleCors, jsonResponse, errorResponse } from "../_shared/cors.ts";
import { getAdminClient } from "../_shared/supabase.ts";
import { generateOtp, hashApiKey, hashOtp } from "../_shared/crypto.ts";
import { sendWhatsAppOtp } from "../_shared/meta.ts";
import { openApiSpec, renderSwaggerHtml } from "../_shared/docs.ts";

const PEPPER = Deno.env.get("PEPPER") || "dev_pepper_secret_12345";
const OTP_EXPIRY_SECONDS = parseInt(Deno.env.get("OTP_EXPIRY_SECONDS") || "300", 10);
const OTP_COOLDOWN_SECONDS = parseInt(Deno.env.get("OTP_COOLDOWN_SECONDS") || "60", 10);
const OTP_CREDIT_COST = parseFloat(Deno.env.get("OTP_CREDIT_COST") || "1.0000");

// Helper to authenticate API Key
async function authenticateApiKey(supabase: any, req: Request) {
  const apiKey = req.headers.get("x-api-key") || req.headers.get("X-API-Key");
  if (!apiKey) {
    return { error: "Missing x-api-key header", status: 401 };
  }

  const keyHash = await hashApiKey(apiKey, PEPPER);

  const { data: keyRecord, error } = await supabase
    .from("api_keys")
    .select("id, customer_id, application_id, status, environment, expires_at")
    .eq("key_hash", keyHash)
    .single();

  if (error || !keyRecord) {
    return { error: "Invalid API key", status: 401 };
  }

  if (keyRecord.status !== "active") {
    return { error: `API key is ${keyRecord.status}`, status: 403 };
  }

  if (keyRecord.expires_at && new Date(keyRecord.expires_at) < new Date()) {
    return { error: "API key has expired", status: 403 };
  }

  // Asynchronously record last_used_at
  supabase
    .from("api_keys")
    .update({ last_used_at: new Date().toISOString() })
    .eq("id", keyRecord.id)
    .then();

  return { keyRecord };
}

Deno.serve(async (req: Request) => {
  const corsResponse = handleCors(req);
  if (corsResponse) return corsResponse;

  const url = new URL(req.url);
  const pathParts = url.pathname.split("/").filter(Boolean);
  const action = pathParts[pathParts.length - 1] || url.searchParams.get("action") || "";

  const supabase = getAdminClient();

  try {
    // -------------------------------------------------------------
    // Interactive Documentation & OpenAPI Spec
    // -------------------------------------------------------------
    if (req.method === "GET" && (action === "docs" || (action === "otp" && req.headers.get("accept")?.includes("text/html")))) {
      return new Response(renderSwaggerHtml(), {
        status: 200,
        headers: { "Content-Type": "text/html; charset=utf-8" },
      });
    }

    if (req.method === "GET" && action === "openapi.json") {
      return jsonResponse(openApiSpec, 200);
    }

    // Root GET health check (direct JSON visit)
    if (req.method === "GET" && (action === "otp" || action === "")) {
      return jsonResponse({
        status: "healthy",
        service: "WhatsApp OTP API Platform",
        version: "1.0.0",
        message: "API is online and operational. Send POST /send with header 'x-api-key' to dispatch OTPs.",
        docs_url: "https://ymstmdjdgwnmtxgurhyn.supabase.co/functions/v1/otp/docs",
        endpoints: {
          documentation: "GET /functions/v1/otp/docs",
          openapi: "GET /functions/v1/otp/openapi.json",
          send: "POST /functions/v1/otp/send",
          verify: "POST /functions/v1/otp/verify",
          resend: "POST /functions/v1/otp/resend",
          status: "GET /functions/v1/otp/status?request_id=...",
        },
        timestamp: new Date().toISOString(),
      }, 200);
    }

    // -------------------------------------------------------------
    // 1. GET /status (or ?request_id=...)
    // -------------------------------------------------------------
    if (req.method === "GET" && (action === "status" || url.searchParams.has("request_id"))) {
      const auth = await authenticateApiKey(supabase, req);
      if (auth.error) return errorResponse(auth.error, "UNAUTHORIZED", auth.status);

      const requestId = url.searchParams.get("request_id") || (action !== "status" ? action : null);
      if (!requestId) {
        return errorResponse("request_id is required", "VALIDATION_ERROR", 400);
      }

      // Check by request_id or UUID id
      const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestId);
      let query = supabase
        .from("otp_requests")
        .select("id, request_id, phone_number, status, attempts, max_attempts, expires_at, verified_at, created_at")
        .eq("customer_id", auth.keyRecord.customer_id);

      if (isUuid) {
        query = query.or(`id.eq.${requestId},request_id.eq.${requestId}`);
      } else {
        query = query.eq("request_id", requestId);
      }

      const { data: otp, error } = await query.single();

      if (error || !otp) {
        return errorResponse("OTP request not found", "NOT_FOUND", 404);
      }

      return jsonResponse({ success: true, data: otp });
    }

    // -------------------------------------------------------------
    // 2. POST /send
    // -------------------------------------------------------------
    if (req.method === "POST" && (action === "send" || action === "otp")) {
      const auth = await authenticateApiKey(supabase, req);
      if (auth.error) return errorResponse(auth.error, "UNAUTHORIZED", auth.status);

      const body = await req.json().catch(() => ({}));
      const phoneNumber = body.phone_number || body.recipient_phone;
      const idempotencyKey = req.headers.get("idempotency-key") || body.idempotency_key;

      if (!phoneNumber) {
        return errorResponse("phone_number is required", "VALIDATION_ERROR", 400);
      }

      // Check Idempotency Key
      if (idempotencyKey) {
        const { data: cached } = await supabase
          .from("idempotency_keys")
          .select("response_code, response_body, expires_at")
          .eq("customer_id", auth.keyRecord.customer_id)
          .eq("key", idempotencyKey)
          .single();

        if (cached && new Date(cached.expires_at) > new Date()) {
          return jsonResponse(cached.response_body, cached.response_code);
        }
      }

      // Atomically deduct credit
      const { data: deduction, error: deductError } = await supabase.rpc(
        "deduct_wallet_credit",
        {
          p_customer_id: auth.keyRecord.customer_id,
          p_amount: OTP_CREDIT_COST,
          p_description: `WhatsApp OTP to ${phoneNumber}`,
        }
      );

      if (deductError || !deduction?.success) {
        return errorResponse(
          deduction?.error || "Insufficient wallet balance to send OTP",
          "INSUFFICIENT_FUNDS",
          402
        );
      }

      // Generate secure OTP
      const otpLength = body.length || 6;
      const otpCode = generateOtp(otpLength);
      const otpHash = await hashOtp(otpCode, PEPPER);
      const requestId = `wotp_${crypto.randomUUID().replace(/-/g, "").substring(0, 24)}`;
      const expiresAt = new Date(Date.now() + OTP_EXPIRY_SECONDS * 1000).toISOString();

      // Dispatch WhatsApp message via Meta Cloud API
      const metaResult = await sendWhatsAppOtp({
        recipientPhone: phoneNumber,
        otpCode,
        templateName: body.template_name,
        language: body.language,
      });

      // Insert record into otp_requests
      const { data: inserted, error: insertError } = await supabase
        .from("otp_requests")
        .insert({
          customer_id: auth.keyRecord.customer_id,
          application_id: auth.keyRecord.application_id,
          api_key_id: auth.keyRecord.id,
          request_id: requestId,
          phone_number: phoneNumber,
          otp_hash: otpHash,
          status: metaResult.success ? "sent" : "failed",
          expires_at: expiresAt,
          attempts: 0,
          max_attempts: 5,
        })
        .select("id, request_id, phone_number, status, expires_at, created_at")
        .single();

      if (insertError || !inserted) {
        // Refund credit on error
        await supabase.rpc("refund_wallet_credit", {
          p_customer_id: auth.keyRecord.customer_id,
          p_amount: OTP_CREDIT_COST,
        });
        return errorResponse(insertError?.message || "Failed to record OTP request", "SERVER_ERROR", 500);
      }

      // Also create an audit log and message log
      if (metaResult.messageId) {
        supabase
          .from("messages")
          .insert({
            customer_id: auth.keyRecord.customer_id,
            otp_request_id: inserted.id,
            provider: "meta",
            provider_message_id: metaResult.messageId,
            phone_number: phoneNumber,
            message_type: "authentication",
            status: metaResult.success ? "sent" : "failed",
          })
          .then();
      }

      const responsePayload = {
        success: true,
        data: {
          id: inserted.id,
          request_id: inserted.request_id,
          phone_number: inserted.phone_number,
          status: inserted.status,
          expires_at: inserted.expires_at,
          cooldown_seconds: OTP_COOLDOWN_SECONDS,
        },
      };

      // Cache idempotency response if key provided
      if (idempotencyKey) {
        supabase
          .from("idempotency_keys")
          .upsert({
            customer_id: auth.keyRecord.customer_id,
            application_id: auth.keyRecord.application_id,
            key: idempotencyKey,
            response_code: 200,
            response_body: responsePayload,
            expires_at: new Date(Date.now() + 86400 * 1000).toISOString(),
          })
          .then();
      }

      return jsonResponse(responsePayload, 200);
    }

    // -------------------------------------------------------------
    // 3. POST /verify
    // -------------------------------------------------------------
    if (req.method === "POST" && action === "verify") {
      const auth = await authenticateApiKey(supabase, req);
      if (auth.error) return errorResponse(auth.error, "UNAUTHORIZED", auth.status);

      const body = await req.json().catch(() => ({}));
      const requestId = body.request_id || body.id;
      const code = body.code || body.otp;

      if (!requestId || !code) {
        return errorResponse("request_id and code are required", "VALIDATION_ERROR", 400);
      }

      const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestId);
      let query = supabase
        .from("otp_requests")
        .select("*")
        .eq("customer_id", auth.keyRecord.customer_id);

      if (isUuid) {
        query = query.or(`id.eq.${requestId},request_id.eq.${requestId}`);
      } else {
        query = query.eq("request_id", requestId);
      }

      const { data: otp, error } = await query.single();

      if (error || !otp) {
        return errorResponse("OTP request not found", "NOT_FOUND", 404);
      }

      if (otp.status === "verified") {
        return errorResponse("OTP has already been verified", "ALREADY_VERIFIED", 400);
      }

      if (new Date(otp.expires_at) < new Date()) {
        await supabase
          .from("otp_requests")
          .update({ status: "expired" })
          .eq("id", otp.id);
        return errorResponse("OTP has expired", "OTP_EXPIRED", 400);
      }

      // Safely increment attempt counter via RPC
      const { data: attemptData } = await supabase.rpc("record_otp_attempt", {
        p_otp_id: otp.id,
      });

      if (attemptData?.exceeded) {
        return errorResponse("Maximum verification attempts exceeded", "MAX_ATTEMPTS_EXCEEDED", 400);
      }

      // Compare HMAC hash
      const computedHash = await hashOtp(String(code).trim(), PEPPER);

      if (computedHash !== otp.otp_hash) {
        const remaining = (otp.max_attempts || 5) - (attemptData?.attempts || 1);
        return errorResponse(
          `Invalid verification code. ${remaining} attempt(s) remaining.`,
          "INVALID_CODE",
          400
        );
      }

      // Mark verified
      const now = new Date().toISOString();
      await supabase
        .from("otp_requests")
        .update({
          status: "verified",
          verified_at: now,
        })
        .eq("id", otp.id);

      return jsonResponse({
        success: true,
        data: {
          id: otp.id,
          request_id: otp.request_id,
          status: "verified",
          verified_at: now,
        },
      });
    }

    // -------------------------------------------------------------
    // 4. POST /resend
    // -------------------------------------------------------------
    if (req.method === "POST" && action === "resend") {
      const auth = await authenticateApiKey(supabase, req);
      if (auth.error) return errorResponse(auth.error, "UNAUTHORIZED", auth.status);

      const body = await req.json().catch(() => ({}));
      const requestId = body.request_id || body.id;

      if (!requestId) {
        return errorResponse("request_id is required", "VALIDATION_ERROR", 400);
      }

      const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestId);
      let query = supabase
        .from("otp_requests")
        .select("*")
        .eq("customer_id", auth.keyRecord.customer_id);

      if (isUuid) {
        query = query.or(`id.eq.${requestId},request_id.eq.${requestId}`);
      } else {
        query = query.eq("request_id", requestId);
      }

      const { data: otp, error } = await query.single();

      if (error || !otp) {
        return errorResponse("OTP request not found", "NOT_FOUND", 404);
      }

      if (otp.status === "verified") {
        return errorResponse("OTP has already been verified", "ALREADY_VERIFIED", 400);
      }

      // Enforce cooldown
      const createdTime = new Date(otp.created_at).getTime();
      const elapsedSeconds = (Date.now() - createdTime) / 1000;
      if (elapsedSeconds < OTP_COOLDOWN_SECONDS) {
        const retryAfter = Math.ceil(OTP_COOLDOWN_SECONDS - elapsedSeconds);
        return errorResponse(
          `Please wait ${retryAfter} seconds before requesting a new code.`,
          "COOLDOWN_ACTIVE",
          429
        );
      }

      // Generate new code and reset expiry
      const otpCode = generateOtp(6);
      const otpHash = await hashOtp(otpCode, PEPPER);
      const expiresAt = new Date(Date.now() + OTP_EXPIRY_SECONDS * 1000).toISOString();

      await sendWhatsAppOtp({
        recipientPhone: otp.phone_number,
        otpCode,
      });

      await supabase
        .from("otp_requests")
        .update({
          otp_hash: otpHash,
          status: "sent",
          expires_at: expiresAt,
        })
        .eq("id", otp.id);

      return jsonResponse({
        success: true,
        data: {
          id: otp.id,
          request_id: otp.request_id,
          status: "sent",
          expires_at: expiresAt,
          cooldown_seconds: OTP_COOLDOWN_SECONDS,
        },
      });
    }

    return errorResponse("Endpoint not found", "NOT_FOUND", 404);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("[FUNCTION ERROR]", message);
    return errorResponse(message, "INTERNAL_SERVER_ERROR", 500);
  }
});
