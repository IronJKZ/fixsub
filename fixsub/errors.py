from __future__ import annotations


class FixsubError(Exception):
    """Base class for user-facing fixsub errors."""


class MissingDependencyError(FixsubError):
    def __init__(self, command: str, install_hint: str) -> None:
        super().__init__(f"Missing required command: {command}\nInstall hint: {install_hint}")
        self.command = command
        self.install_hint = install_hint


class ProviderConfigError(FixsubError):
    pass


class NoVideoFoundError(FixsubError):
    pass


class NoCandidatesError(FixsubError):
    pass
