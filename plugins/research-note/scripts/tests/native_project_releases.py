#!/usr/bin/env python3
"""Opt-in native-host release matrix; no model calls or published changes.

Run with --workspace /path/to/work/tmp. Fixtures/evidence are retained there.
Claude uses an isolated config directory. Codex uses its native cache; temporary
fixture trust entries are removed afterward, preserving user configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import time

PLUGIN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN / "scripts"))
import project_runtime as runtime


def run_matrix(workspace: Path) -> Path:
    for host in ("claude", "codex", "git", "uv"):
        if not shutil.which(host):
            raise ValueError(f"native matrix requires {host}")
    workspace.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="research-note-release-test-", dir=workspace)).resolve()
    env = {k: v for k, v in os.environ.items()
           if k not in {"RESEARCH_NOTE_PROJECT_DIR", "CLAUDE_PROJECT_DIR", "RN_RUNTIME_UPDATE_INTERNAL"}}
    env.update({"CLAUDE_CONFIG_DIR": str(base / "claude-config"),
                "RESEARCH_NOTE_RELEASE_STORE": str(base / "releases"),
                "PYTHONDONTWRITEBYTECODE": "1"})
    results = []
    counter = 0

    def run(cwd, *args, expect=0, extra_env=None):
        nonlocal counter
        counter += 1
        result = subprocess.run(list(map(str, args)), cwd=cwd, env={**env, **(extra_env or {})},
                                capture_output=True, text=True, timeout=180)
        (base / f"{counter:02d}.log").write_text(result.stdout + result.stderr)
        if (result.returncode == 0) != (expect == 0):
            raise AssertionError(f"command {counter} failed expectation: {args}\n{result.stdout}\n{result.stderr}")
        return result

    def pin(p):
        return json.loads((p / runtime.LOCK).read_text())

    def selected(p):
        return base / "releases" / pin(p)["runtime"]

    def fingerprint(p):
        return {str(f.relative_to(p)): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in p.rglob("*") if f.is_file()
                and not {".git", ".venv", "__pycache__"}.intersection(f.relative_to(p).parts)}

    def verify(p):
        run(p, sys.executable, PLUGIN / "scripts/project_runtime.py", "check", p)
        lock = pin(p)
        host = json.loads((p / ".research-note/state/host-install.json").read_text())
        assert host["selector"] == lock["selector"] and host["version"] == lock["version"]
        assert host["claude"]["status"] == "installed", host
        assert host["codex"]["status"] == "loaded", host
        assert all(f"/{lock['marketplace']}/research-note/{lock['version']}/" in path
                   for path in host["codex"]["skills"])
        assert Path(host["claude"]["source"]).resolve() == selected(p)
        assert not (p / runtime.RUNTIME).exists()
        return host

    def passed(case, **details):
        results.append({"case": case, "status": "passed", **details})
        print(f"PASS {case}", flush=True)

    repo = base / "source-repo"
    src = repo / "plugins/research-note"
    shutil.copytree(PLUGIN, src, ignore=shutil.ignore_patterns("tests", "__pycache__", ".in_use"))
    # Different runs have independent immutable identities and native caches.
    for rel in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        p = src / rel
        data = json.loads(p.read_text())
        data.update(version="0.1.0", description=f"Native release fixture {base.name}")
        p.write_text(json.dumps(data, indent=2) + "\n")
    run(base, "git", "init", "-q", "-b", "main", repo)
    run(repo, "git", "add", ".")
    run(repo, "git", "-c", "user.name=release-test", "-c", "user.email=release-test@example.invalid",
        "commit", "-q", "-m", "Release fixture 0.1.0")
    run(repo, "git", "tag", "v0.1.0")
    updater = PLUGIN / "scripts/update_projects.sh"
    a, b, c, conflict, untrusted = [base / name for name in ("a", "b", "c", "conflict", "untrusted")]
    for p in (a, b, c, conflict, untrusted):
        p.mkdir()
        run(p, "git", "init", "-q", "-b", "main")
    codex_config = Path(os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")) / "config.toml"
    before = codex_config.read_bytes() if codex_config.exists() else b""
    trust = "\n" + "\n".join(f"[projects.{json.dumps(str(p))}]\ntrust_level = \"trusted\"\n"
                                for p in (a, b, c, conflict))
    trusted = before + trust.encode()
    codex_config.parent.mkdir(parents=True, exist_ok=True)
    codex_config.write_bytes(trusted)
    start = time.monotonic()
    try:
        for p in (a, b, c, conflict):
            run(p, sys.executable, src / "scripts/bootstrap_project.py", p, "--no-self-tests")
            verify(p)
        assert selected(a) == selected(b) == selected(c)
        passed("same-release-shared", source=str(selected(a)), selector=pin(a)["selector"])
        old_b, old_c = fingerprint(b), fingerprint(c)
        old_a = pin(a)
        run(a, sys.executable, PLUGIN / "scripts/bootstrap_project.py", a, "--no-self-tests")
        assert pin(a) == old_a
        verify(a)
        passed("setup-preserves-selected-release")

        for rel in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
            p = src / rel
            data = json.loads(p.read_text()); data["version"] = "0.1.1"
            p.write_text(json.dumps(data, indent=2) + "\n")
        skill = src / "skills/analyze/SKILL.md"
        skill.write_text(skill.read_text() + "\n<!-- native fixture revision two -->\n")
        run(a, "bash", updater, "--source", src, a)
        verify(a)
        assert pin(a)["version"] == "0.1.1" and pin(a)["sha256"] != old_a["sha256"]
        assert fingerprint(b) == old_b and fingerprint(c) == old_c
        assert selected(b).is_dir()
        verify(b); verify(c)
        passed("local-uncommitted-update-isolates-projects", a=pin(a), b=pin(b))

        current = fingerprint(a)
        skill.write_text(skill.read_text() + "\n<!-- later source edit, not installed -->\n")
        assert fingerprint(a) == current
        assert "later source edit" not in (selected(a) / "skills/analyze/SKILL.md").read_text()
        passed("source-edits-do-not-change-installed-release")
        skill.write_text(skill.read_text().replace("\n<!-- later source edit, not installed -->\n", ""))
        run(repo, "git", "add", ".")
        run(repo, "git", "-c", "user.name=release-test", "-c", "user.email=release-test@example.invalid",
            "commit", "-q", "-m", "Release fixture 0.1.1")
        run(repo, "git", "tag", "v0.1.1")

        run(a, "bash", updater, "--version", "0.1.0", "--repository", repo, a)
        verify(a)
        assert pin(a)["sha256"] == old_a["sha256"]
        assert selected(a) == selected(b) == selected(c)
        passed("explicit-release-downgrade-reuses-installation")

        run(a, "bash", updater, "--latest", "--repository", repo, a)
        verify(a)
        assert pin(a)["version"] == "0.1.1"
        assert fingerprint(b) == old_b and fingerprint(c) == old_c
        passed("latest-fetch-updates-only-requested-project")

        installed_pin = pin(a)
        run(a, sys.executable, PLUGIN / "scripts/bootstrap_project.py", a, "--no-self-tests")
        assert pin(a) == installed_pin
        verify(a)
        passed("setup-preserves-provenance-after-remote-update")

        current = fingerprint(a)
        run(a, "bash", updater, "--source", src, "--version", "9.9.9", a, expect=1)
        assert fingerprint(a) == current
        run(a, "bash", updater, "--version", "9.9.9", "--repository", repo, a, expect=1)
        assert fingerprint(a) == current
        passed("bad-version-and-missing-tag-leave-project-unchanged")

        run(a, "bash", updater, "--latest", "--repository", repo, "--dry-run", a)
        assert fingerprint(a) == current
        passed("dry-run-is-read-only")

        contract = conflict / ".claude/CLAUDE.md"
        contract.write_text("unrecognized framework edit\n" + contract.read_text())
        prior = fingerprint(conflict)
        run(conflict, "bash", updater, "--source", src, conflict, expect=1)
        assert fingerprint(conflict) == prior
        passed("contract-conflict-stops-before-switch")

        failing = base / "failing-source"
        shutil.copytree(src, failing)
        p = failing / "scripts/update_projects.sh"
        p.write_text(p.read_text() + "\nexit 23\n")
        git_config = (a / ".git/config").read_bytes()
        run(a, "bash", updater, "--source", failing, a, expect=1)
        assert fingerprint(a) == current and (a / ".git/config").read_bytes() == git_config
        passed("failed-update-restores-selection-contracts-and-hooks")

        old_installer = base / "old-installer"
        shutil.copytree(src, old_installer)
        (old_installer / "scripts/project_runtime.py").write_text("# pre-shared private installer\n")
        run(a, "bash", updater, "--source", old_installer, a, expect=1)
        assert fingerprint(a) == current
        passed("pre-shared-installer-is-refused-before-writes")

        # Exercise a real native CLI failure after contracts have been synced.
        host_failure = base / "host-failure-source"
        shutil.copytree(src, host_failure)
        p = host_failure / "skills/analyze/SKILL.md"
        p.write_text(p.read_text() + "\n<!-- deliberately failing host fixture -->\n")
        shim_dir = base / "host-failure-bin"
        shim_dir.mkdir()
        shim = shim_dir / "claude"
        shim.write_text('#!/bin/sh\ncase "$1:$2" in plugin:install) echo "deliberate native install failure" >&2; exit 23;; esac\n'
                        + "exec " + shlex.quote(shutil.which("claude")) + ' "$@"\n')
        shim.chmod(0o755)
        run(a, "bash", updater, "--source", host_failure, a, expect=1,
            extra_env={"PATH": str(shim_dir) + os.pathsep + env["PATH"]})
        assert fingerprint(a) == current and (a / ".git/config").read_bytes() == git_config
        verify(a)
        passed("native-install-failure-rolls-back-project")

        run(b, "git", "add", ".")
        run(b, "git", "-c", "user.name=release-test", "-c", "user.email=release-test@example.invalid",
            "commit", "-q", "--no-verify", "-m", "Fixture setup")
        wt = base / "b-worktree"
        run(b, "git", "worktree", "add", "-b", "release-test", wt)
        branch_lock = (wt / runtime.LOCK).read_bytes()
        run(wt, "bash", updater, "--source", src, wt)
        verify(b)
        assert pin(b)["version"] == "0.1.1" and (wt / runtime.LOCK).read_bytes() == branch_lock
        # A checkout may contain a tracked lock from its branch. The command
        # resolves the canonical main lock; it does not edit that branch copy.
        run(wt, sys.executable, PLUGIN / "scripts/project_runtime.py", "check", wt)
        assert selected(c).is_dir() and fingerprint(c) == old_c
        passed("worktree-update-selects-main-checkout-only")

        run(untrusted, sys.executable, src / "scripts/bootstrap_project.py", untrusted, "--no-self-tests")
        host = json.loads((untrusted / ".research-note/state/host-install.json").read_text())
        assert host["claude"]["status"] == "installed" and host["codex"]["status"] == "pending", host
        passed("untrusted-codex-is-reported-pending")

        assert codex_config.read_bytes() == trusted
        passed("native-installation-preserves-user-enablement")
    finally:
        # Remove only our exact trust block if another process edited the file.
        current_config = codex_config.read_bytes()
        if current_config == trusted:
            codex_config.write_bytes(before)
        elif trust.encode() in current_config:
            codex_config.write_bytes(current_config.replace(trust.encode(), b"", 1))
        report = {"workspace": str(base), "seconds": round(time.monotonic() - start, 2),
                  "cases": results, "codex_user_config_restored": codex_config.read_bytes() == before}
        (base / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"Evidence: {base / 'report.json'}", flush=True)
    return base


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    run_matrix(args.workspace.resolve())
