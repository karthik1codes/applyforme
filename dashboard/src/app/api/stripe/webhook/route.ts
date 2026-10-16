import type Stripe from "stripe";
import { applySubscription, stripe, syncCheckoutSession } from "@/lib/billing";

// Stripe -> local billing state. Configure STRIPE_WEBHOOK_SECRET (`stripe listen --forward-to localhost:3000/api/stripe/webhook`).
export async function POST(req: Request) {
  const s = stripe();
  const secret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!s || !secret) return new Response("Stripe webhook not configured", { status: 503 });

  const raw = await req.text();
  let event: Stripe.Event;
  try {
    event = s.webhooks.constructEvent(raw, req.headers.get("stripe-signature") ?? "", secret);
  } catch {
    return new Response("Bad signature", { status: 400 });
  }

  if (event.type === "checkout.session.completed") await syncCheckoutSession((event.data.object as Stripe.Checkout.Session).id);
  if (event.type === "customer.subscription.updated" || event.type === "customer.subscription.deleted") {
    applySubscription(event.data.object as Stripe.Subscription);
  }
  return new Response("ok");
}
