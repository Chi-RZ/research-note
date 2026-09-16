# lib_state.sh — the project's core runtime state directory, for shell callers.
#
# The Python twin is project_config.state_dir(). Both answer
# <main checkout>/.research-note/state/ and create it, with the nested
# .gitignore that keeps it out of every commit, on first use. The record lock,
# the land lock, the harvest stamps and the bus's put backups live here — and
# NOT in .fixer/, which is the fixer's own state and may not exist at all in a
# project that runs without one.
#
# Sourced by record_sync.sh and land_and_launch.sh; doctor.sh reads the path.

rn_state_dir() {  # rn_state_dir <main checkout>  -> prints the directory, created
    local main=$1 dir
    dir="$main/.research-note/state"
    mkdir -p "$dir" || return 1
    [ -f "$main/.research-note/.gitignore" ] || printf 'state/\n' > "$main/.research-note/.gitignore"
    printf '%s\n' "$dir"
}
