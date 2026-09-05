import crypto from "node:crypto";
import { logger } from "../../plugins/logger.js";
import type { SendMessageResult, WhatsAppProvider } from "./whatsapp-provider.interface.js";

export class MockWhatsAppProvider implements WhatsAppProvider {
  async sendOtp(
    phoneNumber: string,
    _otpCode: string,
    _templateName = "otp_auth_v1",
    _languageCode = "en_US"
  ): Promise<SendMessageResult> {
    const mockWamid = `wamid.HBgL${crypto.randomBytes(16).toString("hex")}`;
    logger.info(
      { phoneNumber, mockWamid },
      "[MOCK META API] Simulated OTP delivery successfully generated"
    );

    return {
      success: true,
      providerMessageId: mockWamid,
      isTemporaryError: false,
    };
  }
}
