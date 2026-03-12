"""Tests for CLI commands."""

from click.testing import CliRunner

from wavern.cli import cli


class TestCLI:
    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

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
