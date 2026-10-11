---
name: update
description: Use when the user asks to update research-note in a project — fetch a release and pin this project’s Claude, Codex, hooks and scripts to it. Other projects and user-level plugin installations stay unchanged. Not for editing the plugin itself.
---

# research-note:update

Update the current project's shared framework for both agents. The project's
`.research-note/plugin-lock.json` selects an immutable snapshot; updating an
agent's user-level plugin is neither necessary nor part of this procedure.

## 1. Fetch and update this project

Resolve `$PLUGIN` from `git config --get research-note.pluginRoot`. Read the
current lock when present; a project without one is migrated by this update.
Run from the main checkout (the script also resolves a worktree to its main):

```bash
bash "$PLUGIN/scripts/update_projects.sh" --latest
```

The command fetches the published repository into a temporary checkout and
runs that release's updater against this project only. If the user names a
branch, tag or commit, add `--ref REF`; a requested fork uses `--repository URL`.
Use `--dry-run` for a requested preview. With `--latest`, the preview reports
what would be fetched without contacting the remote. To inspect the actual
file changes, fetch the requested source first and run its updater with
`--dry-run PROJECT_DIR`.

For an older installed release that lacks this flow, fetch the repository
into a temporary directory and run the new copy's
`plugins/research-note/scripts/update_projects.sh PROJECT_DIR`. Do not run
`claude plugin update`, `codex plugin add`, or upgrade a shared marketplace.
A maintainer testing unpublished edits runs the updater from the source
checkout without `--latest`. An unpushed commit is unavailable to other users.

The updater checks contract conflicts before writing, stages a snapshot of
the complete plugin, and carries over the project's existing rules and
permissions. It updates Git hooks and templates, then binds both agents and
`research-note.pluginRoot` to the same snapshot. Different project/release
marketplace IDs prevent host-cache collisions. After a successful switch, the
updater removes superseded project snapshots; Claude and Codex manage their own
caches. A failed write restores managed project files and Git configuration and
removes its unused staged snapshot. No user plugin registry is rewritten.

## 2. Read the result

A contract conflict stops the update before activation. Move project-specific
text below `## Project-specific rules`; if a framework rule was intentionally
edited, reconcile it with the new rule rather than overwriting it blindly.
Then run the update again.

`framework.json` is project-owned state and policy, so it is not copied. Its
`record` value is the migration marker; `record_language` remains the project's
language choice. A record-version mismatch still requires a separate record
migration. HPC settings and edited submit templates also stay project-owned;
port a changed log header manually when the report requests it. Neither
operation is silently resolved by pinning.

Doctor and both record linters report the project's state. Verify the complete
runtime binding separately from environment or record findings:

```bash
PLUGIN=$(git config --get research-note.pluginRoot)
python3 "$PLUGIN/scripts/project_runtime.py" check
```

A zero exit confirms the pinned files and local agent bindings. It does not
claim a running agent has reloaded them or override the host's trust policies.

## 3. Commit and hand over the session boundary

Stage only this update's project files: the lock, changed contracts and hooks,
and the project agent settings. Keep `.research-note/runtime/` and machine-local
settings out of Git. Commit as `agent: update research-note to <version>`.

Report the old and new version/hash, affected project, retained project rules,
any outstanding doctor or record findings, and the commit. The project keeps
only the snapshot selected by its lock. Claude may run `/reload-plugins` to
switch in place; start a new Codex session for the new pin. After switching,
check the host's plugin listing for the lock's selector.

Do not update a second project or user-level plugin as a side effect. Updating
this project's shared rules intentionally applies to both agents in this
project, whichever agent performed the update.
