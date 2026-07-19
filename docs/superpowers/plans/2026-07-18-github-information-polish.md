# GitHub Information Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public repository clearly present automatic audio-based subtitle synchronization, manual timing adjustment, supported formats, and end-user installation while keeping GitHub and package metadata consistent.

**Architecture:** Treat public documentation and metadata as a tested interface. Add failing repository-contract assertions first, make the smallest bilingual README and `pyproject.toml` changes that satisfy them, then publish through the protected-branch pull-request flow. Update GitHub About and topics only after the pull request is merged so remote metadata never leads the default-branch documentation.

**Tech Stack:** Markdown, Python 3.11+, pytest, TOML/PEP 621, Git, GitHub Actions, GitHub CLI.

## Global Constraints

- Work only on `codex/github-info-polish`; do not modify the original `main` worktree or its untracked `.superpowers/` directory.
- No production-code changes.
- No version bump, tag, Release, CHANGELOG rewrite, or PyPI publication.
- Keep English and Simplified Chinese READMEs semantically equivalent.
- Keep `0.1.0`, Python `>=3.11`, MIT, macOS-first scope, CI, security settings, and branch protection unchanged.
- Do not change GitHub About or topics until the content pull request is merged.
- Stage explicit paths only; never use `git add -A` in the original checkout.

## File map

- Modify `tests/test_public_repository.py`: enforce the public wording, installation, formats, badges, and package metadata as repository contracts.
- Modify `README.md`: improve English feature positioning, workflow, installation, format support, and badges.
- Modify `README.zh-CN.md`: make the same promises and instructions in Simplified Chinese.
- Modify `pyproject.toml`: align the package description and keywords with automatic audio synchronization.
- Do not modify files under `fixsub/`: the implementation already supports the documented behavior.
- Remote-only after merge: update the GitHub About description and repository topics.

---

### Task 1: Make automatic and manual synchronization visible

**Files:**
- Modify: `tests/test_public_repository.py`
- Modify: `README.md:1-21`
- Modify: `README.zh-CN.md:1-21`

**Interfaces:**
- Consumes: existing `_read(path: str) -> str` test helper and the implemented `ffsubsync`/`adjust` behavior.
- Produces: bilingual feature lists and workflow text that later metadata must summarize.

- [ ] **Step 1: Add the failing bilingual feature-positioning test**

Append this test near the other README contract tests in `tests/test_public_repository.py`:

```python
def test_bilingual_feature_lists_present_automatic_and_manual_sync() -> None:
    english = _read("README.md")
    chinese = _read("README.zh-CN.md")
    english_features = english.split("## Features\n", 1)[1].split("\n## ", 1)[0]
    chinese_features = chinese.split("## 功能\n", 1)[1].split("\n## ", 1)[0]

    assert "automatically aligns each eligible candidate to the movie audio with `ffsubsync`" in english_features
    assert "low-quality synchronizations are rejected" in english_features
    assert "manual whole-timeline adjustment with `fixsub adjust --seconds`" in english_features
    assert "通过 `ffsubsync` 根据电影音频自动校准每个合格的候选字幕" in chinese_features
    assert "低质量同步结果会被拒绝" in chinese_features
    assert "使用 `fixsub adjust --seconds` 手动整体提前或延后字幕" in chinese_features

    assert "By default, it attempts audio-based synchronization with `ffsubsync` for each eligible candidate; `--no-sync` explicitly skips this step." in english
    assert "默认情况下，它会通过 `ffsubsync` 根据电影音频校准每个合格的候选字幕；`--no-sync` 会明确跳过这一步。" in chinese
```

- [ ] **Step 2: Run the new test and verify the expected red state**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_public_repository.py::test_bilingual_feature_lists_present_automatic_and_manual_sync -q
```

Expected: FAIL because the current feature lists say only that `ffsubsync` validates timing and do not mention manual adjustment.

- [ ] **Step 3: Replace the ambiguous feature bullets and workflow sentence**

In `README.md`, replace the current `ffprobe` bullet and add the manual-adjustment bullet:

```markdown
- Uses `ffprobe` to select the reference audio stream, then automatically aligns each eligible candidate to the movie audio with `ffsubsync`; low-quality synchronizations are rejected.
- Supports manual whole-timeline adjustment with `fixsub adjust --seconds`, including automatic backup and adjustment metadata.
```

Replace the synchronization part of the English workflow paragraph with these sentences while preserving the existing pipeline order:

```markdown
It rejects non-Chinese candidates. By default, it attempts audio-based synchronization with `ffsubsync` for each eligible candidate; `--no-sync` explicitly skips this step. It ranks the decisions, backs up any previous final subtitle, and writes `<video_stem>.zh.<ext>` when a suitable result is found.
```

In `README.zh-CN.md`, make the equivalent feature changes:

```markdown
- 使用 `ffprobe` 选择参考音轨，然后通过 `ffsubsync` 根据电影音频自动校准每个合格的候选字幕；低质量同步结果会被拒绝。
- 支持使用 `fixsub adjust --seconds` 手动整体提前或延后字幕，并自动备份原字幕、记录调整元数据。
```

Replace the synchronization part of the Chinese workflow paragraph with:

```markdown
随后它会排除非中文字幕候选项。默认情况下，它会通过 `ffsubsync` 根据电影音频校准每个合格的候选字幕；`--no-sync` 会明确跳过这一步。工具会对决策排序、备份之前的最终字幕，并在找到合适结果时写入 `<video_stem>.zh.<ext>`。
```

- [ ] **Step 4: Run the targeted test and bilingual contract tests**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_public_repository.py -q
```

Expected: PASS with no failures.

- [ ] **Step 5: Review and commit Task 1**

Run:

```bash
git diff --check
git diff -- README.md README.zh-CN.md tests/test_public_repository.py
```

Confirm that only feature positioning and its contract test changed, then commit:

```bash
git add README.md README.zh-CN.md tests/test_public_repository.py
git commit -m "docs: clarify subtitle synchronization"
```

---

### Task 2: Add end-user installation, supported formats, and badges

**Files:**
- Modify: `tests/test_public_repository.py`
- Modify: `README.md:1-50`
- Modify: `README.zh-CN.md:1-50`

**Interfaces:**
- Consumes: existing GitHub Actions workflow `ci.yml`, release `v0.1.0`, Python floor `>=3.11`, and implementation format constants.
- Produces: copyable end-user installation, contributor installation, exact format tables, and stable badge links in both READMEs.

- [ ] **Step 1: Add failing installation, format, and badge contracts**

Append these tests to `tests/test_public_repository.py`:

```python
def test_bilingual_readmes_separate_user_install_and_list_supported_formats() -> None:
    english = _read("README.md")
    chinese = _read("README.zh-CN.md")

    for text in (english, chinese):
        for command in (
            "git clone https://github.com/IronJKZ/fixsub.git",
            "python3 -m venv .venv",
            "python3 -m pip install .",
            'python3 -m pip install -e ".[dev]"',
        ):
            assert command in text
        for suffix in (".mkv", ".mp4", ".m4v", ".avi", ".mov", ".srt", ".ass", ".ssa", ".zip", ".rar", ".7z"):
            assert f"`{suffix}`" in text

    assert "## Supported formats" in english
    assert "## 支持的格式" in chinese


def test_bilingual_readmes_show_existing_project_status_badges() -> None:
    english = _read("README.md")
    chinese = _read("README.zh-CN.md")
    badges = (
        "https://github.com/IronJKZ/fixsub/actions/workflows/ci.yml/badge.svg",
        "https://img.shields.io/github/v/release/IronJKZ/fixsub",
        "https://img.shields.io/badge/python-3.11%2B-blue",
        "https://img.shields.io/badge/License-MIT-yellow.svg",
    )

    for badge in badges:
        assert badge in english
        assert badge in chinese
```

- [ ] **Step 2: Run both new tests and verify the expected red state**

Run:

```bash
../../.venv/bin/python -m pytest \
  tests/test_public_repository.py::test_bilingual_readmes_separate_user_install_and_list_supported_formats \
  tests/test_public_repository.py::test_bilingual_readmes_show_existing_project_status_badges -q
```

Expected: both tests FAIL because the clone/user-install commands, grouped format list, and badges are absent.

- [ ] **Step 3: Add the same badges below both README titles**

Add this block below the language-switch link in each README:

```markdown
[![CI](https://github.com/IronJKZ/fixsub/actions/workflows/ci.yml/badge.svg)](https://github.com/IronJKZ/fixsub/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/IronJKZ/fixsub)](https://github.com/IronJKZ/fixsub/releases/latest)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
```

- [ ] **Step 4: Add exact supported-format tables**

Insert this section after Requirements in `README.md`:

```markdown
## Supported formats

| Kind | Formats |
| --- | --- |
| Video | `.mkv`, `.mp4`, `.m4v`, `.avi`, `.mov` |
| Subtitle | `.srt`, `.ass`, `.ssa` |
| Download/archive | Direct subtitle files, `.zip`, `.rar`, `.7z` |

Direct subtitle downloads and `.zip` extraction work without `unar`; `.rar` and `.7z` extraction require `unar`.
```

Insert the equivalent section in `README.zh-CN.md`:

```markdown
## 支持的格式

| 类型 | 格式 |
| --- | --- |
| 视频 | `.mkv`、`.mp4`、`.m4v`、`.avi`、`.mov` |
| 字幕 | `.srt`、`.ass`、`.ssa` |
| 下载/压缩包 | 直接字幕文件、`.zip`、`.rar`、`.7z` |

直接下载的字幕和 `.zip` 解压不需要 `unar`；解压 `.rar` 和 `.7z` 需要 `unar`。
```

- [ ] **Step 5: Replace the developer-only installation with user and contributor paths**

Replace the English Installation section with:

````markdown
## Installation

### End-user installation

Clone the repository and install `fixsub` in a virtual environment:

```bash
git clone https://github.com/IronJKZ/fixsub.git
cd fixsub
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install .
python3 -m pip install ffsubsync
```

The final command installs the `ffs` executable used by the default audio-synchronization workflow. No PyPI package is published, so installation currently starts from a source checkout.

### Contributor installation

For tests and local package builds, use an editable development install:

```bash
python3 -m pip install -e ".[dev]"
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contributor workflow.
````

Replace the Chinese Installation section with:

````markdown
## 安装

### 普通用户安装

克隆仓库，并在虚拟环境中安装 `fixsub`：

```bash
git clone https://github.com/IronJKZ/fixsub.git
cd fixsub
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install .
python3 -m pip install ffsubsync
```

最后一条命令会安装默认音频同步流程使用的 `ffs` 可执行文件。项目尚未发布 PyPI 包，因此当前需要从源码检出目录安装。

### 贡献者安装

如需运行测试和本地构建包，请使用可编辑的开发环境安装：

```bash
python3 -m pip install -e ".[dev]"
```

贡献流程请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。
````

- [ ] **Step 6: Run the targeted and full README contract tests**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_public_repository.py -q
```

Expected: PASS with no failures.

- [ ] **Step 7: Review and commit Task 2**

Run:

```bash
git diff --check
git diff -- README.md README.zh-CN.md tests/test_public_repository.py
```

Confirm that badges point only to existing repository resources, installation does not claim PyPI availability, and all extensions match the implementation. Commit:

```bash
git add README.md README.zh-CN.md tests/test_public_repository.py
git commit -m "docs: improve public setup information"
```

---

### Task 3: Align package metadata with automatic synchronization

**Files:**
- Modify: `tests/test_public_repository.py`
- Modify: `pyproject.toml:5-14`

**Interfaces:**
- Consumes: approved About positioning and existing PEP 621 metadata.
- Produces: source-package metadata that uses the same core capability and discoverability terms as the READMEs.

- [ ] **Step 1: Add the failing metadata contract**

Append this test to `tests/test_public_repository.py`:

```python
def test_package_metadata_positions_automatic_subtitle_sync() -> None:
    project = tomllib.loads(_read("pyproject.toml"))["project"]

    assert project["description"] == "macOS CLI for Chinese subtitle search, automatic audio sync, and Infuse-ready output"
    assert {"subtitle-sync", "subtitle-synchronization", "ffsubsync", "chinese-subtitles"} <= set(project["keywords"])
```

- [ ] **Step 2: Run the new test and verify the expected red state**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_public_repository.py::test_package_metadata_positions_automatic_subtitle_sync -q
```

Expected: FAIL because the old description and keyword list do not satisfy the new contract.

- [ ] **Step 3: Make the minimal PEP 621 metadata change**

Set these values in `pyproject.toml`:

```toml
description = "macOS CLI for Chinese subtitle search, automatic audio sync, and Infuse-ready output"
keywords = [
  "subtitles",
  "subtitle-sync",
  "subtitle-synchronization",
  "ffsubsync",
  "chinese-subtitles",
  "macos",
  "ffmpeg",
  "infuse",
]
```

- [ ] **Step 4: Run metadata contracts and build the package**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_public_repository.py -q
../../.venv/bin/python -m build --no-isolation
```

Expected: repository-contract tests PASS; build exits 0 and produces both an sdist and wheel under ignored `dist/`.

- [ ] **Step 5: Review and commit Task 3**

Run:

```bash
git diff --check
git diff -- pyproject.toml tests/test_public_repository.py
```

Confirm no dependency, version, classifier, entry-point, or URL changed. Commit:

```bash
git add pyproject.toml tests/test_public_repository.py
git commit -m "docs: align package metadata"
```

---

### Task 4: Run final local publication gates

**Files:**
- Verify only: all files changed since `origin/main`

**Interfaces:**
- Consumes: completed Tasks 1-3 and their commits.
- Produces: fresh evidence that the branch is safe to push and open as a pull request.

- [ ] **Step 1: Run the complete test suite**

Run:

```bash
../../.venv/bin/python -m pytest -q
```

Expected: PASS with zero failures.

- [ ] **Step 2: Run CLI and package smoke checks**

Run:

```bash
../../.venv/bin/fixsub --help
../../.venv/bin/fixsub adjust --help
../../.venv/bin/python -m build --no-isolation
```

Expected: both help commands exit 0; build produces an sdist and wheel.

- [ ] **Step 3: Run formatting, privacy, and secret checks**

Run:

```bash
git diff --check origin/main...HEAD
../../.venv/bin/python -m pytest tests/test_public_repository.py::test_tracked_text_contains_no_personal_absolute_paths -q
gitleaks dir . --redact --no-banner --exit-code 1
```

Expected: no whitespace errors, path test PASS, and Gitleaks exits 0 with zero findings.

- [ ] **Step 4: Review exact scope and worktree state**

Run:

```bash
git status --short --branch
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
git diff origin/main...HEAD -- README.md README.zh-CN.md pyproject.toml tests/test_public_repository.py docs/superpowers/specs/2026-07-18-github-feature-positioning-design.md docs/superpowers/plans/2026-07-18-github-information-polish.md
```

Expected: clean worktree; only the two approved design/plan documents, bilingual READMEs, `pyproject.toml`, and `tests/test_public_repository.py` differ from `origin/main`; no file under `fixsub/` changed.

---

### Task 5: Push and open the protected-branch pull request

**Files:**
- Create temporarily: `/tmp/fixsub-github-info-pr.md`
- Remote create: draft pull request from `codex/github-info-polish` to `main`

**Interfaces:**
- Consumes: clean verified branch from Task 4 and authenticated GitHub CLI session for `IronJKZ`.
- Produces: reviewable draft PR with required Python 3.11/3.14 checks.

- [ ] **Step 1: Verify GitHub identity and repository target**

Run:

```bash
gh auth status -h github.com
gh repo view IronJKZ/fixsub --json nameWithOwner,defaultBranchRef,visibility
```

Expected: authenticated account is `IronJKZ`; repository is PUBLIC; default branch is `main`. Stop without pushing if any value differs.

- [ ] **Step 2: Push the explicit branch**

Run:

```bash
git push -u origin codex/github-info-polish
```

Expected: the remote branch is created and local tracking is configured.

- [ ] **Step 3: Create the exact PR body**

Create `/tmp/fixsub-github-info-pr.md` with:

```markdown
## What changed

- presents automatic audio-based subtitle synchronization and manual adjustment in both feature lists
- separates end-user and contributor installation
- lists supported video, subtitle, and archive formats
- adds CI, Release, Python, and MIT badges
- aligns package description and keywords with the public positioning

## Why

The implementation already synchronizes subtitle candidates with `ffsubsync`, rejects low-quality results, and supports manual whole-timeline adjustment, but the most visible repository information understated those capabilities.

## Impact

Documentation, package metadata, and repository-contract tests only. No runtime behavior, version, release, dependency, CI, or security-setting change.

## Validation

- complete pytest suite
- CLI and `adjust` help smoke tests
- sdist and wheel build
- tracked-path and Gitleaks checks
- `git diff --check`
```

- [ ] **Step 4: Open the draft pull request**

Run:

```bash
gh pr create --draft --repo IronJKZ/fixsub --base main --head codex/github-info-polish --title "docs: clarify subtitle synchronization" --body-file /tmp/fixsub-github-info-pr.md
```

Expected: one draft PR URL targeting `main`.

- [ ] **Step 5: Wait for required CI without merging**

Run:

```bash
gh pr checks --repo IronJKZ/fixsub --watch
```

Expected: `tests (Python 3.11)` and `tests (Python 3.14)` both succeed. Keep the PR draft and do not merge or change GitHub About/topics in this task.

---

### Task 6: Update GitHub metadata only after merge approval

**Files:**
- Remote modify after merge: repository About description and topics

**Interfaces:**
- Consumes: an explicitly approved and merged content PR whose merge commit is on `main`.
- Produces: GitHub repository metadata consistent with the default-branch README and package metadata.

- [ ] **Step 1: Obtain explicit merge approval**

Present the draft PR, CI result, and exact diff to the user. Do not mark ready, merge, or edit repository metadata until the user explicitly approves merging.

- [ ] **Step 2: Merge through the protected branch and verify the merged state**

After approval, mark the PR ready and merge it with the repository's permitted squash strategy:

```bash
gh pr ready --repo IronJKZ/fixsub
gh pr merge --repo IronJKZ/fixsub --squash --delete-branch
gh pr view --repo IronJKZ/fixsub --json state,mergeCommit,url
```

Expected: PR state is `MERGED` and `mergeCommit.oid` is non-null.

- [ ] **Step 3: Update the About description and add discovery topics**

Run:

```bash
gh repo edit IronJKZ/fixsub --description "macOS CLI that finds Chinese subtitles, auto-syncs them to movie audio, and writes Infuse-ready files." --add-topic subtitle-sync --add-topic subtitle-synchronization --add-topic ffsubsync --add-topic chinese-subtitles
```

Expected: command exits 0. Existing topics remain because only `--add-topic` is used.

- [ ] **Step 4: Verify default-branch content and remote metadata**

Run:

```bash
gh repo view IronJKZ/fixsub --json description,repositoryTopics,defaultBranchRef,latestRelease
gh api repos/IronJKZ/fixsub/readme -H "Accept: application/vnd.github.raw+json"
gh run list --repo IronJKZ/fixsub --branch main --limit 1 --json status,conclusion,headSha,url
```

Expected:

- Description exactly matches the approved About text.
- Topics include all six original topics plus the four new synchronization topics.
- Default-branch README includes automatic synchronization, manual adjustment, installation, formats, and badges.
- Latest Release remains `v0.1.0` and unchanged.
- The latest `main` CI run is completed successfully.

- [ ] **Step 5: Confirm protected and security state remained unchanged**

Run:

```bash
gh api repos/IronJKZ/fixsub/branches/main/protection
gh api repos/IronJKZ/fixsub/private-vulnerability-reporting
```

Expected: strict Python 3.11/3.14 checks, admin enforcement, linear history, conversation resolution, force-push/deletion protection, and private vulnerability reporting remain enabled.
