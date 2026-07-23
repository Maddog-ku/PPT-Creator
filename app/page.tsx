"use client";

import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronDown,
  CircleHelp,
  Clock3,
  Copy,
  Download,
  FileText,
  FolderOpen,
  Fullscreen,
  GripVertical,
  History,
  LayoutTemplate,
  Languages,
  LoaderCircle,
  KeyRound,
  Moon,
  MonitorUp,
  PlugZap,
  Plus,
  Play,
  RefreshCcw,
  RotateCcw,
  Search,
  Save,
  Settings,
  Sparkles,
  Sun,
  Trash2,
  UploadCloud,
  WandSparkles,
  X,
} from "lucide-react";
import type { CSSProperties, ChangeEvent, DragEvent, FormEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  isGenerationJobRetryable,
  jobCenterRefreshIntervalMs,
  shouldAutoOpenGenerationResult,
} from "./job-center";
import { elapsedSeconds, formatDuration } from "./generation-timing";
import {
  buildPresentationPptx,
  comparisonFrom,
  itemsFrom,
  metricFrom,
  pointsFrom,
} from "./presentation-builder";
import type { SlideData } from "./presentation-builder";
import {
  presentationThemes,
  templateCatalog,
} from "./templates";
import type { TemplateId } from "./templates";
import {
  defaultPreferences,
  readPreferences,
  translate,
  writePreferences,
} from "./preferences";
import type { AppLocale, AppPreferences } from "./preferences";

type View = "create" | "generating" | "outline" | "editor" | "preview" | "library" | "jobs" | "settings";

type ProviderKind = "ollama" | "openai" | "anthropic" | "gemini" | "openai_compatible" | "stable_diffusion";

type AIProviderResponse = {
  provider: string;
  model: string;
  image_model?: string | null;
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
  imageModel?: string | null;
};

type ProviderDraft = {
  name: string;
  provider: ProviderKind;
  baseUrl: string;
  model: string;
  apiKey: string;
  imageModel: string;
};

type PresentationRecord = {
  id: string;
  language: string;
  title: string;
  status: "DRAFT" | "PARSING" | "GENERATING_CONTENT" | "RENDERING" | "PREVIEW_READY" | "COMPLETED" | "FAILED";
  slide_count: number;
  updated_at: string;
  template: TemplateId;
  has_output: boolean;
  revision: number;
  last_rendered_revision: number | null;
  has_unrendered_changes: boolean;
  failed_stage: string | null;
  last_error: string | null;
  can_retry: boolean;
};

type SourceExtractionItem = {
  filename: string;
  status: "success" | "error";
  char_count: number;
  error?: string | null;
};

type RenderAssets = {
  preview_urls: string[];
  pptx_url: string;
  pdf_url: string;
};

type OutlineItem = {
  id: string;
  eyebrow: string;
  title: string;
  objective: string;
  kind: SlideData["kind"];
};

type PresentationOutline = {
  title: string;
  language: string;
  items: OutlineItem[];
};

type GenerationJob = {
  id: string;
  presentation_id: string;
  job_type: "outline" | "content";
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELED";
  stage: string;
  progress: number;
  cancel_requested: boolean;
  error?: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
  estimated_duration_seconds: number;
  estimated_remaining_seconds: number;
};

type GenerationJobSummary = GenerationJob & {
  presentation_title: string;
  presentation_status: PresentationRecord["status"];
  can_retry: boolean;
};

type ActiveJob = {
  id: string;
  presentationId: string;
  kind: "outline" | "content";
};

type PresentationDetail = PresentationRecord & {
  content: { title: string; language: string; slides: SlideData[] } | null;
  outline: PresentationOutline | null;
  preview_urls: string[];
  pptx_url: string | null;
  pdf_url: string | null;
  confirmed_at?: string | null;
};

type PresentationVersionRecord = {
  id: string;
  revision: number;
  title: string;
  language: string;
  template: TemplateId;
  change_reason: string;
  created_at: string;
  slide_count: number;
};

type PresentationVersionDetail = PresentationVersionRecord & {
  content: { title: string; language: string; slides: SlideData[] };
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

const providerLabels: Record<ProviderKind, string> = {
  ollama: "本機 API",
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Google Gemini",
  openai_compatible: "OpenAI 相容 API",
  stable_diffusion: "本機 Stable Diffusion",
};

const providerBaseUrls: Record<ProviderKind, string> = {
  ollama: "http://host.docker.internal:11434",
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com/v1",
  gemini: "https://generativelanguage.googleapis.com/v1beta",
  openai_compatible: "http://host.docker.internal:1234/v1",
  stable_diffusion: "http://host.docker.internal:7860",
};

const isTextProvider = (provider: AIProviderOption) => provider.provider !== "stable_diffusion";
const isImageProvider = (provider: AIProviderOption) => (
  (provider.provider === "ollama" && Boolean(provider.imageModel))
  || provider.provider === "stable_diffusion"
  || provider.provider === "openai"
  || (provider.provider === "openai_compatible" && Boolean(provider.imageModel))
);

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
      imageModel: provider.image_model,
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
      image_model: string | null;
    }>;
    options.push(...providers.map((provider) => ({
      id: provider.id,
      name: provider.name,
      provider: provider.provider,
      model: provider.model,
      baseUrl: provider.base_url,
      hasApiKey: provider.has_api_key,
      imageModel: provider.image_model,
    })));
  }
  return options;
}

const templates = templateCatalog;

function makeSlides(topic: string): SlideData[] {
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

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <span />
      <span />
    </span>
  );
}

function SideNavigation({ view, compact, locale, onChange }: { view: View; compact: boolean; locale: AppLocale; onChange: (view: View) => void }) {
  const tr = (text: string) => translate(locale, text);
  const items = [
    { id: "create" as const, label: tr("建立簡報"), icon: Plus },
    { id: "library" as const, label: tr("我的簡報"), icon: FolderOpen },
    { id: "jobs" as const, label: tr("任務中心"), icon: Clock3 },
    { id: "settings" as const, label: tr("設定"), icon: Settings },
  ];

  return (
    <aside className={`side-navigation ${compact ? "compact" : ""}`} aria-label={tr(compact ? "主要導覽（已收合）" : "主要導覽")}>
      <button className="side-logo" onClick={() => onChange("create")} aria-label="PPT Creator 首頁">
        <BrandMark />
      </button>
      <nav>
        {items.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={view === id || (["generating", "outline", "editor", "preview"].includes(view) && id === "create") ? "active" : ""}
            onClick={() => onChange(id)}
            aria-label={label}
            title={label}
          >
            <Icon size={20} strokeWidth={1.9} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <button className="side-help" aria-label={tr("使用說明")} title={tr("使用說明")}>
        <CircleHelp size={20} />
      </button>
    </aside>
  );
}

function AppHeader({ locale, onCreate }: { locale: AppLocale; onCreate: () => void }) {
  const tr = (text: string) => translate(locale, text);
  return (
    <header className="app-header">
      <div className="mobile-brand">
        <BrandMark />
        <strong>PPT Creator</strong>
      </div>
      <div className="header-actions">
        <button className="icon-button" aria-label={tr("搜尋")}>
          <Search size={19} />
        </button>
        <button className="quiet-button" onClick={onCreate}>
          <Plus size={17} />
          {tr("新增簡報")}
        </button>
        <button className="avatar" aria-label={tr("使用者選單")}>DC</button>
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
  customSlideCount,
  setCustomSlideCount,
  providerOptions,
  selectedProviderId,
  setSelectedProviderId,
  generateImages,
  setGenerateImages,
  imageProviderId,
  setImageProviderId,
  sourceStatuses,
  locale,
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
  slideCount: string;
  setSlideCount: (count: string) => void;
  customSlideCount: boolean;
  setCustomSlideCount: (custom: boolean) => void;
  providerOptions: AIProviderOption[];
  selectedProviderId: string;
  setSelectedProviderId: (id: string) => void;
  generateImages: boolean;
  setGenerateImages: (value: boolean) => void;
  imageProviderId: string;
  setImageProviderId: (id: string) => void;
  sourceStatuses: Record<string, SourceExtractionItem>;
  locale: AppLocale;
  onGenerate: (event: FormEvent<HTMLFormElement>) => Promise<void>;
}) {
  const tr = (text: string) => translate(locale, text);
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
        <div className="eyebrow"><WandSparkles size={15} /> {tr("AI 簡報工作室")}</div>
        <h1>{tr("讓每個想法")}<br /><span>{tr("都值得被看見")}</span></h1>
        <p>{tr("輸入主題或加入參考資料，我們會先整理架構，再讓你逐頁確認完整成果。")}</p>
        <div className="trust-row" aria-label={tr("產品特點")}>
          <span><Check size={14} /> {tr("可編輯 PPTX")}</span>
          <span><Check size={14} /> {tr("下載前完整預覽")}</span>
          <span><Check size={14} /> {tr("支援本地模型")}</span>
        </div>
      </section>

      <form className="creator-card" onSubmit={onGenerate}>
        <div className="step-label"><span>1</span> {tr("告訴我們簡報要說什麼")}</div>
        <label className="field-label" htmlFor="presentation-topic">{tr("簡報主題與需求")}</label>
        <div className="topic-field">
          <textarea
            id="presentation-topic"
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder={tr("例如：為管理團隊製作一份 2026 年產品策略提案，重點放在市場機會、三項優先計畫與執行時程。")}
            rows={5}
            required
          />
          <span className="character-count">{topic.length} / 1,500</span>
        </div>

        <label className="field-label">{tr("參考資料")} <small>{tr("選填，最多 8 個檔案")}</small></label>
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
            accept=".pdf,.pptx,.txt,.md"
            onChange={handleFiles}
            aria-label={tr("選擇參考檔案")}
          />
          <span className="upload-icon"><UploadCloud size={22} /></span>
          <div><strong>{tr("拖曳檔案到這裡")}</strong><small>{tr("或點擊選擇 PDF、PPTX、TXT")}</small></div>
        </div>

        {files.length > 0 && (
          <ul className="file-list" aria-label={tr("已加入的檔案")}>
            {files.map((file) => (
              <li key={`${file.name}-${file.size}`}>
                <FileText size={17} />
                <span>
                  <strong>{file.name}</strong>
                  <small>{Math.max(1, Math.round(file.size / 1024))} KB</small>
                  {sourceStatuses[file.name] && (
                    <small className={`source-status ${sourceStatuses[file.name].status}`}>
                      {sourceStatuses[file.name].status === "success"
                        ? `已解析 ${sourceStatuses[file.name].char_count.toLocaleString()} 字元`
                        : sourceStatuses[file.name].error || tr("解析失敗")}
                    </small>
                  )}
                </span>
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
            <span className="field-label">{tr("簡報語言")}</span>
            <select value={language} onChange={(event) => setLanguage(event.target.value)}>
              <option value="zh-TW">{tr("繁體中文")}</option>
              <option value="en">English</option>
              <option value="ja">日本語</option>
            </select>
          </label>
          <label>
            <span className="field-label">{tr("預計頁數")}</span>
            <select
              value={customSlideCount ? "custom" : slideCount}
              onChange={(event) => {
                if (event.target.value === "custom") {
                  setCustomSlideCount(true);
                  setSlideCount("");
                } else {
                  setCustomSlideCount(false);
                  setSlideCount(event.target.value);
                }
              }}
            >
              <option value="6">{tr("約 6 頁")}</option>
              <option value="10">{tr("約 10 頁")}</option>
              <option value="15">{tr("約 15 頁")}</option>
              <option value="20">{tr("約 20 頁")}</option>
              <option value="custom">{tr("自訂頁數")}</option>
            </select>
            {customSlideCount && (
              <span className="custom-slide-count">
                <input
                  type="number"
                  min="3"
                  max="50"
                  step="1"
                  value={slideCount}
                  onChange={(event) => setSlideCount(event.target.value)}
                  placeholder="3–50"
                  aria-label={tr("自訂頁數")}
                  required
                />
                <span>{tr("頁")}</span>
              </span>
            )}
          </label>
        </div>

        <label className="provider-select">
          <span className="field-label">{tr("使用的 AI 模型")}</span>
          <select
            value={selectedProviderId}
            onChange={(event) => setSelectedProviderId(event.target.value)}
            disabled={providerOptions.every((provider) => !isTextProvider(provider))}
          >
            {providerOptions.every((provider) => !isTextProvider(provider)) ? (
              <option value="default">{tr("請先到設定新增 AI API")}</option>
            ) : providerOptions.filter(isTextProvider).map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.name} · {provider.model}
              </option>
            ))}
          </select>
          <small>{tr("可在設定中加入更多本機或雲端模型 API。")}</small>
        </label>

        <div className="image-generation-field">
          <label className="image-toggle">
            <input
              type="checkbox"
              checked={generateImages}
              onChange={(event) => setGenerateImages(event.target.checked)}
            />
            <span><strong>{tr("在簡報中生成圖片")}</strong><small>{tr("優先使用本機圖片 API，最多生成 2 張，避免雲端費用。")}</small></span>
          </label>
          {generateImages && (
            <label className="provider-select image-provider-select">
              <span className="field-label">{tr("圖片生成模型")}</span>
              <select value={imageProviderId} onChange={(event) => setImageProviderId(event.target.value)} required>
                <option value="">{tr("請選擇圖片模型")}</option>
                {providerOptions.filter(isImageProvider).map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name} · {provider.provider === "ollama" ? `${provider.imageModel}・本機免額度` : provider.provider === "stable_diffusion" ? "本機生成・免雲端額度" : `${provider.imageModel || `${provider.model} 圖片工具`}・雲端可能計費`}
                  </option>
                ))}
              </select>
              {providerOptions.every((provider) => !isImageProvider(provider)) && <small>{tr("請先到設定新增本機 Stable Diffusion API。")}</small>}
            </label>
          )}
        </div>

        <fieldset className="template-picker">
          <legend className="field-label">{tr("選擇視覺風格")}</legend>
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
                <span><strong>{tr(item.name)}</strong><small>{tr(item.description)}</small></span>
                {template === item.id && <Check className="template-check" size={15} />}
              </label>
            ))}
          </div>
        </fieldset>

        <button className="primary-button generate-button" type="submit">
          {tr("先產生簡報大綱")}
          <ArrowRight size={18} />
        </button>
        <p className="form-note">{tr("先在網站完整確認每一頁，確認後才會開放下載。")}</p>
      </form>
    </main>
  );
}

function GeneratingView({
  progress,
  error,
  sourceStatuses,
  locale,
  estimatedRemainingSeconds,
  startedAt,
  onBack,
  onCancel,
  stage,
}: {
  progress: number;
  error: string | null;
  sourceStatuses: Record<string, SourceExtractionItem>;
  locale: AppLocale;
  estimatedRemainingSeconds: number | null;
  startedAt: string | null;
  onBack: () => void;
  onCancel: () => void;
  stage: string;
}) {
  const tr = (text: string) => translate(locale, text);
  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => {
    if (error || progress >= 100) return;
    const timer = window.setInterval(() => setClock(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [error, progress]);
  const elapsed = elapsedSeconds(startedAt, clock);
  const stages = [
    { label: tr("分析內容與參考資料"), at: 10 },
    { label: tr("整理簡報敘事架構"), at: 35 },
    { label: tr("建立逐頁內容"), at: 58 },
    { label: tr("套用版型並檢查版面"), at: 82 },
  ];

  return (
    <main className="generating-view" aria-live="polite">
      <div className="generation-orbit" aria-hidden="true">
        <span /><span /><WandSparkles size={30} />
      </div>
      <p className="eyebrow">{tr("正在製作你的簡報")}</p>
      <h1>{tr(error ? "無法完成這次生成" : "把內容變成清楚的故事")}</h1>
      <p>{error ?? tr("AI 服務正在整理重點、安排順序，並為每一頁選擇合適的版面。")}</p>
      <div className="progress-card">
        <div className="progress-heading"><strong>{progress}%</strong><span>{error ? tr("請檢查本機服務") : tr(stage || "等待背景任務")}</span></div>
        <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
        {!error && (
          <div className="generation-estimate" aria-live="polite">
            <div><span>{tr("預估剩餘時間")}</span><strong>{estimatedRemainingSeconds === null ? tr("正在計算") : formatDuration(estimatedRemainingSeconds, locale)}</strong></div>
            <div><span>{tr("已經過時間")}</span><strong>{formatDuration(elapsed, locale)}</strong></div>
            <p><Sparkles size={13} /> {tr("時間會依模型、頁數與硬體速度動態調整，任務結束後會自動釋放本機模型資源")}</p>
          </div>
        )}
        {error ? (
          <div className="generation-error">
            <strong>{tr("請確認後端 API 與 AI 服務都已啟動")}</strong>
            <button className="quiet-button" onClick={onBack}>{tr("返回設定")}</button>
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
        {!error && <button className="quiet-button generation-cancel" onClick={onCancel}>{tr("取消這次生成")}</button>}
        {Object.values(sourceStatuses).length > 0 && (
          <div className="generation-sources">
            <strong>{tr("參考資料解析結果")}</strong>
            {Object.values(sourceStatuses).map((item) => (
              <span className={item.status} key={item.filename}>
                {item.status === "success" ? <Check size={13} /> : <X size={13} />}
                {item.filename} · {item.status === "success" ? `${item.char_count.toLocaleString()} 字元` : item.error || "解析失敗"}
              </span>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

function OutlineView({ outline, locale, onConfirm, onBack }: { outline: PresentationOutline; locale: AppLocale; onConfirm: (outline: PresentationOutline) => Promise<void>; onBack: () => void }) {
  const tr = (text: string) => translate(locale, text);
  const [draft, setDraft] = useState(outline);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateItem = (index: number, changes: Partial<OutlineItem>) => {
    setDraft((current) => ({ ...current, items: current.items.map((item, itemIndex) => itemIndex === index ? { ...item, ...changes } : item) }));
  };

  const moveItem = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 1 || target >= draft.items.length - 1) return;
    setDraft((current) => {
      const items = [...current.items];
      [items[index], items[target]] = [items[target], items[index]];
      return { ...current, items };
    });
  };

  const addItem = () => {
    if (draft.items.length >= 50) return;
    setDraft((current) => {
      const items = [...current.items];
      items.splice(items.length - 1, 0, {
        id: crypto.randomUUID(),
        eyebrow: `${String(items.length).padStart(2, "0")} / 新章節`,
        title: "新的內容頁",
        objective: "說明這一頁希望觀眾理解的重點",
        kind: "cards",
      });
      return { ...current, items };
    });
  };

  const removeItem = (index: number) => {
    if (index === 0 || index === draft.items.length - 1 || draft.items.length <= 3) return;
    setDraft((current) => ({ ...current, items: current.items.filter((_, itemIndex) => itemIndex !== index) }));
  };

  const confirm = async () => {
    setSaving(true);
    setError(null);
    try {
      await onConfirm(draft);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "無法儲存大綱");
      setSaving(false);
    }
  };

  return (
    <main className="outline-view">
      <header className="outline-header">
        <button className="quiet-button" onClick={onBack}><ArrowLeft size={17} /> {tr("返回建立頁")}</button>
        <div><p className="eyebrow">{tr("生成前確認")}</p><h1>{tr("先把故事架構排好")}</h1><p>{tr("調整標題、順序與每頁目的，確認後才會生成完整內容。")}</p></div>
        <div className="outline-summary"><strong>{draft.items.length}</strong><span>{tr("頁簡報")}</span></div>
      </header>
      <section className="outline-title-card">
        <label><span>{tr("簡報名稱")}</span><input value={draft.title} maxLength={180} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
      </section>
      <section className="outline-list" aria-label={tr("簡報大綱")}>
        {draft.items.map((item, index) => {
          const fixed = index === 0 || index === draft.items.length - 1;
          return (
            <article className="outline-item" key={item.id}>
              <div className="outline-number">{String(index + 1).padStart(2, "0")}</div>
              <div className="outline-fields">
                <div className="outline-field-row">
                  <label><span>{tr("眉標")}</span><input value={item.eyebrow} maxLength={80} onChange={(event) => updateItem(index, { eyebrow: event.target.value })} /></label>
                  <label><span>{tr("頁型")}</span><select value={item.kind} disabled={fixed} onChange={(event) => updateItem(index, { kind: event.target.value as SlideData["kind"] })}>{slideKindOptions.map((option) => <option value={option.value} key={option.value}>{tr(option.label)}</option>)}</select></label>
                </div>
                <label><span>{tr("頁面標題")}</span><input value={item.title} maxLength={120} onChange={(event) => updateItem(index, { title: event.target.value })} /></label>
                <label><span>{tr("這一頁要傳達什麼")}</span><textarea value={item.objective} maxLength={300} rows={2} onChange={(event) => updateItem(index, { objective: event.target.value })} /></label>
              </div>
              <div className="outline-actions">
                <button onClick={() => moveItem(index, -1)} disabled={fixed || index === 1} aria-label={`將第 ${index + 1} 頁上移`}><ChevronUp size={16} /></button>
                <button onClick={() => moveItem(index, 1)} disabled={fixed || index === draft.items.length - 2} aria-label={`將第 ${index + 1} 頁下移`}><ChevronDown size={16} /></button>
                <button className="danger-button" onClick={() => removeItem(index)} disabled={fixed || draft.items.length <= 3} aria-label={`刪除第 ${index + 1} 頁`}><Trash2 size={16} /></button>
              </div>
            </article>
          );
        })}
      </section>
      <footer className="outline-footer">
        <button className="quiet-button" onClick={addItem} disabled={draft.items.length >= 50}><Plus size={16} /> {tr("新增內容頁")}</button>
        <div>{error && <span className="outline-error">{error}</span>}<button className="primary-button" onClick={() => void confirm()} disabled={saving || !draft.title.trim()}>{saving ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}{tr(saving ? "正在建立任務" : "確認大綱並生成內容")}</button></div>
      </footer>
    </main>
  );
}

function SlideCanvas({ slide, topic, template = "editorial", index = 0, compact = false, animate = false }: { slide: SlideData; topic: string; template?: TemplateId; index?: number; compact?: boolean; animate?: boolean }) {
  const points = pointsFrom(slide.body);
  const structuredItems = itemsFrom(slide);
  const structuredMetric = metricFrom(slide);
  const structuredComparison = comparisonFrom(slide);
  const theme = presentationThemes[template];
  const bodyFallback = theme.font.includes("Serif") ? "serif" : "sans-serif";
  const headingFallback = theme.headingFont.includes("Serif") ? "serif" : "sans-serif";
  const themeStyle = {
    "--slide-bg": `#${theme.background}`,
    "--slide-surface": `#${theme.surface}`,
    "--slide-text": `#${theme.text}`,
    "--slide-muted": `#${theme.muted}`,
    "--slide-accent": `#${theme.accent}`,
    "--slide-accent-2": `#${theme.accent2}`,
    "--slide-accent-soft": `#${theme.accentSoft}`,
    "--slide-line": `#${theme.line}`,
    "--slide-on-accent": `#${theme.onAccent}`,
    "--slide-font": `"${theme.font}", ${bodyFallback}`,
    "--slide-heading-font": `"${theme.headingFont}", ${headingFallback}`,
  } as CSSProperties;
  const variant = index % 3;
  return (
    <div
      className={`slide-canvas slide-${slide.kind} variant-${variant} ${slide.image_data ? "has-image" : ""} ${compact ? "compact" : ""} ${animate ? "animate-slide" : ""}`}
      data-template={template}
      style={themeStyle}
    >
      <div className="slide-chrome">
        <BrandMark />
        <span>PPT CREATOR</span>
      </div>
      {slide.image_data && (
        <div className="slide-ai-visual">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={slide.image_data} alt="AI 生成的投影片視覺" />
        </div>
      )}
      {slide.kind === "cover" && (
        <>
          <div className="slide-glow" />
          <div className="slide-copy">
            <span className="slide-eyebrow">{slide.eyebrow}</span>
            <h2>{slide.title || topic}</h2>
            <p>{slide.body}</p>
          </div>
          <div className="cover-index">01</div>
        </>
      )}
      {slide.kind === "section" && (
        <div className="section-slide-layout">
          <div className="section-number">{String(index + 1).padStart(2, "0")}</div>
          <div className="section-slide-copy"><span className="slide-eyebrow">{slide.eyebrow}</span><h2>{slide.title}</h2><p>{slide.body}</p></div>
          <div className="section-stripes"><i /><i /><i /></div>
        </div>
      )}
      {slide.kind === "cards" && (
        <div className="slide-layout">
          <span className="slide-eyebrow">{slide.eyebrow}</span>
          <h2>{slide.title}</h2>
          <div className="insight-cards">
            {structuredItems.map((item, pointIndex) => (
              <div key={`${item.label}-${pointIndex}`}><span>{item.label}</span><strong>{item.title}</strong><p>{item.body}</p></div>
            ))}
          </div>
        </div>
      )}
      {slide.kind === "split" && (
        <div className="slide-layout split-layout">
          <div className="split-copy"><span className="slide-eyebrow">{slide.eyebrow}</span><h2>{slide.title}</h2><p>{slide.body}</p></div>
          <div className="split-panel">
            <span>FOCUS</span><strong>{points[0]}</strong>
            <div>{points.slice(1).map((point, pointIndex) => <small key={`${point}-${pointIndex}`}><b>{String(pointIndex + 2).padStart(2, "0")}</b>{point}</small>)}</div>
          </div>
        </div>
      )}
      {slide.kind === "metric" && (
        <div className="slide-layout metric-layout">
          <div><span className="slide-eyebrow">{slide.eyebrow}</span><h2>{slide.title}</h2><p>{structuredMetric.context}</p></div>
          <div className="big-metric"><strong>{structuredMetric.value}</strong><span>{structuredMetric.label}</span><i><b /></i></div>
        </div>
      )}
      {slide.kind === "comparison" && (
        <div className="slide-layout comparison-layout">
          <span className="slide-eyebrow">{slide.eyebrow}</span><h2>{slide.title}</h2>
          <div className="comparison-grid">
            <div><span>{structuredComparison.left.label}</span><strong>{structuredComparison.left.title}</strong><p>{structuredComparison.left.body}</p></div>
            <div><span>{structuredComparison.right.label}</span><strong>{structuredComparison.right.title}</strong><p>{structuredComparison.right.body}</p></div>
          </div>
          <div className="comparison-callout"><b>→</b><span>{structuredComparison.callout}</span></div>
        </div>
      )}
      {slide.kind === "roadmap" && (
        <div className="slide-layout roadmap-layout">
          <span className="slide-eyebrow">{slide.eyebrow}</span>
          <h2>{slide.title}</h2>
          <div className="roadmap-line">
            {structuredItems.map((item, itemIndex) => (
              <div key={`${item.label}-${itemIndex}`}><span>{item.label}</span><strong>{item.title}</strong><small>{item.body}</small></div>
            ))}
          </div>
        </div>
      )}
      {slide.kind === "quote" && (
        <div className="quote-layout">
          <span className="quote-mark">“</span>
          <span className="slide-eyebrow">{slide.eyebrow}</span>
          <h2>{slide.title}</h2>
          <div><i /><p>{slide.body}</p></div>
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

function resolveApiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  try {
    return `${new URL(apiBaseUrl).origin}${path}`;
  } catch {
    return path;
  }
}

const slideKindOptions: Array<{ value: SlideData["kind"]; label: string }> = [
  { value: "cover", label: "封面" },
  { value: "section", label: "章節轉場" },
  { value: "cards", label: "重點卡片" },
  { value: "split", label: "左右圖文" },
  { value: "metric", label: "數據焦點" },
  { value: "comparison", label: "雙欄比較" },
  { value: "roadmap", label: "執行路徑" },
  { value: "quote", label: "關鍵引言" },
  { value: "closing", label: "結尾" },
];

function EditorView({
  topic,
  slides,
  template,
  presentationId,
  locale,
  onSave,
  onRestore,
  onCancel,
}: {
  topic: string;
  slides: SlideData[];
  template: TemplateId;
  presentationId: string | null;
  locale: AppLocale;
  onSave: (topic: string, slides: SlideData[]) => Promise<void>;
  onRestore: (revision: number) => Promise<void>;
  onCancel: () => void;
}) {
  const tr = (text: string) => translate(locale, text);
  const [draftTopic, setDraftTopic] = useState(topic);
  const [draftSlides, setDraftSlides] = useState(slides);
  const [active, setActive] = useState(0);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [versions, setVersions] = useState<PresentationVersionRecord[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<PresentationVersionDetail | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [initialSnapshot] = useState(() => JSON.stringify({ topic, slides }));
  const dirty = JSON.stringify({ topic: draftTopic, slides: draftSlides }) !== initialSnapshot;
  const activeSlide = draftSlides[active];

  useEffect(() => {
    const warnBeforeLeaving = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeLeaving);
    return () => window.removeEventListener("beforeunload", warnBeforeLeaving);
  }, [dirty]);

  const updateActiveSlide = (changes: Partial<SlideData>) => {
    setDraftSlides((current) => current.map((slide, index) => index === active ? { ...slide, ...changes } : slide));
  };

  const updateActiveItem = (itemIndex: number, changes: Partial<ReturnType<typeof itemsFrom>[number]>) => {
    if (!activeSlide) return;
    const items = itemsFrom(activeSlide).map((item, index) => (
      index === itemIndex ? { ...item, ...changes } : item
    ));
    updateActiveSlide({ items });
  };

  const updateActiveMetric = (changes: Partial<ReturnType<typeof metricFrom>>) => {
    if (!activeSlide) return;
    updateActiveSlide({ metric: { ...metricFrom(activeSlide), ...changes } });
  };

  const updateActiveComparison = (
    side: "left" | "right" | "callout",
    changes: string | Partial<ReturnType<typeof comparisonFrom>["left"]>,
  ) => {
    if (!activeSlide) return;
    const comparison = comparisonFrom(activeSlide);
    updateActiveSlide({
      comparison: side === "callout"
        ? { ...comparison, callout: changes as string }
        : { ...comparison, [side]: { ...comparison[side], ...(changes as object) } },
    });
  };

  const moveSlide = (from: number, to: number) => {
    if (to < 0 || to >= draftSlides.length || from === to) return;
    setDraftSlides((current) => {
      const next = [...current];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
    setActive(to);
  };

  const addSlide = () => {
    if (draftSlides.length >= 50) return;
    const nextSlide: SlideData = {
      id: crypto.randomUUID(),
      eyebrow: `${String(active + 2).padStart(2, "0")} / 新增內容`,
      title: "輸入這一頁的核心標題",
      body: "在這裡補充支持標題的內容，讓這一頁只傳達一個清楚重點。",
      kind: "cards",
      visual_prompt: null,
      image_data: null,
    };
    const insertAt = active + 1;
    setDraftSlides((current) => [...current.slice(0, insertAt), nextSlide, ...current.slice(insertAt)]);
    setActive(insertAt);
  };

  const duplicateSlide = () => {
    if (!activeSlide || draftSlides.length >= 50) return;
    const duplicate = { ...activeSlide, id: crypto.randomUUID(), title: `${activeSlide.title}（副本）` };
    const insertAt = active + 1;
    setDraftSlides((current) => [...current.slice(0, insertAt), duplicate, ...current.slice(insertAt)]);
    setActive(insertAt);
  };

  const deleteSlide = () => {
    if (draftSlides.length <= 3) return;
    setDraftSlides((current) => current.filter((_, index) => index !== active));
    setActive((current) => Math.min(current, draftSlides.length - 2));
  };

  const cancelEditing = () => {
    if (dirty && !window.confirm(locale === "en" ? "You have unsaved changes. Leave anyway?" : "尚有未儲存的修改，確定要離開嗎？")) return;
    onCancel();
  };

  const saveChanges = async () => {
    if (!dirty || !draftTopic.trim()) return;
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(draftTopic.trim(), draftSlides);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "無法儲存簡報內容");
      setSaving(false);
    }
  };

  const loadVersionDetail = async (revision: number) => {
    if (!presentationId) return;
    setHistoryError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/presentations/${presentationId}/versions/${revision}`);
      const result = await response.json() as PresentationVersionDetail & { detail?: string };
      if (!response.ok) throw new Error(result.detail || "無法讀取版本內容");
      setSelectedVersion(result);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "無法讀取版本內容");
    }
  };

  const openHistory = async () => {
    if (!presentationId) return;
    setShowHistory(true);
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/presentations/${presentationId}/versions`);
      const result = await response.json() as PresentationVersionRecord[] | { detail?: string };
      if (!response.ok || !Array.isArray(result)) {
        throw new Error(!Array.isArray(result) && result.detail ? result.detail : "無法讀取版本紀錄");
      }
      setVersions(result);
      if (result.length) await loadVersionDetail(result[0].revision);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "無法讀取版本紀錄");
    } finally {
      setHistoryLoading(false);
    }
  };

  const restoreVersion = async () => {
    if (!selectedVersion) return;
    const warning = dirty
      ? "目前尚有未儲存修改，還原版本會捨棄這些修改。確定繼續嗎？"
      : `確定要還原到版本 ${selectedVersion.revision} 嗎？系統會另外建立一個新版本。`;
    if (!window.confirm(warning)) return;
    setRestoring(true);
    setHistoryError(null);
    try {
      await onRestore(selectedVersion.revision);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "無法還原版本");
      setRestoring(false);
    }
  };

  const versionReasonLabels: Record<string, string> = {
    generated: "AI 初次生成",
    content_saved: "內容修改",
    duplicated: "建立副本",
    generation_retried: "生成重試",
  };

  return (
    <main className="editor-view">
      <header className="editor-toolbar">
        <button className="quiet-button" onClick={cancelEditing}><ArrowLeft size={17} /> {tr("返回預覽")}</button>
        <div className="editor-title">
          <strong>{tr("簡報編輯工作台")}</strong>
          <span className={dirty ? "dirty" : "saved"}>{tr(dirty ? "有未儲存修改" : "內容已儲存")}</span>
        </div>
        <div className="editor-toolbar-actions">
          <button className="quiet-button" onClick={() => void openHistory()} disabled={!presentationId}><History size={16} /> {tr("版本紀錄")}</button>
          <button className="primary-button" onClick={() => void saveChanges()} disabled={!dirty || saving || !draftTopic.trim()}>
            {saving ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />}
            {tr(saving ? "正在更新預覽" : "儲存並更新預覽")}
          </button>
        </div>
      </header>

      <div className="editor-workspace">
        <aside className="editor-slide-list" aria-label={tr("可編輯投影片列表")}>
          <div className="editor-list-heading"><span>{tr("投影片")}</span><strong>{draftSlides.length} / 50</strong></div>
          {draftSlides.map((slide, index) => (
            <div
              className={`editor-thumbnail ${active === index ? "active" : ""}`}
              draggable
              key={slide.id}
              onDragStart={() => setDraggedIndex(index)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => {
                if (draggedIndex !== null) moveSlide(draggedIndex, index);
                setDraggedIndex(null);
              }}
            >
              <button className="thumbnail-select" onClick={() => setActive(index)} aria-label={`編輯第 ${index + 1} 頁`}>
                <span>{index + 1}</span>
                <div><SlideCanvas slide={slide} topic={draftTopic} template={template} index={index} compact /></div>
              </button>
              <GripVertical size={14} aria-hidden="true" />
            </div>
          ))}
          <button className="editor-add-slide" onClick={addSlide} disabled={draftSlides.length >= 50}><Plus size={15} /> {tr("新增投影片")}</button>
        </aside>

        <section className="editor-stage">
          <div className="editor-stage-meta"><span>{tr("即時內容預覽")}</span><span>{locale === "en" ? `Slide ${active + 1}` : `第 ${active + 1} 頁`}</span></div>
          <div className="slide-frame">{activeSlide && <SlideCanvas slide={activeSlide} topic={draftTopic} template={template} index={active} />}</div>
        </section>

        <aside className="editor-panel">
          <div className="editor-panel-heading">
            <div><p className="eyebrow">PAGE {String(active + 1).padStart(2, "0")}</p><h2>{tr("編輯投影片內容")}</h2></div>
            <div className="editor-order-actions">
              <button onClick={() => moveSlide(active, active - 1)} disabled={active === 0} aria-label={tr("向前移動")}><ChevronUp size={16} /></button>
              <button onClick={() => moveSlide(active, active + 1)} disabled={active === draftSlides.length - 1} aria-label={tr("向後移動")}><ChevronDown size={16} /></button>
            </div>
          </div>

          <label className="editor-field"><span>{tr("簡報名稱")}</span><input value={draftTopic} maxLength={180} onChange={(event) => setDraftTopic(event.target.value)} /></label>
          {activeSlide && (
            <>
              <label className="editor-field"><span>{tr("頁面類型")}</span><select value={activeSlide.kind} onChange={(event) => updateActiveSlide({ kind: event.target.value as SlideData["kind"], items: undefined, metric: null, comparison: null })}>{slideKindOptions.map((item) => <option value={item.value} key={item.value}>{tr(item.label)}</option>)}</select></label>
              <label className="editor-field"><span>{tr("眉標")}</span><input value={activeSlide.eyebrow} maxLength={80} onChange={(event) => updateActiveSlide({ eyebrow: event.target.value })} /><small>{activeSlide.eyebrow.length} / 80</small></label>
              <label className="editor-field"><span>{tr("標題")}</span><textarea value={activeSlide.title} maxLength={120} rows={3} onChange={(event) => updateActiveSlide({ title: event.target.value })} /><small>{activeSlide.title.length} / 120</small></label>
              <label className="editor-field"><span>{tr("內文")}</span><textarea value={activeSlide.body} maxLength={400} rows={7} onChange={(event) => updateActiveSlide({ body: event.target.value })} /><small>{activeSlide.body.length} / 400</small></label>
              {(activeSlide.kind === "cards" || activeSlide.kind === "roadmap") && (
                <div className="editor-structure-section">
                  <div><strong>{tr(activeSlide.kind === "cards" ? "卡片內容" : "階段內容")}</strong><small>{tr("這些欄位會直接呈現在版型中")}</small></div>
                  {itemsFrom(activeSlide).map((item, itemIndex) => (
                    <fieldset key={`${item.label}-${itemIndex}`}>
                      <legend>{tr("項目")} {itemIndex + 1}</legend>
                      <label className="editor-field"><span>{tr("標籤")}</span><input value={item.label} maxLength={40} onChange={(event) => updateActiveItem(itemIndex, { label: event.target.value })} /></label>
                      <label className="editor-field"><span>{tr("小標題")}</span><input value={item.title} maxLength={80} onChange={(event) => updateActiveItem(itemIndex, { title: event.target.value })} /></label>
                      <label className="editor-field"><span>{tr("說明")}</span><textarea value={item.body} maxLength={180} rows={3} onChange={(event) => updateActiveItem(itemIndex, { body: event.target.value })} /></label>
                    </fieldset>
                  ))}
                </div>
              )}
              {activeSlide.kind === "metric" && (
                <div className="editor-structure-section">
                  <div><strong>{tr("數據內容")}</strong><small>{tr("數值必須來自可信資料")}</small></div>
                  <label className="editor-field"><span>{tr("主要數值")}</span><input value={metricFrom(activeSlide).value} maxLength={40} onChange={(event) => updateActiveMetric({ value: event.target.value })} /></label>
                  <label className="editor-field"><span>{tr("數值標籤")}</span><input value={metricFrom(activeSlide).label} maxLength={80} onChange={(event) => updateActiveMetric({ label: event.target.value })} /></label>
                  <label className="editor-field"><span>{tr("補充脈絡")}</span><textarea value={metricFrom(activeSlide).context} maxLength={180} rows={3} onChange={(event) => updateActiveMetric({ context: event.target.value })} /></label>
                </div>
              )}
              {activeSlide.kind === "comparison" && (
                <div className="editor-structure-section">
                  <div><strong>{tr("比較內容")}</strong><small>{tr("左右欄與最後結論")}</small></div>
                  {(["left", "right"] as const).map((side) => {
                    const column = comparisonFrom(activeSlide)[side];
                    return (
                      <fieldset key={side}>
                        <legend>{tr(side === "left" ? "左欄" : "右欄")}</legend>
                        <label className="editor-field"><span>{tr("標籤")}</span><input value={column.label} maxLength={40} onChange={(event) => updateActiveComparison(side, { label: event.target.value })} /></label>
                        <label className="editor-field"><span>{tr("欄位標題")}</span><input value={column.title} maxLength={80} onChange={(event) => updateActiveComparison(side, { title: event.target.value })} /></label>
                        <label className="editor-field"><span>{tr("內容")}</span><textarea value={column.body} maxLength={180} rows={3} onChange={(event) => updateActiveComparison(side, { body: event.target.value })} /></label>
                      </fieldset>
                    );
                  })}
                  <label className="editor-field"><span>{tr("比較結論")}</span><textarea value={comparisonFrom(activeSlide).callout} maxLength={160} rows={3} onChange={(event) => updateActiveComparison("callout", event.target.value)} /></label>
                </div>
              )}
              {activeSlide.image_data && <button className="quiet-button editor-remove-image" onClick={() => updateActiveSlide({ image_data: null })}><Trash2 size={14} /> {tr("移除這頁圖片")}</button>}
            </>
          )}

          <div className="editor-slide-actions">
            <button className="quiet-button" onClick={duplicateSlide} disabled={draftSlides.length >= 50}><Copy size={14} /> {tr("複製此頁")}</button>
            <button className="danger-action" onClick={deleteSlide} disabled={draftSlides.length <= 3}><Trash2 size={14} /> {tr("刪除此頁")}</button>
          </div>
          {saveError && <p className="editor-save-error">{saveError}</p>}
          <p className="editor-help">{tr("文字修改與排序不會呼叫 AI。儲存後才會重新產生正式 PPTX、PDF 與逐頁預覽。")}</p>
        </aside>
      </div>
      {showHistory && (
        <div className="history-backdrop" role="presentation" onMouseDown={() => setShowHistory(false)}>
          <aside className="history-drawer" aria-label={tr("版本紀錄")} onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div><p className="eyebrow">VERSION HISTORY</p><h2>{tr("版本紀錄")}</h2><p>{tr("查看過去內容，還原時不會覆蓋原有版本。")}</p></div>
              <button className="icon-button" onClick={() => setShowHistory(false)} aria-label={tr("關閉版本紀錄")}><X size={18} /></button>
            </header>
            {historyLoading && <p className="history-message"><LoaderCircle className="spin" size={17} /> {tr("正在讀取版本…")}</p>}
            {historyError && <p className="history-message error">{historyError}</p>}
            {!historyLoading && versions.length === 0 && !historyError && <p className="history-message">{tr("目前還沒有版本紀錄。")}</p>}
            <div className="history-content">
              <div className="history-list">
                {versions.map((version) => {
                  const reason = version.change_reason.startsWith("restored_from_")
                    ? `由版本 ${version.change_reason.replace("restored_from_", "")} 還原`
                    : versionReasonLabels[version.change_reason] ?? version.change_reason;
                  return (
                    <button className={selectedVersion?.revision === version.revision ? "active" : ""} key={version.id} onClick={() => void loadVersionDetail(version.revision)}>
                      <span>{tr("版本")} {version.revision}</span>
                      <strong>{reason}</strong>
                      <small>{version.slide_count} 頁 · {new Intl.DateTimeFormat("zh-TW", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(version.created_at))}</small>
                    </button>
                  );
                })}
              </div>
              <div className="history-preview">
                {selectedVersion ? (
                  <>
                    <div className="history-preview-heading"><div><span>{tr("版本")} {selectedVersion.revision}</span><h3>{selectedVersion.title}</h3></div><button className="primary-button" onClick={() => void restoreVersion()} disabled={restoring}>{restoring ? <LoaderCircle className="spin" size={15} /> : <RotateCcw size={15} />}{tr(restoring ? "正在還原" : "還原此版本")}</button></div>
                    <ol>{selectedVersion.content.slides.map((slide, index) => <li key={slide.id}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{slide.title}</strong><small>{slide.eyebrow}</small></div></li>)}</ol>
                  </>
                ) : !historyLoading && <p className="history-message">{tr("選擇版本以查看內容。")}</p>}
              </div>
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}

function PreviewView({
  topic,
  slides,
  presentationId,
  template,
  assets,
  initiallyConfirmed,
  rendering,
  locale,
  onTemplateChange,
  onBack,
}: {
  topic: string;
  slides: SlideData[];
  presentationId: string | null;
  template: TemplateId;
  assets: RenderAssets | null;
  initiallyConfirmed: boolean;
  rendering: boolean;
  locale: AppLocale;
  onTemplateChange: (template: TemplateId) => Promise<void>;
  onBack: () => void;
}) {
  const tr = (text: string) => translate(locale, text);
  const [active, setActive] = useState(0);
  const [confirmed, setConfirmed] = useState(initiallyConfirmed);
  const [animationsEnabled, setAnimationsEnabled] = useState(false);
  const [theaterMode, setTheaterMode] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const previewUrls = assets?.preview_urls ?? [];

  const confirmPresentation = async () => {
    setActionError(null);
    if (presentationId) {
      const response = await fetch(`${apiBaseUrl}/presentations/${presentationId}/confirm`, { method: "POST" });
      if (!response.ok) {
        const result = await response.json() as { detail?: string };
        setActionError(result.detail || "無法確認簡報");
        return;
      }
    }
    setConfirmed(true);
  };

  const switchTemplate = async (nextTemplate: TemplateId) => {
    if (nextTemplate === template) return;
    setActionError(null);
    setConfirmed(false);
    try {
      await onTemplateChange(nextTemplate);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "無法切換模板");
    }
  };

  const toggleFullscreen = () => {
    setTheaterMode((current) => !current);
  };

  return (
    <main className="preview-view">
      <header className="preview-toolbar">
        <button className="quiet-button" onClick={onBack}><ArrowLeft size={17} /> {tr("返回修改")}</button>
        <div className="preview-title"><strong>{topic || tr("未命名簡報")}</strong><span><Check size={13} /> {tr("已完成預覽")}</span></div>
        <div className="preview-actions">
          <label className="preview-template-select">
            <LayoutTemplate size={16} />
            <select value={template} onChange={(event) => void switchTemplate(event.target.value as TemplateId)} disabled={rendering} aria-label={tr("切換簡報模板")}>
              {templates.map((item) => <option value={item.id} key={item.id}>{tr(item.name)}</option>)}
            </select>
          </label>
          <button
            className={`animation-button ${animationsEnabled ? "active" : ""}`}
            onClick={() => setAnimationsEnabled((current) => !current)}
            aria-pressed={animationsEnabled}
            title={tr("切換網站進場動畫與 PPTX 淡入轉場")}
          >
            <Play size={16} /> {tr(animationsEnabled ? "動畫已開啟" : "加入動畫")}
          </button>
          <button className="icon-button" onClick={toggleFullscreen} aria-label={tr(theaterMode ? "退出全螢幕" : "全螢幕預覽")} title={tr(theaterMode ? "退出全螢幕" : "全螢幕預覽")}><Fullscreen size={18} /></button>
          {confirmed && assets ? (
            <>
              <a className="download-button secondary-download" href={resolveApiUrl(assets.pdf_url)}><Download size={17} /> {tr("下載 PDF")}</a>
              <a className="download-button" href={`${resolveApiUrl(assets.pptx_url)}${animationsEnabled ? "?animations=true" : ""}`}><Download size={17} /> {tr("下載 PPTX")}</a>
            </>
          ) : (
            <button className="download-button" disabled><Download size={17} /> {tr("確認後下載")}</button>
          )}
        </div>
      </header>

      <div className={`preview-workspace ${theaterMode ? "theater-mode" : ""}`}>
        <aside className="slide-strip" aria-label={tr("投影片縮圖")}>
          <div className="slide-strip-heading"><span>{tr("正式輸出")}</span><strong>{previewUrls.length}</strong></div>
          {previewUrls.map((url, index) => (
            <button key={url} className={active === index ? "active" : ""} onClick={() => setActive(index)} aria-label={`前往第 ${index + 1} 頁`}>
              <span className="thumbnail-number">{index + 1}</span>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={resolveApiUrl(url)} alt={`第 ${index + 1} 頁縮圖`} />
            </button>
          ))}
        </aside>

        <section className="slide-stage" ref={stageRef}>
          {theaterMode && <button className="theater-exit" onClick={toggleFullscreen}><X size={16} /> {tr("退出全螢幕")}</button>}
          <div className="stage-meta"><span>{tr("正式 PPTX / PDF 渲染")}</span><span>{locale === "en" ? `Slide ${active + 1}` : `頁面 ${active + 1}`} / {previewUrls.length || slides.length}</span></div>
          <div className="slide-frame official-preview">
            {rendering ? (
              <div className="rendering-preview"><LoaderCircle className="spin" size={28} /><strong>{tr("正在重新套用模板")}</strong><small>{tr("預估少於 30 秒")}</small></div>
            ) : previewUrls[active] ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={`${active}-${animationsEnabled}`} className={animationsEnabled ? "animate-slide-image" : ""} src={resolveApiUrl(previewUrls[active])} alt={`簡報第 ${active + 1} 頁`} />
            ) : (
              <div className="rendering-preview"><LoaderCircle className="spin" size={28} /><strong>{tr("正在準備正式預覽")}</strong><small>{tr("預估少於 30 秒")}</small></div>
            )}
          </div>
          <div className="slide-controls">
            <button onClick={() => setActive(Math.max(0, active - 1))} disabled={active === 0} aria-label={tr("上一頁")}><ChevronLeft size={19} /></button>
            <span>{active + 1} / {previewUrls.length || slides.length}</span>
            <button onClick={() => setActive(Math.min(previewUrls.length - 1, active + 1))} disabled={active >= previewUrls.length - 1} aria-label={tr("下一頁")}><ChevronRight size={19} /></button>
          </div>
        </section>

        <aside className="review-panel">
          <div className="review-icon"><MonitorUp size={22} /></div>
          <p className="eyebrow">{tr("下載前確認")}</p>
          <h2>{tr("每一頁都看過了嗎？")}</h2>
          <p>{tr("請檢查文字、數字與版面。若需要修改，可以返回上一步重新產生。")}</p>
          <ul>
            <li><Check size={15} /> {tr("標題與內容正確")}</li>
            <li><Check size={15} /> {tr("沒有文字溢出")}</li>
            <li><Check size={15} /> {tr("預覽與下載檔一致")}</li>
          </ul>
          {actionError && <p className="preview-action-error">{actionError}</p>}
          {!confirmed ? (
            <button className="primary-button" onClick={confirmPresentation} disabled={!assets || rendering}><Check size={17} /> {tr("確認簡報沒問題")}</button>
          ) : (
            <div className="confirmed-state"><span><Check size={17} /></span><div><strong>{tr("已確認，可以下載")}</strong><small>{tr("PPTX 內的文字仍可編輯")}</small></div></div>
          )}
          <button className="text-button" onClick={onBack}>{tr("需要調整內容")} <ArrowRight size={15} /></button>
        </aside>
      </div>
    </main>
  );
}

function LibraryView({
  onCreate,
  onOpen,
  onDuplicate,
  onRetry,
  locale,
}: {
  onCreate: () => void;
  onOpen: (id: string) => Promise<void>;
  onDuplicate: (id: string) => Promise<void>;
  onRetry: (id: string) => Promise<void>;
  locale: AppLocale;
}) {
  const tr = (text: string) => translate(locale, text);
  const [items, setItems] = useState<PresentationRecord[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetch(`${apiBaseUrl}/presentations`)
      .then(async (response) => {
        if (!response.ok) throw new Error("無法讀取簡報列表");
        const records = await response.json() as PresentationRecord[];
        if (active) setItems(records);
      })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : "無法讀取簡報列表");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const deleteOne = async (item: PresentationRecord) => {
    if (!window.confirm(`確定要刪除「${item.title}」嗎？刪除後無法復原。`)) return;
    const response = await fetch(`${apiBaseUrl}/presentations/${item.id}`, { method: "DELETE" });
    if (response.ok) {
      setItems((current) => current.filter((entry) => entry.id !== item.id));
      setSelected((current) => { const next = new Set(current); next.delete(item.id); return next; });
    }
  };

  const deleteSelected = async () => {
    if (!selected.size || !window.confirm(`確定要刪除選取的 ${selected.size} 份簡報嗎？刪除後無法復原。`)) return;
    const response = await fetch(`${apiBaseUrl}/presentations/batch-delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: Array.from(selected) }),
    });
    if (response.ok) {
      setItems((current) => current.filter((entry) => !selected.has(entry.id)));
      setSelected(new Set());
    }
  };

  const toggleSelected = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const duplicateOne = async (item: PresentationRecord) => {
    setBusyId(item.id);
    setError(null);
    try {
      await onDuplicate(item.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "無法複製簡報");
      setBusyId(null);
    }
  };

  const retryOne = async (item: PresentationRecord) => {
    setBusyId(item.id);
    setError(null);
    try {
      await onRetry(item.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "無法重試簡報");
      setBusyId(null);
    }
  };
  const visible = items.filter((item) => item.title.toLowerCase().includes(query.toLowerCase()));
  const statusLabels: Record<PresentationRecord["status"], string> = {
    DRAFT: tr("草稿"), PARSING: tr("解析中"), GENERATING_CONTENT: tr("生成中"), RENDERING: tr("渲染中"),
    PREVIEW_READY: tr("待確認"), COMPLETED: tr("已完成"), FAILED: tr("失敗"),
  };

  return (
    <main className="secondary-view">
      <div className="section-heading">
        <div><p className="eyebrow">{tr("工作空間")}</p><h1>{tr("我的簡報")}</h1><p>{tr("查看、預覽與管理你建立的所有簡報。")}</p></div>
        <button className="primary-button" onClick={onCreate}><Plus size={17} /> {tr("建立簡報")}</button>
      </div>
      <div className="library-tools">
        <label><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={tr("搜尋簡報")} aria-label={tr("搜尋簡報")} /></label>
        <button><Clock3 size={16} /> {tr("最近更新")} <ChevronRight size={14} /></button>
      </div>
      {selected.size > 0 && <div className="batch-actions"><span>{locale === "en" ? `${selected.size} presentations selected` : `已選取 ${selected.size} 份簡報`}</span><button className="danger-action" onClick={deleteSelected}><Trash2 size={16} /> {tr("批次刪除")}</button></div>}
      {loading && <p className="library-message"><LoaderCircle className="spin" size={18} /> {tr("正在讀取簡報…")}</p>}
      {error && <p className="library-message error">{error}</p>}
      <div className="presentation-grid">
        {!loading && visible.map((item, index) => (
          <article key={item.id} className={selected.has(item.id) ? "selected" : ""}>
            <label className="presentation-select"><input type="checkbox" checked={selected.has(item.id)} onChange={() => toggleSelected(item.id)} aria-label={`選取 ${item.title}`} /></label>
            <div className={`presentation-cover cover-${index + 1}`}><span>{String(index + 1).padStart(2, "0")}</span><strong>{item.title}</strong><BrandMark /></div>
            <div className="presentation-info">
              <div><h2>{item.title}</h2><p>{locale === "en" ? `${item.slide_count} slides` : `${item.slide_count} 頁`} · {new Intl.DateTimeFormat(locale, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(item.updated_at))}</p>{item.status === "FAILED" && item.last_error && <small className="presentation-error">{item.last_error}</small>}</div>
              <div className="presentation-card-actions">
                {item.status === "FAILED" && item.can_retry ? (
                  <button className="quiet-button" onClick={() => void retryOne(item)} disabled={busyId === item.id}>{busyId === item.id ? <LoaderCircle className="spin" size={15} /> : <RefreshCcw size={15} />} {tr(busyId === item.id ? "重試中" : item.failed_stage === "render" ? "重新渲染" : "重試")}</button>
                ) : (
                  <button className="quiet-button" onClick={() => void onOpen(item.id)}><MonitorUp size={15} /> {tr("開啟")}</button>
                )}
                {item.slide_count > 0 && <button className="quiet-button compact-action" onClick={() => void duplicateOne(item)} disabled={busyId === item.id} aria-label={`${tr("複製")} ${item.title}`}><Copy size={15} /> {tr("複製")}</button>}
                <button className="danger-button" onClick={() => deleteOne(item)} aria-label={`刪除 ${item.title}`}><Trash2 size={17} /></button>
              </div>
            </div>
            <span className="status-badge">{statusLabels[item.status]}</span>
          </article>
        ))}
        {!loading && !error && visible.length === 0 && <div className="empty-library"><FolderOpen size={26} /><strong>{tr(query ? "找不到符合的簡報" : "還沒有簡報")}</strong><span>{tr(query ? "請試試其他關鍵字。" : "完成第一次生成後，簡報會自動保存在這裡。")}</span></div>}
        <button className="new-presentation-card" onClick={onCreate}><span><Plus size={21} /></span><strong>{tr("建立新簡報")}</strong><small>{tr("從主題或文件開始")}</small></button>
      </div>
    </main>
  );
}

type JobFilter = "all" | "active" | "completed" | "failed" | "canceled";

function JobCenterView({
  onResume,
  onOpen,
  onRetry,
  locale,
}: {
  onResume: (job: GenerationJobSummary) => void;
  onOpen: (presentationId: string) => Promise<void>;
  onRetry: (presentationId: string) => Promise<void>;
  locale: AppLocale;
}) {
  const tr = (text: string) => translate(locale, text);
  const [filter, setFilter] = useState<JobFilter>("all");
  const [jobs, setJobs] = useState<GenerationJobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const requestControllerRef = useRef<AbortController | null>(null);

  const loadJobs = useCallback(async (silent = false) => {
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    if (!silent) {
      setLoading(true);
      setError(null);
    }
    try {
      const response = await fetch(`${apiBaseUrl}/generation-jobs?state=${filter}&limit=100`, {
        signal: controller.signal,
      });
      const result = await response.json() as GenerationJobSummary[] | { detail?: string };
      if (!response.ok || !Array.isArray(result)) {
        throw new Error(!Array.isArray(result) && result.detail ? result.detail : "無法讀取生成任務");
      }
      if (controller.signal.aborted || requestControllerRef.current !== controller) return;
      setJobs(result);
      setError(null);
    } catch (caught) {
      if (controller.signal.aborted || requestControllerRef.current !== controller) return;
      setError(caught instanceof Error ? caught.message : "無法讀取生成任務");
    } finally {
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
        setLoading(false);
      }
    }
  }, [filter]);

  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    const refresh = async (silent = false) => {
      await loadJobs(silent);
      if (!stopped) {
        timer = window.setTimeout(() => void refresh(true), jobCenterRefreshIntervalMs);
      }
    };
    void refresh();
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
      requestControllerRef.current?.abort();
    };
  }, [loadJobs]);

  const cancelJob = async (job: GenerationJobSummary) => {
    setBusyId(job.id);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/generation-jobs/${job.id}/cancel`, { method: "POST" });
      const result = await response.json() as GenerationJob & { detail?: string };
      if (!response.ok) throw new Error(result.detail || "無法取消生成任務");
      await loadJobs();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "無法取消生成任務");
    } finally {
      setBusyId(null);
    }
  };

  const retryJob = async (job: GenerationJobSummary) => {
    setBusyId(job.id);
    setError(null);
    try {
      await onRetry(job.presentation_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "無法重試生成任務");
      setBusyId(null);
    }
  };

  const filters: Array<{ id: JobFilter; label: string }> = [
    { id: "all", label: tr("全部") },
    { id: "active", label: tr("執行中") },
    { id: "failed", label: tr("失敗") },
    { id: "completed", label: tr("已完成") },
    { id: "canceled", label: tr("已取消") },
  ];
  const statusLabels: Record<GenerationJob["status"], string> = {
    QUEUED: tr("等待中"),
    RUNNING: tr("執行中"),
    COMPLETED: tr("已完成"),
    FAILED: tr("失敗"),
    CANCELED: tr("已取消"),
  };
  const stageLabels: Record<string, string> = {
    queued: "等待背景工作程序",
    recovered: "已恢復，等待繼續",
    starting: "正在啟動模型",
    analyzing_sources: "正在規劃簡報大綱",
    saving_outline: "正在儲存簡報大綱",
    outline_ready: "簡報大綱已完成",
    preparing_content: "正在產生逐頁內容",
    generating_content_batch: "正在分批產生逐頁內容",
    retrying_content_batch: "部分內容未通過驗證，正在重試",
    saving_content: "正在儲存逐頁內容",
    content_ready: "逐頁內容已完成",
    canceling: "正在取消任務",
    canceled: "任務已取消",
  };

  return (
    <main className="secondary-view job-center-view">
      <div className="section-heading">
        <div><p className="eyebrow">BACKGROUND JOBS</p><h1>{tr("生成任務中心")}</h1><p>{tr("查看所有背景任務，重新接回進度或處理失敗項目。")}</p></div>
        <button className="quiet-button" onClick={() => void loadJobs()} disabled={loading}><RefreshCcw className={loading ? "spin" : ""} size={16} /> {tr("重新整理")}</button>
      </div>
      <div className="job-filters" role="group" aria-label={tr("任務狀態篩選")}>
        {filters.map((item) => <button className={filter === item.id ? "active" : ""} key={item.id} onClick={() => setFilter(item.id)}>{item.label}</button>)}
      </div>
      {error && <p className="library-message error">{error}</p>}
      {loading && <p className="library-message"><LoaderCircle className="spin" size={18} /> {tr("正在讀取任務…")}</p>}
      {!loading && !error && jobs.length === 0 && <div className="empty-job-center"><Clock3 size={28} /><strong>{tr("目前沒有這個狀態的任務")}</strong><span>{tr("建立簡報後，生成進度會出現在這裡。")}</span></div>}
      <section className="job-list" aria-label={tr("生成任務列表")}>
        {jobs.map((job) => {
          const active = job.status === "QUEUED" || job.status === "RUNNING";
          const retryable = isGenerationJobRetryable(job);
          return (
            <article className={`job-card status-${job.status.toLowerCase()}`} key={job.id}>
              <div className="job-card-icon">{job.status === "COMPLETED" ? <Check size={18} /> : job.status === "FAILED" || job.status === "CANCELED" ? <X size={18} /> : <LoaderCircle className={job.status === "RUNNING" ? "spin" : ""} size={18} />}</div>
              <div className="job-card-copy">
                <div><span>{tr(job.job_type === "outline" ? "大綱生成" : "內容生成")}</span><strong>{job.presentation_title}</strong></div>
                <p>{job.error || tr(stageLabels[job.stage] || job.stage)}</p>
                <div className="job-progress"><span style={{ width: `${job.progress}%` }} /></div>
                <small>
                  {new Intl.DateTimeFormat(locale, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(job.updated_at))} · {job.progress}%
                  {active ? ` · ${tr("預估剩餘")} ${formatDuration(job.estimated_remaining_seconds, locale)}` : ""}
                </small>
              </div>
              <div className="job-card-status"><span>{statusLabels[job.status]}</span></div>
              <div className="job-card-actions">
                {active && <button className="quiet-button" onClick={() => onResume(job)}><MonitorUp size={15} /> {tr("查看進度")}</button>}
                {job.status === "COMPLETED" && <button className="quiet-button" onClick={() => void onOpen(job.presentation_id)}><FolderOpen size={15} /> {tr("開啟目前簡報")}</button>}
                {active && <button className="danger-button" onClick={() => void cancelJob(job)} disabled={busyId === job.id} aria-label={`取消 ${job.presentation_title}`}>{busyId === job.id ? <LoaderCircle className="spin" size={15} /> : <X size={15} />}</button>}
                {retryable && <button className="quiet-button" onClick={() => void retryJob(job)} disabled={busyId === job.id}>{busyId === job.id ? <LoaderCircle className="spin" size={15} /> : <RefreshCcw size={15} />} {tr("重試")}</button>}
                {job.status === "FAILED" && !retryable && <span className="job-card-resolved">{tr("已由後續任務處理")}</span>}
              </div>
            </article>
          );
        })}
      </section>
    </main>
  );
}

function SettingsView({
  providerOptions,
  preferences,
  onPreferencesChange,
  reloadProviderOptions,
}: {
  providerOptions: AIProviderOption[];
  preferences: AppPreferences;
  onPreferencesChange: (changes: Partial<AppPreferences>) => void;
  reloadProviderOptions: () => Promise<void>;
}) {
  const tr = (text: string) => translate(preferences.locale, text);
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
    imageModel: "",
  });

  const setProviderKind = (provider: ProviderKind) => {
    setDraft((current) => ({
      ...current,
      provider,
      baseUrl: providerBaseUrls[provider],
      model: provider === "stable_diffusion" ? "local-checkpoint" : current.model === "local-checkpoint" ? "" : current.model,
      imageModel: provider === "stable_diffusion" ? "" : current.imageModel,
    }));
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
          image_model: draft.imageModel || null,
          api_key: draft.apiKey || null,
        }),
      });
      const result = await response.json() as { detail?: string };
      if (!response.ok) throw new Error(result.detail || "無法儲存 AI 設定");
      await reloadProviderOptions();
      setDraft({ name: "", provider: "openai", baseUrl: providerBaseUrls.openai, model: "", apiKey: "", imageModel: "" });
      setShowForm(false);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "無法儲存 AI 設定");
    } finally {
      setSaving(false);
    }
  };

  const testProvider = async (provider: AIProviderOption) => {
    setConnections((current) => ({ ...current, [provider.id]: { status: "testing", message: tr("測試中") } }));
    try {
      const path = provider.builtIn ? "/ai-provider/test" : `/ai-providers/${provider.id}/test`;
      const response = await fetch(`${apiBaseUrl}${path}`, { method: "POST" });
      const result = await response.json() as { connected?: boolean; error?: string | null };
      if (!response.ok || !result.connected) throw new Error(result.error || tr("連線失敗"));
      setConnections((current) => ({ ...current, [provider.id]: { status: "connected", message: tr("已連線") } }));
    } catch (error) {
      setConnections((current) => ({
        ...current,
        [provider.id]: { status: "failed", message: error instanceof Error ? error.message : tr("連線失敗") },
      }));
    }
  };

  const deleteProvider = async (provider: AIProviderOption) => {
    const message = preferences.locale === "en"
      ? `Delete “${provider.name}”?`
      : `確定要刪除「${provider.name}」嗎？`;
    if (!window.confirm(message)) return;
    const response = await fetch(`${apiBaseUrl}/ai-providers/${provider.id}`, { method: "DELETE" });
    if (response.ok) await reloadProviderOptions();
  };

  return (
    <main className="secondary-view settings-view">
      <div className="section-heading"><div><p className="eyebrow">{tr("偏好設定")}</p><h1>{tr("AI 模型設定")}</h1><p>{tr("加入文字與本機圖片模型 API，測試後可在建立簡報時自由選擇。")}</p></div></div>
      <section className="settings-card preference-card">
        <div className="settings-section-heading">
          <span><Languages size={18} /></span>
          <div><h2>{tr("介面與外觀")}</h2><p>{tr("調整網站語言與色彩模式，設定會自動保存在這台裝置。")}</p></div>
        </div>
        <div className="preference-grid">
          <fieldset className="preference-field">
            <legend>{tr("介面語言")}</legend>
            <div className="segmented-control">
              <button type="button" className={preferences.locale === "zh-TW" ? "active" : ""} aria-pressed={preferences.locale === "zh-TW"} onClick={() => onPreferencesChange({ locale: "zh-TW" })}>繁體中文</button>
              <button type="button" className={preferences.locale === "en" ? "active" : ""} aria-pressed={preferences.locale === "en"} onClick={() => onPreferencesChange({ locale: "en" })}>English</button>
            </div>
            <small>{tr("只會切換網站操作文字，不會翻譯既有簡報內容。")}</small>
          </fieldset>
          <fieldset className="preference-field">
            <legend>{tr("外觀模式")}</legend>
            <div className="appearance-options">
              <button type="button" className={preferences.colorMode === "light" ? "active" : ""} aria-pressed={preferences.colorMode === "light"} onClick={() => onPreferencesChange({ colorMode: "light" })}>
                <span className="appearance-preview light"><Sun size={18} /></span>
                <span><strong>{tr("淺色")}</strong><small>{tr("淺色模式")}</small></span>
                {preferences.colorMode === "light" && <Check size={16} />}
              </button>
              <button type="button" className={preferences.colorMode === "dark" ? "active" : ""} aria-pressed={preferences.colorMode === "dark"} onClick={() => onPreferencesChange({ colorMode: "dark" })}>
                <span className="appearance-preview dark"><Moon size={18} /></span>
                <span><strong>{tr("深色")}</strong><small>{tr("深色模式")}</small></span>
                {preferences.colorMode === "dark" && <Check size={16} />}
              </button>
            </div>
          </fieldset>
        </div>
      </section>
      <section className="settings-card">
        <div className="settings-section-heading provider-heading">
          <span><Sparkles size={18} /></span>
          <div><h2>{tr("已串接的 AI 模型")}</h2><p>{tr("API Key 會加密保存，設定頁不會再次顯示明文。")}</p></div>
          <button className="quiet-button" onClick={() => setShowForm((current) => !current)}><Plus size={15} /> {tr("新增模型")}</button>
        </div>

        {showForm && (
          <form className="provider-form" onSubmit={saveProvider}>
            <label><span>{tr("設定名稱")}</span><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder={tr("例如：公司 OpenAI")} required /></label>
            <label><span>{tr("API 類型")}</span><select value={draft.provider} onChange={(event) => setProviderKind(event.target.value as ProviderKind)}>{Object.entries(providerLabels).map(([value, label]) => <option key={value} value={value}>{tr(label)}</option>)}</select></label>
            <label className="wide"><span>Base URL</span><input value={draft.baseUrl} onChange={(event) => setDraft({ ...draft, baseUrl: event.target.value })} type="url" required /></label>
            <label><span>{tr(draft.provider === "stable_diffusion" ? "本機模型／Checkpoint" : "模型名稱")}</span><input value={draft.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })} placeholder={draft.provider === "stable_diffusion" ? "e.g. local-checkpoint" : tr("輸入 API 提供的模型 ID")} required /></label>
            {(draft.provider === "openai" || draft.provider === "openai_compatible") && <label><span>{tr("專用圖片模型（選填）")}</span><input value={draft.imageModel} onChange={(event) => setDraft({ ...draft, imageModel: event.target.value })} placeholder="e.g. gpt-image-2" /><small>{tr(draft.provider === "openai" ? "留空時會嘗試使用文字模型的圖片生成工具。" : "相容 API 需填寫可用的圖片模型。")}</small></label>}
            <label><span>API Key {draft.provider === "ollama" || draft.provider === "openai_compatible" || draft.provider === "stable_diffusion" ? `(${tr("選填")})` : ""}</span><div className="secret-field"><KeyRound size={15} /><input value={draft.apiKey} onChange={(event) => setDraft({ ...draft, apiKey: event.target.value })} type="password" autoComplete="new-password" required={draft.provider !== "ollama" && draft.provider !== "openai_compatible" && draft.provider !== "stable_diffusion"} /></div></label>
            {formError && <p className="provider-form-error">{formError}</p>}
            <div className="provider-form-actions"><button type="button" className="quiet-button" onClick={() => setShowForm(false)}>{tr("取消")}</button><button className="primary-button" disabled={saving}>{tr(saving ? "儲存中" : "儲存設定")}</button></div>
          </form>
        )}

        <div className="provider-list">
          {providerOptions.map((provider) => {
            const connection = connections[provider.id] ?? { status: "idle", message: tr("尚未測試") };
            return (
              <div className="setting-row provider-row" key={provider.id}>
                <div className="provider-copy"><strong>{tr(provider.name)}</strong><small>{tr(providerLabels[provider.provider] ?? provider.provider)} · {provider.model}</small>{provider.imageModel && <small>{tr("圖片模型")} · {provider.imageModel}</small>}<small>{tr(provider.builtIn ? "系統預設" : provider.provider === "stable_diffusion" ? "本機生成，不使用雲端額度" : provider.hasApiKey ? "API Key 已加密保存" : "未設定 API Key")}</small></div>
                <span className={`connection-badge ${connection.status}`}>{connection.message}</span>
                <div className="provider-actions">
                  <button className="quiet-button" onClick={() => testProvider(provider)} disabled={connection.status === "testing"}><PlugZap size={14} /> {tr(connection.status === "testing" ? "測試中" : "測試")}</button>
                  {!provider.builtIn && <button className="icon-button danger-button" onClick={() => deleteProvider(provider)} aria-label={`刪除 ${provider.name}`}><Trash2 size={15} /></button>}
                </div>
              </div>
            );
          })}
          {providerOptions.length === 0 && <p className="empty-provider">{tr("目前無法讀取 AI API，請確認後端服務與 PostgreSQL 已啟動。")}</p>}
        </div>
      </section>
      <section className="settings-card">
        <div className="settings-section-heading"><span><LayoutTemplate size={18} /></span><div><h2>{tr("簡報預設值")}</h2><p>{tr("建立新簡報時會自動帶入以下設定。")}</p></div></div>
        <div className="settings-form-grid">
          <label><span>{tr("預設語言")}</span><select value={preferences.defaultPresentationLanguage} onChange={(event) => onPreferencesChange({ defaultPresentationLanguage: event.target.value })}><option value="zh-TW">{tr("繁體中文")}</option><option value="en">English</option><option value="ja">日本語</option></select></label>
          <label><span>{tr("預設頁數")}</span><select value={preferences.defaultSlideCount} onChange={(event) => onPreferencesChange({ defaultSlideCount: event.target.value })}><option value="6">{tr("約 6 頁")}</option><option value="10">{tr("約 10 頁")}</option><option value="15">{tr("約 15 頁")}</option><option value="20">{tr("約 20 頁")}</option></select></label>
        </div>
      </section>
    </main>
  );
}

export default function Home() {
  const [preferences, setPreferences] = useState<AppPreferences>(defaultPreferences);
  const [preferencesReady, setPreferencesReady] = useState(false);
  const [view, setView] = useState<View>("create");
  const [topic, setTopic] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [sourceStatuses, setSourceStatuses] = useState<Record<string, SourceExtractionItem>>({});
  const [template, setTemplate] = useState<TemplateId>("editorial");
  const [language, setLanguage] = useState("zh-TW");
  const [slideCount, setSlideCount] = useState("10");
  const [customSlideCount, setCustomSlideCount] = useState(false);
  const [providerOptions, setProviderOptions] = useState<AIProviderOption[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState("default");
  const [generateImages, setGenerateImages] = useState(false);
  const [imageProviderId, setImageProviderId] = useState("");
  const [progress, setProgress] = useState(0);
  const [jobStage, setJobStage] = useState("");
  const [estimatedRemainingSeconds, setEstimatedRemainingSeconds] = useState<number | null>(null);
  const [generationStartedAt, setGenerationStartedAt] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<ActiveJob | null>(null);
  const [outline, setOutline] = useState<PresentationOutline | null>(null);
  const [slides, setSlides] = useState<SlideData[]>(() => makeSlides(topic));
  const [presentationId, setPresentationId] = useState<string | null>(null);
  const [assets, setAssets] = useState<RenderAssets | null>(null);
  const [initiallyConfirmed, setInitiallyConfirmed] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);

  useEffect(() => {
    const saved = readPreferences(window.localStorage);
    const timer = window.setTimeout(() => {
      setPreferences(saved);
      setLanguage(saved.defaultPresentationLanguage);
      setSlideCount(saved.defaultSlideCount);
      setPreferencesReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!preferencesReady) return;
    writePreferences(window.localStorage, preferences);
    document.documentElement.dataset.colorMode = preferences.colorMode;
    document.documentElement.lang = preferences.locale === "en" ? "en" : "zh-Hant";
  }, [preferences, preferencesReady]);

  const updatePreferences = (changes: Partial<AppPreferences>) => {
    setPreferences((current) => ({ ...current, ...changes }));
  };

  useEffect(() => {
    const saved = window.localStorage.getItem("ppt-creator-active-job");
    if (!saved) return;
    try {
      const restored = JSON.parse(saved) as ActiveJob;
      if (!restored.id || !restored.presentationId || !["outline", "content"].includes(restored.kind)) return;
      const timer = window.setTimeout(() => {
        setActiveJob(restored);
        setPresentationId(restored.presentationId);
        setProgress(5);
        setJobStage("正在恢復背景任務");
        setEstimatedRemainingSeconds(null);
        setGenerationStartedAt(null);
        setView("generating");
      }, 0);
      return () => window.clearTimeout(timer);
    } catch {
      window.localStorage.removeItem("ppt-creator-active-job");
    }
  }, []);

  const reloadProviderOptions = useCallback(async () => {
    const options = await fetchProviderOptions();
    setProviderOptions(options);
    setSelectedProviderId((current) => options.some((provider) => provider.id === current && isTextProvider(provider)) ? current : options.find(isTextProvider)?.id ?? "default");
    setImageProviderId((current) => options.some((provider) => provider.id === current && isImageProvider(provider)) ? current : options.find((provider) => provider.provider === "ollama" && provider.builtIn)?.id ?? options.find((provider) => provider.provider === "stable_diffusion")?.id ?? options.find(isImageProvider)?.id ?? "");
  }, []);

  useEffect(() => {
    let active = true;
    void fetchProviderOptions().then((options) => {
      if (!active) return;
      setProviderOptions(options);
      setSelectedProviderId(options.find(isTextProvider)?.id ?? "default");
      setImageProviderId(options.find((provider) => provider.provider === "ollama" && provider.builtIn)?.id ?? options.find((provider) => provider.provider === "stable_diffusion")?.id ?? options.find(isImageProvider)?.id ?? "");
    });
    return () => { active = false; };
  }, []);

  const renderDeck = useCallback(async (
    id: string,
    deckTopic: string,
    deckSlides: SlideData[],
    deckTemplate: TemplateId,
  ) => {
    setRendering(true);
    try {
      const blob = await buildPresentationPptx(deckTopic, deckSlides, deckTemplate);
      const formData = new FormData();
      formData.append("file", blob, "presentation.pptx");
      formData.append("template", deckTemplate);
      const response = await fetch(`${apiBaseUrl}/presentations/${id}/render`, {
        method: "POST",
        body: formData,
      });
      const result = await response.json() as RenderAssets & { detail?: string };
      if (!response.ok) throw new Error(result.detail || "無法產生正式簡報預覽");
      setAssets(result);
      setTemplate(deckTemplate);
    } finally {
      setRendering(false);
    }
  }, []);

  useEffect(() => {
    if (!activeJob) return;
    window.localStorage.setItem("ppt-creator-active-job", JSON.stringify(activeJob));
    let stopped = false;
    let timer: number | undefined;
    let consecutiveErrors = 0;
    const stageLabels: Record<string, string> = {
      queued: "等待背景工作程序",
      recovered: "任務已恢復，等待繼續",
      starting: "正在啟動本機模型",
      analyzing_sources: "正在分析資料並規劃大綱",
      saving_outline: "正在儲存簡報大綱",
      outline_ready: "大綱已完成",
      preparing_content: "正在準備逐頁內容",
      generating_content_batch: "正在分批產生逐頁內容",
      retrying_content_batch: "部分內容未通過驗證，正在重試",
      saving_content: "正在儲存逐頁內容",
      content_ready: "逐頁內容已完成",
      canceling: "正在取消並釋放模型",
    };
    const clearSavedJob = () => {
      window.localStorage.removeItem("ppt-creator-active-job");
      setActiveJob(null);
    };
    const poll = async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/generation-jobs/${activeJob.id}`);
        const job = await response.json() as GenerationJob & { detail?: string };
        if (!response.ok) {
          if (response.status === 404) {
            clearSavedJob();
            setGenerationError(job.detail || "找不到要恢復的生成任務");
            return;
          }
          throw new Error(job.detail || "無法讀取生成任務");
        }
        if (stopped) return;
        consecutiveErrors = 0;
        setGenerationError(null);
        setProgress(job.progress);
        setJobStage(stageLabels[job.stage] || job.stage);
        setEstimatedRemainingSeconds(job.estimated_remaining_seconds);
        setGenerationStartedAt(job.started_at || job.created_at);
        if (job.status === "FAILED") {
          clearSavedJob();
          setEstimatedRemainingSeconds(0);
          setGenerationError(job.error || "背景生成任務失敗");
          return;
        }
        if (job.status === "CANCELED") {
          clearSavedJob();
          setEstimatedRemainingSeconds(0);
          setGenerationError("這次生成已取消，模型資源已釋放。");
          return;
        }
        if (job.status === "COMPLETED") {
          const detailResponse = await fetch(`${apiBaseUrl}/presentations/${activeJob.presentationId}`);
          const detail = await detailResponse.json() as PresentationDetail & { detail?: string };
          if (!detailResponse.ok) throw new Error(detail.detail || "無法讀取生成結果");
          setTopic(detail.title);
          setLanguage(detail.language);
          setTemplate(templates.some((item) => item.id === detail.template) ? detail.template : "editorial");
          setPresentationId(detail.id);
          if (activeJob.kind === "outline") {
            if (!detail.outline) throw new Error("背景任務沒有產生大綱");
            setOutline(detail.outline);
            setEstimatedRemainingSeconds(0);
            setView((currentView) => shouldAutoOpenGenerationResult(currentView) ? "outline" : currentView);
            clearSavedJob();
            return;
          }
          if (!detail.content) throw new Error("背景任務沒有產生逐頁內容");
          setSlides(detail.content.slides);
          setAssets(null);
          setInitiallyConfirmed(false);
          setProgress(96);
          setJobStage("正在渲染正式預覽");
          setEstimatedRemainingSeconds(30);
          await renderDeck(detail.id, detail.title, detail.content.slides, detail.template);
          setProgress(100);
          setEstimatedRemainingSeconds(0);
          setView((currentView) => shouldAutoOpenGenerationResult(currentView) ? "preview" : currentView);
          clearSavedJob();
          return;
        }
        timer = window.setTimeout(() => void poll(), 900);
      } catch (caught) {
        if (stopped) return;
        consecutiveErrors += 1;
        setJobStage("連線暫時中斷，正在自動重新連線");
        if (consecutiveErrors >= 3) {
          const message = caught instanceof Error ? caught.message : "無法追蹤生成任務";
          setGenerationError(`${message}，系統仍會保留並繼續追蹤背景任務。`);
        }
        const retryDelay = Math.min(5_000, 900 * 2 ** Math.min(consecutiveErrors, 3));
        timer = window.setTimeout(() => void poll(), retryDelay);
      }
    };
    void poll();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [activeJob, renderDeck]);

  const saveEditedDeck = async (nextTopic: string, nextSlides: SlideData[]) => {
    if (!presentationId) throw new Error("找不到要更新的簡報");
    const response = await fetch(`${apiBaseUrl}/presentations/${presentationId}/content`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: nextTopic,
        language,
        slides: nextSlides,
      }),
    });
    const result = await response.json() as PresentationDetail & { detail?: string };
    if (!response.ok || !result.content) throw new Error(result.detail || "無法儲存簡報內容");
    setTopic(result.content.title);
    setSlides(result.content.slides);
    setInitiallyConfirmed(false);
    setAssets(null);
    await renderDeck(presentationId, result.content.title, result.content.slides, template);
    setView("preview");
  };

  const restorePresentationVersion = async (revision: number) => {
    if (!presentationId) throw new Error("找不到要還原的簡報");
    const response = await fetch(`${apiBaseUrl}/presentations/${presentationId}/versions/${revision}/restore`, { method: "POST" });
    const result = await response.json() as PresentationDetail & { detail?: string };
    if (!response.ok || !result.content) throw new Error(result.detail || "無法還原簡報版本");
    const restoredTemplate = templates.some((item) => item.id === result.template) ? result.template : "editorial";
    setTopic(result.title);
    setSlides(result.content.slides);
    setLanguage(result.language);
    setTemplate(restoredTemplate);
    setInitiallyConfirmed(false);
    setAssets(null);
    await renderDeck(presentationId, result.title, result.content.slides, restoredTemplate);
    setView("preview");
  };

  const duplicatePresentation = async (id: string) => {
    const response = await fetch(`${apiBaseUrl}/presentations/${id}/duplicate`, { method: "POST" });
    const result = await response.json() as PresentationDetail & { detail?: string };
    if (!response.ok || !result.content) throw new Error(result.detail || "無法複製簡報");
    const duplicatedTemplate = templates.some((item) => item.id === result.template) ? result.template : "editorial";
    setTopic(result.title);
    setSlides(result.content.slides);
    setLanguage(result.language);
    setPresentationId(result.id);
    setTemplate(duplicatedTemplate);
    setInitiallyConfirmed(false);
    setAssets(null);
    await renderDeck(result.id, result.title, result.content.slides, duplicatedTemplate);
    setView("editor");
  };

  const retryPresentation = async (id: string) => {
    setProgress(20);
    setEstimatedRemainingSeconds(null);
    setGenerationStartedAt(new Date().toISOString());
    setGenerationError(null);
    setView("generating");
    try {
      const detailResponse = await fetch(`${apiBaseUrl}/presentations/${id}`);
      const detail = await detailResponse.json() as PresentationDetail & { detail?: string };
      if (!detailResponse.ok) throw new Error(detail.detail || "無法讀取要重試的簡報");
      setPresentationId(id);
      const retryTemplate = templates.some((item) => item.id === detail.template) ? detail.template : "editorial";
      setTopic(detail.title);
      setTemplate(retryTemplate);
      setLanguage(detail.language);
      if (detail.failed_stage === "render" && detail.content) {
        setSlides(detail.content.slides);
        setJobStage("正在渲染正式預覽");
        setEstimatedRemainingSeconds(30);
        await renderDeck(id, detail.content.title, detail.content.slides, retryTemplate);
        setProgress(100);
        setEstimatedRemainingSeconds(0);
        setInitiallyConfirmed(false);
        setView("preview");
        return;
      }
      const response = await fetch(`${apiBaseUrl}/presentations/${id}/retry`, { method: "POST" });
      const job = await response.json() as GenerationJob & { detail?: string };
      if (!response.ok || !job.id) throw new Error(job.detail || "無法重試簡報");
      setProgress(job.progress);
      setJobStage("等待背景工作程序");
      setEstimatedRemainingSeconds(job.estimated_remaining_seconds);
      setGenerationStartedAt(job.started_at || job.created_at);
      setActiveJob({ id: job.id, presentationId: id, kind: job.job_type });
    } catch (error) {
      const message = error instanceof Error ? error.message : "無法重試簡報";
      setGenerationError(message);
      throw error;
    }
  };

  const startGeneration = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setProgress(3);
    setJobStage("正在準備參考資料");
    setEstimatedRemainingSeconds(45);
    setGenerationStartedAt(new Date().toISOString());
    setGenerationError(null);
    setSourceStatuses({});
    setAssets(null);
    setOutline(null);
    setInitiallyConfirmed(false);
    setView("generating");
    try {
      let sourceText: string | null = null;
      if (files.length) {
        const formData = new FormData();
        files.forEach((file) => formData.append("files", file));
        const extractResponse = await fetch(`${apiBaseUrl}/sources/extract`, {
          method: "POST",
          body: formData,
        });
        const extracted = await extractResponse.json() as {
          files?: SourceExtractionItem[];
          combined_text?: string;
          detail?: string;
        };
        if (!extractResponse.ok) throw new Error(extracted.detail || "無法解析參考資料");
        const statuses = Object.fromEntries((extracted.files ?? []).map((item) => [item.filename, item]));
        setSourceStatuses(statuses);
        sourceText = extracted.combined_text?.trim() || null;
        if (!sourceText) throw new Error("所有參考資料都解析失敗，請移除錯誤檔案後重試");
        setProgress(18);
      }
      const response = await fetch(`${apiBaseUrl}/generation-jobs/outline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          language,
          slide_count: Number(slideCount),
          template,
          source_text: sourceText,
          provider_id: selectedProviderId === "default" ? null : selectedProviderId,
          generate_images: generateImages,
          image_provider_id: generateImages && imageProviderId !== "default" ? imageProviderId : null,
          image_count: 2,
        }),
      });
      const result = await response.json() as { presentation_id?: string; job?: GenerationJob; detail?: string };
      if (!response.ok || !result.presentation_id || !result.job) throw new Error(result.detail || `生成服務回傳 ${response.status}`);
      setPresentationId(result.presentation_id);
      setProgress(result.job.progress);
      setJobStage("等待背景工作程序");
      setEstimatedRemainingSeconds(result.job.estimated_remaining_seconds);
      setGenerationStartedAt(result.job.started_at || result.job.created_at);
      setActiveJob({ id: result.job.id, presentationId: result.presentation_id, kind: "outline" });
    } catch (error) {
      const message = error instanceof TypeError
        ? "無法連線 FastAPI。請確認 http://localhost:8000 已啟動。"
        : error instanceof Error ? error.message : "生成簡報時發生錯誤";
      setGenerationError(message);
    }
  };

  const confirmOutline = async (nextOutline: PresentationOutline) => {
    if (!presentationId) throw new Error("找不到要更新的簡報");
    const saveResponse = await fetch(`${apiBaseUrl}/presentations/${presentationId}/outline`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(nextOutline),
    });
    const saved = await saveResponse.json() as PresentationOutline & { detail?: string };
    if (!saveResponse.ok) throw new Error(saved.detail || "無法儲存簡報大綱");
    const jobResponse = await fetch(`${apiBaseUrl}/presentations/${presentationId}/generation-jobs/content`, { method: "POST" });
    const job = await jobResponse.json() as GenerationJob & { detail?: string };
    if (!jobResponse.ok || !job.id) throw new Error(job.detail || "無法建立內容生成任務");
    setOutline(saved);
    setTopic(saved.title);
    setLanguage(saved.language);
    setGenerationError(null);
    setProgress(job.progress);
    setJobStage("等待背景工作程序");
    setEstimatedRemainingSeconds(job.estimated_remaining_seconds);
    setGenerationStartedAt(job.started_at || job.created_at);
    setView("generating");
    setActiveJob({ id: job.id, presentationId, kind: "content" });
  };

  const cancelActiveGeneration = async () => {
    if (!activeJob) return;
    setJobStage("正在取消並釋放模型");
    try {
      const response = await fetch(`${apiBaseUrl}/generation-jobs/${activeJob.id}/cancel`, { method: "POST" });
      if (!response.ok) throw new Error("無法取消生成任務");
    } catch (caught) {
      setGenerationError(caught instanceof Error ? caught.message : "無法取消生成任務");
    }
  };

  const resumeGenerationJob = (job: GenerationJobSummary) => {
    setPresentationId(job.presentation_id);
    setProgress(job.progress);
    setJobStage(job.stage);
    setEstimatedRemainingSeconds(job.estimated_remaining_seconds);
    setGenerationStartedAt(job.started_at || job.created_at);
    setGenerationError(null);
    setActiveJob({ id: job.id, presentationId: job.presentation_id, kind: job.job_type });
    setView("generating");
  };

  const openPresentation = async (id: string) => {
    window.localStorage.removeItem("ppt-creator-active-job");
    setActiveJob(null);
    setGenerationError(null);
    setProgress(20);
    setJobStage("正在準備正式預覽");
    setEstimatedRemainingSeconds(30);
    setGenerationStartedAt(new Date().toISOString());
    setView("generating");
    try {
      const response = await fetch(`${apiBaseUrl}/presentations/${id}`);
      const detail = await response.json() as PresentationDetail & { detail?: string };
      if (!response.ok) throw new Error(detail.detail || "這份簡報無法開啟");
      const savedTemplate = templates.some((item) => item.id === detail.template) ? detail.template : "editorial";
      setTopic(detail.title);
      setLanguage(detail.language);
      setPresentationId(detail.id);
      setTemplate(savedTemplate);
      if (!detail.content && detail.outline) {
        setOutline(detail.outline);
        setProgress(100);
        setEstimatedRemainingSeconds(0);
        setView("outline");
        return;
      }
      if (!detail.content) throw new Error("這份簡報還沒有可開啟的內容或大綱");
      setSlides(detail.content.slides);
      setInitiallyConfirmed(detail.status === "COMPLETED");
      if (detail.preview_urls.length && detail.pptx_url && detail.pdf_url) {
        setAssets({
          preview_urls: detail.preview_urls,
          pptx_url: detail.pptx_url,
          pdf_url: detail.pdf_url,
        });
      } else {
        await renderDeck(detail.id, detail.title, detail.content.slides, savedTemplate);
      }
      setProgress(100);
      setEstimatedRemainingSeconds(0);
      setView("preview");
    } catch (error) {
      setGenerationError(error instanceof Error ? error.message : "無法開啟簡報");
    }
  };

  const resetNewPresentation = () => {
    if (activeJob) {
      void fetch(`${apiBaseUrl}/generation-jobs/${activeJob.id}/cancel`, { method: "POST" });
    }
    window.localStorage.removeItem("ppt-creator-active-job");
    setActiveJob(null);
    setTopic("");
    setFiles([]);
    setSourceStatuses({});
    setTemplate("editorial");
    setLanguage(preferences.defaultPresentationLanguage);
    setSlideCount(preferences.defaultSlideCount);
    setCustomSlideCount(false);
    setGenerateImages(false);
    setProgress(0);
    setJobStage("");
    setEstimatedRemainingSeconds(null);
    setGenerationStartedAt(null);
    setOutline(null);
    setSlides(makeSlides(""));
    setPresentationId(null);
    setAssets(null);
    setInitiallyConfirmed(false);
    setGenerationError(null);
    setView("create");
  };

  const changeView = (next: View) => {
    if (next === "create") resetNewPresentation();
    else if (next !== "generating" && next !== "preview") setView(next);
  };
  const compactNavigation = ["generating", "outline", "editor", "preview"].includes(view);

  return (
    <div className="app-shell">
      <SideNavigation view={view} compact={compactNavigation} locale={preferences.locale} onChange={changeView} />
      <div className={`app-content ${compactNavigation ? "compact-navigation" : ""}`}>
        {view !== "preview" && <AppHeader locale={preferences.locale} onCreate={resetNewPresentation} />}
        {view === "create" && <CreateView topic={topic} setTopic={setTopic} files={files} setFiles={(nextFiles) => { setFiles(nextFiles); setSourceStatuses({}); }} template={template} setTemplate={setTemplate} language={language} setLanguage={setLanguage} slideCount={slideCount} setSlideCount={setSlideCount} customSlideCount={customSlideCount} setCustomSlideCount={setCustomSlideCount} providerOptions={providerOptions} selectedProviderId={selectedProviderId} setSelectedProviderId={setSelectedProviderId} generateImages={generateImages} setGenerateImages={setGenerateImages} imageProviderId={imageProviderId} setImageProviderId={setImageProviderId} sourceStatuses={sourceStatuses} locale={preferences.locale} onGenerate={startGeneration} />}
        {view === "generating" && <GeneratingView progress={progress} stage={jobStage} error={generationError} sourceStatuses={sourceStatuses} locale={preferences.locale} estimatedRemainingSeconds={estimatedRemainingSeconds} startedAt={generationStartedAt} onBack={resetNewPresentation} onCancel={() => void cancelActiveGeneration()} />}
        {view === "outline" && outline && <OutlineView outline={outline} locale={preferences.locale} onConfirm={confirmOutline} onBack={resetNewPresentation} />}
        {view === "editor" && <EditorView topic={topic} slides={slides} template={template} presentationId={presentationId} locale={preferences.locale} onSave={saveEditedDeck} onRestore={restorePresentationVersion} onCancel={() => setView("preview")} />}
        {view === "preview" && <PreviewView topic={topic} slides={slides} presentationId={presentationId} template={template} assets={assets} initiallyConfirmed={initiallyConfirmed} rendering={rendering} locale={preferences.locale} onTemplateChange={async (nextTemplate) => { if (!presentationId) return; await renderDeck(presentationId, topic, slides, nextTemplate); }} onBack={() => setView("editor")} />}
        {view === "library" && <LibraryView locale={preferences.locale} onCreate={resetNewPresentation} onOpen={openPresentation} onDuplicate={duplicatePresentation} onRetry={retryPresentation} />}
        {view === "jobs" && <JobCenterView locale={preferences.locale} onResume={resumeGenerationJob} onOpen={openPresentation} onRetry={retryPresentation} />}
        {view === "settings" && <SettingsView providerOptions={providerOptions} preferences={preferences} onPreferencesChange={updatePreferences} reloadProviderOptions={reloadProviderOptions} />}
      </div>
    </div>
  );
}
