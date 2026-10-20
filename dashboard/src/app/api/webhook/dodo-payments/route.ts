import { Webhooks } from "@dodopayments/nextjs";
import { applyDodoSubscription } from "@/lib/billing";

/**
 * Dodo Payments webhooks (Standard Webhooks).
 * Configure the endpoint in Developer → Webhooks and set DODO_PAYMENTS_WEBHOOK_KEY.
 * Docs: https://docs.dodopayments.com/developer-resources/integration-guide#webhooks
 */
const key = process.env.DODO_PAYMENTS_WEBHOOK_KEY?.trim();

export const POST = key
  ? Webhooks({
      webhookKey: key,
      onSubscriptionActive: async (payload) => {
        applyDodoSubscription(payload.data);
      },
      onSubscriptionRenewed: async (payload) => {
        applyDodoSubscription(payload.data);
      },
      onSubscriptionUpdated: async (payload) => {
        applyDodoSubscription(payload.data);
      },
      onSubscriptionPlanChanged: async (payload) => {
        applyDodoSubscription(payload.data);
      },
      onSubscriptionOnHold: async (payload) => {
        applyDodoSubscription(payload.data);
      },
      onSubscriptionCancelled: async (payload) => {
        applyDodoSubscription(payload.data);
      },
      onSubscriptionExpired: async (payload) => {
        applyDodoSubscription(payload.data);
      },
      onSubscriptionFailed: async (payload) => {
        applyDodoSubscription(payload.data);
      },
    })
  : async () => new Response("DODO_PAYMENTS_WEBHOOK_KEY is not set", { status: 503 });
