from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


TOKEN_QUERY_RE = re.compile(r"([?&]token=)[^&'\"\s]+", re.IGNORECASE)
REGISTERED_SECRETS: set[str] = set()


def register_log_secret(value: str | None) -> None:
    if value:
        REGISTERED_SECRETS.add(value)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


def redact_log_message(message: str) -> str:
    redacted = TOKEN_QUERY_RE.sub(r"\1<redacted>", message)
    token = os.environ.get("ASSRT_TOKEN", "").strip()
    if token:
        redacted = redacted.replace(token, "<redacted>")
    for secret in REGISTERED_SECRETS:
        redacted = redacted.replace(secret, "<redacted>")
    return redacted


def write_results_json(target: Path, payload: dict[str, Any]) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_json_ready(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"{redact_log_message(message).rstrip()}\n")
