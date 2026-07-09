from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer

from fixsub.alignment import score_alignment
from fixsub.decision import EXCELLENT_ALIGNMENT, decide_candidate_version
from fixsub.encoding import normalize_to_utf8
from fixsub.errors import FixsubError, NoCandidatesError, ProviderConfigError
from fixsub.extract import extract_archive
from fixsub.ffprobe import probe_video, select_audio_stream
from fixsub.logging_utils import append_log, write_results_json
from fixsub.models import CandidateDecision, DownloadedFile, RunOptions, SearchResult, SubtitleCandidate, SyncResult
from fixsub.movie import detect_video, generate_search_queries, parse_movie_info
from fixsub.output import write_final_subtitle
from fixsub.paths import create_workdirs
from fixsub.providers.assrt_api import AssrtClient
from fixsub.ranking import rank_decisions, rank_search_results
from fixsub.sync import run_ffsubsync, synced_output_path

app = typer.Typer(add_completion=False, no_args_is_help=False)


def _parse_providers(value: str) -> tuple[str, ...]:
    providers = tuple(provider.strip().lower() for provider in value.split(",") if provider.strip())
    if providers != ("assrt",):
        raise ProviderConfigError("M1 supports assrt only")
    return providers


def _as_json(value):
    if hasattr(value, "to_json"):
        return value.to_json()
    return value


def _candidate_target(candidate_dir: Path, candidate_id: str, source: Path) -> Path:
    suffix = source.suffix.lower() or ".srt"
    target = candidate_dir / f"{candidate_id}{suffix}"
    if not target.exists() or target.resolve() == source.resolve():
        return target
    index = 1
    while True:
        candidate = candidate_dir / f"{candidate_id}.{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _download_candidates(
    client: AssrtClient,
    ranked_results: list[SearchResult],
    base_dir: Path,
    max_candidates: int,
) -> tuple[list[DownloadedFile], list[SubtitleCandidate]]:
    downloaded: list[DownloadedFile] = []
    candidates: list[SubtitleCandidate] = []
    workdirs = create_workdirs(base_dir)
    log_path = workdirs.logs / "fixsub.log"
    result_by_id = {result.result_id: result for result in ranked_results}
    for result in ranked_results[:max_candidates]:
        try:
            downloaded_file = client.download(result, workdirs.downloads)
            downloaded.append(downloaded_file)
            extracted_paths = extract_archive(downloaded_file.path, workdirs.candidates)
            for extracted_path in extracted_paths:
                normalized_path = _candidate_target(workdirs.candidates, downloaded_file.candidate_id, extracted_path)
                normalize_to_utf8(extracted_path, normalized_path)
                scored_result = result_by_id.get(result.result_id, result)
                candidates.append(
                    SubtitleCandidate(
                        candidate_id=downloaded_file.candidate_id,
                        provider=downloaded_file.provider,
                        source_title=scored_result.title,
                        subtitle_path=normalized_path,
                        language=scored_result.language,
                        format=(normalized_path.suffix.lower().lstrip(".") or scored_result.format or "subtitle"),
                        pre_score=scored_result.pre_score,
                    )
                )
        except Exception as exc:
            append_log(log_path, f"Candidate failed: {result.title}: {exc}")
    return downloaded, candidates


def _decide_candidates(
    candidates: list[SubtitleCandidate],
    video_path: Path,
    duration_seconds: float | None,
    selected_audio: str,
    synced_dir: Path,
    no_sync: bool,
) -> list[CandidateDecision]:
    decisions: list[CandidateDecision] = []
    for candidate in candidates:
        original_score = score_alignment(candidate.subtitle_path, duration_seconds)
        sync_result = SyncResult(attempted=False, succeeded=False)
        synced_score = None
        if not no_sync and original_score.score < EXCELLENT_ALIGNMENT:
            output_path = synced_output_path(candidate.subtitle_path, synced_dir)
            try:
                sync_result = run_ffsubsync(video_path, candidate.subtitle_path, output_path, selected_audio)
            except FixsubError as exc:
                sync_result = SyncResult(attempted=True, succeeded=False, error=str(exc))
            if sync_result.succeeded and sync_result.output_path and sync_result.output_path.exists():
                synced_score = score_alignment(sync_result.output_path, duration_seconds)
        decisions.append(decide_candidate_version(candidate, original_score, sync_result, synced_score))
    return decisions


def run_pipeline(base_dir: Path, options: RunOptions) -> dict[str, object]:
    workdirs = create_workdirs(base_dir)
    log_path = workdirs.logs / "fixsub.log"
    video_path = detect_video(base_dir)
    movie = parse_movie_info(video_path)
    append_log(log_path, f"Video: {video_path}")

    token = os.environ.get("ASSRT_TOKEN", "").strip()
    if not token:
        raise ProviderConfigError("ASSRT_TOKEN is required for ASSRT API access")
    client = AssrtClient(token=token)

    queries = generate_search_queries(movie)
    search_results: list[SearchResult] = []
    for query in queries:
        try:
            search_results.extend(client.search(query))
        except Exception as exc:
            append_log(log_path, f"Search failed for {query}: {exc}")
    ranked_results = rank_search_results(search_results, movie)
    if not ranked_results:
        raise NoCandidatesError("No ASSRT candidates found.")

    probe = probe_video(video_path)
    if options.audio:
        selected_audio = options.audio
    else:
        try:
            selected_audio = select_audio_stream(probe.audio_streams).ffsubsync_id
        except ValueError as exc:
            raise FixsubError(str(exc)) from exc
    typer.echo(f"Selected reference audio: {selected_audio}")

    downloaded, candidates = _download_candidates(client, ranked_results, base_dir, options.max_candidates)
    decisions = _decide_candidates(
        candidates,
        video_path,
        probe.duration_seconds,
        selected_audio,
        workdirs.synced,
        options.no_sync,
    )
    if not decisions:
        raise NoCandidatesError("No downloadable or extractable ASSRT candidates.")

    ranked_decisions = rank_decisions(decisions)
    best = ranked_decisions[0]
    final_output = None
    if best.is_poor:
        message = "No high-confidence subtitle found."
    elif options.dry_run:
        message = f"Dry run complete. Best candidate: {best.candidate.candidate_id} ({best.selected_score:.2f})."
    else:
        final_output = write_final_subtitle(best.selected_path, video_path, options.lang, workdirs.original)
        message = f"Applied subtitle: {final_output}"

    metadata = {
        "video": movie.to_json(),
        "options": options.to_json(),
        "queries": queries,
        "downloaded": [_as_json(item) for item in downloaded],
        "candidates": [_as_json(item) for item in candidates],
        "selected_audio": selected_audio,
        "decisions": [_as_json(item) for item in ranked_decisions],
        "final_output": final_output,
        "message": message,
    }
    write_results_json(workdirs.metadata / "results.json", metadata)
    return {"message": message, "metadata": metadata}


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Process without writing the final subtitle."),
    audio: Optional[str] = typer.Option(None, "--audio", help="Force ffsubsync reference stream, such as a:0."),
    no_sync: bool = typer.Option(False, "--no-sync", help="Skip ffsubsync and rank original candidates only."),
    max_candidates: int = typer.Option(5, "--max-candidates", min=1, help="Maximum candidates to download."),
    lang: str = typer.Option("zh-Hans", "--lang", help="Infuse language suffix for final output."),
    providers: str = typer.Option("assrt", "--providers", help="Comma-separated providers. M1 supports assrt only."),
    debug: bool = typer.Option(False, "--debug", help="Print verbose diagnostics."),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    try:
        options = RunOptions(
            dry_run=dry_run,
            audio=audio,
            no_sync=no_sync,
            max_candidates=max_candidates,
            lang=lang,
            providers=_parse_providers(providers),
            debug=debug,
        )
        result = run_pipeline(Path.cwd(), options)
    except FixsubError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(result["message"])
