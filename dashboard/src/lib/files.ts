import fs from "node:fs";
import path from "node:path";
import { OUTPUT_DIR } from "@/lib/db";

/** Read a generated artifact from output/ (basename only). */
export function readOutput(name: string | null): string | null {
  if (!name) return null;
  try {
    return fs.readFileSync(path.join(OUTPUT_DIR, path.basename(name)), "utf8");
  } catch {
    return null;
  }
}
