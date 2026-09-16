#!/usr/bin/env python3
"""Make one directory into a framework project — the mechanical half of /project-setup.

Everything here is derivable from the plugin's templates plus the target path, so
it is a script rather than skill prose: repeatable, testable, and identical in
every project. What is NOT here is everything that needs a judgment call —
migrating existing code into src/ + experiments/, pinning dependency
versions. The skill owns those and calls this for the rest.

IDEMPOTENT BY CONSTRUCTION: an existing file is kept and reported as `kept`,
never overwritten (your edited contracts and settings survive
a re-run). Generated artifacts (_index.md, dashboard.html) are refreshed.

Also the FINISHING MOVE after either agent updates the plugin: re-run it and the
project's qdash copy, board and fixer daemon all come back pointing at the new
version (everything else reports `kept`).

Usage:
  bootstrap_project.py [PROJECT_DIR] [--dry-run]
                       [--with-fixer] [--with-editor] [--with-cross-agent]
                       [--with-hpc | --remote HOST:DIR ...]

New projects start with the record workflow only. Fixer, HPC, editor support
and cross-agent registration are opt-in and the choice is saved in
`.research-note/project.json`. The old `--no-fixer`, `--no-qdash` and
`--no-cross-agent` flags remain accepted and now persist their choice. Projects
created before this configuration existed keep their integrations enabled.

ONE command can configure BOTH agents. The project-side bindings were always dual
(AGENTS.md per layer, one shared memory dir, one shared skills dir); what was
not was the machine, because each CLI keeps its own marketplace list and its
own install pin. So this also registers the plugin with whichever of Claude /
Codex is installed and does not have it yet, from the same marketplace source
the running side was installed from. Idempotent, never fatal, and
--no-cross-agent opts out.

--remote HOST:DIR declares a remote HPC (ssh alias + project clone path on the
cluster). REPEATABLE: the first occurrence is the default host (written as
REMOTE_HOST/REMOTE_DIR — the single-host back-compat form); with several, all
of them land in .claude/hpc.env's multi-remote keys (REMOTE_HOSTS +
REMOTE_DIR_<host>) and every host is monitored equally. Keys already present
are kept. Each host then gets `remote.sh setup --host <h>` — clone-from-GitHub
/ ff-pull + SHA check; a FRESH clone is sparse (cone: src/ tests/ experiments/,
excluding project_memory/ and wiki/; .claude/ IS included, the submit templates read hpc.env from it), with
an old-git pattern fallback. The local repo must have a GitHub origin: that is
the code channel to the cluster.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
TEMPLATES = PLUGIN / "templates"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import githooks_install  # noqa: E402
import contracts  # noqa: E402
from project_config import (
    CONFIG_PATH,
    ConfigError,
    feature_enabled,
    initial_project_config,
    load_project_config,
    with_feature_choices,
    write_project_config,
)

#: template -> where it lands in the project (project-OWNED copies from here on;
#: the plugin's templates are the seed, not a live mirror)
FILES = {"framework.json": ".claude/framework.json"}
#: the four contracts are not copied but GENERATED — template + the project's
#: own rules file — by contracts.py, here and at every update
# Both agent-specific discovery locations are views onto one canonical skill
# directory. Targets are relative to each link's parent directory.
SKILL_LINKS = {
    ".claude/skills": "../.agent/skills",
    ".agents/skills": "../.agent/skills",
}

#: The two agent CLIs this plugin serves, and the verbs each spells differently
#: for the same two operations. Both were run to find this out, because they
#: agree on nothing: Claude installs with `install` and takes the git ref as a
#: `#ref` SUFFIX on the source; Codex installs with `add` and takes it as a
#: separate `--ref`. `home` is the plugin tree each keeps, and is also how a
#: running bootstrap tells which side it was launched from.
AGENT_CLIS = {
    "claude": {
        "home": Path.home() / ".claude" / "plugins",
        "mkt_add": lambda url, ref: ["claude", "plugin", "marketplace", "add",
                                     f"{url}#{ref}" if ref else url],
        # --scope user: registering the OTHER agent is a machine fact, not this
        # project's. -y: `claude plugin install` prompts when a marketplace
        # declares an install command; this one does not, but a bootstrap has
        # no one to answer if that ever changes.
        "install": lambda sel: ["claude", "plugin", "install",
                                "--scope", "user", "-y", sel],
        "refresh": lambda name: ["claude", "plugin", "marketplace", "update", name],
        "update": lambda sel: ["claude", "plugin", "update", sel,
                               "--scope", "user"],
    },
    "codex": {
        "home": Path.home() / ".codex" / "plugins",
        "mkt_add": lambda url, ref: ["codex", "plugin", "marketplace", "add", url]
                                    + (["--ref", ref] if ref else []),
        "install": lambda sel: ["codex", "plugin", "add", sel],
        "refresh": lambda name: ["codex", "plugin", "marketplace", "upgrade", name],
        "update": lambda sel: ["codex", "plugin", "add", sel],
    },
}

# Agent-neutral project discovery. Claude happens to keep project-scoped plugin
# rows; Codex does not. A shared registry is therefore the only way a Codex-only
# machine can update every framework project without scanning the whole home
# directory. Legacy Claude rows remain an import source in update_projects.sh.
PROJECT_REGISTRY = Path.home() / ".config" / "research-note" / "projects.json"
#: editor/<src> -> the folder it installs as, + the label the step prints. The
#: version in the folder name is FROZEN on purpose: it is a stable overwrite
#: target. Tracking each extension's real version would strand the old folder
#: beside the new one on upgrade, and VS Code would load both.
EDITOR_EXTENSIONS = (
    ("qdash", "local.qdash-0.0.1", "qdash (board viewer)"),
    ("markdown-white-preview", "local.markdown-white-preview-0.0.1",
     "markdown white preview"),
)
# Slash-less on purpose. A pattern ending in "/" matches DIRECTORIES ONLY, so a
# SYMLINK standing where one of these normally sits is NOT ignored — and a
# `git add -A` in a worktree that links data/ and logs/ back to the main
# checkout then stages the link. Merging that commit makes git delete the real
# (ignored) contents to make room for the symlink, silently: it cost a project
# 105 GB of checkpoints and 50 logs in one merge. These forms match files,
# directories and symlinks alike.
GITIGNORE_BASE = (".fixer", ".venv", "__pycache__/", "*.egg-info/")


def gitignore_lines(config: dict) -> tuple[str, ...]:
    lines = list(GITIGNORE_BASE)
    for root in config["roles"]["experiments"]:
        for depth in ("*/*", "*"):
            for kind in ("logs", "data", "checkpoint"):
                lines.append(f"{root}/{depth}/{kind}")
    return tuple(lines)


# Public default retained for the setup contract and its distribution test.
GITIGNORE_LINES = gitignore_lines(initial_project_config())

report: list[tuple[str, str, str]] = []       # (state, what, detail)


def needs_legacy_config(proj: Path) -> bool:
    """Whether first-time schema config must preserve pre-schema behaviour."""
    return (
        not (proj / CONFIG_PATH).exists()
        and (proj / ".claude/framework.json").is_file()
    )


def layout_dirs(config: dict) -> tuple[str, ...]:
    """Directories the configured roles need, in stable creation order."""
    paths = [
        *config["roles"]["libraries"],
        *config["roles"]["tests"],
        *config["roles"]["experiments"],
        *config["roles"]["knowledge"],
        ".agent/skills",
        "project_memory/nodes",
        "project_memory/memory/shared",
        "project_memory/note",
        "project_memory/objectives",
    ]
    paths.extend(f"{root}/tests" for root in config["roles"]["experiments"])
    paths.extend(f"{root}/knowledge" for root in config["roles"]["knowledge"])
    return tuple(dict.fromkeys(paths))


def contract_links(config: dict) -> dict[str, str]:
    """Agent contract views for the configured semantic directories."""
    links = {
        "CLAUDE.md": ".claude/CLAUDE.md",
        "AGENTS.md": ".claude/CLAUDE.md",
        "project_memory/CLAUDE.md": "../.claude/project_memory-CLAUDE.md",
        "project_memory/AGENTS.md": "../.claude/project_memory-CLAUDE.md",
    }
    for root in config["roles"]["experiments"]:
        links[f"{root}/CLAUDE.md"] = "../.claude/experiments-CLAUDE.md"
        links[f"{root}/AGENTS.md"] = "../.claude/experiments-CLAUDE.md"
    for root in config["roles"]["knowledge"]:
        links[f"{root}/CLAUDE.md"] = "../.claude/wiki-CLAUDE.md"
        links[f"{root}/AGENTS.md"] = "../.claude/wiki-CLAUDE.md"
    return links


FEATURE_FLAGS = {
    "fixer": (("--with-fixer",), ("--no-fixer", "--without-fixer")),
    "hpc": (("--with-hpc",), ("--no-hpc", "--without-hpc")),
    "editor": (
        ("--with-editor", "--with-qdash"),
        ("--no-editor", "--without-editor", "--no-qdash"),
    ),
    "cross_agent": (
        ("--with-cross-agent",),
        ("--no-cross-agent", "--without-cross-agent"),
    ),
}


def feature_choices(argv: list[str], *, has_remote: bool = False) -> dict[str, bool]:
    """Translate setup flags into persistent project feature choices."""
    choices: dict[str, bool] = {}
    for name, (positive, negative) in FEATURE_FLAGS.items():
        enabled = any(flag in argv for flag in positive)
        disabled = any(flag in argv for flag in negative)
        if enabled and disabled:
            raise ConfigError(f"conflicting flags for {name}")
        if enabled or disabled:
            choices[name] = enabled
    if has_remote:
        if choices.get("hpc") is False:
            raise ConfigError("--remote cannot be combined with --no-hpc")
        choices["hpc"] = True
    return choices


def settings_text(*, hpc: bool) -> str:
    """Render the smallest settings file needed by the selected features."""
    settings = json.loads((TEMPLATES / "settings.json").read_text(encoding="utf-8"))
    if hpc:
        extra = json.loads(
            (TEMPLATES / "hpc-permissions.json").read_text(encoding="utf-8")
        )
        allowed = settings.setdefault("permissions", {}).setdefault("allow", [])
        allowed.extend(rule for rule in extra if rule not in allowed)
    return json.dumps(settings, indent=2) + "\n"


def fixer_processes(proj: Path) -> list[tuple[str, str]]:
    """Return fixer daemon processes whose command names this project."""
    found = subprocess.run(
        ["ps", "ax", "-o", "pid=", "-o", "command="],
        capture_output=True,
        text=True,
    )
    processes = []
    for line in found.stdout.splitlines():
        pid, _, command = line.strip().partition(" ")
        if pid.isdigit() and "lint_fixer_daemon" in command and str(proj) in command:
            processes.append((pid, command))
    return processes




def _cli_json(cmd: list[str], timeout: int = 120):
    """Run a CLI that speaks --json. Returns None for every failure mode.

    Absent binary, non-zero exit, a human line printed ahead of the JSON — all
    of them mean "this agent cannot answer", and none of them should abort a
    bootstrap whose real work is the project.
    """
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    out = r.stdout
    starts = [i for i in (out.find("{"), out.find("[")) if i >= 0]
    for text in (out, out[min(starts):] if starts else ""):
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _marketplaces(agent: str) -> list[dict]:
    """[{name, url, ref}] for one agent's configured marketplaces.

    The same three facts, two shapes: Claude emits a flat list carrying url and
    ref outright; Codex emits {marketplaces: [{name, root, marketplaceSource}]}
    with NO ref field at all — its ref is whatever the clone at `root` sits on,
    so it is read back from that clone.
    """
    if agent == "claude":
        rows = _cli_json(["claude", "plugin", "marketplace", "list", "--json"])
        return [{"name": m.get("name"), "url": m.get("url"), "ref": m.get("ref"),
                 "root": m.get("installLocation")}
                for m in (rows if isinstance(rows, list) else [])]
    out = _cli_json(["codex", "plugin", "marketplace", "list", "--json"])
    rows = out.get("marketplaces", []) if isinstance(out, dict) else []
    res = []
    for m in rows:
        ref, root = None, m.get("root")
        if root and Path(root).is_dir():
            g = subprocess.run(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"],
                               capture_output=True, text=True)
            ref = g.stdout.strip() or None
        res.append({"name": m.get("name"),
                    "url": (m.get("marketplaceSource") or {}).get("source"),
                    "ref": ref, "root": root})
    return res


def marketplace_head(root: str | None, ref: str | None) -> tuple:
    """(local HEAD, origin's HEAD for `ref`) of a marketplace clone.

    Either half is None when it cannot be established — not a git clone (a
    `github`-source marketplace is a tarball with no .git at all), no network,
    no such ref. The caller reports "unknown", never a false "in step".
    """
    if not root or not (Path(root) / ".git").exists():
        return None, None

    def sh(*args) -> str:
        try:
            r = subprocess.run(["git", "-C", root, *args],
                               capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return r.stdout.strip() if r.returncode == 0 else ""

    local = sh("rev-parse", "HEAD") or None
    ref = ref or sh("rev-parse", "--abbrev-ref", "HEAD") or None
    remote = sh("ls-remote", "origin", ref).split("\t")[0] if ref else ""
    return local, (remote or None)


def installed(agent: str) -> list[dict]:
    """[{id, version}] for what one agent has installed — id is plugin@marketplace.

    Shared with update_projects.sh, which imports this module rather than
    re-deriving two CLIs' JSON shapes in shell.
    """
    if agent == "claude":
        rows = _cli_json(["claude", "plugin", "list", "--json"])
        return [{"id": r.get("id", ""), "version": r.get("version", "")}
                for r in (rows if isinstance(rows, list) else [])]
    out = _cli_json(["codex", "plugin", "list", "--json"])
    rows = out.get("installed", []) if isinstance(out, dict) else []
    return [{"id": r.get("pluginId", ""), "version": r.get("version", "")}
            for r in rows]


def origin_agent() -> str | None:
    """The agent CLI this plugin was installed from — None off any cache.

    Off a cache means a dev checkout, where there is no marketplace to point
    the other agent at, so the cross-agent step has nothing to do.
    """
    return next((a for a, s in AGENT_CLIS.items()
                 if str(PLUGIN).startswith(str(s["home"]))), None)


def other_agent() -> str | None:
    """The agent CLI this plugin was NOT installed from, or None off a cache."""
    origin = origin_agent()
    return None if origin is None else ("codex" if origin == "claude" else "claude")


def sync_other_agent(dry: bool) -> None:
    """Register this plugin with the OTHER agent's CLI, so ONE setup serves both.

    The project side is already dual and has been for versions — AGENTS.md at
    every layer, memory/claude and memory/codex on one shared dir, both skill
    dirs on one .agent/skills. The MACHINE is not: each CLI keeps its own
    marketplace list and its own install pin, and neither reads the other's.
    So a project bootstrapped from Claude left Codex able to read every word of
    the doctrine and unable to run one step of it — measured on the machine
    this was written for: 12 skills in the Claude cache, 0 reachable by codex.

    Nothing here is fatal. A project with one agent installed is complete; the
    second agent is a convenience, and a machine without it just says `skip`.
    """
    origin, target = origin_agent(), other_agent()
    if target is None:
        say("skip", "other agent", "not running from an agent's plugin cache")
        return
    if not shutil.which(target):
        say("skip", target, f"no {target} CLI on this machine")
        return

    # <home>/cache/<marketplace>/<plugin>/<version> — PLUGIN is the version dir.
    plugin_name, mkt_name = PLUGIN.parent.name, PLUGIN.parent.parent.name
    already = [r["id"] for r in installed(target)
                if r["id"].split("@")[0] == plugin_name]
    if already:
        say("kept", f"{target}: {already[0]}")
        return

    src = next((m for m in _marketplaces(origin) if m.get("name") == mkt_name), None)
    if not src or not src.get("url"):
        say("WARN", f"{target}: {plugin_name}",
            f"cannot read marketplace `{mkt_name}` from the {origin} side")
        return
    url, ref = src["url"], src.get("ref")
    if dry:
        say("new", f"{target}: {plugin_name}",
            f"would add {url}" + (f" (ref {ref})" if ref else ""))
        return

    # stdin closed on purpose: a CLI that decides to ask something has nobody
    # to answer here, and a 900 s hang is a worse failure than a clean error.
    r = subprocess.run(AGENT_CLIS[target]["mkt_add"](url, ref),
                       capture_output=True, text=True, timeout=900,
                       stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        last = ((r.stderr or r.stdout).strip().splitlines() or ["add failed"])[-1]
        say("WARN", f"{target} marketplace", last[:160])
        return

    # The marketplace NAME belongs to the TARGET's manifest, not to ours. Both
    # of ours declare `rzchi` today, which is exactly why this must NOT be
    # spelled: when the two disagreed (`claude-setup` and `personal`) a
    # hardcoded name failed loudly on one side; now it would fail only on a
    # machine that added the marketplace from a fork or a local path under
    # another name — silently, since a selector matching nothing is not an
    # error. So the name is read back from the target, matched on the source URL.
    got = next((m for m in _marketplaces(target) if m.get("url") == url), None)
    if not got or not got.get("name"):
        say("WARN", f"{target} marketplace", f"added {url} but it reports no name")
        return
    sel = f"{plugin_name}@{got['name']}"
    r = subprocess.run(AGENT_CLIS[target]["install"](sel),
                       capture_output=True, text=True, timeout=900,
                       stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        last = ((r.stderr or r.stdout).strip().splitlines() or ["install failed"])[-1]
        say("WARN", f"{target}: {sel}", last[:160])
        return
    say("new", f"{target}: {sel}", f"from {url}" + (f" (ref {ref})" if ref else ""))


def say(state: str, what: str, detail: str = "") -> None:
    report.append((state, what, detail))
    print(f"  [{state:<4}] {what}{'  — ' + detail if detail else ''}")


def register_project(proj: Path, dry: bool) -> None:
    """Remember one framework root for agent-neutral bulk updates."""
    try:
        data = json.loads(PROJECT_REGISTRY.read_text(encoding="utf-8")) \
            if PROJECT_REGISTRY.exists() else {"projects": []}
    except (OSError, json.JSONDecodeError, ValueError):
        data = {"projects": []}
    projects = sorted({str(Path(p).resolve()) for p in data.get("projects", [])}
                      | {str(proj.resolve())})
    if data.get("projects") == projects:
        say("kept", "project registry", str(PROJECT_REGISTRY))
        return
    if not dry:
        PROJECT_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        tmp = PROJECT_REGISTRY.with_suffix(".tmp")
        tmp.write_text(json.dumps({"projects": projects}, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(PROJECT_REGISTRY)
    say("new", "project registry", str(PROJECT_REGISTRY))


def main() -> int:
    argv = sys.argv[1:]
    # --remote HOST:DIR is repeatable: the FIRST occurrence is the default host
    # (back-compat REMOTE_HOST/REMOTE_DIR); every occurrence lands in the
    # multi-remote keys (REMOTE_HOSTS + REMOTE_DIR_<host>) when there is more
    # than one. All declared hosts are set up and monitored equally.
    remote_specs: list[tuple[str, str]] = []
    while "--remote" in argv:
        i = argv.index("--remote")
        spec = argv[i + 1] if i + 1 < len(argv) else None
        if not spec or ":" not in spec:
            print("bootstrap: --remote wants HOST:DIR", file=sys.stderr)
            return 2
        host, _, rdir = spec.partition(":")
        remote_specs.append((host, rdir))
        argv = argv[:i] + argv[i + 2:]
    try:
        requested_features = feature_choices(sys.argv[1:], has_remote=bool(remote_specs))
    except ConfigError as exc:
        print(f"bootstrap: {exc}", file=sys.stderr)
        return 2
    args = [a for a in argv if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    proj = Path(args[0]).resolve() if args else Path.cwd().resolve()
    print(f"bootstrap: {proj}" + ("  (DRY RUN — nothing is written)" if dry else ""))
    if not proj.is_dir():
        print(f"bootstrap: {proj} is not a directory", file=sys.stderr)
        return 2

    # Read this before the template loop creates .claude/framework.json. A
    # pre-schema project already had every integration enabled by default, so
    # its first project.json must preserve that behaviour. A new project starts
    # from the smaller core and opts into integrations explicitly.
    config_path = proj / CONFIG_PATH
    legacy_without_config = needs_legacy_config(proj)
    try:
        base_config = (
            load_project_config(proj, legacy_if_missing=False)
            if config_path.exists()
            else initial_project_config(legacy=legacy_without_config)
        )
        project_config = with_feature_choices(base_config, requested_features)
    except ConfigError as exc:
        say("FAIL", str(CONFIG_PATH), str(exc))
        return 2

    def w(path: Path, text: str, label: str) -> None:
        """Write only when absent — an existing file is the user's."""
        if path.exists():
            say("kept", label)
            return
        if not dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        say("new", label)

    print("\n· layout")
    # core runtime state (the record lock, the harvest stamps) lives under
    # .research-note/state/ and never in a commit; the nested ignore is what
    # keeps it out, so it is laid with the layout
    w(proj / ".research-note" / ".gitignore", "state/\n", ".research-note/.gitignore")
    for d in layout_dirs(project_config):
        p = proj / d
        if p.is_dir():
            say("kept", d)
        else:
            if not dry:
                p.mkdir(parents=True, exist_ok=True)
            say("new", d)

    print("\n· agent-neutral project registry")
    register_project(proj, dry)

    print("\n· git")
    if (proj / ".git").exists():
        say("kept", ".git")
    elif dry:
        say("new", ".git", "git init")
    else:
        subprocess.run(["git", "init", "-q", str(proj)], check=False)
        say("new" if (proj / ".git").exists() else "FAIL", ".git", "git init")

    print("\n· project bindings (.claude/)")
    for src, dst in FILES.items():
        t = TEMPLATES / src
        if not t.exists():
            say("FAIL", dst, f"template missing: {t}")
            continue
        w(proj / dst, t.read_text(encoding="utf-8"), dst)
    # the contracts: framework template + .research-note/rules/<x>.md, generated;
    # an appendix under the old boundary block is carried into the rules file
    contracts.sync(proj, PLUGIN, dry=dry, say=say)
    if config_path.exists():
        if project_config == base_config:
            say("kept", str(CONFIG_PATH))
        else:
            if not dry:
                write_project_config(proj, project_config)
            changed = ", ".join(
                f"{name}={'on' if value else 'off'}"
                for name, value in requested_features.items()
            )
            say("ok", str(CONFIG_PATH), changed)
    else:
        if not dry:
            write_project_config(proj, project_config)
        say("new", str(CONFIG_PATH))

    settings_path = proj / ".claude/settings.json"
    if not settings_path.exists():
        w(
            settings_path,
            settings_text(hpc=feature_enabled(project_config, "hpc")),
            ".claude/settings.json",
        )
    elif feature_enabled(project_config, "hpc"):
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            extra = json.loads(
                (TEMPLATES / "hpc-permissions.json").read_text(encoding="utf-8")
            )
            allowed = settings.setdefault("permissions", {}).setdefault("allow", [])
            missing = [rule for rule in extra if rule not in allowed]
            if missing and not dry:
                allowed.extend(missing)
                settings_path.write_text(
                    json.dumps(settings, indent=2) + "\n", encoding="utf-8"
                )
            say(
                "ok" if missing else "kept",
                ".claude/settings.json",
                f"added {len(missing)} HPC permission(s)" if missing else "",
            )
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            say("WARN", ".claude/settings.json", f"cannot merge HPC permissions: {exc}")
    else:
        say("kept", ".claude/settings.json")

    if feature_enabled(project_config, "hpc"):
        hpc_template = TEMPLATES / "hpc.env"
        w(
            proj / ".claude/hpc.env",
            hpc_template.read_text(encoding="utf-8"),
            ".claude/hpc.env",
        )
    else:
        say("skip", ".claude/hpc.env", "HPC is disabled")

    print("\n· page templates (.claude/examples/)")
    for ex in sorted((TEMPLATES.parent / "design").glob("*-template.md")):
        w(proj / ".claude" / "examples" / ex.name,
          ex.read_text(encoding="utf-8"), f".claude/examples/{ex.name}")

    print("\n· contract views (symlinks)")
    for link, target in contract_links(project_config).items():
        p = proj / link
        if p.is_symlink() or p.exists():
            state = "kept" if (p.exists() or p.is_symlink()) else "new"
            broken = p.is_symlink() and not p.exists()
            say("WARN" if broken else state, link,
                "dangling symlink — repoint it by hand" if broken else "")
            continue
        if not dry:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.symlink_to(target)
        say("new", link, f"-> {target}")

    print("\n· shared agent memory")
    memory_root = proj / "project_memory" / "memory"
    for agent in ("claude", "codex"):
        link = memory_root / agent
        if link.exists() or link.is_symlink():
            say("kept", f"project_memory/memory/{agent}")
            continue
        if not dry:
            link.symlink_to("shared", target_is_directory=True)
        say("new", f"project_memory/memory/{agent}", "-> shared")

    print("\n· shared project skills")
    for rel, target in SKILL_LINKS.items():
        link = proj / rel
        if link.is_symlink():
            correct = os.readlink(link) == target and link.exists()
            if correct:
                say("kept", rel)
                continue
            if not dry:
                link.unlink()
                link.symlink_to(target, target_is_directory=True)
            say("ok", rel, f"repointed -> {target}")
            continue
        if link.exists():
            say("kept", rel)
            continue
        if not dry:
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target, target_is_directory=True)
        say("new", rel, f"-> {target}")

    print("\n· submit templates (project-owned copies)")
    # The plugin's .slurm templates are pristine and generic; a PROJECT fills its
    # copies once (partition, gres/GPU types, module loads) and per-experiment
    # scripts are then instantiated from the PROJECT copies, never the plugin's.
    st_src = PLUGIN / "skills" / "hpc-submit" / "scripts"
    st_dst = proj / ".claude" / "hpc-submit"
    # Only the *.slurm TEMPLATES are the project's (you fill partition/gres for
    # YOUR cluster). launch_bare_gpu.sh is framework code invoked from the
    # plugin: a copy here goes stale on every plugin update and, sitting one
    # level shallower than the plugin layout, used to resolve its helper to a
    # path outside the repo.
    if not feature_enabled(project_config, "hpc"):
        say("skip", ".claude/hpc-submit", "HPC is disabled")
    elif not st_src.exists():
        say("WARN", ".claude/hpc-submit", "plugin ships no submit templates")
    elif st_dst.exists():
        stray = st_dst / "launch_bare_gpu.sh"
        if stray.exists():
            say("WARN", ".claude/hpc-submit/launch_bare_gpu.sh",
                "framework code, not a template — delete it and call the plugin's")
        else:
            say("kept", ".claude/hpc-submit")
    else:
        if not dry:
            st_dst.mkdir(parents=True, exist_ok=True)
            for f in sorted(st_src.glob("*.slurm")):
                shutil.copy2(f, st_dst / f.name)
        say("new", ".claude/hpc-submit", "fill partition/gres for YOUR cluster")

    print("\n· githooks (dispatcher: research-note's gates, then the hooks that were there)")
    if (PLUGIN / "githooks" / "dispatch").is_file():
        githooks_install.install(proj, PLUGIN, dry=dry, say=say)
    else:
        say("WARN", ".claude/githooks", "not shipped by this plugin version")
    if not dry:
        subprocess.run(["git", "-C", str(proj), "config", "research-note.pluginRoot",
                        str(PLUGIN)], check=False)
        say("ok", "research-note.pluginRoot", str(PLUGIN))

    print("\n· auto-memory + gitignore")
    slp = proj / ".claude" / "settings.local.json"
    mem = str(proj / "project_memory" / "memory" / "shared")
    local = json.loads(slp.read_text(encoding="utf-8")) if slp.exists() else {}
    if local.get("autoMemoryDirectory") == mem:
        say("kept", ".claude/settings.local.json")
    else:
        local["autoMemoryDirectory"] = mem
        if not dry:
            slp.parent.mkdir(parents=True, exist_ok=True)
            slp.write_text(json.dumps(local, indent=2) + "\n", encoding="utf-8")
        say("new", ".claude/settings.local.json", "autoMemoryDirectory")
    gi = proj / ".gitignore"
    if gi.exists():
        # An existing .gitignore is PROJECT property: its exclusion policy may
        # deliberately diverge from the template (e.g. a repo that TRACKS run
        # logs + cell JSON as record evidence, excluding by weight instead of
        # by folder). Re-appending template lines the project removed silently
        # un-tracks new evidence — so an existing file is never touched.
        say("kept", ".gitignore", "project-owned; template lines not enforced")
    else:
        if not dry:
            lines = gitignore_lines(project_config)
            gi.write_text("# framework runtime + build artifacts\n"
                          + "\n".join(lines) + "\n", encoding="utf-8")
        say("new", ".gitignore", f"{len(gitignore_lines(project_config))} line(s)")

    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(proj),
           "RESEARCH_NOTE_PROJECT_DIR": str(proj)}

    print("\n· generated artifacts")
    for script, label in (("gen_index.py", "project_memory/_index.md"),
                          ("gen_dashboard.py", "project_memory/dashboard.html")):
        if dry:
            say("new", label, f"would run {script}")
            continue
        r = subprocess.run([sys.executable, str(HERE / script)],
                           capture_output=True, text=True, cwd=proj, env=env)
        say("ok" if r.returncode == 0 else "FAIL", label,
            "" if r.returncode == 0 else (r.stderr.strip().splitlines() or [""])[-1])

    print("\n· fixer (headless scan + board refresh)")
    # ONE mechanism, and it is the daemon.
    #
    # Earlier versions installed BOTH a cron line and a daemon on every
    # bootstrap. Two schedulers for one job is one too many — they serialize on
    # the same .fixer/lock, so the second only ever wins the race, never does
    # more work — and the cron half is the invasive half: it writes the user's
    # crontab, a global facility shared with every other tool on the host, for
    # what is one project's concern. On the machine this was written for it came
    # to six schedulers for three projects.
    #
    # The daemon is the one worth keeping. It writes nothing outside .fixer/,
    # `kill` is the whole uninstall, and it is one code path on both platforms —
    # crontab(1) on darwin is TCC-gated, its first use blocking on a GUI consent
    # prompt a headless bootstrap can never answer, which is why the cron branch
    # needed a platform special-case at all. Its one weakness, not surviving a
    # reboot, is the weakness doctor already reports: a .fixer/last_run older
    # than thirty minutes is a hard finding, so the gap is visible rather than
    # silent. fixer/register_cron.sh stays in the tree for anyone who wants
    # reboot survival and knows they want it.
    #
    # When enabled, a whole-record scan catches what the write-time gates cannot see
    # — a job that died, a src/ file renamed under a page's links, a follow-up
    # that never joined a plan — none of which touch the page they invalidate.
    # It runs python and nothing else: both agent tiers are disabled in
    # config.json and prompt_analyze.md does not exist, so no LLM is ever
    # invoked; the cycle lints, stamps `attention:`, refreshes the board, and
    # takes one ssh for the remote queue snapshot.
    if not feature_enabled(project_config, "fixer"):
        running = fixer_processes(proj) if not dry else []
        for pid, _command in running:
            subprocess.run(["pkill", "-P", pid], check=False)
            subprocess.run(["kill", pid], check=False)
        detail = (
            f"disabled; stopped {len(running)} daemon(s)"
            if running else "disabled in .research-note/project.json"
        )
        say("skip", "fixer", detail)
    elif dry:
        say("new", "fixer", "daemon (10 min)")
    else:
        # A daemon launched from an OLDER plugin version keeps exec'ing that
        # version's code, so a re-run after an update doubles as the upgrade's
        # finishing move: stop a daemon whose loop points anywhere but this
        # project's stub, then (re)start. Its own flock makes a healthy daemon
        # a no-op ("already running").
        # ps, not pgrep: macOS pgrep has no -a, and `ps ax -o` is the one
        # spelling procps and BSD both accept.
        for pid, command in fixer_processes(proj):
            if f"{proj}/.fixer/run.sh" not in command:
                subprocess.run(["pkill", "-P", pid], check=False)
                subprocess.run(["kill", pid], check=False)
                say("ok", "stopped stale fixer daemon", f"pid {pid} (pre-upgrade path)")
                time.sleep(1.5)
        r = subprocess.run(["bash", str(PLUGIN / "fixer" / "start_fixer_daemon.sh"),
                            str(proj)], capture_output=True, text=True)
        say("ok" if r.returncode == 0 else "FAIL", "fixer daemon",
            (r.stdout.strip().splitlines() or [""])[-1] if r.returncode == 0
            else r.stderr.strip()[:200])

    print("\n· remote HPC")
    if remote_specs:
        host, rdir = remote_specs[0]        # first --remote = the default host
        envf = proj / ".claude" / "hpc.env"
        have = envf.read_text(encoding="utf-8") if envf.exists() else ""
        import re as _re
        if _re.search(r"^\s*REMOTE_HOST=", have, _re.M):
            say("kept", "hpc.env remote keys")
        else:
            if not dry:
                with open(envf, "a", encoding="utf-8") as f:
                    f.write(f"\nREMOTE_HOST={host}\nREMOTE_DIR={rdir}\n"
                            f"REMOTE_DATA_MAX_MB=50\n")
                    if len(remote_specs) > 1:
                        # multi-remote contract: ALL hosts, monitored equally —
                        # REMOTE_HOST above is only the default when unstated
                        f.write('REMOTE_HOSTS="'
                                + " ".join(h for h, _ in remote_specs) + '"\n')
                        for h, d in remote_specs:
                            f.write(f"REMOTE_DIR_{_re.sub(r'[^A-Za-z0-9_]', '_', h)}"
                                    f"={d}\n")
            say("new", "hpc.env remote keys",
                ", ".join(f"{h}:{d}" for h, d in remote_specs))
        # remote.sh setup per host: fresh clones come up SPARSE (cone: src/
        # tests/ experiments/ + root files — never project_memory/, wiki/ or
        # .claude/), with remote.sh carrying the old-git (1.8.x) fallback:
        # core.sparseCheckout + .git/info/sparse-checkout patterns and a
        # `/*` + `!/src`-style .git/info/exclude to keep `status` clean.
        for h, _d in remote_specs:
            if dry:
                say("new", f"remote clone ({h})",
                    "would run remote.sh setup --host " + h
                    + " (sparse cone: src/ tests/ experiments/)")
                continue
            r = subprocess.run(["bash", str(HERE / "remote.sh"),
                                "setup", "--host", h],
                               capture_output=True, text=True, env=env,
                               timeout=300)
            say("ok" if r.returncode == 0 else "FAIL", f"remote.sh setup ({h})",
                (r.stdout.strip().splitlines() or [""])[-1] if r.returncode == 0
                else (r.stderr.strip() or r.stdout.strip())[:200])
    elif feature_enabled(project_config, "hpc"):
        envf = proj / ".claude" / "hpc.env"
        if envf.exists() and "REMOTE_HOST=" in envf.read_text(encoding="utf-8").replace("#REMOTE_HOST=", ""):
            say("kept", "remote HPC (declared in hpc.env)")
        else:
            say("skip", "remote HPC", "none declared (--remote HOST:DIR to add one)")
    else:
        say("skip", "remote HPC", "disabled in .research-note/project.json")

    print("\n· editor extensions (VS Code)")
    # BOTH dirs can exist on one machine: a local Mac that has ever run the
    # `code` CLI/tunnel grows an (empty) ~/.vscode-server/extensions, while its
    # real window still reads ~/.vscode/extensions. Picking the first one that
    # exists then installs into the dir nobody reads — and prints `ok`, so the
    # board silently never appears. Install into every dir that exists instead:
    # a window reads exactly one of them, so the spare copy is inert and the
    # commands are never double-registered.
    ext_roots = [d for d in (Path.home() / ".vscode-server" / "extensions",
                             Path.home() / ".vscode" / "extensions") if d.is_dir()]
    if not feature_enabled(project_config, "editor"):
        say("skip", "editor extensions", "disabled in .research-note/project.json")
    elif not ext_roots:
        say("skip", "editor extensions",
            "no ~/.vscode-server or ~/.vscode extensions dir (no VS Code here)")
    else:
        for src_name, folder, label in EDITOR_EXTENSIONS:
            src = PLUGIN / "editor" / src_name
            if not src.is_dir():
                say("WARN", label, "not shipped by this plugin version")
                continue
            # A VS Code extension cannot be installed by a Claude Code plugin (two
            # different extension systems), so it is copied in. Overwritten on every
            # run — unlike project files, this is a pure copy of plugin code with no
            # user edits to lose, and a stale copy is exactly what breaks the board.
            dsts = []
            for ext_root in ext_roots:
                dst = ext_root / folder
                if not dry:
                    dst.mkdir(parents=True, exist_ok=True)
                    for f in src.iterdir():
                        shutil.copy2(f, dst / f.name)
                dsts.append(str(dst))
            say("ok", label, f"{', '.join(dsts)} — RELOAD WINDOW once to load it")

    print("\n· the other agent's plugin registry")
    if not feature_enabled(project_config, "cross_agent"):
        say("skip", "other agent", "disabled in .research-note/project.json")
    else:
        sync_other_agent(dry)

    print("\n· acceptance gate")
    if "--no-self-tests" in sys.argv:
        # the plugin's own suite takes a minute; a caller that has just run it
        # (the compatibility matrix, a CI job) skips it here and keeps the linters
        say("skip", "framework self-tests", "--no-self-tests")
    else:
        r = subprocess.run([sys.executable, "-m", "pytest", str(HERE / "tests"), "-q"],
                           capture_output=True, text=True, cwd=proj, env=env)
        if r.returncode == 0:
            say("ok", "framework self-tests")
        elif "No module named pytest" in (r.stderr + r.stdout):
            say("skip", "framework self-tests", "pytest not installed")
        else:
            say("FAIL", "framework self-tests", (r.stdout.strip().splitlines() or [""])[-1])
    for script in ("check_node_page.py", "check_objective_page.py"):
        r = subprocess.run([sys.executable, str(HERE / script), "--quiet"],
                           capture_output=True, text=True, cwd=proj, env=env)
        say("ok" if r.returncode == 0 else "FAIL", script,
            "" if r.returncode == 0 else (r.stdout + r.stderr).strip()[:200])

    bad = [f"{w} ({d})" if d else w for s, w, d in report if s in ("FAIL", "WARN")]
    print(f"\nbootstrap: {sum(1 for s, _, _ in report if s == 'new')} created, "
          f"{sum(1 for s, _, _ in report if s == 'kept')} kept, "
          f"{len(bad)} needing attention")
    if bad:
        print("  needs attention: " + "; ".join(bad))
    print("\nNext (the judgment calls this script deliberately leaves to you):\n"
          "  1. .claude/hpc.env — DOMAIN_LIBS if a domain library's SHA belongs\n"
          "     in log headers\n"
          "  2. pyproject.toml — pin the env however this project prefers\n"
          "     (see the project-setup skill)\n"
          "  3. Reload Window in VS Code, then: Open Q Dashboard\n"
          "  4. Run the plugin's scripts/doctor.sh — it verifies every wire this\n"
          "     script laid (and every one it could not), and prints the fix for\n"
          "     whatever is not yet true")
    return 1 if any(s == "FAIL" for s, _, _ in report) else 0


if __name__ == "__main__":
    sys.exit(main())
