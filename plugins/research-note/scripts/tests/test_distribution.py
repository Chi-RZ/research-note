"""The Claude and Codex packages must be two views of one plugin core."""
from __future__ import annotations

import json
import importlib.util
from pathlib import Path

import pytest


PLUGIN = Path(__file__).resolve().parents[2]
REPO = PLUGIN.parents[1]
HAS_MARKETPLACE = (REPO / ".agents" / "plugins" / "marketplace.json").is_file()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_both_manifests_name_the_same_plugin_version():
    claude = read(PLUGIN / ".claude-plugin" / "plugin.json")
    codex = read(PLUGIN / ".codex-plugin" / "plugin.json")
    assert claude["name"] == codex["name"] == "research-note"
    assert claude["version"] == codex["version"]


def test_the_claude_marketplace_entry_carries_the_plugin_version():
    """The marketplace entry is what `claude plugin install` reads; it sat at
    0.1.9 while both plugin manifests said 0.2.0 and nothing noticed."""
    if not HAS_MARKETPLACE:
        pytest.skip("installed plugin cache intentionally excludes marketplace roots")
    claude = read(PLUGIN / ".claude-plugin" / "plugin.json")
    market = read(REPO / ".claude-plugin" / "marketplace.json")
    entries = [e for e in market["plugins"] if e["name"] == "research-note"]
    assert entries and entries[0]["version"] == claude["version"]


def test_both_marketplaces_point_at_the_one_real_core():
    if not HAS_MARKETPLACE:
        pytest.skip("installed plugin cache intentionally excludes marketplace roots")
    claude = read(REPO / ".claude-plugin" / "marketplace.json")
    codex = read(REPO / ".agents" / "plugins" / "marketplace.json")
    assert claude["plugins"][0]["source"] == "./plugins/research-note"
    assert codex["plugins"][0]["source"]["path"] == "./plugins/research-note"
    for required in ("skills", "scripts", "templates", "hooks"):
        assert (PLUGIN / required).is_dir()
        assert not (PLUGIN / required).is_symlink()


def test_codex_marketplace_policy_is_complete():
    if not HAS_MARKETPLACE:
        pytest.skip("installed plugin cache intentionally excludes marketplace roots")
    entry = read(REPO / ".agents" / "plugins" / "marketplace.json")["plugins"][0]
    assert entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }
    assert entry["category"]


def test_bootstrap_skill_views_resolve_to_one_canonical_directory(tmp_path):
    bootstrap_path = PLUGIN / "scripts" / "bootstrap_project.py"
    spec = importlib.util.spec_from_file_location("research_note_bootstrap_test", bootstrap_path)
    bootstrap = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(bootstrap)

    canonical = tmp_path / ".agent" / "skills"
    canonical.mkdir(parents=True)
    for rel, target in bootstrap.SKILL_LINKS.items():
        link = tmp_path / rel
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target, target_is_directory=True)
        assert link.resolve() == canonical.resolve()


def test_bootstrap_only_preserves_old_feature_defaults_for_legacy_projects(tmp_path):
    bootstrap = _bootstrap()
    assert not bootstrap.needs_legacy_config(tmp_path)

    marker = tmp_path / ".claude/framework.json"
    marker.parent.mkdir()
    marker.write_text("{}")
    assert bootstrap.needs_legacy_config(tmp_path)

    config = tmp_path / ".research-note/project.json"
    config.parent.mkdir()
    config.write_text("{}")
    assert not bootstrap.needs_legacy_config(tmp_path)


def test_bootstrap_feature_flags_are_persistent_choices():
    bootstrap = _bootstrap()
    assert bootstrap.feature_choices(
        ["--with-fixer", "--no-qdash", "--with-cross-agent"]
    ) == {"fixer": True, "editor": False, "cross_agent": True}
    assert bootstrap.feature_choices([], has_remote=True) == {"hpc": True}

    with pytest.raises(bootstrap.ConfigError, match="conflicting"):
        bootstrap.feature_choices(["--with-fixer", "--no-fixer"])
    with pytest.raises(bootstrap.ConfigError, match="--remote"):
        bootstrap.feature_choices(["--no-hpc"], has_remote=True)


def test_core_settings_do_not_request_remote_or_scheduler_permissions():
    bootstrap = _bootstrap()
    core = json.loads(bootstrap.settings_text(hpc=False))
    hpc = json.loads(bootstrap.settings_text(hpc=True))
    core_rules = set(core["permissions"]["allow"])
    hpc_rules = set(hpc["permissions"]["allow"])

    for command in ("ssh", "scp", "rsync", "sbatch", "srun", "squeue"):
        rule = f"Bash({command}:*)"
        assert rule not in core_rules
        assert rule in hpc_rules


def test_bootstrap_layout_artifacts_follow_configured_roles():
    bootstrap = _bootstrap()
    config = json.loads((PLUGIN / "templates/project.json").read_text())
    config["roles"].update({
        "libraries": ["code"],
        "tests": ["spec"],
        "experiments": ["trials"],
        "knowledge": ["docs"],
    })
    config["layers"]["source"]["paths"] = ["code", "spec"]
    config["layers"]["experiments"]["paths"] = ["trials"]
    config["layers"]["knowledge"]["paths"] = ["docs"]

    dirs = bootstrap.layout_dirs(config)
    assert all(path in dirs for path in ("code", "spec", "trials", "docs"))
    assert "src" not in dirs and "experiments" not in dirs and "wiki" not in dirs
    links = bootstrap.contract_links(config)
    assert links["trials/AGENTS.md"] == "../.claude/experiments-CLAUDE.md"
    assert links["docs/CLAUDE.md"] == "../.claude/wiki-CLAUDE.md"
    ignored = bootstrap.gitignore_lines(config)
    assert "trials/*/logs" in ignored
    assert not any(line.startswith("experiments/") for line in ignored)


def _bootstrap():
    """The bootstrap module, loaded from this plugin's own scripts/."""
    path = PLUGIN / "scripts" / "bootstrap_project.py"
    spec = importlib.util.spec_from_file_location("research_note_bootstrap_x", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_the_ignore_list_covers_every_uncommitted_output_kind_at_both_depths():
    """`checkpoint/` was promised uncommitted by two contracts and ignored by
    nothing.

    `experiments/<node>/<group>/` holds four output kinds and the contracts
    split them by what each is FOR: `data/` and `logs/` are excluded, and so is
    `checkpoint/` — "not committed, stays on this machine". The ignore tuple
    gave `logs` and `data` both depths and gave `checkpoint` neither, so a
    freshly bootstrapped project tracked multi-gigabyte state in full. The
    comment introducing that tuple is about a merge that cost a project 105 GB
    OF CHECKPOINTS; the list under it did not mention them.

    Asserted per kind and per depth, because the failure was one missing pair
    in a list where the neighbouring pairs were right.
    """
    path = PLUGIN / "scripts" / "bootstrap_project.py"
    spec = importlib.util.spec_from_file_location("research_note_bootstrap_gi", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for kind in ("logs", "data", "checkpoint"):
        for depth in (f"experiments/*/{kind}", f"experiments/*/*/{kind}"):
            assert depth in mod.GITIGNORE_LINES, (kind, depth, mod.GITIGNORE_LINES)
