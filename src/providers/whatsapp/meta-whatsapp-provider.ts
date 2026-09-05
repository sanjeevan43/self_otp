import { env } from "../../config/env.js";
import { logger } from "../../plugins/logger.js";
import type { SendMessageResult, WhatsAppProvider } from "./whatsapp-provider.interface.js";

export class MetaWhatsAppProvider implements WhatsAppProvider {
  private formatPayload(
    phoneNumber: string,
    otpCode: string,
    templateName = "otp_auth_v1",
    languageCode = "en_US"
  ) {
    return {
      messaging_product: "whatsapp",
      recipient_type: "individual",
      to: phoneNumber,
      type: "template",
      template: {
        name: templateName,
        language: { code: languageCode },
        components: [
          {
            type: "body",
            parameters: [{ type: "text", text: otpCode }],
          },
          {
            type: "button",
            sub_type: "url",
            index: "0",
            parameters: [{ type: "text", text: otpCode }],
          },
        ],
      },
    };
  }

  async sendOtp(
    phoneNumber: string,
    otpCode: string,
    templateName = "otp_auth_v1",
    languageCode = "en_US"
  ): Promise<SendMessageResult> {
    const url = `https://graph.facebook.com/${env.META_API_VERSION}/${env.META_PHONE_NUMBER_ID}/messages`;
    const payload = this.formatPayload(phoneNumber, otpCode, templateName, languageCode);

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.META_ACCESS_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        const data = (await response.json()) as { messages?: Array<{ id: string }> };
        const wamid = data.messages?.[0]?.id;
        return {
          success: true,
          providerMessageId: wamid,
          isTemporaryError: false,
        };
      }

      const statusCode = response.status;
      const errorText = await response.text();
      logger.error({ statusCode, errorText }, "Meta Graph API message dispatch error");

      const isTemporary = statusCode >= 500 || statusCode === 429;
      return {
        success: false,
        isTemporaryError: isTemporary,
        errorMessage: `Meta API error (HTTP ${statusCode}): ${errorText}`,
      };
    } catch (err: any) {
      logger.warn({ err }, "Network error during Meta Graph API dispatch");
      return {
        success: false,
        isTemporaryError: true,
        errorMessage: `Network error: ${err.message}`,
      };
    }
  }
}
