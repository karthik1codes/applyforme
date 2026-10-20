"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { addEvent, db, questionsFor } from "@/lib/db";
import { createCheckout, customerPortalUrl, getBilling, type PlanId } from "@/lib/billing";
import { startPipeline } from "@/lib/pipeline-runner";
import { newCode, setWa } from "@/lib/whatsapp";

/** Save the human's answers. Once every question of a job is answered, resume apply automatically. */
export async function submitAnswers(jobId: string, formData: FormData) {
  const upd = db().prepare("UPDATE questions SET answer=? WHERE id=? AND job_id=?");
  for (const q of questionsFor(jobId)) {
    const v = formData.get(`q_${q.id}`);
    if (typeof v === "string" && v.trim()) upd.run(v.trim(), q.id, jobId);
  }
  const open = questionsFor(jobId).filter((q) => !q.answer).length;
  if (open === 0) {
    db().prepare("UPDATE jobs SET status='ready', notes=NULL, updated_at=? WHERE id=? AND status='needs_feedback'")
      .run(new Date().toISOString(), jobId);
    addEvent(jobId, "answered", "You answered the open questions", "Agent is resuming the application.");
    void startPipeline("apply", 1, { jobId });
  }
  revalidatePath("/", "layout");
  if (open === 0) redirect(`/applications/${encodeURIComponent(jobId)}?applying=1`);
}

export async function skipJob(jobId: string) {
  db().prepare("UPDATE jobs SET status='skipped', notes='skipped by you', updated_at=? WHERE id=?").run(new Date().toISOString(), jobId);
  revalidatePath("/", "layout");
}

export async function generateWhatsAppCode() {
  newCode();
  revalidatePath("/whatsapp");
}

export async function disconnectWhatsApp() {
  setWa({ status: "disconnected" });
  revalidatePath("/whatsapp");
}

export async function startCheckout(planId: PlanId) {
  let url: string;
  try {
    url = await createCheckout(planId);
  } catch (e) {
    redirect(`/billing?error=${encodeURIComponent(e instanceof Error ? e.message : "Checkout failed")}`);
  }
  redirect(url);
}

export async function openBillingPortal() {
  const { customerId } = getBilling();
  if (!customerId) redirect("/billing?error=No%20billing%20customer%20yet");
  redirect(customerPortalUrl(customerId));
}
