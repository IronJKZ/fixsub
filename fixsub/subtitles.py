from __future__ import annotations

import re
from pathlib import Path

from fixsub.errors import FixsubError

SRT_TIMING_PATTERN = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})")


def _parse_srt_time(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def _parse_ass_time(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, centis = rest.split(".")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(centis) / 100


def _shift_interval(start: float, end: float, seconds: float, minimum_duration: float) -> tuple[float, float]:
    shifted_start = max(0.0, start + seconds)
    shifted_end = max(0.0, end + seconds)
    return shifted_start, max(shifted_start + minimum_duration, shifted_end)


def _format_srt_time(value: float) -> str:
    total_millis = max(0, round(value * 1000))
    hours, remainder = divmod(total_millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _format_ass_time(value: float) -> str:
    total_centis = max(0, round(value * 100))
    hours, remainder = divmod(total_centis, 360_000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def shift_subtitle_timing(source: Path, target: Path, seconds: float) -> int:
    if abs(seconds) < 0.001:
        raise FixsubError("Subtitle adjustment must be at least 0.001 seconds.")
    text = source.read_text(encoding="utf-8", errors="replace")
    suffix = source.suffix.lower()
    shifted_count = 0

    if suffix == ".srt":
        def replace_srt(match: re.Match[str]) -> str:
            nonlocal shifted_count
            shifted_count += 1
            start, end = _shift_interval(
                _parse_srt_time(match.group(1)),
                _parse_srt_time(match.group(2)),
                seconds,
                0.001,
            )
            return f"{_format_srt_time(start)} --> {_format_srt_time(end)}"

        shifted_text = SRT_TIMING_PATTERN.sub(replace_srt, text)
    elif suffix in {".ass", ".ssa"}:
        shifted_lines: list[str] = []
        for line in text.splitlines(keepends=True):
            content = line.rstrip("\r\n")
            ending = line[len(content) :]
            if not content.startswith("Dialogue:"):
                shifted_lines.append(line)
                continue
            parts = content.split(",", 9)
            if len(parts) < 3:
                shifted_lines.append(line)
                continue
            try:
                start, end = _shift_interval(
                    _parse_ass_time(parts[1]),
                    _parse_ass_time(parts[2]),
                    seconds,
                    0.01,
                )
            except ValueError:
                shifted_lines.append(line)
                continue
            parts[1] = _format_ass_time(start)
            parts[2] = _format_ass_time(end)
            shifted_lines.append(",".join(parts) + ending)
            shifted_count += 1
        shifted_text = "".join(shifted_lines)
    else:
        raise FixsubError(f"Unsupported subtitle format for adjustment: {source.suffix or '(none)'}")

    if shifted_count == 0:
        raise FixsubError(f"No subtitle timing entries found in {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(shifted_text, encoding="utf-8")
    return shifted_count


def parse_subtitle_intervals(path: Path) -> list[tuple[float, float]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    intervals: list[tuple[float, float]] = []
    if suffix == ".srt":
        for start, end in SRT_TIMING_PATTERN.findall(text):
            intervals.append((_parse_srt_time(start), _parse_srt_time(end)))
    elif suffix in {".ass", ".ssa"}:
        for line in text.splitlines():
            if not line.startswith("Dialogue:"):
                continue
            parts = line.split(",", 9)
            if len(parts) >= 3:
                try:
                    intervals.append((_parse_ass_time(parts[1]), _parse_ass_time(parts[2])))
                except ValueError:
                    continue
    return intervals
