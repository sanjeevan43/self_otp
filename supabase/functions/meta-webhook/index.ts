import { handleCors, jsonResponse, errorResponse } from "../_shared/cors.ts";
import { getAdminClient } from "../_shared/supabase.ts";
import { verifyMetaSignature } from "../_shared/crypto.ts";

const META_WEBHOOK_VERIFY_TOKEN = Deno.env.get("META_WEBHOOK_VERIFY_TOKEN") || "mock_verify_token";
const META_APP_SECRET = Deno.env.get("META_APP_SECRET") || "mock_meta_app_secret";

Deno.serve(async (req: Request) => {
  const corsResponse = handleCors(req);
  if (corsResponse) return corsResponse;

  const url = new URL(req.url);
  const supabase = getAdminClient();

  // -----------------------------------------------------------------
  // 1. GET: Meta Webhook Verification Handshake
  // -----------------------------------------------------------------
  if (req.method === "GET") {
    const mode = url.searchParams.get("hub.mode");
    const token = url.searchParams.get("hub.verify_token");
    const challenge = url.searchParams.get("hub.challenge");

    // Direct browser visit or health check (no query params)
    if (!mode && !token && !challenge) {
      return jsonResponse({
        status: "healthy",
        service: "Meta WhatsApp Webhook Endpoint",
        message: "Webhook endpoint is online and awaiting Meta WhatsApp events.",
        meta_verification_guide: "Meta will verify this endpoint by passing hub.mode, hub.verify_token, and hub.challenge.",
        timestamp: new Date().toISOString(),
      }, 200);
    }

    if (mode === "subscribe" && token === META_WEBHOOK_VERIFY_TOKEN) {
      console.log("[META WEBHOOK] Handshake verified successfully");
      return new Response(challenge, {
        status: 200,
        headers: { "Content-Type": "text/plain" },
      });
    }

    console.warn("[META WEBHOOK] Verification token mismatch", { token, expected: META_WEBHOOK_VERIFY_TOKEN });
    return new Response("Forbidden: Invalid verify token", { status: 403 });
  }

  // -----------------------------------------------------------------
  // 2. POST: Process WhatsApp Status Events
  // -----------------------------------------------------------------
  if (req.method === "POST") {
    const rawBody = await req.text();
    const signature = req.headers.get("x-hub-signature-256");

    // Verify HMAC-SHA256 signature in production
    const isMock = !META_APP_SECRET || META_APP_SECRET === "mock_meta_app_secret";
    if (!isMock) {
      const isValid = await verifyMetaSignature(rawBody, signature, META_APP_SECRET);
      if (!isValid) {
        console.error("[META WEBHOOK] Invalid signature");
        return errorResponse("Invalid signature", "UNAUTHORIZED", 401);
      }
    }

    let payload: any;
    try {
      payload = JSON.parse(rawBody);
    } catch {
      return errorResponse("Invalid JSON payload", "VALIDATION_ERROR", 400);
    }

    // Process WhatsApp delivery statuses
    const entries = payload.entry || [];
    for (const entry of entries) {
      const changes = entry.changes || [];
      for (const change of changes) {
        const statuses = change.value?.statuses || [];
        for (const statusObj of statuses) {
          const messageId = statusObj.id || `wamid_unknown_${Date.now()}`;
          const status = statusObj.status; // "sent", "delivered", "read", "failed"

          console.log(`[META STATUS] Message ${messageId} changed to ${status}`);

          // Log event to meta_webhook_events
          try {
            await supabase.from("meta_webhook_events").insert({
              meta_message_id: messageId,
              event_type: status || "unknown",
              payload: payload,
              status: "processed",
              processed_at: new Date().toISOString(),
            });
          } catch (err) {
            console.error("[META WEBHOOK] Error logging event:", err);
          }

          // Find matching message in messages table
          const { data: msg } = await supabase
            .from("messages")
            .select("id, customer_id, otp_request_id")
            .eq("provider_message_id", messageId)
            .single();

          if (msg) {
            // Update message status
            await supabase
              .from("messages")
              .update({ status: status === "delivered" ? "delivered" : status })
              .eq("id", msg.id);

            // If linked to an OTP request, update OTP request status too
            if (msg.otp_request_id) {
              const { data: otp } = await supabase
                .from("otp_requests")
                .select("id, customer_id, status")
                .eq("id", msg.otp_request_id)
                .single();

              if (otp && otp.status !== "verified") {
                if (status === "delivered") {
                  await supabase
                    .from("otp_requests")
                    .update({ status: "delivered" })
                    .eq("id", otp.id);
                } else if (status === "failed") {
                  await supabase
                    .from("otp_requests")
                    .update({ status: "failed" })
                    .eq("id", otp.id);

                  // Refund 1 credit on delivery failure
                  await supabase.rpc("refund_wallet_credit", {
                    p_customer_id: otp.customer_id,
                    p_amount: 1.0,
                    p_description: "Delivery failure refund",
                  });
                }
              }
            }
          }
        }
      }
    }

    // Meta expects an immediate 200 OK
    return jsonResponse({ status: "EVENT_RECEIVED" }, 200);
  }

  return errorResponse("Method not allowed", "METHOD_NOT_ALLOWED", 405);
});
