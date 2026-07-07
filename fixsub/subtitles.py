from __future__ import annotations

import re
from pathlib import Path


def _parse_srt_time(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def _parse_ass_time(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, centis = rest.split(".")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(centis) / 100


def parse_subtitle_intervals(path: Path) -> list[tuple[float, float]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    intervals: list[tuple[float, float]] = []
    if suffix == ".srt":
        pattern = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})")
        for start, end in pattern.findall(text):
            intervals.append((_parse_srt_time(start), _parse_srt_time(end)))
    elif suffix in {".ass", ".ssa"}:
        for line in text.splitlines():
            if not line.startswith("Dialogue:"):
                continue
            parts = line.split(",", 9)
            if len(parts) >= 3:
                intervals.append((_parse_ass_time(parts[1]), _parse_ass_time(parts[2])))
    return intervals
