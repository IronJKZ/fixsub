from typer.testing import CliRunner

from fixsub.cli import app


def test_help_lists_m1_options() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--dry-run" in result.output
    assert "--audio" in result.output
    assert "--no-sync" in result.output
    assert "--max-candidates" in result.output
    assert "--lang" in result.output
    assert "--providers" in result.output
    assert "--interactive" not in result.output
