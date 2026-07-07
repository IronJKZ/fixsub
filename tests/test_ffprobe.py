import json
import subprocess
from pathlib import Path

import pytest

from fixsub.errors import FixsubError, MissingDependencyError
from fixsub.ffprobe import parse_ffprobe_json, probe_video, select_audio_stream
from fixsub.models import AudioStream


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


def test_parse_ffprobe_json_ignores_malformed_duration() -> None:
    probe = parse_ffprobe_json({"format": {"duration": "N/A"}, "streams": []})

    assert probe.duration_seconds is None


def test_parse_ffprobe_json_skips_non_dict_streams_and_normalizes_metadata() -> None:
    payload = {
        "streams": [
            None,
            {"index": 0, "codec_type": "video"},
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "tags": ["not", "a", "dict"],
                "disposition": "default",
            },
        ]
    }

    probe = parse_ffprobe_json(payload)

    assert len(probe.audio_streams) == 1
    assert probe.audio_streams[0].language is None
    assert probe.audio_streams[0].is_default is False


def test_probe_video_raises_missing_dependency_when_ffprobe_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fixsub.ffprobe.shutil.which", lambda command: None)

    with pytest.raises(MissingDependencyError):
        probe_video(Path("movie.mkv"))


def test_probe_video_wraps_ffprobe_process_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    video_path = Path("movie.mkv")
    monkeypatch.setattr("fixsub.ffprobe.shutil.which", lambda command: "/usr/bin/ffprobe")

    def fail_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, ["ffprobe"], stderr="boom")

    monkeypatch.setattr("fixsub.ffprobe.subprocess.run", fail_run)

    with pytest.raises(FixsubError, match="ffprobe.*movie\\.mkv"):
        probe_video(video_path)


def test_probe_video_wraps_invalid_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fixsub.ffprobe.shutil.which", lambda command: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        "fixsub.ffprobe.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=["ffprobe"], returncode=0, stdout="not-json"),
    )

    with pytest.raises(FixsubError, match="ffprobe"):
        probe_video(Path("movie.mkv"))


def test_select_audio_stream_prefers_default_when_no_english_stream_exists() -> None:
    selected = select_audio_stream(
        [
            AudioStream(1, 0, "aac", "spa", 2, False),
            AudioStream(2, 1, "ac3", "fra", 2, True),
        ]
    )

    assert selected.audio_index == 1


def test_select_audio_stream_prefers_higher_channels_when_language_and_default_tie() -> None:
    selected = select_audio_stream(
        [
            AudioStream(1, 0, "aac", "spa", 2, False),
            AudioStream(2, 1, "ac3", "fra", 6, False),
        ]
    )

    assert selected.audio_index == 1


def test_select_audio_stream_falls_back_to_first_audio_when_all_else_ties() -> None:
    selected = select_audio_stream(
        [
            AudioStream(1, 0, "aac", None, 2, False),
            AudioStream(2, 1, "aac", None, 2, False),
        ]
    )

    assert selected.audio_index == 0
