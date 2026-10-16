import fs from "node:fs";
import path from "node:path";
import { OUTPUT_DIR } from "@/lib/db";

const TYPES: Record<string, string> = {
  ".pdf": "application/pdf",
  ".tex": "text/plain; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
};

/** Serves generated resumes / cover letters from output/. Basename only, extension allow-list: no path traversal. */
export async function GET(req: Request, ctx: { params: Promise<{ name: string }> }) {
  const { name } = await ctx.params;
  const safe = path.basename(decodeURIComponent(name));
  const type = TYPES[path.extname(safe).toLowerCase()];
  const file = path.join(OUTPUT_DIR, safe);
  if (!type || !fs.existsSync(file)) return new Response("Not found", { status: 404 });

  const download = new URL(req.url).searchParams.has("download");
  return new Response(fs.readFileSync(file), {
    headers: {
      "Content-Type": type,
      "Content-Disposition": `${download ? "attachment" : "inline"}; filename="${safe}"`,
      "X-Content-Type-Options": "nosniff",
    },
  });
}
