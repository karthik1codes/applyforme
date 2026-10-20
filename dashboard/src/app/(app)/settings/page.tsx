import { LinkedInConnectorCard } from "@/components/linkedin-connector-card";
import { PageContainer } from "@/components/page-container";
import { SettingsPanel } from "@/components/settings-panel";
import { linkedInCardData } from "@/lib/linkedin";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { workerHealth } from "@/app/actions/pipeline";

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ linkedin?: string; reason?: string }>;
}) {
  await requireOnboarding();
  const health = await workerHealth();
  const linkedIn = await linkedInCardData();
  const { linkedin } = await searchParams;
  const workerUrl = process.env.PIPELINE_WORKER_URL || "http://127.0.0.1:8787";
  const isProd = process.env.NODE_ENV === "production";
  const hostingLabel = isProd
    ? "Hosted on EC2 (systemd worker)"
    : `Local worker · ${workerUrl.replace(/^https?:\/\//, "")}`;

  return (
    <PageContainer
      title="Settings"
      description="Control searches that run on your EC2 worker — no terminal commands."
    >
      <LinkedInConnectorCard data={linkedIn} notice={linkedin} />
      <SettingsPanel
        workerOnline={health.online}
        workerDetail={health.detail}
        scheduleRun={process.env.SCHEDULE_RUN || "0 */4 * * *"}
        scheduleInternships={process.env.SCHEDULE_INTERNSHIPS || "15 */6 * * *"}
        scheduleInbox={process.env.SCHEDULE_INBOX || "30 */6 * * *"}
        hostingLabel={hostingLabel}
      />
    </PageContainer>
  );
}
