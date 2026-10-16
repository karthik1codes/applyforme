import { PageContainer } from "@/components/page-container";
import { SettingsPanel } from "@/components/settings-panel";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { workerHealth } from "@/app/actions/pipeline";

export default async function SettingsPage() {
  requireOnboarding();
  const health = await workerHealth();
  const automationReady = !!process.env.PIPELINE_WEBHOOK_SECRET;

  return (
    <PageContainer
      title="Settings"
      description="How your job search runs — refresh anytime, or let the schedule handle it."
    >
      <SettingsPanel
        workerOnline={health.online}
        workerDetail={health.detail}
        scheduleRun={process.env.SCHEDULE_RUN || "0 */4 * * *"}
        scheduleInbox={process.env.SCHEDULE_INBOX || "30 */6 * * *"}
        automationReady={automationReady}
      />
    </PageContainer>
  );
}
