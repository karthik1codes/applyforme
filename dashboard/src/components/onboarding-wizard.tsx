"use client";

import { useState, useTransition } from "react";
import { ResumeUpload } from "@/components/landing/resume-upload";
import { saveOnboarding } from "@/app/actions/profile";
import type { ProfileData } from "@/lib/profile";

const LEVELS = [
  { id: "intern", label: "Intern / trainee" },
  { id: "junior", label: "Junior / entry-level" },
  { id: "mid", label: "Mid-level" },
  { id: "senior", label: "Senior" },
  { id: "lead", label: "Lead / staff / principal" },
  { id: "executive", label: "Director / executive" },
];

type State = Record<string, string>;

export function OnboardingWizard({ initial, hasResume }: { initial: ProfileData; hasResume: boolean }) {
  const [step, setStep] = useState(hasResume ? 1 : 0);
  const [pending, start] = useTransition();
  const p = initial.personal || {};
  const pref = initial.preferences || {};
  const [v, setV] = useState<State>({
    first_name: p.first_name || "",
    last_name: p.last_name || "",
    email: p.email || "",
    phone: p.phone || "",
    location: p.location || "",
    current_title: pref.current_title || "",
    seniority_level: pref.seniority_level || "junior",
    years_experience: String(pref.years_experience ?? initial.screening?.years_of_experience ?? ""),
    target_titles: (pref.target_titles || []).join(", "),
    summary: initial.summary || "",
    skills: (initial.skills || []).join(", "),
    linkedin: p.linkedin || "",
    github: p.github || "",
    portfolio: p.portfolio || p.website || "",
    website: p.website || "",
    twitter: p.twitter || "",
    locations: (pref.locations || ["Remote"]).join(", "),
    reject_locations: (pref.reject_locations || ["US", "USA", "United States", "Canada", "UK"]).join(", "),
    remote_only: pref.remote_only ? "on" : "",
    min_match_score: String(pref.min_match_score ?? 70),
    exclude_keywords: (pref.exclude_keywords || []).join(", "),
    work_authorization: initial.screening?.work_authorization || "",
    requires_sponsorship: initial.screening?.requires_sponsorship || "No",
    notice_period: initial.screening?.notice_period || "",
    salary_currency: initial.compensation?.salary_currency || "INR",
    salary_expectation: initial.compensation?.salary_expectation || "",
    salary_range_min: initial.compensation?.salary_range_min || "",
    salary_range_max: initial.compensation?.salary_range_max || "",
  });

  const set = (name: string, value: string) => setV((s) => ({ ...s, [name]: value }));

  function finish() {
    const fd = new FormData();
    Object.entries(v).forEach(([k, val]) => fd.set(k, val));
    start(async () => { await saveOnboarding(fd); });
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-10 lg:px-10">
      <p className="text-sm text-muted-foreground">Step {step + 1} of 4</p>
      <div className="mt-2 mb-8 flex gap-1">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={`h-1 flex-1 rounded-full ${i <= step ? "bg-foreground" : "bg-muted"}`} />
        ))}
      </div>

      {step === 0 && (
        <section className="space-y-4">
          <h1 className="text-3xl font-semibold tracking-tight">Upload your resume</h1>
          <p className="text-muted-foreground">
            Agents tailor a version per job from this file. PDF works best — nothing is invented that isn&apos;t on it.
          </p>
          <ResumeUpload redirectTo="/onboarding?resume=1" />
          <button type="button" className="text-sm text-muted-foreground underline" onClick={() => setStep(1)}>
            Skip for now
          </button>
        </section>
      )}

      {step === 1 && (
        <section className="space-y-4">
          <h1 className="text-3xl font-semibold tracking-tight">Your background</h1>
          <p className="text-muted-foreground">
            This tells agents what level you&apos;re targeting. Junior seekers won&apos;t be shown Senior / Staff / Lead roles.
          </p>
          <Field label="First name" value={v.first_name} onChange={(x) => set("first_name", x)} required />
          <Field label="Last name" value={v.last_name} onChange={(x) => set("last_name", x)} required />
          <Field label="Email" value={v.email} onChange={(x) => set("email", x)} type="email" required />
          <Field label="Phone" value={v.phone} onChange={(x) => set("phone", x)} />
          <Field label="Location" value={v.location} onChange={(x) => set("location", x)} placeholder="Bengaluru, India" />
          <Field label="Current job title" value={v.current_title} onChange={(x) => set("current_title", x)} placeholder="Junior Developer" />
          <label className="block space-y-1.5 text-sm">
            <span className="font-medium">Target seniority</span>
            <select
              value={v.seniority_level}
              onChange={(e) => set("seniority_level", e.target.value)}
              className="w-full rounded-md border bg-background px-3 py-2"
            >
              {LEVELS.map((l) => (
                <option key={l.id} value={l.id}>{l.label}</option>
              ))}
            </select>
          </label>
          <Field label="Years of experience" value={v.years_experience} onChange={(x) => set("years_experience", x)} placeholder="2" />
          <Field
            label="Target job titles (comma-separated)"
            value={v.target_titles}
            onChange={(x) => set("target_titles", x)}
            placeholder="Junior Developer, Software Engineer"
            required
          />
          <label className="block space-y-1.5 text-sm">
            <span className="font-medium">Short summary</span>
            <textarea value={v.summary} onChange={(e) => set("summary", e.target.value)} rows={3} className="w-full rounded-md border bg-background px-3 py-2" />
          </label>
          <Field label="Skills (comma-separated)" value={v.skills} onChange={(x) => set("skills", x)} placeholder="Python, React, SQL" />
          <Nav onBack={() => setStep(0)} onNext={() => setStep(2)} />
        </section>
      )}

      {step === 2 && (
        <section className="space-y-4">
          <h1 className="text-3xl font-semibold tracking-tight">Social &amp; portfolio links</h1>
          <p className="text-muted-foreground">
            Agents use these on applications and when grounding &quot;tell us about yourself&quot; answers.
          </p>
          <Field label="LinkedIn URL" value={v.linkedin} onChange={(x) => set("linkedin", x)} placeholder="https://linkedin.com/in/…" />
          <Field label="GitHub URL" value={v.github} onChange={(x) => set("github", x)} placeholder="https://github.com/…" />
          <Field label="Portfolio / personal site" value={v.portfolio} onChange={(x) => set("portfolio", x)} />
          <Field label="Website" value={v.website} onChange={(x) => set("website", x)} />
          <Field label="X / Twitter" value={v.twitter} onChange={(x) => set("twitter", x)} />
          <Nav onBack={() => setStep(1)} onNext={() => setStep(3)} />
        </section>
      )}

      {step === 3 && (
        <section className="space-y-4">
          <h1 className="text-3xl font-semibold tracking-tight">Where &amp; what to chase</h1>
          <p className="text-muted-foreground">
            Discovery and the Jobs dashboard only keep roles that match these filters.
          </p>
          <Field label="Accepted locations (comma-separated)" value={v.locations} onChange={(x) => set("locations", x)} />
          <Field label="Reject if location mentions" value={v.reject_locations} onChange={(x) => set("reject_locations", x)} />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={v.remote_only === "on"} onChange={(e) => set("remote_only", e.target.checked ? "on" : "")} />
            Remote-only roles
          </label>
          <Field label="Minimum match score (0–100)" value={v.min_match_score} onChange={(x) => set("min_match_score", x)} />
          <Field label="Extra title keywords to skip" value={v.exclude_keywords} onChange={(x) => set("exclude_keywords", x)} placeholder="contract, freelance" />
          <Field label="Work authorization answer" value={v.work_authorization} onChange={(x) => set("work_authorization", x)} />
          <Field label="Need sponsorship?" value={v.requires_sponsorship} onChange={(x) => set("requires_sponsorship", x)} />
          <Field label="Notice period" value={v.notice_period} onChange={(x) => set("notice_period", x)} />
          <Field label="Salary currency" value={v.salary_currency} onChange={(x) => set("salary_currency", x)} />
          <Field label="Expected annual salary" value={v.salary_expectation} onChange={(x) => set("salary_expectation", x)} />
          <Field label="Salary floor" value={v.salary_range_min} onChange={(x) => set("salary_range_min", x)} />
          <Field label="Salary ceiling" value={v.salary_range_max} onChange={(x) => set("salary_range_max", x)} />
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={() => setStep(2)} className="rounded-md border px-4 py-2 text-sm">Back</button>
            <button type="button" disabled={pending} onClick={finish} className="rounded-md bg-foreground px-4 py-2 text-sm text-background disabled:opacity-60">
              {pending ? "Saving…" : "Finish & open dashboard"}
            </button>
          </div>
          <p className="text-xs text-muted-foreground">
            Next: run <code className="rounded bg-muted px-1">python -m applyforme run</code> so agents fetch jobs for your target level.
          </p>
        </section>
      )}
    </div>
  );
}

function Field({
  label, value, onChange, placeholder, type = "text", required,
}: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string; required?: boolean;
}) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="font-medium">{label}</span>
      <input
        type={type}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border bg-background px-3 py-2"
      />
    </label>
  );
}

function Nav({ onBack, onNext }: { onBack: () => void; onNext: () => void }) {
  return (
    <div className="flex gap-3 pt-2">
      <button type="button" onClick={onBack} className="rounded-md border px-4 py-2 text-sm">Back</button>
      <button type="button" onClick={onNext} className="rounded-md bg-foreground px-4 py-2 text-sm text-background">Continue</button>
    </div>
  );
}
