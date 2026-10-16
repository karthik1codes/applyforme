import path from "node:path";
import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

// One .env for the whole project (Python agents + dashboard): load it from the repo root.
loadEnvConfig(path.resolve(__dirname, ".."));

const nextConfig: NextConfig = {
  // Pages read a live SQLite DB on every request, so the "cacheComponents"/PPR
  // options from the starter template are intentionally not enabled.
  serverExternalPackages: ["better-sqlite3"],
  images: {
    remotePatterns: [{ protocol: "https", hostname: "images.unsplash.com" }],
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
