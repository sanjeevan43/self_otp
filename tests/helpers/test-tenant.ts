import crypto from "node:crypto";
import { prisma } from "../../src/plugins/prisma.js";
import { hashApiKey, hashPassword } from "../../src/common/utils/crypto.js";
import type { FastifyInstance } from "fastify";

export interface TenantContext {
  customerId: string;
  userId: string;
  applicationId: string;
  apiKeyId: string;
  rawApiKey: string;
  accessToken: string;
}

export async function createTestTenant(
  app: FastifyInstance,
  emailPrefix = "test_tenant",
  initialBalance = 100.0
): Promise<TenantContext> {
  const uniqueId = crypto.randomBytes(6).toString("hex");
  const email = `${emailPrefix}_${uniqueId}@example.com`;
  const company = `Company_${uniqueId}`;
  const now = new Date();

  const hashedPassword = await hashPassword("TestPassword123!");

  const result = await prisma.$transaction(async (tx) => {
    // 1. Customer
    const customer = await tx.customers.create({
      data: {
        company_name: company,
        email,
        status: "active",
        country_code: "+91",
      },
    });

    // 2. User
    const user = await tx.users.create({
      data: {
        email,
        password_hash: hashedPassword,
        first_name: "Test",
        last_name: "User",
        status: "active",
        email_verified: true,
      },
    });

    // 3. CustomerUser
    await tx.customer_users.create({
      data: {
        customer_id: customer.id,
        user_id: user.id,
        role: "owner",
      },
    });

    // 4. Application
    const application = await tx.applications.create({
      data: {
        id: crypto.randomUUID(),
        customer_id: customer.id,
        name: `${company} App`,
        description: "Test App",
        created_at: now,
        updated_at: now,
      },
    });

    // 5. API Key
    const rawSecret = crypto.randomBytes(32).toString("hex");
    const keyPrefix = `wotp_live_${rawSecret.slice(0, 6)}`;
    const rawApiKey = `wotp_live_${rawSecret}`;
    const keyHash = hashApiKey(rawApiKey);

    const apiKey = await tx.api_keys.create({
      data: {
        customer_id: customer.id,
        application_id: application.id,
        name: "Test API Key",
        key_prefix: keyPrefix,
        key_hash: keyHash,
        status: "active",
        created_at: now,
        updated_at: now,
      },
    });

    // 6. Wallet
    await tx.wallets.create({
      data: {
        customer_id: customer.id,
        balance: initialBalance,
        currency: "INR",
        status: "active",
      },
    });

    return {
      customerId: customer.id,
      userId: user.id,
      applicationId: application.id,
      apiKeyId: apiKey.id,
      rawApiKey,
    };
  });

  const accessToken = app.jwt.sign(
    { sub: result.userId, customer_id: result.customerId, type: "access" },
    { expiresIn: "15m" }
  );

  return {
    ...result,
    accessToken,
  };
}
