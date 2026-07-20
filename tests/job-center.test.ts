import assert from "node:assert/strict";
import test from "node:test";

import {
  isGenerationJobRetryable,
  shouldAutoOpenGenerationResult,
} from "../app/job-center.ts";

test("only exposes retry for a currently failed presentation", () => {
  assert.equal(isGenerationJobRetryable({ status: "FAILED", presentation_status: "FAILED", can_retry: true }), true);
  assert.equal(isGenerationJobRetryable({ status: "FAILED", presentation_status: "FAILED", can_retry: false }), false);
  assert.equal(isGenerationJobRetryable({ status: "FAILED", presentation_status: "PREVIEW_READY", can_retry: false }), false);
  assert.equal(isGenerationJobRetryable({ status: "COMPLETED", presentation_status: "FAILED", can_retry: false }), false);
});

test("only auto-opens a completed result from the generating view", () => {
  assert.equal(shouldAutoOpenGenerationResult("generating"), true);
  assert.equal(shouldAutoOpenGenerationResult("jobs"), false);
  assert.equal(shouldAutoOpenGenerationResult("library"), false);
  assert.equal(shouldAutoOpenGenerationResult("settings"), false);
});
