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
  projects?: unknown[];
  honors?: unknown[];
  skill_categories?: unknown[];
  custom_sections?: unknown[];
  resume?: { show_summary?: boolean; portfolio_label?: string };
  preferences: {
    target_titles?: string[];
    seniority_level?: string;
    /** jobs | internships | both — drives which pipeline agents run */
    search_focus?: "jobs" | "internships" | "both" | string;
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
  /** Marketing / onboarding attribution (not ATS company sources). */
  attribution?: {
    how_heard?: string;
    role?: string;
    referral_code?: string;
    invite_code?: string;
  };
  searches?: {
    term: string;
    location?: string;
    sites?: string[];
    results_wanted?: number;
    hours_old?: number;
  }[];
  onboarding_complete?: boolean;
};

const BOARD_SITES = ["indeed", "linkedin", "glassdoor", "zip_recruiter", "google"];

/** Keep JobSpy searches in sync with target titles — discovery always uses these boards. */
export function syncSearches(p: ProfileData): void {
  const titles = p.preferences?.target_titles?.filter(Boolean) || [];
  if (!titles.length) return;
  const locs = (p.preferences?.locations || []).filter((l) => l.toLowerCase() !== "remote");
  const location = locs[0] || p.personal?.location || "";
  p.searches = titles.map((term) => ({
    term,
    location,
    sites: [...BOARD_SITES],
    results_wanted: 25,
    hours_old: 72,
  }));
}

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

/** profile.yaml completeness (agents). Prefer `userOnboardingDone` for per-Gmail gating. */
export function profileOnboardingComplete(p?: ProfileData): boolean {
  try {
    const data = p ?? loadProfile();
    if (!data.onboarding_complete) return false;
    if (!data.preferences?.seniority_level || !data.preferences?.target_titles?.length) return false;
    if (!data.attribution?.how_heard || !data.attribution?.role) return false;
    if (!data.personal?.email || !data.personal?.first_name) return false;
    return true;
  } catch {
    return false;
  }
}

/** @deprecated Use session-aware check via onboarding-gate / userOnboardingDone. */
export function onboardingDone(): boolean {
  return profileOnboardingComplete();
}

/**
 * Bind profile.yaml to the signed-in Google account.
 * A different Gmail than `personal.email` always gets a fresh onboarding pass.
 */
export function applySessionToProfile(
  p: ProfileData,
  user?: { name?: string | null; email?: string | null } | null,
): boolean {
  if (!user) return false;
  let dirty = false;
  const email = (user.email || "").trim();
  const emailNorm = email.toLowerCase();
  const current = (p.personal?.email || "").trim().toLowerCase();

  if (email && current && current !== "local@localhost" && current !== emailNorm) {
    // New Google account on this machine — reset wizard fields so they aren't skipped.
    p.onboarding_complete = false;
    p.attribution = { how_heard: "", role: "", referral_code: "", invite_code: "" };
    p.personal = {
      first_name: "",
      last_name: "",
      email,
      phone: "",
      location: "",
      linkedin: "",
      github: "",
      website: "",
      portfolio: "",
      twitter: "",
    };
    p.preferences = {
      ...(p.preferences || {}),
      current_title: "",
      target_titles: [],
      seniority_level: "junior",
      search_focus: "jobs",
      years_experience: null,
    };
    dirty = true;
  } else if (email && (!p.personal.email || p.personal.email === "local@localhost")) {
    p.personal.email = email;
    dirty = true;
  }

  const name = (user.name || "").trim();
  if (name) {
    const parts = name.split(/\s+/);
    if (!p.personal.first_name && parts[0]) {
      p.personal.first_name = parts[0];
      dirty = true;
    }
    if (!p.personal.last_name && parts.length > 1) {
      p.personal.last_name = parts.slice(1).join(" ");
      dirty = true;
    }
  }
  return dirty;
}

/** Stable invite code for the referral page (derived from email or random once). */
export function ensureInviteCode(p: ProfileData): string {
  if (p.attribution?.invite_code) return p.attribution.invite_code;
  const seed = (p.personal?.email || p.personal?.first_name || "user")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "")
    .slice(0, 8);
  const code = `AFM-${(seed || "USER").toUpperCase()}${Math.abs(
    Array.from(seed).reduce((a, c) => a + c.charCodeAt(0), 0) % 900 + 100,
  )}`;
  p.attribution = { ...(p.attribution || {}), invite_code: code };
  return code;
}

export function targetLabel(): string {
  try {
    const p = loadProfile().preferences;
    const titles = (p.target_titles || []).slice(0, 2).join(" / ") || "roles";
    const focus =
      p.search_focus === "internships" ? "internships" : p.search_focus === "both" ? "jobs + internships" : "jobs";
    return `${p.seniority_level || "mid"} · ${titles} · ${focus}`;
  } catch {
    return "your target roles";
  }
}

export function wantsJobs(focus?: string): boolean {
  const f = (focus || "jobs").toLowerCase();
  return f === "jobs" || f === "both" || f === "fulltime" || f === "full-time" || f === "";
}

export function wantsInternships(focus?: string): boolean {
  const f = (focus || "jobs").toLowerCase();
  return f === "internships" || f === "internship" || f === "both" || f === "intern";
}
