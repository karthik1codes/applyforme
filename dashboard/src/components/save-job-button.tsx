"use client";

import { useState, useTransition } from "react";
import { BookmarkIcon } from "lucide-react";
import { toggleSaveJob } from "@/app/actions/profile";
import { Button } from "@/components/ui/button";

export function SaveJobButton({ jobId, saved: initial }: { jobId: string; saved: boolean }) {
  const [saved, setSaved] = useState(initial);
  const [pending, start] = useTransition();
  return (
    <Button
      type="button"
      size="sm"
      variant={saved ? "default" : "outline"}
      disabled={pending}
      onClick={() => start(async () => setSaved(await toggleSaveJob(jobId)))}
    >
      <BookmarkIcon className="size-3.5" />
      {saved ? "Saved" : "Save"}
    </Button>
  );
}
