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
