"""Tests for wavern.cli.

WHAT THIS TESTS:
- CLI --version flag exits cleanly and includes the expected version string
- list-presets subcommand exits with code 0
- list-visualizations subcommand exits with code 0 and includes core visualization names
Does NOT test: GUI launch (requires display) or headless render pipeline
"""

from click.testing import CliRunner

from wavern.cli import cli


class TestCLI:
    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0a1" in result.output

    def test_list_presets(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["list-presets"])
        assert result.exit_code == 0

    def test_list_visualizations(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["list-visualizations"])
        assert result.exit_code == 0
        assert "spectrum_bars" in result.output
        assert "waveform" in result.output
