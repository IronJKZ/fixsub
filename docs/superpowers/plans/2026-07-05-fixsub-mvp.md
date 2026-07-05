# Fixsub MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the M1 `fixsub` CLI that searches ASSRT API, processes subtitle candidates, detects an audio reference with `ffprobe`, optionally syncs with `ffsubsync`, compares original vs synced quality, and writes an Infuse-compatible subtitle file.

**Architecture:** Implement a small Python package with focused modules for models, paths, movie parsing, ASSRT API access, archive handling, subtitle parsing, audio probing, alignment scoring, sync decisions, output, metadata, and CLI orchestration. The deterministic modules are built first with unit tests, then external network and subprocess boundaries are wrapped behind testable functions, and the final CLI composes the pipeline.

**Tech Stack:** Python 3.11+, Typer, Rich, HTTPX, charset-normalizer, pytest, ffprobe/ffmpeg, ffsubsync (`ffs`), unar/unrar for rar-like archives.

---

## Scope Check

The approved spec is a single cohesive M1: ASSRT API main path plus local processing and original-vs-synced comparison. It excludes SubHD, ASSRT web fallback, interactive mode, full config files, library scans, Web UI, Whisper, translation, and site-restriction bypasses. This plan therefore produces one testable CLI without implementing the excluded systems.

## File Structure

Create these files:

- `pyproject.toml`: package metadata, dependencies, console script, pytest config.
- `README.md`: install, dependencies, usage, and manual acceptance notes.
- `fixsub/__init__.py`: package version.
- `fixsub/cli.py`: Typer app and pipeline orchestration.
- `fixsub/errors.py`: typed exceptions with user-facing messages.
- `fixsub/models.py`: dataclasses shared across modules.
- `fixsub/paths.py`: `.fixsub/` directory creation.
- `fixsub/movie.py`: video detection, filename metadata parsing, ASSRT query generation.
- `fixsub/providers/__init__.py`: provider package export.
- `fixsub/providers/assrt_api.py`: ASSRT API search, response parsing, and download wrappers.
- `fixsub/download.py`: stable download file naming.
- `fixsub/extract.py`: zip/rar/7z extraction and subtitle discovery.
- `fixsub/encoding.py`: UTF-8 normalization.
- `fixsub/ffprobe.py`: subprocess wrapper, JSON parsing, audio selection, stream mapping.
- `fixsub/subtitles.py`: SRT/ASS/SSA timing parsing.
- `fixsub/alignment.py`: explainable heuristic alignment scoring.
- `fixsub/sync.py`: `ffs` subprocess wrapper.
- `fixsub/decision.py`: original-vs-synced decision rules.
- `fixsub/ranking.py`: pre-download and final ranking.
- `fixsub/output.py`: Infuse filename generation, backup, final write.
- `fixsub/logging_utils.py`: human log and JSON metadata writing.
- `tests/fixtures/assrt_search.json`: ASSRT search fixture.
- `tests/fixtures/ffprobe_audio.json`: ffprobe fixture.
- `tests/test_cli_smoke.py`: CLI surface tests.
- `tests/test_paths_models.py`: path and serialization tests.
- `tests/test_movie.py`: video detection and query tests.
- `tests/test_assrt_api.py`: ASSRT parsing and client behavior tests.
- `tests/test_download_extract_encoding.py`: download/extract/encoding tests.
- `tests/test_ffprobe.py`: audio parsing and selection tests.
- `tests/test_subtitles_alignment.py`: timing parsing and alignment scoring tests.
- `tests/test_decision_ranking_output.py`: decision, ranking, output tests.
- `tests/test_cli_pipeline.py`: CLI orchestration tests with mocked boundaries.

## Task 1: Project Scaffold and CLI Smoke Test

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `fixsub/__init__.py`
- Create: `fixsub/cli.py`
- Create: `tests/test_cli_smoke.py`

- [ ] **Step 1: Write the failing CLI smoke test**

Create `tests/test_cli_smoke.py`:

```python
from typer.testing import CliRunner

from fixsub.cli import app


def test_help_lists_m1_options() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--dry-run" in result.output
    assert "--audio" in result.output
    assert "--no-sync" in result.output
    assert "--max-candidates" in result.output
    assert "--lang" in result.output
    assert "--providers" in result.output
    assert "--interactive" not in result.output
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_cli_smoke.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fixsub'`.

- [ ] **Step 3: Add package scaffold**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "fixsub"
version = "0.1.0"
description = "On-demand Chinese subtitle search, validation, and sync CLI"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "typer>=0.12.0",
  "rich>=13.0.0",
  "httpx>=0.27.0",
  "charset-normalizer>=3.3.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0.0",
]

[project.scripts]
fixsub = "fixsub.cli:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Create `README.md`:

```markdown
# fixsub

`fixsub` is a macOS-first CLI for searching Chinese subtitles, validating alignment, syncing only when useful, and writing an Infuse-compatible subtitle next to a local movie file.

M1 supports the ASSRT official API, `ffprobe`, `ffsubsync`, and original-vs-synced comparison.
```

Create `fixsub/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `fixsub/cli.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(add_completion=False, no_args_is_help=False)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Process without writing the final subtitle."),
    audio: Optional[str] = typer.Option(None, "--audio", help="Force ffsubsync reference stream, such as a:0."),
    no_sync: bool = typer.Option(False, "--no-sync", help="Skip ffsubsync and rank original candidates only."),
    max_candidates: int = typer.Option(5, "--max-candidates", min=1, help="Maximum candidates to download."),
    lang: str = typer.Option("zh-Hans", "--lang", help="Infuse language suffix for final output."),
    providers: str = typer.Option("assrt", "--providers", help="Comma-separated providers. M1 supports assrt only."),
    debug: bool = typer.Option(False, "--debug", help="Print verbose diagnostics."),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    typer.echo("fixsub M1 pipeline is not implemented yet.")
```

- [ ] **Step 4: Run the smoke test to verify it passes**

Run: `python3 -m pytest tests/test_cli_smoke.py -v`

Expected: PASS.

- [ ] **Step 5: Commit scaffold**

```bash
git add pyproject.toml README.md fixsub/__init__.py fixsub/cli.py tests/test_cli_smoke.py
git commit -m "feat: scaffold fixsub cli"
```

## Task 2: Models, Errors, and Working Directories

**Files:**
- Create: `fixsub/errors.py`
- Create: `fixsub/models.py`
- Create: `fixsub/paths.py`
- Create: `tests/test_paths_models.py`

- [ ] **Step 1: Write failing tests for models and paths**

Create `tests/test_paths_models.py`:

```python
from pathlib import Path

from fixsub.models import AudioStream, RunOptions, SubtitleCandidate
from fixsub.paths import create_workdirs


def test_create_workdirs_creates_expected_tree(tmp_path: Path) -> None:
    workdirs = create_workdirs(tmp_path)

    assert workdirs.root == tmp_path / ".fixsub"
    assert workdirs.downloads.is_dir()
    assert workdirs.candidates.is_dir()
    assert workdirs.synced.is_dir()
    assert workdirs.original.is_dir()
    assert workdirs.logs.is_dir()
    assert workdirs.metadata.is_dir()


def test_audio_stream_maps_to_ffsubsync_id() -> None:
    stream = AudioStream(
        container_index=2,
        audio_index=1,
        codec="ac3",
        language="eng",
        channels=6,
        is_default=True,
    )

    assert stream.ffsubsync_id == "a:1"
    assert "English" in stream.display_name
    assert "AC3" in stream.display_name
    assert "5.1" in stream.display_name
    assert "default" in stream.display_name


def test_candidate_serialization_uses_strings_for_paths(tmp_path: Path) -> None:
    candidate = SubtitleCandidate(
        candidate_id="assrt_001",
        provider="assrt",
        source_title="Movie 1992",
        subtitle_path=tmp_path / "movie.ass",
        language="bilingual",
        format="ass",
        pre_score=12.5,
    )

    assert candidate.to_json()["subtitle_path"].endswith("movie.ass")


def test_run_options_defaults() -> None:
    options = RunOptions()

    assert options.max_candidates == 5
    assert options.lang == "zh-Hans"
    assert options.providers == ["assrt"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_paths_models.py -v`

Expected: FAIL with imports missing for `fixsub.models` and `fixsub.paths`.

- [ ] **Step 3: Implement models and path helpers**

Create `fixsub/errors.py`:

```python
from __future__ import annotations


class FixsubError(Exception):
    """Base class for user-facing fixsub errors."""


class MissingDependencyError(FixsubError):
    def __init__(self, command: str, install_hint: str) -> None:
        super().__init__(f"Missing required command: {command}\nInstall hint: {install_hint}")
        self.command = command
        self.install_hint = install_hint


class ProviderConfigError(FixsubError):
    pass


class NoVideoFoundError(FixsubError):
    pass


class NoCandidatesError(FixsubError):
    pass
```

Create `fixsub/models.py`:

```python
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


@dataclass(frozen=True)
class RunOptions:
    dry_run: bool = False
    audio: str | None = None
    no_sync: bool = False
    max_candidates: int = 5
    lang: str = "zh-Hans"
    providers: list[str] = field(default_factory=lambda: ["assrt"])
    debug: bool = False

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkDirs:
    root: Path
    downloads: Path
    candidates: Path
    synced: Path
    original: Path
    logs: Path
    metadata: Path


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
        language_name = {"eng": "English", "en": "English"}.get(
            (self.language or "").lower(),
            self.language or "unknown language",
        )
        codec_name = (self.codec or "unknown codec").upper()
        if self.channels and self.channels >= 6:
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
```

Create `fixsub/paths.py`:

```python
from __future__ import annotations

from pathlib import Path

from fixsub.models import WorkDirs


def create_workdirs(base_dir: Path) -> WorkDirs:
    root = base_dir / ".fixsub"
    workdirs = WorkDirs(
        root=root,
        downloads=root / "downloads",
        candidates=root / "candidates",
        synced=root / "synced",
        original=root / "original",
        logs=root / "logs",
        metadata=root / "metadata",
    )
    for directory in (
        workdirs.root,
        workdirs.downloads,
        workdirs.candidates,
        workdirs.synced,
        workdirs.original,
        workdirs.logs,
        workdirs.metadata,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return workdirs
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_paths_models.py -v`

Expected: PASS.

- [ ] **Step 5: Commit models and paths**

```bash
git add fixsub/errors.py fixsub/models.py fixsub/paths.py tests/test_paths_models.py
git commit -m "feat: add core models and workdirs"
```

## Task 3: Movie Detection, Metadata, and Search Queries

**Files:**
- Create: `fixsub/movie.py`
- Create: `tests/test_movie.py`

- [ ] **Step 1: Write failing movie tests**

Create `tests/test_movie.py`:

```python
from pathlib import Path

import pytest

from fixsub.errors import NoVideoFoundError
from fixsub.movie import detect_video, generate_search_queries, parse_movie_info


def test_detect_video_chooses_only_video(tmp_path: Path) -> None:
    video = tmp_path / "Movie.1992.1080p.WEB-DL.mkv"
    video.write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")

    assert detect_video(tmp_path) == video


def test_detect_video_chooses_largest_when_multiple(tmp_path: Path) -> None:
    small = tmp_path / "sample.mp4"
    large = tmp_path / "Feature.1992.BluRay.mkv"
    small.write_bytes(b"x")
    large.write_bytes(b"x" * 10)

    assert detect_video(tmp_path) == large


def test_detect_video_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(NoVideoFoundError):
        detect_video(tmp_path)


def test_parse_movie_info_from_release_name() -> None:
    info = parse_movie_info(Path("Unforgiven.1992.1080p.WEB-DL.ENG.DD5.1.H264-GROUP.mkv"))

    assert info.title == "Unforgiven"
    assert info.year == "1992"
    assert info.resolution == "1080p"
    assert info.source == "WEB-DL"
    assert info.release_group == "GROUP"


def test_generate_search_queries_prefers_original_stem() -> None:
    info = parse_movie_info(Path("Unforgiven.1992.1080p.WEB-DL.ENG.DD5.1.H264-GROUP.mkv"))

    assert generate_search_queries(info) == [
        "Unforgiven.1992.1080p.WEB-DL.ENG.DD5.1.H264-GROUP",
        "Unforgiven 1992 WEB-DL",
        "Unforgiven 1992",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_movie.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fixsub.movie'`.

- [ ] **Step 3: Implement movie helpers**

Create `fixsub/movie.py`:

```python
from __future__ import annotations

import re
from pathlib import Path

from fixsub.errors import NoVideoFoundError
from fixsub.models import MovieInfo

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v", ".avi", ".mov"}
SOURCE_PATTERNS = ["WEB-DL", "WEBRip", "BluRay", "BDRip", "HDTV", "DVDRip"]


def detect_video(directory: Path) -> Path:
    videos = [path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS]
    if not videos:
        raise NoVideoFoundError(f"No supported video file found in {directory}")
    if len(videos) == 1:
        return videos[0]
    return max(videos, key=lambda path: path.stat().st_size)


def parse_movie_info(video_path: Path) -> MovieInfo:
    stem = video_path.stem
    spaced = stem.replace(".", " ").replace("_", " ")
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", spaced)
    year = year_match.group(1) if year_match else None
    title = None
    if year_match:
        title = spaced[: year_match.start()].strip() or None
    resolution_match = re.search(r"\b(480p|576p|720p|1080p|2160p|4K)\b", spaced, re.IGNORECASE)
    resolution = resolution_match.group(1) if resolution_match else None
    source = next((source for source in SOURCE_PATTERNS if re.search(source, stem, re.IGNORECASE)), None)
    release_group = None
    if "-" in stem:
        release_group = stem.rsplit("-", 1)[-1] or None
    return MovieInfo(
        path=video_path,
        stem=stem,
        title=title,
        year=year,
        source=source,
        resolution=resolution,
        release_group=release_group,
    )


def generate_search_queries(info: MovieInfo) -> list[str]:
    queries = [info.stem]
    if info.title and info.year and info.source:
        queries.append(f"{info.title} {info.year} {info.source}")
    if info.title and info.year:
        queries.append(f"{info.title} {info.year}")
    deduped: list[str] = []
    for query in queries:
        if query not in deduped:
            deduped.append(query)
    return deduped
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_movie.py -v`

Expected: PASS.

- [ ] **Step 5: Commit movie helpers**

```bash
git add fixsub/movie.py tests/test_movie.py
git commit -m "feat: detect movie files and search queries"
```

## Task 4: ASSRT API Parsing, Ranking Signals, and Client Boundaries

**Files:**
- Create: `fixsub/providers/__init__.py`
- Create: `fixsub/providers/assrt_api.py`
- Create: `fixsub/ranking.py`
- Create: `tests/fixtures/assrt_search.json`
- Create: `tests/test_assrt_api.py`

- [ ] **Step 1: Write ASSRT fixture**

Create `tests/fixtures/assrt_search.json`:

```json
{
  "status": 0,
  "sub": {
    "subs": [
      {
        "id": "1001",
        "native_name": "Unforgiven 1992 WEB-DL bilingual.ass",
        "videoname": "Unforgiven.1992.1080p.WEB-DL-GROUP",
        "lang": {
          "desc": "简英双语"
        },
        "revision": 2,
        "subtype": "ass",
        "download_url": "https://api.assrt.net/v1/sub/download/1001"
      },
      {
        "id": "1002",
        "native_name": "Wrong Movie 2001.srt",
        "videoname": "Wrong.Movie.2001.BluRay",
        "lang": {
          "desc": "英文"
        },
        "subtype": "srt",
        "download_url": "https://api.assrt.net/v1/sub/download/1002"
      }
    ]
  }
}
```

- [ ] **Step 2: Write failing ASSRT tests**

Create `tests/test_assrt_api.py`:

```python
import json
from pathlib import Path

import httpx
import pytest

from fixsub.models import MovieInfo
from fixsub.providers.assrt_api import AssrtClient, parse_search_response
from fixsub.ranking import score_search_result


def test_parse_search_response_extracts_results() -> None:
    payload = json.loads(Path("tests/fixtures/assrt_search.json").read_text(encoding="utf-8"))

    results = parse_search_response(payload)

    assert [result.result_id for result in results] == ["1001", "1002"]
    assert results[0].title == "Unforgiven 1992 WEB-DL bilingual.ass"
    assert results[0].language == "bilingual"
    assert results[0].format == "ass"
    assert results[0].download_url is not None


def test_search_result_scoring_prefers_matching_chinese_ass() -> None:
    payload = json.loads(Path("tests/fixtures/assrt_search.json").read_text(encoding="utf-8"))
    info = MovieInfo(
        path=Path("Unforgiven.1992.1080p.WEB-DL-GROUP.mkv"),
        stem="Unforgiven.1992.1080p.WEB-DL-GROUP",
        title="Unforgiven",
        year="1992",
        source="WEB-DL",
        resolution="1080p",
        release_group="GROUP",
    )
    results = parse_search_response(payload)

    scored = [score_search_result(result, info) for result in results]

    assert scored[0].pre_score > scored[1].pre_score


def test_client_requires_token() -> None:
    with pytest.raises(ValueError, match="ASSRT_TOKEN"):
        AssrtClient(token="")


def test_client_search_uses_token_and_query() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "token=secret-token" in str(request.url)
        assert "q=Unforgiven" in str(request.url)
        payload = json.loads(Path("tests/fixtures/assrt_search.json").read_text(encoding="utf-8"))
        return httpx.Response(200, json=payload)

    client = AssrtClient(token="secret-token", http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    results = client.search("Unforgiven")

    assert results[0].result_id == "1001"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_assrt_api.py -v`

Expected: FAIL with imports missing for `fixsub.providers.assrt_api` and `fixsub.ranking`.

- [ ] **Step 4: Implement ASSRT parsing, search client, and search scoring**

Create `fixsub/providers/__init__.py`:

```python
from fixsub.providers.assrt_api import AssrtClient, parse_search_response

__all__ = ["AssrtClient", "parse_search_response"]
```

Create `fixsub/ranking.py`:

```python
from __future__ import annotations

import re
from dataclasses import replace

from fixsub.models import CandidateDecision, MovieInfo, SearchResult


def _contains(text: str, value: str | None) -> bool:
    return bool(value) and value.lower() in text.lower()


def score_search_result(result: SearchResult, movie: MovieInfo) -> SearchResult:
    haystack = " ".join([result.title, result.raw.get("videoname", "")]).lower()
    score = 0.0
    if result.language in {"bilingual", "zh-Hans", "zh-Hant", "zh"}:
        score += 30
    if result.language == "bilingual":
        score += 5
    if _contains(haystack, movie.title):
        score += 15
    if _contains(haystack, movie.year):
        score += 12
    if _contains(haystack, movie.source):
        score += 8
    if _contains(haystack, movie.resolution):
        score += 4
    if _contains(haystack, movie.release_group):
        score += 6
    if result.format in {"ass", "ssa"}:
        score += 4
    elif result.format == "srt":
        score += 2
    if re.search(r"\bS\d{1,2}E\d{1,2}\b", haystack, re.IGNORECASE):
        score -= 20
    if movie.year and re.search(r"\b(19\d{2}|20\d{2})\b", haystack) and movie.year not in haystack:
        score -= 12
    return replace(result, pre_score=score)


def rank_search_results(results: list[SearchResult], movie: MovieInfo) -> list[SearchResult]:
    return sorted((score_search_result(result, movie) for result in results), key=lambda item: item.pre_score, reverse=True)


def rank_decisions(decisions: list[CandidateDecision]) -> list[CandidateDecision]:
    return sorted(
        decisions,
        key=lambda decision: (
            not decision.is_poor,
            decision.selected_score,
            decision.candidate.pre_score,
            1 if decision.candidate.format in {"ass", "ssa"} else 0,
        ),
        reverse=True,
    )
```

Create `fixsub/providers/assrt_api.py`:

```python
from __future__ import annotations

from typing import Any

import httpx

from fixsub.models import DownloadedFile, SearchResult

ASSRT_API_BASE = "https://api.assrt.net/v1"


def _detect_language(item: dict[str, Any]) -> str | None:
    text = " ".join(
        str(part)
        for part in [
            item.get("native_name"),
            item.get("videoname"),
            item.get("lang", {}).get("desc") if isinstance(item.get("lang"), dict) else item.get("lang"),
        ]
        if part
    )
    if any(token in text for token in ["简英", "双语", "中英", "简体&英文"]):
        return "bilingual"
    if any(token in text for token in ["简体", "简中", "中文字幕", "中文"]):
        return "zh-Hans"
    if any(token in text for token in ["繁体", "繁中"]):
        return "zh-Hant"
    return None


def _detect_format(item: dict[str, Any]) -> str | None:
    text = " ".join(str(part) for part in [item.get("subtype"), item.get("native_name"), item.get("filename")] if part)
    lowered = text.lower()
    for ext in ("ass", "ssa", "srt"):
        if ext in lowered:
            return ext
    return None


def parse_search_response(payload: dict[str, Any]) -> list[SearchResult]:
    raw_items = payload.get("sub", {}).get("subs", [])
    results: list[SearchResult] = []
    for item in raw_items:
        result_id = str(item.get("id") or item.get("subid") or "")
        title = str(item.get("native_name") or item.get("videoname") or result_id)
        if not result_id or not title:
            continue
        download_url = item.get("download_url") or item.get("downloadUrl")
        results.append(
            SearchResult(
                provider="assrt",
                result_id=result_id,
                title=title,
                download_url=str(download_url) if download_url else None,
                detail_url=f"{ASSRT_API_BASE}/sub/detail",
                language=_detect_language(item),
                format=_detect_format(item),
                raw=item,
            )
        )
    return results


class AssrtClient:
    def __init__(self, token: str, http_client: httpx.Client | None = None, base_url: str = ASSRT_API_BASE) -> None:
        if not token:
            raise ValueError("ASSRT_TOKEN is required for ASSRT API access")
        self.token = token
        self.http_client = http_client or httpx.Client(timeout=20.0, follow_redirects=True)
        self.base_url = base_url.rstrip("/")

    def search(self, query: str) -> list[SearchResult]:
        response = self.http_client.get(f"{self.base_url}/sub/search", params={"token": self.token, "q": query})
        response.raise_for_status()
        return parse_search_response(response.json())

    def download(self, result: SearchResult, target_dir) -> DownloadedFile:
        url = result.download_url or f"{self.base_url}/sub/download"
        params = {"token": self.token}
        if not result.download_url:
            params["id"] = result.result_id
        response = self.http_client.get(url, params=params)
        response.raise_for_status()
        suffix = "." + (result.format or "bin")
        target_path = target_dir / f"assrt_{result.result_id}{suffix}"
        target_path.write_bytes(response.content)
        return DownloadedFile(candidate_id=f"assrt_{result.result_id}", provider="assrt", path=target_path, source_url=url)
```

- [ ] **Step 5: Run ASSRT tests**

Run: `python3 -m pytest tests/test_assrt_api.py -v`

Expected: PASS.

- [ ] **Step 6: Commit ASSRT parsing and ranking**

```bash
git add fixsub/providers/__init__.py fixsub/providers/assrt_api.py fixsub/ranking.py tests/fixtures/assrt_search.json tests/test_assrt_api.py
git commit -m "feat: parse and rank assrt results"
```

## Task 5: Download Naming, Archive Extraction, and Encoding Normalization

**Files:**
- Create: `fixsub/download.py`
- Create: `fixsub/extract.py`
- Create: `fixsub/encoding.py`
- Create: `tests/test_download_extract_encoding.py`

- [ ] **Step 1: Write failing tests for local file handling**

Create `tests/test_download_extract_encoding.py`:

```python
from pathlib import Path
from zipfile import ZipFile

from fixsub.download import safe_download_name
from fixsub.encoding import normalize_to_utf8
from fixsub.extract import collect_subtitle_files, extract_archive


def test_safe_download_name_keeps_known_extension() -> None:
    assert safe_download_name("assrt_001", "Movie 中文.ass") == "assrt_001.ass"
    assert safe_download_name("assrt_002", "archive.zip") == "assrt_002.zip"


def test_extract_zip_collects_subtitles_only(tmp_path: Path) -> None:
    archive = tmp_path / "subs.zip"
    out_dir = tmp_path / "out"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("movie.ass", "[Script Info]\n")
        zip_file.writestr("notes.txt", "ignore")

    extracted = extract_archive(archive, out_dir)

    assert extracted == [out_dir / "movie.ass"]


def test_collect_subtitle_files_finds_supported_extensions(tmp_path: Path) -> None:
    (tmp_path / "a.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHi", encoding="utf-8")
    (tmp_path / "b.ass").write_text("[Events]\n", encoding="utf-8")
    (tmp_path / "cover.jpg").write_bytes(b"jpg")

    assert sorted(path.name for path in collect_subtitle_files(tmp_path)) == ["a.srt", "b.ass"]


def test_normalize_to_utf8_writes_candidate_copy(tmp_path: Path) -> None:
    source = tmp_path / "gb.srt"
    target = tmp_path / "candidate.srt"
    source.write_bytes("中文".encode("gb18030"))

    normalize_to_utf8(source, target)

    assert target.read_text(encoding="utf-8") == "中文"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_download_extract_encoding.py -v`

Expected: FAIL with imports missing for local file handling modules.

- [ ] **Step 3: Implement download, extraction, and encoding helpers**

Create `fixsub/download.py`:

```python
from __future__ import annotations

from pathlib import Path

SUPPORTED_DOWNLOAD_EXTENSIONS = {".zip", ".rar", ".7z", ".srt", ".ass", ".ssa"}


def safe_download_name(candidate_id: str, original_name: str) -> str:
    suffix = Path(original_name).suffix.lower()
    if suffix not in SUPPORTED_DOWNLOAD_EXTENSIONS:
        suffix = ".bin"
    return f"{candidate_id}{suffix}"
```

Create `fixsub/extract.py`:

```python
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from zipfile import ZipFile

from fixsub.errors import MissingDependencyError

SUBTITLE_EXTENSIONS = {".ass", ".ssa", ".srt"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z"}


def collect_subtitle_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in SUBTITLE_EXTENSIONS
    )


def extract_archive(archive_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = archive_path.suffix.lower()
    if suffix not in ARCHIVE_EXTENSIONS:
        if archive_path.suffix.lower() in SUBTITLE_EXTENSIONS:
            target = output_dir / archive_path.name
            shutil.copy2(archive_path, target)
            return [target]
        return []
    if suffix == ".zip":
        with ZipFile(archive_path) as zip_file:
            zip_file.extractall(output_dir)
        return collect_subtitle_files(output_dir)
    tool = shutil.which("unar") or shutil.which("unrar")
    if not tool:
        raise MissingDependencyError("unar", "brew install unar")
    if Path(tool).name == "unar":
        command = [tool, "-o", str(output_dir), str(archive_path)]
    else:
        command = [tool, "x", str(archive_path), str(output_dir)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return collect_subtitle_files(output_dir)
```

Create `fixsub/encoding.py`:

```python
from __future__ import annotations

import shutil
from pathlib import Path

from charset_normalizer import from_bytes


def normalize_to_utf8(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    data = source.read_bytes()
    match = from_bytes(data).best()
    if match is None:
        shutil.copy2(source, target)
        return target
    text = str(match)
    target.write_text(text, encoding="utf-8", newline="")
    return target
```

- [ ] **Step 4: Run local file handling tests**

Run: `python3 -m pytest tests/test_download_extract_encoding.py -v`

Expected: PASS.

- [ ] **Step 5: Commit local file handling**

```bash
git add fixsub/download.py fixsub/extract.py fixsub/encoding.py tests/test_download_extract_encoding.py
git commit -m "feat: handle subtitle downloads and extraction"
```

## Task 6: ffprobe Audio Parsing and Selection

**Files:**
- Create: `fixsub/ffprobe.py`
- Create: `tests/fixtures/ffprobe_audio.json`
- Create: `tests/test_ffprobe.py`

- [ ] **Step 1: Write ffprobe fixture**

Create `tests/fixtures/ffprobe_audio.json`:

```json
{
  "format": {
    "duration": "7800.500000"
  },
  "streams": [
    {
      "index": 0,
      "codec_type": "video",
      "codec_name": "h264"
    },
    {
      "index": 1,
      "codec_type": "audio",
      "codec_name": "ac3",
      "channels": 6,
      "tags": {
        "language": "spa"
      },
      "disposition": {
        "default": 1
      }
    },
    {
      "index": 2,
      "codec_type": "audio",
      "codec_name": "aac",
      "channels": 2,
      "tags": {
        "language": "eng"
      },
      "disposition": {
        "default": 0
      }
    }
  ]
}
```

- [ ] **Step 2: Write failing ffprobe tests**

Create `tests/test_ffprobe.py`:

```python
import json
from pathlib import Path

from fixsub.ffprobe import parse_ffprobe_json, select_audio_stream


def test_parse_ffprobe_json_maps_audio_indexes() -> None:
    payload = json.loads(Path("tests/fixtures/ffprobe_audio.json").read_text(encoding="utf-8"))

    probe = parse_ffprobe_json(payload)

    assert probe.duration_seconds == 7800.5
    assert [stream.container_index for stream in probe.audio_streams] == [1, 2]
    assert [stream.ffsubsync_id for stream in probe.audio_streams] == ["a:0", "a:1"]


def test_select_audio_stream_prefers_english_over_default() -> None:
    payload = json.loads(Path("tests/fixtures/ffprobe_audio.json").read_text(encoding="utf-8"))
    probe = parse_ffprobe_json(payload)

    selected = select_audio_stream(probe.audio_streams)

    assert selected.language == "eng"
    assert selected.ffsubsync_id == "a:1"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ffprobe.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fixsub.ffprobe'`.

- [ ] **Step 4: Implement ffprobe parsing and subprocess wrapper**

Create `fixsub/ffprobe.py`:

```python
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
```

- [ ] **Step 5: Run ffprobe tests**

Run: `python3 -m pytest tests/test_ffprobe.py -v`

Expected: PASS.

- [ ] **Step 6: Commit ffprobe support**

```bash
git add fixsub/ffprobe.py tests/fixtures/ffprobe_audio.json tests/test_ffprobe.py
git commit -m "feat: parse and select ffprobe audio streams"
```

## Task 7: Subtitle Timing Parsing and Alignment Scoring

**Files:**
- Create: `fixsub/subtitles.py`
- Create: `fixsub/alignment.py`
- Create: `tests/test_subtitles_alignment.py`

- [ ] **Step 1: Write failing subtitle and alignment tests**

Create `tests/test_subtitles_alignment.py`:

```python
from pathlib import Path

from fixsub.alignment import score_alignment
from fixsub.subtitles import parse_subtitle_intervals


def test_parse_srt_intervals(tmp_path: Path) -> None:
    subtitle = tmp_path / "movie.srt"
    subtitle.write_text(
        "1\n00:00:05,000 --> 00:00:07,000\nHello\n\n2\n00:01:00,500 --> 00:01:02,000\nWorld\n",
        encoding="utf-8",
    )

    intervals = parse_subtitle_intervals(subtitle)

    assert intervals == [(5.0, 7.0), (60.5, 62.0)]


def test_parse_ass_intervals(tmp_path: Path) -> None:
    subtitle = tmp_path / "movie.ass"
    subtitle.write_text(
        "[Events]\nDialogue: 0,0:00:05.00,0:00:07.00,Default,,0,0,0,,Hello\n",
        encoding="utf-8",
    )

    intervals = parse_subtitle_intervals(subtitle)

    assert intervals == [(5.0, 7.0)]


def test_alignment_scores_plausible_subtitle_high(tmp_path: Path) -> None:
    subtitle = tmp_path / "movie.srt"
    subtitle.write_text(
        "1\n00:02:00,000 --> 00:02:02,000\nA\n\n2\n00:30:00,000 --> 00:30:03,000\nB\n\n3\n01:40:00,000 --> 01:40:04,000\nC\n",
        encoding="utf-8",
    )

    score = score_alignment(subtitle, duration_seconds=7200)

    assert score.score >= 0.7


def test_alignment_scores_out_of_video_subtitle_low(tmp_path: Path) -> None:
    subtitle = tmp_path / "bad.srt"
    subtitle.write_text(
        "1\n03:00:00,000 --> 03:00:02,000\nToo late\n",
        encoding="utf-8",
    )

    score = score_alignment(subtitle, duration_seconds=7200)

    assert score.score < 0.5
    assert any("outside video" in reason for reason in score.reasons)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_subtitles_alignment.py -v`

Expected: FAIL with imports missing for `fixsub.subtitles` and `fixsub.alignment`.

- [ ] **Step 3: Implement subtitle parsers and heuristic scoring**

Create `fixsub/subtitles.py`:

```python
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
```

Create `fixsub/alignment.py`:

```python
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
```

- [ ] **Step 4: Run subtitle and alignment tests**

Run: `python3 -m pytest tests/test_subtitles_alignment.py -v`

Expected: PASS.

- [ ] **Step 5: Commit subtitle parsing and alignment scoring**

```bash
git add fixsub/subtitles.py fixsub/alignment.py tests/test_subtitles_alignment.py
git commit -m "feat: score subtitle alignment heuristically"
```

## Task 8: ffsubsync Wrapper and Original-vs-Synced Decisions

**Files:**
- Create: `fixsub/sync.py`
- Create: `fixsub/decision.py`
- Create: `tests/test_decision_ranking_output.py`

- [ ] **Step 1: Write failing decision tests**

Create `tests/test_decision_ranking_output.py` with decision tests first:

```python
from pathlib import Path

from fixsub.decision import decide_candidate_version
from fixsub.models import AlignmentScore, SubtitleCandidate, SyncResult


def make_candidate(tmp_path: Path) -> SubtitleCandidate:
    subtitle = tmp_path / "candidate.ass"
    subtitle.write_text("[Events]\n", encoding="utf-8")
    return SubtitleCandidate(
        candidate_id="assrt_001",
        provider="assrt",
        source_title="Unforgiven",
        subtitle_path=subtitle,
        language="bilingual",
        format="ass",
        pre_score=50,
    )


def test_decision_skips_sync_when_original_is_excellent(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)

    decision = decide_candidate_version(
        candidate=candidate,
        original_score=AlignmentScore(0.92, []),
        sync_result=SyncResult(attempted=False, succeeded=False),
        synced_score=None,
    )

    assert decision.selected_version == "original"
    assert decision.selected_path == candidate.subtitle_path
    assert decision.decision_reason == "Original subtitle already aligned; sync skipped."


def test_decision_selects_synced_when_materially_better(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    synced = tmp_path / "candidate.synced.ass"
    synced.write_text("[Events]\n", encoding="utf-8")

    decision = decide_candidate_version(
        candidate=candidate,
        original_score=AlignmentScore(0.64, []),
        sync_result=SyncResult(attempted=True, succeeded=True, output_path=synced),
        synced_score=AlignmentScore(0.91, []),
    )

    assert decision.selected_version == "synced"
    assert decision.selected_path == synced
    assert decision.is_poor is False


def test_decision_keeps_original_when_synced_is_not_better(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    synced = tmp_path / "candidate.synced.ass"
    synced.write_text("[Events]\n", encoding="utf-8")

    decision = decide_candidate_version(
        candidate=candidate,
        original_score=AlignmentScore(0.89, []),
        sync_result=SyncResult(attempted=True, succeeded=True, output_path=synced),
        synced_score=AlignmentScore(0.87, []),
    )

    assert decision.selected_version == "original"
    assert decision.decision_reason == "Synced version did not improve alignment."


def test_decision_marks_candidate_poor_when_both_scores_are_low(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    synced = tmp_path / "candidate.synced.ass"
    synced.write_text("[Events]\n", encoding="utf-8")

    decision = decide_candidate_version(
        candidate=candidate,
        original_score=AlignmentScore(0.41, []),
        sync_result=SyncResult(attempted=True, succeeded=True, output_path=synced),
        synced_score=AlignmentScore(0.45, []),
    )

    assert decision.is_poor is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_decision_ranking_output.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'fixsub.decision'`.

- [ ] **Step 3: Implement decision logic and sync wrapper**

Create `fixsub/decision.py`:

```python
from __future__ import annotations

from fixsub.models import AlignmentScore, CandidateDecision, SubtitleCandidate, SyncResult

EXCELLENT_ALIGNMENT = 0.90
SYNC_IMPROVEMENT_THRESHOLD = 0.08
POOR_ALIGNMENT = 0.50


def decide_candidate_version(
    candidate: SubtitleCandidate,
    original_score: AlignmentScore,
    sync_result: SyncResult,
    synced_score: AlignmentScore | None,
) -> CandidateDecision:
    if original_score.score >= EXCELLENT_ALIGNMENT and not sync_result.attempted:
        selected_version = "original"
        selected_path = candidate.subtitle_path
        selected_score = original_score.score
        reason = "Original subtitle already aligned; sync skipped."
    elif sync_result.succeeded and synced_score and sync_result.output_path and synced_score.score >= original_score.score + SYNC_IMPROVEMENT_THRESHOLD:
        selected_version = "synced"
        selected_path = sync_result.output_path
        selected_score = synced_score.score
        reason = f"Synced score improved by {synced_score.score - original_score.score:.2f}."
    else:
        selected_version = "original"
        selected_path = candidate.subtitle_path
        selected_score = original_score.score
        if sync_result.attempted and not sync_result.succeeded:
            reason = "Sync failed; original candidate kept."
        elif sync_result.attempted:
            reason = "Synced version did not improve alignment."
        else:
            reason = "Sync skipped; original candidate kept."
    synced_value = synced_score.score if synced_score else None
    is_poor = original_score.score < POOR_ALIGNMENT and (synced_value is None or synced_value < POOR_ALIGNMENT)
    return CandidateDecision(
        candidate=candidate,
        original_score=original_score,
        synced_score=synced_score,
        sync_result=sync_result,
        selected_version=selected_version,
        selected_path=selected_path,
        selected_score=selected_score,
        is_poor=is_poor,
        decision_reason=reason,
    )
```

Create `fixsub/sync.py`:

```python
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from fixsub.errors import MissingDependencyError
from fixsub.models import SyncResult


def synced_output_path(candidate_path: Path, synced_dir: Path) -> Path:
    return synced_dir / f"{candidate_path.stem}.synced{candidate_path.suffix}"


def run_ffsubsync(video_path: Path, subtitle_path: Path, output_path: Path, audio_stream: str) -> SyncResult:
    if not shutil.which("ffs"):
        raise MissingDependencyError("ffs", "python3 -m pip install ffsubsync")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffs",
        str(video_path),
        "--reference-stream",
        audio_stream,
        "--skip-sync-on-low-quality",
        "-i",
        str(subtitle_path),
        "-o",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return SyncResult(attempted=True, succeeded=False, output_path=None, error=result.stderr.strip() or result.stdout.strip())
    return SyncResult(attempted=True, succeeded=True, output_path=output_path, error=None)
```

- [ ] **Step 4: Run decision tests**

Run: `python3 -m pytest tests/test_decision_ranking_output.py -v`

Expected: PASS for the decision tests present in the file.

- [ ] **Step 5: Commit sync decisions**

```bash
git add fixsub/sync.py fixsub/decision.py tests/test_decision_ranking_output.py
git commit -m "feat: compare original and synced subtitles"
```

## Task 9: Output, Backups, Ranking, and Metadata Logs

**Files:**
- Modify: `tests/test_decision_ranking_output.py`
- Create: `fixsub/output.py`
- Create: `fixsub/logging_utils.py`
- Modify: `fixsub/ranking.py`

- [ ] **Step 1: Add failing output, ranking, and metadata tests**

Append to `tests/test_decision_ranking_output.py`:

```python
import json

from fixsub.logging_utils import write_results_json
from fixsub.output import final_subtitle_path, write_final_subtitle
from fixsub.ranking import rank_decisions


def test_final_subtitle_path_uses_infuse_language_suffix(tmp_path: Path) -> None:
    video = tmp_path / "Movie.1992.1080p.WEB-DL.mkv"

    assert final_subtitle_path(video, "zh-Hans", ".ass") == tmp_path / "Movie.1992.1080p.WEB-DL.zh-Hans.ass"


def test_write_final_subtitle_backs_up_existing_file(tmp_path: Path) -> None:
    video = tmp_path / "Movie.mkv"
    selected = tmp_path / "selected.ass"
    selected.write_text("new", encoding="utf-8")
    final = tmp_path / "Movie.zh-Hans.ass"
    final.write_text("old", encoding="utf-8")
    backup_dir = tmp_path / ".fixsub" / "original"

    written = write_final_subtitle(selected, video, "zh-Hans", backup_dir)

    assert written == final
    assert final.read_text(encoding="utf-8") == "new"
    backups = list(backup_dir.glob("*.Movie.zh-Hans.ass"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old"


def test_rank_decisions_prefers_non_poor_high_score(tmp_path: Path) -> None:
    good = make_candidate(tmp_path)
    poor = make_candidate(tmp_path)
    poor = SubtitleCandidate(
        candidate_id="assrt_002",
        provider="assrt",
        source_title="Other",
        subtitle_path=poor.subtitle_path,
        language="zh-Hans",
        format="srt",
        pre_score=100,
    )
    good_decision = decide_candidate_version(good, AlignmentScore(0.82, []), SyncResult(False, False), None)
    poor_decision = decide_candidate_version(poor, AlignmentScore(0.40, []), SyncResult(False, False), None)

    ranked = rank_decisions([poor_decision, good_decision])

    assert ranked[0].candidate.candidate_id == "assrt_001"


def test_write_results_json_serializes_paths(tmp_path: Path) -> None:
    target = tmp_path / "metadata" / "results.json"

    write_results_json(target, {"path": tmp_path / "Movie.mkv", "status": "ok"})

    assert json.loads(target.read_text(encoding="utf-8"))["path"].endswith("Movie.mkv")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_decision_ranking_output.py -v`

Expected: FAIL with imports missing for `fixsub.output` and `fixsub.logging_utils`.

- [ ] **Step 3: Implement output and metadata helpers**

Create `fixsub/output.py`:

```python
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def final_subtitle_path(video_path: Path, lang: str, subtitle_suffix: str) -> Path:
    suffix = subtitle_suffix if subtitle_suffix.startswith(".") else f".{subtitle_suffix}"
    return video_path.with_name(f"{video_path.stem}.{lang}{suffix}")


def write_final_subtitle(selected_subtitle: Path, video_path: Path, lang: str, backup_dir: Path) -> Path:
    final_path = final_subtitle_path(video_path, lang, selected_subtitle.suffix)
    backup_dir.mkdir(parents=True, exist_ok=True)
    if final_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_dir / f"{timestamp}.{final_path.name}"
        shutil.copy2(final_path, backup_path)
    shutil.copy2(selected_subtitle, final_path)
    return final_path
```

Create `fixsub/logging_utils.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_results_json(target: Path, payload: dict[str, Any]) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, default=_json_default, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")
```

- [ ] **Step 4: Run output and metadata tests**

Run: `python3 -m pytest tests/test_decision_ranking_output.py -v`

Expected: PASS.

- [ ] **Step 5: Commit output and metadata helpers**

```bash
git add fixsub/output.py fixsub/logging_utils.py fixsub/ranking.py tests/test_decision_ranking_output.py
git commit -m "feat: write final subtitles and metadata"
```

## Task 10: CLI Pipeline Orchestration with Mocked Boundaries

**Files:**
- Modify: `fixsub/cli.py`
- Create: `tests/test_cli_pipeline.py`

- [ ] **Step 1: Write failing CLI orchestration tests**

Create `tests/test_cli_pipeline.py`:

```python
from pathlib import Path

from typer.testing import CliRunner

from fixsub.cli import app
from fixsub.ffprobe import ProbeResult
from fixsub.models import (
    AlignmentScore,
    AudioStream,
    DownloadedFile,
    SearchResult,
)


def test_cli_rejects_unimplemented_provider(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["--providers", "subhd"])

    assert result.exit_code != 0
    assert "M1 supports assrt only" in result.output


def test_cli_runs_dry_run_pipeline(tmp_path: Path, monkeypatch) -> None:
    video = tmp_path / "Unforgiven.1992.1080p.WEB-DL-GROUP.mkv"
    video.write_bytes(b"video")
    subtitle = tmp_path / ".fixsub" / "candidates" / "assrt_1001.ass"
    subtitle.parent.mkdir(parents=True)
    subtitle.write_text("[Events]\nDialogue: 0,0:02:00.00,0:02:03.00,Default,,0,0,0,,Hi\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ASSRT_TOKEN", "secret")

    class FakeClient:
        def __init__(self, token: str) -> None:
            assert token == "secret"

        def search(self, query: str) -> list[SearchResult]:
            return [
                SearchResult(
                    provider="assrt",
                    result_id="1001",
                    title="Unforgiven 1992 WEB-DL bilingual.ass",
                    download_url="https://example.test/1001",
                    language="bilingual",
                    format="ass",
                    pre_score=10,
                )
            ]

        def download(self, result: SearchResult, target_dir: Path) -> DownloadedFile:
            return DownloadedFile(candidate_id="assrt_1001", provider="assrt", path=subtitle, source_url=result.download_url)

    monkeypatch.setattr("fixsub.cli.AssrtClient", FakeClient)
    monkeypatch.setattr("fixsub.cli.extract_archive", lambda path, out_dir: [subtitle])
    monkeypatch.setattr("fixsub.cli.normalize_to_utf8", lambda source, target: target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8") or target)
    monkeypatch.setattr(
        "fixsub.cli.probe_video",
        lambda path: ProbeResult(
            duration_seconds=7200,
            audio_streams=[AudioStream(1, 0, "ac3", "eng", 6, True)],
            raw={},
        ),
    )
    monkeypatch.setattr("fixsub.cli.score_alignment", lambda path, duration_seconds: AlignmentScore(0.92, []))

    result = CliRunner().invoke(app, ["--dry-run"])

    assert result.exit_code == 0
    assert "Selected reference audio: a:0" in result.output
    assert "Dry run complete" in result.output
    assert (tmp_path / ".fixsub" / "metadata" / "results.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_cli_pipeline.py -v`

Expected: FAIL because `cli.py` still prints the initial scaffold message and has no pipeline.

- [ ] **Step 3: Implement CLI orchestration**

Replace `fixsub/cli.py` with:

```python
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from fixsub.alignment import score_alignment
from fixsub.decision import EXCELLENT_ALIGNMENT, decide_candidate_version
from fixsub.encoding import normalize_to_utf8
from fixsub.errors import FixsubError, NoCandidatesError, ProviderConfigError
from fixsub.extract import extract_archive
from fixsub.ffprobe import probe_video, select_audio_stream
from fixsub.logging_utils import append_log, write_results_json
from fixsub.models import RunOptions, SubtitleCandidate, SyncResult
from fixsub.movie import detect_video, generate_search_queries, parse_movie_info
from fixsub.output import write_final_subtitle
from fixsub.paths import create_workdirs
from fixsub.providers.assrt_api import AssrtClient
from fixsub.ranking import rank_decisions, rank_search_results
from fixsub.sync import run_ffsubsync, synced_output_path

app = typer.Typer(add_completion=False, no_args_is_help=False)
console = Console()


def _parse_providers(value: str) -> list[str]:
    providers = [item.strip() for item in value.split(",") if item.strip()]
    if providers != ["assrt"]:
        raise ProviderConfigError("M1 supports assrt only.")
    return providers


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Process without writing the final subtitle."),
    audio: Optional[str] = typer.Option(None, "--audio", help="Force ffsubsync reference stream, such as a:0."),
    no_sync: bool = typer.Option(False, "--no-sync", help="Skip ffsubsync and rank original candidates only."),
    max_candidates: int = typer.Option(5, "--max-candidates", min=1, help="Maximum candidates to download."),
    lang: str = typer.Option("zh-Hans", "--lang", help="Infuse language suffix for final output."),
    providers: str = typer.Option("assrt", "--providers", help="Comma-separated providers. M1 supports assrt only."),
    debug: bool = typer.Option(False, "--debug", help="Print verbose diagnostics."),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    try:
        options = RunOptions(
            dry_run=dry_run,
            audio=audio,
            no_sync=no_sync,
            max_candidates=max_candidates,
            lang=lang,
            providers=_parse_providers(providers),
            debug=debug,
        )
        result = run_pipeline(Path.cwd(), options)
        console.print(result["message"])
    except FixsubError as error:
        console.print(str(error))
        raise typer.Exit(1) from error


def run_pipeline(base_dir: Path, options: RunOptions) -> dict:
    workdirs = create_workdirs(base_dir)
    log_path = workdirs.logs / "fixsub.log"
    video_path = detect_video(base_dir)
    movie = parse_movie_info(video_path)
    append_log(log_path, f"Video: {video_path}")
    token = os.environ.get("ASSRT_TOKEN", "")
    if not token:
        raise ProviderConfigError("ASSRT_TOKEN is required for ASSRT API access.")
    client = AssrtClient(token=token)
    queries = generate_search_queries(movie)
    search_results = []
    for query in queries:
        try:
            search_results.extend(client.search(query))
        except Exception as exc:
            append_log(log_path, f"ASSRT query failed for {query}: {exc}")
    ranked_results = rank_search_results(search_results, movie)
    if not ranked_results:
        raise NoCandidatesError("No ASSRT subtitle results found.")
    probe = probe_video(video_path)
    selected_audio = options.audio or select_audio_stream(probe.audio_streams).ffsubsync_id
    console.print(f"Selected reference audio: {selected_audio}")
    decisions = []
    downloaded = []
    candidates = []
    for result in ranked_results[: options.max_candidates]:
        try:
            downloaded_file = client.download(result, workdirs.downloads)
            downloaded.append(downloaded_file)
            extracted_files = extract_archive(downloaded_file.path, workdirs.candidates / downloaded_file.candidate_id)
            for extracted in extracted_files:
                candidate_path = workdirs.candidates / f"{downloaded_file.candidate_id}{extracted.suffix.lower()}"
                normalize_to_utf8(extracted, candidate_path)
                candidate = SubtitleCandidate(
                    candidate_id=downloaded_file.candidate_id,
                    provider="assrt",
                    source_title=result.title,
                    subtitle_path=candidate_path,
                    language=result.language,
                    format=candidate_path.suffix.lower().lstrip("."),
                    pre_score=result.pre_score,
                )
                candidates.append(candidate)
                original_score = score_alignment(candidate.subtitle_path, probe.duration_seconds)
                sync_result = SyncResult(attempted=False, succeeded=False)
                synced_score = None
                if not options.no_sync and original_score.score < EXCELLENT_ALIGNMENT:
                    output_path = synced_output_path(candidate.subtitle_path, workdirs.synced)
                    try:
                        sync_result = run_ffsubsync(video_path, candidate.subtitle_path, output_path, selected_audio)
                    except FixsubError as exc:
                        sync_result = SyncResult(attempted=True, succeeded=False, error=str(exc))
                    if sync_result.succeeded and sync_result.output_path:
                        synced_score = score_alignment(sync_result.output_path, probe.duration_seconds)
                decisions.append(decide_candidate_version(candidate, original_score, sync_result, synced_score))
        except Exception as exc:
            append_log(log_path, f"Candidate failed for result {result.result_id}: {exc}")
    if not decisions:
        raise NoCandidatesError("No downloadable or extractable ASSRT candidates.")
    ranked_decisions = rank_decisions(decisions)
    best = ranked_decisions[0]
    final_output = None
    message = "No high-confidence subtitle found. Candidates were saved for manual review."
    if not best.is_poor:
        if options.dry_run:
            message = "Dry run complete. Best subtitle selected but final output was not written."
        else:
            final_output = write_final_subtitle(best.selected_path, video_path, options.lang, workdirs.original)
            message = f"Applied best subtitle: {final_output}"
    metadata = {
        "video": movie.to_json(),
        "options": options.to_json(),
        "queries": queries,
        "downloaded": [item.to_json() for item in downloaded],
        "candidates": [item.to_json() for item in candidates],
        "selected_audio": selected_audio,
        "decisions": [item.to_json() for item in ranked_decisions],
        "final_output": final_output,
        "message": message,
    }
    write_results_json(workdirs.metadata / "results.json", metadata)
    return {"message": message, "metadata": metadata}
```

- [ ] **Step 4: Run CLI orchestration tests**

Run: `python3 -m pytest tests/test_cli_pipeline.py -v`

Expected: PASS.

- [ ] **Step 5: Run all tests**

Run: `python3 -m pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit CLI orchestration**

```bash
git add fixsub/cli.py tests/test_cli_pipeline.py
git commit -m "feat: orchestrate fixsub mvp pipeline"
```

## Task 11: README, Install Notes, and Manual Acceptance Checklist

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace README with complete M1 usage docs**

Replace `README.md` with:

```markdown
# fixsub

`fixsub` is a macOS-first CLI for on-demand Chinese subtitle search, validation, sync, and application inside a single movie folder.

M1 supports:

- ASSRT official API through `ASSRT_TOKEN`
- video detection in the current folder
- ASSRT search and download
- archive extraction for `.zip`, `.rar`, and `.7z`
- subtitle normalization to UTF-8
- audio detection through `ffprobe`
- optional sync through `ffsubsync`
- original-vs-synced scoring and comparison
- Infuse-compatible output naming

## Install

```bash
python3 -m pip install -e ".[dev]"
brew install ffmpeg unar
python3 -m pip install ffsubsync
```

Set your ASSRT token:

```bash
export ASSRT_TOKEN="your-token"
```

## Usage

Run from inside a movie folder:

```bash
fixsub
```

Supported M1 options:

```bash
fixsub --dry-run
fixsub --audio a:0
fixsub --no-sync
fixsub --max-candidates 5
fixsub --lang zh-Hans
fixsub --providers assrt
fixsub --debug
```

M1 does not implement SubHD, ASSRT web fallback, interactive mode, library scanning, Whisper generation, translation, or Web UI.

## Output

The final subtitle is written next to the video:

```text
<video_stem>.zh-Hans.<ext>
```

Existing subtitles at that path are copied to:

```text
.fixsub/original/<timestamp>.<filename>
```

Run artifacts are preserved under:

```text
.fixsub/downloads/
.fixsub/candidates/
.fixsub/synced/
.fixsub/logs/fixsub.log
.fixsub/metadata/results.json
```

## Manual Acceptance

1. Put one movie file in a local test folder.
2. Run `fixsub --dry-run`.
3. Confirm `.fixsub/metadata/results.json` is written.
4. Run `fixsub` with a movie that has ASSRT Chinese subtitles.
5. Confirm selected audio is printed as `a:0`, `a:1`, or another ffsubsync stream id.
6. Confirm excellent original subtitles skip sync.
7. Confirm a materially better synced subtitle is selected when its score improves by at least `0.08`.
8. Confirm worse synced subtitles do not replace originals.
9. Confirm existing final subtitles are backed up before replacement.
```

- [ ] **Step 2: Run all tests after docs update**

Run: `python3 -m pytest -v`

Expected: PASS.

- [ ] **Step 3: Commit README**

```bash
git add README.md
git commit -m "docs: document fixsub mvp usage"
```

## Task 12: Final Verification and Packaging Check

**Files:**
- Modify only if verification reveals a concrete failing test or packaging error.

- [ ] **Step 1: Run full test suite**

Run: `python3 -m pytest -v`

Expected: all tests PASS.

- [ ] **Step 2: Verify console script imports**

Run: `python3 -m pip install -e ".[dev]"`

Expected: editable install succeeds and reports `Successfully installed fixsub-0.1.0`.

- [ ] **Step 3: Verify CLI help**

Run: `fixsub --help`

Expected: output includes `--dry-run`, `--audio`, `--no-sync`, `--max-candidates`, `--lang`, `--providers`, and `--debug`.

- [ ] **Step 4: Verify dry-run missing token error in an empty temp movie folder**

Run these commands from a temporary folder containing one small dummy `.mkv` file:

```bash
unset ASSRT_TOKEN
touch Movie.1992.1080p.WEB-DL.mkv
fixsub --dry-run
```

Expected: command exits non-zero and prints `ASSRT_TOKEN is required for ASSRT API access.`

- [ ] **Step 5: Commit verification fixes if files changed**

If files changed during verification:

```bash
git add <changed-files>
git commit -m "fix: complete mvp verification"
```

If no files changed, do not create an empty commit.

## Self-Review Checklist

- Spec coverage:
  - Video detection: Task 3 and Task 10.
  - ASSRT API: Task 4 and Task 10.
  - Download, extraction, normalization: Task 5 and Task 10.
  - ffprobe selection and `a:x` mapping: Task 6 and Task 10.
  - Alignment score: Task 7 and Task 10.
  - ffsubsync wrapper: Task 8 and Task 10.
  - Original-vs-synced comparison: Task 8.
  - Infuse output and backups: Task 9.
  - Logs and metadata: Task 9 and Task 10.
  - CLI options: Task 1, Task 10, and Task 11.
  - Deterministic tests: Tasks 1 through 10.
- Red-flag scan: this plan contains no unfinished markers, incomplete sections, or unspecified test steps.
- Type consistency:
  - `RunOptions`, `AudioStream`, `SearchResult`, `DownloadedFile`, `SubtitleCandidate`, `AlignmentScore`, `SyncResult`, and `CandidateDecision` are defined in Task 2 before consumers use them.
  - `ProbeResult` is defined in Task 6 and imported from `fixsub.ffprobe` by the CLI test in Task 10.
  - `rank_decisions` is defined in Task 4 and exercised after decision objects exist in Task 9.
