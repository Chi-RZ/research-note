#!/usr/bin/env bash
# bump_lib.sh — point the project at the CURRENT commit of a fork checkout.
#
# With git-pinned sources (`{ git = ..., rev = <sha> }`) the lockfile carries the
# fork's identity, so a run is reproducible from one checkout — but the pin does
# not follow the fork on its own. This is the one ritual that keeps them in step:
# after committing and pushing work in the fork, run this before the next
# RECORDED run that is meant to use the new revision. Moving the pin alone does
# not invalidate old entries or schedule their benchmarks.
#
# Usage: bump_lib.sh <lib-name> [<lib-name> ...]     (names as in tool.uv.sources)
#        bump_lib.sh --all                            (every git-pinned source)
#        bump_lib.sh --check                          (report drift, change nothing)
#
# Refuses when the fork is dirty or unpushed: the cluster resolves the pin from
# the remote, so a SHA that only exists on this machine would not be fetchable.
set -euo pipefail

PROJ="${CLAUDE_PROJECT_DIR:-$PWD}"
while [ "$PROJ" != "/" ] && [ ! -f "$PROJ/pyproject.toml" ]; do PROJ=$(dirname "$PROJ"); done
[ -f "$PROJ/pyproject.toml" ] || { echo "bump_lib: no pyproject.toml above $PWD" >&2; exit 2; }
PYPROJECT="$PROJ/pyproject.toml"

CHECK=0; ALL=0; declare -a NAMES=()
for a in "$@"; do
    case "$a" in
        --check) CHECK=1 ;;
        --all)   ALL=1 ;;
        -*)      echo "bump_lib: unknown flag $a" >&2; exit 2 ;;
        *)       NAMES+=("$a") ;;
    esac
done
# --check with no names means "every pin", the same set --all would bump.
[ "$CHECK" = 1 ] && [ ${#NAMES[@]} -eq 0 ] && ALL=1
[ "$ALL" = 1 ] || [ ${#NAMES[@]} -gt 0 ] || { echo "usage: bump_lib.sh <lib> [...] | --all | --check" >&2; exit 2; }

# Where does each fork live on THIS machine? The pin names a git URL, not a path,
# so the working checkout is declared separately in
# .research-note/editables.env. Older declarations remain readable.
[ -f "$PROJ/.claude/hpc.env" ] && . "$PROJ/.claude/hpc.env"
[ -f "$PROJ/.claude/hpc.local.env" ] && . "$PROJ/.claude/hpc.local.env"
[ -f "$PROJ/.research-note/editables.env" ] && . "$PROJ/.research-note/editables.env"

checkout_for() {  # name -> path, or empty
    local n=$1 pair v
    # The LIB_<name>_LOCAL declaration is the current spelling (templates/editables.env);
    # a uv source name may carry characters a variable cannot, so they map to _.
    v="LIB_${n//[^A-Za-z0-9]/_}_LOCAL"
    [ -n "${!v:-}" ] && { echo "${!v}"; return 0; }
    for pair in ${LIB_CHECKOUTS:-}; do
        case "$pair" in "$n="*) echo "${pair#*=}"; return 0 ;; esac
    done
    for pair in ${DOMAIN_LIBS:-${DOMAIN_LIB_DIR:-}}; do
        [ "$(basename "$pair")" = "$n" ] && { echo "$pair"; return 0; }
    done
    return 1
}

pinned_names() {  # every source with a `git =` in pyproject
    grep -oE '^[A-Za-z0-9_.-]+[[:space:]]*=[[:space:]]*\{[^}]*git[[:space:]]*=' "$PYPROJECT" \
        | sed 's/[[:space:]]*=.*//'
}

# `while read`, not mapfile — a bash 4 builtin, absent from macOS's 3.2.
[ "$ALL" = 1 ] && while IFS= read -r n; do NAMES+=("$n"); done < <(pinned_names)
[ ${#NAMES[@]} -gt 0 ] || { echo "bump_lib: no git-pinned sources found in $PYPROJECT" >&2; exit 1; }

changed=0
for name in "${NAMES[@]}"; do
    path=$(checkout_for "$name") || {
        echo "bump_lib: no checkout known for '$name' — declare LIB_${name}_LOCAL=/path/to/$name in .research-note/editables.env" >&2
        exit 1; }
    # `git -C`, not `-d .git`: a checkout that is a SUBDIRECTORY of its repo
    # (qecbench = qec_bench/projects/qecbench) has no .git of its own — the
    # same false negative remote.sh fixed in 0.13.20.
    git -C "$path" rev-parse --git-dir >/dev/null 2>&1 \
        || { echo "bump_lib: $path is not inside a git repo" >&2; exit 1; }

    cur=$(grep -oE "^$name[[:space:]]*=[[:space:]]*\{[^}]*rev[[:space:]]*=[[:space:]]*\"[0-9a-f]+\"" "$PYPROJECT" \
          | grep -oE '"[0-9a-f]+"' | tr -d '"') || true
    new=$(git -C "$path" rev-parse HEAD)

    if [ "$cur" = "$new" ]; then
        echo "$name: up to date (${new:0:8})"
        continue
    fi
    if [ "$CHECK" = 1 ]; then
        echo "$name: DRIFT — pinned ${cur:0:8}, checkout ${new:0:8}"
        changed=1
        continue
    fi

    # The pin must be fetchable from the fork's remote, or the cluster cannot resolve it.
    [ -z "$(git -C "$path" status --porcelain)" ] \
        || { echo "bump_lib: $name has uncommitted changes — commit them first" >&2; exit 1; }
    br=$(git -C "$path" branch --show-current)
    git -C "$path" fetch -q origin "$br" 2>/dev/null || true
    git -C "$path" merge-base --is-ancestor "$new" "origin/$br" 2>/dev/null \
        || { echo "bump_lib: $name commit ${new:0:8} is not on origin/$br — push the fork first" >&2; exit 1; }

    python3 - "$PYPROJECT" "$name" "$new" <<'PY'
import re, sys
path, name, new = sys.argv[1:4]
t = open(path).read()
pat = re.compile(rf'(^{re.escape(name)}\s*=\s*\{{[^}}]*rev\s*=\s*")[0-9a-f]+(")', re.M)
t2, n = pat.subn(rf'\g<1>{new}\g<2>', t)
if n != 1:
    sys.exit(f"bump_lib: could not rewrite the rev of '{name}' in {path}")
open(path, "w").write(t2)
PY
    echo "$name: ${cur:0:8} -> ${new:0:8}"
    changed=1
done

if [ "$CHECK" = 1 ]; then
    [ "$changed" = 0 ] && echo "all pins current" || echo "run bump_lib.sh --all to update" >&2
    exit "$changed"
fi
[ "$changed" = 0 ] && exit 0

( cd "$PROJ" && VIRTUAL_ENV= uv lock )
echo
echo "pyproject.toml + uv.lock updated — commit them (chore:) and the next recorded run is pinned."
