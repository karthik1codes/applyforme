import crypto from "node:crypto";
import { kvGet, kvSet, overview } from "@/lib/db";

/**
 * WhatsApp Cloud API (official, Meta). Connect flow:
 *  1. Dashboard generates a one-time code and a wa.me link:  "CONNECT <code>"
 *  2. The user sends that message from their phone to the business number.
 *  3. Meta calls /api/whatsapp/webhook; we match the code and store the sender as the connected number.
 *  4. From then on that number can message "status" and gets its applied-jobs count back.
 * User-initiated messages open a 24h window, so no pre-approved templates are needed.
 */
const GRAPH = "https://graph.facebook.com/v21.0";

export type WaState = {
  status: "disconnected" | "pending" | "connected";
  code?: string;
  expiresAt?: string;
  waId?: string;
  connectedAt?: string;
};

export function waConfig() {
  const c = {
    token: process.env.WHATSAPP_TOKEN ?? "",
    phoneNumberId: process.env.WHATSAPP_PHONE_NUMBER_ID ?? "",
    businessNumber: (process.env.WHATSAPP_BUSINESS_NUMBER ?? "").replace(/\D/g, ""),
    appSecret: process.env.WHATSAPP_APP_SECRET ?? "",
    verifyToken: process.env.WHATSAPP_VERIFY_TOKEN ?? "",
  };
  const missing = Object.entries({
    WHATSAPP_TOKEN: c.token, WHATSAPP_PHONE_NUMBER_ID: c.phoneNumberId, WHATSAPP_BUSINESS_NUMBER: c.businessNumber,
    WHATSAPP_APP_SECRET: c.appSecret, WHATSAPP_VERIFY_TOKEN: c.verifyToken,
  }).filter(([, v]) => !v).map(([k]) => k);
  return { ...c, missing, configured: missing.length === 0 };
}

export const getWa = (): WaState => kvGet<WaState>("whatsapp", { status: "disconnected" });
export const setWa = (s: WaState) => kvSet("whatsapp", s);

export function newCode(): WaState {
  const alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"; // no look-alikes
  const code = Array.from(crypto.randomBytes(6), (b) => alphabet[b % alphabet.length]).join("");
  const s: WaState = { status: "pending", code, expiresAt: new Date(Date.now() + 15 * 60_000).toISOString() };
  setWa(s);
  return s;
}

export function connectLink(code: string): string {
  return `https://wa.me/${waConfig().businessNumber}?text=${encodeURIComponent(`CONNECT ${code}`)}`;
}

export function verifySignature(raw: string, header: string | null): boolean {
  const { appSecret } = waConfig();
  if (!appSecret || !header?.startsWith("sha256=")) return false;
  const expected = crypto.createHmac("sha256", appSecret).update(raw).digest("hex");
  const got = header.slice(7);
  return got.length === expected.length && crypto.timingSafeEqual(Buffer.from(got), Buffer.from(expected));
}

export async function sendText(to: string, body: string): Promise<{ ok: boolean; error?: string }> {
  const { token, phoneNumberId } = waConfig();
  if (!token || !phoneNumberId) return { ok: false, error: "WhatsApp is not configured" };
  try {
    const r = await fetch(`${GRAPH}/${phoneNumberId}/messages`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ messaging_product: "whatsapp", to, type: "text", text: { body } }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!r.ok) return { ok: false, error: `${r.status} ${(await r.text()).slice(0, 200)}` };
    return { ok: true };
  } catch (e) {
    // Never let a failed reply break webhook handling (Meta would retry the delivery).
    return { ok: false, error: e instanceof Error ? e.message : "network error" };
  }
}

export function statusText(): string {
  const o = overview();
  return [
    "applyforme status",
    `Applied: ${o.applied} total (${o.appliedToday} today, ${o.appliedWeek} this week)`,
    `Ready to apply: ${o.ready}`,
    `Need your answers: ${o.needsFeedback}`,
    `Employer replies: ${o.replies}`,
  ].join("\n");
}

/** Handle one inbound WhatsApp text. Messages from anyone but the connected number are ignored. */
export async function handleIncoming(from: string, text: string): Promise<void> {
  const st = getWa();
  const t = text.trim();

  const m = t.match(/^connect\s+([a-z0-9]{6})$/i);
  if (m && st.status === "pending" && st.code && st.expiresAt && new Date(st.expiresAt) > new Date()) {
    if (m[1].toUpperCase() === st.code) {
      setWa({ status: "connected", waId: from, connectedAt: new Date().toISOString() });
      await sendText(from, `Connected to applyforme.\n\n${statusText()}\n\nReply STATUS any time to see this again.`);
    }
    return;
  }

  if (st.status === "connected" && st.waId === from) {
    if (/^(status|applied|stats|count)$/i.test(t)) await sendText(from, statusText());
    else await sendText(from, "Send STATUS to see how many jobs you've applied to.");
  }
}
