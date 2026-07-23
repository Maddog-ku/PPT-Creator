import type { SlideData } from "./presentation-builder";

export function makeSlides(topic: string): SlideData[] {
  const subject = topic.trim() || "下一個好點子";
  return [
    {
      id: crypto.randomUUID(),
      eyebrow: "STRATEGY / 2026",
      title: subject,
      body: "從複雜資訊中，整理出一條清楚、可行動的敘事路徑。",
      kind: "cover",
    },
    {
      id: crypto.randomUUID(),
      eyebrow: "01 / 核心洞察",
      title: "先聚焦真正重要的三件事",
      body: "把所有資料收斂成受眾、價值與行動，讓每一頁只傳遞一個核心訊息。",
      kind: "cards",
    },
    {
      id: crypto.randomUUID(),
      eyebrow: "02 / 關鍵數字",
      title: "讓成果一眼就能理解",
      body: "重要數據不該被藏在段落裡。用清楚的層級讓決策者快速掌握變化。",
      kind: "metric",
    },
    {
      id: crypto.randomUUID(),
      eyebrow: "03 / 執行路徑",
      title: "從今天開始，逐步走到目標",
      body: "把策略拆成三個可驗證階段，每一階段都有清楚的交付成果。",
      kind: "roadmap",
    },
    {
      id: crypto.randomUUID(),
      eyebrow: "NEXT STEP",
      title: "準備好，把想法變成行動",
      body: "確認方向、建立第一版，並用真實回饋持續修正。",
      kind: "closing",
    },
  ];
}
