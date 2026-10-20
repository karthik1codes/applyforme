/** Parallel pipelines — jobs vs internships never block each other. */
export type PipelineLane = "jobs" | "internships" | "apply" | "inbox";

export function laneForStage(stage: string): PipelineLane {
  if (stage === "internships") return "internships";
  if (stage === "apply") return "apply";
  if (stage === "inbox") return "inbox";
  return "jobs"; // run, discover, enrich, match, tailor, cleanup
}
