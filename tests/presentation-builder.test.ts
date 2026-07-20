import assert from "node:assert/strict";
import test from "node:test";

import JSZip from "jszip";

import {
  buildPresentationPptx,
  type SlideData,
} from "../app/presentation-builder.ts";

test("builds every content-aware slide layout into an editable PPTX", async () => {
  const kinds: SlideData["kind"][] = [
    "cover",
    "section",
    "cards",
    "split",
    "metric",
    "comparison",
    "roadmap",
    "quote",
    "closing",
  ];
  const slides = kinds.map((kind, index): SlideData => ({
    id: crypto.randomUUID(),
    eyebrow: `PAGE ${String(index + 1).padStart(2, "0")}`,
    title: kind === "metric" ? "轉換率提升 42%" : `${kind} 版型示範`,
    body: "第一個內容重點。第二個內容重點。第三個內容重點。",
    kind,
    visual_prompt: null,
    image_data: null,
  }));

  const blob = await buildPresentationPptx("內容導向簡報", slides, "paper");
  const archive = await JSZip.loadAsync(await blob.arrayBuffer());
  const slideFiles = Object.keys(archive.files).filter((name) => (
    /^ppt\/slides\/slide\d+\.xml$/.test(name)
  ));

  assert.equal(slideFiles.length, kinds.length);
  const metricSlide = await archive.file("ppt/slides/slide5.xml")?.async("string");
  assert.match(metricSlide ?? "", /42%/);
});
