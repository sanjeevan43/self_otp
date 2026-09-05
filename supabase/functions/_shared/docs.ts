export const openApiSpec = {
  openapi: "3.0.3",
  info: {
    title: "Meta WhatsApp OTP SaaS Platform API",
    version: "1.0.0",
    description: `
Enterprise Multi-Tenant WhatsApp OTP API SaaS Platform.
Hosted on **Supabase Edge Functions** and **Supabase PostgreSQL**.

### Authentication Options:
1. **API Key Authentication**: For client applications sending/verifying OTPs.
   - Header: \`x-api-key: <your_api_key>\`
   - Demo Key: \`wotp_live_demo_secret_key_1234567890abcdef\`
2. **Bearer JWT Authentication**: For dashboard management (Applications, Wallets, Webhooks).
   - Header: \`Authorization: Bearer <jwt_access_token>\`
`,
  },
  servers: [
    {
      url: "https://ymstmdjdgwnmtxgurhyn.supabase.co/functions/v1",
      description: "Live Supabase Cloud Functions (ap-northeast-1)",
    },
    {
      url: "http://localhost:8000",
      description: "Local FastAPI Backend (Docker / Local Dev)",
    },
  ],
  tags: [
    { name: "1. Authentication", description: "Customer account registration, session tokens, and password management" },
    { name: "2. Applications", description: "Isolated project environments within a customer account" },
    { name: "3. API Keys", description: "Application-scoped credentials (test and live environments)" },
    { name: "4. OTP — Core API", description: "Mission-critical OTP delivery, verification, and status endpoints" },
    { name: "5. Account", description: "Customer company profile, limits, and usage settings" },
    { name: "6. Wallet", description: "Prepaid OTP credits, balance checks, and immutable transaction ledger" },
    { name: "7. Payments", description: "Top-up order generation and payment gateway callbacks" },
    { name: "8. Pricing", description: "Per-message rates, volume tiers, and channel pricing" },
    { name: "9. Usage / Statistics", description: "Aggregated metrics, delivery analytics, and time-series reporting" },
    { name: "10. Customer Webhooks", description: "Outbound event dispatching to customer webhook listeners" },
    { name: "11. Meta Webhooks", description: "Inbound Meta WhatsApp Graph API challenge and status updates" },
    { name: "12. Health / System", description: "Liveness, readiness, and monitoring probes" },
    { name: "13. Admin APIs", description: "Platform operator management, tenant controls, and auditing" },
  ],
  components: {
    securitySchemes: {
      ApiKeyAuth: {
        type: "apiKey",
        in: "header",
        name: "x-api-key",
        description: "API Key for OTP and messaging endpoints",
      },
      BearerAuth: {
        type: "http",
        scheme: "bearer",
        bearerFormat: "JWT",
        description: "JWT Token for customer and admin management",
      },
    },
    schemas: {
      ErrorResponse: {
        type: "object",
        properties: {
          error: {
            type: "object",
            properties: {
              message: { type: "string" },
              code: { type: "string" },
            },
          },
        },
      },
      // Auth
      RegisterRequest: {
        type: "object",
        required: ["company_name", "email", "password"],
        properties: {
          company_name: { type: "string", example: "Acme Corp" },
          email: { type: "string", format: "email", example: "developer@acme.com" },
          password: { type: "string", format: "password", example: "StrongP@ssw0rd!" },
          phone: { type: "string", example: "+14155552671" },
        },
      },
      LoginRequest: {
        type: "object",
        required: ["email", "password"],
        properties: {
          email: { type: "string", format: "email", example: "developer@acme.com" },
          password: { type: "string", format: "password", example: "StrongP@ssw0rd!" },
        },
      },
      TokenResponse: {
        type: "object",
        properties: {
          access_token: { type: "string", example: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." },
          refresh_token: { type: "string", example: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." },
          token_type: { type: "string", example: "bearer" },
          expires_in: { type: "integer", example: 900 },
        },
      },
      UserProfile: {
        type: "object",
        properties: {
          id: { type: "string", format: "uuid" },
          email: { type: "string" },
          customer_id: { type: "string", format: "uuid" },
          role: { type: "string", example: "owner" },
        },
      },
      // Application
      ApplicationCreate: {
        type: "object",
        required: ["name"],
        properties: {
          name: { type: "string", example: "My Mobile App" },
          description: { type: "string", example: "Customer-facing Android & iOS app" },
        },
      },
      ApplicationItem: {
        type: "object",
        properties: {
          id: { type: "string", format: "uuid" },
          customer_id: { type: "string", format: "uuid" },
          name: { type: "string", example: "My Mobile App" },
          description: { type: "string" },
          status: { type: "string", example: "active" },
          created_at: { type: "string", format: "date-time" },
        },
      },
      // API Key
      ApiKeyCreate: {
        type: "object",
        required: ["name", "environment"],
        properties: {
          name: { type: "string", example: "Production Backend Key" },
          environment: { type: "string", enum: ["test", "live"], default: "live" },
          rate_limit_rps: { type: "integer", default: 60 },
        },
      },
      ApiKeyItem: {
        type: "object",
        properties: {
          id: { type: "string", format: "uuid" },
          name: { type: "string", example: "Production Backend Key" },
          key_prefix: { type: "string", example: "motp_live_ab12cd" },
          environment: { type: "string", example: "live" },
          status: { type: "string", example: "active" },
          rate_limit_rps: { type: "integer", example: 60 },
          created_at: { type: "string", format: "date-time" },
          raw_key: { type: "string", example: "motp_live_9f83ac124b89...", description: "Only displayed once upon creation" },
        },
      },
      // OTP
      SendOtpRequest: {
        type: "object",
        required: ["phone"],
        properties: {
          phone: { type: "string", example: "+94771234567", description: "E.164 phone number" },
          purpose: { type: "string", example: "login", description: "Purpose of OTP (login, signup, password_reset, transaction)" },
          length: { type: "integer", default: 6, example: 6, description: "OTP digit count (4-8)" },
          template_name: { type: "string", example: "otp_verification" },
        },
      },
      SendOtpResponse: {
        type: "object",
        properties: {
          success: { type: "boolean", example: true },
          data: {
            type: "object",
            properties: {
              request_id: { type: "string", example: "otp_req_9f1b2c3d" },
              expires_in: { type: "integer", example: 300 },
              cooldown_seconds: { type: "integer", example: 60 },
            },
          },
          request_id: { type: "string", example: "req_global_123456" },
        },
      },
      VerifyOtpRequest: {
        type: "object",
        required: ["request_id", "code"],
        properties: {
          request_id: { type: "string", example: "otp_req_9f1b2c3d" },
          code: { type: "string", example: "123456" },
        },
      },
      VerifyOtpResponse: {
        type: "object",
        properties: {
          success: { type: "boolean", example: true },
          data: {
            type: "object",
            properties: {
              request_id: { type: "string", example: "otp_req_9f1b2c3d" },
              status: { type: "string", example: "verified" },
              verified_at: { type: "string", format: "date-time" },
            },
          },
        },
      },
      OtpStatusResponse: {
        type: "object",
        properties: {
          success: { type: "boolean", example: true },
          data: {
            type: "object",
            properties: {
              request_id: { type: "string", example: "otp_req_9f1b2c3d" },
              phone: { type: "string", example: "+94771234567" },
              status: { type: "string", enum: ["created", "queued", "sent", "delivered", "verified", "expired", "failed"] },
              attempts: { type: "integer", example: 0 },
              max_attempts: { type: "integer", example: 5 },
              expires_at: { type: "string", format: "date-time" },
              verified_at: { type: "string", format: "date-time", nullable: true },
            },
          },
        },
      },
      // Wallet
      WalletBalance: {
        type: "object",
        properties: {
          currency: { type: "string", example: "USD" },
          balance: { type: "number", example: 500.00 },
          status: { type: "string", example: "active" },
        },
      },
      WalletTransaction: {
        type: "object",
        properties: {
          id: { type: "string", format: "uuid" },
          amount: { type: "number", example: -1.00 },
          transaction_type: { type: "string", example: "debit" },
          balance_after: { type: "number", example: 499.00 },
          reference_id: { type: "string" },
          description: { type: "string", example: "WhatsApp OTP to +94771234567" },
          created_at: { type: "string", format: "date-time" },
        },
      },
      // Webhooks
      CustomerWebhookCreate: {
        type: "object",
        required: ["url", "events"],
        properties: {
          url: { type: "string", format: "uri", example: "https://customer.com/webhooks/otp" },
          events: {
            type: "array",
            items: { type: "string" },
            example: ["otp.sent", "otp.delivered", "otp.failed", "otp.verified"],
          },
        },
      },
      // Pricing
      PricingOtpResponse: {
        type: "object",
        properties: {
          currency: { type: "string", example: "USD" },
          otp_price: { type: "number", example: 0.02 },
          channel: { type: "string", example: "whatsapp" },
        },
      },
    },
  },
  paths: {
    // ==========================================
    // 1. AUTHENTICATION
    // ==========================================
    "/v1/auth/register": {
      post: {
        tags: ["1. Authentication"],
        summary: "Register new customer account",
        description: "Creates tenant customer, admin user, default application, and funded sandbox wallet.",
        requestBody: {
          required: true,
          content: { "application/json": { schema: { $ref: "#/components/schemas/RegisterRequest" } } },
        },
        responses: {
          "201": { description: "Registered successfully", content: { "application/json": { schema: { $ref: "#/components/schemas/TokenResponse" } } } },
          "400": { description: "Validation error or email already exists" },
        },
      },
    },
    "/v1/auth/login": {
      post: {
        tags: ["1. Authentication"],
        summary: "Authenticate customer user",
        description: "Returns JWT access and refresh tokens.",
        requestBody: {
          required: true,
          content: { "application/json": { schema: { $ref: "#/components/schemas/LoginRequest" } } },
        },
        responses: {
          "200": { description: "Authenticated", content: { "application/json": { schema: { $ref: "#/components/schemas/TokenResponse" } } } },
          "401": { description: "Invalid credentials" },
        },
      },
    },
    "/v1/auth/refresh": {
      post: {
        tags: ["1. Authentication"],
        summary: "Refresh access token",
        responses: {
          "200": { description: "Token refreshed", content: { "application/json": { schema: { $ref: "#/components/schemas/TokenResponse" } } } },
        },
      },
    },
    "/v1/auth/logout": {
      post: {
        tags: ["1. Authentication"],
        security: [{ BearerAuth: [] }],
        summary: "Sign out and invalidate session",
        responses: { "200": { description: "Logged out" } },
      },
    },
    "/v1/auth/forgot-password": {
      post: {
        tags: ["1. Authentication"],
        summary: "Request password reset link",
        requestBody: {
          required: true,
          content: { "application/json": { schema: { type: "object", properties: { email: { type: "string" } } } } },
        },
        responses: { "200": { description: "Reset email dispatched" } },
      },
    },
    "/v1/auth/reset-password": {
      post: {
        tags: ["1. Authentication"],
        summary: "Reset password with recovery token",
        responses: { "200": { description: "Password reset successful" } },
      },
    },
    "/v1/auth/me": {
      get: {
        tags: ["1. Authentication"],
        security: [{ BearerAuth: [] }],
        summary: "Get current user profile and customer tenant info",
        responses: {
          "200": { description: "Profile info", content: { "application/json": { schema: { $ref: "#/components/schemas/UserProfile" } } } },
        },
      },
    },

    // ==========================================
    // 2. APPLICATIONS
    // ==========================================
    "/v1/applications": {
      post: {
        tags: ["2. Applications"],
        security: [{ BearerAuth: [] }],
        summary: "Create an application",
        description: "Applications isolate API keys, rate limits, templates, and analytics.",
        requestBody: {
          required: true,
          content: { "application/json": { schema: { $ref: "#/components/schemas/ApplicationCreate" } } },
        },
        responses: {
          "201": { description: "Application created", content: { "application/json": { schema: { $ref: "#/components/schemas/ApplicationItem" } } } },
        },
      },
      get: {
        tags: ["2. Applications"],
        security: [{ BearerAuth: [] }],
        summary: "List all customer applications",
        responses: {
          "200": { description: "Applications list", content: { "application/json": { schema: { type: "array", items: { $ref: "#/components/schemas/ApplicationItem" } } } } },
        },
      },
    },
    "/v1/applications/{application_id}": {
      get: {
        tags: ["2. Applications"],
        security: [{ BearerAuth: [] }],
        summary: "Get application details",
        parameters: [{ name: "application_id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: { "200": { description: "Application details", content: { "application/json": { schema: { $ref: "#/components/schemas/ApplicationItem" } } } } },
      },
      patch: {
        tags: ["2. Applications"],
        security: [{ BearerAuth: [] }],
        summary: "Update application",
        parameters: [{ name: "application_id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: { "200": { description: "Updated successfully" } },
      },
      delete: {
        tags: ["2. Applications"],
        security: [{ BearerAuth: [] }],
        summary: "Delete application",
        parameters: [{ name: "application_id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: { "204": { description: "Application deleted" } },
      },
    },
    "/v1/applications/{application_id}/activate": {
      post: {
        tags: ["2. Applications"],
        security: [{ BearerAuth: [] }],
        summary: "Activate an application",
        parameters: [{ name: "application_id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: { "200": { description: "Activated" } },
      },
    },
    "/v1/applications/{application_id}/suspend": {
      post: {
        tags: ["2. Applications"],
        security: [{ BearerAuth: [] }],
        summary: "Suspend an application",
        parameters: [{ name: "application_id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: { "200": { description: "Suspended" } },
      },
    },

    // ==========================================
    // 3. API KEYS
    // ==========================================
    "/v1/applications/{application_id}/api-keys": {
      post: {
        tags: ["3. API Keys"],
        security: [{ BearerAuth: [] }],
        summary: "Create an API Key for an application",
        parameters: [{ name: "application_id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        requestBody: {
          required: true,
          content: { "application/json": { schema: { $ref: "#/components/schemas/ApiKeyCreate" } } },
        },
        responses: {
          "201": { description: "Key generated", content: { "application/json": { schema: { $ref: "#/components/schemas/ApiKeyItem" } } } },
        },
      },
      get: {
        tags: ["3. API Keys"],
        security: [{ BearerAuth: [] }],
        summary: "List all API keys for an application",
        parameters: [{ name: "application_id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: {
          "200": { description: "Keys list", content: { "application/json": { schema: { type: "array", items: { $ref: "#/components/schemas/ApiKeyItem" } } } } },
        },
      },
    },
    "/v1/applications/{application_id}/api-keys/{key_id}": {
      get: {
        tags: ["3. API Keys"],
        security: [{ BearerAuth: [] }],
        summary: "Get API key details",
        parameters: [
          { name: "application_id", in: "path", required: true, schema: { type: "string", format: "uuid" } },
          { name: "key_id", in: "path", required: true, schema: { type: "string", format: "uuid" } },
        ],
        responses: { "200": { description: "Key details" } },
      },
      delete: {
        tags: ["3. API Keys"],
        security: [{ BearerAuth: [] }],
        summary: "Delete API key",
        parameters: [
          { name: "application_id", in: "path", required: true, schema: { type: "string", format: "uuid" } },
          { name: "key_id", in: "path", required: true, schema: { type: "string", format: "uuid" } },
        ],
        responses: { "204": { description: "Key deleted" } },
      },
    },
    "/v1/applications/{application_id}/api-keys/{key_id}/rotate": {
      post: {
        tags: ["3. API Keys"],
        security: [{ BearerAuth: [] }],
        summary: "Rotate API key (generates new secret and invalidates old)",
        parameters: [
          { name: "application_id", in: "path", required: true, schema: { type: "string", format: "uuid" } },
          { name: "key_id", in: "path", required: true, schema: { type: "string", format: "uuid" } },
        ],
        responses: { "200": { description: "Key rotated" } },
      },
    },
    "/v1/applications/{application_id}/api-keys/{key_id}/revoke": {
      post: {
        tags: ["3. API Keys"],
        security: [{ BearerAuth: [] }],
        summary: "Revoke API key immediately",
        parameters: [
          { name: "application_id", in: "path", required: true, schema: { type: "string", format: "uuid" } },
          { name: "key_id", in: "path", required: true, schema: { type: "string", format: "uuid" } },
        ],
        responses: { "200": { description: "Key revoked" } },
      },
    },

    // ==========================================
    // 4. OTP — CORE API (Live on Supabase)
    // ==========================================
    "/v1/otp/send": {
      post: {
        tags: ["4. OTP — Core API"],
        security: [{ ApiKeyAuth: [] }],
        summary: "Send WhatsApp OTP",
        description: "Dispatches a cryptographically secure OTP code via Meta WhatsApp Cloud API.",
        requestBody: {
          required: true,
          content: { "application/json": { schema: { $ref: "#/components/schemas/SendOtpRequest" } } },
        },
        responses: {
          "200": { description: "OTP dispatched successfully", content: { "application/json": { schema: { $ref: "#/components/schemas/SendOtpResponse" } } } },
          "401": { description: "Missing or invalid API key" },
          "402": { description: "Insufficient wallet credits" },
        },
      },
    },
    "/v1/otp/verify": {
      post: {
        tags: ["4. OTP — Core API"],
        security: [{ ApiKeyAuth: [] }],
        summary: "Verify OTP Code",
        description: "Constant-time HMAC comparison with max attempt limit enforcement.",
        requestBody: {
          required: true,
          content: { "application/json": { schema: { $ref: "#/components/schemas/VerifyOtpRequest" } } },
        },
        responses: {
          "200": { description: "OTP verified", content: { "application/json": { schema: { $ref: "#/components/schemas/VerifyOtpResponse" } } } },
          "400": { description: "Invalid code, expired, or attempts exceeded" },
        },
      },
    },
    "/v1/otp/{request_id}": {
      get: {
        tags: ["4. OTP — Core API"],
        security: [{ ApiKeyAuth: [] }],
        summary: "Get OTP status",
        parameters: [{ name: "request_id", in: "path", required: true, schema: { type: "string" }, example: "otp_req_9f1b2c3d" }],
        responses: {
          "200": { description: "Status retrieved", content: { "application/json": { schema: { $ref: "#/components/schemas/OtpStatusResponse" } } } },
          "404": { description: "Request ID not found" },
        },
      },
    },
    "/v1/otp/{request_id}/resend": {
      post: {
        tags: ["4. OTP — Core API"],
        security: [{ ApiKeyAuth: [] }],
        summary: "Resend OTP",
        parameters: [{ name: "request_id", in: "path", required: true, schema: { type: "string" } }],
        responses: {
          "200": { description: "New OTP code sent" },
          "429": { description: "Cooldown period active (must wait 60s)" },
        },
      },
    },
    "/v1/otp/{request_id}/cancel": {
      post: {
        tags: ["4. OTP — Core API"],
        security: [{ ApiKeyAuth: [] }],
        summary: "Cancel pending OTP request",
        parameters: [{ name: "request_id", in: "path", required: true, schema: { type: "string" } }],
        responses: { "200": { description: "OTP cancelled" } },
      },
    },

    // ==========================================
    // 5. ACCOUNT
    // ==========================================
    "/v1/account": {
      get: {
        tags: ["5. Account"],
        security: [{ BearerAuth: [] }],
        summary: "Get customer company account details",
        responses: { "200": { description: "Account info" } },
      },
      patch: {
        tags: ["5. Account"],
        security: [{ BearerAuth: [] }],
        summary: "Update customer company info",
        responses: { "200": { description: "Account updated" } },
      },
    },
    "/v1/account/usage": {
      get: {
        tags: ["5. Account"],
        security: [{ BearerAuth: [] }],
        summary: "Get monthly account usage stats",
        responses: { "200": { description: "Usage metrics" } },
      },
    },
    "/v1/account/limits": {
      get: {
        tags: ["5. Account"],
        security: [{ BearerAuth: [] }],
        summary: "Get account rate limits and concurrency quotas",
        responses: { "200": { description: "Quotas and limits" } },
      },
    },

    // ==========================================
    // 6. WALLET
    // ==========================================
    "/v1/wallet": {
      get: {
        tags: ["6. Wallet"],
        security: [{ BearerAuth: [] }, { ApiKeyAuth: [] }],
        summary: "Get wallet details",
        responses: { "200": { description: "Wallet details", content: { "application/json": { schema: { $ref: "#/components/schemas/WalletBalance" } } } } },
      },
    },
    "/v1/wallet/balance": {
      get: {
        tags: ["6. Wallet"],
        security: [{ BearerAuth: [] }, { ApiKeyAuth: [] }],
        summary: "Get real-time credit balance",
        responses: { "200": { description: "Current balance", content: { "application/json": { schema: { $ref: "#/components/schemas/WalletBalance" } } } } },
      },
    },
    "/v1/wallet/transactions": {
      get: {
        tags: ["6. Wallet"],
        security: [{ BearerAuth: [] }],
        summary: "List wallet ledger transactions",
        responses: {
          "200": { description: "Transaction history", content: { "application/json": { schema: { type: "array", items: { $ref: "#/components/schemas/WalletTransaction" } } } } },
        },
      },
    },
    "/v1/wallet/transactions/{transaction_id}": {
      get: {
        tags: ["6. Wallet"],
        security: [{ BearerAuth: [] }],
        summary: "Get transaction receipt details",
        parameters: [{ name: "transaction_id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: { "200": { description: "Transaction receipt" } },
      },
    },

    // ==========================================
    // 7. PAYMENTS
    // ==========================================
    "/v1/payments/orders": {
      post: {
        tags: ["7. Payments"],
        security: [{ BearerAuth: [] }],
        summary: "Create a wallet top-up payment order",
        requestBody: {
          required: true,
          content: { "application/json": { schema: { type: "object", properties: { amount: { type: "number", example: 50.00 }, currency: { type: "string", example: "USD" } } } } },
        },
        responses: { "201": { description: "Payment order created" } },
      },
      get: {
        tags: ["7. Payments"],
        security: [{ BearerAuth: [] }],
        summary: "List customer payment orders",
        responses: { "200": { description: "Payment orders list" } },
      },
    },
    "/v1/payments/orders/{order_id}": {
      get: {
        tags: ["7. Payments"],
        security: [{ BearerAuth: [] }],
        summary: "Get payment order status",
        parameters: [{ name: "order_id", in: "path", required: true, schema: { type: "string" } }],
        responses: { "200": { description: "Order status" } },
      },
    },
    "/v1/payments/orders/{order_id}/cancel": {
      post: {
        tags: ["7. Payments"],
        security: [{ BearerAuth: [] }],
        summary: "Cancel unpaid order",
        parameters: [{ name: "order_id", in: "path", required: true, schema: { type: "string" } }],
        responses: { "200": { description: "Order cancelled" } },
      },
    },
    "/v1/webhooks/payments/{provider}": {
      post: {
        tags: ["7. Payments"],
        summary: "Payment provider gateway callback (Stripe / Razorpay)",
        parameters: [{ name: "provider", in: "path", required: true, schema: { type: "string", example: "stripe" } }],
        responses: { "200": { description: "Payment processed and wallet credited" } },
      },
    },

    // ==========================================
    // 8. PRICING
    // ==========================================
    "/v1/pricing": {
      get: {
        tags: ["8. Pricing"],
        summary: "Get pricing details",
        responses: { "200": { description: "Pricing catalogue" } },
      },
    },
    "/v1/pricing/otp": {
      get: {
        tags: ["8. Pricing"],
        summary: "Get current OTP per-message unit rate",
        responses: {
          "200": { description: "Unit price", content: { "application/json": { schema: { $ref: "#/components/schemas/PricingOtpResponse" } } } },
        },
      },
    },
    "/v1/pricing/plans": {
      get: {
        tags: ["8. Pricing"],
        summary: "List available subscription/volume tiers",
        responses: { "200": { description: "Tier list" } },
      },
    },

    // ==========================================
    // 9. USAGE / STATISTICS
    // ==========================================
    "/v1/usage": {
      get: {
        tags: ["9. Usage / Statistics"],
        security: [{ BearerAuth: [] }, { ApiKeyAuth: [] }],
        summary: "Get aggregated usage statistics",
        parameters: [
          { name: "from", in: "query", schema: { type: "string", format: "date" } },
          { name: "to", in: "query", schema: { type: "string", format: "date" } },
        ],
        responses: { "200": { description: "Usage metrics" } },
      },
    },
    "/v1/usage/summary": {
      get: {
        tags: ["9. Usage / Statistics"],
        security: [{ BearerAuth: [] }],
        summary: "Get high-level summary (sent, delivered, verified, failure rate)",
        responses: { "200": { description: "Summary metrics" } },
      },
    },
    "/v1/usage/daily": {
      get: {
        tags: ["9. Usage / Statistics"],
        security: [{ BearerAuth: [] }],
        summary: "Get daily time-series chart data",
        responses: { "200": { description: "Daily breakdown" } },
      },
    },
    "/v1/applications/{application_id}/usage": {
      get: {
        tags: ["9. Usage / Statistics"],
        security: [{ BearerAuth: [] }],
        summary: "Get usage metrics specific to one application",
        parameters: [{ name: "application_id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: { "200": { description: "Application usage" } },
      },
    },

    // ==========================================
    // 10. CUSTOMER WEBHOOKS
    // ==========================================
    "/v1/customer-webhooks": {
      get: {
        tags: ["10. Customer Webhooks"],
        security: [{ BearerAuth: [] }],
        summary: "List registered customer webhook endpoints",
        responses: { "200": { description: "Webhooks list" } },
      },
      post: {
        tags: ["10. Customer Webhooks"],
        security: [{ BearerAuth: [] }],
        summary: "Register new customer webhook endpoint",
        requestBody: {
          required: true,
          content: { "application/json": { schema: { $ref: "#/components/schemas/CustomerWebhookCreate" } } },
        },
        responses: { "201": { description: "Webhook registered" } },
      },
    },
    "/v1/customer-webhooks/{id}": {
      get: {
        tags: ["10. Customer Webhooks"],
        security: [{ BearerAuth: [] }],
        summary: "Get webhook config",
        parameters: [{ name: "id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: { "200": { description: "Webhook details" } },
      },
      patch: {
        tags: ["10. Customer Webhooks"],
        security: [{ BearerAuth: [] }],
        summary: "Update webhook config",
        parameters: [{ name: "id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: { "200": { description: "Updated" } },
      },
      delete: {
        tags: ["10. Customer Webhooks"],
        security: [{ BearerAuth: [] }],
        summary: "Delete webhook config",
        parameters: [{ name: "id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: { "204": { description: "Deleted" } },
      },
    },
    "/v1/customer-webhooks/{id}/test": {
      post: {
        tags: ["10. Customer Webhooks"],
        security: [{ BearerAuth: [] }],
        summary: "Send test ping event to customer URL",
        parameters: [{ name: "id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: { "200": { description: "Test ping sent" } },
      },
    },

    // ==========================================
    // 11. META WEBHOOKS (Internal Provider)
    // ==========================================
    "/v1/webhooks/meta": {
      get: {
        tags: ["11. Meta Webhooks"],
        summary: "Meta Webhook Verification Handshake",
        description: "Called by Meta when configuring WhatsApp Cloud API callback URL.",
        parameters: [
          { name: "hub.mode", in: "query", schema: { type: "string", example: "subscribe" } },
          { name: "hub.verify_token", in: "query", schema: { type: "string", example: "mock_verify_token" } },
          { name: "hub.challenge", in: "query", schema: { type: "string", example: "1158201444" } },
        ],
        responses: { "200": { description: "Returns hub.challenge" }, "403": { description: "Invalid verify token" } },
      },
      post: {
        tags: ["11. Meta Webhooks"],
        summary: "Meta WhatsApp Status Update Callback",
        description: "Receives asynchronous delivery statuses (sent, delivered, read, failed).",
        responses: { "200": { description: "Status processed" } },
      },
    },

    // ==========================================
    // 12. HEALTH / SYSTEM
    // ==========================================
    "/health": {
      get: {
        tags: ["12. Health / System"],
        summary: "Service health probe",
        responses: { "200": { description: "Healthy" } },
      },
    },
    "/health/live": {
      get: {
        tags: ["12. Health / System"],
        summary: "Liveness probe",
        responses: { "200": { description: "Alive" } },
      },
    },
    "/health/ready": {
      get: {
        tags: ["12. Health / System"],
        summary: "Readiness probe (checks PostgreSQL connectivity)",
        responses: { "200": { description: "Ready to accept traffic" } },
      },
    },

    // ==========================================
    // 13. ADMIN APIS
    // ==========================================
    "/v1/admin/customers": {
      get: {
        tags: ["13. Admin APIs"],
        security: [{ BearerAuth: [] }],
        summary: "Admin: List all tenant customers",
        responses: { "200": { description: "Customer list" } },
      },
    },
    "/v1/admin/customers/{customer_id}/suspend": {
      post: {
        tags: ["13. Admin APIs"],
        security: [{ BearerAuth: [] }],
        summary: "Admin: Suspend customer account",
        parameters: [{ name: "customer_id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        responses: { "200": { description: "Customer suspended" } },
      },
    },
    "/v1/admin/wallets/{wallet_id}/credit": {
      post: {
        tags: ["13. Admin APIs"],
        security: [{ BearerAuth: [] }],
        summary: "Admin: Manually credit a customer wallet",
        parameters: [{ name: "wallet_id", in: "path", required: true, schema: { type: "string", format: "uuid" } }],
        requestBody: {
          required: true,
          content: { "application/json": { schema: { type: "object", properties: { amount: { type: "number" }, description: { type: "string" } } } } },
        },
        responses: { "200": { description: "Credits added" } },
      },
    },
    "/v1/admin/audit-logs": {
      get: {
        tags: ["13. Admin APIs"],
        security: [{ BearerAuth: [] }],
        summary: "Admin: Query platform immutable audit trail",
        responses: { "200": { description: "Audit trail events" } },
      },
    },
  },
};

export function renderSwaggerHtml(): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>WhatsApp OTP API — Interactive Swagger UI</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" />
  <link rel="icon" type="image/png" href="https://supabase.com/favicon/favicon-32x32.png" />
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #0b0f19;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .top-banner {
      background: linear-gradient(135deg, #059669 0%, #10b981 100%);
      padding: 16px 28px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      color: #fff;
      font-weight: 600;
      box-shadow: 0 4px 16px rgba(0,0,0,0.25);
    }
    .top-banner .badge {
      background: rgba(255,255,255,0.2);
      padding: 6px 14px;
      border-radius: 999px;
      font-size: 13px;
    }
    #swagger-ui {
      max-width: 1280px;
      margin: 20px auto;
      background: #ffffff;
      border-radius: 12px;
      padding: 16px 28px;
      box-shadow: 0 12px 40px rgba(0,0,0,0.3);
    }
    .swagger-ui .topbar { display: none; }
  </style>
</head>
<body>
  <div class="top-banner">
    <div>⚡ Meta WhatsApp OTP API SaaS Platform — Live Swagger Reference</div>
    <div class="badge">Supabase: ymstmdjdgwnmtxgurhyn</div>
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
          ui.preauthorizeApiKey("ApiKeyAuth", "wotp_live_demo_secret_key_1234567890abcdef");
        }
      });
      window.ui = ui;
    };
  </script>
</body>
</html>`;
}
