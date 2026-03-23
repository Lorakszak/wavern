"""Tests for wavern.cli.

WHAT THIS TESTS:
- CLI --version flag exits cleanly and includes the expected version string
- list-presets subcommand exits with code 0
- list-visualizations subcommand exits with code 0 and includes core visualization names
- --log-level flag is accepted and passes validation
- --log-file flag accepts a path argument
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

    def test_log_level_debug_accepted(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--log-level", "debug", "list-presets"])
        assert result.exit_code == 0

    def test_log_level_invalid_rejected(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--log-level", "banana", "list-presets"])
        assert result.exit_code != 0

    def test_log_file_accepted(self, tmp_path):
        runner = CliRunner()
        log_file = str(tmp_path / "test.log")
        result = runner.invoke(cli, ["--log-file", log_file, "list-presets"])
        assert result.exit_code == 0
