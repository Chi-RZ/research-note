from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parent.parent / "project_config.py"


def module():
    spec = importlib.util.spec_from_file_location("research_note_project_config", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def project(tmp_path: Path) -> Path:
    (tmp_path / "project_memory").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/framework.json").write_text("{}")
    return tmp_path


def test_old_projects_get_the_standard_layout_and_legacy_features(tmp_path):
    m = module()
    cfg = m.load_project_config(project(tmp_path))
    assert cfg["roles"]["libraries"] == ["src"]
    assert cfg["features"] == m.LEGACY_FEATURES


def test_new_config_defaults_optional_integrations_off(tmp_path):
    m = module()
    root = project(tmp_path)
    path = root / m.CONFIG_PATH
    path.parent.mkdir()
    path.write_text("{}")
    cfg = m.load_project_config(root)
    assert cfg["features"] == {
        "fixer": False,
        "hpc": False,
        "editor": False,
        "cross_agent": False,
    }


def test_first_schema_config_preserves_integrations_for_legacy_projects():
    m = module()
    cfg = m.initial_project_config(legacy=True)
    assert cfg["features"] == m.LEGACY_FEATURES


def test_first_schema_config_uses_core_only_defaults_for_new_projects():
    m = module()
    cfg = m.initial_project_config()
    assert cfg["features"] == m.DEFAULT_CONFIG["features"]
    assert cfg["features"] != m.LEGACY_FEATURES


def test_feature_choices_are_persisted_without_changing_layout(tmp_path):
    m = module()
    root = project(tmp_path)
    original = m.initial_project_config()
    changed = m.with_feature_choices(original, {"fixer": True, "editor": True})
    path = m.write_project_config(root, changed)

    loaded = m.load_project_config(root)
    assert path == root / m.CONFIG_PATH
    assert loaded["features"]["fixer"] is True
    assert loaded["features"]["editor"] is True
    assert loaded["layers"] == original["layers"]


def test_custom_layout_can_keep_existing_code_in_place(tmp_path):
    m = module()
    root = project(tmp_path)
    path = root / m.CONFIG_PATH
    path.parent.mkdir()
    path.write_text(json.dumps({
        "roles": {"libraries": ["code"]},
        "layers": {
            "source": {"paths": ["code", "tests"],
                       "prefixes": ["feat", "fix", "refactor"]},
        },
    }))
    cfg = m.load_project_config(root)
    assert cfg["roles"]["libraries"] == ["code"]
    assert m.prefix_rules(cfg)["feat"] == {"code", "tests"}


def test_a_path_cannot_belong_to_two_layers(tmp_path):
    m = module()
    root = project(tmp_path)
    path = root / m.CONFIG_PATH
    path.parent.mkdir()
    path.write_text(json.dumps({
        "layers": {
            "source": {"paths": ["src", "tests", "shared"],
                       "prefixes": ["feat", "fix", "refactor"]},
            "experiments": {"paths": ["experiments", "shared"],
                            "prefixes": ["exp"]},
        },
    }))
    with pytest.raises(m.ConfigError, match="belongs to both"):
        m.load_project_config(root)


def test_all_base_layers_are_required():
    m = module()
    config = m.initial_project_config()
    config["layers"].pop("source")
    with pytest.raises(m.ConfigError, match="missing required base layers: source"):
        m.validate_config(config)


def test_role_path_must_have_an_owner(tmp_path):
    m = module()
    root = project(tmp_path)
    path = root / m.CONFIG_PATH
    path.parent.mkdir()
    path.write_text(json.dumps({"roles": {"libraries": ["unowned"]}}))
    with pytest.raises(m.ConfigError, match="no owning layer"):
        m.load_project_config(root)


def test_configured_roots_are_safe_for_git_and_shell_consumers(tmp_path):
    m = module()
    root = project(tmp_path)
    path = root / m.CONFIG_PATH
    path.parent.mkdir()
    path.write_text(json.dumps({
        "roles": {"libraries": ["code space"]},
        "layers": {
            "source": {"paths": ["code space", "tests"],
                       "prefixes": ["feat", "fix", "refactor"]},
        },
    }))
    with pytest.raises(m.ConfigError, match="unsafe path"):
        m.load_project_config(root)
