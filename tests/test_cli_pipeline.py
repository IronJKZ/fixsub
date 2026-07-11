import json
from pathlib import Path

from typer.testing import CliRunner

from fixsub.cli import app
from fixsub.errors import FixsubError, MissingDependencyError
from fixsub.ffprobe import ProbeResult
from fixsub.models import (
    AlignmentScore,
    AudioStream,
    DownloadedFile,
    SearchResult,
    SyncResult,
)


METADATA_KEYS = {
    "video",
    "options",
    "queries",
    "downloaded",
    "candidates",
    "selected_audio",
    "decisions",
    "final_output",
    "message",
}


def _write_video(tmp_path: Path) -> Path:
    video = tmp_path / "Unforgiven.1992.1080p.WEB-DL-GROUP.mkv"
    video.write_bytes(b"video")
    return video


def _read_metadata(tmp_path: Path) -> dict:
    with (tmp_path / ".fixsub" / "metadata" / "results.json").open(encoding="utf-8") as file:
        return json.load(file)


def test_cli_rejects_unknown_provider(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["--providers", "opensubtitles"])

    assert result.exit_code != 0
    assert "Unsupported provider: opensubtitles" in result.output


def test_cli_accepts_subhd_provider_without_assrt_token(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
    subtitle = tmp_path / ".fixsub" / "candidates" / "subhd_kAqdvK.srt"
    subtitle.parent.mkdir(parents=True)
    subtitle.write_text("1\n00:02:00,000 --> 00:02:03,000\nHi\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ASSRT_TOKEN", raising=False)

    class FakeSubhdClient:
        def search(self, query: str) -> list[SearchResult]:
            return [
                SearchResult(
                    provider="subhd",
                    result_id="kAqdvK",
                    title="大地的女儿 Nell.1994.1080p.BluRay.x265-RARBG",
                    download_url="https://subhd.tv/down/kAqdvK",
                    detail_url="https://subhd.tv/a/kAqdvK",
                    language="bilingual",
                    format="srt",
                    raw={"version": "Nell.1994.1080p.BluRay.x265-RARBG"},
                )
            ]

        def download(self, result: SearchResult, target_dir: Path) -> DownloadedFile:
            return DownloadedFile(
                candidate_id="subhd_kAqdvK",
                provider="subhd",
                path=subtitle,
                source_url=result.download_url,
            )

    monkeypatch.setattr("fixsub.providers.registry.SubhdClient", FakeSubhdClient)
    monkeypatch.setattr("fixsub.cli.extract_archive", lambda path, out_dir: [subtitle])
    monkeypatch.setattr(
        "fixsub.cli.normalize_to_utf8",
        lambda source, target: target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8") or target,
    )
    monkeypatch.setattr(
        "fixsub.cli.probe_video",
        lambda path: ProbeResult(
            duration_seconds=7200,
            audio_streams=[AudioStream(1, 0, "ac3", "eng", 6, True)],
            raw={},
        ),
    )
    monkeypatch.setattr("fixsub.cli.score_alignment", lambda path, duration_seconds: AlignmentScore(0.92, []))

    result = CliRunner().invoke(app, ["--dry-run", "--no-sync", "--providers", "subhd"])

    assert result.exit_code == 0
    assert "Dry run complete" in result.output
    metadata = _read_metadata(tmp_path)
    assert metadata["downloaded"][0]["provider"] == "subhd"


def test_cli_default_skips_assrt_when_token_missing_and_subhd_is_available(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
    subtitle = tmp_path / ".fixsub" / "candidates" / "subhd_kAqdvK.srt"
    subtitle.parent.mkdir(parents=True)
    subtitle.write_text("1\n00:02:00,000 --> 00:02:03,000\nHi\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ASSRT_TOKEN", raising=False)

    class FakeSubhdClient:
        def search(self, query: str) -> list[SearchResult]:
            return [
                SearchResult(
                    provider="subhd",
                    result_id="kAqdvK",
                    title="Nell.1994.1080p.BluRay.x265-RARBG",
                    language="bilingual",
                    format="srt",
                    raw={"version": "Nell.1994.1080p.BluRay.x265-RARBG"},
                )
            ]

        def download(self, result: SearchResult, target_dir: Path) -> DownloadedFile:
            return DownloadedFile(
                candidate_id="subhd_kAqdvK",
                provider="subhd",
                path=subtitle,
                source_url=result.download_url,
            )

    monkeypatch.setattr("fixsub.providers.registry.SubhdClient", FakeSubhdClient)
    monkeypatch.setattr("fixsub.cli.extract_archive", lambda path, out_dir: [subtitle])
    monkeypatch.setattr(
        "fixsub.cli.normalize_to_utf8",
        lambda source, target: target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8") or target,
    )
    monkeypatch.setattr(
        "fixsub.cli.probe_video",
        lambda path: ProbeResult(
            duration_seconds=7200,
            audio_streams=[AudioStream(1, 0, "ac3", "eng", 6, True)],
            raw={},
        ),
    )
    monkeypatch.setattr("fixsub.cli.score_alignment", lambda path, duration_seconds: AlignmentScore(0.92, []))

    result = CliRunner().invoke(app, ["--dry-run", "--no-sync"])

    assert result.exit_code == 0
    assert "Dry run complete" in result.output
    assert "ASSRT skipped: ASSRT_TOKEN is required for ASSRT API access." in (
        tmp_path / ".fixsub" / "logs" / "fixsub.log"
    ).read_text(encoding="utf-8")


def test_cli_runs_dry_run_pipeline(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
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

    monkeypatch.setattr("fixsub.providers.registry.AssrtClient", FakeClient)
    monkeypatch.setattr("fixsub.cli.extract_archive", lambda path, out_dir: [subtitle])
    monkeypatch.setattr(
        "fixsub.cli.normalize_to_utf8",
        lambda source, target: target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8") or target,
    )
    monkeypatch.setattr(
        "fixsub.cli.probe_video",
        lambda path: ProbeResult(
            duration_seconds=7200,
            audio_streams=[AudioStream(1, 0, "ac3", "eng", 6, True)],
            raw={},
        ),
    )
    monkeypatch.setattr("fixsub.cli.score_alignment", lambda path, duration_seconds: AlignmentScore(1.0, []))

    def fake_sync(video_path: Path, subtitle_path: Path, output_path: Path, audio_stream: str) -> SyncResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(subtitle_path.read_text(encoding="utf-8"), encoding="utf-8")
        return SyncResult(
            attempted=True,
            succeeded=True,
            output_path=output_path,
            ffsubsync_score=100.0,
            offset_seconds=2.0,
            framerate_scale=1.0,
        )

    monkeypatch.setattr("fixsub.cli.run_ffsubsync", fake_sync)

    result = CliRunner().invoke(app, ["--dry-run", "--providers", "assrt"])

    assert result.exit_code == 0
    assert "Selected reference audio: a:0" in result.output
    assert "Dry run complete. Best candidate: assrt_1001 (synced, timeline 1.00)." in result.output
    assert (tmp_path / ".fixsub" / "metadata" / "results.json").exists()


def test_cli_writes_metadata_when_token_is_missing_after_video_detection(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ASSRT_TOKEN", raising=False)

    result = CliRunner().invoke(app, ["--dry-run", "--providers", "assrt"])

    assert result.exit_code != 0
    assert "ASSRT_TOKEN is required" in result.output
    metadata = _read_metadata(tmp_path)
    assert set(metadata) == METADATA_KEYS
    assert metadata["queries"] == []
    assert metadata["downloaded"] == []
    assert metadata["candidates"] == []
    assert metadata["selected_audio"] is None
    assert metadata["decisions"] == []
    assert metadata["final_output"] is None
    assert metadata["message"] == "ASSRT_TOKEN is required for ASSRT API access."


def test_cli_writes_metadata_when_search_returns_no_results(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ASSRT_TOKEN", "secret")

    class FakeClient:
        def __init__(self, token: str) -> None:
            assert token == "secret"

        def search(self, query: str) -> list[SearchResult]:
            return []

    monkeypatch.setattr("fixsub.providers.registry.AssrtClient", FakeClient)

    result = CliRunner().invoke(app, ["--dry-run", "--providers", "assrt"])

    assert result.exit_code != 0
    assert "No subtitle candidates found." in result.output
    metadata = _read_metadata(tmp_path)
    assert set(metadata) == METADATA_KEYS
    assert metadata["queries"]
    assert metadata["downloaded"] == []
    assert metadata["candidates"] == []
    assert metadata["selected_audio"] is None
    assert metadata["decisions"] == []
    assert metadata["final_output"] is None
    assert metadata["message"] == "No subtitle candidates found."


def test_cli_writes_metadata_when_all_search_queries_fail(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ASSRT_TOKEN", "secret")

    class FakeClient:
        def __init__(self, token: str) -> None:
            assert token == "secret"

        def search(self, query: str) -> list[SearchResult]:
            raise RuntimeError(f"bad token for {query}")

    monkeypatch.setattr("fixsub.providers.registry.AssrtClient", FakeClient)

    result = CliRunner().invoke(app, ["--dry-run", "--providers", "assrt"])

    assert result.exit_code != 0
    assert "Subtitle search failed" in result.output
    assert "No subtitle candidates found." not in result.output
    metadata = _read_metadata(tmp_path)
    assert set(metadata) == METADATA_KEYS
    assert metadata["queries"]
    assert metadata["downloaded"] == []
    assert metadata["candidates"] == []
    assert metadata["selected_audio"] is None
    assert metadata["decisions"] == []
    assert metadata["final_output"] is None
    assert metadata["message"] == "Subtitle search failed for all providers and queries."


def test_cli_writes_metadata_when_probe_fails_after_search(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
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

    error = FixsubError("ffprobe could not read the video")
    monkeypatch.setattr("fixsub.providers.registry.AssrtClient", FakeClient)
    monkeypatch.setattr("fixsub.cli.probe_video", lambda path: (_ for _ in ()).throw(error))

    result = CliRunner().invoke(app, ["--dry-run", "--providers", "assrt"])

    assert result.exit_code != 0
    assert "ffprobe could not read the video" in result.output
    metadata = _read_metadata(tmp_path)
    assert set(metadata) == METADATA_KEYS
    assert metadata["queries"]
    assert metadata["downloaded"] == []
    assert metadata["candidates"] == []
    assert metadata["selected_audio"] is None
    assert metadata["decisions"] == []
    assert metadata["final_output"] is None
    assert metadata["message"] == "ffprobe could not read the video"


def test_cli_writes_metadata_when_ffprobe_dependency_is_missing_after_search(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
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

    error = MissingDependencyError("ffprobe", "brew install ffmpeg")
    monkeypatch.setattr("fixsub.providers.registry.AssrtClient", FakeClient)
    monkeypatch.setattr("fixsub.cli.probe_video", lambda path: (_ for _ in ()).throw(error))

    result = CliRunner().invoke(app, ["--dry-run", "--providers", "assrt"])

    assert result.exit_code != 0
    assert "Missing required command: ffprobe" in result.output
    metadata = _read_metadata(tmp_path)
    assert set(metadata) == METADATA_KEYS
    assert metadata["queries"]
    assert metadata["downloaded"] == []
    assert metadata["candidates"] == []
    assert metadata["selected_audio"] is None
    assert metadata["decisions"] == []
    assert metadata["final_output"] is None
    assert metadata["message"] == "Missing required command: ffprobe\nInstall hint: brew install ffmpeg"


def test_cli_writes_metadata_when_no_audio_streams_are_found_after_search(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
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

    monkeypatch.setattr("fixsub.providers.registry.AssrtClient", FakeClient)
    monkeypatch.setattr(
        "fixsub.cli.probe_video",
        lambda path: ProbeResult(duration_seconds=7200, audio_streams=[], raw={}),
    )

    result = CliRunner().invoke(app, ["--dry-run", "--providers", "assrt"])

    assert result.exit_code != 0
    assert "No audio streams found" in result.output
    metadata = _read_metadata(tmp_path)
    assert set(metadata) == METADATA_KEYS
    assert metadata["queries"]
    assert metadata["downloaded"] == []
    assert metadata["candidates"] == []
    assert metadata["selected_audio"] is None
    assert metadata["decisions"] == []
    assert metadata["final_output"] is None
    assert metadata["message"] == "No audio streams found"


def test_cli_writes_metadata_when_downloads_produce_no_candidates(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
    downloaded_path = tmp_path / ".fixsub" / "downloads" / "assrt_1001.zip"
    downloaded_path.parent.mkdir(parents=True)
    downloaded_path.write_bytes(b"archive")
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
            return DownloadedFile(
                candidate_id="assrt_1001",
                provider="assrt",
                path=downloaded_path,
                source_url=result.download_url,
            )

    monkeypatch.setattr("fixsub.providers.registry.AssrtClient", FakeClient)
    monkeypatch.setattr("fixsub.cli.extract_archive", lambda path, out_dir: [])
    monkeypatch.setattr(
        "fixsub.cli.probe_video",
        lambda path: ProbeResult(
            duration_seconds=7200,
            audio_streams=[AudioStream(1, 0, "ac3", "eng", 6, True)],
            raw={},
        ),
    )

    result = CliRunner().invoke(app, ["--dry-run", "--providers", "assrt"])

    assert result.exit_code != 0
    assert "No downloadable or extractable subtitle candidates." in result.output
    metadata = _read_metadata(tmp_path)
    assert set(metadata) == METADATA_KEYS
    assert metadata["queries"]
    assert metadata["downloaded"]
    assert {item["candidate_id"] for item in metadata["downloaded"]} == {"assrt_1001"}
    assert metadata["candidates"] == []
    assert metadata["selected_audio"] == "a:0"
    assert metadata["decisions"] == []
    assert metadata["final_output"] is None
    assert metadata["message"] == "No downloadable or extractable subtitle candidates."
