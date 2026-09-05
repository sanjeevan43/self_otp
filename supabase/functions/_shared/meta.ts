export interface SendOtpMessageOptions {
  phoneNumberId?: string;
  accessToken?: string;
  recipientPhone: string;
  otpCode: string;
  templateName?: string;
  language?: string;
}

export interface MetaSendResult {
  success: boolean;
  messageId: string;
  rawResponse?: unknown;
  error?: string;
}

export async function sendWhatsAppOtp(options: SendOtpMessageOptions): Promise<MetaSendResult> {
  const version = Deno.env.get("META_API_VERSION") || "v20.0";
  const phoneNumberId = options.phoneNumberId || Deno.env.get("META_PHONE_NUMBER_ID");
  const accessToken = options.accessToken || Deno.env.get("META_ACCESS_TOKEN");

  // Check if credentials are mock/missing
  const isMock =
    !accessToken ||
    accessToken === "mock_meta_access_token" ||
    !phoneNumberId ||
    phoneNumberId === "100000000000000";

  if (isMock) {
    console.log(
      `[MOCK META DISPATCH] Sending OTP "${options.otpCode}" to ${options.recipientPhone} (mock mode)`
    );
    return {
      success: true,
      messageId: `wamid.mock_${crypto.randomUUID()}`,
      rawResponse: {
        messaging_product: "whatsapp",
        contacts: [{ input: options.recipientPhone, wa_id: options.recipientPhone }],
        messages: [{ id: `wamid.mock_${crypto.randomUUID()}` }],
      },
    };
  }

  // Real Meta WhatsApp Cloud API request
  const url = `https://graph.facebook.com/${version}/${phoneNumberId}/messages`;
  const templateName = options.templateName || "otp_verification";
  const language = options.language || "en_US";

  const payload = {
    messaging_product: "whatsapp",
    recipient_type: "individual",
    to: options.recipientPhone,
    type: "template",
    template: {
      name: templateName,
      language: { code: language },
      components: [
        {
          type: "body",
          parameters: [
            {
              type: "text",
              text: options.otpCode,
            },
          ],
        },
        {
          type: "button",
          sub_type: "url",
          index: "0",
          parameters: [
            {
              type: "text",
              text: options.otpCode,
            },
          ],
        },
      ],
    },
  };

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    if (!response.ok) {
      console.error("[META API ERROR]", data);
      return {
        success: false,
        messageId: "",
        error: data.error?.message || "Meta API dispatch failed",
        rawResponse: data,
      };
    }

    const messageId = data.messages?.[0]?.id || "";
    return {
      success: true,
      messageId,
      rawResponse: data,
    };
  } catch (err: unknown) {
    const errorMessage = err instanceof Error ? err.message : String(err);
    console.error("[META NETWORK ERROR]", errorMessage);
    return {
      success: false,
      messageId: "",
      error: errorMessage,
    };
  }
}
