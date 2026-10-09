#!/usr/bin/env bash
# Align path-editable libraries without making filesystem layout part of the
# project. Each machine gets its real path from .research-note/editables.env;
# uv sees only .research-note/editables/<name>.
#
# Usage: sync_editables.sh --local
#        sync_editables.sh --host <ssh-alias> --remote-dir <project-dir>
set -euo pipefail

PROJ="${RESEARCH_NOTE_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$PWD}}"
while [ "$PROJ" != "/" ] && [ ! -f "$PROJ/.research-note/project.json" ] \
      && [ ! -f "$PROJ/.claude/framework.json" ]; do PROJ=$(dirname "$PROJ"); done
[ -d "$PROJ/.research-note" ] || { echo "sync_editables: not inside a research-note project" >&2; exit 2; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANON="$PROJ/.research-note/editables.env"
LEGACY=0
if [ -f "$CANON" ]; then
    . "$CANON"
else
    # Existing projects keep working; new configuration has one home above.
    LEGACY=1
    [ -f "$PROJ/.claude/hpc.env" ] && . "$PROJ/.claude/hpc.env"
    [ -f "$PROJ/.claude/hpc.local.env" ] && . "$PROJ/.claude/hpc.local.env"
fi
. "$HERE/lib_paths.sh"

HOST=""; REMOTE_DIR=""; LOCAL_ONLY=0
while [ $# -gt 0 ]; do
    case "$1" in
        --local) LOCAL_ONLY=1 ;;
        --host) shift; HOST=${1:-} ;;
        --remote-dir) shift; REMOTE_DIR=${1:-} ;;
        -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
        *) echo "sync_editables: unknown argument $1" >&2; exit 2 ;;
    esac
    shift
done
if [ "$LOCAL_ONLY" = 0 ] && { [ -z "$HOST" ] || [ -z "$REMOTE_DIR" ]; }; then
    echo "sync_editables: use --local, or --host HOST --remote-dir PROJECT_DIR" >&2
    exit 2
fi

declared_names() {
    local v n seen=" "
    for v in "${!LIB_@}"; do
        n=${v#LIB_}; n=${n%_*}
        case "$n" in CHECKOUTS) continue ;; esac
        case "$seen" in *" $n "*) ;; *) printf '%s\n' "$n"; seen="$seen$n " ;; esac
    done
}
names=$(declared_names)
# One release of compatibility for projects that declared only SYNC_LIBS. Its
# old contract used the same absolute path on both sides; preserve that while
# pointing doctor at the path map that removes the assumption.
if [ -z "$names" ] && [ -n "${SYNC_LIBS:-}" ]; then
    hk=""; [ -z "$HOST" ] || hk=$(lib_hostkey "$HOST")
    for old_path in $SYNC_LIBS; do
        old_name=$(basename "$old_path" | sed 's/[^A-Za-z0-9_]/_/g')
        printf -v "LIB_${old_name}_LOCAL" '%s' "$old_path"
        [ -z "$hk" ] || printf -v "LIB_${old_name}_${hk}" '%s' "$old_path"
    done
    names=$(declared_names)
fi
[ -n "$names" ] || exit 0
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o LogLevel=ERROR)
rssh() { ssh "${SSH_OPTS[@]}" "$HOST" "$@" </dev/null; }

local_slot() {
    local name=$1 path=$2 slot="$PROJ/.research-note/editables/$1"
    mkdir -p "$PROJ/.research-note/editables"
    if [ -e "$slot" ] && [ ! -L "$slot" ]; then
        echo "sync_editables: $slot exists and is not a symlink" >&2; exit 1
    fi
    ln -sfn "$path" "$slot"
}

bundle_to_remote() {
    local name=$1 lp=$2 rp=$3 sha=$4 bundle remote_bundle
    bundle=$(mktemp "${TMPDIR:-/tmp}/research-note-${name}.XXXXXX.bundle")
    remote_bundle="$REMOTE_DIR/.research-note/state/editable-${name}-$$.bundle"
    git -C "$lp" bundle create "$bundle" HEAD
    ssh "${SSH_OPTS[@]}" "$HOST" \
        "mkdir -p '$REMOTE_DIR/.research-note/state' && cat > '$remote_bundle'" < "$bundle"
    rm -f "$bundle"
    rssh "mkdir -p '$rp' && \
          { git -C '$rp' rev-parse --git-dir >/dev/null 2>&1 || git -C '$rp' init -q; } && \
          git -C '$rp' fetch -q '$remote_bundle' HEAD && \
          git -C '$rp' checkout -q --detach '$sha' && rm -f '$remote_bundle'"
}

for name in $names; do
    # A git+rev source is installed by uv; its LIB_<name>_LOCAL declaration is
    # only the checkout bump_lib reads and needs no remote editable checkout.
    if grep -Eq "^[[:space:]]*$name[[:space:]]*=[[:space:]]*\\{[^}]*git[[:space:]]*=" \
            "$PROJ/pyproject.toml" 2>/dev/null; then
        continue
    fi
    lp=$(lib_path_for "$name" LOCAL)
    [ -n "$lp" ] || { echo "sync_editables: lib $name has no LIB_${name}_LOCAL in ${CANON#$PROJ/}" >&2; exit 1; }
    [ -d "$lp" ] || { echo "sync_editables: checkout path does not exist: $lp" >&2; exit 1; }
    if ! git -C "$lp" rev-parse --git-dir >/dev/null 2>&1; then
        git -C "$lp" init -q
        echo "sync_editables: initialized Git in $lp; make its first commit, then retry" >&2
        exit 1
    fi
    git -C "$lp" rev-parse -q --verify HEAD >/dev/null 2>&1 \
        || { echo "sync_editables: $name has no commit yet — make its first commit, then retry" >&2; exit 1; }
    [ -z "$(git -C "$lp" status --porcelain)" ] \
        || { echo "sync_editables: $name has uncommitted changes — commit them first" >&2; exit 1; }
    sha=$(git -C "$lp" rev-parse HEAD)
    local_slot "$name" "$lp"
    if [ "$LOCAL_ONLY" = 1 ]; then
        echo "$name @ ${sha:0:7} (local slot ready)"
        continue
    fi

    hk=$(lib_hostkey "$HOST")
    rp=$(lib_path_for "$name" "$hk")
    [ -n "$rp" ] || { echo "sync_editables: lib $name has no LIB_${name}_${hk} path for $HOST" >&2; exit 1; }
    # A remote editable is a mirror. Refuse to overwrite work done there.
    if ! rssh "if git -C '$rp' rev-parse --git-dir >/dev/null 2>&1; then \
                   test -z \"\$(git -C '$rp' status --porcelain)\"; \
               else true; fi"; then
        echo "sync_editables: $HOST:$rp has uncommitted changes" >&2; exit 1
    fi

    origin=$(git -C "$lp" remote get-url origin 2>/dev/null || true)
    branch=$(git -C "$lp" branch --show-current)
    fetched=0
    if [ -n "$origin" ] && [ -n "$branch" ]; then
        # A configured remote remains authoritative: a rejected push signals
        # divergence and must be reconciled instead of hidden by bundle copying.
        git -C "$lp" push -q origin "$branch"
        if rssh "if git -C '$rp' rev-parse --git-dir >/dev/null 2>&1; then \
                     git -C '$rp' remote get-url origin >/dev/null 2>&1 || git -C '$rp' remote add origin '$origin'; \
                 else mkdir -p \"\$(dirname '$rp')\" && git clone -q '$origin' '$rp'; fi && \
                 git -C '$rp' fetch -q origin && git -C '$rp' cat-file -e '$sha^{commit}' && \
                 git -C '$rp' checkout -q --detach '$sha'"; then
            fetched=1
        fi
    fi
    if [ "$fetched" = 0 ]; then
        bundle_to_remote "$name" "$lp" "$rp" "$sha"
        transport=bundle
    else
        transport=git
    fi
    rssh "mkdir -p '$REMOTE_DIR/.research-note/editables' && \
          slot='$REMOTE_DIR/.research-note/editables/$name'; \
          { [ ! -e \"\$slot\" ] || [ -L \"\$slot\" ]; } && ln -sfn '$rp' \"\$slot\"" \
        || { echo "sync_editables: remote slot for $name exists and is not a symlink" >&2; exit 1; }
    rsha=$(rssh "git -C '$rp' rev-parse HEAD")
    [ "$rsha" = "$sha" ] || { echo "sync_editables: $name SHA mismatch after sync" >&2; exit 1; }
    echo "$name @ ${sha:0:7} ($HOST via $transport)"
done

[ "$LEGACY" = 0 ] || echo "sync_editables: migrate LIB_* lines from .claude/hpc.env to .research-note/editables.env" >&2
