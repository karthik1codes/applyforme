import { handleIncoming, verifySignature, waConfig } from "@/lib/whatsapp";

// Meta calls this once to verify the webhook URL.
export async function GET(req: Request) {
  const q = new URL(req.url).searchParams;
  const { verifyToken } = waConfig();
  if (verifyToken && q.get("hub.mode") === "subscribe" && q.get("hub.verify_token") === verifyToken) {
    return new Response(q.get("hub.challenge") ?? "", { status: 200 });
  }
  return new Response("Forbidden", { status: 403 });
}

type Payload = {
  entry?: { changes?: { value?: { messages?: { from: string; type: string; text?: { body: string } }[] } }[] }[];
};

// Inbound messages. The signature is mandatory: unsigned/forged requests are rejected.
export async function POST(req: Request) {
  const raw = await req.text();
  if (!waConfig().appSecret) return new Response("WHATSAPP_APP_SECRET not configured", { status: 503 });
  if (!verifySignature(raw, req.headers.get("x-hub-signature-256"))) return new Response("Bad signature", { status: 401 });

  let payload: Payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    return new Response("Bad JSON", { status: 400 });
  }
  for (const e of payload.entry ?? [])
    for (const c of e.changes ?? [])
      for (const m of c.value?.messages ?? [])
        if (m.type === "text" && m.text?.body) await handleIncoming(m.from, m.text.body);
  return new Response("ok");
}
