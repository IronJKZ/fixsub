# Contributing to fixsub

## Before you start

Thank you for improving fixsub. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) and keep each contribution focused on one clear change. For vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of opening an issue.

## Development setup

fixsub supports Python 3.11 and later. Create and activate a virtual environment, then install the development dependencies:

```bash
python3 -m pip install -e ".[dev]"
```

Confirm the command-line interface is available:

```bash
fixsub --help
```

## Making a focused change

Keep changes small, explain their purpose, and avoid unrelated refactors. Use focused commits that make review and rollback straightforward. Add or update tests for every behavior change.

## Tests and local validation

Run the complete test suite before opening a pull request:

```bash
.venv/bin/python -m pytest -q
```

Build locally when packaging-related files change:

```bash
python -m build
```

Local builds do not publish a package.

## Security and private data

Do not include ASSRT tokens, credentials, private movie filenames, personal absolute paths, or unsanitized `.fixsub/` logs and metadata. Remove or replace sensitive values in test fixtures, issue reports, pull requests, and logs. Report suspected vulnerabilities through [SECURITY.md](SECURITY.md), not through public issues.

## Pull requests

Describe the problem and change, include the tests you ran, and note compatibility effects. Keep the pull request limited to its stated purpose, update user-facing documentation when needed, and use the pull request template as a final privacy check.
