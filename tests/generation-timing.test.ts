import assert from "node:assert/strict";
import test from "node:test";
import { elapsedSeconds, formatDuration } from "../app/generation-timing.ts";

test("formats approximate durations in both interface languages", () => {
  assert.equal(formatDuration(125, "zh-TW"), "約 2 分 5 秒");
  assert.equal(formatDuration(125, "en"), "about 2 min 5 sec");
  assert.equal(formatDuration(5, "zh-TW"), "少於 10 秒");
});

test("calculates elapsed time safely", () => {
  assert.equal(
    elapsedSeconds("2026-07-24T10:00:00.000Z", Date.parse("2026-07-24T10:01:30.000Z")),
    90,
  );
  assert.equal(elapsedSeconds(null), 0);
  assert.equal(elapsedSeconds("invalid"), 0);
});
