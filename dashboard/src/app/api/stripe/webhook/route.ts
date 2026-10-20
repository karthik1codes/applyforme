/** Legacy Stripe webhook — billing now uses Dodo Payments at /api/webhook/dodo-payments. */
export async function POST() {
  return new Response("Stripe billing has been replaced by Dodo Payments", { status: 410 });
}
