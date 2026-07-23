import type {
  AIProviderOption,
  AIProviderResponse,
  ProviderKind,
} from "./types";

export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export const providerLabels: Record<ProviderKind, string> = {
  ollama: "本機 API",
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Google Gemini",
  openai_compatible: "OpenAI 相容 API",
  stable_diffusion: "本機 Stable Diffusion",
};

export const providerBaseUrls: Record<ProviderKind, string> = {
  ollama: "http://host.docker.internal:11434",
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com/v1",
  gemini: "https://generativelanguage.googleapis.com/v1beta",
  openai_compatible: "http://host.docker.internal:1234/v1",
  stable_diffusion: "http://host.docker.internal:7860",
};

export const isTextProvider = (provider: AIProviderOption) =>
  provider.provider !== "stable_diffusion";

export const isImageProvider = (provider: AIProviderOption) =>
  (provider.provider === "ollama" && Boolean(provider.imageModel)) ||
  provider.provider === "stable_diffusion" ||
  provider.provider === "openai" ||
  (provider.provider === "openai_compatible" && Boolean(provider.imageModel));

export async function fetchProviderOptions(): Promise<AIProviderOption[]> {
  const options: AIProviderOption[] = [];
  const [builtInResult, customResult] = await Promise.allSettled([
    fetch(`${apiBaseUrl}/ai-provider`),
    fetch(`${apiBaseUrl}/ai-providers`),
  ]);
  if (builtInResult.status === "fulfilled" && builtInResult.value.ok) {
    const provider = (await builtInResult.value.json()) as AIProviderResponse;
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
    const providers = (await customResult.value.json()) as Array<{
      id: string;
      name: string;
      provider: ProviderKind;
      base_url: string;
      model: string;
      has_api_key: boolean;
      image_model: string | null;
    }>;
    options.push(
      ...providers.map((provider) => ({
        id: provider.id,
        name: provider.name,
        provider: provider.provider,
        model: provider.model,
        baseUrl: provider.base_url,
        hasApiKey: provider.has_api_key,
        imageModel: provider.image_model,
      })),
    );
  }
  return options;
}
