// Smoke test for the WhatsApp webhook (signature check, code handshake, sender allow-list).
// Usage (dashboard running with WHATSAPP_APP_SECRET=testsecret, WHATSAPP_VERIFY_TOKEN=verify-me):
//   node scripts/test-webhooks.mjs http://localhost:3100 path/to/applyforme.db
import crypto from "node:crypto";
import Database from "better-sqlite3";

const [base = "http://localhost:3000", dbPath] = process.argv.slice(2);
const SECRET = process.env.WHATSAPP_APP_SECRET ?? "testsecret";
const VERIFY = process.env.WHATSAPP_VERIFY_TOKEN ?? "verify-me";
const db = new Database(dbPath);
let failed = 0;
const check = (name, ok, extra = "") => { console.log(`${ok ? "PASS" : "FAIL"}  ${name} ${extra}`); if (!ok) failed++; };
const wa = () => JSON.parse(db.prepare("SELECT value FROM kv WHERE key='whatsapp'").get()?.value ?? '{"status":"disconnected"}');

const body = (from, text) => JSON.stringify({ entry: [{ changes: [{ value: { messages: [{ from, type: "text", text: { body: text } }] } }] }] });
const post = (raw, sig) => fetch(`${base}/api/whatsapp/webhook`, { method: "POST", body: raw, headers: { "x-hub-signature-256": sig ?? "sha256=" + crypto.createHmac("sha256", SECRET).update(raw).digest("hex") } });

// 1. Meta's one-time verification handshake
let r = await fetch(`${base}/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=${VERIFY}&hub.challenge=12345`);
check("GET verify with right token echoes challenge", r.status === 200 && (await r.text()) === "12345");
r = await fetch(`${base}/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=12345`);
check("GET verify with wrong token is rejected", r.status === 403);

// 2. Forged / unsigned POSTs are rejected
r = await post(body("919876543210", "CONNECT ABC234"), "sha256=" + "0".repeat(64));
check("POST with bad signature -> 401", r.status === 401);

// 3. Handshake: pending code + correct message from the phone -> connected
db.prepare("INSERT INTO kv (key,value) VALUES ('whatsapp',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value")
  .run(JSON.stringify({ status: "pending", code: "ABC234", expiresAt: new Date(Date.now() + 600000).toISOString() }));
r = await post(body("919876543210", "CONNECT WRONG1"));
check("wrong code does not connect", r.status === 200 && wa().status === "pending");
r = await post(body("919876543210", "connect abc234"));
check("correct code (case-insensitive) connects the sender", r.status === 200 && wa().status === "connected" && wa().waId === "919876543210", JSON.stringify(wa()));

// 4. After connecting only that number is served; a stranger can't take over
r = await post(body("911111111111", "CONNECT ABC234"));
check("stranger cannot re-use the code", r.status === 200 && wa().waId === "919876543210");
r = await post(body("919876543210", "status"));
check("connected number can send STATUS without a 5xx", r.status === 200);

// 5. Expired code
db.prepare("UPDATE kv SET value=? WHERE key='whatsapp'").run(JSON.stringify({ status: "pending", code: "ZZZ999", expiresAt: new Date(Date.now() - 1000).toISOString() }));
await post(body("918888888888", "CONNECT ZZZ999"));
check("expired code is ignored", wa().status === "pending");

console.log(failed ? `\n${failed} FAILED` : "\nAll webhook checks passed");
process.exit(failed ? 1 : 0);
