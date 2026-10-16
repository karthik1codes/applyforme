import Stripe from "stripe";
import { kvGet, kvSet } from "@/lib/db";

/** Edit these freely: plan names, prices and feature copy are placeholders for your product. */
export const PLANS = [
  { id: "free", name: "Starter", price: 0, blurb: "Try the pipeline", features: ["Up to 10 tailored applications / month", "Dashboard + resume showcase", "Overleaf LaTeX export"] },
  { id: "pro", name: "Pro", price: 19, blurb: "For an active job search", popular: true, features: ["Up to 150 tailored applications / month", "WhatsApp status updates", "Applied inbox (email replies)", "Priority form-filling fixes"] },
  { id: "max", name: "Unlimited", price: 49, blurb: "Maximum volume", features: ["Unlimited applications", "Everything in Pro", "Multiple resume categories", "Early access to new ATS support"] },
] as const;

export type PlanId = (typeof PLANS)[number]["id"];
export type BillingState = {
  plan: PlanId; status: "none" | "active" | "past_due" | "canceled";
  customerId?: string; subscriptionId?: string; currentPeriodEnd?: string;
};

export const currency = () => (process.env.BILLING_CURRENCY ?? "usd").toLowerCase();
export const appUrl = () => process.env.APP_URL ?? "http://localhost:3000";
export const getBilling = (): BillingState => kvGet<BillingState>("billing", { plan: "free", status: "none" });
export const setBilling = (b: BillingState) => kvSet("billing", b);

export function stripe(): Stripe | null {
  return process.env.STRIPE_SECRET_KEY ? new Stripe(process.env.STRIPE_SECRET_KEY) : null;
}

export async function createCheckout(planId: PlanId): Promise<string> {
  const s = stripe();
  const plan = PLANS.find((p) => p.id === planId);
  if (!s) throw new Error("STRIPE_SECRET_KEY is not set");
  if (!plan || plan.price === 0) throw new Error("Pick a paid plan");
  const b = getBilling();
  const session = await s.checkout.sessions.create({
    mode: "subscription",
    ...(b.customerId ? { customer: b.customerId } : {}),
    line_items: [{
      quantity: 1,
      price_data: {
        currency: currency(), unit_amount: plan.price * 100, recurring: { interval: "month" },
        product_data: { name: `applyforme ${plan.name}` },
      },
    }],
    metadata: { plan: plan.id },
    subscription_data: { metadata: { plan: plan.id } },
    success_url: `${appUrl()}/billing?checkout=success&session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${appUrl()}/billing?checkout=cancelled`,
  });
  if (!session.url) throw new Error("Stripe did not return a checkout URL");
  return session.url;
}

/** Idempotent: read a finished Checkout Session and record the subscription locally (works without webhooks). */
export async function syncCheckoutSession(sessionId: string): Promise<void> {
  const s = stripe();
  if (!s) return;
  const session = await s.checkout.sessions.retrieve(sessionId, { expand: ["subscription"] });
  if (session.status !== "complete") return;
  const sub = session.subscription as Stripe.Subscription | null;
  setBilling({
    plan: (session.metadata?.plan as PlanId) ?? "pro",
    status: "active",
    customerId: typeof session.customer === "string" ? session.customer : session.customer?.id,
    subscriptionId: sub?.id,
    currentPeriodEnd: periodEnd(sub),
  });
}

export function applySubscription(sub: Stripe.Subscription): void {
  const prev = getBilling();
  const status = sub.status === "active" || sub.status === "trialing" ? "active" : sub.status === "past_due" ? "past_due" : "canceled";
  setBilling({
    ...prev,
    plan: status === "canceled" ? "free" : ((sub.metadata?.plan as PlanId) ?? prev.plan),
    status,
    customerId: typeof sub.customer === "string" ? sub.customer : sub.customer.id,
    subscriptionId: sub.id,
    currentPeriodEnd: periodEnd(sub),
  });
}

function periodEnd(sub: Stripe.Subscription | null): string | undefined {
  // Newer Stripe API versions put the period on the subscription item.
  const end = (sub as unknown as { current_period_end?: number })?.current_period_end ?? sub?.items?.data?.[0]?.current_period_end;
  return end ? new Date(end * 1000).toISOString() : undefined;
}
