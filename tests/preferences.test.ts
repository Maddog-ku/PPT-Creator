import assert from "node:assert/strict";
import test from "node:test";
import {
  defaultPreferences,
  normalizePreferences,
  preferencesStorageKey,
  readPreferences,
  translate,
  writePreferences,
} from "../app/preferences.ts";

test("normalizes unknown and partial preference values safely", () => {
  assert.deepEqual(normalizePreferences(null), defaultPreferences);
  assert.deepEqual(normalizePreferences({
    colorMode: "dark",
    locale: "en",
    defaultPresentationLanguage: "ja",
    defaultSlideCount: "20",
  }), {
    colorMode: "dark",
    locale: "en",
    defaultPresentationLanguage: "ja",
    defaultSlideCount: "20",
  });
  assert.deepEqual(normalizePreferences({
    colorMode: "sepia",
    locale: "fr",
    defaultPresentationLanguage: "invalid",
    defaultSlideCount: "500",
  }), defaultPreferences);
});

test("reads and writes preferences through the provided storage", () => {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  };

  writePreferences(storage, {
    colorMode: "dark",
    locale: "en",
    defaultPresentationLanguage: "en",
    defaultSlideCount: "15",
  });

  assert.ok(values.has(preferencesStorageKey));
  assert.deepEqual(readPreferences(storage), {
    colorMode: "dark",
    locale: "en",
    defaultPresentationLanguage: "en",
    defaultSlideCount: "15",
  });
});

test("falls back when stored JSON is invalid", () => {
  assert.deepEqual(readPreferences({ getItem: () => "{" }), defaultPreferences);
});

test("translates interface copy without changing presentation content", () => {
  assert.equal(translate("en", "建立簡報"), "Create");
  assert.equal(translate("zh-TW", "建立簡報"), "建立簡報");
  assert.equal(translate("en", "使用者自己的簡報文字"), "使用者自己的簡報文字");
});
