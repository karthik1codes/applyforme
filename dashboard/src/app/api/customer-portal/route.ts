import { CustomerPortal } from "@dodopayments/nextjs";
import { dodoEnvironment } from "@/lib/billing";

/** Customer portal — https://docs.dodopayments.com/developer-resources/nextjs-adaptor */
export const GET = CustomerPortal({
  bearerToken: process.env.DODO_PAYMENTS_API_KEY,
  environment: dodoEnvironment(),
});
