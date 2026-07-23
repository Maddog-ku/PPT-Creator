from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


TERMINAL_JOB_STATUSES = {"COMPLETED", "FAILED", "CANCELED"}


def estimate_job_duration_seconds(job_type: str, payload: dict[str, Any]) -> int:
    request = payload.get("request") if isinstance(payload, dict) else {}
    if not isinstance(request, dict):
        request = {}
    slide_count = max(3, min(50, int(request.get("slide_count") or 10)))
    source_chars = len(str(request.get("source_text") or ""))
    source_seconds = min(45, source_chars // 1_500)

    if job_type == "outline":
        return max(60, 35 + slide_count * 4 + source_seconds)

    image_count = (
        max(0, min(3, int(request.get("image_count") or 0)))
        if request.get("generate_images")
        else 0
    )
    return max(120, 30 + slide_count * 18 + image_count * 50 + source_seconds)


def estimate_job_remaining_seconds(
    *,
    job_type: str,
    payload: dict[str, Any],
    status: str,
    progress: int,
    started_at: datetime | None,
    now: datetime | None = None,
) -> int:
    if status in TERMINAL_JOB_STATUSES:
        return 0

    baseline = estimate_job_duration_seconds(job_type, payload)
    if started_at is None:
        return baseline

    current = now or datetime.now(UTC)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    elapsed = max(0, int((current - started_at).total_seconds()))
    normalized_progress = max(0, min(99, progress))

    if normalized_progress < 10:
        return max(5, baseline - elapsed)

    observed_total = elapsed / max(0.1, normalized_progress / 100)
    adjusted_total = baseline * 0.65 + observed_total * 0.35
    adjusted_total = max(baseline * 0.7, min(baseline * 3, adjusted_total))
    return max(5, int(adjusted_total - elapsed))
