#!/usr/bin/env python3
"""Hold a Julia environment's variants to containment.

A project may legitimately need TWO environments: one platform-only dependency
is enough (MKL has no aarch64 build, so putting it in the shared file makes
`Pkg.instantiate()` fail on a Mac). What it must not have is the two drifting
apart underneath that difference — a variant that quietly re-resolved is two
different numerical stacks wearing one project's name.

So the rule is containment, checked on the FILES rather than the machines:
every package the base names must appear in the variant AT THE SAME VERSION,
and the variant may only add. No host, no network, no platform — the manifests
are in git, and this reads them.

Usage: julia_variants.py <base/Manifest.toml> <variant/Manifest.toml> [...]
Exit 0 when every variant contains the base, 1 otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

G, R, Y, Z = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def packages(path: Path) -> dict[str, str]:
    """name -> version, from a Manifest.toml. Stdlib entries carry no version
    and compare as '-', which is stable across both files."""
    out: dict[str, str] = {}
    for block in re.split(r"\n(?=\[\[deps\.)", path.read_text(encoding="utf-8")):
        name = re.match(r"\[\[deps\.([^\]]+)\]\]", block)
        if not name:
            continue
        ver = re.search(r'^version = "([^"]+)"', block, re.M)
        out[name.group(1)] = ver.group(1) if ver else "-"
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__.strip().splitlines()[-2], file=sys.stderr)
        return 2
    base_path = Path(sys.argv[1])
    if not base_path.is_file():
        print(f"  {Y}!{Z} {base_path} is not a Manifest.toml — nothing to compare against")
        return 0
    base = packages(base_path)
    failed = False
    for arg in sys.argv[2:]:
        vpath = Path(arg)
        label = vpath.parent.name or str(vpath)
        if not vpath.is_file():
            print(f"  {Y}!{Z} {label}: no Manifest.toml to compare")
            continue
        var = packages(vpath)
        absent = sorted(k for k in base if k not in var)
        skew = sorted(k for k in base if k in var and base[k] != var[k])
        if absent or skew:
            failed = True
            print(f"  {R}✗{Z} {label} has drifted from {base_path.parent.name}")
            if absent:
                print(f"     → absent there: {', '.join(absent[:6])}"
                      + (f" (+{len(absent) - 6} more)" if len(absent) > 6 else ""))
            if skew:
                shown = ", ".join(f"{k} {base[k]}/{var[k]}" for k in skew[:6])
                print(f"     → version skew: {shown}"
                      + (f" (+{len(skew) - 6} more)" if len(skew) > 6 else ""))
            print("     → a variant may only ADD packages; re-resolve it from the base and re-mirror")
        else:
            extra = len(set(var) - set(base))
            print(f"  {G}✓{Z} {label} strictly contains {base_path.parent.name} (+{extra} packages)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
