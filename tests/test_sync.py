from pathlib import Path
import subprocess

import pytest

from fixsub.errors import MissingDependencyError
from fixsub.models import SyncResult
from fixsub.sync import run_ffsubsync


def test_run_ffsubsync_missing_dependency_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("fixsub.sync.shutil.which", lambda command: None)

    with pytest.raises(MissingDependencyError) as exc_info:
        run_ffsubsync(
            video_path=tmp_path / "movie.mkv",
            subtitle_path=tmp_path / "candidate.ass",
            output_path=tmp_path / "synced" / "candidate.ass",
            audio_stream="a:0",
        )

    assert exc_info.value.command == "ffs"


def test_run_ffsubsync_nonzero_return_captures_stderr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("fixsub.sync.shutil.which", lambda command: "/usr/bin/ffs")

    def fake_run(command: list[str], capture_output: bool, text: bool) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2, stdout="stdout details", stderr="stderr details")

    monkeypatch.setattr("fixsub.sync.subprocess.run", fake_run)

    result = run_ffsubsync(
        video_path=tmp_path / "movie.mkv",
        subtitle_path=tmp_path / "candidate.ass",
        output_path=tmp_path / "synced" / "candidate.ass",
        audio_stream="a:0",
    )

    assert result == SyncResult(attempted=True, succeeded=False, output_path=None, error="stderr details")


def test_run_ffsubsync_nonzero_return_falls_back_to_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("fixsub.sync.shutil.which", lambda command: "/usr/bin/ffs")

    def fake_run(command: list[str], capture_output: bool, text: bool) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 2, stdout="stdout details", stderr="")

    monkeypatch.setattr("fixsub.sync.subprocess.run", fake_run)

    result = run_ffsubsync(
        video_path=tmp_path / "movie.mkv",
        subtitle_path=tmp_path / "candidate.ass",
        output_path=tmp_path / "synced" / "candidate.ass",
        audio_stream="a:0",
    )

    assert result == SyncResult(attempted=True, succeeded=False, output_path=None, error="stdout details")


def test_run_ffsubsync_success_uses_expected_command_and_creates_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("fixsub.sync.shutil.which", lambda command: "/usr/bin/ffs")
    video = tmp_path / "movie.mkv"
    subtitle = tmp_path / "candidate.ass"
    output = tmp_path / "synced" / "candidate.ass"
    calls: list[list[str]] = []

    def fake_run(command: list[str], capture_output: bool, text: bool) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert capture_output is True
        assert text is True
        assert output.parent.exists()
        output.write_text("synced", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="score: 305917.769\noffset seconds: 23.420\nframerate scale factor: 1.043\n",
            stderr="",
        )

    monkeypatch.setattr("fixsub.sync.subprocess.run", fake_run)

    result = run_ffsubsync(
        video_path=video,
        subtitle_path=subtitle,
        output_path=output,
        audio_stream="a:1",
    )

    assert calls == [
        [
            "ffs",
            str(video),
            "--reference-stream",
            "a:1",
            "--skip-sync-on-low-quality",
            "-i",
            str(subtitle),
            "-o",
            str(output),
        ]
    ]
    assert result == SyncResult(
        attempted=True,
        succeeded=True,
        output_path=output,
        error=None,
        ffsubsync_score=305917.769,
        offset_seconds=23.42,
        framerate_scale=1.043,
    )


def test_run_ffsubsync_rejects_zero_exit_low_quality_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("fixsub.sync.shutil.which", lambda command: "/usr/bin/ffs")
    output = tmp_path / "synced" / "candidate.srt"

    def fake_run(command: list[str], capture_output: bool, text: bool) -> subprocess.CompletedProcess[str]:
        output.write_text("original subtitle", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                "score: 305917.769\n"
                "offset seconds: 31.730\n"
                "framerate scale factor: 1.043\n"
                "low-quality alignment; leaving subtitles unmodified\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("fixsub.sync.subprocess.run", fake_run)

    result = run_ffsubsync(
        video_path=tmp_path / "movie.mkv",
        subtitle_path=tmp_path / "candidate.srt",
        output_path=output,
        audio_stream="a:4",
    )

    assert result.succeeded is False
    assert result.error == "ffsubsync rejected a low-quality alignment"
    assert result.offset_seconds == 31.73
    assert result.framerate_scale == 1.043
    assert not output.exists()


def test_run_ffsubsync_does_not_reuse_stale_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("fixsub.sync.shutil.which", lambda command: "/usr/bin/ffs")
    output = tmp_path / "synced" / "candidate.srt"
    output.parent.mkdir(parents=True)
    output.write_text("stale subtitle", encoding="utf-8")

    def fake_run(command: list[str], capture_output: bool, text: bool) -> subprocess.CompletedProcess[str]:
        assert not output.exists()
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="score: 1.0\noffset seconds: 2.0\nframerate scale factor: 1.0\n",
            stderr="",
        )

    monkeypatch.setattr("fixsub.sync.subprocess.run", fake_run)

    result = run_ffsubsync(
        video_path=tmp_path / "movie.mkv",
        subtitle_path=tmp_path / "candidate.srt",
        output_path=output,
        audio_stream="a:0",
    )

    assert result.succeeded is False
    assert result.error == "ffsubsync exited successfully without writing an output file"
    assert not output.exists()


def test_run_ffsubsync_requires_complete_alignment_metrics(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("fixsub.sync.shutil.which", lambda command: "/usr/bin/ffs")
    output = tmp_path / "synced" / "candidate.srt"

    def fake_run(command: list[str], capture_output: bool, text: bool) -> subprocess.CompletedProcess[str]:
        output.write_text("new subtitle", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="offset seconds: 2.0\n", stderr="")

    monkeypatch.setattr("fixsub.sync.subprocess.run", fake_run)

    result = run_ffsubsync(
        video_path=tmp_path / "movie.mkv",
        subtitle_path=tmp_path / "candidate.srt",
        output_path=output,
        audio_stream="a:0",
    )

    assert result.succeeded is False
    assert result.error == "ffsubsync output did not include complete alignment metrics"
    assert not output.exists()


def test_run_ffsubsync_oserror_returns_failed_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("fixsub.sync.shutil.which", lambda command: "/usr/bin/ffs")

    def fake_run(command: list[str], capture_output: bool, text: bool) -> subprocess.CompletedProcess[str]:
        raise OSError("cannot execute ffs")

    monkeypatch.setattr("fixsub.sync.subprocess.run", fake_run)

    result = run_ffsubsync(
        video_path=tmp_path / "movie.mkv",
        subtitle_path=tmp_path / "candidate.ass",
        output_path=tmp_path / "synced" / "candidate.ass",
        audio_stream="a:0",
    )

    assert result == SyncResult(
        attempted=True,
        succeeded=False,
        output_path=None,
        error="cannot execute ffs",
    )
