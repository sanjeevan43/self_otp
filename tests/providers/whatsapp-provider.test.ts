import { describe, it, expect, afterEach } from "vitest";
import { getWhatsAppProvider } from "../../src/providers/whatsapp/provider-factory.js";
import { MetaWhatsAppProvider } from "../../src/providers/whatsapp/meta-whatsapp-provider.js";
import { MockWhatsAppProvider } from "../../src/providers/whatsapp/mock-whatsapp-provider.js";

describe("WhatsApp Provider Explicit Selection & No Silent Fallback", () => {
  const originalEnv = process.env.WHATSAPP_PROVIDER;

  afterEach(() => {
    process.env.WHATSAPP_PROVIDER = originalEnv;
  });

  it("Explicitly selects MockWhatsAppProvider when WHATSAPP_PROVIDER=mock", () => {
    process.env.WHATSAPP_PROVIDER = "mock";
    const provider = getWhatsAppProvider();
    expect(provider).toBeInstanceOf(MockWhatsAppProvider);
  });

  it("Explicitly selects MetaWhatsAppProvider when WHATSAPP_PROVIDER=meta", () => {
    process.env.WHATSAPP_PROVIDER = "meta";
    const provider = getWhatsAppProvider();
    expect(provider).toBeInstanceOf(MetaWhatsAppProvider);
  });

  it("Throws explicit error if WHATSAPP_PROVIDER is invalid", () => {
    process.env.WHATSAPP_PROVIDER = "twilio";
    expect(() => getWhatsAppProvider()).toThrow(/Unsupported WHATSAPP_PROVIDER/);
  });

  it("MetaWhatsAppProvider never silently succeeds when token is invalid mock token", async () => {
    const metaProvider = new MetaWhatsAppProvider();
    // With mock/invalid access token, Meta Cloud API must fail (never silently return success)
    const result = await metaProvider.sendOtp("+14155559999", "123456");
    expect(result.success).toBe(false);
    expect(result.errorMessage).toBeDefined();
    expect(result.providerMessageId).toBeUndefined();
  });
});
