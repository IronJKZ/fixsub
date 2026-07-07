from __future__ import annotations

from pathlib import Path

from charset_normalizer import from_bytes

from fixsub.errors import SubtitleEncodingError


def _encoding_error(source: Path) -> SubtitleEncodingError:
    return SubtitleEncodingError(f"Could not decode subtitle file: {source}")


def _looks_like_binary(data: bytes) -> bool:
    binary_signatures = (
        b"\xff\xd8\xff",
        b"\x89PNG\r\n\x1a\n",
        b"GIF87a",
        b"GIF89a",
        b"%PDF",
        b"PK\x03\x04",
    )
    return any(data.startswith(signature) for signature in binary_signatures)


def normalize_to_utf8(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    data = source.read_bytes()
    if _looks_like_binary(data):
        raise _encoding_error(source)
    bom_encodings = (
        (b"\xff\xfe\x00\x00", "utf-32"),
        (b"\x00\x00\xfe\xff", "utf-32"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
        (b"\xef\xbb\xbf", "utf-8-sig"),
    )
    for bom, encoding in bom_encodings:
        if data.startswith(bom):
            try:
                text = data.decode(encoding)
            except UnicodeDecodeError as error:
                raise _encoding_error(source) from error
            target.write_text(text, encoding="utf-8", newline="")
            return target
    if b"\x00" in data:
        raise _encoding_error(source)
    for encoding in ("utf-8", "gb18030"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        target.write_text(text, encoding="utf-8", newline="")
        return target
    match = from_bytes(data).best()
    if match is None:
        raise _encoding_error(source)
    text = str(match)
    if not text:
        raise _encoding_error(source)
    target.write_text(text, encoding="utf-8", newline="")
    return target
