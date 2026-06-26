import logging
import os
from pathlib import Path

import pytest

from gitlabform.configuration import Configuration
from gitlabform.configuration.core import (
    ConfigInvalidException,
    ConfigurationCore,
    KeyNotFoundException,
)


class TestInit:
    def test_rejects_both_path_and_string(self):
        with pytest.raises(SystemExit):
            Configuration(config_path="/tmp/x.yml", config_string="foo: bar")

    def test_exits_on_missing_file(self):
        # yamlpath prints the error and calls exit() before any exception escapes
        with pytest.raises(SystemExit):
            Configuration(config_path="/nonexistent/does-not-exist-xyz.yml")


class TestGetConfigPath:
    def test_app_home_env_overrides(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APP_HOME", str(tmp_path))
        assert ConfigurationCore._get_config_path("ignored") == os.path.join(str(tmp_path), "config.yml")

    def test_defaults_to_home_when_unset(self, monkeypatch):
        monkeypatch.delenv("APP_HOME", raising=False)
        expected = os.path.join(str(Path.home()), ".gitlabform", "config.yml")
        assert ConfigurationCore._get_config_path(None) == expected

    def test_resolves_relative_dot_paths_to_cwd(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APP_HOME", raising=False)
        monkeypatch.chdir(tmp_path)
        for arg in [os.path.join(".", "config.yml"), "config.yml"]:
            assert ConfigurationCore._get_config_path(arg) == os.path.join(str(tmp_path), "config.yml")

    def test_passes_through_explicit_path(self, monkeypatch):
        monkeypatch.delenv("APP_HOME", raising=False)
        assert ConfigurationCore._get_config_path("/abs/path.yml") == "/abs/path.yml"


class TestGet:
    def test_returns_default_when_missing(self):
        cfg = Configuration(config_string="projects_and_groups: {}\n")
        assert cfg.get("missing|path", default="fallback") == "fallback"

    def test_raises_when_missing_and_no_default_in_debug(self):
        # KeyNotFoundException's __init__ calls sys.exit() unless DEBUG logging
        # is enabled. To exercise the exception path itself we flip the log level.
        logging.getLogger().setLevel(logging.DEBUG)
        try:
            cfg = Configuration(config_string="projects_and_groups: {}\n")
            with pytest.raises(KeyNotFoundException):
                cfg.get("missing|path")
        finally:
            logging.getLogger().setLevel(logging.WARNING)

    def test_exits_when_missing_and_no_default_outside_debug(self):
        cfg = Configuration(config_string="projects_and_groups: {}\n")
        with pytest.raises(SystemExit):
            cfg.get("missing|path")

    def test_unwraps_scalar_strings_to_plain_str(self):
        # ruamel.yaml gives back ScalarString subclasses for some YAML scalars;
        # the get() helper should normalize those to plain str for callers.
        cfg = Configuration(config_string="foo: bar\nprojects_and_groups: {}\n")
        value = cfg.get("foo")
        assert value == "bar"
        assert type(value) is str


class TestKeyNotFoundException:
    def test_stores_key_when_debug_enabled(self):
        logging.getLogger().setLevel(logging.DEBUG)
        try:
            exc = KeyNotFoundException("group|setting")
            assert exc.key == "group|setting"
        finally:
            logging.getLogger().setLevel(logging.WARNING)

    def test_exits_when_debug_disabled(self):
        logging.getLogger().setLevel(logging.WARNING)
        with pytest.raises(SystemExit):
            KeyNotFoundException("group|setting")


class TestConfigInvalidException:
    def test_wraps_underlying(self):
        inner = ValueError("bad")
        exc = ConfigInvalidException(inner)
        assert exc.underlying is inner


class TestExampleConfigDetection:
    def test_exits_when_example_config_flag_set(self, tmp_path):
        config_file = tmp_path / "config.yml"
        config_file.write_text("example_config: true\nconfig_version: 4\nprojects_and_groups: {}\n")
        with pytest.raises(SystemExit):
            Configuration(config_path=str(config_file))

    def test_exits_when_config_version_missing_or_wrong(self, tmp_path):
        config_file = tmp_path / "config.yml"
        config_file.write_text("projects_and_groups: {}\n")
        with pytest.raises(SystemExit):
            Configuration(config_path=str(config_file))

    def test_loads_valid_file(self, tmp_path):
        config_file = tmp_path / "config.yml"
        config_file.write_text("config_version: 4\nprojects_and_groups: {}\n")
        cfg = Configuration(config_path=str(config_file))
        assert cfg.config_dir == str(tmp_path)


class TestMergeConfigsInheritBreak:
    def test_rejects_inherit_true(self):
        with pytest.raises(SystemExit):
            ConfigurationCore._merge_configs(
                {"section": {"foo": 1}},
                {"section": {"foo": 2, "inherit": True}},
            )

    def test_inherit_false_replaces_section(self):
        merged = ConfigurationCore._merge_configs(
            {"section": {"foo": 1, "bar": 2}},
            {"section": {"foo": 99, "inherit": False}},
        )
        assert merged == {"section": {"foo": 99}}
