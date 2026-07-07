from __future__ import annotations

import shutil
from pathlib import Path

from charset_normalizer import from_bytes


def normalize_to_utf8(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    data = source.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        target.write_text(text, encoding="utf-8", newline="")
        return target
    match = from_bytes(data).best()
    if match is None:
        shutil.copy2(source, target)
        return target
    text = str(match)
    target.write_text(text, encoding="utf-8", newline="")
    return target
