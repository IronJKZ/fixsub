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
