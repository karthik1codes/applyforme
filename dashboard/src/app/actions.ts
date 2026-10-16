"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { addEvent, db, questionsFor } from "@/lib/db";
import { createCheckout, getBilling, stripe, appUrl, type PlanId } from "@/lib/billing";
import { newCode, setWa } from "@/lib/whatsapp";

/** Save the human's answers. Once every question of a job is answered it goes back to "ready" for `apply`. */
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
    addEvent(jobId, "answered", "You answered the open questions", "Re-run: python -m applyforme apply " + jobId);
  }
  revalidatePath("/", "layout");
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
  const s = stripe();
  const { customerId } = getBilling();
  if (!s || !customerId) redirect("/billing?error=No%20Stripe%20customer%20yet");
  const session = await s.billingPortal.sessions.create({ customer: customerId, return_url: `${appUrl()}/billing` });
  redirect(session.url);
}
