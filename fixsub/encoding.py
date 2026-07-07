from __future__ import annotations

from pathlib import Path

from charset_normalizer import from_bytes

from fixsub.errors import SubtitleEncodingError


def normalize_to_utf8(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    data = source.read_bytes()
    bom_encodings = (
        (b"\xff\xfe\x00\x00", "utf-32"),
        (b"\x00\x00\xfe\xff", "utf-32"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
        (b"\xef\xbb\xbf", "utf-8-sig"),
    )
    for bom, encoding in bom_encodings:
        if data.startswith(bom):
            text = data.decode(encoding)
            target.write_text(text, encoding="utf-8", newline="")
            return target
    if b"\x00" in data:
        raise SubtitleEncodingError(f"Could not decode subtitle file: {source}")
    for encoding in ("utf-8", "gb18030"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        target.write_text(text, encoding="utf-8", newline="")
        return target
    match = from_bytes(data).best()
    if match is None:
        raise SubtitleEncodingError(f"Could not decode subtitle file: {source}")
    text = str(match)
    if not text:
        raise SubtitleEncodingError(f"Could not decode subtitle file: {source}")
    target.write_text(text, encoding="utf-8", newline="")
    return target
