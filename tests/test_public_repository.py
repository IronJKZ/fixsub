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
