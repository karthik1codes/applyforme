import fs from "node:fs";
import { dump as yamlDump, load as yamlLoad } from "js-yaml";
import { PROFILE_PATH } from "@/lib/db";

export type ProfileData = {
  personal: Record<string, string>;
  resume_path?: string;
  summary?: string;
  skills?: string[];
  experience?: unknown[];
  education?: unknown[];
  preferences: {
    target_titles?: string[];
    seniority_level?: string;
    current_title?: string;
    years_experience?: number | null;
    locations?: string[];
    reject_locations?: string[];
    remote_only?: boolean;
    min_match_score?: number;
    exclude_keywords?: string[];
  };
  screening?: Record<string, string>;
  compensation?: Record<string, string>;
  sources?: Record<string, unknown>;
  searches?: unknown[];
  onboarding_complete?: boolean;
};

export function loadProfile(): ProfileData {
  const raw = fs.readFileSync(PROFILE_PATH, "utf8");
  const data = yamlLoad(raw) as ProfileData;
  if (!data?.personal) throw new Error("profile.yaml missing personal section");
  data.preferences = data.preferences || {};
  return data;
}

export function saveProfile(data: ProfileData) {
  const header =
    "# Written by the applyforme dashboard / onboarding. Agents read this as the source of truth.\n";
  fs.writeFileSync(PROFILE_PATH, header + yamlDump(data, { lineWidth: 100, noRefs: true }), "utf8");
}

export function profileSummary(): { name: string; email: string } {
  try {
    const p = loadProfile().personal;
    return {
      name: `${p.first_name || ""} ${p.last_name || ""}`.trim() || "You",
      email: p.email || "",
    };
  } catch {
    return { name: "You", email: "" };
  }
}

export function onboardingDone(): boolean {
  try {
    const p = loadProfile();
    return !!(p.onboarding_complete && p.preferences?.seniority_level && p.preferences?.target_titles?.length);
  } catch {
    return false;
  }
}

export function targetLabel(): string {
  try {
    const p = loadProfile().preferences;
    const titles = (p.target_titles || []).slice(0, 2).join(" / ") || "roles";
    return `${p.seniority_level || "mid"} · ${titles}`;
  } catch {
    return "your target roles";
  }
}
