# fixsub

`fixsub` is a macOS-first CLI for on-demand Chinese subtitle search, validation, sync, and application inside one movie folder.

The M1 MVP is designed for the common local workflow: open a folder that contains one movie file, run `fixsub`, and get an Infuse-compatible Chinese subtitle written next to the video.

## Provider Support

`fixsub` supports these subtitle sources:

- ASSRT official API search through `ASSRT_TOKEN`
- ASSRT public web download fallback when the API search result download returns `404`
- SubHD public search through `https://subhd.tv/search/<query>`

The default provider list is:

```bash
fixsub --providers assrt,subhd
```

If `ASSRT_TOKEN` is missing, ASSRT is skipped when another provider is enabled. If you explicitly run `fixsub --providers assrt` without `ASSRT_TOKEN`, the command stops and asks for the token.

## M1 Support

M1 supports:

- Video detection in the current folder
- ASSRT search and download, including web fallback for stale API download links
- SubHD search and download
- Archive extraction for `.zip`, `.rar`, and `.7z`
- Subtitle normalization to UTF-8
- Audio detection through `ffprobe`
- Optional sync through `ffsubsync`
- Original-vs-synced scoring and comparison
- Infuse-compatible output naming

M1 does not implement interactive mode, library scanning, Whisper generation, translation, or a Web UI.

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

ASSRT is optional when SubHD is enabled, but recommended because it gives `fixsub` another source to compare.

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

Fine-tune an existing final subtitle without searching or running ffsubsync again. Positive values delay subtitles; negative values advance them:

```bash
fixsub adjust --seconds 1.0
fixsub adjust --seconds -1.0
```

The existing final subtitle is backed up under `.fixsub/original/`, and the adjustment is recorded in `.fixsub/metadata/adjustment.json`.

Inspect candidates without audio validation or subtitle sync:

```bash
fixsub --no-sync
```

The reported timeline score only checks whether subtitle timestamps look structurally plausible within the video duration. It does not prove that the dialogue matches the movie or that the timing matches the audio. Unless `--no-sync` is explicit, every candidate must pass ffsubsync audio validation before it can be applied automatically.

Limit the number of candidates:

```bash
fixsub --max-candidates 5
```

Set the output subtitle language tag:

```bash
fixsub --lang zh-Hans
```

Use only SubHD:

```bash
fixsub --providers subhd
```

Use ASSRT and SubHD:

```bash
fixsub --providers assrt,subhd
```

Use only ASSRT:

```bash
fixsub --providers assrt
```

Preview a real movie folder with more candidates:

```bash
fixsub --dry-run --max-candidates 20
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
- `--providers assrt,subhd`
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

Provider failures are recorded in `.fixsub/logs/fixsub.log`. ASSRT tokens are redacted before log lines are written.

## Manual Acceptance Checklist

1. Put one movie file in a local test folder.
2. Run `fixsub --dry-run`.
3. Confirm `.fixsub/metadata/results.json` is written.
4. Run `fixsub` with a movie that has ASSRT Chinese subtitles.
5. Confirm selected audio is printed as `a:0`, `a:1`, or another ffsubsync stream id.
6. Confirm every candidate attempts ffsubsync unless `--no-sync` is explicit.
7. Confirm `results.json` records the ffsubsync score, offset, and framerate scale.
8. Confirm a low-quality or unchanged ffsubsync result is rejected even when the original timeline score is `1.00`.
9. Confirm the selected candidate reports `selected_version: "synced"` before automatic output.
10. Confirm existing final subtitles are backed up before replacement.
