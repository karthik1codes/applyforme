import { Checkout } from "@dodopayments/nextjs";
import { appUrl, dodoEnvironment } from "@/lib/billing";

/** Hosted checkout sessions — see https://docs.dodopayments.com/developer-resources/nextjs-adaptor */
export const POST = Checkout({
  bearerToken: process.env.DODO_PAYMENTS_API_KEY,
  returnUrl: process.env.DODO_PAYMENTS_RETURN_URL || `${appUrl()}/billing?checkout=success`,
  environment: dodoEnvironment(),
  type: "session",
});
