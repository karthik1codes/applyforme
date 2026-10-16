import { PageContainer } from "@/components/page-container";
import { savePreferences } from "@/app/actions/profile";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { loadProfile } from "@/lib/profile";

export default async function PreferencesPage({
  searchParams,
}: {
  searchParams: Promise<{ saved?: string }>;
}) {
  requireOnboarding();
  const { saved } = await searchParams;
  const pref = loadProfile().preferences;

  return (
    <PageContainer
      title="Preferences"
      description="What you're looking for right now. Agents re-read this on every discover / match run — junior level blocks Senior/Staff/Lead titles."
    >
      {saved && <p className="mb-4 text-sm text-emerald-600">Saved. Re-run discover to refresh the Jobs list.</p>}
      <form action={savePreferences} className="max-w-xl space-y-4">
        <label className="block space-y-1 text-sm">
          <span className="font-medium">Seniority</span>
          <select name="seniority_level" defaultValue={pref.seniority_level || "mid"} className="w-full rounded-md border bg-background px-3 py-2">
            {["intern", "junior", "mid", "senior", "lead", "executive"].map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </label>
        <F name="current_title" label="Current title" defaultValue={pref.current_title || ""} />
        <F name="years_experience" label="Years of experience" defaultValue={String(pref.years_experience ?? "")} />
        <F name="target_titles" label="Target titles (comma-separated)" defaultValue={(pref.target_titles || []).join(", ")} />
        <F name="locations" label="Locations" defaultValue={(pref.locations || []).join(", ")} />
        <F name="reject_locations" label="Reject locations" defaultValue={(pref.reject_locations || []).join(", ")} />
        <F name="exclude_keywords" label="Extra exclude keywords" defaultValue={(pref.exclude_keywords || []).join(", ")} />
        <F name="min_match_score" label="Min match score" defaultValue={String(pref.min_match_score ?? 70)} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="remote_only" defaultChecked={!!pref.remote_only} /> Remote only
        </label>
        <button type="submit" className="rounded-md bg-foreground px-4 py-2 text-sm text-background">Save preferences</button>
      </form>
    </PageContainer>
  );
}

function F({ name, label, defaultValue }: { name: string; label: string; defaultValue: string }) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="font-medium">{label}</span>
      <input name={name} defaultValue={defaultValue} className="w-full rounded-md border bg-background px-3 py-2" />
    </label>
  );
}
