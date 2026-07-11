import subprocess

from fixsub.credentials import (
    KEYCHAIN_ACCOUNT,
    KEYCHAIN_SERVICE,
    delete_keychain_token,
    get_assrt_token,
    read_keychain_token,
    store_keychain_token_interactive,
)


def test_environment_token_takes_precedence_over_keychain(monkeypatch) -> None:
    monkeypatch.setenv("ASSRT_TOKEN", "environment-secret")
    monkeypatch.setattr("fixsub.credentials.read_keychain_token", lambda: "keychain-secret")

    assert get_assrt_token() == ("environment-secret", "environment")


def test_get_assrt_token_falls_back_to_keychain(monkeypatch) -> None:
    monkeypatch.delenv("ASSRT_TOKEN", raising=False)
    monkeypatch.setattr("fixsub.credentials.read_keychain_token", lambda: "keychain-secret")

    assert get_assrt_token() == ("keychain-secret", "keychain")


def test_read_keychain_token_returns_none_when_item_is_missing(monkeypatch) -> None:
    monkeypatch.setattr("fixsub.credentials._security_command", lambda: "/usr/bin/security")
    monkeypatch.setattr(
        "fixsub.credentials.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 44, stdout="", stderr="missing"),
    )

    assert read_keychain_token() is None


def test_store_keychain_token_uses_interactive_security_prompt(monkeypatch) -> None:
    calls: list[tuple[list[str], dict]] = []
    monkeypatch.setattr("fixsub.credentials._security_command", lambda: "/usr/bin/security")

    def fake_run(command: list[str], **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("fixsub.credentials.subprocess.run", fake_run)

    store_keychain_token_interactive()

    command, kwargs = calls[0]
    assert command[-1] == "-w"
    assert KEYCHAIN_ACCOUNT in command
    assert KEYCHAIN_SERVICE in command
    assert kwargs == {"text": True}


def test_delete_keychain_token_uses_service_and_account(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("fixsub.credentials._security_command", lambda: "/usr/bin/security")

    def fake_run(command: list[str], **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("fixsub.credentials.subprocess.run", fake_run)

    delete_keychain_token()

    assert calls[0][1:] == ["delete-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE]
