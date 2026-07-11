from pathlib import Path

from fixsub.logging_utils import REGISTERED_SECRETS, append_log, redact_log_message, register_log_secret


def test_redact_log_message_removes_token_query_value(monkeypatch) -> None:
    monkeypatch.setenv("ASSRT_TOKEN", "secret-token")

    message = (
        "Client error for url "
        "'https://api.assrt.net/v1/sub/download?token=secret-token&id=156894'"
    )

    assert redact_log_message(message) == (
        "Client error for url "
        "'https://api.assrt.net/v1/sub/download?token=<redacted>&id=156894'"
    )


def test_append_log_redacts_current_assrt_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASSRT_TOKEN", "secret-token")
    log_path = tmp_path / "fixsub.log"

    append_log(log_path, "failed with secret-token")

    assert log_path.read_text(encoding="utf-8") == "failed with <redacted>\n"


def test_redact_log_message_redacts_registered_keychain_secret() -> None:
    REGISTERED_SECRETS.clear()
    register_log_secret("keychain-secret")

    try:
        assert redact_log_message("failed with keychain-secret") == "failed with <redacted>"
    finally:
        REGISTERED_SECRETS.clear()
