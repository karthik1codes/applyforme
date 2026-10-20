"use server";

import { revalidatePath } from "next/cache";
import { loadProfile, saveProfile, type ProfileData } from "@/lib/profile";
import { resumeDocToProfilePatch, type ResumeEditorDoc } from "@/lib/resume-doc";

export async function saveMasterResume(doc: ResumeEditorDoc): Promise<{ ok: boolean; message: string }> {
  try {
    const p = loadProfile() as ProfileData & Record<string, unknown>;
    const patch = resumeDocToProfilePatch(doc);
    p.personal = { ...p.personal, ...patch.personal };
    p.summary = patch.summary;
    p.skills = patch.skills;
    p.experience = patch.experience;
    p.education = patch.education;
    p.projects = patch.projects;
    p.honors = patch.honors;
    p.skill_categories = patch.skill_categories;
    p.custom_sections = patch.custom_sections;
    p.resume = patch.resume;
    saveProfile(p);
    revalidatePath("/resumes");
    revalidatePath("/profile");
    revalidatePath("/", "layout");
    return { ok: true, message: "Master resume saved. Agents will use this on the next tailor run." };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "Could not save resume." };
  }
}
