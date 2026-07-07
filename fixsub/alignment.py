from __future__ import annotations

from pathlib import Path

from fixsub.models import AlignmentScore
from fixsub.subtitles import parse_subtitle_intervals


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def score_alignment(subtitle_path: Path, duration_seconds: float | None) -> AlignmentScore:
    reasons: list[str] = []
    intervals = parse_subtitle_intervals(subtitle_path)
    if not intervals:
        return AlignmentScore(score=0.0, reasons=["no parseable subtitle intervals"])
    valid_intervals = [(start, end) for start, end in intervals if start >= 0 and end > start]
    valid_rate = len(valid_intervals) / len(intervals)
    if valid_rate < 1.0:
        reasons.append("invalid subtitle timing intervals")
    if not valid_intervals:
        return AlignmentScore(score=0.0, reasons=reasons)
    if not duration_seconds or duration_seconds <= 0:
        return AlignmentScore(score=_clamp(0.4 + 0.5 * valid_rate), reasons=reasons + ["video duration unavailable"])
    outside_count = sum(1 for start, end in valid_intervals if start > duration_seconds or end > duration_seconds + 30)
    if outside_count:
        reasons.append("subtitle intervals outside video duration")
    first_start = min(start for start, _end in valid_intervals)
    last_end = max(end for _start, end in valid_intervals)
    span = max(1.0, last_end - first_start)
    density = len(valid_intervals) / (span / 60.0)
    score = 1.0
    score -= (1.0 - valid_rate) * 0.3
    score -= min(0.4, outside_count / len(valid_intervals))
    if first_start < 1:
        score -= 0.08
        reasons.append("first subtitle starts very early")
    if first_start > min(1800, duration_seconds * 0.35):
        score -= 0.25
        reasons.append("first subtitle starts too late")
    if last_end < duration_seconds * 0.45:
        score -= 0.25
        reasons.append("last subtitle ends too early")
    if last_end > duration_seconds + 30:
        score -= 0.25
        reasons.append("last subtitle ends outside video")
    if density < 0.15:
        score -= 0.15
        reasons.append("subtitle density is sparse")
    if density > 20:
        score -= 0.15
        reasons.append("subtitle density is unusually high")
    sorted_intervals = sorted(valid_intervals)
    long_gaps = [
        next_start - prev_end
        for (_prev_start, prev_end), (next_start, _next_end) in zip(sorted_intervals, sorted_intervals[1:])
        if next_start - prev_end > 1800
    ]
    if long_gaps:
        score -= min(0.2, 0.05 * len(long_gaps))
        reasons.append("very long gaps inside subtitle span")
    return AlignmentScore(score=round(_clamp(score), 3), reasons=reasons)
