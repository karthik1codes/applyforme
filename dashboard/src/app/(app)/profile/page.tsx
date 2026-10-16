import { PageContainer } from "@/components/page-container";
import { saveProfileBasics } from "@/app/actions/profile";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { loadProfile } from "@/lib/profile";

export default async function ProfilePage({ searchParams }: { searchParams: Promise<{ saved?: string }> }) {
  requireOnboarding();
  const { saved } = await searchParams;
  const p = loadProfile();
  const personal = p.personal;

  return (
    <PageContainer title="Profile" description="Background and social links agents use on every application.">
      {saved && <p className="mb-4 text-sm text-emerald-600">Profile saved.</p>}
      <form action={saveProfileBasics} className="max-w-xl space-y-4">
        {(["first_name", "last_name", "email", "phone", "location", "linkedin", "github", "portfolio", "website", "twitter"] as const).map((k) => (
          <label key={k} className="block space-y-1 text-sm">
            <span className="font-medium capitalize">{k.replace("_", " ")}</span>
            <input name={k} defaultValue={personal[k] || ""} className="w-full rounded-md border bg-background px-3 py-2" />
          </label>
        ))}
        <label className="block space-y-1 text-sm">
          <span className="font-medium">Summary</span>
          <textarea name="summary" rows={4} defaultValue={p.summary || ""} className="w-full rounded-md border bg-background px-3 py-2" />
        </label>
        <label className="block space-y-1 text-sm">
          <span className="font-medium">Skills (comma-separated)</span>
          <input name="skills" defaultValue={(p.skills || []).join(", ")} className="w-full rounded-md border bg-background px-3 py-2" />
        </label>
        <button type="submit" className="rounded-md bg-foreground px-4 py-2 text-sm text-background">Save profile</button>
      </form>
    </PageContainer>
  );
}
