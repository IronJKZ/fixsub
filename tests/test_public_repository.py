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
