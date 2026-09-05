import { describe, it, expect, afterAll } from "vitest";
import { prisma } from "../../src/plugins/prisma.js";

describe("Database Schema Integrity & Compatibility Verification", () => {
  afterAll(async () => {
    await prisma.$disconnect().catch(() => {});
  });

  it("Verifies connection and accessibility of existing PostgreSQL database tables", async () => {
    const result = await prisma.$queryRaw<Array<{ table_name: string }>>`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      ORDER BY table_name;
    `;

    const tableNames = result.map((r) => r.table_name);

    // Essential business tables from Python implementation
    const expectedTables = [
      "customers",
      "users",
      "customer_users",
      "applications",
      "api_keys",
      "wallets",
      "wallet_transactions",
      "otp_requests",
      "otp_verifications",
      "messages",
      "message_events",
      "webhook_events",
      "idempotency_keys",
      "pricing_plans",
      "pricing_rules",
      "payment_orders",
      "payments",
    ];

    for (const table of expectedTables) {
      expect(tableNames).toContain(table);
    }
  });

  it("Verifies Decimal/Numeric column precision on financial and pricing tables", async () => {
    const columns = await prisma.$queryRaw<Array<{ table_name: string; column_name: string; data_type: string }>>`
      SELECT table_name, column_name, data_type 
      FROM information_schema.columns 
      WHERE table_schema = 'public' 
        AND (
          (table_name = 'wallets' AND column_name = 'balance')
          OR (table_name = 'wallet_transactions' AND column_name IN ('amount', 'balance_before', 'balance_after'))
        );
    `;

    expect(columns.length).toBeGreaterThanOrEqual(4);
    for (const col of columns) {
      // Must be numeric or double precision (float) in postgres
      expect(["numeric", "double precision"]).toContain(col.data_type);
    }
  });

  it("Verifies critical unique indexes exist for idempotency and security", async () => {
    const indexes = await prisma.$queryRaw<Array<{ indexname: string }>>`
      SELECT indexname 
      FROM pg_indexes 
      WHERE schemaname = 'public';
    `;

    const indexNames = indexes.map((i) => i.indexname);

    expect(indexNames).toContain("ix_api_keys_key_hash");
    expect(indexNames).toContain("ix_otp_requests_request_id");
    expect(indexNames).toContain("ix_wallets_customer_id");
    expect(indexNames).toContain("ix_users_email");
  });
});
