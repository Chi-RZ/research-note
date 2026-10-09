# lib_paths.sh — resolve a project's developed-library declarations.
#
# ONE declaration serves both halves of DESIGN.md §8.2: the log header RECORDS
# the commit that ran, and `remote.sh push` ALIGNS the two sides to one commit
# before anything launches. Declaring a lib buys both; there is no way to get
# the record without the gate — the half-open state (a SHA in every header,
# nothing holding the sides to it) is the one that produced runs on a commit
# no remote holds.
#
# The declaration, in the local .research-note/editables.env — one line per side:
#
#   LIB_<name>_LOCAL=<path on the record-keeping machine>
#   LIB_<name>_<HOSTKEY>=<path on that remote host>
#
# <name> is variable-name-safe (letters, digits, _). <HOSTKEY> is REMOTE_HOST
# with every non-alphanumeric dropped (see lib_hostkey) and never contains an
# underscore — that is what makes the name/suffix split unambiguous, so a
# <name> may itself contain underscores. sync_editables creates a stable slot
# inside each project clone; launchers can discover that slot without carrying
# the private path map to the remote machine.
#
# Sourced by remote.sh, doctor.sh and bump_lib.sh. The launchers cannot source
# it (they travel to the cluster alone), so each carries a verbatim copy of the
# marked block below; scripts/tests/test_lib_paths.py holds the copies
# byte-identical to this one.

# >>> lib_paths (keep every copy of this block identical) >>>
lib_slot_root() {
    local root=${REPO_ROOT:-}
    [ -n "$root" ] || root=$(git rev-parse --show-toplevel 2>/dev/null) || return 1
    printf '%s\n' "$root/.research-note/editables"
}
lib_names() {  # every declared <name>, once, one per line
    local v n p root seen=" "
    root=$(lib_slot_root 2>/dev/null) || root=""
    if [ -n "$root" ]; then
        for p in "$root"/*; do
            [ -d "$p" ] || continue
            n=$(basename "$p")
            case "$seen" in *" $n "*) ;; *) printf '%s\n' "$n"; seen="$seen$n " ;; esac
        done
    fi
    for v in "${!LIB_@}"; do
        n=${v#LIB_}; n=${n%_*}
        case "$n" in CHECKOUTS) continue ;; esac   # legacy bump_lib map, not a lib
        case "$seen" in *" $n "*) ;; *) printf '%s\n' "$n"; seen="$seen$n " ;; esac
    done
}
lib_path_here() {  # <name> -> the first declared path that exists on THIS machine
    local v suffix root
    root=$(lib_slot_root 2>/dev/null) || root=""
    [ -n "$root" ] && [ -d "$root/$1" ] && { printf '%s\n' "$root/$1"; return 0; }
    for v in "${!LIB_@}"; do
        case "$v" in "LIB_$1_"*) ;; *) continue ;; esac
        suffix=${v#LIB_$1_}
        case "$suffix" in *_*) continue ;; esac   # a longer lib name, not a side of this one
        [ -d "${!v}" ] && { printf '%s\n' "${!v}"; return 0; }
    done
    return 1
}
lib_path_for() {  # <name> <side: LOCAL or a hostkey> -> the declared path, set or fail
    local v="LIB_$1_$2"
    [ -n "${!v:-}" ] && printf '%s\n' "${!v}"
}
lib_hostkey() {  # <host> -> its variable-suffix spelling (alphanumerics only)
    local h=$1 out="" c
    while [ -n "$h" ]; do
        c=${h%"${h#?}"}; h=${h#?}
        case "$c" in [A-Za-z0-9]) out="$out$c" ;; esac
    done
    printf '%s\n' "$out"
}
# <<< lib_paths <<<
