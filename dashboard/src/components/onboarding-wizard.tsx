"use client";

import { useState, useTransition } from "react";
import { ResumeUpload } from "@/components/landing/resume-upload";
import { saveOnboarding } from "@/app/actions/profile";
import type { ProfileData } from "@/lib/profile";

const HEAR_ABOUT = [
  { id: "friend", label: "Friend or classmate" },
  { id: "linkedin", label: "LinkedIn" },
  { id: "twitter", label: "X / Twitter" },
  { id: "youtube", label: "YouTube" },
  { id: "google", label: "Google / search" },
  { id: "college", label: "College / career fair" },
  { id: "referral", label: "Referral link" },
  { id: "other", label: "Other" },
];

const ROLES = [
  { id: "student", label: "Student / recent grad" },
  { id: "intern", label: "Intern / trainee" },
  { id: "professional", label: "Working professional" },
  { id: "career_switcher", label: "Career switcher" },
  { id: "freelancer", label: "Freelancer / contractor" },
  { id: "other", label: "Other" },
];

const LEVELS = [
  { id: "intern", label: "Intern / trainee" },
  { id: "junior", label: "Junior / entry-level" },
  { id: "mid", label: "Mid-level" },
  { id: "senior", label: "Senior" },
  { id: "lead", label: "Lead / staff / principal" },
  { id: "executive", label: "Director / executive" },
];

const SEARCH_FOCUS = [
  {
    id: "jobs",
    title: "Full-time jobs",
    blurb: "Software / backend / data roles — agents skip pure internships.",
  },
  {
    id: "internships",
    title: "Internships only",
    blurb: "Intern, trainee & co-op from major boards.",
  },
  {
    id: "both",
    title: "Jobs + internships",
    blurb: "Run both pipelines so nothing matching your titles is missed.",
  },
] as const;

const STEPS = ["Hear about us", "Your role", "Referral", "Resume", "Preferences"] as const;

type State = Record<string, string>;

export function OnboardingWizard({
  initial,
  hasResume,
  startStep = 0,
}: {
  initial: ProfileData;
  hasResume: boolean;
  startStep?: number;
}) {
  const [step, setStep] = useState(startStep);
  const [pending, start] = useTransition();
  const p = initial.personal || {};
  const pref = initial.preferences || {};
  const attr = initial.attribution || {};
  const [v, setV] = useState<State>({
    how_heard: attr.how_heard || initial.screening?.how_did_you_hear || "",
    role: attr.role || "",
    referral_code: attr.referral_code || "",
    first_name: p.first_name || "",
    last_name: p.last_name || "",
    email: p.email || "",
    phone: p.phone || "",
    location: p.location || "",
    current_title: pref.current_title || "",
    seniority_level: pref.seniority_level || "junior",
    search_focus: pref.search_focus || (pref.seniority_level === "intern" ? "internships" : "jobs"),
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
    // Keep website in sync with portfolio for profile.yaml / ATS forms.
    if (!fd.get("website") && v.portfolio) fd.set("website", v.portfolio);
    start(async () => {
      await saveOnboarding(fd);
    });
  }

  const canHear = !!v.how_heard;
  const canRole = !!v.role && !!v.seniority_level && !!v.target_titles.trim() && !!v.search_focus;

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-10 lg:px-10">
      <p className="text-sm text-muted-foreground">
        Step {step + 1} of {STEPS.length} · {STEPS[step]}
      </p>
      <div className="mt-2 mb-8 flex gap-1">
        {STEPS.map((_, i) => (
          <div key={i} className={`h-1 flex-1 rounded-full ${i <= step ? "bg-foreground" : "bg-muted"}`} />
        ))}
      </div>

      {step === 0 && (
        <section className="space-y-4">
          <h1 className="text-3xl font-semibold tracking-tight">How did you hear about applyforme?</h1>
          <p className="text-muted-foreground">Helps us know what&apos;s working — pick one.</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {HEAR_ABOUT.map((opt) => {
              const on = v.how_heard === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => set("how_heard", opt.id)}
                  className={`rounded-xl border px-4 py-3 text-left text-sm font-medium transition ${
                    on ? "border-foreground bg-foreground text-background" : "hover:bg-muted/50"
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              disabled={!canHear}
              onClick={() => setStep(1)}
              className="rounded-md bg-foreground px-4 py-2 text-sm text-background disabled:opacity-40"
            >
              Continue
            </button>
          </div>
        </section>
      )}

      {step === 1 && (
        <section className="space-y-4">
          <h1 className="text-3xl font-semibold tracking-tight">What&apos;s your role?</h1>
          <p className="text-muted-foreground">So agents search the right boards and seniority.</p>

          <div className="space-y-2">
            <p className="text-sm font-medium">I am a…</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {ROLES.map((opt) => {
                const on = v.role === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => {
                      set("role", opt.id);
                      if (opt.id === "student" || opt.id === "intern") {
                        set("seniority_level", "intern");
                        if (v.search_focus === "jobs") set("search_focus", "internships");
                      }
                    }}
                    className={`rounded-xl border px-4 py-3 text-left text-sm font-medium transition ${
                      on ? "border-foreground bg-foreground text-background" : "hover:bg-muted/50"
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">What should we search for?</p>
            <div className="grid gap-2 sm:grid-cols-3">
              {SEARCH_FOCUS.map((opt) => {
                const on = v.search_focus === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => {
                      set("search_focus", opt.id);
                      if (opt.id === "internships") set("seniority_level", "intern");
                    }}
                    className={`rounded-xl border px-3 py-3 text-left transition ${
                      on ? "border-foreground bg-foreground text-background" : "hover:bg-muted/50"
                    }`}
                  >
                    <span className="block text-sm font-semibold">{opt.title}</span>
                    <span className={`mt-1 block text-xs ${on ? "text-background/80" : "text-muted-foreground"}`}>
                      {opt.blurb}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <Field label="Current title" value={v.current_title} onChange={(x) => set("current_title", x)} placeholder="e.g. Backend Intern" />
          <label className="block space-y-1.5 text-sm">
            <span className="font-medium">Target seniority</span>
            <select
              value={v.seniority_level}
              onChange={(e) => {
                set("seniority_level", e.target.value);
                if (e.target.value === "intern" && v.search_focus === "jobs") set("search_focus", "internships");
              }}
              className="w-full rounded-md border bg-background px-3 py-2"
            >
              {LEVELS.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>
          <Field
            label="Target titles (comma-separated)"
            value={v.target_titles}
            onChange={(x) => set("target_titles", x)}
            placeholder="Software Engineer, Backend Engineer"
            required
          />
          <Field label="Years of experience" value={v.years_experience} onChange={(x) => set("years_experience", x)} placeholder="2" />
          <Nav onBack={() => setStep(0)} onNext={() => setStep(2)} nextDisabled={!canRole} />
        </section>
      )}

      {step === 2 && (
        <section className="space-y-4">
          <h1 className="text-3xl font-semibold tracking-tight">Got a referral?</h1>
          <p className="text-muted-foreground">
            If a friend shared applyforme with you, enter their code. You&apos;ll get your own invite link after setup.
          </p>
          <Field
            label="Referral code (optional)"
            value={v.referral_code}
            onChange={(x) => set("referral_code", x)}
            placeholder="AFM-FRIEND123"
          />
          <Nav onBack={() => setStep(1)} onNext={() => setStep(3)} nextLabel="Continue" />
        </section>
      )}

      {step === 3 && (
        <section className="space-y-4">
          <h1 className="text-3xl font-semibold tracking-tight">Upload your resume</h1>
          <p className="text-muted-foreground">
            We parse name, experience, projects, and socials into your profile. PDF works best.
          </p>
          {hasResume ? (
            <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">Resume already on file — continue or replace below.</p>
          ) : null}
          <ResumeUpload redirectTo="/onboarding?resume=1" variant="profile" />
          <Nav
            onBack={() => setStep(2)}
            onNext={() => setStep(4)}
            nextLabel={hasResume ? "Continue" : "Skip for now"}
          />
        </section>
      )}

      {step === 4 && (
        <section className="space-y-4">
          <h1 className="text-3xl font-semibold tracking-tight">Confirm details &amp; filters</h1>
          <p className="text-muted-foreground">Pre-filled from your resume when possible. Edit anything, then open the dashboard.</p>
          <Field label="First name" value={v.first_name} onChange={(x) => set("first_name", x)} required />
          <Field label="Last name" value={v.last_name} onChange={(x) => set("last_name", x)} required />
          <Field label="Email" value={v.email} onChange={(x) => set("email", x)} type="email" required />
          <Field label="Phone" value={v.phone} onChange={(x) => set("phone", x)} />
          <Field label="Location" value={v.location} onChange={(x) => set("location", x)} placeholder="Bengaluru, India" />
          <Field label="LinkedIn URL" value={v.linkedin} onChange={(x) => set("linkedin", x)} />
          <Field label="GitHub URL" value={v.github} onChange={(x) => set("github", x)} />
          <Field label="Portfolio" value={v.portfolio} onChange={(x) => set("portfolio", x)} />
          <Field label="Accepted locations" value={v.locations} onChange={(x) => set("locations", x)} />
          <Field label="Reject if location mentions" value={v.reject_locations} onChange={(x) => set("reject_locations", x)} />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={v.remote_only === "on"}
              onChange={(e) => set("remote_only", e.target.checked ? "on" : "")}
            />
            Remote-only roles
          </label>
          <Field label="Work authorization" value={v.work_authorization} onChange={(x) => set("work_authorization", x)} />
          <Field label="Salary currency" value={v.salary_currency} onChange={(x) => set("salary_currency", x)} />
          <Field label="Expected annual salary" value={v.salary_expectation} onChange={(x) => set("salary_expectation", x)} />
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={() => setStep(3)} className="rounded-md border px-4 py-2 text-sm">
              Back
            </button>
            <button
              type="button"
              disabled={pending || !v.first_name || !v.email}
              onClick={finish}
              className="rounded-md bg-foreground px-4 py-2 text-sm text-background disabled:opacity-60"
            >
              {pending ? "Saving to profile…" : "Save profile & continue"}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  required?: boolean;
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

function Nav({
  onBack,
  onNext,
  nextLabel = "Continue",
  nextDisabled,
}: {
  onBack: () => void;
  onNext: () => void;
  nextLabel?: string;
  nextDisabled?: boolean;
}) {
  return (
    <div className="flex gap-3 pt-2">
      <button type="button" onClick={onBack} className="rounded-md border px-4 py-2 text-sm">
        Back
      </button>
      <button
        type="button"
        disabled={nextDisabled}
        onClick={onNext}
        className="rounded-md bg-foreground px-4 py-2 text-sm text-background disabled:opacity-40"
      >
        {nextLabel}
      </button>
    </div>
  );
}
