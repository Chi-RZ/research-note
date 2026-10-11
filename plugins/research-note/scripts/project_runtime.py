#!/usr/bin/env python3
"""Select a project release; share immutable installations across projects.

Project locks and settings select a release, never the highest cache version.
Native hosts keep their own caches; their user-level enablement is unchanged.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

LOCK = Path(".research-note/plugin-lock.json")
RUNTIME = Path(".research-note/runtime")
BEGIN = "# BEGIN research-note project runtime"
END = "# END research-note project runtime"
SELECTOR_RE = re.compile(r"research-note@[A-Za-z0-9_.-]+")
EXCLUDED = {"__pycache__", ".pytest_cache", ".git", "tests", ".in_use"}


def release_store() -> Path:
    override = os.environ.get("RESEARCH_NOTE_RELEASE_STORE")
    data = Path(os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share"))
    return (Path(override) if override else data / "research-note/releases").resolve()


def pin_root(project: Path, pin: dict) -> Path:
    sha = pin.get("sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("invalid plugin lock digest")
    if pin.get("schema") == 2:
        if pin.get("runtime") != f"{sha}/plugins/research-note":
            raise ValueError("invalid shared release path in plugin lock")
        if pin.get("marketplace") != f"rn-release-{sha}" or pin.get("selector") != f"research-note@rn-release-{sha}":
            raise ValueError("shared release identity differs from plugin lock digest")
        return release_store() / sha / "plugins/research-note"
    if pin.get("schema") != 1:
        raise ValueError("unsupported plugin lock schema")
    return project / RUNTIME / sha / "plugins/research-note"


def shared_capable(source: Path) -> bool:
    """The release must be able to read its own schema-2 lock after loading."""
    script = source / "scripts/project_runtime.py"
    return script.is_file() and "def release_store(" in script.read_text(encoding="utf-8")


def git(project: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", "-C", str(project), *args], check=check,
                          capture_output=True, text=True).stdout.strip()


def main_project(project: Path) -> Path:
    """A worktree shares its main checkout's record and installation."""
    common = git(project, "rev-parse", "--path-format=absolute", "--git-common-dir", check=False)
    if common and Path(common).name == ".git":
        return Path(common).resolve().parent
    return project.resolve()


def json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write(path: Path, text: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    if path.is_symlink():
        raise ValueError(f"refusing to replace a configuration symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     delete=False) as tmp:
        tmp.write(text)
    os.replace(tmp.name, path)


def write_json(path: Path, value: dict) -> None:
    write(path, json.dumps(value, indent=2, ensure_ascii=True) + "\n")


def payload(root: Path, legacy: bool = False):
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        excluded = EXCLUDED - {".in_use"} if legacy else EXCLUDED
        if any(part in excluded for part in rel.parts) or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"plugin snapshot cannot contain symlinks: {rel}")
        if path.is_file():
            yield path, rel


def digest(root: Path, legacy: bool = False) -> str:
    h = hashlib.sha256()
    for path, rel in payload(root, legacy):
        h.update(str(rel).encode() + b"\0")
        h.update(str(path.stat().st_mode & 0o111).encode() + b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def snapshot(project: Path, source: Path) -> dict:
    source = source.resolve()
    manifest = json_file(source / ".codex-plugin/plugin.json")
    if manifest.get("name") != "research-note" or not manifest.get("version"):
        raise ValueError("source is not a versioned research-note plugin")
    content = digest(source)
    claude_manifest = json_file(source / ".claude-plugin/plugin.json")
    if claude_manifest.get("version") != manifest["version"]:
        raise ValueError("Claude and Codex manifest versions differ")
    release = release_store() / content
    target = release / "plugins/research-note"
    if not target.exists():
        release.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=release.parent) as tmp:
            staged = Path(tmp) / "release"
            for path, rel in payload(source):
                dst = staged / "plugins/research-note" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dst)
            if digest(staged / "plugins/research-note") != content:
                raise ValueError("plugin source changed during snapshot")
            # Concurrent projects may install exactly the same release.
            try:
                staged.rename(release)
            except OSError:
                if not target.is_dir() or digest(target) != content:
                    raise
    if digest(target) != content:
        raise ValueError("snapshot digest mismatch; restore the pinned release")
    marketplace = f"rn-release-{content}"
    catalog = {"name": marketplace, "description": "Shared immutable research-note release",
               "owner": {"name": "research-note"},
               "plugins": [{"name": "research-note", "source": "./plugins/research-note"}]}
    write_json(release / ".claude-plugin/marketplace.json", catalog)
    catalog["plugins"][0].update({"source": {"source": "local", "path": "./plugins/research-note"},
                                 "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                                 "category": "Productivity"})
    write_json(release / ".agents/plugins/marketplace.json", catalog)
    # A host cache need not retain Git metadata. The content digest is always
    # authoritative; a source commit is additional provenance when available.
    provenance = json_file(source.parents[1] / "provenance.json")
    if not provenance:
        provenance = {"source_commit": git(source, "rev-parse", "HEAD", check=False) or None,
                      "source_branch": git(source, "symbolic-ref", "--short", "-q", "HEAD", check=False) or None,
                      "source_dirty": bool(git(source, "status", "--porcelain", "--", ".", check=False))}
    if not (release / "provenance.json").exists():
        write_json(release / "provenance.json", provenance)
    return {"schema": 2, "version": manifest["version"], "sha256": content,
            **provenance, "runtime": f"{content}/plugins/research-note",
            "marketplace": marketplace, "selector": f"research-note@{marketplace}"}


def locked_root(project: Path) -> Path | None:
    project = main_project(project)
    pin = json_file(project / LOCK)
    if not pin:
        return None
    root = pin_root(project, pin)
    if not root.is_dir() or digest(root, legacy=pin.get("schema") == 1) != pin["sha256"]:
        raise ValueError("pinned runtime missing or digest mismatch; restore it before continuing")
    return root


def runtime_snapshots(project: Path) -> set[str]:
    """Return complete snapshot directory names owned by this project."""
    root = project / RUNTIME
    if not root.is_dir():
        return set()
    return {path.name for path in root.iterdir()
            if re.fullmatch(r"[0-9a-f]{64}", path.name) and
            (path.is_dir() or path.is_symlink())}


def prune_runtime(project: Path, keep: set[str]) -> list[str]:
    """Remove project snapshots outside ``keep``; host caches are host-owned."""
    root = project / RUNTIME
    removed = []
    for name in sorted(runtime_snapshots(project) - keep):
        path = root / name
        if path.is_symlink() or path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
        removed.append(name)
    return removed


def prune_locked_runtime(project: Path) -> list[str]:
    """Under the install lock, retain only the snapshot selected right now."""
    from project_config import state_dir
    state = state_dir(project)
    with (state / "install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pin = json_file(project / LOCK)
        sha = pin.get("sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("cannot prune project runtime without a valid plugin lock")
        # Shared releases can be selected by projects outside this checkout.
        # Never prune them as a side effect of a project update.
        return prune_runtime(project, {sha} if pin.get("schema") == 1 else set())


def codex_text(original: str, selector: str, marketplace: str, release: Path,
               disabled: set[str]) -> str:
    """Preserve user TOML text; own one block and only existing enable values.

    No TOML writer dependency on Python 3.10. Nonstandard inline/dotted plugin
    definitions are refused instead of risking duplicate keys or losing policy.
    """
    text = re.sub(rf"(?ms)^{re.escape(BEGIN)}\n.*?^{re.escape(END)}\n?", "", original)
    sections = re.split(r"(?m)(?=^\s*\[)", text)
    existing = set()
    out = []
    for section in sections:
        head = re.match(r'''\s*\[plugins\.(["'])(research-note@[A-Za-z0-9_.-]+)\1\]\s*(?:#[^\n]*)?\n''', section)
        if head:
            key = head.group(2)
            existing.add(key)
            body = section[head.end():]
            value = "true" if key == selector else "false"
            if re.search(r"(?m)^\s*enabled\s*=", body):
                body = re.sub(r"(?m)^(\s*enabled\s*=\s*)(true|false)(\s*(?:#.*)?)$",
                              lambda m: m.group(1) + value + m.group(3), body)
            else:
                body = f"enabled = {value}\n" + body
            section = section[:head.end()] + body
        elif (SELECTOR_RE.search(section)
              and (re.match(r"\s*\[plugins(?:\.|\])", section)
                   or re.search(r"(?m)^\s*plugins\s*[.=]", section))
              and not re.match(r'''\s*\[plugins\.["']research-note@[^"']+["']\.\w+''', section)):
            # Comments mentioning a selector are harmless.
            if any(SELECTOR_RE.search(line) for line in section.splitlines()
                   if line.strip() and not line.lstrip().startswith("#")):
                raise ValueError("use [plugins.\"research-note@marketplace\"] tables in Codex config before pinning")
        out.append(section)
    text = "".join(out).rstrip() + "\n\n" + BEGIN + "\n"
    for key in sorted((disabled | {selector}) - existing):
        text += f"[plugins.{json.dumps(key)}]\nenabled = {'true' if key == selector else 'false'}\n"
    text += (f"[marketplaces.{json.dumps(marketplace)}]\nsource_type = \"local\"\n"
             f"source = {json.dumps(str(release))}\n{END}\n")
    try:
        import tomllib
    except ImportError:
        pass
    else:
        tomllib.loads(text)
    return text


def activate(project: Path, pin: dict) -> None:
    """Write only THIS project's selectors; never install or enable globally."""
    root = pin_root(project, pin)
    if digest(root) != pin["sha256"]:
        raise ValueError("snapshot digest mismatch")
    release = root.parents[1]
    paths = [project / ".claude/settings.json", project / ".claude/settings.local.json"]
    settings = [json_file(p) for p in paths]
    selector, market = pin["selector"], pin["marketplace"]
    disabled = {"research-note@research-tools", "research-note@inline", "research-note@skills-dir"}
    texts = []
    claude_home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude"))
    codex_home = Path(os.environ.get("CODEX_HOME") or str(Path.home() / ".codex"))
    registry = json_file(claude_home / "plugins/installed_plugins.json")
    for key, rows in registry.get("plugins", {}).items():
        if key.startswith("research-note@") and any(not row.get("projectPath") or
                row.get("scope") == "user" or row.get("projectPath") == str(project) for row in rows):
            disabled.add(key)
    for path in [claude_home / "settings.json", claude_home / "settings.local.json", codex_home / "config.toml",
                 project / ".codex/config.toml", *paths]:
        if path.is_file():
            texts.append(path.read_text(encoding="utf-8"))
    for text in texts:
        disabled.update(SELECTOR_RE.findall(text))
    disabled.discard(selector)
    for config in settings:
        enabled = config.setdefault("enabledPlugins", {})
        enabled.update({key: False for key in sorted(disabled)})
        enabled[selector] = True
        # Drop only OUR old immutable marketplace declarations in this project.
        extra = config.get("extraKnownMarketplaces", {})
        for key in list(extra):
            if re.fullmatch(r"rn-(?:[0-9a-f]{12}-[0-9a-f]{16}|release-[0-9a-f]{64})", key):
                del extra[key]
    settings[1].setdefault("extraKnownMarketplaces", {})[market] = {
        "source": {"source": "directory", "path": str(release)}, "autoUpdate": False}
    codex = project / ".codex/config.toml"
    text = codex_text(codex.read_text() if codex.exists() else "", selector, market, release, disabled)
    for path, config in zip(paths, settings):
        write_json(path, config)
    write(codex, text)
    ignore = project / ".research-note/.gitignore"
    ignore_text = ignore.read_text() if ignore.exists() else "state/\n"
    lines = ignore_text.splitlines()
    for local_path in ("runtime/", "editables/", "editables.env"):
        if local_path not in lines:
            lines.append(local_path)
    write(ignore, "\n".join(lines) + "\n")
    git(project, "config", "research-note.pluginRoot", str(root))
    write_json(project / LOCK, pin)


def check(project: Path) -> list[str]:
    project = main_project(project)
    try:
        root = locked_root(project)
        if root is None:
            return ["project has no plugin lock"]
        pin = json_file(project / LOCK)
        if json_file(root / ".codex-plugin/plugin.json").get("version") != pin.get("version"):
            raise ValueError("installed version differs from project lock")
        selector = pin["selector"]
        release = root.parents[1]
        market = pin["marketplace"]
        for rel in (".claude/settings.json", ".claude/settings.local.json"):
            enabled = json_file(project / rel).get("enabledPlugins", {})
            if enabled.get(selector) is not True or any(v and k != selector for k, v in enabled.items() if k.startswith("research-note@")):
                raise ValueError(f"{rel}: research-note selector differs from lock")
        declaration = json_file(project / ".claude/settings.local.json").get("extraKnownMarketplaces", {}).get(market, {})
        if declaration.get("source") != {"source": "directory", "path": str(release)}:
            raise ValueError("Claude marketplace source differs from lock")
        codex = (project / ".codex/config.toml").read_text()
        if f'[plugins.{json.dumps(selector)}]\nenabled = true' not in codex:
            raise ValueError("Codex plugin selector differs from lock")
        if f'source = {json.dumps(str(release))}' not in codex:
            raise ValueError("Codex marketplace source differs from lock")
        for rel in (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json"):
            catalog = json_file(release / rel)
            if catalog.get("name") != market:
                raise ValueError(f"{rel}: marketplace identity differs from lock")
            entry = catalog.get("plugins", [{}])[0]
            expected = "./plugins/research-note"
            if entry.get("source") not in (expected, {"source": "local", "path": expected}):
                raise ValueError(f"{rel}: plugin source differs from lock")
        if git(project, "config", "--get", "research-note.pluginRoot", check=False) != str(root):
            raise ValueError("script binding differs from plugin lock")
        return []
    except (OSError, ValueError, KeyError) as exc:
        return [str(exc)]


def restore(project: Path, source: Path) -> None:
    """Recreate a clone/move's local bindings without upgrading its content."""
    project = main_project(project)
    pin = json_file(project / LOCK)
    if not pin:
        raise ValueError("project has no lock to restore")
    existing = pin_root(project, pin)
    candidate = existing if existing.is_dir() else source
    if digest(candidate, legacy=pin.get("schema") == 1) != pin["sha256"]:
        raise ValueError("restore needs --source with the locked content digest; it never upgrades")
    if not shared_capable(candidate):
        if pin.get("schema") != 1:
            raise ValueError("locked source predates shared installations; cannot restore a schema-2 selection")
        # Preserve a private legacy installation rather than giving its old
        # scripts a lock they cannot read. Explicit update performs migration.
        subprocess.run([sys.executable, "-B", str(candidate / "scripts/project_runtime.py"),
                        "restore", "--source", str(candidate), str(project)], check=True)
        return
    with transaction(project):
        restored = snapshot(project, candidate)
        restored.update({k: pin.get(k) for k in ("source_commit", "source_branch", "source_dirty")})
        activate(project, restored)
        from host_install import sync_hosts
        sync_hosts(project, restored, pin_root(project, restored))
    prune_locked_runtime(project)
    print("restored both project bindings without changing the pinned content")


@contextmanager
def transaction(project: Path):
    """Restore managed files and discard snapshots staged by a failed write."""
    from project_config import state_dir
    state = state_dir(project)
    with (state / "install.lock").open("a") as lock, (state / "record.lock").open("a") as record_lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        fcntl.flock(record_lock, fcntl.LOCK_EX)
        snapshots_before = runtime_snapshots(project)
        paths = [project / ".claude", project / ".codex/config.toml", project / LOCK,
                 project / ".research-note/project.json", project / ".research-note/.gitignore",
                 project / ".research-note/state/host-install.json"]
        from project_config import load_project_config, contract_views
        paths += [project / view for views in contract_views(load_project_config(project)).values()
                  for view in views if not view.startswith(".claude/")]
        common = git(project, "rev-parse", "--path-format=absolute", "--git-common-dir")
        paths += [Path(common) / "config", Path(common) / "hooks"]
        with tempfile.TemporaryDirectory(dir=state) as tmp:
            backup = Path(tmp)
            present = []
            for i, path in enumerate(paths):
                exists = path.exists() or path.is_symlink()
                present.append(exists)
                if exists:
                    copy_path(path, backup / str(i))
            try:
                yield
            except BaseException:
                for i, path in enumerate(paths):
                    if path.is_symlink() or path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        shutil.rmtree(path)
                    if present[i]:
                        copy_path(backup / str(i), path)
                prune_runtime(project, snapshots_before)
                raise


def copy_path(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        dest.symlink_to(os.readlink(source))
    elif source.is_dir():
        shutil.copytree(source, dest, symlinks=True)
    else:
        shutil.copy2(source, dest)


def update(project: Path, source: Path, dry: bool = False, *, source_label: str | None = None) -> None:
    project = main_project(project)
    if not (project / "project_memory").is_dir() or not any((project / p).exists() for p in
            (".research-note/project.json", ".claude/framework.json", ".claude/roles.json")):
        print(f"{project}: not a framework project — skipped")
        return
    env = {**os.environ, "RN_RUNTIME_UPDATE_INTERNAL": "1", "RESEARCH_NOTE_PROJECT_DIR": str(project),
           "CLAUDE_PROJECT_DIR": str(project), "PYTHONDONTWRITEBYTECODE": "1"}
    if not shared_capable(source):
        raise ValueError("requested source predates shared installations; use a current --source or a newer release. Existing project bindings were kept")
    if dry:
        subprocess.run(["bash", str(source / "scripts/update_projects.sh"), "--dry-run", "--agents", "none", str(project)],
                       check=True, env=env)
        print("would select a shared release for this project's Claude, Codex and scripts")
        return
    import contracts
    findings = []
    contracts.sync(project, source, dry=True, say=lambda *args: findings.append(args))
    conflicts = [row for row in findings if row[0] in {"CONFLICT", "WARN"}]
    if conflicts:
        raise ValueError("contract preflight failed: " + "; ".join(str(row) for row in conflicts))
    with transaction(project):
        pin = snapshot(project, source)
        root = pin_root(project, pin)
        activate(project, pin)
        subprocess.run(["bash", str(root / "scripts/update_projects.sh"), "--agents", "none", str(project)],
                       check=True, env=env)
        errors = check(project)
        if errors:
            raise ValueError("; ".join(errors))
        from host_install import sync_hosts
        sync_hosts(project, pin, root)
    removed = prune_locked_runtime(project)
    print(f"pinned both agents: {pin['version']} {pin['sha256'][:12]} — {project}")
    print(f"source: {source_label or ('local ' + str(source.resolve()))}")
    branch = pin.get("source_branch") or "detached/unknown"
    commit = (pin.get("source_commit") or "unknown")[:12]
    edits = "includes uncommitted plugin changes" if pin.get("source_dirty") else "no uncommitted plugin changes recorded"
    print(f"provenance: branch {branch}; commit {commit}; {edits}")
    if "-" in pin["version"].split("+", 1)[0] or pin.get("source_dirty"):
        print("development build; manifest version and content digest identify this installation")
    if removed:
        print(f"removed {len(removed)} legacy project runtime snapshot(s); shared releases retained")
    print("Claude can /reload-plugins to switch now; start a new Codex session for the new pin.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["update", "check", "restore"])
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--latest", action="store_true", help="fetch the release source without upgrading a user plugin")
    parser.add_argument("--ref", help="Git branch, tag or commit (defaults to main)")
    parser.add_argument("--version", help="select a release tag vVERSION, or verify an explicit local source's version")
    parser.add_argument("--repository", default="https://github.com/Chi-RZ/research-note.git")
    parser.add_argument("--agents", choices=["both", "claude", "codex", "none"], default="both",
                        help="compatibility option; both project bindings always use the same release")
    parser.add_argument("--no-cross-agent", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("projects", nargs="*", type=Path)
    args = parser.parse_intermixed_args()
    explicit_source = "--source" in sys.argv[1:]
    if args.version and args.ref:
        parser.error("choose --version or --ref")
    if (args.latest or args.ref) and explicit_source:
        parser.error("choose a remote release (--latest/--ref) or --source")
    projects = args.projects or [Path(os.environ.get("RESEARCH_NOTE_PROJECT_DIR") or os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())]
    try:
        for project in projects:
            project = main_project(project.resolve())
            if args.command == "check":
                errors = check(project)
                if errors:
                    raise ValueError("; ".join(errors))
                print("project runtime: OK (Claude + Codex + scripts)")
            elif args.command == "restore":
                if args.dry_run:
                    print(f"would restore the locked release in {project}")
                else:
                    restore(project, args.source.resolve())
            else:
                if args.latest or args.ref or (args.version and not explicit_source):
                    ref = args.ref or (f"v{args.version}" if args.version else "main")
                    if args.dry_run:
                        print(f"would fetch {args.repository} at {ref} and update only {project}")
                        continue
                    if ref.startswith("-"):
                        raise ValueError("invalid Git ref")
                    with tempfile.TemporaryDirectory(prefix="research-note-update-") as tmp:
                        checkout = Path(tmp)
                        git(checkout, "init", "-q")
                        git(checkout, "remote", "add", "origin", args.repository)
                        git(checkout, "fetch", "--depth", "1", "origin", ref)
                        git(checkout, "checkout", "--detach", "FETCH_HEAD")
                        source = checkout / "plugins/research-note"
                        if args.version and json_file(source / ".codex-plugin/plugin.json").get("version") != args.version:
                            raise ValueError("requested version differs from fetched manifest")
                        update(project, source, source_label=f"remote {args.repository} @ {ref}")
                else:
                    if args.version and json_file(args.source / ".codex-plugin/plugin.json").get("version") != args.version:
                        raise ValueError("requested version differs from local manifest")
                    update(project, args.source.resolve(), args.dry_run)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"project runtime: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
