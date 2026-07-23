import type { SlideData } from "./presentation-builder";
import type { TemplateId } from "./templates";

export type View =
  | "create"
  | "generating"
  | "outline"
  | "editor"
  | "preview"
  | "library"
  | "jobs"
  | "settings";

export type ProviderKind =
  | "ollama"
  | "openai"
  | "anthropic"
  | "gemini"
  | "openai_compatible"
  | "stable_diffusion";

export type AIProviderResponse = {
  provider: string;
  model: string;
  image_model?: string | null;
  transport: "api";
};

export type AIProviderOption = {
  id: string;
  name: string;
  provider: ProviderKind;
  model: string;
  baseUrl?: string;
  hasApiKey?: boolean;
  builtIn?: boolean;
  imageModel?: string | null;
};

export type ProviderDraft = {
  name: string;
  provider: ProviderKind;
  baseUrl: string;
  model: string;
  apiKey: string;
  imageModel: string;
};

export type PresentationStatus =
  | "DRAFT"
  | "PARSING"
  | "GENERATING_CONTENT"
  | "RENDERING"
  | "PREVIEW_READY"
  | "COMPLETED"
  | "FAILED";

export type PresentationRecord = {
  id: string;
  language: string;
  title: string;
  status: PresentationStatus;
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

export type SourceExtractionItem = {
  filename: string;
  status: "success" | "error";
  char_count: number;
  error?: string | null;
};

export type RenderAssets = {
  preview_urls: string[];
  pptx_url: string;
  pdf_url: string;
};

export type OutlineItem = {
  id: string;
  eyebrow: string;
  title: string;
  objective: string;
  kind: SlideData["kind"];
};

export type PresentationOutline = {
  title: string;
  language: string;
  items: OutlineItem[];
};

export type GenerationJob = {
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

export type GenerationJobSummary = GenerationJob & {
  presentation_title: string;
  presentation_status: PresentationStatus;
  can_retry: boolean;
};

export type ActiveJob = {
  id: string;
  presentationId: string;
  kind: "outline" | "content";
};

export type PresentationDetail = PresentationRecord & {
  content: { title: string; language: string; slides: SlideData[] } | null;
  outline: PresentationOutline | null;
  preview_urls: string[];
  pptx_url: string | null;
  pdf_url: string | null;
  confirmed_at?: string | null;
};

export type PresentationVersionRecord = {
  id: string;
  revision: number;
  title: string;
  language: string;
  template: TemplateId;
  change_reason: string;
  created_at: string;
  slide_count: number;
};

export type PresentationVersionDetail = PresentationVersionRecord & {
  content: { title: string; language: string; slides: SlideData[] };
};
