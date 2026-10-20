"use client";

import { useState, useTransition } from "react";
import {
  DownloadIcon,
  EyeIcon,
  MinusIcon,
  PencilIcon,
  PlusIcon,
  PrinterIcon,
  RotateCcwIcon,
  Trash2Icon,
} from "lucide-react";
import { ElegantResumePreview } from "@/components/elegant-resume-preview";
import { Button } from "@/components/ui/button";
import { saveMasterResume } from "@/app/actions/resume";
import {
  emptyCustomSection,
  emptyEducation,
  emptyExperience,
  emptyProject,
  emptySkillCategory,
  type ResumeCustomSection,
  type ResumeEditorDoc,
  type ResumeEducation,
  type ResumeExperience,
  type ResumeProject,
  type ResumeSkillCategory,
} from "@/lib/resume-doc";
import { downloadBlob, resumeDocToHtml, resumeFileStem } from "@/lib/resume-export";
import { cn } from "@/lib/utils";

const ZOOM_MIN = 50;
const ZOOM_MAX = 150;
const ZOOM_STEP = 10;

export function ResumeEditor({ initial }: { initial: ResumeEditorDoc }) {
  const [doc, setDoc] = useState(initial);
  const [mode, setMode] = useState<"split" | "edit" | "preview">("split");
  const [zoom, setZoom] = useState(100);
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);

  function downloadHtml() {
    downloadBlob(`${resumeFileStem(doc)}-resume.html`, resumeDocToHtml(doc), "text/html;charset=utf-8");
  }

  function downloadTxt() {
    const lines = [
      `${doc.first_name} ${doc.last_name}`.trim(),
      [doc.email, doc.phone, doc.website, doc.github].filter(Boolean).join(" | "),
      "",
      ...doc.education.flatMap((e) => [`${e.school} — ${e.location}`, `${e.degree}; ${e.details} — ${e.dates}`, ""]),
      "SKILLS",
      ...doc.skill_categories.map((c) => `${c.label}: ${c.items}`),
      "",
      "EXPERIENCE",
      ...doc.experience.flatMap((r) => [
        `${r.company} — ${r.location}`,
        `${r.title} (${[r.start, r.end].filter(Boolean).join(" – ")})`,
        ...r.bullets.filter(Boolean).map((b) => `  • ${b}`),
        "",
      ]),
      "PROJECTS",
      ...doc.projects.flatMap((p) => [
        `${p.name}${p.tagline ? ` – ${p.tagline}` : ""} — ${p.links}`,
        ...p.bullets.filter(Boolean).map((b) => `  • ${b}`),
        "",
      ]),
      "HONORS",
      ...doc.honors.filter(Boolean).map((h) => `• ${h}`),
      ...doc.custom_sections.flatMap((s) => ["", s.title.toUpperCase(), ...s.bullets.map((b) => `• ${b}`)]),
    ];
    downloadBlob(`${resumeFileStem(doc)}-resume.txt`, lines.join("\n"), "text/plain;charset=utf-8");
  }

  /** Print / Save as PDF without browser URL/date headers when possible. */
  function printPdf() {
    const html = resumeDocToHtml(doc);
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const w = window.open(url, "_blank");
    if (!w) {
      setMsg("Allow pop-ups, then use Print → Save as PDF. Turn off “Headers and footers” in the print dialog.");
      URL.revokeObjectURL(url);
      return;
    }
    // Delay print until stylesheet paints; revoke after
    const done = () => {
      try {
        w.document.title = "\u200b";
        w.focus();
        w.print();
      } finally {
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      }
    };
    if (w.document.readyState === "complete") setTimeout(done, 250);
    else w.onload = () => setTimeout(done, 250);
    setMsg("In the print dialog: destination “Save as PDF”, and disable Headers & footers.");
  }

  const set = <K extends keyof ResumeEditorDoc>(key: K, value: ResumeEditorDoc[K]) =>
    setDoc((d) => ({ ...d, [key]: value }));

  const setExp = (i: number, patch: Partial<ResumeExperience>) =>
    setDoc((d) => ({ ...d, experience: d.experience.map((r, idx) => (idx === i ? { ...r, ...patch } : r)) }));
  const setEdu = (i: number, patch: Partial<ResumeEducation>) =>
    setDoc((d) => ({ ...d, education: d.education.map((r, idx) => (idx === i ? { ...r, ...patch } : r)) }));
  const setSkill = (i: number, patch: Partial<ResumeSkillCategory>) =>
    setDoc((d) => ({
      ...d,
      skill_categories: d.skill_categories.map((r, idx) => (idx === i ? { ...r, ...patch } : r)),
    }));
  const setProj = (i: number, patch: Partial<ResumeProject>) =>
    setDoc((d) => ({ ...d, projects: d.projects.map((r, idx) => (idx === i ? { ...r, ...patch } : r)) }));
  const setCustom = (i: number, patch: Partial<ResumeCustomSection>) =>
    setDoc((d) => ({
      ...d,
      custom_sections: d.custom_sections.map((r, idx) => (idx === i ? { ...r, ...patch } : r)),
    }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">Resume editor</h3>
          <p className="text-sm text-muted-foreground">
            Academic single-column layout (education, skills, experience, projects, honors). Add your own sections below.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg border p-0.5">
            {(
              [
                ["edit", PencilIcon, "Edit"],
                ["split", EyeIcon, "Split"],
                ["preview", EyeIcon, "Preview"],
              ] as const
            ).map(([id, Icon, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setMode(id)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium",
                  mode === id ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon className="size-3.5" />
                {label}
              </button>
            ))}
          </div>
          <Button
            type="button"
            disabled={pending}
            onClick={() =>
              start(async () => {
                setMsg(null);
                const r = await saveMasterResume(doc);
                setMsg(r.message);
              })
            }
          >
            {pending ? "Saving…" : "Save master resume"}
          </Button>
        </div>
      </div>
      {msg && <p className="text-sm text-muted-foreground">{msg}</p>}

      <div
        className={cn(
          "grid gap-4",
          mode === "split" && "lg:grid-cols-2",
          mode === "preview" && "grid-cols-1",
          mode === "edit" && "grid-cols-1",
        )}
      >
        {mode !== "preview" && (
          <div className="max-h-[70vh] space-y-5 overflow-y-auto rounded-xl border bg-card/30 p-4">
            <fieldset className="grid gap-3 sm:grid-cols-2">
              <legend className="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">Header</legend>
              <Field label="First name" value={doc.first_name} onChange={(x) => set("first_name", x)} />
              <Field label="Last name" value={doc.last_name} onChange={(x) => set("last_name", x)} />
              <Field label="Email" value={doc.email} onChange={(x) => set("email", x)} />
              <Field label="Phone" value={doc.phone} onChange={(x) => set("phone", x)} />
              <Field label="Portfolio / website URL" value={doc.website} onChange={(x) => set("website", x)} />
              <Field label="Portfolio link label" value={doc.portfolio_label} onChange={(x) => set("portfolio_label", x)} placeholder="Portfolio" />
              <Field label="GitHub URL" value={doc.github} onChange={(x) => set("github", x)} />
              <Field label="LinkedIn URL" value={doc.linkedin} onChange={(x) => set("linkedin", x)} />
              <Field label="Location (optional)" value={doc.location} onChange={(x) => set("location", x)} />
            </fieldset>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={doc.show_summary}
                onChange={(e) => set("show_summary", e.target.checked)}
              />
              Show professional summary section
            </label>
            {doc.show_summary && (
              <label className="block space-y-1.5 text-sm">
                <span className="font-medium">Summary</span>
                <textarea
                  value={doc.summary}
                  onChange={(e) => set("summary", e.target.value)}
                  rows={3}
                  className="w-full rounded-md border bg-background px-3 py-2"
                />
              </label>
            )}

            <Block
              title="Education"
              onAdd={() => set("education", [...doc.education, emptyEducation()])}
            >
              {doc.education.map((e, i) => (
                <Card key={i} onRemove={() => set("education", doc.education.filter((_, j) => j !== i))}>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Field label="School" value={e.school} onChange={(x) => setEdu(i, { school: x })} />
                    <Field label="Location" value={e.location} onChange={(x) => setEdu(i, { location: x })} />
                    <Field label="Degree / program" value={e.degree} onChange={(x) => setEdu(i, { degree: x })} />
                    <Field label="Dates" value={e.dates} onChange={(x) => setEdu(i, { dates: x })} placeholder="August 2023 – August 2027" />
                    <Field label="Details (GPA, etc.)" value={e.details} onChange={(x) => setEdu(i, { details: x })} className="sm:col-span-2" />
                  </div>
                </Card>
              ))}
            </Block>

            <Block
              title="Skills (categories)"
              onAdd={() => set("skill_categories", [...doc.skill_categories, emptySkillCategory()])}
            >
              {doc.skill_categories.map((c, i) => (
                <Card key={i} onRemove={() => set("skill_categories", doc.skill_categories.filter((_, j) => j !== i))}>
                  <div className="grid gap-2 sm:grid-cols-3">
                    <Field label="Category" value={c.label} onChange={(x) => setSkill(i, { label: x })} placeholder="Languages" />
                    <div className="sm:col-span-2">
                      <Field label="Items (comma-separated)" value={c.items} onChange={(x) => setSkill(i, { items: x })} />
                    </div>
                  </div>
                </Card>
              ))}
            </Block>

            <Block title="Experience" onAdd={() => set("experience", [...doc.experience, emptyExperience()])}>
              {doc.experience.map((r, i) => (
                <Card key={i} onRemove={() => set("experience", doc.experience.filter((_, j) => j !== i))}>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Field label="Company" value={r.company} onChange={(x) => setExp(i, { company: x })} />
                    <Field label="Location" value={r.location} onChange={(x) => setExp(i, { location: x })} placeholder="Remote" />
                    <Field label="Title" value={r.title} onChange={(x) => setExp(i, { title: x })} />
                    <div className="grid grid-cols-2 gap-2">
                      <Field label="Start" value={r.start} onChange={(x) => setExp(i, { start: x })} />
                      <Field label="End" value={r.end} onChange={(x) => setExp(i, { end: x })} />
                    </div>
                  </div>
                  <Bullets
                    hint="Tip: start with Lead: description for bold lead-ins"
                    value={r.bullets}
                    onChange={(bullets) => setExp(i, { bullets })}
                  />
                </Card>
              ))}
            </Block>

            <Block title="Projects" onAdd={() => set("projects", [...doc.projects, emptyProject()])}>
              {doc.projects.length === 0 && (
                <p className="text-xs text-muted-foreground">Optional — add projects like PrizeVault, etc.</p>
              )}
              {doc.projects.map((p, i) => (
                <Card key={i} onRemove={() => set("projects", doc.projects.filter((_, j) => j !== i))}>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Field label="Name" value={p.name} onChange={(x) => setProj(i, { name: x })} />
                    <Field label="Links (e.g. Official Link | GitHub)" value={p.links} onChange={(x) => setProj(i, { links: x })} />
                    <div className="sm:col-span-2">
                      <Field label="Tagline" value={p.tagline} onChange={(x) => setProj(i, { tagline: x })} />
                    </div>
                  </div>
                  <Bullets value={p.bullets} onChange={(bullets) => setProj(i, { bullets })} />
                </Card>
              ))}
            </Block>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-medium">Honors and awards</h4>
                <Button type="button" size="sm" variant="outline" onClick={() => set("honors", [...doc.honors, ""])}>
                  <PlusIcon className="size-3.5" /> Add
                </Button>
              </div>
              {doc.honors.map((h, i) => (
                <div key={i} className="flex gap-2">
                  <input
                    value={h}
                    onChange={(e) =>
                      set(
                        "honors",
                        doc.honors.map((x, j) => (j === i ? e.target.value : x)),
                      )
                    }
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                    placeholder="Winner at PixelGenesis Hackathon, 2025"
                  />
                  <button type="button" className="text-muted-foreground hover:text-destructive" onClick={() => set("honors", doc.honors.filter((_, j) => j !== i))}>
                    <Trash2Icon className="size-4" />
                  </button>
                </div>
              ))}
            </div>

            <Block
              title="Custom sections"
              onAdd={() => set("custom_sections", [...doc.custom_sections, emptyCustomSection()])}
            >
              <p className="text-xs text-muted-foreground">Add any section you want — Certifications, Publications, Leadership, etc.</p>
              {doc.custom_sections.map((s, i) => (
                <Card key={i} onRemove={() => set("custom_sections", doc.custom_sections.filter((_, j) => j !== i))}>
                  <Field label="Section title" value={s.title} onChange={(x) => setCustom(i, { title: x })} placeholder="Certifications" />
                  <Bullets value={s.bullets} onChange={(bullets) => setCustom(i, { bullets })} />
                </Card>
              ))}
            </Block>
          </div>
        )}

        {mode !== "edit" && (
          <div className="flex max-h-[70vh] flex-col overflow-hidden rounded-xl border bg-zinc-100/80 dark:bg-zinc-900/40">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-background/80 px-3 py-2">
              <div className="flex items-center gap-1">
                <Button type="button" size="sm" variant="outline" disabled={zoom <= ZOOM_MIN} aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(ZOOM_MIN, z - ZOOM_STEP))}>
                  <MinusIcon className="size-3.5" />
                </Button>
                <span className="min-w-12 text-center text-xs tabular-nums text-muted-foreground">{zoom}%</span>
                <Button type="button" size="sm" variant="outline" disabled={zoom >= ZOOM_MAX} aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(ZOOM_MAX, z + ZOOM_STEP))}>
                  <PlusIcon className="size-3.5" />
                </Button>
                <Button type="button" size="sm" variant="ghost" aria-label="Reset zoom" onClick={() => setZoom(100)}>
                  <RotateCcwIcon className="size-3.5" />
                </Button>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Button type="button" size="sm" variant="outline" onClick={downloadHtml}>
                  <DownloadIcon className="size-3.5" /> HTML
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={downloadTxt}>
                  <DownloadIcon className="size-3.5" /> TXT
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={printPdf}>
                  <PrinterIcon className="size-3.5" /> PDF / Print
                </Button>
              </div>
            </div>
            <div className="flex-1 overflow-auto p-3">
              <div className="flex justify-center">
                <div className="origin-top transition-transform duration-150" style={{ transform: `scale(${zoom / 100})` }}>
                  <ElegantResumePreview doc={doc} />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Block({ title, onAdd, children }: { title: string; onAdd: () => void; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium">{title}</h4>
        <Button type="button" size="sm" variant="outline" onClick={onAdd}>
          <PlusIcon className="size-3.5" /> Add
        </Button>
      </div>
      {children}
    </div>
  );
}

function Card({ children, onRemove }: { children: React.ReactNode; onRemove: () => void }) {
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex justify-end">
        <button type="button" className="text-muted-foreground hover:text-destructive" aria-label="Remove" onClick={onRemove}>
          <Trash2Icon className="size-4" />
        </button>
      </div>
      {children}
    </div>
  );
}

function Bullets({
  value,
  onChange,
  hint,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  hint?: string;
}) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="font-medium">Bullets (one per line)</span>
      {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
      <textarea
        value={value.join("\n")}
        onChange={(e) => onChange(e.target.value.split("\n"))}
        rows={4}
        className="w-full rounded-md border bg-background px-3 py-2 font-mono text-xs"
      />
    </label>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  className,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <label className={cn("block space-y-1 text-sm", className)}>
      <span className="text-muted-foreground">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border bg-background px-3 py-2"
      />
    </label>
  );
}
