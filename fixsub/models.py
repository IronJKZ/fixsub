from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


def _path_to_str(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_path_to_str(item) for item in value]
    if isinstance(value, dict):
        return {key: _path_to_str(item) for key, item in value.items()}
    return value


def _json_ready(value: Any) -> Any:
    value = _path_to_str(value)
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class RunOptions:
    dry_run: bool = False
    audio: str | None = None
    no_sync: bool = False
    max_candidates: int = 5
    lang: str = "zh"
    providers: tuple[str, ...] = ("assrt", "subhd")
    debug: bool = False

    def to_json(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(frozen=True)
class WorkDirs:
    root: Path
    downloads: Path
    candidates: Path
    synced: Path
    original: Path
    logs: Path
    metadata: Path

    def to_json(self) -> dict[str, Any]:
        return _path_to_str(asdict(self))


@dataclass(frozen=True)
class MovieInfo:
    path: Path
    stem: str
    title: str | None = None
    year: str | None = None
    source: str | None = None
    resolution: str | None = None
    release_group: str | None = None

    def to_json(self) -> dict[str, Any]:
        return _path_to_str(asdict(self))


@dataclass(frozen=True)
class AudioStream:
    container_index: int
    audio_index: int
    codec: str | None
    language: str | None
    channels: int | None
    is_default: bool = False

    @property
    def ffsubsync_id(self) -> str:
        return f"a:{self.audio_index}"

    @property
    def display_name(self) -> str:
        language_name = {"eng": "English", "en": "English", "und": "unknown language"}.get(
            (self.language or "").lower(),
            self.language or "unknown language",
        )
        codec_name = (self.codec or "unknown codec").upper()
        if self.channels == 6:
            channel_name = "5.1"
        elif self.channels == 2:
            channel_name = "stereo"
        elif self.channels:
            channel_name = f"{self.channels}ch"
        else:
            channel_name = "unknown channels"
        default_name = ", default" if self.is_default else ""
        return f"{language_name}, {codec_name} {channel_name}{default_name}"

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["ffsubsync_id"] = self.ffsubsync_id
        data["display_name"] = self.display_name
        return data


@dataclass(frozen=True)
class SearchResult:
    provider: str
    result_id: str
    title: str
    download_url: str | None = None
    detail_url: str | None = None
    language: str | None = None
    format: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    pre_score: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return _path_to_str(asdict(self))


@dataclass(frozen=True)
class DownloadedFile:
    candidate_id: str
    provider: str
    path: Path
    source_url: str | None = None

    def to_json(self) -> dict[str, Any]:
        return _path_to_str(asdict(self))


@dataclass(frozen=True)
class SubtitleCandidate:
    candidate_id: str
    provider: str
    source_title: str
    subtitle_path: Path
    language: str | None
    format: str
    pre_score: float

    def to_json(self) -> dict[str, Any]:
        return _path_to_str(asdict(self))


@dataclass(frozen=True)
class AlignmentScore:
    score: float
    reasons: list[str]

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SyncResult:
    attempted: bool
    succeeded: bool
    output_path: Path | None = None
    error: str | None = None
    ffsubsync_score: float | None = None
    offset_seconds: float | None = None
    framerate_scale: float | None = None

    def to_json(self) -> dict[str, Any]:
        return _path_to_str(asdict(self))


@dataclass(frozen=True)
class CandidateDecision:
    candidate: SubtitleCandidate
    original_score: AlignmentScore
    synced_score: AlignmentScore | None
    sync_result: SyncResult
    selected_version: Literal["original", "synced"]
    selected_path: Path
    selected_score: float
    is_poor: bool
    decision_reason: str

    def to_json(self) -> dict[str, Any]:
        return _path_to_str(asdict(self))
