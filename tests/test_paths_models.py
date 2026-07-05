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
