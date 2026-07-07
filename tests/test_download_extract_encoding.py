from pathlib import Path
from zipfile import ZipFile

from fixsub.download import safe_download_name
from fixsub.encoding import normalize_to_utf8
from fixsub.extract import collect_subtitle_files, extract_archive


def test_safe_download_name_keeps_known_extension() -> None:
    assert safe_download_name("assrt_001", "Movie 中文.ass") == "assrt_001.ass"
    assert safe_download_name("assrt_002", "archive.zip") == "assrt_002.zip"


def test_extract_zip_collects_subtitles_only(tmp_path: Path) -> None:
    archive = tmp_path / "subs.zip"
    out_dir = tmp_path / "out"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("movie.ass", "[Script Info]\n")
        zip_file.writestr("notes.txt", "ignore")

    extracted = extract_archive(archive, out_dir)

    assert extracted == [out_dir / "movie.ass"]


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
