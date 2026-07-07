from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fixsub.errors import FixsubError, MissingDependencyError
from fixsub.models import AudioStream


class ProbeError(FixsubError):
    pass


@dataclass(frozen=True)
class ProbeResult:
    duration_seconds: float | None
    audio_streams: list[AudioStream]
    raw: dict[str, Any]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_duration(duration_text: Any) -> float | None:
    if not duration_text:
        return None
    try:
        return float(duration_text)
    except (TypeError, ValueError):
        return None


def parse_ffprobe_json(payload: dict[str, Any]) -> ProbeResult:
    duration_seconds = _parse_duration(_as_dict(payload.get("format")).get("duration"))
    audio_streams: list[AudioStream] = []
    audio_index = 0
    for stream in payload.get("streams", []):
        if not isinstance(stream, dict):
            continue
        if stream.get("codec_type") != "audio":
            continue
        tags = _as_dict(stream.get("tags"))
        disposition = _as_dict(stream.get("disposition"))
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
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        details = error.stderr.strip() if error.stderr else "ffprobe returned a non-zero exit status"
        raise ProbeError(f"ffprobe failed for {video_path}: {details}") from error
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ProbeError(f"ffprobe returned invalid JSON for {video_path}") from error
    return parse_ffprobe_json(payload)
