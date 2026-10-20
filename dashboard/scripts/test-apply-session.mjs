import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const dir = fs.mkdtempSync(path.join(os.tmpdir(), "afm-db-"));
process.env.APPLYFORME_DB = path.join(dir, "test.db");

const {
  authorizeApply,
  clearApplyAuthorization,
  clearApplyCancel,
  db,
  getApplySession,
  requestApplyCancel,
  submissionRecorded,
} = await import("../src/lib/db.ts");

test("dashboard submit authorization is one explicit record and can be cleared", () => {
  assert.equal(authorizeApply("job-auth", "user-a"), true);
  const session = getApplySession("job-auth");
  assert.ok(session?.submitAuthorizedAt);
  assert.equal(session?.cancelRequested, false);

  clearApplyAuthorization("job-auth");
  assert.equal(getApplySession("job-auth")?.submitAuthorizedAt, null);
});

test("cancellation is persisted and can be cleared by a new prepare", () => {
  requestApplyCancel("job-cancel");
  assert.equal(getApplySession("job-cancel")?.cancelRequested, true);
  clearApplyCancel("job-cancel");
  assert.equal(getApplySession("job-cancel")?.cancelRequested, false);
});

test("a recorded submission blocks new authorization and is visible to the UI", () => {
  assert.equal(authorizeApply("job-done", "user-a"), true);
  db().prepare("UPDATE apply_sessions SET submitted_at=?, confirmation=? WHERE job_id=?").run(
    new Date().toISOString(),
    "Application received",
    "job-done",
  );
  assert.equal(submissionRecorded("job-done"), true);
  assert.equal(authorizeApply("job-done", "user-a"), false);
  assert.equal(getApplySession("job-done")?.confirmation, "Application received");
});

test.after(() => {
  try {
    db().close();
  } catch {
    /* ignore */
  }
  fs.rmSync(dir, { recursive: true, force: true });
});
