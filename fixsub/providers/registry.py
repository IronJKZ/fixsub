from __future__ import annotations

from typing import Protocol

from fixsub.credentials import get_assrt_token
from fixsub.errors import ProviderConfigError
from fixsub.logging_utils import register_log_secret
from fixsub.models import DownloadedFile, SearchResult
from fixsub.providers.assrt_api import AssrtClient
from fixsub.providers.subhd import SubhdClient

SUPPORTED_PROVIDERS = {"assrt", "subhd"}
DEFAULT_PROVIDERS = ("assrt", "subhd")


class ProviderClient(Protocol):
    def search(self, query: str) -> list[SearchResult]:
        ...

    def download(self, result: SearchResult, target_dir) -> DownloadedFile:
        ...


def parse_providers(value: str) -> tuple[str, ...]:
    providers: list[str] = []
    for raw_provider in value.split(","):
        provider = raw_provider.strip().lower()
        if not provider:
            continue
        if provider not in SUPPORTED_PROVIDERS:
            raise ProviderConfigError(f"Unsupported provider: {provider}")
        if provider not in providers:
            providers.append(provider)
    return tuple(providers) or DEFAULT_PROVIDERS


def build_provider_clients(providers: tuple[str, ...]) -> tuple[dict[str, ProviderClient], list[str]]:
    clients: dict[str, ProviderClient] = {}
    warnings: list[str] = []
    if "assrt" in providers:
        token, _source = get_assrt_token()
        if token:
            register_log_secret(token)
            clients["assrt"] = AssrtClient(token=token)
        elif providers == ("assrt",):
            raise ProviderConfigError("ASSRT token is required. Run `fixsub auth set` or set ASSRT_TOKEN.")
        else:
            warnings.append("ASSRT skipped: run `fixsub auth set` or set ASSRT_TOKEN.")
    if "subhd" in providers:
        clients["subhd"] = SubhdClient()
    if not clients:
        raise ProviderConfigError("No subtitle providers are available.")
    return clients, warnings
