from datetime import UTC, datetime, timedelta

from app.job_timing import (
    estimate_job_duration_seconds,
    estimate_job_remaining_seconds,
)


def test_duration_estimate_scales_with_slides_and_images() -> None:
    short_outline = estimate_job_duration_seconds(
        "outline", {"request": {"slide_count": 6}}
    )
    long_outline = estimate_job_duration_seconds(
        "outline", {"request": {"slide_count": 30}}
    )
    content_without_images = estimate_job_duration_seconds(
        "content",
        {"request": {"slide_count": 10, "generate_images": False}},
    )
    content_with_images = estimate_job_duration_seconds(
        "content",
        {
            "request": {
                "slide_count": 10,
                "generate_images": True,
                "image_count": 2,
            }
        },
    )

    assert long_outline > short_outline
    assert content_with_images > content_without_images


def test_remaining_estimate_uses_elapsed_time_and_progress() -> None:
    now = datetime.now(UTC)
    remaining = estimate_job_remaining_seconds(
        job_type="content",
        payload={"request": {"slide_count": 10}},
        status="RUNNING",
        progress=50,
        started_at=now - timedelta(seconds=90),
        now=now,
    )

    assert 5 <= remaining < estimate_job_duration_seconds(
        "content", {"request": {"slide_count": 10}}
    )


def test_terminal_job_has_no_remaining_time() -> None:
    remaining = estimate_job_remaining_seconds(
        job_type="outline",
        payload={"request": {"slide_count": 10}},
        status="COMPLETED",
        progress=100,
        started_at=datetime.now(UTC),
    )

    assert remaining == 0
