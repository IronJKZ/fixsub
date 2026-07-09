import json
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


def test_cli_rejects_unimplemented_provider(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["--providers", "subhd"])

    assert result.exit_code != 0
    assert "M1 supports assrt only" in result.output


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

    monkeypatch.setattr("fixsub.cli.AssrtClient", FakeClient)
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

    result = CliRunner().invoke(app, ["--dry-run"])

    assert result.exit_code == 0
    assert "Selected reference audio: a:0" in result.output
    assert "Dry run complete" in result.output
    assert (tmp_path / ".fixsub" / "metadata" / "results.json").exists()


def test_cli_writes_metadata_when_token_is_missing_after_video_detection(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ASSRT_TOKEN", raising=False)

    result = CliRunner().invoke(app, ["--dry-run"])

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

    monkeypatch.setattr("fixsub.cli.AssrtClient", FakeClient)

    result = CliRunner().invoke(app, ["--dry-run"])

    assert result.exit_code != 0
    assert "No ASSRT candidates found." in result.output
    metadata = _read_metadata(tmp_path)
    assert set(metadata) == METADATA_KEYS
    assert metadata["queries"]
    assert metadata["downloaded"] == []
    assert metadata["candidates"] == []
    assert metadata["selected_audio"] is None
    assert metadata["decisions"] == []
    assert metadata["final_output"] is None
    assert metadata["message"] == "No ASSRT candidates found."


def test_cli_writes_metadata_when_all_search_queries_fail(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ASSRT_TOKEN", "secret")

    class FakeClient:
        def __init__(self, token: str) -> None:
            assert token == "secret"

        def search(self, query: str) -> list[SearchResult]:
            raise RuntimeError(f"bad token for {query}")

    monkeypatch.setattr("fixsub.cli.AssrtClient", FakeClient)

    result = CliRunner().invoke(app, ["--dry-run"])

    assert result.exit_code != 0
    assert "ASSRT search failed" in result.output
    assert "No ASSRT candidates found." not in result.output
    metadata = _read_metadata(tmp_path)
    assert set(metadata) == METADATA_KEYS
    assert metadata["queries"]
    assert metadata["downloaded"] == []
    assert metadata["candidates"] == []
    assert metadata["selected_audio"] is None
    assert metadata["decisions"] == []
    assert metadata["final_output"] is None
    assert metadata["message"] == "ASSRT search failed for all queries."


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

    monkeypatch.setattr("fixsub.cli.AssrtClient", FakeClient)
    monkeypatch.setattr("fixsub.cli.extract_archive", lambda path, out_dir: [])
    monkeypatch.setattr(
        "fixsub.cli.probe_video",
        lambda path: ProbeResult(
            duration_seconds=7200,
            audio_streams=[AudioStream(1, 0, "ac3", "eng", 6, True)],
            raw={},
        ),
    )

    result = CliRunner().invoke(app, ["--dry-run"])

    assert result.exit_code != 0
    assert "No downloadable or extractable ASSRT candidates." in result.output
    metadata = _read_metadata(tmp_path)
    assert set(metadata) == METADATA_KEYS
    assert metadata["queries"]
    assert metadata["downloaded"]
    assert {item["candidate_id"] for item in metadata["downloaded"]} == {"assrt_1001"}
    assert metadata["candidates"] == []
    assert metadata["selected_audio"] == "a:0"
    assert metadata["decisions"] == []
    assert metadata["final_output"] is None
    assert metadata["message"] == "No downloadable or extractable ASSRT candidates."
