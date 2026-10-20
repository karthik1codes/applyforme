"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import {
  currentLinkedInUserId,
  deleteLegacyLinkedInFile,
  disconnectLinkedIn,
  refreshLinkedInConnection,
} from "@/lib/linkedin";

export async function disconnectLinkedInAction(): Promise<void> {
  const userId = await currentLinkedInUserId();
  if (!userId) redirect("/?linkedin=signin");
  disconnectLinkedIn(userId);
  revalidatePath("/settings");
  redirect("/settings?linkedin=disconnected");
}

export async function refreshLinkedInAction(): Promise<void> {
  const userId = await currentLinkedInUserId();
  if (!userId) redirect("/?linkedin=signin");
  try {
    await refreshLinkedInConnection(userId);
  } catch (e) {
    const reason = e instanceof Error ? e.message : "LinkedIn refresh failed";
    redirect(`/settings?linkedin=refresh_error&reason=${encodeURIComponent(reason.slice(0, 200))}`);
  }
  revalidatePath("/settings");
  redirect("/settings?linkedin=refreshed");
}

/** Explicit cleanup for the old plaintext password file. The file is never read. */
export async function deleteLegacyLinkedInFileAction(): Promise<void> {
  const userId = await currentLinkedInUserId();
  if (!userId) redirect("/?linkedin=signin");
  const removed = deleteLegacyLinkedInFile();
  revalidatePath("/settings");
  redirect(`/settings?linkedin=${removed ? "legacy_deleted" : "legacy_missing"}`);
}
