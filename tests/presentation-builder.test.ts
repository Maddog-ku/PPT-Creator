import assert from "node:assert/strict";
import test from "node:test";

import JSZip from "jszip";

import {
  buildPresentationPptx,
  comparisonFrom,
  itemsFrom,
  metricFrom,
  PROJECTION_TYPOGRAPHY,
  type SlideData,
} from "../app/presentation-builder.ts";
import {
  presentationThemes,
  templateCatalog,
} from "../app/templates.ts";

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
    items: kind === "cards" || kind === "roadmap"
      ? [
          { label: "探索", title: "理解問題", body: "先確認真正需求" },
          { label: "驗證", title: "測試方案", body: "用回饋降低風險" },
          { label: "擴展", title: "規模化", body: "建立可重複流程" },
        ]
      : [],
    metric: kind === "metric"
      ? { value: "42%", label: "轉換率提升", context: "來自正式報表" }
      : null,
    comparison: kind === "comparison"
      ? {
          left: { label: "現行", title: "人工整理", body: "資訊容易分散" },
          right: { label: "建議", title: "結構化流程", body: "重點更容易理解" },
          callout: "先從最常使用的報告開始",
        }
      : null,
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
  const cardsSlide = await archive.file("ppt/slides/slide3.xml")?.async("string");
  assert.match(cardsSlide ?? "", /理解問題/);
  const comparisonSlide = await archive.file("ppt/slides/slide6.xml")?.async("string");
  assert.match(comparisonSlide ?? "", /人工整理/);
  assert.match(comparisonSlide ?? "", /結構化流程/);
  const roadmapSlide = await archive.file("ppt/slides/slide7.xml")?.async("string");
  assert.match(roadmapSlide ?? "", /規模化/);
});

test("upgrades legacy body-only slide data in the renderer", () => {
  const slide: SlideData = {
    id: crypto.randomUUID(),
    eyebrow: "01",
    title: "成果提升 18%",
    body: "理解問題。驗證方案。擴大成果。",
    kind: "metric",
  };

  assert.equal(metricFrom(slide).value, "18%");
  assert.equal(itemsFrom({ ...slide, kind: "cards" })[1].body, "驗證方案");
  assert.equal(
    comparisonFrom({ ...slide, kind: "comparison" }).right.body,
    "驗證方案",
  );
});

test("uses projection-safe typography for exported slides", () => {
  assert.ok(PROJECTION_TYPOGRAPHY.coverTitle >= 48);
  assert.ok(PROJECTION_TYPOGRAPHY.contentTitle >= 36);
  assert.ok(PROJECTION_TYPOGRAPHY.body >= 20);
  assert.ok(PROJECTION_TYPOGRAPHY.bodyCompact >= 18);
  assert.ok(PROJECTION_TYPOGRAPHY.itemBody >= 18);
  assert.ok(PROJECTION_TYPOGRAPHY.itemTitle >= 20);
  assert.ok(PROJECTION_TYPOGRAPHY.chrome >= 11);
});

test("supports at least ten distinct visual templates in editable PPTX output", async () => {
  assert.ok(templateCatalog.length >= 10);
  assert.deepEqual(
    new Set(templateCatalog.map((template) => template.id)),
    new Set(Object.keys(presentationThemes)),
  );

  const slides: SlideData[] = [
    {
      id: crypto.randomUUID(),
      eyebrow: "VISION",
      title: "十種視覺模板",
      body: "依照報告情境選擇適合的視覺語言。",
      kind: "cover",
    },
    {
      id: crypto.randomUUID(),
      eyebrow: "01",
      title: "內容保持一致",
      body: "模板負責視覺。結構負責溝通。使用者保有選擇。",
      kind: "cards",
    },
    {
      id: crypto.randomUUID(),
      eyebrow: "NEXT",
      title: "選擇最合適的風格",
      body: "完成模板矩陣驗證。",
      kind: "closing",
    },
  ];

  for (const template of templateCatalog) {
    const blob = await buildPresentationPptx(
      "模板矩陣",
      slides,
      template.id,
    );
    const archive = await JSZip.loadAsync(await blob.arrayBuffer());
    const slideFiles = Object.keys(archive.files).filter((name) => (
      /^ppt\/slides\/slide\d+\.xml$/.test(name)
    ));
    assert.equal(slideFiles.length, slides.length, template.id);
    const firstSlide = await archive.file("ppt/slides/slide1.xml")?.async("string");
    assert.match(firstSlide ?? "", new RegExp(presentationThemes[template.id].accent));
  }
});
