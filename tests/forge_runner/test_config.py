"""Tests for scripts/forge_runner/config.py (T019).

Tests:
  - default values for all flags
  - each flag parsed correctly
  - duration parsing (45m, 2700s, 1h, invalid)
  - --retry and --once are mutually exclusive
"""

from __future__ import annotations

import os

import pytest

from scripts.forge_runner.config import RunConfig, parse_args, parse_duration


class TestParseDuration:
    def test_minutes(self) -> None:
        assert parse_duration("45m") == 2700

    def test_seconds(self) -> None:
        assert parse_duration("2700s") == 2700

    def test_hours(self) -> None:
        assert parse_duration("1h") == 3600

    def test_zero_seconds(self) -> None:
        assert parse_duration("0s") == 0

    def test_large_minutes(self) -> None:
        assert parse_duration("90m") == 5400

    def test_invalid_no_unit(self) -> None:
        import argparse

        with pytest.raises(argparse.ArgumentTypeError):
            parse_duration("45")

    def test_invalid_unknown_unit(self) -> None:
        import argparse

        with pytest.raises(argparse.ArgumentTypeError):
            parse_duration("45d")

    def test_invalid_empty(self) -> None:
        import argparse

        with pytest.raises(argparse.ArgumentTypeError):
            parse_duration("")

    def test_strips_whitespace(self) -> None:
        assert parse_duration("  30m  ") == 1800


class TestParseArgsDefaults:
    def test_default_filter(self) -> None:
        cfg = parse_args([])
        assert cfg.filter_regex == ".*"

    def test_default_timeout(self) -> None:
        cfg = parse_args([])
        assert cfg.timeout_sec == 2700  # 45m

    def test_default_max_turns(self) -> None:
        cfg = parse_args([])
        assert cfg.max_turns == 120

    def test_default_repo_is_cwd(self) -> None:
        cfg = parse_args([])
        assert cfg.repo == os.getcwd()

    def test_default_log_dir(self) -> None:
        cfg = parse_args([])
        assert cfg.log_dir == ".forge/logs"

    def test_default_resume_false(self) -> None:
        cfg = parse_args([])
        assert cfg.resume is False

    def test_default_retry_none(self) -> None:
        cfg = parse_args([])
        assert cfg.retry is None

    def test_default_dry_run_false(self) -> None:
        cfg = parse_args([])
        assert cfg.dry_run is False

    def test_default_once_false(self) -> None:
        cfg = parse_args([])
        assert cfg.once is False

    def test_default_strict_dead_man_false(self) -> None:
        cfg = parse_args([])
        assert cfg.strict_dead_man is False

    def test_default_verbose_zero(self) -> None:
        cfg = parse_args([])
        assert cfg.verbose == 0


class TestParseArgsFlags:
    def test_filter_flag(self) -> None:
        cfg = parse_args(["--filter", r"^V1-\d+$"])
        assert cfg.filter_regex == r"^V1-\d+$"

    def test_timeout_minutes(self) -> None:
        cfg = parse_args(["--timeout", "30m"])
        assert cfg.timeout_sec == 1800

    def test_timeout_seconds(self) -> None:
        cfg = parse_args(["--timeout", "1800s"])
        assert cfg.timeout_sec == 1800

    def test_timeout_hours(self) -> None:
        cfg = parse_args(["--timeout", "2h"])
        assert cfg.timeout_sec == 7200

    def test_max_turns(self) -> None:
        cfg = parse_args(["--max-turns", "500"])
        assert cfg.max_turns == 500

    def test_repo_flag(self) -> None:
        cfg = parse_args(["--repo", "/tmp/myrepo"])
        assert cfg.repo == "/tmp/myrepo"

    def test_log_dir_flag(self) -> None:
        cfg = parse_args(["--log-dir", "/tmp/logs"])
        assert cfg.log_dir == "/tmp/logs"

    def test_resume_flag(self) -> None:
        cfg = parse_args(["--resume"])
        assert cfg.resume is True

    def test_retry_flag(self) -> None:
        cfg = parse_args(["--retry", "V1-3"])
        assert cfg.retry == "V1-3"

    def test_dry_run_flag(self) -> None:
        cfg = parse_args(["--dry-run"])
        assert cfg.dry_run is True

    def test_once_flag(self) -> None:
        cfg = parse_args(["--once"])
        assert cfg.once is True

    def test_strict_dead_man_flag(self) -> None:
        cfg = parse_args(["--strict-dead-man"])
        assert cfg.strict_dead_man is True

    def test_verbose_single(self) -> None:
        cfg = parse_args(["-v"])
        assert cfg.verbose == 1

    def test_verbose_double(self) -> None:
        cfg = parse_args(["-v", "-v"])
        assert cfg.verbose == 2

    def test_verbose_long_form(self) -> None:
        cfg = parse_args(["--verbose"])
        assert cfg.verbose == 1


class TestParseArgsMutualExclusion:
    def test_retry_and_once_are_mutually_exclusive(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--retry", "V1-3", "--once"])
        assert exc_info.value.code != 0

    def test_retry_alone_ok(self) -> None:
        cfg = parse_args(["--retry", "V1-3"])
        assert cfg.retry == "V1-3"
        assert cfg.once is False

    def test_once_alone_ok(self) -> None:
        cfg = parse_args(["--once"])
        assert cfg.once is True
        assert cfg.retry is None


class TestRunConfigDataclass:
    def test_run_config_is_dataclass(self) -> None:
        import dataclasses

        assert dataclasses.is_dataclass(RunConfig)

    def test_run_config_default_construction(self) -> None:
        cfg = RunConfig()
        assert cfg.filter_regex == ".*"
        assert cfg.max_turns == 120
        assert cfg.once is False
