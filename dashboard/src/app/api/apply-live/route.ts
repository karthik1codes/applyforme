import fs from "node:fs";
import path from "node:path";
import { auth, authDisabled } from "@/auth";

const ROOT = path.resolve(process.cwd(), "..");
const DATA = path.join(ROOT, "data");
const PNG = path.join(DATA, "apply-live.png");
const JSON_PATH = path.join(DATA, "apply-live.json");

/** Live browser snapshot while the applier runs (PNG + status JSON). */
export async function GET(req: Request) {
  if (!authDisabled() && !(await auth())) {
    return new Response("Unauthorized", { status: 401 });
  }
  const want = new URL(req.url).searchParams.get("format") || "meta";

  if (want === "png") {
    if (!fs.existsSync(PNG)) return new Response("Not found", { status: 404 });
    const buf = fs.readFileSync(PNG);
    return new Response(buf, {
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "no-store, max-age=0",
        "X-Content-Type-Options": "nosniff",
      },
    });
  }

  let meta: Record<string, unknown> = { active: false };
  if (fs.existsSync(JSON_PATH)) {
    try {
      meta = JSON.parse(fs.readFileSync(JSON_PATH, "utf8"));
      const age = Date.now() / 1000 - Number(meta.updated_at || 0);
      meta.active = age < 120 && meta.phase !== "done";
      meta.has_image = fs.existsSync(PNG);
      meta.age_sec = Math.round(age);
    } catch {
      meta = { active: false };
    }
  }
  return Response.json(meta, { headers: { "Cache-Control": "no-store" } });
}
