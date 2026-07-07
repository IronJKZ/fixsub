from __future__ import annotations

from fixsub.models import AlignmentScore, CandidateDecision, SubtitleCandidate, SyncResult

EXCELLENT_ALIGNMENT = 0.90
SYNC_IMPROVEMENT_THRESHOLD = 0.08
POOR_ALIGNMENT = 0.50


def decide_candidate_version(
    candidate: SubtitleCandidate,
    original_score: AlignmentScore,
    sync_result: SyncResult,
    synced_score: AlignmentScore | None,
) -> CandidateDecision:
    if original_score.score >= EXCELLENT_ALIGNMENT and not sync_result.attempted:
        selected_version = "original"
        selected_path = candidate.subtitle_path
        selected_score = original_score.score
        reason = "Original subtitle already aligned; sync skipped."
    elif (
        sync_result.succeeded
        and synced_score
        and sync_result.output_path
        and sync_result.output_path.exists()
        and synced_score.score >= original_score.score + SYNC_IMPROVEMENT_THRESHOLD
    ):
        selected_version = "synced"
        selected_path = sync_result.output_path
        selected_score = synced_score.score
        reason = f"Synced score improved by {synced_score.score - original_score.score:.2f}."
    else:
        selected_version = "original"
        selected_path = candidate.subtitle_path
        selected_score = original_score.score
        if sync_result.attempted and not sync_result.succeeded:
            reason = "Sync failed; original candidate kept."
        elif sync_result.attempted:
            reason = "Synced version did not improve alignment."
        else:
            reason = "Sync skipped; original candidate kept."
    synced_value = synced_score.score if synced_score else None
    is_poor = original_score.score < POOR_ALIGNMENT and (synced_value is None or synced_value < POOR_ALIGNMENT)
    return CandidateDecision(
        candidate=candidate,
        original_score=original_score,
        synced_score=synced_score,
        sync_result=sync_result,
        selected_version=selected_version,
        selected_path=selected_path,
        selected_score=selected_score,
        is_poor=is_poor,
        decision_reason=reason,
    )
