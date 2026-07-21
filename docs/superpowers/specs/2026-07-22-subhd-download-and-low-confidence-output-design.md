# SubHD Download and Low-Confidence Output Design

**Date:** 2026-07-22

**Status:** Approved for implementation planning

## Goal

Restore compatibility with SubHD's current prepared-download flow and make `fixsub` fulfill its best-effort repair contract: when at least one downloadable, extractable, parseable Chinese subtitle exists, select the best candidate, attempt audio synchronization, and write a final subtitle even when synchronization confidence is low.

## Scope

This change covers two related pipeline failures:

1. SubHD search results are found but downloads fail because the client directly opens `/down/{sid}` without first preparing that temporary page.
2. Candidates are retained but no final subtitle is written when `ffsubsync` rejects a low-quality alignment or the selected candidate otherwise remains low-confidence.

The change does not add providers, alter movie detection, introduce interactive candidate selection, or replace the existing ranking model.

## Confirmed User Experience

- `fixsub` continues to prefer high-confidence candidates.
- `ffsubsync` first runs conservatively with `--skip-sync-on-low-quality`.
- When that conservative pass explicitly rejects a low-quality alignment, `fixsub` automatically retries without `--skip-sync-on-low-quality` and accepts the best alignment that `ffsubsync` can produce.
- When synchronization fails for another reason, `fixsub` falls back to the best original Chinese subtitle.
- A normal run writes a final subtitle whenever at least one usable Chinese candidate exists.
- A low-confidence or original-fallback result is clearly identified in the console message and metadata.
- `--dry-run` never writes the final subtitle, but reports which candidate and version would be selected and whether the result is low-confidence.
- A run still fails without output when no candidate can be downloaded, extracted, normalized, parsed, or accepted as Chinese.
- Original downloads and normalized candidates remain under `.fixsub/` for inspection and recovery.

## Architecture

The provider and synchronization changes remain inside their existing boundaries:

- `fixsub/providers/subhd.py` owns SubHD's prepared-download protocol and URL validation.
- `fixsub/sync.py` owns conservative synchronization and the forced low-quality retry.
- `fixsub/models.py` records whether a successful synchronization required the forced retry.
- `fixsub/decision.py` continues to classify confidence and select synced versus original content.
- `fixsub/cli.py` ranks decisions and applies the best usable result, treating low confidence as a warning rather than an output veto.

No new runtime dependency is required.

## SubHD Download Flow

For each selected SubHD search result, the client performs these requests in one persistent `httpx.Client` session:

1. `GET /a/{sid}` to load the subtitle detail page.
2. `POST /api/sub/prepare-download` with JSON `{"sid": sid}` and the detail page as `Referer`.
3. Validate the JSON response and resolve its `url` value.
4. `GET` the prepared `/down/{sid}` page using the detail page as `Referer`.
5. If that response is already a subtitle or archive, save it through the existing direct-download path.
6. Otherwise, `POST /api/sub/down` with JSON `{"sid": sid}` and the prepared page as `Referer`.
7. Validate and download the returned subtitle or archive URL through the existing bounded redirect and content checks.

The preparation response must be a JSON object with `success: true` and a non-empty string `url`. The resolved URL must:

- use HTTPS;
- belong to an allowed SubHD-owned domain or the configured test host;
- have a path exactly equal to `/down/{sid}`;
- contain no username, password, non-default port, query string, or fragment.

Preparation network failures, invalid JSON, rejection responses, missing URLs, and unsafe URLs become specific `FixsubError` messages. Existing URL validation remains in force for the final downloadable file.

## Two-Pass Synchronization

`run_ffsubsync` first executes its existing conservative command with `--skip-sync-on-low-quality`.

If the command reports a low-quality alignment or that it is leaving subtitles unmodified:

1. Delete any conservative-pass output.
2. Run `ffsubsync` again with the same video, subtitle, output path, and reference audio stream, but without `--skip-sync-on-low-quality`.
3. Require the forced pass to exit successfully, create the output file, and expose the same complete alignment metrics required today.
4. Return a successful `SyncResult` with `forced_low_quality=True`.

A normal first-pass success returns `forced_low_quality=False`. A forced-pass process failure, missing output, or incomplete metrics remains a synchronization failure and triggers original-subtitle fallback in candidate selection.

The retry is narrowly triggered only by the existing low-quality diagnostic phrases. Other failures are not retried because they indicate dependency, input, process, or output problems rather than a confidence policy decision.

## Selection and Output Behavior

Candidate confidence remains meaningful:

- `is_poor=False` identifies a high-confidence selected result.
- `is_poor=True` identifies a low-confidence result, including forced low-quality synchronization and original fallback after synchronization failure.
- `rank_decisions` continues to place high-confidence decisions before low-confidence decisions, then compare selected timeline score, provider pre-score, and subtitle format as it does today.

The output gate changes:

- If there are no candidate decisions, raise `NoCandidatesError` as today.
- Otherwise, choose the top-ranked decision even when `is_poor=True`.
- In a normal run, write that decision's selected path through `write_final_subtitle`, preserving the existing backup behavior.
- In a dry run, do not write the final subtitle.

Console messages distinguish four outcomes:

- high-confidence normal application;
- low-confidence forced synchronization application;
- low-confidence original-subtitle fallback application;
- the corresponding dry-run selections without writing output.

Messages identify the candidate, selected version, and timeline score so the user can inspect the decision without opening metadata.

## Metadata

`SyncResult` gains a boolean `forced_low_quality` field with a default of `False`. Existing serialization includes it automatically.

The existing decision record retains:

- `is_poor` as the confidence warning;
- `selected_version` as `original` or `synced`;
- synchronization metrics and errors;
- `decision_reason` describing normal synchronization, forced synchronization, or original fallback.

`final_output` is populated for low-confidence normal runs and remains null for every dry run.

## Error Handling and Safety

- Provider errors continue to be isolated per candidate and written to `.fixsub/logs/fixsub.log`.
- SubHD preparation and download URLs are validated before requests to prevent redirects or API responses from sending the client to arbitrary hosts.
- Download response content continues to reject empty or HTML payloads and to identify supported archive or subtitle formats by signature and metadata.
- Low confidence is visible and retained in metadata; it is not silently presented as high confidence.
- Existing final subtitles are backed up before replacement.
- Forced synchronization never overwrites normalized candidates; it writes under `.fixsub/synced/` before final application.

## Testing

Tests are added test-first for these behaviors:

1. SubHD performs detail, prepare, gate, download-API, and final-file requests in order.
2. SubHD rejects invalid preparation JSON, rejected preparation responses, missing URLs, and unsafe or mismatched prepared URLs.
3. A conservative low-quality result triggers exactly one forced retry without `--skip-sync-on-low-quality`.
4. A normal conservative success does not retry.
5. A forced retry failure returns a failed synchronization result and leaves no stale output.
6. A forced retry success records `forced_low_quality=True` and supplies complete metrics.
7. A low-confidence synced decision is applied during a normal run with a warning message.
8. A synchronization failure applies the best original Chinese candidate with a warning message.
9. Low-confidence dry runs report the selected candidate without creating a final subtitle.
10. Runs with no usable Chinese candidate still fail without a final subtitle.

Focused tests run before the complete test suite. The final verification includes the full pytest suite and a live SubHD dry run or equivalent protocol probe against a current public subtitle result.

## Documentation

The English and Chinese README files are updated to explain:

- SubHD's prepared-download support;
- the conservative then forced synchronization behavior;
- the fact that low confidence produces a warned best-effort output instead of blocking the final subtitle;
- the remaining hard-stop condition when no usable Chinese candidate exists;
- where to find original, candidate, synchronized, log, and metadata artifacts.
