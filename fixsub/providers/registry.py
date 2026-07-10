from __future__ import annotations

import os
from typing import Protocol

from fixsub.errors import ProviderConfigError
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
        token = os.environ.get("ASSRT_TOKEN", "").strip()
        if token:
            clients["assrt"] = AssrtClient(token=token)
        elif providers == ("assrt",):
            raise ProviderConfigError("ASSRT_TOKEN is required for ASSRT API access.")
        else:
            warnings.append("ASSRT skipped: ASSRT_TOKEN is required for ASSRT API access.")
    if "subhd" in providers:
        clients["subhd"] = SubhdClient()
    if not clients:
        raise ProviderConfigError("No subtitle providers are available.")
    return clients, warnings
