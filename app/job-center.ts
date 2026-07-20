export type RetryableJobState = {
  status: string;
  presentation_status: string;
  can_retry: boolean;
};

export function isGenerationJobRetryable(job: RetryableJobState): boolean {
  return job.status === "FAILED"
    && job.presentation_status === "FAILED"
    && job.can_retry;
}

export function shouldAutoOpenGenerationResult(view: string): boolean {
  return view === "generating";
}

export const jobCenterRefreshIntervalMs = 2500;
