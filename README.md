# fixsub

[简体中文](README.zh-CN.md)

`fixsub` is a macOS-first command-line tool that finds, validates, synchronizes, and applies Chinese subtitles for a movie stored in a local folder.

> Status: `0.1.0` is an early public release. Use `--dry-run` first with valuable media libraries.

## Features

- Searches ASSRT and SubHD for Chinese subtitle candidates for the video in the current folder.
- Downloads and extracts supported subtitle files, then normalizes them to UTF-8.
- Uses `ffprobe` to choose a reference audio stream and can validate timing with `ffsubsync`.
- Ranks candidates, preserves an existing final subtitle before replacement, and writes an Infuse-compatible Chinese subtitle beside the video.
- Records runtime artifacts and diagnostics under `.fixsub/` so a run can be inspected afterwards.

## How it works

Run `fixsub` from a folder containing the target movie. The tool detects a supported local video, derives search queries, asks the enabled providers for results, ranks them, probes and selects the reference audio, then downloads, extracts, and normalizes subtitle files. It rejects non-Chinese candidates, validates and optionally synchronizes candidates, ranks the decisions, backs up any previous final subtitle, and writes `<video_stem>.zh.<ext>` when a suitable result is found.

This is a one-movie-folder workflow. If the folder contains more than one supported video, the largest file is selected; use a dedicated folder when that is not the intended movie.

## Requirements

- macOS and Python 3.11 or later.
- Homebrew tools for media probing and archive extraction:

  ```bash
  brew install ffmpeg unar
  ```

- Optional audio synchronization support:

  ```bash
  python3 -m pip install ffsubsync
  ```

`ffprobe` is supplied by `ffmpeg`. `unar` handles `.rar` and `.7z` archives; `.zip` extraction is built in. `fixsub` is macOS-first and does not make non-macOS compatibility guarantees.

## Installation

Install from a source checkout in editable mode:

```bash
python3 -m pip install -e ".[dev]"
```

No PyPI package is published. Install the required macOS tools from the Requirements section, and install `ffsubsync` when you want audio-based synchronization rather than the deliberately riskier `--no-sync` mode.

## Authentication

ASSRT uses a token. Store it in the macOS Keychain with:

```bash
fixsub auth set
```

Check the configured source or remove the stored Keychain token with:

```bash
fixsub auth status
fixsub auth delete
```

macOS Keychain is the preferred persistent store. A temporary `ASSRT_TOKEN` environment variable overrides the Keychain value, which is useful for a single shell or automation job. Keep the token out of shell history, issue reports, logs, and committed files. ASSRT is skipped when no token is available and SubHD is also enabled; `fixsub --providers assrt` instead stops and asks for credentials.

## Usage

From a folder containing a movie, run:

```bash
fixsub
```

The default provider set is ASSRT plus SubHD. A final subtitle is written only when the selected candidate is not poor; otherwise inspect the saved candidates and diagnostics.

### Safe preview

```bash
fixsub --dry-run
```

`--dry-run` performs searching, probing, downloading, extraction, validation, and synchronization, and writes `.fixsub/` artifacts, but does not write or replace the final subtitle next to the video. It is the recommended first command for valuable libraries; provider requests and local runtime files still occur.

### Provider selection

```bash
fixsub --providers subhd
fixsub --providers assrt,subhd
```

Use `fixsub --providers subhd` to avoid ASSRT credentials. Use `fixsub --providers assrt,subhd` to explicitly select both providers (also the default). Provider search or download failures are logged and the run can continue with other available providers, but provider outages can leave no usable candidate.

### Audio and synchronization

```bash
fixsub --audio a:0
fixsub --no-sync
```

By default, `fixsub` probes audio with `ffprobe`, selects a reference stream, and tries `ffsubsync` for each candidate. `fixsub --audio a:0` forces the stream passed to `ffsubsync`. `fixsub --no-sync` skips audio synchronization and ranks original candidates only; use it only when necessary because structural timestamp checks cannot establish dialogue or audio alignment. A failed or low-quality synchronization makes a candidate poor and prevents automatic application.

### Candidate and language controls

```bash
fixsub --max-candidates 5
fixsub --lang zh-Hans
```

`--max-candidates` limits the ranked provider results selected for download (the default is `5`), which controls run time and provider traffic. One downloaded archive can contain multiple subtitle files, so the number of extracted candidates can exceed this value. `--lang` controls the final subtitle suffix; the default `zh` produces `<video_stem>.zh.<ext>`, while `zh-Hans` is available when that tag is required by the media library.

### Manual timing adjustment

```bash
fixsub adjust --seconds 1.0
fixsub adjust --seconds -1.0
```

`adjust` shifts the detected final subtitle without searching or running synchronization again. Positive seconds delay subtitle cues and negative seconds advance them. The command backs up the replaced final subtitle under `.fixsub/original/` and records the adjustment in `.fixsub/metadata/adjustment.json`; verify the result in your player before keeping the change.

### Diagnostics

```bash
fixsub --debug
```

`--debug` is accepted and recorded in the run options inside `.fixsub/metadata/results.json`. In this early release it does not add separate verbose console output, so inspect that metadata file and `.fixsub/logs/fixsub.log` for diagnostics. Treat both files as private run data before sharing them.

## Output and backups

The applied subtitle is written beside the detected video as:

```text
<video_stem>.zh.<ext>
```

Each run creates or reuses these local working paths:

- `.fixsub/downloads/` holds downloaded provider files.
- `.fixsub/candidates/` holds extracted, UTF-8-normalized subtitle candidates.
- `.fixsub/synced/` holds subtitle files produced by successful synchronization.
- `.fixsub/original/` holds timestamped backups before a final subtitle is replaced, including by `adjust`.
- `.fixsub/logs/fixsub.log` records provider and run diagnostics.
- `.fixsub/metadata/results.json` records the video, options, queries, downloads, candidates, decisions, selected audio, output path, and result message.

## Privacy and security

Use `fixsub auth set` rather than placing an ASSRT token in project files. `ASSRT_TOKEN` is supported for temporary use and takes precedence over Keychain, but it is still a secret. The log writer redacts the active token from messages, yet logs and metadata can contain movie filenames, provider data, and local paths.

Before opening an issue, remove `.fixsub/logs/fixsub.log`, `.fixsub/metadata/results.json`, downloaded data, and every token or private path unless the information is necessary and has been carefully sanitized. Never paste credentials into an issue, command transcript, or screenshot.

## Troubleshooting

- **`ffprobe` is missing:** install it with `brew install ffmpeg`, then ensure Homebrew's binaries are on your `PATH`.
- **A `.rar` or `.7z` archive cannot be extracted:** install archive support with `brew install unar` and retry. `.zip` files do not need `unar`.
- **ASSRT reports missing credentials:** run `fixsub auth set`, check `fixsub auth status`, or set a temporary `ASSRT_TOKEN`. Use `fixsub --providers subhd` if you do not intend to use ASSRT.
- **A provider is unavailable or no candidate is found:** retry later, select another provider, and inspect `.fixsub/logs/fixsub.log`; provider results and downloads can change independently of the tool.
- **Candidates are rejected as low confidence:** inspect `.fixsub/candidates/` and `.fixsub/metadata/results.json`. Low structural timing scores or failed synchronization intentionally prevent automatic output.
- **Synchronization fails:** install `ffsubsync`, confirm `ffprobe` can read the video, choose the correct stream with `fixsub --audio a:0`, and inspect the log. `fixsub --no-sync` is available only as a manual-risk fallback.

## Development

Run the test suite with:

```bash
.venv/bin/python -m pytest -q
```

Build a distribution artifact locally with:

```bash
python -m build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contributor workflow, testing, and privacy expectations. Building locally does not publish a package.

## Current limitations

Interactive mode, library scanning, Whisper subtitle generation, translation, and a Web UI are not implemented. There are no non-macOS compatibility guarantees and no PyPI distribution. Candidate ranking and synchronization reduce risk, but automatic perfect dialogue matching is not implemented or guaranteed.

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before contributing. Report security concerns through [SECURITY.md](SECURITY.md), not in a public issue. Release history is in [CHANGELOG.md](CHANGELOG.md).

## License

This project is licensed under the [MIT License](LICENSE).
