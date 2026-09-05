export const openApiSpec = {
  openapi: "3.0.3",
  info: {
    title: "WhatsApp OTP API Platform (Supabase)",
    version: "1.0.0",
    description: `
Enterprise Multi-Tenant WhatsApp OTP API SaaS Platform hosted natively on **Supabase Edge Functions** and **Supabase PostgreSQL**.

### Getting Started:
1. Include your API key in the **\`x-api-key\`** HTTP header.
2. Demo key pre-authorized: \`wotp_live_demo_secret_key_1234567890abcdef\`
3. Pre-funded demo wallet: **$500.00**
`,
  },
  servers: [
    {
      url: "https://ymstmdjdgwnmtxgurhyn.supabase.co/functions/v1",
      description: "Live Supabase Cloud Project",
    },
  ],
  components: {
    securitySchemes: {
      ApiKeyAuth: {
        type: "apiKey",
        in: "header",
        name: "x-api-key",
        description: "Your secret developer API key",
      },
    },
    schemas: {
      SendOtpRequest: {
        type: "object",
        required: ["phone_number"],
        properties: {
          phone_number: {
            type: "string",
            example: "+14155552671",
            description: "Recipient phone number in E.164 format (+[country][number])",
          },
          length: {
            type: "integer",
            default: 6,
            example: 6,
            description: "Number of digits for the OTP code (4-8)",
          },
          template_name: {
            type: "string",
            example: "otp_verification",
            description: "Optional WhatsApp approved template name",
          },
          language: {
            type: "string",
            default: "en_US",
            example: "en_US",
            description: "Template language code",
          },
        },
      },
      SendOtpResponse: {
        type: "object",
        properties: {
          success: { type: "boolean", example: true },
          data: {
            type: "object",
            properties: {
              id: { type: "string", format: "uuid" },
              request_id: { type: "string", example: "wotp_05e9cd97d3b4479392b67d39" },
              phone_number: { type: "string", example: "+14155552671" },
              status: { type: "string", example: "sent" },
              expires_at: { type: "string", format: "date-time" },
              cooldown_seconds: { type: "integer", example: 60 },
            },
          },
        },
      },
      VerifyOtpRequest: {
        type: "object",
        required: ["request_id", "code"],
        properties: {
          request_id: {
            type: "string",
            example: "wotp_05e9cd97d3b4479392b67d39",
            description: "The unique request ID returned from /send",
          },
          code: {
            type: "string",
            example: "123456",
            description: "The 6-digit numeric OTP code entered by the user",
          },
        },
      },
      VerifyOtpResponse: {
        type: "object",
        properties: {
          success: { type: "boolean", example: true },
          data: {
            type: "object",
            properties: {
              id: { type: "string", format: "uuid" },
              request_id: { type: "string", example: "wotp_05e9cd97d3b4479392b67d39" },
              status: { type: "string", example: "verified" },
              verified_at: { type: "string", format: "date-time" },
            },
          },
        },
      },
      ResendOtpRequest: {
        type: "object",
        required: ["request_id"],
        properties: {
          request_id: {
            type: "string",
            example: "wotp_05e9cd97d3b4479392b67d39",
            description: "The original request ID to resend",
          },
        },
      },
      StatusResponse: {
        type: "object",
        properties: {
          success: { type: "boolean", example: true },
          data: {
            type: "object",
            properties: {
              id: { type: "string", format: "uuid" },
              request_id: { type: "string" },
              phone_number: { type: "string" },
              status: { type: "string", enum: ["created", "queued", "sent", "delivered", "verified", "expired", "failed"] },
              attempts: { type: "integer", example: 0 },
              max_attempts: { type: "integer", example: 5 },
              expires_at: { type: "string", format: "date-time" },
              verified_at: { type: "string", format: "date-time", nullable: true },
              created_at: { type: "string", format: "date-time" },
            },
          },
        },
      },
    },
  },
  security: [
    {
      ApiKeyAuth: [],
    },
  ],
  paths: {
    "/otp/send": {
      post: {
        summary: "Send WhatsApp OTP",
        description: "Atomically deducts 1 credit, generates a secure random OTP, computes an HMAC-SHA256 hash, and dispatches the code via Meta WhatsApp Cloud API.",
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: {
                $ref: "#/components/schemas/SendOtpRequest",
              },
            },
          },
        },
        responses: {
          "200": {
            description: "OTP generated and dispatched successfully",
            content: {
              "application/json": {
                schema: {
                  $ref: "#/components/schemas/SendOtpResponse",
                },
              },
            },
          },
          "402": {
            description: "Insufficient wallet credits",
          },
          "401": {
            description: "Invalid or missing API key",
          },
        },
      },
    },
    "/otp/verify": {
      post: {
        summary: "Verify OTP Code",
        description: "Timing-attack safe comparison of OTP code against HMAC-SHA256 hash. Enforces maximum 5 attempts and expiration checks.",
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: {
                $ref: "#/components/schemas/VerifyOtpRequest",
              },
            },
          },
        },
        responses: {
          "200": {
            description: "Code verified successfully",
            content: {
              "application/json": {
                schema: {
                  $ref: "#/components/schemas/VerifyOtpResponse",
                },
              },
            },
          },
          "400": {
            description: "Invalid code, expired, or maximum attempts exceeded",
          },
        },
      },
    },
    "/otp/resend": {
      post: {
        summary: "Resend OTP",
        description: "Generates a new code and resets expiration, subject to a 60-second cooldown period.",
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: {
                $ref: "#/components/schemas/ResendOtpRequest",
              },
            },
          },
        },
        responses: {
          "200": {
            description: "New OTP code sent successfully",
          },
          "429": {
            description: "Cooldown active (must wait 60 seconds between resends)",
          },
        },
      },
    },
    "/otp/status": {
      get: {
        summary: "Get OTP Request Status",
        description: "Check delivery and verification status of a previous OTP request.",
        parameters: [
          {
            name: "request_id",
            in: "query",
            required: true,
            schema: { type: "string" },
            example: "wotp_05e9cd97d3b4479392b67d39",
            description: "The request ID or UUID of the OTP request",
          },
        ],
        responses: {
          "200": {
            description: "Status retrieved successfully",
            content: {
              "application/json": {
                schema: {
                  $ref: "#/components/schemas/StatusResponse",
                },
              },
            },
          },
          "404": {
            description: "OTP request not found",
          },
        },
      },
    },
    "/meta-webhook": {
      get: {
        summary: "Meta Webhook Verification Handshake",
        description: "Called by Meta when registering your webhook callback URL in the Meta App dashboard.",
        parameters: [
          { name: "hub.mode", in: "query", schema: { type: "string" } },
          { name: "hub.verify_token", in: "query", schema: { type: "string" } },
          { name: "hub.challenge", in: "query", schema: { type: "string" } },
        ],
        responses: {
          "200": { description: "Returns hub.challenge" },
          "403": { description: "Invalid verify token" },
        },
      },
      post: {
        summary: "Meta WhatsApp Status Update Callback",
        description: "Receives asynchronous WhatsApp delivery status updates (sent, delivered, read, failed).",
        responses: {
          "200": { description: "Event received" },
        },
      },
    },
  },
};

export function renderSwaggerHtml(): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>WhatsApp OTP API Documentation</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" />
  <link rel="icon" type="image/png" href="https://supabase.com/favicon/favicon-32x32.png" />
  <style>
    body {
      margin: 0;
      background: #0f172a;
      color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .top-banner {
      background: linear-gradient(90deg, #059669 0%, #10b981 100%);
      padding: 16px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      color: #fff;
      font-weight: 600;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .top-banner .badge {
      background: rgba(255,255,255,0.2);
      padding: 4px 12px;
      border-radius: 999px;
      font-size: 13px;
    }
    .swagger-ui {
      background: #ffffff;
      padding: 24px 0;
    }
  </style>
</head>
<body>
  <div class="top-banner">
    <div>⚡ WhatsApp OTP API Platform — Live on Supabase Edge Functions</div>
    <div class="badge">Project: ymstmdjdgwnmtxgurhyn</div>
  </div>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = function() {
      const ui = SwaggerUIBundle({
        spec: ${JSON.stringify(openApiSpec)},
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIBundle.SwaggerUIStandalonePreset
        ],
        layout: "BaseLayout",
        onComplete: function() {
          // Pre-authorize demo key for 1-click testing
          ui.preauthorizeApiKey("ApiKeyAuth", "wotp_live_demo_secret_key_1234567890abcdef");
        }
      });
      window.ui = ui;
    };
  </script>
</body>
</html>`;
}
