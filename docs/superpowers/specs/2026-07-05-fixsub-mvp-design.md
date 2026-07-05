# fixsub MVP Design

Date: 2026-07-05

## Purpose

`fixsub` is a macOS-first CLI for on-demand Chinese subtitle search, validation, sync, and application inside a single movie folder. The first version is intentionally narrow: it must make the main path work with ASSRT API, `ffprobe`, `ffsubsync`, and original-vs-synced comparison before adding more providers or interactive flows.

The core product rule is: do not blindly use synced output. Score the original subtitle, sync only when needed, score the synced subtitle, and apply the synced version only when it is materially better.

## M1 Scope

In scope:

- Run `fixsub` from the current movie folder.
- Detect the main local video file.
- Generate ASSRT search queries from the video filename.
- Use ASSRT official API with `ASSRT_TOKEN`.
- Download up to `--max-candidates` subtitle candidates.
- Extract supported archives and collect `.ass`, `.ssa`, and `.srt` files.
- Normalize subtitle text to UTF-8.
- Detect audio streams through `ffprobe`.
- Select an audio reference stream, preferring English/default/5.1/first.
- Map ffprobe audio streams to ffsubsync stream ids such as `a:0`.
- Score original subtitle alignment.
- Run `ffsubsync` only when original alignment is below the excellent threshold.
- Score synced subtitle alignment.
- Compare original and synced versions before choosing.
- Output an Infuse-compatible subtitle file next to the video.
- Preserve downloads, candidates, synced outputs, logs, and metadata under `.fixsub/`.

Out of scope for M1:

- SubHD provider.
- ASSRT web fallback provider.
- `--interactive`.
- Full config file support.
- Full library scan.
- Web UI.
- Whisper generation.
- Machine translation.
- Login, CAPTCHA, paywall, or anti-bot bypass.

## CLI Surface

M1 supports:

```bash
fixsub
fixsub --dry-run
fixsub --audio a:0
fixsub --no-sync
fixsub --max-candidates 5
fixsub --lang zh-Hans
fixsub --debug
fixsub --providers assrt
```

`--providers` is accepted for forward compatibility, but M1 only allows `assrt`. Other provider names fail with a clear "not implemented in M1" message.

## Architecture

Use Python 3.11+ with:

- `typer` for the CLI.
- `httpx` for HTTP.
- `rich` for terminal output.
- `pytest` for tests.
- Standard-library `dataclasses` for models unless implementation complexity later justifies Pydantic.

Proposed package layout:

```text
fixsub/
  pyproject.toml
  README.md
  fixsub/
    __init__.py
    cli.py
    models.py
    paths.py
    movie.py
    providers/
      __init__.py
      assrt_api.py
    download.py
    extract.py
    encoding.py
    ffprobe.py
    subtitles.py
    alignment.py
    sync.py
    decision.py
    ranking.py
    output.py
    logging_utils.py
  tests/
```

Module responsibilities:

- `cli.py`: parse options, orchestrate the run, print final status.
- `models.py`: shared data structures for videos, streams, search results, candidates, scores, and decisions.
- `paths.py`: create and expose `.fixsub/` subdirectories.
- `movie.py`: detect video files, choose the largest in default mode, parse filename metadata, generate search queries.
- `providers/assrt_api.py`: read `ASSRT_TOKEN`, search ASSRT, parse responses, download results.
- `download.py`: save provider downloads with stable candidate ids.
- `extract.py`: unpack `.zip`, `.rar`, and `.7z`; use Python zip support where possible and system `unar`/`unrar` for rar-like archives.
- `encoding.py`: normalize subtitle files to UTF-8 while preserving format.
- `ffprobe.py`: call `ffprobe`, parse JSON, select and map audio streams.
- `subtitles.py`: parse `.srt`, `.ass`, and `.ssa` timing intervals.
- `alignment.py`: compute an explainable MVP alignment score.
- `sync.py`: call `ffs` and preserve failures as candidate metadata.
- `decision.py`: implement original-vs-synced selection rules.
- `ranking.py`: combine alignment, pre-download match signals, language/format preference, and provider priority.
- `output.py`: back up existing output and write `<video_stem>.<lang>.<ext>`.
- `logging_utils.py`: write human logs and machine-readable run metadata.

## Data Flow

1. User runs `fixsub` inside a movie folder.
2. The CLI creates:

   ```text
   .fixsub/
     downloads/
     candidates/
     synced/
     original/
     logs/
     metadata/
   ```

3. `movie.py` detects supported video files: `.mkv`, `.mp4`, `.m4v`, `.avi`, `.mov`.
4. If one video exists, use it. If multiple exist in M1 default mode, use the largest file.
5. Generate ASSRT search queries in this order:
   - Original video filename stem.
   - Cleaned title + year + source when available.
   - Cleaned title + year when available.
6. ASSRT API searches with `ASSRT_TOKEN`; missing token is a hard stop with a clear message.
7. Search results receive a pre-download score based on title/year/source/release tokens, Chinese/bilingual signals, format, and ASSRT provider priority.
8. Download the top N results, where N comes from `--max-candidates`.
9. Extract archives and collect supported subtitle files.
10. Normalize collected subtitle files into `.fixsub/candidates/`.
11. Use `ffprobe` JSON output to list audio streams.
12. Select the reference stream unless `--audio` is provided.
13. For each subtitle candidate:
    - Score original alignment.
    - Skip sync if original score is excellent.
    - Otherwise run `ffs` unless `--no-sync` is set.
    - Score synced output when sync succeeds.
    - Decide original vs synced.
14. Rank candidate decisions.
15. If the best candidate is high confidence, write final subtitle next to the video.
16. If no high-confidence candidate exists, do not write final output; preserve candidates and report where to inspect them.
17. Always write `.fixsub/logs/fixsub.log` and `.fixsub/metadata/results.json`.

## Audio Selection

`ffprobe.py` calls `ffprobe` with JSON output and parses audio stream metadata.

Selection order:

1. English language metadata.
2. Default disposition.
3. More channels, preferring 5.1 over stereo.
4. First audio stream.

Mapping rule:

- First audio stream in ffprobe result becomes `a:0`.
- Second audio stream becomes `a:1`.
- This mapping is independent of the container stream index.

If the user passes `--audio`, M1 trusts that value and uses it directly.

## Alignment Scoring

M1 implements an explainable heuristic score from 0.0 to 1.0. It parses subtitle timing intervals and video duration, then scores:

- Valid parse rate.
- First subtitle timing plausibility.
- Last subtitle timing plausibility.
- Subtitle coverage span relative to video duration.
- Subtitle density plausibility.
- Absence of negative, overlapping, or out-of-video intervals.
- Lack of very long subtitle gaps inside the main subtitle span.

If `ffmpeg` is available and the implementation can do this cheaply, `alignment.py` may use `silencedetect` as an optional extra signal. Audio activity is not required for M1 correctness; the score must still work from subtitle timing and video duration alone.

The score is meant to compare:

- Original subtitle vs synced subtitle for the same candidate.
- Candidate A vs candidate B.

It is not presented as a perfect alignment detector.

## Sync Decision

Use these M1 thresholds:

```text
EXCELLENT_ALIGNMENT = 0.90
SYNC_IMPROVEMENT_THRESHOLD = 0.08
POOR_ALIGNMENT = 0.50
```

Decision rules:

1. Score original subtitle.
2. If original score is `>= 0.90`, skip sync and select original.
3. If `--no-sync` is set, select original and mark sync as skipped by option.
4. Otherwise run:

   ```bash
   ffs "<video>" \
     --reference-stream "<audio_stream>" \
     --skip-sync-on-low-quality \
     -i "<candidate_subtitle>" \
     -o "<synced_output>"
   ```

5. If sync fails, keep original as the candidate version and record the failure.
6. If sync succeeds, score synced output.
7. Select synced only when `synced_score >= original_score + 0.08`.
8. If both original and synced scores are below `0.50`, mark the candidate as poor.
9. The final run is successful only if the selected best candidate is not poor.

## Output Behavior

The final subtitle path is:

```text
<video_stem>.<lang>.<ext>
```

Default language is `zh-Hans`. The subtitle extension is preserved from the selected candidate.

If the final output path already exists:

1. Copy the existing subtitle into `.fixsub/original/<timestamp>.<filename>`.
2. Write the new selected subtitle.

M1 never overwrites an existing subtitle without a backup.

`--dry-run` performs detection, search, ranking, and metadata writing, but does not write the final subtitle next to the video.

## Error Handling

Hard stops:

- No supported video file in the current directory.
- Missing `ASSRT_TOKEN`.
- `ffprobe` unavailable or unable to inspect the selected video.
- No downloadable or extractable ASSRT candidates.

Soft failures:

- One ASSRT search query fails: continue with other queries.
- One download fails: continue with other candidates.
- One archive extraction fails: record and continue.
- One candidate has no supported subtitle file: record and continue.
- `ffsubsync` fails for one candidate: keep original candidate and continue.
- Alignment scoring cannot parse one subtitle: assign a very low score and continue.

Missing external tools should print macOS-oriented install hints:

```bash
brew install ffmpeg unar
python3 -m pip install ffsubsync
```

## Metadata

Write `.fixsub/metadata/results.json` with:

- Video path and parsed metadata.
- Created working directories.
- CLI options.
- ASSRT search queries.
- Search results and pre-download scores.
- Downloaded files.
- Extraction results.
- Candidate subtitle files.
- Audio streams and selected reference stream.
- Original alignment scores.
- Sync attempts and failures.
- Synced alignment scores.
- Original-vs-synced decisions.
- Final ranking.
- Final output path or no-success reason.
- Warnings and errors.

## Testing

Default tests must avoid live network calls and real media dependencies.

Unit tests:

- Video detection and largest-file selection.
- Filename metadata parsing.
- Search query generation.
- ASSRT response parsing with fixtures.
- Pre-download ranking.
- `ffprobe` JSON parsing.
- Audio stream selection and `a:x` mapping.
- SRT timing parsing.
- ASS/SSA timing parsing.
- Alignment heuristic scoring for plausible, early, late, sparse, and invalid subtitles.
- Original-vs-synced decision thresholds.
- Output filename generation.
- Existing subtitle backup behavior.
- Metadata serialization shape.

Integration-style tests should mock subprocess calls for `ffprobe` and `ffs`.

Manual acceptance:

- Run `fixsub --dry-run` in a sample movie folder with `ASSRT_TOKEN`.
- Run `fixsub` against a movie with available ASSRT Chinese subtitles.
- Confirm that already-aligned subtitles skip sync.
- Confirm that materially improved synced subtitles are selected.
- Confirm that worse synced subtitles do not replace originals.

## Acceptance Criteria

M1 is complete when:

- `fixsub` can be installed in editable mode and invoked as a CLI.
- Running inside a folder with one movie file detects that file.
- ASSRT API searches use the original filename query first.
- At least one downloadable ASSRT candidate can be processed when ASSRT provides one.
- `ffprobe` selects and prints the reference audio stream.
- Each candidate records original alignment score.
- `ffsubsync` runs only when sync is allowed and original score is not excellent.
- Synced output is selected only when it improves by at least `0.08`.
- Existing final subtitles are backed up before replacement.
- Successful runs produce `<video_stem>.zh-Hans.<ext>`.
- Low-confidence runs do not pretend success and preserve review artifacts under `.fixsub/`.
- Tests cover the deterministic parts of the system.
