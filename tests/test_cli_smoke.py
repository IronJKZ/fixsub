from rich.text import Text
from typer.testing import CliRunner

from fixsub.cli import app


def test_help_lists_m1_options() -> None:
    result = CliRunner().invoke(
        app,
        ["--help"],
        color=True,
        env={"FORCE_COLOR": "1", "TERM": "xterm-256color"},
    )
    output = Text.from_ansi(result.output).plain

    assert result.exit_code == 0
    assert "\x1b[" in result.output
    assert "--dry-run" in output
    assert "--audio" in output
    assert "--no-sync" in output
    assert "--max-candidates" in output
    assert "--lang" in output
    assert "--providers" in output
    assert "--interactive" not in output
