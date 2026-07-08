from pathlib import Path
import json

from fixsub.decision import decide_candidate_version
from fixsub.logging_utils import append_log, write_results_json
from fixsub.models import AlignmentScore, SubtitleCandidate, SyncResult
from fixsub.output import final_subtitle_path, write_final_subtitle
from fixsub.ranking import rank_decisions


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
        original_score=AlignmentScore(0.90, []),
        sync_result=SyncResult(attempted=False, succeeded=False),
        synced_score=None,
    )

    assert decision.selected_version == "original"
    assert decision.selected_path == candidate.subtitle_path
    assert decision.decision_reason == "Original subtitle already aligned; sync skipped."


def test_decision_keeps_excellent_original_even_if_synced_would_improve(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    synced = tmp_path / "candidate.synced.ass"
    synced.write_text("[Events]\n", encoding="utf-8")

    decision = decide_candidate_version(
        candidate=candidate,
        original_score=AlignmentScore(0.90, []),
        sync_result=SyncResult(attempted=True, succeeded=True, output_path=synced),
        synced_score=AlignmentScore(0.98, []),
    )

    assert decision.selected_version == "original"
    assert decision.selected_path == candidate.subtitle_path
    assert decision.selected_score == 0.90
    assert decision.decision_reason == "Original subtitle already aligned; sync skipped."


def test_decision_selects_synced_at_exact_improvement_threshold(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    synced = tmp_path / "candidate.synced.ass"
    synced.write_text("[Events]\n", encoding="utf-8")

    decision = decide_candidate_version(
        candidate=candidate,
        original_score=AlignmentScore(0.72, []),
        sync_result=SyncResult(attempted=True, succeeded=True, output_path=synced),
        synced_score=AlignmentScore(0.80, []),
    )

    assert decision.selected_version == "synced"
    assert decision.selected_path == synced
    assert decision.is_poor is False


def test_decision_keeps_original_when_synced_output_is_missing(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)

    decision = decide_candidate_version(
        candidate=candidate,
        original_score=AlignmentScore(0.40, []),
        sync_result=SyncResult(
            attempted=True,
            succeeded=True,
            output_path=tmp_path / "missing.synced.ass",
        ),
        synced_score=AlignmentScore(0.95, []),
    )

    assert decision.selected_version == "original"
    assert decision.selected_path == candidate.subtitle_path
    assert decision.is_poor is True
    assert decision.decision_reason == "Synced output missing; original candidate kept."


def test_decision_keeps_original_when_synced_score_is_missing(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    synced = tmp_path / "candidate.synced.ass"
    synced.write_text("[Events]\n", encoding="utf-8")

    decision = decide_candidate_version(
        candidate=candidate,
        original_score=AlignmentScore(0.40, []),
        sync_result=SyncResult(attempted=True, succeeded=True, output_path=synced),
        synced_score=None,
    )

    assert decision.selected_version == "original"
    assert decision.selected_path == candidate.subtitle_path
    assert decision.is_poor is True
    assert decision.decision_reason == "Synced score missing; original candidate kept."


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


def test_decision_marks_sync_failure_with_low_original_poor(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)

    decision = decide_candidate_version(
        candidate=candidate,
        original_score=AlignmentScore(0.40, []),
        sync_result=SyncResult(attempted=True, succeeded=False, error="failed"),
        synced_score=None,
    )

    assert decision.selected_version == "original"
    assert decision.is_poor is True
    assert decision.decision_reason == "Sync failed; original candidate kept."


def test_final_subtitle_path_adds_language_before_subtitle_extension(tmp_path: Path) -> None:
    video = tmp_path / "Movie.1992.1080p.WEB-DL.mkv"

    assert final_subtitle_path(video, "zh-Hans", ".ass") == tmp_path / "Movie.1992.1080p.WEB-DL.zh-Hans.ass"


def test_write_final_subtitle_backs_up_existing_file_and_writes_selected(tmp_path: Path) -> None:
    video = tmp_path / "Movie.mkv"
    selected = tmp_path / "selected.ass"
    selected.write_text("selected subtitle\n", encoding="utf-8")
    final_path = tmp_path / "Movie.zh-Hans.ass"
    final_path.write_text("existing subtitle\n", encoding="utf-8")

    written_path = write_final_subtitle(
        selected_subtitle=selected,
        video_path=video,
        lang="zh-Hans",
        backup_dir=tmp_path / ".fixsub" / "original",
    )

    backups = list((tmp_path / ".fixsub" / "original").glob("*.Movie.zh-Hans.ass"))
    assert written_path == final_path
    assert final_path.read_text(encoding="utf-8") == "selected subtitle\n"
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "existing subtitle\n"


def test_rank_decisions_prefers_non_poor_high_score_over_poor_higher_pre_score(tmp_path: Path) -> None:
    good_candidate = make_candidate(tmp_path)
    poor_candidate = SubtitleCandidate(
        candidate_id="assrt_002",
        provider="assrt",
        source_title="Unforgiven",
        subtitle_path=tmp_path / "poor.ass",
        language="bilingual",
        format="ass",
        pre_score=99,
    )
    poor_candidate.subtitle_path.write_text("[Events]\n", encoding="utf-8")
    good_decision = decide_candidate_version(
        candidate=good_candidate,
        original_score=AlignmentScore(0.70, []),
        sync_result=SyncResult(attempted=False, succeeded=False),
        synced_score=None,
    )
    poor_decision = decide_candidate_version(
        candidate=poor_candidate,
        original_score=AlignmentScore(0.40, []),
        sync_result=SyncResult(attempted=False, succeeded=False),
        synced_score=None,
    )

    assert rank_decisions([poor_decision, good_decision]) == [good_decision, poor_decision]


def test_write_results_json_serializes_paths_to_strings(tmp_path: Path) -> None:
    target = tmp_path / "metadata" / "result.json"

    written_path = write_results_json(
        target,
        {
            "video": tmp_path / "Movie.mkv",
            "outputs": [tmp_path / "Movie.zh-Hans.ass"],
            "nested": {"backup": tmp_path / ".fixsub" / "original"},
        },
    )

    assert written_path == target
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "video": str(tmp_path / "Movie.mkv"),
        "outputs": [str(tmp_path / "Movie.zh-Hans.ass")],
        "nested": {"backup": str(tmp_path / ".fixsub" / "original")},
    }


def test_append_log_creates_parent_and_appends_stripped_messages(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "fixsub.log"

    append_log(log_path, "first\n")
    append_log(log_path, "second")

    assert log_path.read_text(encoding="utf-8") == "first\nsecond\n"
