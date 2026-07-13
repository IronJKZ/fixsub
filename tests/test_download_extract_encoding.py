import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from fixsub.download import safe_download_name
from fixsub.encoding import normalize_to_utf8
from fixsub.errors import MissingDependencyError, SubtitleEncodingError
from fixsub.extract import collect_subtitle_files, extract_archive


def test_safe_download_name_keeps_known_extension() -> None:
    assert safe_download_name("assrt_001", "Movie 中文.ass") == "assrt_001.ass"
    assert safe_download_name("assrt_002", "archive.zip") == "assrt_002.zip"


def test_safe_download_name_sanitizes_candidate_id() -> None:
    name = safe_download_name("../../assrt_001", "Movie.ass")

    assert name == "assrt_001.ass"
    assert "/" not in name
    assert ".." not in name


def test_safe_download_name_sanitizes_windows_path_candidate_id() -> None:
    name = safe_download_name(r"C:\tmp\assrt_001", "Movie.ass")

    assert name == "assrt_001.ass"
    assert "\\" not in name
    assert ":" not in name


def test_extract_zip_collects_subtitles_only(tmp_path: Path) -> None:
    archive = tmp_path / "subs.zip"
    out_dir = tmp_path / "out"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("movie.ass", "[Script Info]\n")
        zip_file.writestr("notes.txt", "ignore")

    extracted = extract_archive(archive, out_dir)

    assert extracted == [out_dir / "movie.ass"]


def test_extract_zip_skips_relative_zip_slip_entries(tmp_path: Path) -> None:
    archive = tmp_path / "subs.zip"
    out_dir = tmp_path / "out"
    outside = tmp_path / "evil.srt"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("../../evil.srt", "owned")
        zip_file.writestr("safe.srt", "safe")

    extracted = extract_archive(archive, out_dir)

    assert extracted == [out_dir / "safe.srt"]
    assert not outside.exists()


def test_extract_zip_skips_absolute_zip_slip_entries(tmp_path: Path) -> None:
    archive = tmp_path / "subs.zip"
    out_dir = tmp_path / "out"
    outside = tmp_path / "absolute_evil.srt"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr(str(outside), "owned")
        zip_file.writestr("safe.srt", "safe")

    extracted = extract_archive(archive, out_dir)

    assert extracted == [out_dir / "safe.srt"]
    assert not outside.exists()


def test_extract_archive_returns_only_current_extraction_files(tmp_path: Path) -> None:
    archive = tmp_path / "subs.zip"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "stale.srt").write_text("old", encoding="utf-8")
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("fresh.srt", "new")

    extracted = extract_archive(archive, out_dir)

    assert extracted == [out_dir / "fresh.srt"]


def test_extract_direct_subtitle_uses_collision_safe_name(tmp_path: Path) -> None:
    source = tmp_path / "movie.srt"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    existing = out_dir / "movie.srt"
    source.write_text("new", encoding="utf-8")
    existing.write_text("old", encoding="utf-8")

    extracted = extract_archive(source, out_dir)

    assert extracted == [out_dir / "movie.1.srt"]
    assert existing.read_text(encoding="utf-8") == "old"
    assert (out_dir / "movie.1.srt").read_text(encoding="utf-8") == "new"


def test_extract_7z_requires_unar_when_only_unrar_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "subs.7z"
    archive.write_bytes(b"archive")
    probes: list[str] = []

    def fake_which(command: str) -> str | None:
        probes.append(command)
        if command == "unrar":
            return "/usr/bin/unrar"
        return None

    monkeypatch.setattr("fixsub.extract.shutil.which", fake_which)

    with pytest.raises(MissingDependencyError) as error:
        extract_archive(archive, tmp_path / "out")

    assert error.value.command == "unar"
    assert probes == ["unar"]


def test_extract_rar_may_use_unrar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "subs.rar"
    out_dir = tmp_path / "out"
    archive.write_bytes(b"archive")
    commands: list[list[str]] = []
    probes: list[str] = []

    def fake_which(command: str) -> str | None:
        probes.append(command)
        if command == "unrar":
            return "/usr/bin/unrar"
        return None

    def fake_run(command: list[str], **_: object) -> None:
        commands.append(command)
        extract_dir = Path(command[-1])
        extract_dir.mkdir(parents=True, exist_ok=True)
        (extract_dir / "movie.srt").write_text("subtitle", encoding="utf-8")

    monkeypatch.setattr("fixsub.extract.shutil.which", fake_which)
    monkeypatch.setattr("fixsub.extract.subprocess.run", fake_run)

    extracted = extract_archive(archive, out_dir)

    assert commands[0][:3] == ["/usr/bin/unrar", "x", str(archive)]
    assert probes == ["unar", "unrar"]
    assert extracted == [out_dir / "movie.srt"]


def test_extract_rar_uses_verified_tar_bsdtar_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "subs.rar"
    out_dir = tmp_path / "out"
    archive.write_bytes(b"archive")
    commands: list[list[str]] = []

    def fake_which(command: str) -> str | None:
        if command == "tar":
            return "/usr/bin/tar"
        return None

    def fake_run(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[-1] == "--version":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=b"bsdtar 3.5.3",
                stderr=b"",
            )
        extract_dir = Path(command[command.index("-C") + 1])
        (extract_dir / "movie.srt").write_text("subtitle", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("fixsub.extract.shutil.which", fake_which)
    monkeypatch.setattr("fixsub.extract.subprocess.run", fake_run)

    extracted = extract_archive(archive, out_dir)

    assert commands[0] == ["/usr/bin/tar", "--version"]
    extract_command = commands[1]
    assert extract_command[:3] == ["/usr/bin/tar", "-xf", str(archive)]
    assert extract_command[3] == "-C"
    assert Path(extract_command[4]).parent == out_dir
    assert extracted == [out_dir / "movie.srt"]


def test_extract_rar_recognizes_bsdtar_in_undecodable_probe_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "subs.rar"
    out_dir = tmp_path / "out"
    archive.write_bytes(b"archive")
    commands: list[list[str]] = []

    def fake_which(command: str) -> str | None:
        if command == "tar":
            return "/usr/bin/tar"
        return None

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[-1] == "--version":
            assert kwargs.get("text") is not True
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=b"\xffBSDTAR 3.5.3",
                stderr=b"\xfe",
            )
        extract_dir = Path(command[command.index("-C") + 1])
        (extract_dir / "movie.srt").write_text("subtitle", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("fixsub.extract.shutil.which", fake_which)
    monkeypatch.setattr("fixsub.extract.subprocess.run", fake_run)

    extracted = extract_archive(archive, out_dir)

    assert commands[0] == ["/usr/bin/tar", "--version"]
    assert commands[1][:4] == ["/usr/bin/tar", "-xf", str(archive), "-C"]
    assert Path(commands[1][4]).parent == out_dir
    assert extracted == [out_dir / "movie.srt"]


def test_extract_rar_rejects_non_bsdtar_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "subs.rar"
    archive.write_bytes(b"archive")
    commands: list[list[str]] = []

    def fake_which(command: str) -> str | None:
        if command == "tar":
            return "/usr/bin/tar"
        return None

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=b"tar (GNU tar) 1.35",
            stderr=b"",
        )

    monkeypatch.setattr("fixsub.extract.shutil.which", fake_which)
    monkeypatch.setattr("fixsub.extract.subprocess.run", fake_run)

    with pytest.raises(MissingDependencyError) as error:
        extract_archive(archive, tmp_path / "out")

    assert error.value.command == "unar"
    assert commands == [["/usr/bin/tar", "--version"]]


@pytest.mark.parametrize("failure_mode", ["nonzero", "exception"])
def test_extract_rar_ignores_failed_bsdtar_probe_and_tries_next_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
) -> None:
    archive = tmp_path / "subs.rar"
    out_dir = tmp_path / "out"
    archive.write_bytes(b"archive")
    commands: list[list[str]] = []

    def fake_which(command: str) -> str | None:
        return {
            "bsdtar": "/usr/local/bin/bsdtar",
            "tar": "/usr/bin/tar",
        }.get(command)

    def fake_run(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]:
        commands.append(command)
        if command == ["/usr/local/bin/bsdtar", "--version"]:
            if failure_mode == "exception":
                raise OSError("probe failed")
            return subprocess.CompletedProcess(command, 1, stdout=b"bsdtar", stderr=b"failed")
        if command == ["/usr/bin/tar", "--version"]:
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"BSDTAR 3.5.3")
        extract_dir = Path(command[command.index("-C") + 1])
        (extract_dir / "movie.srt").write_text("subtitle", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("fixsub.extract.shutil.which", fake_which)
    monkeypatch.setattr("fixsub.extract.subprocess.run", fake_run)

    extracted = extract_archive(archive, out_dir)

    assert commands[:2] == [
        ["/usr/local/bin/bsdtar", "--version"],
        ["/usr/bin/tar", "--version"],
    ]
    assert commands[2][:3] == ["/usr/bin/tar", "-xf", str(archive)]
    assert extracted == [out_dir / "movie.srt"]


def test_extract_rar_returns_current_file_when_existing_name_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "subs.rar"
    out_dir = tmp_path / "out"
    archive.write_bytes(b"archive")
    out_dir.mkdir()
    existing = out_dir / "movie.srt"
    existing.write_text("old", encoding="utf-8")

    def fake_which(command: str) -> str | None:
        if command == "unrar":
            return "/usr/bin/unrar"
        return None

    def fake_run(command: list[str], **_: object) -> None:
        extract_dir = Path(command[-1])
        extract_dir.mkdir(parents=True, exist_ok=True)
        (extract_dir / "movie.srt").write_text("new", encoding="utf-8")

    monkeypatch.setattr("fixsub.extract.shutil.which", fake_which)
    monkeypatch.setattr("fixsub.extract.subprocess.run", fake_run)

    extracted = extract_archive(archive, out_dir)

    assert extracted == [out_dir / "movie.1.srt"]
    assert existing.read_text(encoding="utf-8") == "old"
    assert (out_dir / "movie.1.srt").read_text(encoding="utf-8") == "new"


def test_collect_subtitle_files_finds_supported_extensions(tmp_path: Path) -> None:
    (tmp_path / "a.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHi", encoding="utf-8")
    (tmp_path / "b.ass").write_text("[Events]\n", encoding="utf-8")
    (tmp_path / "cover.jpg").write_bytes(b"jpg")

    assert sorted(path.name for path in collect_subtitle_files(tmp_path)) == ["a.srt", "b.ass"]


def test_normalize_to_utf8_writes_candidate_copy(tmp_path: Path) -> None:
    source = tmp_path / "gb.srt"
    target = tmp_path / "candidate.srt"
    source.write_bytes("中文".encode("gb18030"))

    normalize_to_utf8(source, target)

    assert target.read_text(encoding="utf-8") == "中文"


def test_normalize_to_utf8_handles_utf16_bom(tmp_path: Path) -> None:
    source = tmp_path / "utf16.srt"
    target = tmp_path / "candidate.srt"
    source.write_bytes("字幕".encode("utf-16"))

    normalize_to_utf8(source, target)

    assert target.read_text(encoding="utf-8") == "字幕"


def test_normalize_to_utf8_wraps_malformed_bom_decode_error(tmp_path: Path) -> None:
    source = tmp_path / "malformed.srt"
    target = tmp_path / "candidate.srt"
    source.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(SubtitleEncodingError):
        normalize_to_utf8(source, target)

    assert not target.exists()


def test_normalize_to_utf8_rejects_binary_bytes(tmp_path: Path) -> None:
    source = tmp_path / "binary.srt"
    target = tmp_path / "candidate.srt"
    source.write_bytes(b"\x00\xff\x00\xff\x00\xff")

    with pytest.raises(SubtitleEncodingError):
        normalize_to_utf8(source, target)

    assert not target.exists()


def test_normalize_to_utf8_rejects_binary_bytes_without_nuls(tmp_path: Path) -> None:
    source = tmp_path / "image.srt"
    target = tmp_path / "candidate.srt"
    source.write_bytes(b"\xff\xd8\xff\xe0JFIF\x01\x02\x03\xff\xd9")

    with pytest.raises(SubtitleEncodingError):
        normalize_to_utf8(source, target)

    assert not target.exists()
