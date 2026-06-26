from unittest.mock import MagicMock, patch

import pytest
import requests

from gitlabform.processors.abstract_processor import (
    AbstractProcessor,
    MaxProcessorRetriesExceeded,
)


class _DummyProcessor(AbstractProcessor):
    """Minimal concrete subclass so we can instantiate AbstractProcessor for tests."""

    def __init__(self):
        # Skip the real __init__ — it builds a GitLab/GraphQL client which we don't need.
        self.configuration_name = "dummy"
        self.gitlab = MagicMock()
        self.custom_diff_analyzers = {}
        self.gl = MagicMock()
        self._process_calls: list[tuple[str, dict]] = []
        self._raise_on_call: Exception | None = None
        self._raise_n_times = 0

    def _process_configuration(self, project_or_project_and_group, configuration):
        self._process_calls.append((project_or_project_and_group, configuration))
        if self._raise_on_call and len(self._process_calls) <= self._raise_n_times:
            raise self._raise_on_call


class TestSectionInConfig:
    def test_true_when_section_present(self):
        p = _DummyProcessor()
        assert p._section_is_in_config({"dummy": {"x": 1}})

    def test_false_when_section_missing(self):
        p = _DummyProcessor()
        assert not p._section_is_in_config({"other": {}})


class TestNeedsUpdate:
    def test_no_update_when_dicts_match(self):
        p = _DummyProcessor()
        assert not p._needs_update({"a": 1, "b": 2}, {"a": 1, "b": 2})

    def test_update_when_value_differs(self):
        p = _DummyProcessor()
        assert p._needs_update({"a": 1, "b": 2}, {"a": 1, "b": 3})

    def test_update_when_extra_key_in_configuration(self):
        # API may return more keys than the user configured — only flag when
        # the user adds something the API isn't already reporting.
        p = _DummyProcessor()
        assert p._needs_update({"a": 1}, {"a": 1, "b": 2})

    def test_no_update_when_gitlab_has_extra_keys(self):
        p = _DummyProcessor()
        assert not p._needs_update({"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 2})

    def test_custom_diff_analyzer_overrides_default(self):
        p = _DummyProcessor()
        # analyzer says "no diff" even though values clearly differ
        p.custom_diff_analyzers["a"] = lambda key, gl, cfg: False
        assert not p._needs_update({"a": [1]}, {"a": [2]})

        p.custom_diff_analyzers["a"] = lambda key, gl, cfg: True
        assert p._needs_update({"a": [1]}, {"a": [1]})


class TestCanProceed:
    def test_default_returns_true(self):
        p = _DummyProcessor()
        assert p._can_proceed("group/proj", {})


class TestShouldRetryProcessor:
    def test_retries_on_remote_disconnected(self):
        e = requests.exceptions.ConnectionError("RemoteDisconnected('Remote end closed connection without response')")
        assert AbstractProcessor._should_retry_processor(e)

    def test_does_not_retry_other_connection_errors(self):
        assert not AbstractProcessor._should_retry_processor(requests.exceptions.ConnectionError("some other reason"))

    def test_does_not_retry_when_max_retries_exceeded(self):
        # If the lower retry layer already gave up, don't retry again at this layer.
        e = requests.exceptions.ConnectionError("HTTPSConnectionPool: Max retries exceeded with url: /foo")
        assert not AbstractProcessor._should_retry_processor(e)

    def test_does_not_retry_unrelated_exceptions(self):
        assert not AbstractProcessor._should_retry_processor(ValueError("nope"))


class TestProcessConfigurationWithRetries:
    def test_succeeds_on_first_try(self):
        p = _DummyProcessor()
        p._process_configuration_with_retries("g/p", {"dummy": {}})
        assert len(p._process_calls) == 1

    def test_retries_then_succeeds_on_retryable_error(self):
        p = _DummyProcessor()
        p._raise_on_call = requests.exceptions.ConnectionError(
            "RemoteDisconnected('Remote end closed connection without response')"
        )
        p._raise_n_times = 2
        p._process_configuration_with_retries("g/p", {"dummy": {}})
        # 2 failures + 1 success
        assert len(p._process_calls) == 3

    def test_raises_max_retries_exceeded_when_retryable_keeps_failing(self):
        p = _DummyProcessor()
        p._raise_on_call = requests.exceptions.ConnectionError(
            "RemoteDisconnected('Remote end closed connection without response')"
        )
        p._raise_n_times = 999
        with pytest.raises(MaxProcessorRetriesExceeded):
            p._process_configuration_with_retries("g/p", {"dummy": {}})
        # initial + 3 retries
        assert len(p._process_calls) == 4

    def test_reraises_non_retryable_immediately(self):
        p = _DummyProcessor()
        p._raise_on_call = ValueError("boom")
        p._raise_n_times = 999
        with pytest.raises(ValueError):
            p._process_configuration_with_retries("g/p", {"dummy": {}})
        assert len(p._process_calls) == 1


class TestProcess:
    def _make(self, configuration, dry_run=False):
        p = _DummyProcessor()
        eff = MagicMock()
        p.process("g/p", configuration, dry_run, False, eff)
        return p, eff

    def test_skips_when_section_missing(self):
        p, eff = self._make({"other": {}})
        assert p._process_calls == []
        eff.add_configuration.assert_not_called()

    def test_skips_when_section_marked_skip(self):
        p, eff = self._make({"dummy": {"skip": True}})
        assert p._process_calls == []
        eff.add_configuration.assert_not_called()

    def test_skips_non_project_sections_when_project_archived(self):
        p, eff = self._make({"dummy": {"x": 1}, "project": {"archive": True}})
        assert p._process_calls == []

    def test_processes_project_section_even_when_archived(self):
        p = _DummyProcessor()
        p.configuration_name = "project"
        eff = MagicMock()
        p.process("g/p", {"project": {"archive": True}}, False, False, eff)
        assert len(p._process_calls) == 1

    def test_dry_run_prints_diff_and_does_not_process(self):
        p = _DummyProcessor()
        eff = MagicMock()
        with patch.object(p, "_print_diff") as print_diff:
            p.process("g/p", {"dummy": {"x": 1}}, True, False, eff)
            print_diff.assert_called_once()
        assert p._process_calls == []

    def test_dry_run_with_transfer_uses_source_project(self):
        p = _DummyProcessor()
        eff = MagicMock()
        with patch.object(p, "_print_diff") as print_diff:
            p.process(
                "g/p",
                {"dummy": {"x": 1}, "project": {"transfer_from": "other/src"}},
                True,
                False,
                eff,
            )
            args, _ = print_diff.call_args
            assert args[0] == "other/src"
