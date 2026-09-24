---
name: update
description: Use when the user asks to update research-note in a project — pull the newest plugin into Claude and Codex with their own commands, then bring THIS project's contracts, hooks and pin up to it. Other projects are left alone. Not for editing the plugin itself.
---

# research-note:update

Installing a plugin version does not update a project: its contracts, hooks
and Claude pin live in the repository and stay on the version that wrote them.
An update is therefore two steps — the agents, with their own commands, then
the project the user asked from, with `update_projects.sh` from the copy just
installed. Every other project stays on its version until someone updates it
from there: an update changes hooks and linters under whatever is running.

Run the whole sequence and report what moved. The user invoking this has
already decided, so the steps run without asking between them.

## 1. Install the new version into each agent

Read the marketplace name each agent registered — it is the installer's, not
this repository's, and may differ between the two:

```bash
claude plugin list | grep -A1 'research-note@'    # research-note@<mkt>
codex plugin list | grep 'research-note@'
```

Then, for each agent present:

```bash
claude plugin marketplace update <mkt> && claude plugin update research-note@<mkt>
codex plugin marketplace upgrade <mkt> && codex plugin add research-note@<mkt>
```

A marketplace refreshes from the plugin's remote, so an unpushed commit reaches
neither agent — a maintainer pushes first. Claude's refresh replaces its
marketplace clone; if that clone is an editable checkout, uncommitted work in
it is lost, so a maintainer never registers their working checkout as the
marketplace. Codex refuses an upgrade whose marketplace was renamed upstream:
`codex plugin remove`, `marketplace remove`, `marketplace add <url>`,
`plugin add` re-registers it under the new name, and Codex asks once to trust
the hooks again.

## 2. Update this project

Run the updater from the copy just installed — not from
`research-note.pluginRoot`, which still names the old one. Look only inside the
marketplace from step 1: a cache can hold copies from a marketplace registered
earlier under another name, and version numbers do not compare across
marketplaces (a renamed repository may restart at 0.1).

```bash
PLUGIN=$(ls -d ~/.claude/plugins/cache/<mkt>/research-note/* | sort -V | tail -1)
# Codex-only machine: ~/.codex/plugins/cache/<mkt>/research-note/*
bash "$PLUGIN/scripts/update_projects.sh" --dry-run   # preview
bash "$PLUGIN/scripts/update_projects.sh"
```

Run from inside the project, it updates that project and nothing else. A path
argument names a different project; pass one only when the user asked for it.

In order, it:

1. **migrates once** — a project from before `.research-note/project.json`
   gets one with every integration ON, exactly what it had; an update never
   disables anything. `--dry-run` first prints the ownership table: who owns
   each managed path and what this run may do to it;
2. moves the project's Claude pin to the version just installed (Codex has no
   per-project pin); `--agents none` skips this;
3. updates the framework section of the four contracts, copies the page
   templates, refreshes the git hooks, merges the permissions the template
   gained, and points `research-note.pluginRoot` at this copy — every
   `$PLUGIN` script resolves through it;
4. for a project that enables `hpc`, reports `hpc.env` keys it lacks and a
   `.slurm` that differs from the plugin's; otherwise touches none of it;
5. counts the `CONFLICT` lines — files whose two halves a person must sort;
   nothing there was overwritten;
6. runs doctor and both linters.

It does not commit.

## 3. Sort what the updater left for a person

| File | What the update does |
|---|---|
| the four `CLAUDE.md` contracts | Framework section replaced; `## Project-specific rules` kept. A project's own `CLAUDE.md`/`AGENTS.md` standing where a view belongs is adopted into that section. A framework section edited in place is a `CONFLICT`, left alone |
| `framework.json` | Never copied: `record` is the project's migration marker, and the linters' FW gate reads it |
| `settings.json` | Permissions the template gained are added; everything the project has stays |
| `hpc.env` | Never copied — values are the user's. Missing keys are reported |
| `githooks/*` | Synced. A pre-declaration `commit-msg` carrying the project's own `RULES` rows is left alone until those rows move into `project.json` `layers` |
| `hpc-submit/*.slurm` | Never copied. Port the plugin's log-header block by hand; the `#SBATCH` resources and script lines are the node's |

For a `CONFLICT` on a contract, sort the project's text by why it is there:

| The project's text is… | Resolution |
|---|---|
| an older wording of a framework rule | `contracts.py sync PROJECT --force` |
| a machine fact (a path, a cluster, a partition) | move it to `hpc.env` or `settings.json`, then `--force` |
| a rule the project decided for itself | move it below `## Project-specific rules`; if it would serve every project, say so |

## 4. Verify, then commit

Doctor and the linters ran in step 2; read their lines. A tightened rule can
turn a green page red, and an update is where that shows. **One `FW` line with
exit 3 is expected** for a project whose `framework.json` declares an older
`record`: migrating the record is its own step, never a side effect of an
update.

Commit it as `agent: update to research-note <version>`, staging only the
files the update changed.

## 5. Make it take effect

| What | Picks up the change |
|---|---|
| Scripts (the bus, linters, doctor, launchers) | immediately — each run reads the file |
| Claude skills, hooks, agents | `/reload-plugins`, which the user runs; ask for it |
| Codex skills and configuration | a new Codex session |
| Contract files | not reloadable — Read the ones the updater synced; a fresh session is the clean answer |

A reload pins to the moment it runs and cannot un-read what is already in
context. When a changed rule matters to work in progress, quote the changed
clause to the agent doing it.

## 6. Report

Per agent and for the project, the version before and after, read from the
registries rather than from command output; the contracts synced and the ones
left alone, with why; what was ported into `.slurm` copies; doctor and lint;
and what the user still has to do — `/reload-plugins`, a new Codex session.
