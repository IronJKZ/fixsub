from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from fixsub.alignment import score_alignment
from fixsub.credentials import delete_keychain_token, get_assrt_token, store_keychain_token_interactive
from fixsub.decision import decide_candidate_version
from fixsub.encoding import normalize_to_utf8
from fixsub.errors import FixsubError, NoCandidatesError, ProviderConfigError
from fixsub.extract import extract_archive
from fixsub.ffprobe import probe_video, select_audio_stream
from fixsub.logging_utils import append_log, write_results_json
from fixsub.models import CandidateDecision, DownloadedFile, RunOptions, SearchResult, SubtitleCandidate, SyncResult
from fixsub.movie import detect_video, generate_search_queries, parse_movie_info
from fixsub.output import compatible_language_tags, final_subtitle_path, write_final_subtitle
from fixsub.paths import create_workdirs
from fixsub.providers.registry import (
    DEFAULT_PROVIDERS,
    ProviderClient,
    build_provider_clients,
    parse_providers,
)
from fixsub.ranking import rank_decisions, rank_search_results
from fixsub.sync import run_ffsubsync, synced_output_path
from fixsub.subtitles import analyze_subtitle_language, shift_subtitle_timing

app = typer.Typer(add_completion=False, no_args_is_help=False)
auth_app = typer.Typer(help="Manage the ASSRT token in macOS Keychain.")
app.add_typer(auth_app, name="auth")

SUPPORTED_SUBTITLE_SUFFIXES = (".srt", ".ass", ".ssa")


def _as_json(value):
    if hasattr(value, "to_json"):
        return value.to_json()
    return value


def _write_pipeline_metadata(
    metadata_path: Path,
    *,
    movie,
    options: RunOptions,
    queries: list[str] | None = None,
    downloaded: list[DownloadedFile] | None = None,
    candidates: list[SubtitleCandidate] | None = None,
    selected_audio: str | None = None,
    decisions: list[CandidateDecision] | None = None,
    final_output: Path | None = None,
    message: str,
) -> dict[str, object]:
    metadata = {
        "video": movie.to_json(),
        "options": options.to_json(),
        "queries": queries or [],
        "downloaded": [_as_json(item) for item in downloaded or []],
        "candidates": [_as_json(item) for item in candidates or []],
        "selected_audio": selected_audio,
        "decisions": [_as_json(item) for item in decisions or []],
        "final_output": final_output,
        "message": message,
    }
    write_results_json(metadata_path, metadata)
    return metadata


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
    clients: dict[str, ProviderClient],
    ranked_results: list[SearchResult],
    base_dir: Path,
    max_candidates: int,
) -> tuple[list[DownloadedFile], list[SubtitleCandidate]]:
    downloaded: list[DownloadedFile] = []
    candidates: list[SubtitleCandidate] = []
    workdirs = create_workdirs(base_dir)
    log_path = workdirs.logs / "fixsub.log"
    for result in ranked_results[:max_candidates]:
        try:
            client = clients[result.provider]
            downloaded_file = client.download(result, workdirs.downloads)
            downloaded.append(downloaded_file)
            extracted_paths = extract_archive(downloaded_file.path, workdirs.candidates)
            for extracted_path in extracted_paths:
                normalized_path = _candidate_target(workdirs.candidates, downloaded_file.candidate_id, extracted_path)
                normalize_to_utf8(extracted_path, normalized_path)
                language_analysis = analyze_subtitle_language(normalized_path)
                if language_analysis.classification == "non-chinese":
                    append_log(
                        log_path,
                        f"Candidate rejected as non-Chinese: {result.title} "
                        f"(Han={language_analysis.han_characters}, Latin={language_analysis.latin_characters})",
                    )
                    continue
                candidates.append(
                    SubtitleCandidate(
                        candidate_id=normalized_path.stem,
                        provider=downloaded_file.provider,
                        source_title=result.title,
                        subtitle_path=normalized_path,
                        language=result.language,
                        format=(normalized_path.suffix.lower().lstrip(".") or result.format or "subtitle"),
                        pre_score=result.pre_score,
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
        if not no_sync:
            output_path = synced_output_path(candidate.subtitle_path, synced_dir)
            try:
                sync_result = run_ffsubsync(video_path, candidate.subtitle_path, output_path, selected_audio)
            except FixsubError as exc:
                sync_result = SyncResult(attempted=True, succeeded=False, error=str(exc))
            if sync_result.succeeded and sync_result.output_path and sync_result.output_path.exists():
                synced_score = score_alignment(sync_result.output_path, duration_seconds)
        decisions.append(decide_candidate_version(candidate, original_score, sync_result, synced_score))
    return decisions


def _selection_label(decision: CandidateDecision) -> str:
    if decision.sync_result.forced_low_quality and decision.selected_version == "synced":
        return "forced synchronization"
    if decision.selected_version == "original" and decision.sync_result.attempted:
        return "original fallback"
    if decision.selected_version == "synced":
        return "synchronization"
    return "original subtitle"


def run_pipeline(base_dir: Path, options: RunOptions) -> dict[str, object]:
    workdirs = create_workdirs(base_dir)
    log_path = workdirs.logs / "fixsub.log"
    metadata_path = workdirs.metadata / "results.json"
    video_path = detect_video(base_dir)
    movie = parse_movie_info(video_path)
    append_log(log_path, f"Video: {video_path}")

    try:
        clients, provider_warnings = build_provider_clients(options.providers)
    except ProviderConfigError as exc:
        message = str(exc)
        _write_pipeline_metadata(metadata_path, movie=movie, options=options, message=message)
        raise
    for warning in provider_warnings:
        append_log(log_path, warning)

    queries = generate_search_queries(movie)
    search_results: list[SearchResult] = []
    successful_searches = 0
    seen_results: set[tuple[str, str]] = set()
    for query in queries:
        for provider_name, client in clients.items():
            try:
                provider_results = client.search(query)
                successful_searches += 1
            except Exception as exc:
                append_log(log_path, f"Search failed for {provider_name}:{query}: {exc}")
                continue
            for result in provider_results:
                key = (result.provider, result.result_id)
                if key in seen_results:
                    continue
                search_results.append(result)
                seen_results.add(key)
    if queries and successful_searches == 0:
        message = "Subtitle search failed for all providers and queries."
        _write_pipeline_metadata(metadata_path, movie=movie, options=options, queries=queries, message=message)
        raise FixsubError(message)
    ranked_results = rank_search_results(search_results, movie)
    if not ranked_results:
        message = "No subtitle candidates found."
        _write_pipeline_metadata(metadata_path, movie=movie, options=options, queries=queries, message=message)
        raise NoCandidatesError(message)

    try:
        probe = probe_video(video_path)
    except FixsubError as exc:
        _write_pipeline_metadata(metadata_path, movie=movie, options=options, queries=queries, message=str(exc))
        raise
    if options.audio:
        selected_audio = options.audio
    else:
        try:
            selected_audio = select_audio_stream(probe.audio_streams).ffsubsync_id
        except ValueError as exc:
            message = str(exc)
            _write_pipeline_metadata(metadata_path, movie=movie, options=options, queries=queries, message=message)
            raise FixsubError(message) from exc
    typer.echo(f"Selected reference audio: {selected_audio}")

    downloaded, candidates = _download_candidates(clients, ranked_results, base_dir, options.max_candidates)
    decisions = _decide_candidates(
        candidates,
        video_path,
        probe.duration_seconds,
        selected_audio,
        workdirs.synced,
        options.no_sync,
    )
    if not decisions:
        message = "No downloadable or extractable subtitle candidates."
        _write_pipeline_metadata(
            metadata_path,
            movie=movie,
            options=options,
            queries=queries,
            downloaded=downloaded,
            candidates=candidates,
            selected_audio=selected_audio,
            decisions=decisions,
            message=message,
        )
        raise NoCandidatesError(message)

    ranked_decisions = rank_decisions(decisions)
    best = ranked_decisions[0]
    selection_label = _selection_label(best)
    final_output = None
    if options.dry_run:
        confidence = "Low-confidence " if best.is_poor else ""
        message = (
            f"Dry run complete. {confidence}best candidate: {best.candidate.candidate_id} "
            f"({selection_label}, timeline {best.selected_score:.2f})."
        )
    else:
        final_output = write_final_subtitle(best.selected_path, video_path, options.lang, workdirs.original)
        if best.is_poor:
            message = (
                f"Applied low-confidence subtitle ({selection_label}, timeline {best.selected_score:.2f}): "
                f"{final_output}"
            )
        else:
            message = f"Applied subtitle: {final_output}"

    metadata = _write_pipeline_metadata(
        metadata_path,
        movie=movie,
        options=options,
        queries=queries,
        downloaded=downloaded,
        candidates=candidates,
        selected_audio=selected_audio,
        decisions=ranked_decisions,
        final_output=final_output,
        message=message,
    )
    return {"message": message, "metadata": metadata}


def _find_final_subtitle(video_path: Path, lang: str) -> Path:
    matches = [
        final_subtitle_path(video_path, candidate_lang, suffix)
        for candidate_lang in compatible_language_tags(lang)
        for suffix in SUPPORTED_SUBTITLE_SUFFIXES
        if final_subtitle_path(video_path, candidate_lang, suffix).is_file()
    ]
    if not matches:
        raise FixsubError(f"No final subtitle found for {video_path.name} with language tag {lang}.")
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise FixsubError(f"Multiple final subtitles found ({names}); select one with --subtitle.")
    return matches[0]


@auth_app.command("set")
def auth_set() -> None:
    try:
        store_keychain_token_interactive()
    except FixsubError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo("ASSRT token stored in macOS Keychain.")


@auth_app.command("status")
def auth_status() -> None:
    _token, source = get_assrt_token()
    if source == "environment":
        typer.echo("ASSRT token is available from ASSRT_TOKEN.")
    elif source == "keychain":
        typer.echo("ASSRT token is stored in macOS Keychain.")
    else:
        typer.echo("No ASSRT token is configured.", err=True)
        raise typer.Exit(1)


@auth_app.command("delete")
def auth_delete() -> None:
    try:
        delete_keychain_token()
    except FixsubError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo("ASSRT token deleted from macOS Keychain.")


@app.command()
def adjust(
    seconds: float = typer.Option(..., "--seconds", help="Shift timestamps: positive delays, negative advances."),
    lang: str = typer.Option("zh", "--lang", help="Language tag used by the final subtitle."),
    subtitle: Optional[Path] = typer.Option(None, "--subtitle", help="Explicit subtitle path when auto-detection is ambiguous."),
) -> None:
    try:
        base_dir = Path.cwd()
        video_path = detect_video(base_dir)
        subtitle_path = subtitle.expanduser() if subtitle else _find_final_subtitle(video_path, lang)
        if not subtitle_path.is_absolute():
            subtitle_path = base_dir / subtitle_path
        if not subtitle_path.is_file():
            raise FixsubError(f"Subtitle file not found: {subtitle_path}")
        if subtitle_path.suffix.lower() not in SUPPORTED_SUBTITLE_SUFFIXES:
            raise FixsubError(f"Unsupported subtitle format for adjustment: {subtitle_path.suffix or '(none)'}")

        workdirs = create_workdirs(base_dir)
        adjusted_path = workdirs.root / "adjusted" / subtitle_path.name
        shifted_count = shift_subtitle_timing(subtitle_path, adjusted_path, seconds)
        final_output = write_final_subtitle(adjusted_path, video_path, lang, workdirs.original)
        direction = "delayed" if seconds > 0 else "advanced"
        message = f"Adjusted {shifted_count} subtitle cues: {direction} by {abs(seconds):.3f}s -> {final_output}"
        append_log(workdirs.logs / "fixsub.log", message)
        write_results_json(
            workdirs.metadata / "adjustment.json",
            {
                "video": video_path,
                "source_subtitle": subtitle_path,
                "final_output": final_output,
                "seconds": seconds,
                "direction": direction,
                "shifted_cues": shifted_count,
                "message": message,
            },
        )
    except FixsubError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(message)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Process without writing the final subtitle."),
    audio: Optional[str] = typer.Option(None, "--audio", help="Force ffsubsync reference stream, such as a:0."),
    no_sync: bool = typer.Option(False, "--no-sync", help="Skip ffsubsync and rank original candidates only."),
    max_candidates: int = typer.Option(5, "--max-candidates", min=1, help="Maximum candidates to download."),
    lang: str = typer.Option("zh", "--lang", help="Infuse language suffix for final output."),
    providers: str = typer.Option(
        ",".join(DEFAULT_PROVIDERS),
        "--providers",
        help="Comma-separated providers: assrt,subhd.",
    ),
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
            providers=parse_providers(providers),
            debug=debug,
        )
        result = run_pipeline(Path.cwd(), options)
    except FixsubError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(result["message"])
