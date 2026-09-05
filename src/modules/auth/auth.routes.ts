import crypto from "node:crypto";
import type { FastifyPluginAsync } from "fastify";
import { z } from "zod";
import { prisma } from "../../plugins/prisma.js";
import { hashPassword, verifyPassword } from "../../common/utils/crypto.js";
import { WalletService } from "../wallet/wallet.service.js";
import {
  BadRequestError,
  UnauthorizedError,
} from "../../common/errors/app-error.js";
import { env } from "../../config/env.js";
import { RefreshTokenService } from "./refresh-token.service.js";

const registerSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
  first_name: z.string().min(1),
  last_name: z.string().min(1),
  phone: z.string().optional(),
  company_name: z.string().min(1),
});

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

const refreshSchema = z.object({
  refresh_token: z.string().min(1),
});

export const authRoutes: FastifyPluginAsync = async (fastify) => {
  // POST /v1/auth/register (201 Created)
  fastify.post("/register", async (request, reply) => {
    const parseResult = registerSchema.safeParse(request.body);
    if (!parseResult.success) {
      throw parseResult.error;
    }
    const body = parseResult.data;

    // Check if user email already exists
    const existingUser = await prisma.users.findUnique({
      where: { email: body.email },
    });

    if (existingUser) {
      throw new BadRequestError(
        "An account with this email already exists.",
        "EMAIL_EXISTS"
      );
    }

    const hashedPassword = await hashPassword(body.password);
    const now = new Date();

    const result = await prisma.$transaction(async (tx) => {
      // Create Customer
      const customer = await tx.customers.create({
        data: {
          company_name: body.company_name,
          email: body.email,
          phone: body.phone || null,
          status: "active",
          country_code: "+91",
        },
      });

      // Create User
      const user = await tx.users.create({
        data: {
          email: body.email,
          password_hash: hashedPassword,
          first_name: body.first_name,
          last_name: body.last_name,
          phone: body.phone || null,
          status: "active",
          email_verified: false,
        },
      });

      // Link Customer and User
      await tx.customer_users.create({
        data: {
          customer_id: customer.id,
          user_id: user.id,
          role: "owner",
        },
      });

      // Create default Application
      await tx.applications.create({
        data: {
          id: crypto.randomUUID(),
          customer_id: customer.id,
          name: `${body.company_name} - Default`,
          description: "Auto-created default application",
          created_at: now,
          updated_at: now,
        },
      });

      // Initialize Wallet with initial 100 credits
      await WalletService.getOrCreateWallet(customer.id, tx);

      return { user, customer };
    });

    return reply.status(201).send({
      id: result.user.id,
      email: result.user.email,
      first_name: result.user.first_name,
      last_name: result.user.last_name,
      phone: result.user.phone,
      status: result.user.status,
      customer_id: result.customer.id,
      created_at: result.user.created_at.toISOString(),
    });
  });

  // POST /v1/auth/login (200 OK)
  fastify.post("/login", async (request, reply) => {
    const parseResult = loginSchema.safeParse(request.body);
    if (!parseResult.success) {
      throw parseResult.error;
    }
    const body = parseResult.data;

    const user = await prisma.users.findUnique({
      where: { email: body.email },
    });

    if (!user) {
      throw new UnauthorizedError(
        "Incorrect email or password.",
        "INVALID_CREDENTIALS"
      );
    }

    const isValid = await verifyPassword(body.password, user.password_hash);
    if (!isValid) {
      throw new UnauthorizedError(
        "Incorrect email or password.",
        "INVALID_CREDENTIALS"
      );
    }

    const customerUser = await prisma.customer_users.findFirst({
      where: { user_id: user.id },
    });
    const customerId = customerUser ? customerUser.customer_id : "";

    const accessToken = fastify.jwt.sign(
      { sub: user.id, customer_id: customerId, type: "access" },
      { expiresIn: `${env.ACCESS_TOKEN_EXPIRE_MINUTES}m` }
    );

    // Create cryptographically secure, persisted refresh token
    const refreshToken = await RefreshTokenService.createInitialToken(user.id);

    // Update last_login_at
    await prisma.users
      .update({
        where: { id: user.id },
        data: { last_login_at: new Date() },
      })
      .catch(() => {});

    return reply.status(200).send({
      access_token: accessToken,
      refresh_token: refreshToken,
      token_type: "bearer",
    });
  });

  // POST /v1/auth/refresh (200 OK)
  fastify.post("/refresh", async (request, reply) => {
    const parseResult = refreshSchema.safeParse(request.body);
    if (!parseResult.success) {
      throw parseResult.error;
    }
    const { refresh_token } = parseResult.data;

    // Atomically rotate refresh token, detecting reuse and invalidating token family
    const { user, customerId, newRefreshToken } =
      await RefreshTokenService.rotateToken(refresh_token);

    const accessToken = fastify.jwt.sign(
      { sub: user.id, customer_id: customerId, type: "access" },
      { expiresIn: `${env.ACCESS_TOKEN_EXPIRE_MINUTES}m` }
    );

    return reply.status(200).send({
      access_token: accessToken,
      refresh_token: newRefreshToken,
      token_type: "bearer",
    });
  });

  // POST /v1/auth/logout (200 OK)
  fastify.post("/logout", async (request, reply) => {
    const logoutSchema = z.object({
      refresh_token: z.string().optional(),
    });
    const parseResult = logoutSchema.safeParse(request.body || {});
    const refreshToken = parseResult.success ? parseResult.data.refresh_token : undefined;

    if (refreshToken) {
      // Revoke the entire refresh token family for this session
      await RefreshTokenService.revokeFamilyByToken(refreshToken);
    }

    // If request contains Bearer JWT, we can optionally revoke all user tokens
    try {
      await request.jwtVerify();
      const payload = request.user as { sub?: string };
      if (payload?.sub && !refreshToken) {
        await RefreshTokenService.revokeAllUserTokens(payload.sub);
      }
    } catch {
      // If no valid JWT present, logout still succeeds based on refresh_token
    }

    return reply.status(200).send({
      message: "Logged out successfully",
    });
  });

  // GET /v1/auth/me (200 OK)
  fastify.get("/me", { preHandler: fastify.authenticateJwt }, async (request, reply) => {
    const user = request.authUser!;
    const customer = request.customer!;

    return reply.status(200).send({
      id: user.id,
      email: user.email,
      first_name: user.first_name,
      last_name: user.last_name,
      phone: user.phone,
      status: user.status,
      customer_id: customer.id,
      created_at: user.created_at.toISOString(),
    });
  });
};
