import assert from "node:assert/strict";
import test from "node:test";
import { buildPipelineArgs } from "../src/lib/pipeline-args.ts";

test("dashboard prepare never authorizes submission", () => {
  const args = buildPipelineArgs("apply", 1, { jobId: "job-1" });
  assert.deepEqual(args, ["-m", "applyforme", "apply", "job-1", "--limit", "1"]);
  assert.equal(args.includes("--yes"), false);
  assert.equal(args.includes("--submit"), false);
});

test("dashboard submit passes exactly one explicit --submit for one job", () => {
  const args = buildPipelineArgs("apply", 1, { jobId: "job-1", submit: true });
  assert.deepEqual(args, ["-m", "applyforme", "apply", "job-1", "--submit", "--limit", "1"]);
  assert.equal(args.includes("--yes"), false);
  assert.equal(args.filter((a) => a === "--submit").length, 1);
  assert.equal(args.filter((a) => a === "job-1").length, 1);
});

test("bulk apply is prepare-only in the dashboard", () => {
  const args = buildPipelineArgs("apply", 40);
  assert.deepEqual(args, ["-m", "applyforme", "apply", "--limit", "40"]);
  assert.equal(args.includes("--yes"), false);
  assert.equal(args.includes("--submit"), false);
});

test("other stages keep their existing argument shape", () => {
  assert.deepEqual(buildPipelineArgs("tailor", 40, { jobId: "job-1" }), [
    "-m", "applyforme", "tailor", "job-1", "--limit", "1",
  ]);
  assert.deepEqual(buildPipelineArgs("inbox", 40), ["-m", "applyforme", "inbox", "--days", "14"]);
  assert.deepEqual(buildPipelineArgs("run", 12), ["-m", "applyforme", "run", "--limit", "12"]);
});

test("cleanup uses the configured retention window, never a --limit", () => {
  const prev = process.env.JOB_RETENTION_DAYS;
  delete process.env.JOB_RETENTION_DAYS;
  try {
    assert.deepEqual(buildPipelineArgs("cleanup", 40), ["-m", "applyforme", "cleanup", "--days", "10"]);
    process.env.JOB_RETENTION_DAYS = "7";
    assert.deepEqual(buildPipelineArgs("cleanup", 40), ["-m", "applyforme", "cleanup", "--days", "7"]);
  } finally {
    if (prev === undefined) delete process.env.JOB_RETENTION_DAYS;
    else process.env.JOB_RETENTION_DAYS = prev;
  }
});
