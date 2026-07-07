from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fixsub.errors import MissingDependencyError
from fixsub.models import AudioStream


@dataclass(frozen=True)
class ProbeResult:
    duration_seconds: float | None
    audio_streams: list[AudioStream]
    raw: dict[str, Any]


def parse_ffprobe_json(payload: dict[str, Any]) -> ProbeResult:
    duration_text = payload.get("format", {}).get("duration")
    duration_seconds = float(duration_text) if duration_text else None
    audio_streams: list[AudioStream] = []
    audio_index = 0
    for stream in payload.get("streams", []):
        if stream.get("codec_type") != "audio":
            continue
        tags = stream.get("tags", {}) or {}
        disposition = stream.get("disposition", {}) or {}
        audio_streams.append(
            AudioStream(
                container_index=int(stream.get("index", audio_index)),
                audio_index=audio_index,
                codec=stream.get("codec_name"),
                language=tags.get("language"),
                channels=stream.get("channels"),
                is_default=bool(disposition.get("default")),
            )
        )
        audio_index += 1
    return ProbeResult(duration_seconds=duration_seconds, audio_streams=audio_streams, raw=payload)


def select_audio_stream(streams: list[AudioStream]) -> AudioStream:
    if not streams:
        raise ValueError("No audio streams found")
    return sorted(
        streams,
        key=lambda stream: (
            (stream.language or "").lower() in {"eng", "en"},
            stream.is_default,
            stream.channels or 0,
            -stream.audio_index,
        ),
        reverse=True,
    )[0]


def probe_video(video_path: Path) -> ProbeResult:
    if not shutil.which("ffprobe"):
        raise MissingDependencyError("ffprobe", "brew install ffmpeg")
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return parse_ffprobe_json(json.loads(result.stdout))
