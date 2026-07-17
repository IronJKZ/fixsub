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
