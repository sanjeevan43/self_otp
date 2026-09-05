import crypto from "node:crypto";
import { prisma } from "../../plugins/prisma.js";
import { hashRefreshToken } from "../../common/utils/crypto.js";
import { UnauthorizedError } from "../../common/errors/app-error.js";
import { env } from "../../config/env.js";
import type { users } from "@prisma/client";

export class RefreshTokenService {
  /**
   * Creates an initial refresh token for a user session (login/registration).
   * Persists only the SHA-256 token hash; returns the raw unhashed token to the client.
   */
  static async createInitialToken(userId: string): Promise<string> {
    const rawToken = crypto.randomBytes(40).toString("hex");
    const tokenHash = hashRefreshToken(rawToken);
    const familyId = crypto.randomUUID();
    const expiresAt = new Date(Date.now() + env.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60 * 1000);

    await prisma.refresh_tokens.create({
      data: {
        user_id: userId,
        token_hash: tokenHash,
        family_id: familyId,
        expires_at: expiresAt,
      },
    });

    return rawToken;
  }

  /**
   * Atomically rotates a refresh token inside a single transaction with row-level locking.
   * Detects reuse and invalidates the entire token family if reuse is attempted.
   */
  static async rotateToken(rawToken: string): Promise<{
    user: users;
    customerId: string;
    newRefreshToken: string;
  }> {
    const tokenHash = hashRefreshToken(rawToken);

    let isReuse = false;
    let familyIdToRevoke: string | null = null;

    try {
      return await prisma.$transaction(async (tx) => {
        // Row-level lock on the refresh token row
        const [record] = await tx.$queryRaw<Array<{
          id: string;
          user_id: string;
          token_hash: string;
          family_id: string;
          expires_at: Date;
          revoked_at: Date | null;
          replaced_by_token_id: string | null;
          created_at: Date;
          last_used_at: Date | null;
        }>>`SELECT * FROM public.refresh_tokens WHERE token_hash = ${tokenHash} FOR UPDATE`;

        if (!record) {
          throw new UnauthorizedError("Invalid refresh token.", "INVALID_REFRESH_TOKEN");
        }

        // 1. Detect reuse: If the token has already been revoked, flag for family revocation
        if (record.revoked_at !== null) {
          isReuse = true;
          familyIdToRevoke = record.family_id;
          throw new UnauthorizedError(
            "Refresh token reuse detected. Session terminated.",
            "TOKEN_REUSE_DETECTED"
          );
        }

      // 2. Detect expiration
      if (new Date(record.expires_at) < new Date()) {
        throw new UnauthorizedError("Refresh token has expired.", "TOKEN_EXPIRED");
      }

      // 3. Verify user status
      const user = await tx.users.findUnique({
        where: { id: record.user_id },
        include: { customer_users: true },
      });
      if (!user || user.status !== "active") {
        throw new UnauthorizedError("User not found or inactive.", "UNAUTHORIZED");
      }

      // 4. Generate replacement token in the same token family
      const newRawToken = crypto.randomBytes(40).toString("hex");
      const newTokenHash = hashRefreshToken(newRawToken);
      const newExpiresAt = new Date(Date.now() + env.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60 * 1000);

      const newRecord = await tx.refresh_tokens.create({
        data: {
          user_id: user.id,
          token_hash: newTokenHash,
          family_id: record.family_id,
          expires_at: newExpiresAt,
        },
      });

      // 5. Revoke current token and link replaced_by_token_id to guarantee linear audit lineage
      await tx.refresh_tokens.update({
        where: { id: record.id },
        data: {
          revoked_at: new Date(),
          last_used_at: new Date(),
          replaced_by_token_id: newRecord.id,
        },
      });

      const customerId = user.customer_users[0]?.customer_id || "";

      return {
        user,
        customerId,
        newRefreshToken: newRawToken,
      };
      });
    } catch (err) {
      if (isReuse && familyIdToRevoke) {
        await prisma.refresh_tokens.updateMany({
          where: {
            family_id: familyIdToRevoke,
            revoked_at: null,
          },
          data: {
            revoked_at: new Date(),
          },
        });
      }
      throw err;
    }
  }

  /**
   * Revokes the entire refresh token family for a session upon logout.
   */
  static async revokeFamilyByToken(rawToken: string): Promise<boolean> {
    const tokenHash = hashRefreshToken(rawToken);

    const record = await prisma.refresh_tokens.findUnique({
      where: { token_hash: tokenHash },
    });

    if (!record) {
      return false;
    }

    await prisma.refresh_tokens.updateMany({
      where: {
        family_id: record.family_id,
        revoked_at: null,
      },
      data: {
        revoked_at: new Date(),
      },
    });

    return true;
  }

  /**
   * Revokes all active refresh tokens for a user.
   */
  static async revokeAllUserTokens(userId: string): Promise<number> {
    const result = await prisma.refresh_tokens.updateMany({
      where: {
        user_id: userId,
        revoked_at: null,
      },
      data: {
        revoked_at: new Date(),
      },
    });
    return result.count;
  }
}
