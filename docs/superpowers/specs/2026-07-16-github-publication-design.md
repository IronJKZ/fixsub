# GitHub Public Repository Design

**Date:** 2026-07-16

**Repository:** `IronJKZ/fixsub`

**Visibility:** Public

**License:** MIT

**Initial release:** `v0.1.0`

## Purpose

Publish the existing `fixsub` project as a professional, secure, and maintainable public GitHub repository. A new user should be able to understand the tool, install it on macOS, configure ASSRT access without exposing credentials, and run the CLI successfully. A contributor should be able to report an issue, propose a change, and validate it without needing private project context.

## Approved Decisions

- Create the public repository at `https://github.com/IronJKZ/fixsub`.
- Preserve the existing Git history only after it passes a full-history sensitive-information audit.
- Rewrite unpublished history if it contains private author email addresses, credentials, personal paths, or other sensitive information that should not become public.
- Use the MIT License with `IronJKZ` as the public copyright holder.
- Use English as the primary README language and provide a linked Simplified Chinese README.
- Publish to GitHub only. Do not publish to PyPI or add automated PyPI release credentials.
- Create the initial `v0.1.0` GitHub Release only after the remote CI and repository checks pass.

## Scope

### In Scope

- Bilingual user and developer documentation.
- Standard open-source community and security files.
- GitHub issue forms and a pull request template.
- Repository metadata and Python package metadata suitable for a public project.
- A least-privilege GitHub Actions CI workflow.
- Dependabot configuration for Python and GitHub Actions dependencies.
- Working-tree and full-history sensitive-information auditing.
- Public repository creation, initial push, security settings, branch protection, and a `v0.1.0` GitHub Release.
- Local and remote verification, including a clean-clone check.

### Out of Scope

- PyPI publication or PyPI trusted publishing.
- Automated release workflows.
- Wiki, GitHub Projects, Discussions, or sponsorship configuration.
- New `fixsub` product features or unrelated refactoring.
- Promising support for platforms beyond the project's current macOS-first scope.

## Public Documentation

### English README

`README.md` remains the GitHub landing page and contains:

1. A concise description of the problem `fixsub` solves.
2. A language link to `README.zh-CN.md`.
3. Core features and an explicit list of current limitations.
4. Requirements: macOS, Python 3.11 or newer, FFmpeg, archive extraction support, and optional `ffsubsync` support.
5. Installation instructions for end users and contributors.
6. Secure ASSRT authentication using macOS Keychain, with environment-variable use limited to temporary shells and automation.
7. Copyable usage examples for the main command, dry runs, provider selection, sync controls, language tags, debugging, and subtitle adjustment.
8. Output paths, backup behavior, and runtime artifact locations.
9. Troubleshooting guidance for provider, archive, media-probe, and synchronization failures.
10. Privacy guidance explaining that logs and metadata can contain local movie filenames or paths and must be sanitized before sharing.
11. Development, testing, contribution, security, changelog, and license links.

All credential examples use unmistakable placeholders. No real token, personal email address, or local absolute path appears in documentation.

### Chinese README

`README.zh-CN.md` mirrors the English README's structure and operational content in Simplified Chinese. It links back to `README.md` at the top. Commands, environment variable names, file paths, and behavior remain identical across both languages.

### Community and Release Files

- `LICENSE`: MIT License with the 2026 copyright holder `IronJKZ`.
- `CHANGELOG.md`: a Keep a Changelog-style `0.1.0` entry describing the initial public feature set without claiming unsupported features.
- `CONTRIBUTING.md`: environment setup, focused-change expectations, test commands, security precautions, and the pull request process.
- `CODE_OF_CONDUCT.md`: a standard contributor covenant with a GitHub-based enforcement contact that does not disclose a private email address.
- `SECURITY.md`: supported-version policy, private vulnerability reporting through GitHub Security Advisories, and instructions not to open public vulnerability issues.
- `.github/ISSUE_TEMPLATE/bug_report.yml`: structured reproduction details, macOS/Python versions, sanitized logs, and an explicit credential/privacy warning.
- `.github/ISSUE_TEMPLATE/feature_request.yml`: problem, proposed outcome, alternatives, and scope.
- `.github/ISSUE_TEMPLATE/config.yml`: disables unstructured blank issues while directing security reports to the private reporting route.
- `.github/pull_request_template.md`: change summary, motivation, validation, compatibility, and security/privacy checklist.

GitHub's community profile recognizes README, license, contribution guidelines, code of conduct, security policy, and valid issue templates in these supported locations.

## Package and Repository Metadata

Update `pyproject.toml` without introducing private identity data:

- Declare the MIT license using current packaging metadata supported by the existing build backend.
- Add public project URLs for repository, issues, changelog, and documentation.
- Add accurate classifiers and keywords for Python, macOS, CLI tools, and subtitles.
- Keep `requires-python = ">=3.11"` and the current package version `0.1.0`.
- Do not add an author email address.

Repository metadata will use:

- Description: a concise macOS-first Chinese subtitle search, validation, sync, and application CLI description.
- Topics: `python`, `macos`, `cli`, `subtitles`, `ffmpeg`, and `infuse`.
- Issues enabled.
- Wiki, Projects, and Discussions disabled for the initial public release.
- Squash merging enabled and merged branches automatically deleted where applicable.

## Sensitive-Information Gate

No public repository is created and no commit is pushed until every pre-publication check passes.

### Audit Coverage

The audit covers:

- Untracked and ignored filenames that commonly contain credentials or runtime data.
- Every tracked file in the current tree.
- Every reachable Git revision, not only the current checkout.
- High-confidence token, password, private-key, credential-pair, and connection-string patterns.
- `.env` files, credential exports, runtime logs, and `.fixsub/` artifacts.
- Personal absolute paths, local usernames, private email addresses, and Git author/committer identities.
- Unexpected large or binary files that could contain media, archives, or embedded metadata.

The scan reports locations and classifications without printing secret values into terminal output, documentation, commits, issues, or chat.

### Remediation

If a real secret is found:

1. Stop the publication flow.
2. Revoke and rotate the credential at its provider.
3. Remove it from the current tree and rewrite every affected unpublished revision.
4. Re-run the complete audit from the beginning.
5. Continue only after the replacement credential remains outside the repository.

Deleting a secret only from the latest revision is not sufficient. A suspected false positive must be reviewed and documented locally before publication; GitHub push-protection bypass is not the default response.

If unpublished commits contain a private author email address, rewrite author and committer metadata to the verified GitHub noreply identity before the first public push, then re-run the history audit.

### Prevention

Expand `.gitignore` to cover:

- `.env` and local environment variants while permitting an intentionally sanitized `.env.example` if one is ever added.
- `.fixsub/` runtime downloads, candidates, synchronized files, logs, and metadata.
- Python caches, virtual environments, test caches, coverage files, build artifacts, and package metadata.
- macOS filesystem metadata and editor-local files.

The application continues to prefer macOS Keychain for `ASSRT_TOKEN`. CI receives no ASSRT token and all provider behavior in CI uses the existing isolated tests.

## Continuous Integration

Create `.github/workflows/ci.yml` with these properties:

- Trigger on pushes to `main` and pull requests targeting `main`.
- Use macOS runners because the product is macOS-first.
- Cover Python 3.11, the declared minimum, and Python 3.14, the latest stable feature series at publication time.
- Install the package and development dependencies from the repository.
- Run the complete pytest suite.
- Run the CLI smoke check.
- Build both source and wheel artifacts and validate that the expected files are present.
- Use explicit workflow-level `permissions: contents: read`.
- Persist no credentials and upload no logs or artifacts containing user paths or runtime media metadata.
- Pin third-party Actions to full commit SHAs and annotate their corresponding release versions.

Create `.github/dependabot.yml` with weekly, grouped updates for:

- Python dependencies in the repository root.
- GitHub Actions used by workflows.

Dependabot pull requests must pass the same CI checks and are never auto-merged by this design.

## Repository Security and Branch Policy

After the initial `main` push:

- Confirm GitHub secret scanning is active for the public repository.
- Enable private vulnerability reporting.
- Enable Dependabot alerts and Dependabot security updates.
- Protect `main` from force pushes and deletion.
- Require the CI status check for future changes to `main`.
- Use pull requests for subsequent changes while keeping the policy practical for a single maintainer.

Repository settings that require an existing default branch are applied only after the initial push. A settings failure does not cause the release to proceed silently; it is reported and retried or left as an explicit blocker.

## Publication Flow

1. Confirm the local worktree contains only the intended publication-preparation changes.
2. Run the sensitive-information gate against the working tree and full Git history.
3. Run the complete local test suite, CLI smoke check, and package build.
4. Re-authenticate GitHub CLI as `IronJKZ`; the session observed during design was invalid.
5. Verify that `IronJKZ/fixsub` does not already exist, or stop for explicit conflict resolution.
6. Create `IronJKZ/fixsub` as a public repository without auto-generated files.
7. Add the new repository as `origin` and push the audited local `main` with its existing history.
8. Apply repository metadata, merge settings, security features, and branch protection.
9. Wait for the remote CI run and inspect its final result.
10. Perform a clean clone into a temporary directory, install the project, run the smoke check, and run tests.
11. Create and push the annotated `v0.1.0` tag only after all prior checks pass.
12. Create the initial GitHub Release from `CHANGELOG.md`, with installation and known-limitations notes.

The first push establishes the new repository's default branch. The pull-request workflow applies to later changes; the repository is not initialized with a disconnected remote commit solely to manufacture an initial pull request.

## Validation and Acceptance Criteria

### Local Evidence

- The full pytest suite exits successfully with zero failures.
- The installed `fixsub` CLI help command exits successfully.
- Source and wheel builds exit successfully.
- The working-tree and full-history sensitive-information scan reports no unresolved findings.
- A file and history review reports no private author email, personal absolute path, runtime media, archive, or `.fixsub/` artifact.
- README language links and all local Markdown links resolve.
- Git status contains only intentional publication changes before commit and is clean before the initial push.

### Remote Evidence

- `https://github.com/IronJKZ/fixsub` is publicly accessible.
- `main` is the default branch and contains the audited history.
- GitHub recognizes the MIT License and community health files.
- Repository description, topics, feature toggles, merge settings, security features, and branch protection match this design.
- The initial CI workflow completes successfully on every configured Python version.
- A fresh clone installs, exposes the CLI, and passes the test suite.
- The `v0.1.0` tag and GitHub Release point to the verified `main` commit.

## Failure Handling

- **Authentication failure:** stop before repository creation and require a successful `gh auth login` for `IronJKZ`.
- **Repository name conflict:** do not overwrite, rename, delete, or repoint an existing repository without explicit approval.
- **Secret or personal-data finding:** stop, rotate real credentials, rewrite affected unpublished history, and restart the audit.
- **Local test or build failure:** fix the scoped publication issue or report the blocker; do not push a known-broken release.
- **Push failure:** preserve the local commit and diagnose authentication, permissions, or remote configuration without force pushing.
- **Remote CI failure:** inspect and fix the failure before tagging or releasing.
- **Settings failure:** report the exact setting that could not be applied and do not claim the repository is fully configured.
- **Clean-clone failure:** treat it as a release blocker even when local tests passed.

## References

- [GitHub: About community profiles for public repositories](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories)
- [GitHub: Push protection](https://docs.github.com/en/code-security/concepts/secret-security/push-protection)
- [GitHub: Secret scanning detection scope](https://docs.github.com/en/code-security/reference/secret-security/secret-scanning-scope)
- [GitHub: Dependabot version updates](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-version-updates)
- [Python.org: Python 3.14.6](https://www.python.org/downloads/release/python-3146/)
