from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fixsub.errors import FixsubError

KEYCHAIN_SERVICE = "fixsub.assrt"
KEYCHAIN_ACCOUNT = "ASSRT_TOKEN"
SECURITY_PATH = Path("/usr/bin/security")


def _security_command() -> str | None:
    if SECURITY_PATH.is_file() and os.access(SECURITY_PATH, os.X_OK):
        return str(SECURITY_PATH)
    return None


def read_keychain_token() -> str | None:
    security = _security_command()
    if not security:
        return None
    result = subprocess.run(
        [security, "find-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def get_assrt_token() -> tuple[str | None, str | None]:
    environment_token = os.environ.get("ASSRT_TOKEN", "").strip()
    if environment_token:
        return environment_token, "environment"
    keychain_token = read_keychain_token()
    if keychain_token:
        return keychain_token, "keychain"
    return None, None


def store_keychain_token_interactive() -> None:
    security = _security_command()
    if not security:
        raise FixsubError("macOS security command is unavailable; cannot store ASSRT token in Keychain.")
    result = subprocess.run(
        [
            security,
            "add-generic-password",
            "-U",
            "-a",
            KEYCHAIN_ACCOUNT,
            "-s",
            KEYCHAIN_SERVICE,
            "-l",
            "fixsub ASSRT token",
            "-w",
        ],
        text=True,
    )
    if result.returncode != 0:
        raise FixsubError("Failed to store ASSRT token in macOS Keychain.")


def delete_keychain_token() -> None:
    security = _security_command()
    if not security:
        raise FixsubError("macOS security command is unavailable; cannot update Keychain.")
    result = subprocess.run(
        [security, "delete-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FixsubError("No fixsub ASSRT token was found in macOS Keychain.")
