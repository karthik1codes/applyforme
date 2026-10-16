import { disconnectWhatsApp, generateWhatsAppCode } from "@/app/actions";
import { AutoRefresh } from "@/components/auto-refresh";
import { PageContainer } from "@/components/page-container";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { overview } from "@/lib/db";
import { connectLink, getWa, waConfig } from "@/lib/whatsapp";

export default function Page() {
  const cfg = waConfig();
  let wa = getWa();
  if (wa.status === "pending" && wa.expiresAt && new Date(wa.expiresAt) < new Date()) wa = { status: "disconnected" };
  const o = overview();
  const masked = wa.waId ? `+${wa.waId.slice(0, 2)}••••••${wa.waId.slice(-3)}` : "";

  return (
    <PageContainer title="WhatsApp" description="Link your phone to ask the agents how many jobs they've applied to, right from WhatsApp.">
      {wa.status === "pending" && <AutoRefresh />}

      <div className="grid gap-4 @3xl/main:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Connection
              <Badge variant={wa.status === "connected" ? "default" : "secondary"}>{wa.status}</Badge>
            </CardTitle>
            <CardDescription>Uses the official WhatsApp Business Cloud API. Nobody else can read your counts: only the number you link can query them.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            {!cfg.configured && (
              <Alert>
                <AlertTitle>Setup needed</AlertTitle>
                <AlertDescription>
                  Add these to the root <code>.env</code> and restart the dashboard: <code>{cfg.missing.join(", ")}</code>. See the checklist on the right.
                </AlertDescription>
              </Alert>
            )}

            {wa.status === "connected" && (
              <>
                <p>
                  Linked to <b>{masked}</b>. Message <code className="rounded bg-muted px-1.5 py-0.5">STATUS</code> to the business number any time.
                </p>
                <form action={disconnectWhatsApp}>
                  <Button type="submit" variant="destructive" size="sm">
                    Disconnect
                  </Button>
                </form>
              </>
            )}

            {wa.status === "pending" && wa.code && (
              <>
                <p>
                  Send this exact message from your phone (valid 15 minutes):
                </p>
                <code className="block rounded-md bg-muted px-3 py-2 text-base tracking-widest">CONNECT {wa.code}</code>
                {cfg.configured ? (
                  <a className={buttonVariants()} href={connectLink(wa.code)} target="_blank" rel="noreferrer">
                    Open WhatsApp and send it
                  </a>
                ) : (
                  <p className="text-muted-foreground">Finish the setup first, then this button opens WhatsApp for you.</p>
                )}
                <p className="text-xs text-muted-foreground">This page refreshes automatically once the message arrives.</p>
              </>
            )}

            {wa.status === "disconnected" && (
              <form action={generateWhatsAppCode}>
                <Button type="submit" disabled={!cfg.configured}>
                  Connect WhatsApp
                </Button>
              </form>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>What you&apos;ll get</CardTitle>
            <CardDescription>Reply STATUS and the agents answer with live numbers:</CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap rounded-md bg-muted/50 p-3 font-sans text-sm">
{`applyforme status
Applied: ${o.applied} total (${o.appliedToday} today, ${o.appliedWeek} this week)
Ready to apply: ${o.ready}
Need your answers: ${o.needsFeedback}
Employer replies: ${o.replies}`}
            </pre>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>One-time setup (Meta WhatsApp Cloud API)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <ol className="list-decimal space-y-1.5 pl-5">
            <li>Create a Meta developer app with the <b>WhatsApp</b> product (developers.facebook.com) and note the <code>Phone number ID</code> and a permanent <code>access token</code>.</li>
            <li>Put these in the root <code>.env</code>: <code>WHATSAPP_TOKEN</code>, <code>WHATSAPP_PHONE_NUMBER_ID</code>, <code>WHATSAPP_BUSINESS_NUMBER</code> (digits, with country code), <code>WHATSAPP_APP_SECRET</code>, and any random <code>WHATSAPP_VERIFY_TOKEN</code>.</li>
            <li>Expose this dashboard publicly (for example <code>ngrok http 3000</code>) and set the webhook callback URL to <code>https://&lt;your-host&gt;/api/whatsapp/webhook</code> with your verify token. Subscribe to the <b>messages</b> field.</li>
            <li>With the free test number, add your own phone as an allowed recipient in the Meta dashboard first.</li>
          </ol>
          <p className="text-muted-foreground">
            Missing right now: {cfg.missing.length ? cfg.missing.join(", ") : "nothing, you're set."}
          </p>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
