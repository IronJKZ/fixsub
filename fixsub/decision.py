from __future__ import annotations

from fixsub.models import AlignmentScore, CandidateDecision, SubtitleCandidate, SyncResult

POOR_ALIGNMENT = 0.50


def decide_candidate_version(
    candidate: SubtitleCandidate,
    original_score: AlignmentScore,
    sync_result: SyncResult,
    synced_score: AlignmentScore | None,
) -> CandidateDecision:
    synced_output_exists = sync_result.output_path is not None and sync_result.output_path.exists()
    synced_is_usable = sync_result.succeeded and synced_score is not None and synced_output_exists
    if synced_is_usable:
        selected_version = "synced"
        selected_path = sync_result.output_path
        selected_score = synced_score.score
        if sync_result.forced_low_quality:
            reason = "ffsubsync forced a low-quality audio alignment."
        else:
            reason = "ffsubsync audio alignment succeeded."
    else:
        selected_version = "original"
        selected_path = candidate.subtitle_path
        selected_score = original_score.score
        if sync_result.attempted and not sync_result.succeeded:
            reason = "Sync failed; original candidate kept."
        elif sync_result.attempted and not synced_output_exists:
            reason = "Synced output missing; original candidate kept."
        elif sync_result.attempted and synced_score is None:
            reason = "Synced score missing; original candidate kept."
        elif sync_result.attempted:
            reason = "ffsubsync validation did not produce a usable synced subtitle."
        else:
            reason = "Audio validation explicitly skipped; original candidate kept."
    usable_score = synced_score.score if selected_version == "synced" and synced_score is not None else original_score.score
    is_poor = (
        sync_result.forced_low_quality
        or usable_score < POOR_ALIGNMENT
        or (sync_result.attempted and not synced_is_usable)
    )
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
