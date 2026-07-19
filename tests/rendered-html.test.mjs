import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the PPT Creator application", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>PPT Creator｜把內容變成好看的簡報<\/title>/i);
  assert.match(html, /把內容整理成/);
  assert.match(html, /產生簡報預覽/);
  assert.match(html, /下載前完整預覽/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|react-loading-skeleton/i);
});

test("ships accessible creation controls", async () => {
  const response = await render();
  const html = await response.text();

  assert.match(html, /id="presentation-topic"/);
  assert.match(html, /aria-label="選擇參考檔案"/);
  assert.match(html, /type="submit"/);
});
