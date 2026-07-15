# Secure GitHub Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the existing `fixsub` history as a secure, professional public repository at `https://github.com/IronJKZ/fixsub`, then create a verified `v0.1.0` GitHub Release.

**Architecture:** Prepare and verify all public-facing files locally before creating any remote. Rewrite the unpublished Git identity metadata to the account's ID-based GitHub noreply address, exercise repository contracts with pytest, scan the working tree and full history, then create and harden the GitHub repository. Treat the initial push, remote CI, clean-clone test, branch protection, and release as separate gates so no release is created from an unverified state.

**Tech Stack:** Python 3.11/3.14, setuptools 77+, pytest, Typer, Git, GitHub CLI, GitHub Actions, Dependabot, Gitleaks, git-filter-repo, uv for isolated local verification.

## Global Constraints

- The repository must be public at `IronJKZ/fixsub` and licensed under MIT with `IronJKZ` as the public copyright holder.
- Preserve existing Git history only after rewriting private author/committer identity metadata and passing a full-history sensitive-information audit.
- Never print secret values while scanning; all Gitleaks invocations use 100% redaction.
- Use an ID-based `ID+IronJKZ@users.noreply.github.com` address for all local author and committer metadata.
- Keep English as the primary README and provide a linked Simplified Chinese README with equivalent commands and behavior.
- Do not publish to PyPI, configure PyPI credentials, or add automated release publishing.
- Do not create the GitHub repository until all local tests, builds, metadata checks, and sensitive-information checks pass.
- Do not create `v0.1.0` until remote CI and a clean-clone test pass.
- Keep the work focused on publication readiness; add no new subtitle product features and perform no unrelated refactoring.
- Apply file edits with `apply_patch`; stage only explicit intended paths.

---

## File Structure

### Files to Create

- `LICENSE`: MIT license text and public copyright holder.
- `README.zh-CN.md`: Simplified Chinese user guide mirroring the English README.
- `CHANGELOG.md`: initial `0.1.0` public release notes.
- `CONTRIBUTING.md`: contributor setup, testing, privacy, and pull request rules.
- `CODE_OF_CONDUCT.md`: Contributor Covenant-based community behavior and private enforcement route.
- `SECURITY.md`: supported-version policy and GitHub private vulnerability reporting route.
- `.github/ISSUE_TEMPLATE/bug_report.yml`: structured bug report with privacy warnings.
- `.github/ISSUE_TEMPLATE/feature_request.yml`: structured feature proposal.
- `.github/ISSUE_TEMPLATE/config.yml`: disable blank issues and route security reports privately.
- `.github/pull_request_template.md`: change, test, compatibility, and privacy checklist.
- `.github/workflows/ci.yml`: least-privilege macOS Python 3.11/3.14 CI.
- `.github/dependabot.yml`: grouped weekly Python and Actions updates.
- `tests/test_public_repository.py`: executable contract for public metadata, docs, templates, and automation.

### Files to Modify

- `.gitignore`: exclude credentials, runtime artifacts, caches, builds, coverage, editors, and macOS metadata.
- `README.md`: replace the current M1-focused text with a complete English user/developer guide.
- `pyproject.toml`: add SPDX license, license files, keywords, classifiers, and public URLs; raise the setuptools floor for PEP 639.
- `setup.py`: reduce duplicated package metadata to a compatibility shim that delegates to `pyproject.toml`.

### Git and Remote State to Modify

- All unpublished commits: rewrite author and committer name/email while preserving messages, trees, and dates.
- Repository-local Git config: set `IronJKZ` and the ID-based noreply email.
- `origin`: create only after local acceptance passes.
- GitHub repository settings: metadata, features, merge policy, security features, and `main` protection.
- Git tag and Release: create `v0.1.0` only after remote acceptance passes.

---

### Task 1: Authenticate Safely and Sanitize Unpublished Git Identity

**Files:**

- Modify: repository-local `.git/config`
- Modify: every unpublished commit's author and committer metadata
- Create outside repository: `/tmp/fixsub-before-identity-rewrite.bundle`

**Interfaces:**

- Consumes: GitHub account `IronJKZ`, current 59+ commit linear history, approved history-rewrite policy.
- Produces: a history with unchanged commit count/content and only the account's ID-based GitHub noreply identity.

- [ ] **Step 1: Verify the expected preconditions without printing identity values**

Run:

```bash
git status -sb
git rev-list --count --all
git rev-list --merges --count --all
git remote -v
git log --all --format='%ae%n%ce' | awk '
  NF { total++; if ($0 ~ /@users\.noreply\.github\.com$/) noreply++; else non_noreply++ }
  END { printf "identity_entries=%d noreply_entries=%d non_noreply_entries=%d\n", total, noreply, non_noreply }
'
```

Expected: clean `main`, zero merge commits, no remote, and at least one non-noreply identity entry. Stop if the worktree is mixed or a remote unexpectedly exists.

- [ ] **Step 2: Re-authenticate GitHub CLI as the intended owner**

Run:

```bash
gh auth status -h github.com
gh auth login -h github.com -p https -w
gh auth status -h github.com
gh api user --jq '{login: .login, id_present: (.id != null)}'
```

Expected: the final output identifies `IronJKZ` and reports `id_present: true` without printing any authentication token. Stop if the authenticated login differs.

- [ ] **Step 3: Install the two local audit/rewrite tools if absent**

Run:

```bash
command -v git-filter-repo
command -v gitleaks
brew install git-filter-repo gitleaks
git-filter-repo --version
gitleaks version
```

Expected: both commands are available. Skip the Homebrew install when both were already present.

- [ ] **Step 4: Create a non-repository recovery bundle and record the commit count**

Run:

```bash
git bundle create /tmp/fixsub-before-identity-rewrite.bundle --all
git bundle verify /tmp/fixsub-before-identity-rewrite.bundle
git rev-list --count --all
```

Expected: bundle verification succeeds. Record the commit count for the post-rewrite comparison; do not add the bundle to the repository.

- [ ] **Step 5: Configure the repository-local ID-based noreply identity**

Run:

```bash
NOREPLY_EMAIL="$(gh api user --jq '"'"'(.id|tostring) + "+" + .login + "@users.noreply.github.com"'"'"')"
test -n "$NOREPLY_EMAIL"
git config user.name "IronJKZ"
git config user.email "$NOREPLY_EMAIL"
git config user.useConfigOnly true
git config --local --get-regexp '^user\.(name|email|useConfigOnly)$' | sed -E 's#(^user\.email ).+#\1[configured ID-based noreply]#'
```

Expected: name and `useConfigOnly` are visible, while the address is redacted in terminal output.

- [ ] **Step 6: Rewrite author and committer identities without changing commit content**

Run:

```bash
NOREPLY_EMAIL="$(git config user.email)"
git filter-repo --force --commit-callback "
commit.author_name = b'IronJKZ'
commit.author_email = b'${NOREPLY_EMAIL}'
commit.committer_name = b'IronJKZ'
commit.committer_email = b'${NOREPLY_EMAIL}'
"
```

Expected: the command rewrites the unpublished history and does not create `refs/original/*`. `git-filter-repo` preserves commit messages, file trees, and original author/committer dates unless explicitly changed.

- [ ] **Step 7: Verify the identity rewrite and content integrity**

Run:

```bash
git status -sb
git rev-list --count --all
git fsck --full
git log --all --format='%ae%n%ce' | awk '
  NF { total++; if ($0 ~ /^[0-9]+\+IronJKZ@users\.noreply\.github\.com$/) valid++; else invalid++ }
  END { printf "identity_entries=%d valid_noreply_entries=%d invalid_entries=%d\n", total, valid, invalid; exit invalid != 0 }
'
.venv/bin/python -m pytest -q
```

Expected: the commit count matches Step 4, `invalid_entries=0`, `git fsck` succeeds, and the existing test suite passes. Keep the recovery bundle until the public remote and release are verified.

---

### Task 2: Add the Public Package and Release Metadata Contract

**Files:**

- Create: `tests/test_public_repository.py`
- Create: `LICENSE`
- Create: `CHANGELOG.md`
- Modify: `.gitignore`
- Modify: `pyproject.toml`
- Modify: `setup.py`

**Interfaces:**

- Consumes: current setuptools-based package, `fixsub` version `0.1.0`, MIT decision.
- Produces: canonical PEP 621/639 metadata and an executable repository contract used by later tasks.

- [ ] **Step 1: Write failing tests for package metadata, license, changelog, and ignored private artifacts**

Create `tests/test_public_repository.py` with:

```python
from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_package_metadata_is_complete() -> None:
    data = tomllib.loads(_read("pyproject.toml"))
    project = data["project"]
    build_requires = data["build-system"]["requires"]

    assert project["name"] == "fixsub"
    assert project["version"] == "0.1.0"
    assert project["requires-python"] == ">=3.11"
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert set(project["urls"]) == {"Homepage", "Repository", "Issues", "Changelog"}
    assert project["urls"]["Repository"] == "https://github.com/IronJKZ/fixsub"
    assert "Programming Language :: Python :: 3.14" in project["classifiers"]
    assert not any(item.startswith("License ::") for item in project["classifiers"])
    assert any(item.startswith("setuptools>=77.0.3") for item in build_requires)
    assert "build>=1.5.1" in project["optional-dependencies"]["dev"]


def test_license_and_changelog_match_initial_release() -> None:
    license_text = _read("LICENSE")
    changelog = _read("CHANGELOG.md")

    assert license_text.startswith("MIT License\n")
    assert "Copyright (c) 2026 IronJKZ" in license_text
    assert "## [0.1.0] - 2026-07-16" in changelog
    assert "GitHub" in changelog
    assert "PyPI" in changelog and "not published" in changelog.lower()


def test_private_and_generated_files_are_ignored() -> None:
    gitignore = _read(".gitignore").splitlines()
    required = {
        ".env",
        ".env.*",
        "!.env.example",
        ".fixsub/",
        ".coverage",
        "htmlcov/",
        "dist/",
        "build/",
        ".pytest_cache/",
        ".ruff_cache/",
        ".idea/",
        ".vscode/",
        ".DS_Store",
    }
    assert required <= set(gitignore)


def test_setup_py_delegates_metadata_to_pyproject() -> None:
    setup_py = _read("setup.py")
    assert setup_py == "from setuptools import setup\n\n\nsetup()\n"
```

- [ ] **Step 2: Run the new tests and verify the expected failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_public_repository.py -q
```

Expected: FAIL because `LICENSE`, `CHANGELOG.md`, and the new metadata do not yet exist.

- [ ] **Step 3: Expand `.gitignore` with explicit credential and artifact rules**

Replace `.gitignore` with:

```gitignore
# Credentials and local configuration
.env
.env.*
!.env.example

# fixsub runtime data (may contain local paths or provider responses)
.fixsub/

# Python environments and caches
.venv/
venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
.coverage.*
htmlcov/

# Packaging output
build/
dist/
*.egg-info/

# Editors and operating systems
.idea/
.vscode/
.DS_Store

# Local worktrees
.worktrees/
```

- [ ] **Step 4: Create the MIT license and initial changelog**

Create `LICENSE` using the unmodified standard MIT terms, beginning with:

```text
MIT License

Copyright (c) 2026 IronJKZ
```

The remainder must be the standard MIT permission grant, notice-retention requirement, and warranty/liability disclaimer.

Create `CHANGELOG.md` with this complete structure and release content:

```markdown
# Changelog

All notable changes to this project are documented in this file. This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-16

### Added

- macOS-first CLI for detecting a movie, searching ASSRT and SubHD, downloading and extracting subtitle candidates, normalizing encodings, validating audio alignment, optionally synchronizing with `ffsubsync`, and writing an Infuse-compatible Chinese subtitle.
- Secure ASSRT token storage through macOS Keychain with temporary `ASSRT_TOKEN` environment-variable support.
- Dry-run, provider selection, audio stream selection, candidate limits, language tags, debugging, and manual subtitle timing adjustment.
- Backup and metadata handling under `.fixsub/` with token redaction in logs.
- Bilingual documentation, community health files, macOS CI, and dependency maintenance for the initial public GitHub release.

### Distribution

Version 0.1.0 is released on GitHub. It is not published to PyPI.

[Unreleased]: https://github.com/IronJKZ/fixsub/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/IronJKZ/fixsub/releases/tag/v0.1.0
```

- [ ] **Step 5: Make `pyproject.toml` the canonical metadata source**

Use these exact additions/changes while preserving dependencies and the CLI entry point:

```toml
[build-system]
requires = ["setuptools>=77.0.3", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "fixsub"
version = "0.1.0"
description = "On-demand Chinese subtitle search, validation, and sync CLI"
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
license-files = ["LICENSE"]
keywords = ["subtitles", "subtitle-sync", "macos", "ffmpeg", "infuse"]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Environment :: Console",
  "Intended Audience :: End Users/Desktop",
  "Operating System :: MacOS",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Programming Language :: Python :: 3.14",
  "Topic :: Multimedia :: Video",
  "Topic :: Utilities",
]
```

Add after `[project.scripts]`:

```toml
[project.urls]
Homepage = "https://github.com/IronJKZ/fixsub"
Repository = "https://github.com/IronJKZ/fixsub"
Issues = "https://github.com/IronJKZ/fixsub/issues"
Changelog = "https://github.com/IronJKZ/fixsub/blob/main/CHANGELOG.md"
```

Keep pytest and add the current Python Packaging Authority build frontend to the development extra:

```toml
[project.optional-dependencies]
dev = [
  "pytest>=8.0.0",
  "build>=1.5.1",
]
```

Do not add an author email or a deprecated `License ::` classifier.

- [ ] **Step 6: Replace duplicated `setup.py` metadata with a compatibility shim**

Replace `setup.py` with:

```python
from setuptools import setup


setup()
```

- [ ] **Step 7: Run the focused contract test and full regression suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_public_repository.py -q
.venv/bin/python -m pytest -q
```

Expected: the focused contract and the entire existing suite pass.

- [ ] **Step 8: Commit the package metadata unit**

Run:

```bash
git add .gitignore LICENSE CHANGELOG.md pyproject.toml setup.py tests/test_public_repository.py
git diff --cached --check
git commit -m "chore: prepare public package metadata"
```

Expected: one focused commit using the configured GitHub noreply identity.

---

### Task 3: Publish Complete Bilingual User Documentation

**Files:**

- Modify: `README.md`
- Create: `README.zh-CN.md`
- Modify: `tests/test_public_repository.py`

**Interfaces:**

- Consumes: actual CLI commands and behavior already implemented in `fixsub/cli.py`.
- Produces: equivalent English and Simplified Chinese installation, usage, privacy, troubleshooting, and development guides.

- [ ] **Step 1: Add failing README contract tests**

Append to `tests/test_public_repository.py`:

```python
def test_bilingual_readmes_cover_usage_security_and_development() -> None:
    english = _read("README.md")
    chinese = _read("README.zh-CN.md")

    assert "[简体中文](README.zh-CN.md)" in english
    assert "[English](README.md)" in chinese
    for heading in (
        "## Features",
        "## Requirements",
        "## Installation",
        "## Authentication",
        "## Usage",
        "## Output and backups",
        "## Privacy and security",
        "## Troubleshooting",
        "## Development",
        "## Current limitations",
    ):
        assert heading in english
    for heading in (
        "## 功能",
        "## 系统要求",
        "## 安装",
        "## 身份验证",
        "## 使用方式",
        "## 输出与备份",
        "## 隐私与安全",
        "## 故障排查",
        "## 开发",
        "## 当前限制",
    ):
        assert heading in chinese
    for command in (
        "fixsub auth set",
        "fixsub --dry-run",
        "fixsub --providers subhd",
        "fixsub --providers assrt,subhd",
        "fixsub --audio a:0",
        "fixsub --no-sync",
        "fixsub adjust --seconds 1.0",
        "fixsub --debug",
    ):
        assert command in english
        assert command in chinese
    for warning in ("ASSRT_TOKEN", ".fixsub/logs/fixsub.log", ".fixsub/metadata/results.json"):
        assert warning in english
        assert warning in chinese
    assert "/Users/" not in english + chinese
```

- [ ] **Step 2: Run the README test and verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_public_repository.py::test_bilingual_readmes_cover_usage_security_and_development -q
```

Expected: FAIL because the Chinese README and the expanded English sections do not exist.

- [ ] **Step 3: Rewrite the English README with the approved information architecture**

Use this exact section order in `README.md`:

```markdown
# fixsub

[简体中文](README.zh-CN.md)

`fixsub` is a macOS-first command-line tool that finds, validates, synchronizes, and applies Chinese subtitles for a movie stored in a local folder.

> Status: `0.1.0` is an early public release. Use `--dry-run` first with valuable media libraries.

## Features
## How it works
## Requirements
## Installation
## Authentication
## Usage
### Safe preview
### Provider selection
### Audio and synchronization
### Candidate and language controls
### Manual timing adjustment
### Diagnostics
## Output and backups
## Privacy and security
## Troubleshooting
## Development
## Current limitations
## Contributing and security
## License
```

Fill those sections with the existing verified behavior, using these requirements:

- Explain the folder workflow: detect one movie, query enabled providers, download/extract candidates, normalize UTF-8, probe audio, validate/sync, rank, back up, and write `<video_stem>.zh.<ext>`.
- List macOS, Python 3.11+, `brew install ffmpeg unar`, and optional `python3 -m pip install ffsubsync`.
- Keep editable installation as `python3 -m pip install -e ".[dev]"` because no PyPI package is published.
- Explain `fixsub auth set`, `fixsub auth status`, and `fixsub auth delete`; state that macOS Keychain is preferred and a temporary `ASSRT_TOKEN` overrides it.
- Include every command asserted by the test, with a one-paragraph explanation of behavior and risk.
- Explain `.fixsub/downloads/`, `candidates/`, `synced/`, `original/`, `logs/fixsub.log`, and `metadata/results.json`.
- Warn that logs and metadata can contain movie filenames and local paths; tell users to remove those and all tokens before opening an issue.
- Troubleshoot missing `ffprobe`, missing archive support, absent ASSRT credentials, provider outages, rejected low-confidence candidates, and failed synchronization.
- Development commands are `.venv/bin/python -m pytest -q` and `python -m build`; link to `CONTRIBUTING.md`.
- State that interactive mode, library scanning, Whisper generation, translation, a Web UI, non-macOS guarantees, PyPI distribution, and automatic perfect dialogue matching are not implemented.
- Link `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, and `LICENSE` using relative paths.

- [ ] **Step 4: Create the equivalent Simplified Chinese README**

Use this exact section order in `README.zh-CN.md`:

```markdown
# fixsub

[English](README.md)

`fixsub` 是一款优先支持 macOS 的命令行工具，用于为本地电影搜索、验证、同步并应用中文字幕。

> 状态：`0.1.0` 是早期公开版本。对重要媒体库操作前，请先使用 `--dry-run`。

## 功能
## 工作流程
## 系统要求
## 安装
## 身份验证
## 使用方式
### 安全预览
### 字幕源选择
### 音轨与同步
### 候选数量与语言标签
### 手动微调时间轴
### 诊断信息
## 输出与备份
## 隐私与安全
## 故障排查
## 开发
## 当前限制
## 贡献与安全报告
## 许可证
```

Translate every operational statement from the English README without changing commands, option names, paths, provider behavior, safety guidance, or limitations. Do not claim PyPI installation or cross-platform support.

- [ ] **Step 5: Verify both README contracts and all existing tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_public_repository.py -q
.venv/bin/python -m pytest -q
```

Expected: all tests pass and both language guides contain identical command coverage.

- [ ] **Step 6: Commit the bilingual documentation unit**

Run:

```bash
git add README.md README.zh-CN.md tests/test_public_repository.py
git diff --cached --check
git commit -m "docs: add bilingual usage guide"
```

---

### Task 4: Add Community, Contribution, and Private Security Reporting Files

**Files:**

- Create: `CONTRIBUTING.md`
- Create: `CODE_OF_CONDUCT.md`
- Create: `SECURITY.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/pull_request_template.md`
- Modify: `tests/test_public_repository.py`

**Interfaces:**

- Consumes: public GitHub URLs and privacy rules from the design.
- Produces: GitHub-recognized community health files and structured contribution intake.

- [ ] **Step 1: Add failing tests for community health files and templates**

Append to `tests/test_public_repository.py`:

```python
def test_community_health_files_define_safe_contribution_paths() -> None:
    contributing = _read("CONTRIBUTING.md")
    conduct = _read("CODE_OF_CONDUCT.md")
    security = _read("SECURITY.md")
    pull_request = _read(".github/pull_request_template.md")

    assert "## Development setup" in contributing
    assert ".venv/bin/python -m pytest -q" in contributing
    assert "Do not include" in contributing and "token" in contributing.lower()
    assert "Contributor Covenant" in conduct
    assert "security/advisories/new" in conduct
    assert "## Supported versions" in security
    assert "security/advisories/new" in security
    assert "Do not open a public issue" in security
    assert "Security and privacy" in pull_request
    assert "Tests" in pull_request


def test_issue_forms_are_structured_and_warn_about_sensitive_data() -> None:
    bug = _read(".github/ISSUE_TEMPLATE/bug_report.yml")
    feature = _read(".github/ISSUE_TEMPLATE/feature_request.yml")
    config = _read(".github/ISSUE_TEMPLATE/config.yml")

    assert "name: Bug report" in bug
    assert "type: textarea" in bug
    assert "ASSRT token" in bug
    assert "movie filenames" in bug
    assert "name: Feature request" in feature
    assert "alternatives" in feature.lower()
    assert "blank_issues_enabled: false" in config
    assert "security/advisories/new" in config
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_public_repository.py -q
```

Expected: FAIL on missing community and template files.

- [ ] **Step 3: Create contributor, conduct, and security policies**

`CONTRIBUTING.md` must contain these exact sections:

```markdown
# Contributing to fixsub
## Before you start
## Development setup
## Making a focused change
## Tests and local validation
## Security and private data
## Pull requests
```

Specify Python 3.11+, `python3 -m pip install -e ".[dev]"`, `.venv/bin/python -m pytest -q`, `fixsub --help`, and `python -m build`. Require focused commits and tests for behavior changes. State: “Do not include ASSRT tokens, credentials, private movie filenames, personal absolute paths, or unsanitized `.fixsub/` logs and metadata.” Direct vulnerabilities to `SECURITY.md` instead of issues.

`CODE_OF_CONDUCT.md` must use the Contributor Covenant 2.1 behavior, scope, enforcement, and attribution text. Replace a private maintainer email with this private contact route:

```markdown
Instances of abusive, harassing, or otherwise unacceptable behavior may be reported privately through [GitHub private reporting](https://github.com/IronJKZ/fixsub/security/advisories/new). Prefix the report title with `[Conduct]`. Do not include credentials or unrelated personal data.
```

`SECURITY.md` must contain:

```markdown
# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| Earlier versions | No |

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use [GitHub private vulnerability reporting](https://github.com/IronJKZ/fixsub/security/advisories/new) and include affected versions, reproduction steps, impact, and any suggested mitigation. Do not include live credentials; revoke and rotate any credential that may already be exposed.

The maintainer will acknowledge a complete report when practical, investigate it privately, and coordinate disclosure after a fix or mitigation is available. This policy does not promise a fixed response deadline for an early volunteer-maintained release.
```

- [ ] **Step 4: Create structured GitHub issue forms**

Create `.github/ISSUE_TEMPLATE/bug_report.yml` with valid Issue Form keys `name`, `description`, `title`, `labels`, and `body`. The body must require:

- acknowledgement that the issue is not a private vulnerability;
- fixsub version/commit, macOS version, Python version, install method, enabled providers, and whether `ffsubsync` is installed;
- reproduction steps, expected behavior, actual behavior, and a minimal sanitized log excerpt;
- a checked statement that the report contains no ASSRT token, credential, private movie filenames, personal paths, or unsanitized metadata.

Create `.github/ISSUE_TEMPLATE/feature_request.yml` requiring the user problem, desired outcome, alternatives considered, and scope/compatibility notes.

Create `.github/ISSUE_TEMPLATE/config.yml` with:

```yaml
blank_issues_enabled: false
contact_links:
  - name: Private security report
    url: https://github.com/IronJKZ/fixsub/security/advisories/new
    about: Report suspected vulnerabilities privately. Do not open a public issue.
```

- [ ] **Step 5: Create the pull request template**

Create `.github/pull_request_template.md` with these unchecked sections:

```markdown
## Summary
## Why
## Tests
- [ ] Focused tests pass
- [ ] Full test suite passes
- [ ] `fixsub --help` still works
## Compatibility
- [ ] macOS-first behavior is preserved or the compatibility impact is documented
## Security and privacy
- [ ] No credentials, tokens, private media names, personal paths, or unsanitized runtime artifacts are included
- [ ] User-visible documentation is updated when needed
```

- [ ] **Step 6: Run focused and full tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_public_repository.py -q
.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit the community health unit**

Run:

```bash
git add CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md .github/ISSUE_TEMPLATE .github/pull_request_template.md tests/test_public_repository.py
git diff --cached --check
git commit -m "docs: add open source community guidelines"
```

---

### Task 5: Add Least-Privilege CI and Dependency Maintenance

**Files:**

- Create: `.github/workflows/ci.yml`
- Create: `.github/dependabot.yml`
- Modify: `tests/test_public_repository.py`

**Interfaces:**

- Consumes: `pyproject.toml`, all pytest tests, CLI entry point `fixsub`.
- Produces: two macOS CI checks named `tests (Python 3.11)` and `tests (Python 3.14)`, plus grouped weekly dependency PRs.

- [ ] **Step 1: Add failing automation contract tests**

Append to `tests/test_public_repository.py`:

```python
def test_ci_is_pinned_least_privilege_and_covers_supported_python() -> None:
    workflow = _read(".github/workflows/ci.yml")

    assert "permissions:\n  contents: read" in workflow
    assert "macos-15" in workflow
    assert 'python-version: ["3.11", "3.14"]' in workflow
    assert "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd" in workflow
    assert "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405" in workflow
    assert "python -m pytest -q" in workflow
    assert "fixsub --help" in workflow
    assert "python -m build" in workflow
    assert "ASSRT_TOKEN" not in workflow


def test_dependabot_groups_python_and_actions_updates() -> None:
    dependabot = _read(".github/dependabot.yml")

    assert dependabot.startswith("version: 2\n")
    assert 'package-ecosystem: "pip"' in dependabot
    assert 'package-ecosystem: "github-actions"' in dependabot
    assert dependabot.count('interval: "weekly"') == 2
    assert dependabot.count("groups:") == 2
```

- [ ] **Step 2: Run the automation tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_public_repository.py -q
```

Expected: FAIL because the workflow and Dependabot files do not exist.

- [ ] **Step 3: Create the pinned, least-privilege macOS CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    name: tests (Python ${{ matrix.python-version }})
    runs-on: macos-15
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.14"]
    steps:
      - name: Check out repository
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          persist-credentials: false
      - name: Set up Python
        uses: actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405 # v6.2.0
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - name: Install package and test tooling
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[dev]"
      - name: Run tests
        run: python -m pytest -q
      - name: Run CLI smoke test
        run: fixsub --help
      - name: Build source and wheel distributions
        run: python -m build
      - name: Verify distribution artifacts
        run: |
          test -n "$(find dist -maxdepth 1 -name '*.tar.gz' -print -quit)"
          test -n "$(find dist -maxdepth 1 -name '*.whl' -print -quit)"
```

Do not add repository secrets or artifact uploads.

- [ ] **Step 4: Create grouped weekly Dependabot updates**

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "Asia/Shanghai"
    open-pull-requests-limit: 5
    groups:
      python-dependencies:
        patterns:
          - "*"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "Asia/Shanghai"
    open-pull-requests-limit: 5
    groups:
      github-actions:
        patterns:
          - "*"
```

- [ ] **Step 5: Run contract, regression, CLI, and build checks**

Run:

```bash
.venv/bin/python -m pytest tests/test_public_repository.py -q
.venv/bin/python -m pytest -q
.venv/bin/fixsub --help
UV_CACHE_DIR=/tmp/fixsub-uv-cache uv run --python 3.11 --extra dev python -m build
test -n "$(find dist -maxdepth 1 -name '*.tar.gz' -print -quit)"
test -n "$(find dist -maxdepth 1 -name '*.whl' -print -quit)"
```

Expected: all tests pass, help exits zero, build exits zero, and both distribution types exist. The new `dist/` remains ignored.

- [ ] **Step 6: Commit the automation unit**

Run:

```bash
git add .github/workflows/ci.yml .github/dependabot.yml tests/test_public_repository.py
git diff --cached --check
git commit -m "ci: add test and dependency automation"
```

---

### Task 6: Run the Publication Gate, Create and Harden GitHub, Then Release

**Files:**

- Inspect: all tracked/untracked files and all reachable Git history
- Create outside repository: `/tmp/fixsub-branch-protection.json`
- Create outside repository: a temporary clean clone
- Modify remote: `https://github.com/IronJKZ/fixsub`
- Create remote/local tag: `v0.1.0`

**Interfaces:**

- Consumes: clean, fully documented local `main` with passing tests and noreply-only history.
- Produces: public hardened repository, green CI, verified clean clone, protected `main`, and GitHub Release `v0.1.0`.

- [ ] **Step 1: Invoke the verification-before-completion skill and inspect the exact publication diff**

Run:

```bash
git status -sb
git log -5 --oneline --decorate
git diff HEAD~4..HEAD --stat
git diff --check
git ls-files | sort
```

Expected: only the intended publication commits are present and the worktree is clean. If unrelated files appear, stop and separate them before continuing.

- [ ] **Step 2: Scan the current directory with secret redaction and archive inspection**

Run:

```bash
gitleaks dir --no-banner --redact=100 --max-archive-depth=2 .
```

Expected: exit 0 with no findings. Never rerun without `--redact=100` in shared output.

- [ ] **Step 3: Scan every reachable Git revision**

Run:

```bash
gitleaks git --no-banner --redact=100 --max-archive-depth=2 --log-opts="--all" .
```

Expected: exit 0 with no findings. A real finding triggers credential rotation and another history rewrite before returning to Task 6 Step 2.

- [ ] **Step 4: Check identity, personal paths, tracked binaries, and large files without printing private values**

Run:

```bash
git log --all --format='%ae%n%ce' | awk '
  NF { total++; if ($0 ~ /^[0-9]+\+IronJKZ@users\.noreply\.github\.com$/) valid++; else invalid++ }
  END { printf "identity_entries=%d valid_noreply_entries=%d invalid_entries=%d\n", total, valid, invalid; exit invalid != 0 }
'
git log -p --all -- . | awk '
  /\/Users\/[A-Za-z0-9._-]+\// || /\/home\/[A-Za-z0-9._-]+\// || /[A-Za-z]:\\Users\\/ { findings++ }
  END { printf "personal_path_findings=%d\n", findings; exit findings != 0 }
'
git ls-files -z | xargs -0 file | awk '
  !/text|empty|Python script|JSON data/ { print $1 }
' | sed -E 's/:$//' | sort -u
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '$1 == "blob" && $3 > 5242880 { print "large_blob_bytes=" $3 " path=" $4; found=1 } END { exit found }'
```

Expected: `invalid_entries=0`, `personal_path_findings=0`, no unexpected binary path, and no Git blob over 5 MiB. Standard repository text, JSON fixtures, and Python files are allowed; any other output is reviewed before proceeding.

- [ ] **Step 5: Run fresh local acceptance checks**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/fixsub --help
UV_CACHE_DIR=/tmp/fixsub-uv-cache uv run --python 3.11 --extra dev python -m build
git diff --check
git status -sb
```

Expected: zero test failures, CLI exit 0, build exit 0, no whitespace errors, and clean `main`.

- [ ] **Step 6: Confirm authentication and repository-name availability**

Run:

```bash
gh auth status -h github.com
gh api user --jq '.login'
gh repo view IronJKZ/fixsub
```

Expected: authenticated as `IronJKZ`; `gh repo view` reports that `IronJKZ/fixsub` does not exist. If it exists, stop without modifying it and ask for conflict resolution.

- [ ] **Step 7: Create the empty public GitHub repository and add `origin`**

Run:

```bash
gh repo create IronJKZ/fixsub \
  --public \
  --source=. \
  --remote=origin \
  --disable-wiki \
  --description="macOS-first CLI for Chinese subtitle search, validation, sync, and application"
git remote -v
```

Expected: the repository exists publicly, contains no disconnected auto-generated commit, and `origin` points to `https://github.com/IronJKZ/fixsub.git` or the authenticated equivalent.

- [ ] **Step 8: Push the audited `main` history**

Run:

```bash
git push -u origin main
git status -sb
```

Expected: push succeeds without bypassing secret protection and the local branch tracks `origin/main`.

- [ ] **Step 9: Apply repository metadata, features, merge settings, and security features**

Run:

```bash
gh repo edit IronJKZ/fixsub \
  --enable-issues=true \
  --enable-wiki=false \
  --enable-projects=false \
  --enable-discussions=false \
  --enable-squash-merge=true \
  --enable-merge-commit=false \
  --enable-rebase-merge=false \
  --delete-branch-on-merge=true \
  --allow-update-branch=true \
  --add-topic python,macos,cli,subtitles,ffmpeg,infuse
gh repo edit IronJKZ/fixsub --enable-secret-scanning --enable-secret-scanning-push-protection
gh api --method PUT repos/IronJKZ/fixsub/vulnerability-alerts --silent
gh api --method PUT repos/IronJKZ/fixsub/automated-security-fixes --silent
gh api --method PUT repos/IronJKZ/fixsub/private-vulnerability-reporting --silent
```

Expected: every command exits zero. Do not silently ignore a feature unavailable to this account; report the exact setting and resolve it before claiming full configuration.

- [ ] **Step 10: Wait for the initial remote CI and record the exact check names**

Run:

```bash
gh run list --repo IronJKZ/fixsub --workflow ci.yml --branch main --limit 1 --json databaseId,status,conclusion,url
RUN_ID="$(gh run list --repo IronJKZ/fixsub --workflow ci.yml --branch main --limit 1 --json databaseId --jq '.[0].databaseId')"
test -n "$RUN_ID"
gh run watch "$RUN_ID" --repo IronJKZ/fixsub --exit-status
gh api repos/IronJKZ/fixsub/commits/main/check-runs --jq '.check_runs[] | {name, conclusion}'
```

Expected: `tests (Python 3.11)` and `tests (Python 3.14)` both conclude `success`.

- [ ] **Step 11: Create and apply the `main` branch protection payload**

Create `/tmp/fixsub-branch-protection.json` with `apply_patch`:

```json
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "tests (Python 3.11)",
      "tests (Python 3.14)"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": true
}
```

Apply and verify:

```bash
gh api --method PUT repos/IronJKZ/fixsub/branches/main/protection --input /tmp/fixsub-branch-protection.json --silent
gh api repos/IronJKZ/fixsub/branches/main/protection --jq '{enforce_admins: .enforce_admins.enabled, required_checks: .required_status_checks.contexts, force_pushes: .allow_force_pushes.enabled, deletions: .allow_deletions.enabled}'
```

Expected: admin enforcement is true, both CI checks are required, and force pushes/deletions are false.

- [ ] **Step 12: Perform a clean-clone installation and test**

Run:

```bash
CLONE_ROOT="$(mktemp -d /tmp/fixsub-public-clone.XXXXXX)"
git clone https://github.com/IronJKZ/fixsub.git "$CLONE_ROOT/fixsub"
cd "$CLONE_ROOT/fixsub"
UV_CACHE_DIR=/tmp/fixsub-uv-cache uv run --python 3.11 --extra dev pytest -q
UV_CACHE_DIR=/tmp/fixsub-uv-cache uv run --python 3.11 --extra dev fixsub --help
```

Expected: fresh clone succeeds, all tests pass, and CLI help exits zero without an ASSRT token.

- [ ] **Step 13: Create the annotated tag and initial GitHub Release**

Return to the original repository, then run:

```bash
git tag -a v0.1.0 -m "fixsub v0.1.0"
git push origin v0.1.0
gh release create v0.1.0 \
  --repo IronJKZ/fixsub \
  --verify-tag \
  --title "fixsub v0.1.0" \
  --notes-file CHANGELOG.md
```

Expected: the annotated tag points to the verified `main` commit and the release is published as the latest release. Do not run this step if any earlier check failed.

- [ ] **Step 14: Run final remote verification before claiming completion**

Run:

```bash
gh repo view IronJKZ/fixsub --json nameWithOwner,url,visibility,defaultBranchRef,description,repositoryTopics,hasIssuesEnabled,hasWikiEnabled,hasProjectsEnabled
gh api repos/IronJKZ/fixsub/community/profile --jq '{health_percentage, files: (.files | keys)}'
gh api repos/IronJKZ/fixsub/private-vulnerability-reporting --silent
gh api repos/IronJKZ/fixsub/branches/main/protection --silent
gh release view v0.1.0 --repo IronJKZ/fixsub --json name,tagName,url,isDraft,isPrerelease
git status -sb
git remote -v
```

Expected: public visibility, default branch `main`, correct metadata/topics, Issues on, Wiki/Projects off, recognized community files, private reporting and protection endpoints available, a non-draft/non-prerelease `v0.1.0`, and a clean local branch tracking `origin/main`.

- [ ] **Step 15: Remove the temporary identity-rewrite recovery bundle only after all acceptance criteria pass**

Run only after Step 14 succeeds:

```bash
rm /tmp/fixsub-before-identity-rewrite.bundle
```

Expected: the unpublished private-identity backup is no longer retained on disk. Do not remove it earlier.

---

## Plan Self-Review Checklist

- Every approved design requirement maps to a task above: public docs (Tasks 2–4), security/history (Tasks 1 and 6), CI/dependencies (Task 5), repository settings/release (Task 6).
- The only public remote target is `IronJKZ/fixsub`; no PyPI command or credential exists.
- Every implementation task has a focused failing test or an explicit failing precondition, a verification step, and a scoped commit or externally verifiable result.
- GitHub Actions are pinned to the full SHAs for `actions/checkout` v6.0.2 and `actions/setup-python` v6.2.0.
- Python packaging uses PEP 639 fields supported by `setuptools>=77.0.3` and omits deprecated license classifiers.
- The history rewrite precedes all implementation commits, and later gates verify that every author and committer address uses the ID-based noreply form.
- No step instructs the worker to print a token or unredacted Gitleaks finding.
- Remote creation, push, settings, CI, branch protection, clean clone, tag, and release are separate stop/go gates.

## Reference Basis

- [Approved GitHub publication design](../specs/2026-07-16-github-publication-design.md)
- [GitHub commit email configuration](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address)
- [Python packaging license and license-files guidance](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#license-and-license-files)
- [GitHub branch protection REST API](https://docs.github.com/en/rest/branches/branch-protection?apiVersion=2026-03-10)
- [GitHub private vulnerability reporting REST API](https://docs.github.com/en/rest/repos/repos?apiVersion=2026-03-10)
- [Gitleaks Git and directory scanning](https://github.com/gitleaks/gitleaks)
- [actions/checkout v6.0.2](https://github.com/actions/checkout/releases/tag/v6.0.2)
- [actions/setup-python v6.2.0](https://github.com/actions/setup-python/releases/tag/v6.2.0)
