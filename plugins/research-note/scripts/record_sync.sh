#!/usr/bin/env bash
# record_sync.sh — the record bus: the ONE write path onto the record's single
# live instance (project_memory/ in the MAIN checkout, on the default branch).
# Works from any cwd including a linked worktree; all record writers serialize
# on .fixer/record.lock (shared with the fixer daemon).
#
# Two modes:
#   record_sync.sh -m "<commit message>" <repo-rel-file> [...]
#       lint + commit files ALREADY edited in place in the main checkout
#       (interactive sessions, the fixer).
#   record_sync.sh put -m "<commit message>" <repo-rel-file> <content-file>
#       the bus PLACES the content onto main itself, then lints + commits.
#       For sessions that cannot (or should not) edit the main checkout
#       directly — a bg agent edits a LOCAL copy of the page, then hands it
#       over; the harness worktree guard never applies, because the bus is a
#       shell script, not a file-edit tool.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    { echo "usage: $(basename "$0") -m \"<commit message>\" <project_memory/...> [...]"
      echo "       $(basename "$0") put -m \"<commit message>\" -b <sha256|new|force> <project_memory/...> <content-file>"
      echo "       -F <file> reads the commit message from a file instead of -m —"
      echo "          the caller's shell eats backticks and \$() inside -m; -F is verbatim"
    } >&2
    exit 2
}

mode=commit
[[ ${1:-} == put ]] && { mode=put; shift; }

msg=""; base=""; msgfile=""
while getopts "m:b:F:" opt; do
    case $opt in m) msg=$OPTARG ;; b) base=$OPTARG ;; F) msgfile=$OPTARG ;; *) usage ;; esac
done
shift $((OPTIND - 1))
if [[ -n $msgfile ]]; then
    [[ -f $msgfile ]] || { echo "ERROR: -F message file not found: $msgfile" >&2; exit 2; }
    msg="$(cat -- "$msgfile")"
fi

declare -a files
src=""
if [[ $mode == put ]]; then
    [[ -n $msg && $# -eq 2 ]] || usage
    # -b is REQUIRED: a put replaces the whole page, and between the caller's
    # read and this write the launcher may have recorded a live job's row on it.
    # Naming the version you started from turns that race into a refusal.
    # `-b new` for a page you are creating; `-b force` to overwrite knowingly.
    [[ -n $base ]] || { echo "ERROR: put needs -b <sha256|new|force> — the version you started from (see --help)" >&2; exit 2; }
    files=("$1"); src=$2
    [[ -f $src ]] || { echo "ERROR: content file not found: $src" >&2; exit 1; }
else
    [[ -n $msg && $# -ge 1 ]] || usage
    files=("$@")
fi

for f in "${files[@]}"; do
    [[ $f == project_memory/* ]] \
        || { echo "ERROR: $f is not under project_memory/ — the bus carries records only" >&2; exit 1; }
    # the prefix test above is literal, so `project_memory/../src/x` would pass
    # it, skip the linter and land a commit outside the record layer
    if [[ "/$f/" == *"/../"* ]]; then
        echo "ERROR: $f contains a '..' component — name the file by its real repo-relative path" >&2; exit 1
    fi
done

# main checkout = parent of the common .git dir (correct from any linked worktree)
MAIN="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"

# the record has ONE live instance: the main checkout, on the default branch
default="$(git -C "$MAIN" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')" || true
if [[ -z ${default:-} ]]; then
    if git -C "$MAIN" show-ref -q --verify refs/heads/main; then default=main
    elif git -C "$MAIN" show-ref -q --verify refs/heads/master; then default=master
    else echo "ERROR: cannot determine the default branch of $MAIN" >&2; exit 1; fi
fi
branch="$(git -C "$MAIN" rev-parse --abbrev-ref HEAD)"
[[ $branch == "$default" ]] \
    || { echo "ERROR: main checkout $MAIN is on '$branch', not '$default' — refusing to write the record" >&2; exit 1; }

mkdir -p "$MAIN/.fixer"
exec 9>"$MAIN/.fixer/record.lock"
# flock(2) on the inherited fd 9, taken by python3 rather than flock(1) — macOS
# ships no flock(1), python3 is already this script's linter runtime. The lock
# lives on the OPEN FILE DESCRIPTION, so it outlives this helper and is held for
# the REST of the script, exactly as `flock -w 60 9` was; the fixer takes the
# same lock with fcntl.flock, so the two serialize against each other.
python3 -c 'import fcntl, signal, sys
signal.signal(signal.SIGALRM, lambda *_: sys.exit(1))
signal.alarm(60)
fcntl.flock(9, fcntl.LOCK_EX)' \
    || { echo "ERROR: record.lock still held after 60s — is the fixer wedged?" >&2; exit 1; }

# put: optimistic-concurrency check INSIDE the lock — the caller names the
# page version it started from (sha256, or "new" for a page it is creating);
# if main moved meanwhile, refuse instead of silently overwriting the other
# writer. Omitting -b skips the check (last-write-wins; fine for a page with
# a single writer).
if [[ $mode == put && -n $base ]]; then
    tgt="$MAIN/${files[0]}"
    if [[ $base == force ]]; then
        echo "WARNING: -b force — overwriting ${files[0]} without a base check" >&2
    elif [[ $base == new ]]; then
        [[ ! -e $tgt ]] || { echo "ERROR: ${files[0]} already exists on main — someone created it first; re-read and re-apply" >&2; exit 1; }
    else
        [[ -f $tgt ]] || { echo "ERROR: ${files[0]} not found on main but base given — pass -b new to create" >&2; exit 1; }
        cur="$(python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$tgt")"
        [[ $cur == "$base" ]] \
            || { echo "ERROR: ${files[0]} moved under you (base $base, main now $cur) — re-read main's version and re-apply your change" >&2; exit 1; }
    fi
fi

# put: place the handed-over content onto main INSIDE the lock, so the
# copy + lint + commit are one atomic bus transaction. The pre-put bytes are
# backed up first and restored on ANY exit before the commit lands: a failed
# put that left the file dirty made its sha match no committed version, so
# every later `put -b` on the page was refused as "moved under you" and the
# bus wedged until a human ran `git checkout --` by hand.
put_committed=0
put_bak=""
if [[ $mode == put ]]; then
    mkdir -p "$MAIN/$(dirname "${files[0]}")"
    if [[ -f "$MAIN/${files[0]}" ]]; then
        put_bak="$(mktemp "$MAIN/.fixer/put_bak.XXXXXX")"
        cp "$MAIN/${files[0]}" "$put_bak"
    fi
    restore_put() {
        if [[ $put_committed -eq 0 ]]; then
            if [[ -n $put_bak ]]; then cp "$put_bak" "$MAIN/${files[0]}"
            else rm -f "$MAIN/${files[0]}"; fi
            echo "restored: ${files[0]} — the failed put left main clean (fix the content and re-run; no checkout needed)" >&2
        fi
        if [[ -n $put_bak ]]; then rm -f "$put_bak"; fi
    }
    trap restore_put EXIT
    cp "$src" "$MAIN/${files[0]}"
    echo "placed: ${files[0]}"
fi

for f in "${files[@]}"; do
    abs="$MAIN/$f"
    [[ -f $abs ]] || { echo "ERROR: $f not found in main checkout $MAIN" >&2; exit 1; }
    linter=""
    case "$f" in
        project_memory/objectives/*.md)                   linter="$HERE/check_objective_page.py" ;;
        project_memory/nodes/*.md | project_memory/note/*.md) linter="$HERE/check_node_page.py" ;;
    esac
    if [[ -n $linter ]]; then
        if ! out="$(cd "$MAIN" && RESEARCH_NOTE_PROJECT_DIR="$MAIN" CLAUDE_PROJECT_DIR="$MAIN" python3 "$linter" "$abs" 2>&1)"; then
            echo "LINT FAIL: $f — not committed" >&2
            echo "$out" >&2
            exit 1
        fi
        echo "lint ok: $f"
    else
        echo "lint skipped (no linter covers it): $f"
    fi
done

# The roster is DERIVED from the pages this commit is changing, so it goes
# stale the instant they land. Regenerating it here is what keeps the two in
# step. Left to a separate run someone has to remember, it drifts silently:
# nothing joins an entry's status back to _index.md — N3 checks only the node
# table and the objectives registry — so a stale row is invisible until a
# reader believes it. Failure is NOT fatal: a record write must never be
# blocked by a roster.
needs_roster=""; has_roster=""
for f in "${files[@]}"; do
    case "$f" in
        project_memory/_index.md)                          has_roster=1 ;;
        project_memory/nodes/* | project_memory/objectives/*) needs_roster=1 ;;
    esac
done
if [[ -n $needs_roster && -z $has_roster ]]; then
    if (cd "$MAIN" && RESEARCH_NOTE_PROJECT_DIR="$MAIN" CLAUDE_PROJECT_DIR="$MAIN" python3 "$HERE/gen_index.py" --record) >/dev/null 2>&1 \
            && [[ -f $MAIN/project_memory/_index.md ]]; then
        files+=("project_memory/_index.md")
    else
        echo "WARNING: could not regenerate project_memory/_index.md — committing the page(s) anyway; regenerate it by hand (gen_index.py --record)" >&2
    fi
fi

git -C "$MAIN" add -- "${files[@]}"
if git -C "$MAIN" diff --quiet HEAD -- "${files[@]}"; then
    echo "ERROR: nothing to commit — file(s) unchanged in the main checkout" >&2; exit 1
fi
git -C "$MAIN" commit -m "$msg" -- "${files[@]}"
put_committed=1
echo "committed: $msg (${#files[@]} file(s))"
if git -C "$MAIN" remote get-url origin >/dev/null 2>&1; then
    git -C "$MAIN" push \
        || echo "WARNING: push failed — the commit is LOCAL ONLY. Do NOT retry the put (it landed); push when the remote is reachable — doctor.sh counts unpushed record commits" >&2
fi
