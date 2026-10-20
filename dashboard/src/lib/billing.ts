import DodoPayments from "dodopayments";
import { auth } from "@/auth";
import { kvGet, kvSet } from "@/lib/db";

/** Edit these freely: plan names, prices and feature copy are placeholders for your product. */
export const PLANS = [
  { id: "free", name: "Starter", price: 0, blurb: "Try the pipeline", features: ["Up to 10 tailored applications / month", "Dashboard + resume showcase", "Overleaf LaTeX export"] },
  { id: "pro", name: "Pro", price: 19, blurb: "For an active job search", popular: true, features: ["Up to 150 tailored applications / month", "WhatsApp status updates", "Applied inbox (email replies)", "Priority form-filling fixes"] },
  { id: "max", name: "Unlimited", price: 49, blurb: "Maximum volume", features: ["Unlimited applications", "Everything in Pro", "Multiple resume categories", "Early access to new ATS support"] },
] as const;

export type PlanId = (typeof PLANS)[number]["id"];
export type BillingState = {
  plan: PlanId;
  status: "none" | "active" | "past_due" | "canceled";
  customerId?: string;
  subscriptionId?: string;
  currentPeriodEnd?: string;
};

export const currency = () => (process.env.BILLING_CURRENCY ?? "usd").toLowerCase();
export const appUrl = () => process.env.APP_URL ?? "http://localhost:3000";
export const getBilling = (): BillingState => kvGet<BillingState>("billing", { plan: "free", status: "none" });
export const setBilling = (b: BillingState) => kvSet("billing", b);

export function dodoEnvironment(): "test_mode" | "live_mode" {
  const raw = (process.env.DODO_PAYMENTS_ENVIRONMENT || "test_mode").trim().toLowerCase();
  return raw === "live_mode" || raw === "live" ? "live_mode" : "test_mode";
}

export function dodoEnabled(): boolean {
  return !!process.env.DODO_PAYMENTS_API_KEY?.trim();
}

export function dodo(): DodoPayments | null {
  const key = process.env.DODO_PAYMENTS_API_KEY?.trim();
  if (!key) return null;
  return new DodoPayments({ bearerToken: key, environment: dodoEnvironment() });
}

/** Map plan id → Dodo product id (create products in the Dodo dashboard / API). */
export function productIdForPlan(planId: PlanId): string | undefined {
  if (planId === "pro") return process.env.DODO_PAYMENTS_PRODUCT_PRO?.trim() || undefined;
  if (planId === "max") return process.env.DODO_PAYMENTS_PRODUCT_MAX?.trim() || undefined;
  return undefined;
}

export function planFromProductId(productId: string | undefined | null): PlanId | undefined {
  if (!productId) return undefined;
  const pro = process.env.DODO_PAYMENTS_PRODUCT_PRO?.trim();
  const max = process.env.DODO_PAYMENTS_PRODUCT_MAX?.trim();
  if (pro && productId === pro) return "pro";
  if (max && productId === max) return "max";
  return undefined;
}

export async function createCheckout(planId: PlanId): Promise<string> {
  const client = dodo();
  const plan = PLANS.find((p) => p.id === planId);
  const productId = productIdForPlan(planId);
  if (!client) throw new Error("DODO_PAYMENTS_API_KEY is not set");
  if (!plan || plan.price === 0) throw new Error("Pick a paid plan");
  if (!productId) throw new Error(`Missing DODO_PAYMENTS_PRODUCT_${planId.toUpperCase()} product id`);

  const session = await auth();
  const email = session?.user?.email ?? undefined;
  const name = session?.user?.name ?? undefined;
  const billing = getBilling();

  const checkout = await client.checkoutSessions.create({
    product_cart: [{ product_id: productId, quantity: 1 }],
    ...(billing.customerId
      ? { customer: { customer_id: billing.customerId } }
      : email
        ? { customer: { email, ...(name ? { name } : {}) } }
        : {}),
    metadata: { plan: plan.id },
    return_url: `${appUrl()}/billing?checkout=success`,
  });

  if (!checkout.checkout_url) throw new Error("Dodo Payments did not return a checkout URL");
  return checkout.checkout_url;
}

/** After hosted checkout redirect: `?subscription_id=…&status=active`. */
export async function syncCheckoutReturn(subscriptionId: string): Promise<void> {
  const client = dodo();
  if (!client || !subscriptionId) return;
  const sub = await client.subscriptions.retrieve(subscriptionId);
  applyDodoSubscription(sub);
}

type DodoSub = {
  subscription_id: string;
  product_id: string;
  status: string;
  customer?: { customer_id?: string };
  metadata?: Record<string, unknown>;
  next_billing_date?: string | Date | null;
};

export function applyDodoSubscription(sub: DodoSub): void {
  const prev = getBilling();
  const fromMeta = typeof sub.metadata?.plan === "string" ? (sub.metadata.plan as PlanId) : undefined;
  const fromProduct = planFromProductId(sub.product_id);
  const plan = fromMeta && fromMeta !== "free" ? fromMeta : fromProduct ?? prev.plan;

  let status: BillingState["status"];
  if (sub.status === "active") status = "active";
  else if (sub.status === "on_hold" || sub.status === "pending") status = "past_due";
  else if (sub.status === "cancelled" || sub.status === "expired" || sub.status === "failed") status = "canceled";
  else status = prev.status;

  setBilling({
    ...prev,
    plan: status === "canceled" ? "free" : plan,
    status: status === "canceled" ? "canceled" : status,
    customerId: sub.customer?.customer_id ?? prev.customerId,
    subscriptionId: sub.subscription_id,
    currentPeriodEnd: sub.next_billing_date
      ? new Date(sub.next_billing_date).toISOString()
      : prev.currentPeriodEnd,
  });
}

export function customerPortalUrl(customerId: string): string {
  const base = appUrl().replace(/\/$/, "");
  return `${base}/api/customer-portal?customer_id=${encodeURIComponent(customerId)}`;
}
