import { PageContainer } from "@/components/page-container";
import { ResumeUpload } from "@/components/landing/resume-upload";
import { saveProfileBasics } from "@/app/actions/profile";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { loadProfile } from "@/lib/profile";
import fs from "node:fs";
import path from "node:path";

function resumeStatus(): { present: boolean; name: string } {
  // The agent's resume sits in the repo root, outside the Next.js project.
  // Without the opt-out Turbopack traces the whole project into the build.
  const root = path.resolve(process.cwd(), "..");
  for (const name of ["resume.pdf", "resume.txt", "resume.docx", "resume.doc"]) {
    const candidate = path.join(/* turbopackIgnore: true */ root, name);
    if (fs.existsSync(/* turbopackIgnore: true */ candidate)) return { present: true, name };
  }
  return { present: false, name: "resume.pdf" };
}

export default async function ProfilePage({ searchParams }: { searchParams: Promise<{ saved?: string }> }) {
  await requireOnboarding();
  const { saved } = await searchParams;
  const p = loadProfile();
  const personal = p.personal;
  const resume = resumeStatus();
  const counts = {
    roles: (p.experience || []).length,
    skills: (p.skills || []).length,
    education: (p.education || []).length,
    projects: (p.projects || []).length,
    honors: (p.honors || []).length,
    custom: (p.custom_sections || []).length,
  };

  return (
    <PageContainer title="Profile" description="Filled from your resume on upload. Agents use this on every application.">
      {saved && <p className="mb-4 text-sm text-emerald-600">Profile saved.</p>}
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(260px,340px)] lg:items-start">
        <form action={saveProfileBasics} className="max-w-xl space-y-4">
          {(["first_name", "last_name", "email", "phone", "location", "linkedin", "github", "portfolio", "website", "twitter"] as const).map(
            (k) => (
              <label key={k} className="block space-y-1 text-sm">
                <span className="font-medium capitalize">{k.replace("_", " ")}</span>
                <input name={k} defaultValue={personal[k] || ""} className="w-full rounded-md border bg-background px-3 py-2" />
              </label>
            ),
          )}
          <label className="block space-y-1 text-sm">
            <span className="font-medium">Summary</span>
            <textarea name="summary" rows={4} defaultValue={p.summary || ""} className="w-full rounded-md border bg-background px-3 py-2" />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="font-medium">Skills (comma-separated)</span>
            <input name="skills" defaultValue={(p.skills || []).join(", ")} className="w-full rounded-md border bg-background px-3 py-2" />
          </label>
          <button type="submit" className="rounded-md bg-foreground px-4 py-2 text-sm text-background">
            Save profile
          </button>
        </form>

        <aside className="rounded-lg border bg-muted/30 p-5 lg:sticky lg:top-20">
          <h2 className="text-base font-semibold">Resume</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Upload your master PDF. We copy name, contact, socials, education, experience, projects, honors, and other sections into your profile exactly as written, then Tailor builds a job-specific PDF for each apply.
          </p>
          <dl className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-muted-foreground">File</dt>
              <dd className="truncate font-medium">{resume.present ? resume.name : "None yet"}</dd>
            </div>
            {(
              [
                ["Roles", counts.roles],
                ["Skills", counts.skills],
                ["Education", counts.education],
                ["Projects", counts.projects],
                ["Honors", counts.honors],
                ["Other sections", counts.custom],
              ] as const
            ).map(([label, n]) => (
              <div key={label} className="flex justify-between gap-3">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="font-medium">{n}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-5">
            <ResumeUpload variant="profile" redirectTo="" />
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            After upload, the form on the left refreshes with your details — no need to type them in. Replacing the PDF updates everything for the next Tailor/apply run.
          </p>
        </aside>
      </div>
    </PageContainer>
  );
}
