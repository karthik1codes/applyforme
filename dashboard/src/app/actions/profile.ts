"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { sessionUserId } from "@/lib/onboarding-gate";
import { startPipeline } from "@/lib/pipeline-runner";
import {
  ensureInviteCode,
  loadProfile,
  saveProfile,
  syncSearches,
  wantsInternships,
  wantsJobs,
  type ProfileData,
} from "@/lib/profile";
import { toggleSaved } from "@/lib/saved";
import { markUserOnboardingComplete, upsertUser } from "@/lib/users";

function csv(s: string): string[] {
  return s.split(",").map((x) => x.trim()).filter(Boolean);
}

function normalizeFocus(raw: string, seniority: string): "jobs" | "internships" | "both" {
  const f = raw.toLowerCase();
  if (f === "internships" || f === "internship" || f === "intern") return "internships";
  if (f === "both") return "both";
  if (seniority === "intern" && !raw) return "internships";
  return "jobs";
}

function kickOffSearch(focus: string) {
  if (wantsJobs(focus)) void startPipeline("run", 40);
  if (wantsInternships(focus)) void startPipeline("internships", 40);
}

export async function saveOnboarding(formData: FormData) {
  const p = loadProfile();
  const get = (k: string) => String(formData.get(k) ?? "").trim();

  const portfolio = get("portfolio") || get("website");
  p.personal = {
    ...p.personal,
    first_name: get("first_name") || p.personal.first_name || "",
    last_name: get("last_name") || p.personal.last_name || "",
    email: get("email") || p.personal.email || "",
    phone: get("phone") || p.personal.phone || "",
    location: get("location") || p.personal.location || "",
    linkedin: get("linkedin") || p.personal.linkedin || "",
    github: get("github") || p.personal.github || "",
    website: get("website") || portfolio || p.personal.website || "",
    portfolio: portfolio || p.personal.portfolio || "",
    twitter: get("twitter") || p.personal.twitter || "",
  };

  const years = parseFloat(get("years_experience"));
  const seniority = get("seniority_level") || "mid";
  const searchFocus = normalizeFocus(get("search_focus"), seniority);

  // Align exclude keywords with focus so internships aren't filtered out by accident
  let exclude = csv(get("exclude_keywords"));
  if (searchFocus === "internships" || searchFocus === "both") {
    exclude = exclude.filter((k) => !/^intern(ship)?s?$/i.test(k));
  } else if (!exclude.some((k) => /^intern/i.test(k)) && seniority !== "intern") {
    exclude = [...exclude, "intern"];
  }

  p.preferences = {
    ...p.preferences,
    seniority_level: searchFocus === "internships" && seniority === "mid" ? "intern" : seniority,
    search_focus: searchFocus,
    current_title: get("current_title"),
    years_experience: Number.isFinite(years) ? years : null,
    target_titles: csv(get("target_titles")),
    locations: csv(get("locations")),
    reject_locations: csv(get("reject_locations")),
    remote_only: formData.get("remote_only") === "on",
    min_match_score: parseInt(get("min_match_score") || "70", 10) || 70,
    exclude_keywords: exclude,
  };

  p.summary = get("summary") || p.summary || "";
  if (get("skills")) p.skills = csv(get("skills"));

  p.screening = {
    ...(p.screening || {}),
    work_authorization: get("work_authorization") || p.screening?.work_authorization || "",
    requires_sponsorship: get("requires_sponsorship") || p.screening?.requires_sponsorship || "No",
    notice_period: get("notice_period") || p.screening?.notice_period || "",
    years_of_experience: get("years_experience") || p.screening?.years_of_experience || "",
    how_did_you_hear: get("how_heard") || p.screening?.how_did_you_hear || "",
  };

  p.compensation = {
    ...(p.compensation || {}),
    salary_currency: get("salary_currency") || p.compensation?.salary_currency || "INR",
    salary_expectation: get("salary_expectation") || p.compensation?.salary_expectation || "",
    salary_range_min: get("salary_range_min") || p.compensation?.salary_range_min || "",
    salary_range_max: get("salary_range_max") || p.compensation?.salary_range_max || "",
  };

  p.attribution = {
    ...(p.attribution || {}),
    how_heard: get("how_heard") || p.attribution?.how_heard || "",
    role: get("role") || p.attribution?.role || "",
    referral_code: get("referral_code") || p.attribution?.referral_code || "",
  };
  ensureInviteCode(p);

  p.onboarding_complete = true;
  syncSearches(p);
  saveProfile(p);

  // Mark this Google account complete so every Gmail gets its own onboarding pass.
  const session = await auth();
  if (session?.user?.email) {
    const userId = sessionUserId(session);
    upsertUser({ id: userId, email: session.user.email, name: session.user.name, image: session.user.image });
    markUserOnboardingComplete(userId, true);
  }

  kickOffSearch(searchFocus);
  revalidatePath("/", "layout");
  redirect("/referral?welcome=1");
}

export async function savePreferences(formData: FormData) {
  const p = loadProfile();
  const get = (k: string) => String(formData.get(k) ?? "").trim();
  const years = parseFloat(get("years_experience"));
  const seniority = get("seniority_level") || p.preferences.seniority_level || "mid";
  const searchFocus = normalizeFocus(get("search_focus") || p.preferences.search_focus || "jobs", seniority);

  let exclude = csv(get("exclude_keywords"));
  if (searchFocus === "internships" || searchFocus === "both") {
    exclude = exclude.filter((k) => !/^intern(ship)?s?$/i.test(k));
  }

  p.preferences = {
    ...p.preferences,
    seniority_level: seniority,
    search_focus: searchFocus,
    current_title: get("current_title") || p.preferences.current_title || "",
    years_experience: Number.isFinite(years) ? years : p.preferences.years_experience,
    target_titles: csv(get("target_titles")),
    locations: csv(get("locations")),
    reject_locations: csv(get("reject_locations")),
    remote_only: formData.get("remote_only") === "on",
    min_match_score: parseInt(get("min_match_score") || "70", 10) || 70,
    exclude_keywords: exclude,
  };
  syncSearches(p);
  saveProfile(p);
  kickOffSearch(searchFocus);
  revalidatePath("/", "layout");
  redirect("/preferences?saved=1&refreshing=1");
}

export async function saveProfileBasics(formData: FormData) {
  const p = loadProfile();
  const get = (k: string) => String(formData.get(k) ?? "").trim();
  p.personal = {
    ...p.personal,
    first_name: get("first_name"),
    last_name: get("last_name"),
    email: get("email"),
    phone: get("phone"),
    location: get("location"),
    linkedin: get("linkedin"),
    github: get("github"),
    website: get("website"),
    portfolio: get("portfolio"),
    twitter: get("twitter"),
  };
  p.summary = get("summary") || p.summary || "";
  if (get("skills")) p.skills = csv(get("skills"));
  saveProfile(p);
  revalidatePath("/", "layout");
  redirect("/profile?saved=1");
}

export async function toggleSaveJob(jobId: string) {
  const on = toggleSaved(jobId);
  revalidatePath("/saved");
  revalidatePath("/jobs");
  revalidatePath("/home");
  return on;
}

export type { ProfileData };
