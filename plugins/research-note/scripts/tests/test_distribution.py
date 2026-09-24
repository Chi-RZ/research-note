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


def test_bootstrap_memory_views_resolve_to_shared_memory(tmp_path):
    bootstrap = _bootstrap()
    shared = tmp_path / "project_memory" / "memory" / "shared"
    shared.mkdir(parents=True)
    for name in ("claude", "codex"):
        link = shared.parent / name
        link.symlink_to("shared", target_is_directory=True)
        assert link.resolve() == shared.resolve()


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


def test_contracts_name_shared_memory_as_the_authority():
    root = (PLUGIN / "templates" / "CLAUDE.md").read_text()
    record = (PLUGIN / "templates" / "project_memory-CLAUDE.md").read_text()
    assert "memory/shared/" in root
    assert "memory/shared/" in record
    assert "memory/claude/         the agent's own memory" not in record


def _bootstrap():
    """The bootstrap module, loaded from this plugin's own scripts/."""
    path = PLUGIN / "scripts" / "bootstrap_project.py"
    spec = importlib.util.spec_from_file_location("research_note_bootstrap_x", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_the_cross_agent_selector_is_read_back_never_spelled(monkeypatch):
    """The name after `@` belongs to whoever ran `marketplace add`.

    This replaces a canary. Both manifests used to declare DIFFERENT names
    (`claude-setup`, `personal`), and a test asserted they stayed different —
    not as a design rule but so that a hardcoded selector would fail visibly on
    one side. They now both declare `research-tools`, which is friendlier to read and
    kills that canary: nothing would notice the code going back to spelling it.

    So the property is tested directly. The TARGET CLI reports a marketplace
    name this repo has never heard of, and the install selector must carry that
    name. On a machine that added the marketplace from a fork or a local path,
    this is the difference between installing and silently installing nothing.

    The two `_marketplaces` answers differ on purpose: the ORIGIN side is
    searched by the name in `PLUGIN`'s own cache path, the TARGET side by the
    source URL. An earlier draft returned one list for both, and the run bailed
    before the install with the assertion never reached — passing vacuously.
    """
    b = _bootstrap()
    url = "git@example.invalid:someone/their-fork.git"
    monkeypatch.setattr(b, "PLUGIN",
                        Path.home() / ".claude/plugins/cache/mkt/research-note/9.9.9")
    monkeypatch.setattr(b.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(b, "installed", lambda agent: [])
    monkeypatch.setattr(b, "_marketplaces", lambda agent: (
        [{"name": "mkt", "url": url}] if agent == "claude"
        else [{"url": url, "name": "whatever-they-called-it"}]))

    calls = []

    class R:
        returncode = 0
        stdout = stderr = ""

    monkeypatch.setattr(b.subprocess, "run",
                        lambda cmd, **kw: (calls.append(cmd), R())[1])
    b.report.clear()
    b.sync_other_agent(dry=False)

    joined = " ".join(" ".join(c) for c in calls)
    assert "research-note@" in joined, f"never reached the install: {calls}"
    assert "research-note@whatever-they-called-it" in joined, joined
    assert "research-tools" not in joined, joined


def test_other_agent_is_the_opposite_side_and_none_off_a_cache(monkeypatch):
    b = _bootstrap()
    home = Path.home()
    monkeypatch.setattr(
        b, "PLUGIN", home / ".claude/plugins/cache/mkt/research-note/9.9.9")
    assert b.other_agent() == "codex"
    monkeypatch.setattr(
        b, "PLUGIN", home / ".codex/plugins/cache/mkt/research-note/9.9.9")
    assert b.other_agent() == "claude"
    # a dev checkout is not an agent cache: there is no marketplace to point at
    monkeypatch.setattr(b, "PLUGIN", Path("/tmp/some/checkout/research-note"))
    assert b.other_agent() is None


def test_installed_normalises_both_cli_shapes(monkeypatch):
    """Claude answers with a flat list of {id}; Codex with {installed:[{pluginId}]}."""
    b = _bootstrap()
    monkeypatch.setattr(b, "_cli_json", lambda cmd, timeout=120: (
        [{"id": "research-note@claude-setup", "version": "1.2.3"}]
        if cmd[0] == "claude" else
        {"installed": [{"pluginId": "research-note@personal", "version": "1.2.3"}]}))
    assert b.installed("claude") == [
        {"id": "research-note@claude-setup", "version": "1.2.3"}]
    assert b.installed("codex") == [
        {"id": "research-note@personal", "version": "1.2.3"}]


def test_sync_other_agent_skips_without_the_other_cli(monkeypatch):
    """A machine with one agent is complete — the step must not run or raise."""
    b = _bootstrap()
    monkeypatch.setattr(
        b, "PLUGIN", Path.home() / ".claude/plugins/cache/mkt/research-note/9.9.9")
    monkeypatch.setattr(b.shutil, "which", lambda _: None)

    def explode(*a, **k):
        raise AssertionError("no subprocess may run when the other CLI is absent")

    monkeypatch.setattr(b.subprocess, "run", explode)
    b.report.clear()
    b.sync_other_agent(dry=False)
    assert [state for state, _, _ in b.report] == ["skip"]


def test_marketplace_head_is_silent_off_a_clone(tmp_path):
    """A `github`-source marketplace is a tarball with no .git — not an error."""
    b = _bootstrap()
    assert b.marketplace_head(str(tmp_path), "uni-plugin") == (None, None)
    assert b.marketplace_head(None, None) == (None, None)


def test_marketplace_head_reads_the_clone_and_says_unknown_without_origin(tmp_path):
    """Local HEAD is read; the remote half is None rather than a false match.

    Reporting "in step" when origin could not be reached would be the one
    wrong answer here — the whole point is catching a side that has drifted.
    """
    import subprocess
    b = _bootstrap()
    run = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a],
                                    capture_output=True, text=True, check=True)
    run("init", "-q", "-b", "uni-plugin")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    (tmp_path / "f").write_text("x")
    run("add", "f")
    run("commit", "-qm", "c")
    head = run("rev-parse", "HEAD").stdout.strip()

    local, remote = b.marketplace_head(str(tmp_path), None)   # ref read from the clone
    assert local == head
    assert remote is None                                     # no origin configured


def test_each_cli_spells_the_same_two_operations_its_own_way():
    """The codex->claude half cannot be exercised live without uninstalling the
    agent running the suite, so its command shapes are pinned here instead.

    Claude takes the git ref as a `#ref` SUFFIX and installs with `install`;
    Codex takes it as a separate `--ref` and installs with `add`. `-y` is on
    the Claude install because that CLI prompts when a marketplace declares an
    install command — a bootstrap has nobody to answer.
    """
    b = _bootstrap()
    claude, codex = b.AGENT_CLIS["claude"], b.AGENT_CLIS["codex"]

    assert claude["mkt_add"]("git@h:r.git", "uni-plugin")[-1] == "git@h:r.git#uni-plugin"
    assert claude["mkt_add"]("git@h:r.git", None)[-1] == "git@h:r.git"

    cx = codex["mkt_add"]("git@h:r.git", "uni-plugin")
    assert cx[-3:] == ["git@h:r.git", "--ref", "uni-plugin"]
    assert codex["mkt_add"]("git@h:r.git", None)[-1] == "git@h:r.git"

    ci = claude["install"]("research-note@claude-setup")
    assert ci[:3] == ["claude", "plugin", "install"]
    assert "-y" in ci and ci[ci.index("--scope") + 1] == "user"
    assert ci[-1] == "research-note@claude-setup"

    assert codex["install"]("research-note@personal") == [
        "codex", "plugin", "add", "research-note@personal"]
    assert claude["refresh"]("claude-setup") == [
        "claude", "plugin", "marketplace", "update", "claude-setup"]
    assert codex["refresh"]("personal") == [
        "codex", "plugin", "marketplace", "upgrade", "personal"]
    assert claude["update"]("research-note@claude-setup") == [
        "claude", "plugin", "update", "research-note@claude-setup",
        "--scope", "user"]
    assert codex["update"]("research-note@personal") == [
        "codex", "plugin", "add", "research-note@personal"]


def test_project_registry_is_shared_and_idempotent(tmp_path, monkeypatch):
    b = _bootstrap()
    registry = tmp_path / "state" / "projects.json"
    monkeypatch.setattr(b, "PROJECT_REGISTRY", registry)
    b.report.clear()

    project = tmp_path / "project"
    project.mkdir()
    b.register_project(project, dry=False)
    b.register_project(project, dry=False)

    assert read(registry) == {"projects": [str(project.resolve())]}
    assert [s for s, what, _ in b.report if what == "project registry"] == [
        "new", "kept"]


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
