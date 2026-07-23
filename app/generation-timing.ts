import type { AppLocale } from "./preferences";

export function elapsedSeconds(startedAt: string | null, now = Date.now()): number {
  if (!startedAt) return 0;
  const started = Date.parse(startedAt);
  if (!Number.isFinite(started)) return 0;
  return Math.max(0, Math.floor((now - started) / 1_000));
}

export function formatDuration(seconds: number, locale: AppLocale): string {
  const safeSeconds = Math.max(0, Math.round(seconds));
  if (safeSeconds < 60) {
    if (safeSeconds < 10) return locale === "en" ? "under 10 sec" : "少於 10 秒";
    return locale === "en" ? `about ${safeSeconds} sec` : `約 ${safeSeconds} 秒`;
  }
  const minutes = Math.floor(safeSeconds / 60);
  const remainder = safeSeconds % 60;
  if (locale === "en") {
    return remainder ? `about ${minutes} min ${remainder} sec` : `about ${minutes} min`;
  }
  return remainder ? `約 ${minutes} 分 ${remainder} 秒` : `約 ${minutes} 分鐘`;
}
