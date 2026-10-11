---
name: update
description: Use when the user asks to update research-note in a project, select a release version, or test a local plugin checkout. Changes this project's Claude, Codex, hooks and scripts together; other projects keep their selections. Not for editing the plugin itself.
---

# research-note:update

## Select the source and update

Read `.research-note/plugin-lock.json` and resolve the current plugin with
`git config --get research-note.pluginRoot`. Worktrees use the main checkout's
selection. Choose the command matching the request:

```bash
# Default user request: fetch the published main branch.
bash "$PLUGIN/scripts/update_projects.sh" --latest PROJECT_DIR

# A particular release: fetch its vVERSION tag and check the manifest version.
bash "$PLUGIN/scripts/update_projects.sh" --version 0.1.0 PROJECT_DIR

# A branch, tag or commit; --repository URL selects a fork.
bash "$PLUGIN/scripts/update_projects.sh" --ref REF PROJECT_DIR

# Unpublished local edits: the directory containing the plugin manifests.
bash "$PLUGIN/scripts/update_projects.sh" --source /path/to/repo/plugins/research-note PROJECT_DIR
```

Use an explicit `--source` for local development; it installs a copy of the
working files, including uncommitted edits. GitHub is not contacted and switching
the clone's branch afterward does not change installed content. Once published,
`--latest` or `--version` selects the remote content in the same way. The version
and content digest identify what was actually installed, even when two local
builds still carry the same manifest version. Prefer distinct prerelease versions
for development releases.

Version selection requires a release whose installer understands shared
installations. Earlier private snapshots remain usable and can migrate to a
current release; selecting an old installer is refused before project writes.
The initial public release tag must include the shared-install implementation.

For an installed updater lacking these options, fetch the current repository
into a temporary directory and run its updater with the requested source and
project. Add `--dry-run` for a preview. Remote previews report the repository/ref
without fetching; local previews inspect the source without installing hosts.

The updater preflights contract conflicts, installs immutable content once per
machine, updates project contracts and Git hooks, then selects that release for
both hosts. Projects selecting identical content share its installation and
marketplace identity. The portable lock stays in the project; full plugin files
live in `~/.local/share/research-note/releases/<digest>/` (or the XDG data directory).
Legacy project runtime copies are removed only after a successful switch.
Shared releases are retained because another project may still select them.

Claude is installed with native **project scope**. Codex uses the project config
and native discovery to populate its cache, without global `plugin add`.
Available hosts are verified; absent hosts or an untrusted Codex project are
reported as pending. User enablement and unrelated installations are preserved.
Claude local marketplaces may load directly from the shared immutable source;
Codex loads its own cache. Neither follows the mutable development checkout.
Failure restores managed project files and the previous selection, and removes
a newly added Claude project registration. Shared cache/source files may remain.

## Verify and report

Reconcile contract conflicts before retrying. Preserve project-specific rules,
permissions, record language, HPC profiles and edited submit templates. A record
format mismatch still needs its own migration; installing a release is not that
migration. Doctor and the two record linters report separate project findings.

```bash
PLUGIN="$(git config --get research-note.pluginRoot)"
python3 "$PLUGIN/scripts/project_runtime.py" check PROJECT_DIR
```

Check the selected version/hash, both project selectors and the native host
report in `.research-note/state/host-install.json`. A successful binding check
does not mean an already running session reloaded. If Codex is pending, resolve
the host's project trust/diagnostics and rerun setup to complete installation.

Stage only this update's lock, contracts and project configuration. Machine-local
settings, state and installed content stay out of Git. Commit the requested
project update as `agent: update research-note to <version>`; report old/new
version and hash, affected project, commit and outstanding findings.

Claude can `/reload-plugins` in place; start a new Codex session. Verify the host's
plugin listing matches the lock's selector after switching. Apply updates only
to the requested projects, whichever host runs the command.
