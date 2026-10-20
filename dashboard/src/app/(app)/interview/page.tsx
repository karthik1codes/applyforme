import { PageContainer } from "@/components/page-container";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { loadProfile } from "@/lib/profile";

export default async function InterviewPage() {
  await requireOnboarding();
  const p = loadProfile();
  const title = p.preferences.current_title || p.preferences.target_titles?.[0] || "your target role";
  const prompts = [
    `Tell me about yourself — keep it to 90 seconds for a ${title} interview.`,
    `Walk me through a project from your resume that used ${(p.skills || []).slice(0, 2).join(" and ") || "your main stack"}.`,
    `Why are you interested in ${p.preferences.target_titles?.[0] || "this role"} at this stage of your career?`,
    "Describe a time you disagreed with a teammate and how you resolved it.",
    "What would you want to learn in the first 90 days?",
  ];

  return (
    <PageContainer
      title="AI Interview Assistant"
      description="Practice prompts grounded in your profile. Answer out loud, then refine — agents do not submit interview answers for you."
    >
      <ul className="space-y-3">
        {prompts.map((q) => (
          <li key={q} className="rounded-lg border p-4 text-sm leading-relaxed">
            {q}
          </li>
        ))}
      </ul>
      <p className="mt-6 text-sm text-muted-foreground">
        Tip: keep answers tied to employers and metrics already in your profile so you stay consistent with tailored resumes.
      </p>
    </PageContainer>
  );
}
