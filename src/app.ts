import fastify, { type FastifyInstance } from "fastify";
import cors from "@fastify/cors";
import fastifyJwt from "@fastify/jwt";
import fastifySensible from "@fastify/sensible";
import { env } from "./config/env.js";
import { logger } from "./plugins/logger.js";
import { requestIdPlugin } from "./middleware/request-id.js";
import { authPlugin } from "./plugins/auth.js";
import { errorHandler } from "./middleware/error-handler.js";

import fastifySwagger from "@fastify/swagger";
import fastifySwaggerUi from "@fastify/swagger-ui";

// Routes
import { healthRoutes } from "./modules/health/health.routes.js";
import { authRoutes } from "./modules/auth/auth.routes.js";
import { accountRoutes } from "./modules/account/account.routes.js";
import { applicationRoutes } from "./modules/applications/applications.routes.js";
import { apiKeyRoutes } from "./modules/api-keys/api-keys.routes.js";
import { walletRoutes } from "./modules/wallet/wallet.routes.js";
import { otpRoutes } from "./modules/otp/otp.routes.js";
import { webhookRoutes } from "./modules/webhooks/webhooks.routes.js";

export function buildApp(): FastifyInstance {
  const app = fastify({
    loggerInstance: logger as any,
    disableRequestLogging: env.NODE_ENV === "test",
  });

  // Base plugins
  app.register(cors, {
    origin: true,
    credentials: true,
  });

  app.register(fastifySensible);

  app.register(fastifyJwt, {
    secret: env.SECRET_KEY,
  });

  // Custom middleware plugins
  app.register(requestIdPlugin);
  app.register(authPlugin);

  // Swagger documentation
  app.register(fastifySwagger, {
    openapi: {
      info: {
        title: "Meta WhatsApp OTP API SaaS Platform",
        description: "Production-Grade Meta WhatsApp OTP SaaS API in Node.js, TypeScript, Fastify, Prisma & BullMQ.",
        version: "1.0.0",
      },
      servers: [
        { url: "/", description: "Current Server (Auto-detected)" },
        { url: `http://localhost:${env.PORT}`, description: "Local API Server" },
      ],
      components: {
        securitySchemes: {
          ApiKeyAuth: {
            type: "apiKey",
            name: "X-API-Key",
            in: "header",
            description: "Customer API Key (format: wotp_live_...)",
          },
          BearerAuth: {
            type: "http",
            scheme: "bearer",
            bearerFormat: "JWT",
            description: "Dashboard User JWT Access Token",
          },
        },
      },
    },
  });

  app.register(fastifySwaggerUi, {
    routePrefix: "/docs",
    uiConfig: {
      docExpansion: "list",
      deepLinking: true,
    },
  });

  // Alias /swagger and /api-docs to /docs
  app.get("/swagger", async (_req, reply) => {
    return reply.redirect("/docs");
  });

  app.get("/api-docs", async (_req, reply) => {
    return reply.redirect("/docs");
  });

  // Global error handler
  app.setErrorHandler(errorHandler);

  // Health routes
  app.register(healthRoutes);

  // API v1 routes
  app.register(authRoutes, { prefix: "/v1/auth" });
  app.register(accountRoutes, { prefix: "/v1/account" });
  app.register(applicationRoutes, { prefix: "/v1/applications" });
  app.register(apiKeyRoutes, { prefix: "/v1/api-keys" });
  app.register(walletRoutes, { prefix: "/v1/wallet" });
  app.register(otpRoutes, { prefix: "/v1/otp" });
  app.register(webhookRoutes, { prefix: "/v1/webhooks" });

  return app;
}
