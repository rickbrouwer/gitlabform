from unittest.mock import MagicMock

import pytest

from gitlabform.processors.defining_keys import And, Key
from gitlabform.processors.multiple_entities_processor import MultipleEntitiesProcessor


class _Processor(MultipleEntitiesProcessor):
    """Test-only concrete subclass that bypasses the AbstractProcessor constructor
    so we don't need a real GitLab client."""

    def __init__(self, list_result=None, edit_method=True):
        self.configuration_name = "things"
        self.gitlab = MagicMock()
        self.custom_diff_analyzers = {}
        self.gl = MagicMock()

        self.list_method = MagicMock(return_value=list_result or [])
        self.add_method = MagicMock()
        self.delete_method = MagicMock()
        self.edit_method = MagicMock() if edit_method else None

        self.defining = Key("name")
        self.required_to_create_or_update = And(Key("name"), Key("value"))


class TestIsIn:
    def test_returns_matching_entity(self):
        p = _Processor()
        match = p._is_in({"name": "a"}, {"1": {"name": "a", "value": 1}})
        assert match == {"name": "a", "value": 1}

    def test_returns_false_when_no_match(self):
        p = _Processor()
        assert p._is_in({"name": "a"}, {"1": {"name": "b"}}) is False


class TestFindDuplicates:
    def test_exits_on_duplicate_defining_keys(self):
        p = _Processor()
        with pytest.raises(SystemExit):
            p._find_duplicates(
                "g/proj",
                {
                    "first": {"name": "x", "value": 1},
                    "second": {"name": "x", "value": 2},
                },
            )

    def test_passes_when_no_duplicates(self):
        p = _Processor()
        p._find_duplicates(
            "g/proj",
            {
                "first": {"name": "x"},
                "second": {"name": "y"},
            },
        )


class TestValidateRequired:
    def test_create_or_update_exits_when_missing_required(self):
        p = _Processor()
        with pytest.raises(SystemExit):
            p._validate_required_to_create_or_update("g/p", "first", {"name": "x"})

    def test_create_or_update_passes_when_all_required_present(self):
        p = _Processor()
        p._validate_required_to_create_or_update("g/p", "first", {"name": "x", "value": 1})

    def test_delete_exits_when_missing_defining(self):
        p = _Processor()
        with pytest.raises(SystemExit):
            p._validate_required_to_delete("g/p", "first", {"value": 1})

    def test_delete_passes_when_defining_present(self):
        p = _Processor()
        p._validate_required_to_delete("g/p", "first", {"name": "x"})


class TestProcessConfiguration:
    def test_adds_entity_only_in_configuration(self):
        p = _Processor(list_result=[])
        p._process_configuration("g/p", {"things": {"first": {"name": "x", "value": 1}}})
        p.add_method.assert_called_once_with("g/p", {"name": "x", "value": 1})
        p.edit_method.assert_not_called()
        p.delete_method.assert_not_called()

    def test_edits_when_existing_entity_changed(self):
        p = _Processor(list_result=[{"name": "x", "value": 0}])
        p._process_configuration("g/p", {"things": {"first": {"name": "x", "value": 1}}})
        p.edit_method.assert_called_once()
        p.add_method.assert_not_called()

    def test_no_action_when_existing_entity_matches(self):
        p = _Processor(list_result=[{"name": "x", "value": 1}])
        p._process_configuration("g/p", {"things": {"first": {"name": "x", "value": 1}}})
        p.edit_method.assert_not_called()
        p.add_method.assert_not_called()
        p.delete_method.assert_not_called()

    def test_delete_marker_removes_entity(self):
        p = _Processor(list_result=[{"name": "x", "value": 1}])
        p._process_configuration("g/p", {"things": {"first": {"name": "x", "delete": True}}})
        p.delete_method.assert_called_once()

    def test_recreates_when_no_edit_method(self):
        p = _Processor(list_result=[{"name": "x", "value": 0}], edit_method=False)
        p._process_configuration("g/p", {"things": {"first": {"name": "x", "value": 1}}})
        p.delete_method.assert_called_once()
        p.add_method.assert_called_once_with("g/p", {"name": "x", "value": 1})

    def test_enforce_deletes_entities_only_in_gitlab(self):
        p = _Processor(list_result=[{"name": "stranger", "value": 9}])
        p._process_configuration(
            "g/p",
            {
                "things": {
                    "enforce": True,
                    "first": {"name": "x", "value": 1},
                }
            },
        )
        p.delete_method.assert_called_once_with("g/p", {"name": "stranger", "value": 9})
        p.add_method.assert_called_once_with("g/p", {"name": "x", "value": 1})

    def test_without_enforce_leaves_extra_gitlab_entities_alone(self):
        p = _Processor(list_result=[{"name": "stranger", "value": 9}])
        p._process_configuration("g/p", {"things": {"first": {"name": "x", "value": 1}}})
        p.delete_method.assert_not_called()
        p.add_method.assert_called_once()
