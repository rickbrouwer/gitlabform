import logging
from unittest.mock import MagicMock

import pytest

from gitlabform.configuration import Configuration
from gitlabform.configuration.transform import (
    AccessLevelsTransformer,
    ConfigurationTransformers,
    GroupTransformer,
    ImplicitNameTransformer,
)
from gitlabform.gitlab import GitLab


def _config(yaml_string):
    return Configuration(config_string=yaml_string)


class TestConfigurationTransformers:
    def test_init_wires_up_all_transformers(self):
        gitlab = MagicMock(GitLab)
        t = ConfigurationTransformers(gitlab, log_level=logging.INFO)
        assert t.user_transformer is not None
        assert t.group_transformer is not None
        assert t.implicit_name_transformer is not None
        assert t.access_level_transformer is not None

    def test_transform_runs_all_sub_transformers(self):
        gitlab = MagicMock(GitLab)
        t = ConfigurationTransformers(gitlab, log_level=logging.INFO)
        configuration = _config("projects_and_groups:\n  foo/*:\n    project_settings:\n      x: 1\n")
        t.transform(configuration)
        # config should still be present and traversable after the chain
        assert configuration.get("projects_and_groups|foo/*|project_settings|x") == 1

    def test_transform_logs_debug_diff_when_debug_enabled(self):
        gitlab = MagicMock(GitLab)
        t = ConfigurationTransformers(gitlab, log_level=logging.DEBUG)
        configuration = _config("projects_and_groups:\n  foo/*:\n    project_settings:\n      x: 1\n")
        t.transform(configuration)


class TestGroupTransformerNoMatches:
    def test_does_not_fail_when_no_protected_environments(self):
        gitlab = MagicMock(GitLab)
        configuration = _config("projects_and_groups:\n  foo/*:\n    project_settings:\n      x: 1\n")
        # Should silently no-op (YAMLPathException is swallowed internally).
        GroupTransformer(gitlab).transform(configuration)

    def test_does_not_fail_when_no_approval_rule_groups(self):
        gitlab = MagicMock(GitLab)
        configuration = _config("projects_and_groups:\n  foo/*:\n    project_settings:\n      x: 1\n")
        GroupTransformer(gitlab).transform(configuration)


class TestImplicitNameTransformerEdgeCases:
    def test_does_not_fail_when_no_protected_environments(self):
        configuration = _config("projects_and_groups:\n  foo/*:\n    project_settings:\n      x: 1\n")
        ImplicitNameTransformer(MagicMock(GitLab)).transform(configuration)

    def test_sets_name_from_environment_key(self):
        configuration = _config("""
            projects_and_groups:
              foo/bar:
                protected_environments:
                  staging:
                    deploy_access_levels:
                      - access_level: 30
            """)
        ImplicitNameTransformer(MagicMock(GitLab)).transform(configuration)
        assert configuration.get("projects_and_groups|foo/bar|protected_environments|staging|name") == "staging"


class TestAccessLevelsTransformerArrayBranch:
    def test_translates_string_levels_inside_allowed_to_push(self):
        configuration = _config("""
            projects_and_groups:
              foo/bar:
                branches:
                  main:
                    protected: true
                    allowed_to_push:
                      - access_level: developer
                    allowed_to_merge:
                      - access_level: maintainer
                    allowed_to_unprotect:
                      - access_level: maintainer
            """)
        AccessLevelsTransformer(MagicMock(GitLab)).transform(configuration)
        assert configuration.get("projects_and_groups|foo/bar|branches|main|allowed_to_push")[0]["access_level"] == 30

    def test_exits_on_invalid_access_level_string_in_array(self):
        configuration = _config("""
            projects_and_groups:
              foo/bar:
                branches:
                  main:
                    protected: true
                    allowed_to_push:
                      - access_level: notavalidlevel
            """)
        with pytest.raises(SystemExit):
            AccessLevelsTransformer(MagicMock(GitLab)).transform(configuration)
