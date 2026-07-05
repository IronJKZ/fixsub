from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(add_completion=False, no_args_is_help=False)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Process without writing the final subtitle."),
    audio: Optional[str] = typer.Option(None, "--audio", help="Force ffsubsync reference stream, such as a:0."),
    no_sync: bool = typer.Option(False, "--no-sync", help="Skip ffsubsync and rank original candidates only."),
    max_candidates: int = typer.Option(5, "--max-candidates", min=1, help="Maximum candidates to download."),
    lang: str = typer.Option("zh-Hans", "--lang", help="Infuse language suffix for final output."),
    providers: str = typer.Option("assrt", "--providers", help="Comma-separated providers. M1 supports assrt only."),
    debug: bool = typer.Option(False, "--debug", help="Print verbose diagnostics."),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    typer.echo("fixsub M1 pipeline is not implemented yet.")
