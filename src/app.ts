import fastify, { type FastifyInstance } from "fastify";
import cors from "@fastify/cors";
import fastifyJwt from "@fastify/jwt";
import fastifySensible from "@fastify/sensible";
import { env } from "./config/env.js";
import { logger } from "./plugins/logger.js";
import { requestIdPlugin } from "./middleware/request-id.js";
import { authPlugin } from "./plugins/auth.js";
import { errorHandler } from "./middleware/error-handler.js";

// Routes
import { healthRoutes } from "./modules/health/health.routes.js";
import { authRoutes } from "./modules/auth/auth.routes.js";
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

  // Global error handler
  app.setErrorHandler(errorHandler);

  // Health routes
  app.register(healthRoutes);

  // API v1 routes
  app.register(authRoutes, { prefix: "/v1/auth" });
  app.register(applicationRoutes, { prefix: "/v1/applications" });
  app.register(apiKeyRoutes, { prefix: "/v1/api-keys" });
  app.register(walletRoutes, { prefix: "/v1/wallet" });
  app.register(otpRoutes, { prefix: "/v1/otp" });
  app.register(webhookRoutes, { prefix: "/v1/webhooks" });

  return app;
}
