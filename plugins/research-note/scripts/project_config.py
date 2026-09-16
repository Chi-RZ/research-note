#!/usr/bin/env python3
"""Read and validate one research-note project's public configuration.

The file is project-owned and agent-neutral: `.research-note/project.json`.
Older projects have no such file, so their effective configuration preserves
the behaviour that predates feature flags while using the standard layout.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(".research-note/project.json")
#: core runtime state — the record lock, the land lock, the harvest stamps, the
#: bus's put backups. Under the MAIN checkout, gitignored by a nested
#: .research-note/.gitignore, and independent of whether the fixer exists:
#: it used to live in .fixer/, which made a disabled fixer own the record's lock.
STATE_DIR = Path(".research-note/state")
SCHEMA = 1

DEFAULT_CONFIG: dict[str, Any] = {
    "schema": SCHEMA,
    "paths": {"record": "project_memory"},
    "roles": {
        "libraries": ["src"],
        "tests": ["tests"],
        "experiments": ["experiments"],
        "knowledge": ["wiki"],
    },
    "layers": {
        "source": {
            "paths": ["src", "tests"],
            "prefixes": ["feat", "fix", "refactor"],
        },
        "experiments": {"paths": ["experiments"], "prefixes": ["exp"]},
        "record": {"paths": ["project_memory"], "prefixes": ["memory"]},
        "knowledge": {"paths": ["wiki"], "prefixes": ["wiki"]},
        "agent": {
            "paths": [".research-note", ".agent", ".agents", ".claude", ".codex"],
            "prefixes": ["agent"],
        },
        "root": {"paths": [], "prefixes": ["chore"]},
    },
    "features": {
        "fixer": False,
        "hpc": False,
        "editor": False,
        "cross_agent": False,
    },
}

# Missing configuration means an installed project from before schema 1. Those
# projects already received these integrations by default. Preserving that
# behaviour avoids an update silently disabling a user's working system.
LEGACY_FEATURES = {
    "fixer": True,
    "hpc": True,
    "editor": True,
    "cross_agent": True,
}


def state_dir(root: str | Path) -> Path:
    """The project's core runtime state directory, created on first use with the
    nested .gitignore that keeps it out of the record's commits."""
    base = Path(root).expanduser().resolve() / STATE_DIR
    base.mkdir(parents=True, exist_ok=True)
    ignore = base.parent / ".gitignore"
    if not ignore.exists():
        ignore.write_text("state/\n", encoding="utf-8")
    return base


#: Who owns each managed path, and what an update may therefore do to it. The
#: updater prints this under --dry-run and each step follows its own row; the
#: update skill's table is this list in prose. `feature` names the integration
#: a row belongs to — a disabled one is left exactly as it is.
OWNERSHIP: tuple[tuple[str, str, str, str], ...] = (
    # path, owner, what an update does, feature ("" = core)
    (".research-note/project.json", "project (declaration)",
     "created once when missing — a pre-declaration project gets every integration ON; never rewritten", ""),
    (".research-note/rules/*.md", "legacy project input",
     "read once for compatibility; new project rules belong below the heading in the contract", ""),
    (".research-note/state/", "runtime state (core)",
     "never synced, never committed", ""),
    (".claude/CLAUDE.md, experiments-, project_memory-, wiki-CLAUDE.md", "mixed (framework + project)",
     "updates the framework section and preserves the project rules below its heading; an edited framework section is a conflict", ""),
    (".claude/framework.json", "state + policy",
     "never copied; a record marker behind the linter is reported", ""),
    (".claude/examples/*.md", "framework",
     "copied over", ""),
    (".claude/githooks/dispatch, research-note/*", "framework",
     "synced; a pre-declaration commit-msg that differs is a conflict until its layers are declared", ""),
    (".claude/githooks/<hook> links", "framework",
     "relinked; forwarding to the project's pre-existing hooks kept", ""),
    (".claude/settings.json", "mixed",
     "permission rules the template gained are added; everything the project has is kept", ""),
    (".claude/hpc.env", "project (machine facts)",
     "keys the template documents and the project lacks are reported; no value is ever written", "hpc"),
    (".claude/hpc-submit/*.slurm", "mixed (derived + personalised)",
     "a difference from the plugin's is a conflict to port by hand; never copied over", "hpc"),
    (".fixer/", "runtime state (fixer)",
     "untouched", "fixer"),
    ("git config research-note.pluginRoot", "framework",
     "repointed to the version being installed, every update", ""),
    ("git config core.hooksPath", "framework",
     "set to .claude/githooks; the previous value is remembered and forwarded to", ""),
)


def ownership_rows(config: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(path, owner, action) for this project — a disabled integration's rows
    say so instead of describing an action that will not happen."""
    rows = []
    for path, owner, action, feature in OWNERSHIP:
        if feature and not feature_enabled(config, feature):
            action = f"{feature} is disabled in project.json — left exactly as it is"
        rows.append((path, owner, action))
    return rows


def init_project_config(root: str | Path, *, dry: bool = False) -> tuple[str, str]:
    """Write the declaration ONCE for a project that has none, and lay the core
    state directory's ignore. A project from before the declaration gets every
    integration on — what it had — so nothing is disabled by an update.
    Returns (state, detail): kept · migrated · new."""
    project = Path(root).expanduser().resolve()
    path = project / CONFIG_PATH
    if path.is_file():
        return "kept", str(CONFIG_PATH)
    legacy = (project / ".claude/framework.json").is_file() or (project / ".claude/roles.json").is_file()
    config = initial_project_config(legacy=legacy)
    if not dry:
        write_project_config(project, config)
        state_dir(project)
    if legacy:
        return "migrated", f"{CONFIG_PATH} written — pre-declaration project, every integration on, as it was"
    return "new", f"{CONFIG_PATH} written with the defaults (integrations off)"


class ConfigError(ValueError):
    """A project configuration is ambiguous or unsafe to apply."""


def initial_project_config(*, legacy: bool = False) -> dict[str, Any]:
    """Return the configuration to write on a project's first schema-1 setup."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    if legacy:
        config["features"] = copy.deepcopy(LEGACY_FEATURES)
    validate_config(config)
    return config


def with_feature_choices(
    config: dict[str, Any], choices: dict[str, bool]
) -> dict[str, Any]:
    """Return a validated copy with explicit setup choices applied."""
    result = copy.deepcopy(config)
    for name, enabled in choices.items():
        if name not in DEFAULT_CONFIG["features"]:
            raise ConfigError(f"unknown feature {name!r}")
        if not isinstance(enabled, bool):
            raise ConfigError(f"feature choice {name!r} must be true or false")
        result["features"][name] = enabled
    validate_config(result)
    return result


def write_project_config(root: str | Path, config: dict[str, Any]) -> Path:
    """Atomically write a validated project configuration."""
    validate_config(config)
    path = Path(root).expanduser().resolve() / CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def find_project_root(start: str | Path = ".") -> Path:
    here = Path(start).expanduser().resolve()
    if here.is_file():
        here = here.parent
    for candidate in (here, *here.parents):
        if (candidate / CONFIG_PATH).is_file() or (
            (candidate / "project_memory").is_dir()
            and (candidate / ".claude/framework.json").is_file()
        ):
            return candidate
    raise ConfigError(f"not inside a research-note project: {here}")


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _top_level(value: object, where: str) -> str:
    if not isinstance(value, str) or not value or value in (".", ".."):
        raise ConfigError(f"{where} must be a non-empty top-level path")
    path = Path(value)
    if path.is_absolute() or len(path.parts) != 1 or value.startswith("../"):
        raise ConfigError(f"{where} must be a repo-relative top-level path: {value!r}")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise ConfigError(f"{where} contains unsafe path characters: {value!r}")
    return value


def validate_config(config: dict[str, Any]) -> None:
    if config.get("schema") != SCHEMA:
        raise ConfigError(
            f"unsupported project schema {config.get('schema')!r}; expected {SCHEMA}"
        )
    if config.get("paths", {}).get("record") != "project_memory":
        raise ConfigError("schema 1 keeps the record at project_memory")

    features = config.get("features")
    if not isinstance(features, dict):
        raise ConfigError("features must be an object")
    for name in DEFAULT_CONFIG["features"]:
        if not isinstance(features.get(name), bool):
            raise ConfigError(f"features.{name} must be true or false")

    layers = config.get("layers")
    if not isinstance(layers, dict) or not layers:
        raise ConfigError("layers must be a non-empty object")
    path_owner: dict[str, str] = {}
    prefix_owner: dict[str, str] = {}
    for name, layer in layers.items():
        if not isinstance(name, str) or not isinstance(layer, dict):
            raise ConfigError("each layer must be a named object")
        paths = layer.get("paths")
        prefixes = layer.get("prefixes")
        if not isinstance(paths, list) or not isinstance(prefixes, list) or not prefixes:
            raise ConfigError(f"layers.{name} needs paths and at least one prefix")
        for raw in paths:
            path = _top_level(raw, f"layers.{name}.paths")
            other = path_owner.setdefault(path, name)
            if other != name:
                raise ConfigError(f"path {path!r} belongs to both {other!r} and {name!r}")
        for prefix in prefixes:
            if not isinstance(prefix, str) or not prefix.isalpha() or not prefix.islower():
                raise ConfigError(f"invalid commit prefix {prefix!r} in layer {name!r}")
            other = prefix_owner.setdefault(prefix, name)
            if other != name:
                raise ConfigError(
                    f"prefix {prefix!r} belongs to both {other!r} and {name!r}"
                )

    roles = config.get("roles")
    if not isinstance(roles, dict):
        raise ConfigError("roles must be an object")
    for role, values in roles.items():
        if not isinstance(values, list) or not values:
            raise ConfigError(f"roles.{role} must be a non-empty list")
        for raw in values:
            path = _top_level(raw, f"roles.{role}")
            if path not in path_owner:
                raise ConfigError(f"role path {path!r} has no owning layer")

    if path_owner.get("project_memory") != "record":
        raise ConfigError("project_memory must be owned by the record layer")


def load_project_config(root: str | Path, *, legacy_if_missing: bool = True) -> dict[str, Any]:
    project = Path(root).expanduser().resolve()
    path = project / CONFIG_PATH
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"cannot read {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError(f"{path} must contain a JSON object")
        config = _merge(DEFAULT_CONFIG, raw)
    else:
        config = initial_project_config(legacy=legacy_if_missing)
    validate_config(config)
    return config


def prefix_rules(config: dict[str, Any]) -> dict[str, set[str]]:
    return {
        prefix: set(layer["paths"])
        for layer in config["layers"].values()
        for prefix in layer["prefixes"]
    }


def feature_enabled(config: dict[str, Any], name: str) -> bool:
    if name not in DEFAULT_CONFIG["features"]:
        raise ConfigError(f"unknown feature {name!r}")
    return bool(config["features"][name])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    show = sub.add_parser("show")
    show.add_argument("--compact", action="store_true")
    feature = sub.add_parser("feature")
    feature.add_argument("name")
    role = sub.add_parser("role")
    role.add_argument("name")
    set_feature = sub.add_parser("set-feature")
    set_feature.add_argument("name")
    set_feature.add_argument("value", choices=("true", "false"))
    init = sub.add_parser("init", help="write the declaration once if missing (migration)")
    init.add_argument("--dry-run", action="store_true")
    sub.add_parser("ownership", help="who owns each managed path, and what an update does to it")
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            state, detail = init_project_config(args.project, dry=args.dry_run)
            print(f"{state:<9} {detail}")
            return 0
        root = find_project_root(args.project)
        config = load_project_config(root)
        if args.command == "ownership":
            for path, owner, action in ownership_rows(config):
                print(f"{path}\t{owner}\t{action}")
        elif args.command == "validate":
            print(root / CONFIG_PATH)
        elif args.command == "show":
            print(json.dumps(config, indent=None if args.compact else 2, sort_keys=True))
        elif args.command == "feature":
            print("true" if feature_enabled(config, args.name) else "false")
        elif args.command == "role":
            values = config["roles"].get(args.name)
            if not values:
                raise ConfigError(f"unknown or empty role {args.name!r}")
            print("\n".join(values))
        elif args.command == "set-feature":
            config = with_feature_choices(
                config, {args.name: args.value == "true"}
            )
            print(write_project_config(root, config))
    except ConfigError as exc:
        print(f"project_config: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
