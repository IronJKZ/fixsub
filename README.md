# fixsub

`fixsub` is a macOS-first CLI for on-demand Chinese subtitle search, validation, sync, and application inside one movie folder.

The M1 MVP is designed for the common local workflow: open a folder that contains one movie file, run `fixsub`, and get an Infuse-compatible Chinese subtitle written next to the video.

## M1 Support

M1 supports:

- ASSRT official API search through `ASSRT_TOKEN`
- Video detection in the current folder
- ASSRT search and download
- Archive extraction for `.zip`, `.rar`, and `.7z`
- Subtitle normalization to UTF-8
- Audio detection through `ffprobe`
- Optional sync through `ffsubsync`
- Original-vs-synced scoring and comparison
- Infuse-compatible output naming

M1 does not implement SubHD, ASSRT web fallback, interactive mode, library scanning, Whisper generation, translation, or a Web UI.

## Install

Install the Python package in editable mode:

```bash
python3 -m pip install -e ".[dev]"
```

Install the required macOS tools:

```bash
brew install ffmpeg unar
```

Install optional subtitle sync support:

```bash
python3 -m pip install ffsubsync
```

Configure ASSRT API access:

```bash
export ASSRT_TOKEN="your-token"
```

## Usage

Run `fixsub` from inside a movie folder. M1 expects the current folder to contain the target movie file.

Basic run:

```bash
fixsub
```

Preview what would happen without replacing or writing the final subtitle:

```bash
fixsub --dry-run
```

Select a specific audio stream for sync:

```bash
fixsub --audio a:0
```

Search, validate, and score candidates without running subtitle sync:

```bash
fixsub --no-sync
```

Limit the number of candidates:

```bash
fixsub --max-candidates 5
```

Set the output subtitle language tag:

```bash
fixsub --lang zh-Hans
```

Use the ASSRT provider:

```bash
fixsub --providers assrt
```

Print detailed diagnostic output:

```bash
fixsub --debug
```

Supported M1 options:

- `--dry-run`
- `--audio a:0`
- `--no-sync`
- `--max-candidates 5`
- `--lang zh-Hans`
- `--providers assrt`
- `--debug`

## Output

The final subtitle is written next to the detected video using Infuse-compatible naming:

```text
<video_stem>.zh-Hans.<ext>
```

When an existing final subtitle would be replaced, it is backed up first:

```text
.fixsub/original/<timestamp>.<filename>
```

Runtime artifacts are written under `.fixsub/`:

- `.fixsub/downloads/`
- `.fixsub/candidates/`
- `.fixsub/synced/`
- `.fixsub/logs/fixsub.log`
- `.fixsub/metadata/results.json`

## Manual Acceptance Checklist

1. Put one movie file in a local test folder.
2. Run `fixsub --dry-run`.
3. Confirm `.fixsub/metadata/results.json` is written.
4. Run `fixsub` with a movie that has ASSRT Chinese subtitles.
5. Confirm selected audio is printed as `a:0`, `a:1`, or another ffsubsync stream id.
6. Confirm excellent original subtitles skip sync.
7. Confirm a materially better synced subtitle is selected when its score improves by at least `0.08`.
8. Confirm worse synced subtitles do not replace originals.
9. Confirm existing final subtitles are backed up before replacement.
