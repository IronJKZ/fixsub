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
    assert decision.decision_reason != "Synced score improved by 0.55."


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
