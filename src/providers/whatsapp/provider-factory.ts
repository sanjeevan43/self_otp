import { env } from "../../config/env.js";
import { MetaWhatsAppProvider } from "./meta-whatsapp-provider.js";
import { MockWhatsAppProvider } from "./mock-whatsapp-provider.js";
import type { WhatsAppProvider, SendMessageResult } from "./whatsapp-provider.interface.js";

export function getWhatsAppProvider(): WhatsAppProvider {
  const providerType = process.env.WHATSAPP_PROVIDER || env.WHATSAPP_PROVIDER;
  if (providerType === "meta") {
    return new MetaWhatsAppProvider();
  }
  if (providerType === "mock") {
    return new MockWhatsAppProvider();
  }
  throw new Error(`Unsupported WHATSAPP_PROVIDER: ${providerType}`);
}

export const whatsappProvider: WhatsAppProvider = {
  async sendOtp(phoneNumber, otpCode, templateName, languageCode): Promise<SendMessageResult> {
    const provider = getWhatsAppProvider();
    return await provider.sendOtp(phoneNumber, otpCode, templateName, languageCode);
  },
};
