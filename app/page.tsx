"use client";

import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  Download,
  FileText,
  FolderOpen,
  Fullscreen,
  LayoutTemplate,
  LoaderCircle,
  KeyRound,
  MonitorUp,
  MoreHorizontal,
  PlugZap,
  Plus,
  Search,
  Settings,
  Sparkles,
  Trash2,
  UploadCloud,
  WandSparkles,
  X,
} from "lucide-react";
import type { ChangeEvent, DragEvent, FormEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

type View = "create" | "generating" | "preview" | "library" | "settings";
type TemplateId = "editorial" | "midnight" | "paper";

type SlideData = {
  eyebrow: string;
  title: string;
  body: string;
  kind: "cover" | "cards" | "metric" | "roadmap" | "closing";
};

type GenerationResponse = {
  title: string;
  language: string;
  provider: string;
  model: string;
  slides: SlideData[];
};

type ProviderKind = "ollama" | "openai" | "anthropic" | "gemini" | "openai_compatible";

type AIProviderResponse = {
  provider: string;
  model: string;
  transport: "api";
};

type AIProviderOption = {
  id: string;
  name: string;
  provider: ProviderKind;
  model: string;
  baseUrl?: string;
  hasApiKey?: boolean;
  builtIn?: boolean;
};

type ProviderDraft = {
  name: string;
  provider: ProviderKind;
  baseUrl: string;
  model: string;
  apiKey: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

const providerLabels: Record<ProviderKind, string> = {
  ollama: "本機 API",
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Google Gemini",
  openai_compatible: "OpenAI 相容 API",
};

const providerBaseUrls: Record<ProviderKind, string> = {
  ollama: "http://127.0.0.1:11434",
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com/v1",
  gemini: "https://generativelanguage.googleapis.com/v1beta",
  openai_compatible: "http://localhost:1234/v1",
};

async function fetchProviderOptions(): Promise<AIProviderOption[]> {
  const options: AIProviderOption[] = [];
  const [builtInResult, customResult] = await Promise.allSettled([
    fetch(`${apiBaseUrl}/ai-provider`),
    fetch(`${apiBaseUrl}/ai-providers`),
  ]);
  if (builtInResult.status === "fulfilled" && builtInResult.value.ok) {
    const provider = await builtInResult.value.json() as AIProviderResponse;
    options.push({
      id: "default",
      name: "本機預設",
      provider: provider.provider as ProviderKind,
      model: provider.model,
      builtIn: true,
    });
  }
  if (customResult.status === "fulfilled" && customResult.value.ok) {
    const providers = await customResult.value.json() as Array<{
      id: string;
      name: string;
      provider: ProviderKind;
      base_url: string;
      model: string;
      has_api_key: boolean;
    }>;
    options.push(...providers.map((provider) => ({
      id: provider.id,
      name: provider.name,
      provider: provider.provider,
      model: provider.model,
      baseUrl: provider.base_url,
      hasApiKey: provider.has_api_key,
    })));
  }
  return options;
}

const templates: Array<{
  id: TemplateId;
  name: string;
  description: string;
}> = [
  { id: "editorial", name: "創意編輯", description: "明亮、有節奏的品牌提案" },
  { id: "midnight", name: "深夜科技", description: "高對比的產品與數據簡報" },
  { id: "paper", name: "紙本報告", description: "安靜、理性的研究型版面" },
];

const recentPresentations = [
  { title: "2026 產品策略提案", slides: 12, updated: "剛剛", status: "草稿" },
  { title: "品牌季度成效回顧", slides: 18, updated: "昨天", status: "已完成" },
  { title: "新進同仁培訓手冊", slides: 24, updated: "7 月 15 日", status: "已完成" },
];

function makeSlides(topic: string): SlideData[] {
  const subject = topic.trim() || "下一個好點子";
  return [
    {
      eyebrow: "STRATEGY / 2026",
      title: subject,
      body: "從複雜資訊中，整理出一條清楚、可行動的敘事路徑。",
      kind: "cover",
    },
    {
      eyebrow: "01 / 核心洞察",
      title: "先聚焦真正重要的三件事",
      body: "把所有資料收斂成受眾、價值與行動，讓每一頁只傳遞一個核心訊息。",
      kind: "cards",
    },
    {
      eyebrow: "02 / 關鍵數字",
      title: "讓成果一眼就能理解",
      body: "重要數據不該被藏在段落裡。用清楚的層級讓決策者快速掌握變化。",
      kind: "metric",
    },
    {
      eyebrow: "03 / 執行路徑",
      title: "從今天開始，逐步走到目標",
      body: "把策略拆成三個可驗證階段，每一階段都有清楚的交付成果。",
      kind: "roadmap",
    },
    {
      eyebrow: "NEXT STEP",
      title: "準備好，把想法變成行動",
      body: "確認方向、建立第一版，並用真實回饋持續修正。",
      kind: "closing",
    },
  ];
}

function slidePoints(body: string, count = 3): string[] {
  const points = body
    .split(/[。！？；\n]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, count);
  while (points.length < count) points.push(points.at(-1) ?? body);
  return points;
}

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <span />
      <span />
    </span>
  );
}

function SideNavigation({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  const items = [
    { id: "create" as const, label: "建立簡報", icon: Plus },
    { id: "library" as const, label: "我的簡報", icon: FolderOpen },
    { id: "settings" as const, label: "設定", icon: Settings },
  ];

  return (
    <aside className="side-navigation" aria-label="主要導覽">
      <button className="side-logo" onClick={() => onChange("create")} aria-label="PPT Creator 首頁">
        <BrandMark />
      </button>
      <nav>
        {items.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={view === id || (view === "generating" && id === "create") || (view === "preview" && id === "create") ? "active" : ""}
            onClick={() => onChange(id)}
            aria-label={label}
            title={label}
          >
            <Icon size={20} strokeWidth={1.9} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <button className="side-help" aria-label="使用說明" title="使用說明">
        <CircleHelp size={20} />
      </button>
    </aside>
  );
}

function AppHeader({ onCreate }: { onCreate: () => void }) {
  return (
    <header className="app-header">
      <div className="mobile-brand">
        <BrandMark />
        <strong>PPT Creator</strong>
      </div>
      <div className="header-actions">
        <button className="icon-button" aria-label="搜尋">
          <Search size={19} />
        </button>
        <button className="quiet-button" onClick={onCreate}>
          <Plus size={17} />
          新增簡報
        </button>
        <button className="avatar" aria-label="使用者選單">DC</button>
      </div>
    </header>
  );
}

function CreateView({
  topic,
  setTopic,
  files,
  setFiles,
  template,
  setTemplate,
  language,
  setLanguage,
  slideCount,
  setSlideCount,
  providerOptions,
  selectedProviderId,
  setSelectedProviderId,
  onGenerate,
}: {
  topic: string;
  setTopic: (value: string) => void;
  files: File[];
  setFiles: (files: File[]) => void;
  template: TemplateId;
  setTemplate: (template: TemplateId) => void;
  language: string;
  setLanguage: (language: string) => void;
  slideCount: number;
  setSlideCount: (count: number) => void;
  providerOptions: AIProviderOption[];
  selectedProviderId: string;
  setSelectedProviderId: (id: string) => void;
  onGenerate: (event: FormEvent<HTMLFormElement>) => Promise<void>;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const addFiles = (incoming: File[]) => {
    const next = [...files];
    incoming.forEach((file) => {
      if (!next.some((item) => item.name === file.name && item.size === file.size)) next.push(file);
    });
    setFiles(next.slice(0, 8));
  };

  const handleFiles = (event: ChangeEvent<HTMLInputElement>) => {
    addFiles(Array.from(event.target.files ?? []));
    event.target.value = "";
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    addFiles(Array.from(event.dataTransfer.files));
  };

  return (
    <main className="create-view">
      <section className="create-intro">
        <div className="eyebrow"><WandSparkles size={15} /> AI 簡報工作室</div>
        <h1>把內容整理成<br /><span>一份好看的簡報。</span></h1>
        <p>輸入主題或加入參考資料，我們會先整理架構，再讓你逐頁確認完整成果。</p>
        <div className="trust-row" aria-label="產品特點">
          <span><Check size={14} /> 可編輯 PPTX</span>
          <span><Check size={14} /> 下載前完整預覽</span>
          <span><Check size={14} /> 支援本地模型</span>
        </div>
      </section>

      <form className="creator-card" onSubmit={onGenerate}>
        <div className="step-label"><span>1</span> 告訴我們簡報要說什麼</div>
        <label className="field-label" htmlFor="presentation-topic">簡報主題與需求</label>
        <div className="topic-field">
          <textarea
            id="presentation-topic"
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="例如：為管理團隊製作一份 2026 年產品策略提案，重點放在市場機會、三項優先計畫與執行時程。"
            rows={5}
            required
          />
          <span className="character-count">{topic.length} / 1,500</span>
        </div>

        <label className="field-label">參考資料 <small>選填，最多 8 個檔案</small></label>
        <div
          className={`dropzone ${dragging ? "dragging" : ""}`}
          onDragEnter={() => setDragging(true)}
          onDragLeave={() => setDragging(false)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
          onClick={() => fileInput.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") fileInput.current?.click();
          }}
        >
          <input
            ref={fileInput}
            type="file"
            multiple
            accept=".pdf,.ppt,.pptx,.txt,.md"
            onChange={handleFiles}
            aria-label="選擇參考檔案"
          />
          <span className="upload-icon"><UploadCloud size={22} /></span>
          <div><strong>拖曳檔案到這裡</strong><small>或點擊選擇 PDF、PPTX、TXT</small></div>
        </div>

        {files.length > 0 && (
          <ul className="file-list" aria-label="已加入的檔案">
            {files.map((file) => (
              <li key={`${file.name}-${file.size}`}>
                <FileText size={17} />
                <span><strong>{file.name}</strong><small>{Math.max(1, Math.round(file.size / 1024))} KB</small></span>
                <button
                  type="button"
                  aria-label={`移除 ${file.name}`}
                  onClick={() => setFiles(files.filter((item) => item !== file))}
                ><X size={16} /></button>
              </li>
            ))}
          </ul>
        )}

        <div className="form-grid">
          <label>
            <span className="field-label">簡報語言</span>
            <select value={language} onChange={(event) => setLanguage(event.target.value)}>
              <option value="zh-TW">繁體中文</option>
              <option value="en">English</option>
              <option value="ja">日本語</option>
            </select>
          </label>
          <label>
            <span className="field-label">預計頁數</span>
            <select value={slideCount} onChange={(event) => setSlideCount(Number(event.target.value))}>
              <option value="6">約 6 頁</option>
              <option value="10">約 10 頁</option>
              <option value="15">約 15 頁</option>
              <option value="20">約 20 頁</option>
            </select>
          </label>
        </div>

        <label className="provider-select">
          <span className="field-label">使用的 AI 模型</span>
          <select
            value={selectedProviderId}
            onChange={(event) => setSelectedProviderId(event.target.value)}
            disabled={providerOptions.length === 0}
          >
            {providerOptions.length === 0 ? (
              <option value="default">請先到設定新增 AI API</option>
            ) : providerOptions.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.name} · {provider.model}
              </option>
            ))}
          </select>
          <small>可在設定中加入更多本機或雲端模型 API。</small>
        </label>

        <fieldset className="template-picker">
          <legend className="field-label">選擇視覺風格</legend>
          <div className="template-options">
            {templates.map((item) => (
              <label key={item.id} className={template === item.id ? "selected" : ""}>
                <input
                  type="radio"
                  name="template"
                  value={item.id}
                  checked={template === item.id}
                  onChange={() => setTemplate(item.id)}
                />
                <span className={`template-swatch ${item.id}`} aria-hidden="true"><i /><i /><i /></span>
                <span><strong>{item.name}</strong><small>{item.description}</small></span>
                {template === item.id && <Check className="template-check" size={15} />}
              </label>
            ))}
          </div>
        </fieldset>

        <button className="primary-button generate-button" type="submit">
          產生簡報預覽
          <ArrowRight size={18} />
        </button>
        <p className="form-note">先在網站完整確認每一頁，確認後才會開放下載。</p>
      </form>
    </main>
  );
}

function GeneratingView({ progress, error, onBack }: { progress: number; error: string | null; onBack: () => void }) {
  const stages = [
    { label: "分析內容與參考資料", at: 10 },
    { label: "整理簡報敘事架構", at: 35 },
    { label: "建立逐頁內容", at: 58 },
    { label: "套用版型並檢查版面", at: 82 },
  ];

  return (
    <main className="generating-view" aria-live="polite">
      <div className="generation-orbit" aria-hidden="true">
        <span /><span /><WandSparkles size={30} />
      </div>
      <p className="eyebrow">正在製作你的簡報</p>
      <h1>{error ? "無法完成這次生成" : "把內容變成清楚的故事"}</h1>
      <p>{error ?? "AI 服務正在整理重點、安排順序，並為每一頁選擇合適的版面。"}</p>
      <div className="progress-card">
        <div className="progress-heading"><strong>{progress}%</strong><span>{error ? "請檢查本機服務" : "本地模型生成中"}</span></div>
        <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
        {error ? (
          <div className="generation-error">
            <strong>請確認後端 API 與 AI 服務都已啟動</strong>
            <button className="quiet-button" onClick={onBack}>返回設定</button>
          </div>
        ) : (
          <ol>
            {stages.map((stage) => (
              <li key={stage.label} className={progress >= stage.at ? "done" : progress + 18 >= stage.at ? "current" : ""}>
                <span>{progress >= stage.at ? <Check size={14} /> : <LoaderCircle size={14} />}</span>
                {stage.label}
              </li>
            ))}
          </ol>
        )}
      </div>
    </main>
  );
}

function SlideCanvas({ slide, topic, compact = false }: { slide: SlideData; topic: string; compact?: boolean }) {
  const points = slidePoints(slide.body);
  return (
    <div className={`slide-canvas slide-${slide.kind} ${compact ? "compact" : ""}`}>
      <div className="slide-chrome">
        <BrandMark />
        <span>PPT CREATOR</span>
      </div>
      {slide.kind === "cover" && (
        <>
          <div className="slide-glow" />
          <div className="slide-copy">
            <span className="slide-eyebrow">{slide.eyebrow}</span>
            <h2>{topic || slide.title}</h2>
            <p>{slide.body}</p>
          </div>
          <div className="cover-index">01</div>
        </>
      )}
      {slide.kind === "cards" && (
        <div className="slide-layout">
          <span className="slide-eyebrow">{slide.eyebrow}</span>
          <h2>{slide.title}</h2>
          <div className="insight-cards">
            {["重點一", "重點二", "重點三"].map((label, index) => (
              <div key={label}><span>0{index + 1}</span><strong>{label}</strong><p>{points[index]}</p></div>
            ))}
          </div>
        </div>
      )}
      {slide.kind === "metric" && (
        <div className="slide-layout metric-layout">
          <div><span className="slide-eyebrow">{slide.eyebrow}</span><h2>{slide.title}</h2><p>{slide.body}</p></div>
          <div className="big-metric"><strong>3.2×</strong><span>更快掌握核心訊息</span><i><b /></i></div>
        </div>
      )}
      {slide.kind === "roadmap" && (
        <div className="slide-layout roadmap-layout">
          <span className="slide-eyebrow">{slide.eyebrow}</span>
          <h2>{slide.title}</h2>
          <div className="roadmap-line">
            {["第一階段", "第二階段", "第三階段"].map((label, index) => (
              <div key={label}><span>{index + 1}</span><strong>{label}</strong><small>{points[index]}</small></div>
            ))}
          </div>
        </div>
      )}
      {slide.kind === "closing" && (
        <div className="closing-layout">
          <span className="slide-eyebrow">{slide.eyebrow}</span>
          <h2>{slide.title}</h2>
          <p>{slide.body}</p>
          <div className="closing-pill">LET&apos;S BEGIN <ArrowRight size={16} /></div>
        </div>
      )}
    </div>
  );
}

function PreviewView({ topic, slides, onBack }: { topic: string; slides: SlideData[]; onBack: () => void }) {
  const [active, setActive] = useState(0);
  const [confirmed, setConfirmed] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);
  const current = slides[active];

  const downloadPptx = async () => {
    if (!confirmed) return;
    setDownloading(true);
    try {
      const { default: PptxGenJS } = await import("pptxgenjs");
      const pptx = new PptxGenJS();
      pptx.layout = "LAYOUT_WIDE";
      pptx.author = "PPT Creator";
      pptx.subject = topic;
      pptx.title = topic;
      pptx.company = "PPT Creator";

      const dark = "15121F";
      const cream = "FFF8F2";
      const pink = "EC4899";
      slides.forEach((item, index) => {
        const slide = pptx.addSlide();
        slide.background = { color: index === 2 ? cream : dark };
        slide.addText("PPT CREATOR", { x: 0.65, y: 0.38, w: 1.8, h: 0.25, fontFace: "Arial", fontSize: 9, bold: true, color: index === 2 ? "831843" : "F8DDEC", charSpacing: 2 });
        slide.addText(item.eyebrow, { x: 0.75, y: 1.25, w: 3.5, h: 0.3, fontFace: "Arial", fontSize: 11, bold: true, color: pink, charSpacing: 1.5 });
        slide.addText(index === 0 ? topic : item.title, { x: 0.75, y: 1.8, w: 8.8, h: 1.45, fontFace: "Arial", fontSize: index === 0 ? 34 : 29, bold: true, color: index === 2 ? "351B2B" : "FFFFFF", breakLine: false, margin: 0 });
        slide.addText(item.body, { x: 0.78, y: 3.45, w: 6.4, h: 0.8, fontFace: "Arial", fontSize: 15, color: index === 2 ? "684F5D" : "DACED6", margin: 0, breakLine: false });
        slide.addShape(pptx.ShapeType.line, { x: 0.75, y: 6.75, w: 11.85, h: 0, line: { color: index === 2 ? "E9CFDD" : "44394E", width: 1 } });
        slide.addText(String(index + 1).padStart(2, "0"), { x: 11.9, y: 6.85, w: 0.7, h: 0.25, align: "right", fontFace: "Arial", fontSize: 9, color: index === 2 ? "831843" : "F8DDEC" });
      });
      const safeName = (topic || "presentation").replace(/[\\/:*?"<>|]/g, "-").slice(0, 60);
      await pptx.writeFile({ fileName: `${safeName}.pptx` });
    } finally {
      setDownloading(false);
    }
  };

  const toggleFullscreen = async () => {
    if (!stageRef.current) return;
    if (document.fullscreenElement) await document.exitFullscreen();
    else await stageRef.current.requestFullscreen();
  };

  return (
    <main className="preview-view">
      <header className="preview-toolbar">
        <button className="quiet-button" onClick={onBack}><ArrowLeft size={17} /> 返回修改</button>
        <div className="preview-title"><strong>{topic || "未命名簡報"}</strong><span><Check size={13} /> 已完成預覽</span></div>
        <div className="preview-actions">
          <button className="icon-button" onClick={toggleFullscreen} aria-label="全螢幕預覽" title="全螢幕預覽"><Fullscreen size={18} /></button>
          <button className="download-button" onClick={downloadPptx} disabled={!confirmed || downloading}>
            {downloading ? <LoaderCircle className="spin" size={17} /> : <Download size={17} />}
            {downloading ? "準備檔案" : "下載 PPTX"}
          </button>
        </div>
      </header>

      <div className="preview-workspace">
        <aside className="slide-strip" aria-label="投影片縮圖">
          <div className="slide-strip-heading"><span>投影片</span><strong>{slides.length}</strong></div>
          {slides.map((slide, index) => (
            <button key={`${slide.kind}-${index}`} className={active === index ? "active" : ""} onClick={() => setActive(index)} aria-label={`前往第 ${index + 1} 頁`}>
              <span className="thumbnail-number">{index + 1}</span>
              <SlideCanvas slide={slide} topic={topic} compact />
            </button>
          ))}
        </aside>

        <section className="slide-stage" ref={stageRef}>
          <div className="stage-meta"><span>16:9</span><span>頁面 {active + 1} / {slides.length}</span></div>
          <div className="slide-frame"><SlideCanvas slide={current} topic={topic} /></div>
          <div className="slide-controls">
            <button onClick={() => setActive(Math.max(0, active - 1))} disabled={active === 0} aria-label="上一頁"><ChevronLeft size={19} /></button>
            <span>{active + 1} / {slides.length}</span>
            <button onClick={() => setActive(Math.min(slides.length - 1, active + 1))} disabled={active === slides.length - 1} aria-label="下一頁"><ChevronRight size={19} /></button>
          </div>
        </section>

        <aside className="review-panel">
          <div className="review-icon"><MonitorUp size={22} /></div>
          <p className="eyebrow">下載前確認</p>
          <h2>每一頁都看過了嗎？</h2>
          <p>請檢查文字、數字與版面。若需要修改，可以返回上一步重新產生。</p>
          <ul>
            <li><Check size={15} /> 標題與內容正確</li>
            <li><Check size={15} /> 沒有文字溢出</li>
            <li><Check size={15} /> 頁面順序符合需求</li>
          </ul>
          {!confirmed ? (
            <button className="primary-button" onClick={() => setConfirmed(true)}><Check size={17} /> 確認簡報沒問題</button>
          ) : (
            <div className="confirmed-state"><span><Check size={17} /></span><div><strong>已確認，可以下載</strong><small>PPTX 內的文字仍可編輯</small></div></div>
          )}
          <button className="text-button" onClick={onBack}>需要調整內容 <ArrowRight size={15} /></button>
        </aside>
      </div>
    </main>
  );
}

function LibraryView({ onCreate }: { onCreate: () => void }) {
  return (
    <main className="secondary-view">
      <div className="section-heading">
        <div><p className="eyebrow">工作空間</p><h1>我的簡報</h1><p>查看、預覽與管理你建立的所有簡報。</p></div>
        <button className="primary-button" onClick={onCreate}><Plus size={17} /> 建立簡報</button>
      </div>
      <div className="library-tools">
        <label><Search size={17} /><input placeholder="搜尋簡報" aria-label="搜尋簡報" /></label>
        <button><Clock3 size={16} /> 最近更新 <ChevronRight size={14} /></button>
      </div>
      <div className="presentation-grid">
        {recentPresentations.map((item, index) => (
          <article key={item.title}>
            <div className={`presentation-cover cover-${index + 1}`}><span>{String(index + 1).padStart(2, "0")}</span><strong>{item.title}</strong><BrandMark /></div>
            <div className="presentation-info"><div><h2>{item.title}</h2><p>{item.slides} 頁 · {item.updated}</p></div><button aria-label={`${item.title} 更多選項`}><MoreHorizontal size={18} /></button></div>
            <span className="status-badge">{item.status}</span>
          </article>
        ))}
        <button className="new-presentation-card" onClick={onCreate}><span><Plus size={21} /></span><strong>建立新簡報</strong><small>從主題或文件開始</small></button>
      </div>
    </main>
  );
}

function SettingsView({
  providerOptions,
  reloadProviderOptions,
}: {
  providerOptions: AIProviderOption[];
  reloadProviderOptions: () => Promise<void>;
}) {
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [connections, setConnections] = useState<Record<string, { status: "idle" | "testing" | "connected" | "failed"; message: string }>>({});
  const [draft, setDraft] = useState<ProviderDraft>({
    name: "",
    provider: "openai",
    baseUrl: providerBaseUrls.openai,
    model: "",
    apiKey: "",
  });

  const setProviderKind = (provider: ProviderKind) => {
    setDraft((current) => ({ ...current, provider, baseUrl: providerBaseUrls[provider] }));
  };

  const saveProvider = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/ai-providers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: draft.name,
          provider: draft.provider,
          base_url: draft.baseUrl,
          model: draft.model,
          api_key: draft.apiKey || null,
        }),
      });
      const result = await response.json() as { detail?: string };
      if (!response.ok) throw new Error(result.detail || "無法儲存 AI 設定");
      await reloadProviderOptions();
      setDraft({ name: "", provider: "openai", baseUrl: providerBaseUrls.openai, model: "", apiKey: "" });
      setShowForm(false);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "無法儲存 AI 設定");
    } finally {
      setSaving(false);
    }
  };

  const testProvider = async (provider: AIProviderOption) => {
    setConnections((current) => ({ ...current, [provider.id]: { status: "testing", message: "測試中" } }));
    try {
      const path = provider.builtIn ? "/ai-provider/test" : `/ai-providers/${provider.id}/test`;
      const response = await fetch(`${apiBaseUrl}${path}`, { method: "POST" });
      const result = await response.json() as { connected?: boolean; error?: string | null };
      if (!response.ok || !result.connected) throw new Error(result.error || "連線失敗");
      setConnections((current) => ({ ...current, [provider.id]: { status: "connected", message: "已連線" } }));
    } catch (error) {
      setConnections((current) => ({
        ...current,
        [provider.id]: { status: "failed", message: error instanceof Error ? error.message : "連線失敗" },
      }));
    }
  };

  const deleteProvider = async (provider: AIProviderOption) => {
    if (!window.confirm(`確定要刪除「${provider.name}」嗎？`)) return;
    const response = await fetch(`${apiBaseUrl}/ai-providers/${provider.id}`, { method: "DELETE" });
    if (response.ok) await reloadProviderOptions();
  };

  return (
    <main className="secondary-view settings-view">
      <div className="section-heading"><div><p className="eyebrow">偏好設定</p><h1>AI 模型設定</h1><p>加入多個模型 API，測試後可在建立簡報時自由選擇。</p></div></div>
      <section className="settings-card">
        <div className="settings-section-heading provider-heading">
          <span><Sparkles size={18} /></span>
          <div><h2>已串接的 AI 模型</h2><p>API Key 會加密保存，設定頁不會再次顯示明文。</p></div>
          <button className="quiet-button" onClick={() => setShowForm((current) => !current)}><Plus size={15} /> 新增模型</button>
        </div>

        {showForm && (
          <form className="provider-form" onSubmit={saveProvider}>
            <label><span>設定名稱</span><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="例如：公司 OpenAI" required /></label>
            <label><span>API 類型</span><select value={draft.provider} onChange={(event) => setProviderKind(event.target.value as ProviderKind)}>{Object.entries(providerLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label className="wide"><span>Base URL</span><input value={draft.baseUrl} onChange={(event) => setDraft({ ...draft, baseUrl: event.target.value })} type="url" required /></label>
            <label><span>模型名稱</span><input value={draft.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })} placeholder="輸入 API 提供的模型 ID" required /></label>
            <label><span>API Key {draft.provider === "ollama" || draft.provider === "openai_compatible" ? "（選填）" : ""}</span><div className="secret-field"><KeyRound size={15} /><input value={draft.apiKey} onChange={(event) => setDraft({ ...draft, apiKey: event.target.value })} type="password" autoComplete="new-password" required={draft.provider !== "ollama" && draft.provider !== "openai_compatible"} /></div></label>
            {formError && <p className="provider-form-error">{formError}</p>}
            <div className="provider-form-actions"><button type="button" className="quiet-button" onClick={() => setShowForm(false)}>取消</button><button className="primary-button" disabled={saving}>{saving ? "儲存中" : "儲存設定"}</button></div>
          </form>
        )}

        <div className="provider-list">
          {providerOptions.map((provider) => {
            const connection = connections[provider.id] ?? { status: "idle", message: "尚未測試" };
            return (
              <div className="setting-row provider-row" key={provider.id}>
                <div className="provider-copy"><strong>{provider.name}</strong><small>{providerLabels[provider.provider] ?? provider.provider} · {provider.model}</small><small>{provider.builtIn ? "系統預設" : provider.hasApiKey ? "API Key 已加密保存" : "未設定 API Key"}</small></div>
                <span className={`connection-badge ${connection.status}`}>{connection.message}</span>
                <div className="provider-actions">
                  <button className="quiet-button" onClick={() => testProvider(provider)} disabled={connection.status === "testing"}><PlugZap size={14} /> {connection.status === "testing" ? "測試中" : "測試"}</button>
                  {!provider.builtIn && <button className="icon-button danger-button" onClick={() => deleteProvider(provider)} aria-label={`刪除 ${provider.name}`}><Trash2 size={15} /></button>}
                </div>
              </div>
            );
          })}
          {providerOptions.length === 0 && <p className="empty-provider">目前無法讀取 AI API，請確認後端服務與 PostgreSQL 已啟動。</p>}
        </div>
      </section>
      <section className="settings-card">
        <div className="settings-section-heading"><span><LayoutTemplate size={18} /></span><div><h2>簡報預設值</h2><p>建立新簡報時會自動帶入以下設定。</p></div></div>
        <div className="settings-form-grid"><label><span>預設語言</span><select defaultValue="zh-TW"><option value="zh-TW">繁體中文</option><option value="en">English</option></select></label><label><span>預設頁數</span><select defaultValue="10"><option value="10">約 10 頁</option><option value="15">約 15 頁</option></select></label></div>
      </section>
    </main>
  );
}

export default function Home() {
  const [view, setView] = useState<View>("create");
  const [topic, setTopic] = useState("2026 年產品策略提案");
  const [files, setFiles] = useState<File[]>([]);
  const [template, setTemplate] = useState<TemplateId>("editorial");
  const [language, setLanguage] = useState("zh-TW");
  const [slideCount, setSlideCount] = useState(10);
  const [providerOptions, setProviderOptions] = useState<AIProviderOption[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState("default");
  const [progress, setProgress] = useState(0);
  const [slides, setSlides] = useState<SlideData[]>(() => makeSlides(topic));
  const [generationError, setGenerationError] = useState<string | null>(null);

  const reloadProviderOptions = useCallback(async () => {
    const options = await fetchProviderOptions();
    setProviderOptions(options);
    setSelectedProviderId((current) => options.some((provider) => provider.id === current) ? current : options[0]?.id ?? "default");
  }, []);

  useEffect(() => {
    let active = true;
    void fetchProviderOptions().then((options) => {
      if (!active) return;
      setProviderOptions(options);
      setSelectedProviderId(options[0]?.id ?? "default");
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (view !== "generating" || generationError) return;
    const timer = window.setInterval(() => {
      setProgress((current) => Math.min(88, current + Math.max(1, Math.round((90 - current) / 10))));
    }, 650);
    return () => window.clearInterval(timer);
  }, [generationError, view]);

  const startGeneration = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setProgress(7);
    setGenerationError(null);
    setView("generating");
    try {
      const textSources = await Promise.all(
        files
          .filter((file) => /\.(txt|md)$/i.test(file.name))
          .map(async (file) => `# ${file.name}\n${await file.text()}`),
      );
      const response = await fetch(`${apiBaseUrl}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          language,
          slide_count: slideCount,
          template,
          source_text: textSources.join("\n\n").slice(0, 60_000) || null,
          provider_id: selectedProviderId === "default" ? null : selectedProviderId,
        }),
      });
      const result = await response.json() as GenerationResponse & { detail?: string };
      if (!response.ok) throw new Error(result.detail || `生成服務回傳 ${response.status}`);
      setSlides(result.slides);
      setProgress(100);
      window.setTimeout(() => setView("preview"), 450);
    } catch (error) {
      const message = error instanceof TypeError
        ? "無法連線 FastAPI。請確認 http://localhost:8000 已啟動。"
        : error instanceof Error ? error.message : "生成簡報時發生錯誤";
      setGenerationError(message);
    }
  };

  const changeView = (next: View) => {
    if (next !== "generating" && next !== "preview") setView(next);
  };

  return (
    <div className="app-shell">
      <SideNavigation view={view} onChange={changeView} />
      <div className="app-content">
        {view !== "preview" && <AppHeader onCreate={() => setView("create")} />}
        {view === "create" && <CreateView topic={topic} setTopic={setTopic} files={files} setFiles={setFiles} template={template} setTemplate={setTemplate} language={language} setLanguage={setLanguage} slideCount={slideCount} setSlideCount={setSlideCount} providerOptions={providerOptions} selectedProviderId={selectedProviderId} setSelectedProviderId={setSelectedProviderId} onGenerate={startGeneration} />}
        {view === "generating" && <GeneratingView progress={progress} error={generationError} onBack={() => setView("create")} />}
        {view === "preview" && <PreviewView topic={topic} slides={slides} onBack={() => setView("create")} />}
        {view === "library" && <LibraryView onCreate={() => setView("create")} />}
        {view === "settings" && <SettingsView providerOptions={providerOptions} reloadProviderOptions={reloadProviderOptions} />}
      </div>
    </div>
  );
}
