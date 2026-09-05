export interface SendMessageResult {
  success: boolean;
  providerMessageId?: string;
  isTemporaryError: boolean;
  errorMessage?: string;
}

export interface WhatsAppProvider {
  sendOtp(
    phoneNumber: string,
    otpCode: string,
    templateName?: string,
    languageCode?: string
  ): Promise<SendMessageResult>;
}
