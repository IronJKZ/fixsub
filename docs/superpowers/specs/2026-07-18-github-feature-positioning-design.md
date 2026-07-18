# GitHub feature positioning design

## Context

The public repository is technically complete, but its most visible feature list understates subtitle synchronization. The current wording says that `ffsubsync` validates timing even though the default pipeline also produces synchronized subtitle candidates, rejects low-quality synchronization results, and selects a usable synchronized output. Manual timeline adjustment is documented later in the README but is absent from the feature summary.

The repository metadata has the same discoverability problem: the About description mentions generic "sync," while the topics do not include the subtitle-synchronization terms a user is likely to search for. Installation is written primarily for contributors, and the supported media formats are not listed together.

## Goals

- Make automatic audio-based subtitle synchronization a clear primary capability.
- Distinguish automatic synchronization from manual whole-timeline adjustment.
- Keep the English and Simplified Chinese READMEs semantically equivalent.
- Give end users a normal source-install path without development dependencies.
- State supported video, subtitle, and archive formats explicitly.
- Align package metadata, GitHub About text, and repository topics with the README.
- Add compact status badges that reflect existing CI, release, Python, and license information.
- Preserve the existing `0.1.0` release, product behavior, security posture, and scope.

## Non-goals

- No production-code changes.
- No version bump, tag, Release, or CHANGELOG rewrite.
- No PyPI publication or new distribution channel.
- No demo GIF, architecture diagram, documentation site, or broader README redesign.
- No change to branch protection, Actions, Dependabot, or repository security settings.

## Considered approaches

### 1. Feature-list-only correction

Change the two feature lists and leave all other public information unchanged. This is the smallest diff, but installation, format support, About text, and discovery topics remain weaker than the implementation.

### 2. Complete but restrained information pass

Update the bilingual feature summaries and workflow text, add end-user installation and supported-format information, align package and GitHub metadata, and add existing-status badges. Protect the content with repository-contract tests and publish through a focused pull request.

This is the selected approach because it fixes every confirmed information gap without changing the product or reopening the initial release.

### 3. Full launch-page redesign

Add visual demos, diagrams, a documentation site, and rewritten release material. This would create a larger maintenance surface and is unnecessary for the current early release.

## Public content design

### Feature positioning

Both READMEs will state that:

- `ffprobe` selects the reference audio stream.
- By default, `ffsubsync` aligns each downloaded subtitle candidate to the movie audio.
- Low-quality or incomplete synchronization results are rejected and are not applied automatically.
- `fixsub adjust --seconds` can advance or delay the final subtitle as a separate manual operation.
- Manual adjustment preserves the replaced subtitle and records adjustment metadata.

The workflow section will say that synchronization is attempted by default when `ffsubsync` is available and that `--no-sync` explicitly skips it. It will not describe synchronization as merely validation or as an unspecified optional phase.

### Installation

The installation section will separate two audiences:

- End users: clone the repository, create and activate a virtual environment, install the package with `python3 -m pip install .`, and install `ffsubsync` when using the default audio-synchronization workflow.
- Contributors: use the editable development install `python3 -m pip install -e ".[dev]"` and follow `CONTRIBUTING.md`.

The documentation will continue to state that no PyPI package is published.

### Supported formats

A compact table will list formats derived from the implementation:

- Video: `.mkv`, `.mp4`, `.m4v`, `.avi`, `.mov`
- Subtitle: `.srt`, `.ass`, `.ssa`
- Download/archive: `.zip`, `.rar`, `.7z`, plus direct supported subtitle files

The existing dependency distinction remains: `.zip` uses built-in extraction, while `.rar` and `.7z` require `unar`.

### Badges

The English README will show compact badges for the existing GitHub Actions CI workflow, latest GitHub Release, supported Python baseline, and MIT license. The Chinese README will use the same badges and targets so both entry points expose the same project status.

## Metadata design

The package description will explicitly mention automatic audio synchronization, and its keywords will add synchronization-focused terms without removing the current relevant keywords.

After the content pull request is merged, the GitHub About description will be updated to:

> macOS CLI that finds Chinese subtitles, auto-syncs them to movie audio, and writes Infuse-ready files.

The repository will retain its current topics and add:

- `subtitle-sync`
- `subtitle-synchronization`
- `ffsubsync`
- `chinese-subtitles`

About and topics will not be changed before the pull request is merged, preventing temporary disagreement between repository metadata and the default-branch README.

## Testing and validation

Repository-contract tests in `tests/test_public_repository.py` will be updated before the documentation and metadata changes. The new assertions will cover:

- Automatic audio synchronization and low-quality rejection in both READMEs.
- Manual adjustment in both feature lists.
- End-user and contributor installation commands.
- All supported format groups.
- Badge targets.
- The synchronization-focused package description and keywords.

The new tests must first fail for the expected missing or outdated public information. After the minimal documentation and metadata changes, the targeted tests and the complete test suite must pass. Final local validation will also include CLI help, package build, `git diff --check`, tracked-file personal-path checks, and a review of the exact diff.

## Publication flow

Work will remain isolated on `codex/github-info-polish`. Only the design, implementation plan, bilingual READMEs, `pyproject.toml`, and the related public-contract test changes belong in scope.

The branch will be pushed and opened as a draft pull request against `main`. Python 3.11 and Python 3.14 CI must pass. The pull request will not modify or recreate `v0.1.0`. GitHub About and topics will be changed only after the content pull request is merged and the default branch contains the matching documentation.

## Acceptance criteria

- A reader sees automatic audio-based subtitle synchronization in the first feature screen.
- A reader can distinguish automatic synchronization from manual offset adjustment.
- English and Chinese public descriptions make the same promises.
- A normal user can install without development dependencies.
- Supported formats are discoverable without reading source code.
- README, package metadata, About text, and topics use consistent positioning.
- Existing behavior, versioning, release assets, CI, and security settings remain unchanged.
- All local and remote checks pass before the change is described as complete.
