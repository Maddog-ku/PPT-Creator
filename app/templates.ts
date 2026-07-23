export const templateCatalog = [
  { id: "editorial", name: "創意編輯", description: "桃紅撞色與大膽編排" },
  { id: "midnight", name: "深夜科技", description: "深色高對比的科技質感" },
  { id: "paper", name: "紙本報告", description: "襯線字與溫暖紙張色調" },
  { id: "ocean", name: "海洋策略", description: "冷靜藍綠的專業提案" },
  { id: "forest", name: "永續森林", description: "自然綠與有機曲線" },
  { id: "ember", name: "熾熱發表", description: "橘紅能量與斜向光束" },
  { id: "lavender", name: "柔霧創意", description: "紫色柔光的優雅敘事" },
  { id: "cobalt", name: "瑞士藍圖", description: "網格系統與精準藍色" },
  { id: "mono", name: "黑白極簡", description: "純粹留白與銳利線條" },
  { id: "aurora", name: "極光未來", description: "霓虹漸層與未來氛圍" },
] as const;

export type TemplateId = (typeof templateCatalog)[number]["id"];

export type PresentationTheme = {
  background: string;
  surface: string;
  text: string;
  muted: string;
  accent: string;
  accent2: string;
  accentSoft: string;
  line: string;
  onAccent: string;
  font: string;
  headingFont: string;
  motif:
    | "band"
    | "orbit"
    | "stripe"
    | "wave"
    | "arch"
    | "beam"
    | "bloom"
    | "grid"
    | "frame"
    | "aurora";
};

export const presentationThemes: Record<TemplateId, PresentationTheme> = {
  editorial: {
    background: "FFF7F1",
    surface: "FFFFFF",
    text: "271521",
    muted: "725F69",
    accent: "E9468C",
    accent2: "F97316",
    accentSoft: "FAD8E7",
    line: "E9D6DF",
    onAccent: "FFFFFF",
    font: "Noto Sans CJK TC",
    headingFont: "Noto Sans CJK TC",
    motif: "band",
  },
  midnight: {
    background: "101423",
    surface: "1B2236",
    text: "F7F8FC",
    muted: "B7BED1",
    accent: "58D6C7",
    accent2: "7C8CFF",
    accentSoft: "203F45",
    line: "35405A",
    onAccent: "081513",
    font: "Noto Sans CJK TC",
    headingFont: "Noto Sans CJK TC",
    motif: "orbit",
  },
  paper: {
    background: "F4F0E6",
    surface: "FBF8F1",
    text: "26251F",
    muted: "6D695D",
    accent: "B14A32",
    accent2: "D7A34A",
    accentSoft: "E9D7CB",
    line: "D8D0C0",
    onAccent: "FFFFFF",
    font: "Noto Serif CJK TC",
    headingFont: "Noto Serif CJK TC",
    motif: "stripe",
  },
  ocean: {
    background: "F2FAFB",
    surface: "FFFFFF",
    text: "10303A",
    muted: "526E76",
    accent: "007C91",
    accent2: "28B8A6",
    accentSoft: "D8F1F0",
    line: "C8E0E3",
    onAccent: "FFFFFF",
    font: "Noto Sans CJK TC",
    headingFont: "Noto Sans CJK TC",
    motif: "wave",
  },
  forest: {
    background: "F4F7EF",
    surface: "FCFDF9",
    text: "1F3327",
    muted: "607064",
    accent: "2F6B4F",
    accent2: "A07A45",
    accentSoft: "DDE9D9",
    line: "CDD8CA",
    onAccent: "FFFFFF",
    font: "Noto Serif CJK TC",
    headingFont: "Noto Serif CJK TC",
    motif: "arch",
  },
  ember: {
    background: "FFF8F2",
    surface: "FFFFFF",
    text: "341B18",
    muted: "765D57",
    accent: "E14B2D",
    accent2: "F59E0B",
    accentSoft: "FDE1D1",
    line: "EDCEC1",
    onAccent: "FFFFFF",
    font: "Noto Sans CJK TC",
    headingFont: "Noto Sans CJK TC",
    motif: "beam",
  },
  lavender: {
    background: "FAF7FF",
    surface: "FFFFFF",
    text: "302442",
    muted: "746680",
    accent: "7C5AC7",
    accent2: "D16BA5",
    accentSoft: "E9E0F8",
    line: "DED4EA",
    onAccent: "FFFFFF",
    font: "Noto Sans CJK TC",
    headingFont: "Noto Serif CJK TC",
    motif: "bloom",
  },
  cobalt: {
    background: "F5F8FF",
    surface: "FFFFFF",
    text: "101D3D",
    muted: "586680",
    accent: "155EEF",
    accent2: "00A3FF",
    accentSoft: "DCE8FF",
    line: "C9D6EF",
    onAccent: "FFFFFF",
    font: "Noto Sans CJK TC",
    headingFont: "Noto Sans CJK TC",
    motif: "grid",
  },
  mono: {
    background: "FAFAF8",
    surface: "FFFFFF",
    text: "111111",
    muted: "606060",
    accent: "111111",
    accent2: "737373",
    accentSoft: "E8E8E4",
    line: "CBCBC7",
    onAccent: "FFFFFF",
    font: "Noto Sans CJK TC",
    headingFont: "Noto Sans CJK TC",
    motif: "frame",
  },
  aurora: {
    background: "0B1020",
    surface: "171D35",
    text: "F5F7FF",
    muted: "B9C1D9",
    accent: "6EE7F2",
    accent2: "B76CF4",
    accentSoft: "263052",
    line: "354165",
    onAccent: "08131D",
    font: "Noto Sans CJK TC",
    headingFont: "Noto Sans CJK TC",
    motif: "aurora",
  },
};

export function isTemplateId(value: string): value is TemplateId {
  return templateCatalog.some((template) => template.id === value);
}
