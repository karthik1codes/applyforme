import { CheckIcon } from "lucide-react";
import { openBillingPortal, startCheckout } from "@/app/actions";
import { PageContainer } from "@/components/page-container";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { PLANS, currency, getBilling, stripe, syncCheckoutSession } from "@/lib/billing";

export default async function Page({ searchParams }: { searchParams: Promise<{ checkout?: string; session_id?: string; error?: string }> }) {
  const q = await searchParams;
  // Returning from Stripe Checkout: record the subscription right away (the webhook does the same, idempotently).
  if (q.checkout === "success" && q.session_id) {
    try {
      await syncCheckoutSession(q.session_id);
    } catch {
      /* the webhook will catch up */
    }
  }
  const billing = getBilling();
  const enabled = !!stripe();
  const fmt = new Intl.NumberFormat("en-US", { style: "currency", currency: currency().toUpperCase(), maximumFractionDigits: 0 });

  return (
    <PageContainer title="Billing" description="Pick a plan. Payments are handled by Stripe Checkout: card details never touch this app.">
      {q.checkout === "success" && (
        <Alert>
          <AlertTitle>Payment received</AlertTitle>
          <AlertDescription>Thanks! Your plan is now {PLANS.find((p) => p.id === billing.plan)?.name ?? billing.plan}.</AlertDescription>
        </Alert>
      )}
      {q.checkout === "cancelled" && (
        <Alert>
          <AlertTitle>Checkout cancelled</AlertTitle>
          <AlertDescription>No charge was made.</AlertDescription>
        </Alert>
      )}
      {q.error && (
        <Alert variant="destructive">
          <AlertTitle>Couldn&apos;t start checkout</AlertTitle>
          <AlertDescription>{q.error}</AlertDescription>
        </Alert>
      )}
      {!enabled && (
        <Alert>
          <AlertTitle>Stripe isn&apos;t configured yet</AlertTitle>
          <AlertDescription>
            Add <code>STRIPE_SECRET_KEY</code> (test key: sk_test_...) to the root <code>.env</code> and restart. For automatic status updates also set{" "}
            <code>STRIPE_WEBHOOK_SECRET</code> and run <code>stripe listen --forward-to localhost:3000/api/stripe/webhook</code>.
          </AlertDescription>
        </Alert>
      )}

      <Card size="sm">
        <CardContent className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm">
            Current plan: <b>{PLANS.find((p) => p.id === billing.plan)?.name}</b>{" "}
            <Badge variant="secondary">{billing.status === "none" ? "free" : billing.status}</Badge>
            {billing.currentPeriodEnd && <span className="ml-2 text-muted-foreground">renews {new Date(billing.currentPeriodEnd).toLocaleDateString()}</span>}
          </div>
          {billing.customerId && enabled && (
            <form action={openBillingPortal}>
              <Button type="submit" variant="outline" size="sm">
                Manage subscription
              </Button>
            </form>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 @3xl/main:grid-cols-3">
        {PLANS.map((p) => {
          const current = billing.plan === p.id && (p.id === "free" || billing.status === "active");
          return (
            <Card key={p.id} className={"popular" in p && p.popular ? "ring-2 ring-primary" : ""}>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  {p.name}
                  {"popular" in p && p.popular && <Badge>Most popular</Badge>}
                </CardTitle>
                <CardDescription>{p.blurb}</CardDescription>
                <div className="pt-2 text-3xl font-semibold tabular-nums">
                  {p.price === 0 ? "Free" : fmt.format(p.price)}
                  {p.price > 0 && <span className="text-sm font-normal text-muted-foreground"> / month</span>}
                </div>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  {p.features.map((f) => (
                    <li key={f} className="flex items-start gap-2">
                      <CheckIcon className="mt-0.5 size-4 shrink-0 text-emerald-500" />
                      {f}
                    </li>
                  ))}
                </ul>
              </CardContent>
              <CardFooter>
                {p.price === 0 ? (
                  <Button variant="outline" disabled className="w-full">
                    {current ? "Current plan" : "Included"}
                  </Button>
                ) : (
                  <form action={startCheckout.bind(null, p.id)} className="w-full">
                    <Button type="submit" className="w-full" disabled={!enabled || current}>
                      {current ? "Current plan" : `Subscribe to ${p.name}`}
                    </Button>
                  </form>
                )}
              </CardFooter>
            </Card>
          );
        })}
      </div>
    </PageContainer>
  );
}
