"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { loadProfile, saveProfile, type ProfileData } from "@/lib/profile";
import { toggleSaved } from "@/lib/saved";

function csv(s: string): string[] {
  return s.split(",").map((x) => x.trim()).filter(Boolean);
}

export async function saveOnboarding(formData: FormData) {
  const p = loadProfile();
  const get = (k: string) => String(formData.get(k) ?? "").trim();

  p.personal = {
    ...p.personal,
    first_name: get("first_name") || p.personal.first_name || "",
    last_name: get("last_name") || p.personal.last_name || "",
    email: get("email") || p.personal.email || "",
    phone: get("phone") || p.personal.phone || "",
    location: get("location") || p.personal.location || "",
    linkedin: get("linkedin"),
    github: get("github"),
    website: get("website"),
    portfolio: get("portfolio"),
    twitter: get("twitter"),
  };

  const years = parseFloat(get("years_experience"));
  p.preferences = {
    ...p.preferences,
    seniority_level: get("seniority_level") || "mid",
    current_title: get("current_title"),
    years_experience: Number.isFinite(years) ? years : null,
    target_titles: csv(get("target_titles")),
    locations: csv(get("locations")),
    reject_locations: csv(get("reject_locations")),
    remote_only: formData.get("remote_only") === "on",
    min_match_score: parseInt(get("min_match_score") || "70", 10) || 70,
    exclude_keywords: csv(get("exclude_keywords")),
  };

  p.summary = get("summary") || p.summary || "";
  if (get("skills")) p.skills = csv(get("skills"));

  p.screening = {
    ...(p.screening || {}),
    work_authorization: get("work_authorization") || p.screening?.work_authorization || "",
    requires_sponsorship: get("requires_sponsorship") || p.screening?.requires_sponsorship || "No",
    notice_period: get("notice_period") || p.screening?.notice_period || "",
    years_of_experience: get("years_experience") || p.screening?.years_of_experience || "",
  };

  p.compensation = {
    ...(p.compensation || {}),
    salary_currency: get("salary_currency") || p.compensation?.salary_currency || "INR",
    salary_expectation: get("salary_expectation") || p.compensation?.salary_expectation || "",
    salary_range_min: get("salary_range_min") || p.compensation?.salary_range_min || "",
    salary_range_max: get("salary_range_max") || p.compensation?.salary_range_max || "",
  };

  p.onboarding_complete = true;
  saveProfile(p);
  revalidatePath("/", "layout");
  redirect("/home");
}

export async function savePreferences(formData: FormData) {
  const p = loadProfile();
  const get = (k: string) => String(formData.get(k) ?? "").trim();
  const years = parseFloat(get("years_experience"));
  p.preferences = {
    ...p.preferences,
    seniority_level: get("seniority_level") || p.preferences.seniority_level || "mid",
    current_title: get("current_title") || p.preferences.current_title || "",
    years_experience: Number.isFinite(years) ? years : p.preferences.years_experience,
    target_titles: csv(get("target_titles")),
    locations: csv(get("locations")),
    reject_locations: csv(get("reject_locations")),
    remote_only: formData.get("remote_only") === "on",
    min_match_score: parseInt(get("min_match_score") || "70", 10) || 70,
    exclude_keywords: csv(get("exclude_keywords")),
  };
  saveProfile(p);
  revalidatePath("/", "layout");
  redirect("/preferences?saved=1");
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
