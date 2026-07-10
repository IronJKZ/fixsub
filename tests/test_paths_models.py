import json
from pathlib import Path

import pytest

from fixsub.models import (
    AlignmentScore,
    AudioStream,
    CandidateDecision,
    RunOptions,
    SubtitleCandidate,
    SyncResult,
)
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


def test_workdirs_serialization_uses_strings_for_paths(tmp_path: Path) -> None:
    root = create_workdirs(tmp_path).to_json()["root"]

    assert isinstance(root, str)
    assert root.endswith(".fixsub")


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


def test_audio_stream_displays_non_surround_channel_count() -> None:
    stream = AudioStream(
        container_index=3,
        audio_index=2,
        codec="dts",
        language="eng",
        channels=8,
    )

    assert "English" in stream.display_name
    assert "DTS" in stream.display_name
    assert "8ch" in stream.display_name
    assert "5.1" not in stream.display_name


def test_audio_stream_displays_undetermined_language_as_unknown() -> None:
    stream = AudioStream(
        container_index=4,
        audio_index=3,
        codec="aac",
        language="und",
        channels=2,
    )

    assert "unknown language" in stream.display_name


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


def test_candidate_decision_serialization_converts_nested_paths(tmp_path: Path) -> None:
    candidate = SubtitleCandidate(
        candidate_id="assrt_001",
        provider="assrt",
        source_title="Movie 1992",
        subtitle_path=tmp_path / "movie.ass",
        language="bilingual",
        format="ass",
        pre_score=12.5,
    )
    sync_result = SyncResult(
        attempted=True,
        succeeded=True,
        output_path=tmp_path / "movie.synced.ass",
    )
    decision = CandidateDecision(
        candidate=candidate,
        original_score=AlignmentScore(score=71.0, reasons=["baseline"]),
        synced_score=AlignmentScore(score=96.5, reasons=["aligned"]),
        sync_result=sync_result,
        selected_version="synced",
        selected_path=tmp_path / "movie.synced.ass",
        selected_score=96.5,
        is_poor=False,
        decision_reason="synced score improved",
    )

    data = decision.to_json()

    json.dumps(data)
    assert data["candidate"]["subtitle_path"].endswith("movie.ass")
    assert data["sync_result"]["output_path"].endswith("movie.synced.ass")
    assert data["selected_path"].endswith("movie.synced.ass")


def test_run_options_defaults() -> None:
    options = RunOptions()

    assert options.max_candidates == 5
    assert options.lang == "zh-Hans"
    assert options.providers == ("assrt", "subhd")
    assert options.to_json()["providers"] == ["assrt", "subhd"]


def test_run_options_providers_are_immutable_tuple_like() -> None:
    options = RunOptions()

    assert isinstance(options.providers, tuple)
    assert options.providers == ("assrt", "subhd")
    with pytest.raises(AttributeError):
        options.providers.append("opensubtitles")
