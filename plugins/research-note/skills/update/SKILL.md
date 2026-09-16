---
name: update
description: Use when pulling a new version of this plugin into a machine — refreshes Claude and Codex marketplaces, equalizes their installed versions, and syncs every registered project's framework files without touching personalized ones. Run it after the plugin repo gains a commit, or whenever a project's contract files look older than the skills. Not for editing the plugin itself.
---

# research-note:update

Pulling a plugin version into one agent is only part of the job. Claude and
Codex keep separate caches and registries; the four contract files live in each project's
`.claude/` and do NOT — so a plugin upgrade silently leaves every project's
written doctrine one version behind its own linter. This skill closes that gap
in one pass.

Run the whole sequence; report what moved. **Do not ask between steps** — the
user invoking this has already decided.

## 0. Resolve the package that invoked this skill

```
PLUGIN="$(git config --get research-note.pluginRoot)"
[ -d "$PLUGIN" ] || PLUGIN="$(cd "$(dirname "$SKILL_FILE")/../.." && pwd -P)"
```

When the harness does not expose `SKILL_FILE`, use the plugin root containing
this `SKILL.md`. Do not resolve "latest" from only one agent's cache: that makes
the update's meaning depend on which CLI happens to have the larger version
directory. The invoked package is the target version.

## 1. Run the agent-neutral updater

```
bash "$PLUGIN/scripts/update_projects.sh"              # this is the whole command
bash "$PLUGIN/scripts/update_projects.sh" --dry-run    # preview
```

**Which agents to update is not a decision anyone makes.** The updater looks for
each CLI on PATH and updates the ones it finds, so a Claude-only machine, a
Codex-only machine and a machine with both all take the identical command; the
missing side prints `no CLI on this machine` and the run carries on. The parity
check fires only when both are present, so one agent alone raises no warning.

`--agents both|claude|codex|none` exists only to NARROW that — `none` syncs the
projects without touching either CLI registry, and naming one side isolates half
the pipeline while debugging it. **Do not write `--agents both`:** it is the
default, and spelling it out teaches the next reader that there is a choice here
when there is not.

With no project arguments, discovery is
the union of the neutral registry `~/.config/research-note/projects.json` and
legacy Claude project-scope rows. Bootstrap maintains the neutral registry, so
a Codex-only machine has the same update path. An explicit project works before
either registry exists.

The script then performs, in order:

1. refresh each selected agent's own marketplace;
2. update its own plugin pin using its native selector and command;
3. read both registries back and require the same plugin version and source
   commit (the cache paths are intentionally different);
4. update every Claude project-scope pin, where Claude has one;
5. sync the four contract files, page templates and missing hooks; merge new
   permissions, report `hpc.env` and `.slurm` drift, repoint
   `research-note.pluginRoot`, then run doctor and cross-lint.

It prints the commit line per project and stops there — staging is yours.

A script rather than these steps done by hand, for a reason worth keeping: it is
a separate process, so it always runs the newest version on disk and needs no
reload to be current. The three mistakes it removes are the three that actually
recurred — a scope updated from the wrong directory, a permission the template
had gained left unmerged, and a sync nobody verified.

What it deliberately leaves to you: the judgment calls in step 3 (a hunk that
is this project's own decision, a `.slurm` header to port), the commits, and
step 5.

## 2. Source safety and parity

Claude's native marketplace refresh may delete and re-clone its marketplace.
That is correct for an ordinary downloaded marketplace and hazardous when the
marketplace path is itself an editable git checkout.

**If you MAINTAIN this plugin, that delete is a hazard.** Your marketplace clone
is a normal checkout of your own repo — same origin, push rights intact, often
the path already open in your editor — and the refresh discards every
uncommitted edit and untracked file in it without a prompt. Measured, not
assumed: a probe file and a modified `DESIGN.md` were both gone across one
invocation.

For a clean git-backed Claude marketplace the updater therefore uses
`git pull --ff-only`; if it is dirty, it stops that side and reports the path.
For a downloaded Claude marketplace and for Codex's disposable marketplace
snapshot, it uses the native refresh command. Never clean or overwrite an
editable checkout on the user's behalf.

**Commit AND PUSH the plugin source before running an update.** Each agent's
marketplace is a clone of the plugin's remote, and the updater refreshes those
clones from it — so an unpushed commit is invisible to every one of them, on
your own machine included. Push is not the last tidying step of a release; it
is the only channel the release travels through. The updater compares the
source commits, not just semver: equal version labels on different commits are
not parity.

That one extra step is the whole difference between maintaining this plugin and
using it. A maintainer edits a checkout, commits, pushes; a user pulls. From
the updater onward the two are the same command, deliberately — a maintainer
with a private shortcut stops exercising the path everyone else is on, and it
rots unobserved.

`research-note.pluginRoot` is a SEPARATE pin and moving the scope does not move
it. It is an absolute path into the version directory, written by
`bootstrap_project.py`, and `$PLUGIN` in every skill and launcher resolves
through it — so a project pinned to the new version with `pluginRoot` still on
the old one runs the NEW skills over the OLD scripts, including both linters,
the record bus and `.fixer/run.sh`'s first branch. `update_projects.sh`
repoints it (step 0); if you are updating by hand, set it yourself or re-run
`bootstrap_project.py`, which is the finishing move for exactly this reason.

Installing an agent that has the plugin NOWHERE is still
`bootstrap_project.py`'s job, not an update's.

The fixer and all project scripts resolve the shared `research-note.pluginRoot`,
which the updater moves to the exact package running the update. Agent-native
skills still follow each agent's own installed pin until its session reloads.

## 3. Sync the framework files, never the personalized ones

For every project on the framework, compare `.claude/<file>` against
`<cache>/templates/<file>`:

| File | Treatment |
|---|---|
| `CLAUDE.md`, `experiments-CLAUDE.md`, `wiki-CLAUDE.md`, `project_memory-CLAUDE.md` | **Generated — never edited, never copied by hand.** `contracts.py` (the updater runs it) writes each as the plugin's template plus the project's own `.research-note/rules/<root\|experiments\|record\|wiki>.md`; the first line of the generated file names both. A project rule goes in the rules file; a framework rule goes in the plugin. A pre-generation file (0.1.9–0.2.3, the boundary block with an appendix under it) has its appendix carried into the rules file once — `migrated`. It reports `CONFLICT` and leaves the file alone only when a pre-generation file's project text cannot be told apart (edited in place, or an appendix beside a rules file that already has content): that is the judgment call — move the text, then `contracts.py sync PROJECT --force` |
| `framework.json` | **State + policy — never copy.** `record` is the project's migration marker; the linters' FW gate reads it, and copying the template's value marks an unmigrated record as current, disarming the one check that protects it. The marker moves only when the record is actually migrated. `record_language` is the project's policy and stays |
| `settings.json` | **Personalized** (permissions, env) — never copy wholesale. But DIFF the `permissions.allow` lists: a new mechanism often needs a new command (0.11 added `flock` and `sha256sum` for the record bus), and a project missing it fails at the moment the mechanism first runs. Add what the template gained; keep everything the project has. Verify `enabledPlugins` still names the plugin |
| `hpc.env` | **Personalized** (this machine's cluster) — never copy. But diff it against `templates/hpc.env` for KEYS the template documents and the project lacks, and tell the user what each would do (0.11 added `REMOTE_PARTITION` / `REMOTE_RESERVATION` / `REMOTE_ACCOUNT`; a project without them queues wherever the cluster defaults). Their values are the user's to give |
| `githooks/*` | **Framework text, laid by `githooks_install.py`** — the updater runs it: the dispatcher and `research-note/pre-commit` are synced; every hook name is (re)linked; forwarding to the project's pre-existing hooks is kept. The one file it will not overwrite is a `research-note/commit-msg` that differs while the project declares no layers in `.research-note/project.json` — a pre-declaration hook carries the project's own `RULES` rows INSIDE it, and a copy would delete its prefixes. It says so; move the rows into `project.json` `layers`, re-run, and the hook syncs. Verify `git config core.hooksPath` is `.claude/githooks` and doctor's hook lines are green |
| `hpc-submit/*.slurm` | **Derived + personalized**: instantiated from the plugin's `skills/hpc-submit/scripts/*.slurm`, then edited for this cluster (partition, reservation, account). Do NOT copy over — DIFF them against the plugin's versions and port any plugin-side fix by hand, reporting what you ported. A project copy silently keeps the bugs the template already fixed |

`project_memory/CLAUDE.md` and its siblings in the project tree are symlinks
into `.claude/` — edit the `.claude/` file, and the change is an `agent:`
commit.

A `CONFLICT` line on a contract is the one place this step needs you. Read
the diff it prints, and sort the project's text by WHY it is there:

| The project's text is… | Resolution |
|---|---|
| an older wording of a framework rule | nothing to keep — `contracts.py sync PROJECT --force` |
| a machine fact (a path, a cluster name, a partition) | that belongs in `hpc.env` or `settings.json`, not in a contract. Move it there, then `--force`; report the move |
| a rule the project genuinely decided for itself | move it into `.research-note/rules/<x>.md`, then `--force`. If it would serve every project, say so — it may belong in the template instead; the user decides which |

For the derived-and-personalized files (`hpc-submit/*.slurm`) the same question
has a different answer, because both halves are legitimate: the log-header block
is the framework's and must be ported forward; the `#SBATCH` resources and the
script/args lines are the node's and must be left alone. Port the header, keep
the rest, and say which lines you moved. If the project's copy carries a cluster
fact the template has since taught `hpc.env` to supply (a partition, a
reservation), drop it from the copy and declare it in `hpc.env` instead —
declared twice, the two can silently disagree.

`settings.json` and `hpc.env` drift in BOTH directions and the directions mean
different things. What the project has and the template does not is almost
always a machine fact (an absolute path, a domain allowance) and stays. What the
TEMPLATE has and the project does not is almost always a new mechanism's
requirement (0.11 added `flock`, `sha256sum`, then `bash`/`python3`/`ssh`/
`scp`/`rsync` for the bus, remote.sh and doctor) and must be added, or that
mechanism fails the first time it runs — silently, as a permission prompt
nobody is there to answer.

## 4. Verify, then commit

Run `scripts/doctor.sh` in each project first (the core plus whatever the
project enables; a disabled integration is listed, not failed) — it checks the wiring the sync
just touched (githooks installed and pointed at, record layer on the default
branch, the scanner alive, each remote reachable and in step) and prints the
fix for anything it finds. A green doctor is the evidence that the update
landed; the lint pass below covers the pages, doctor covers the machinery.

Re-run both linters with the NEW cache over every page the projects hold —
`check_node_page.py` on `project_memory/nodes/**/*.md` and
`check_objective_page.py` on `project_memory/objectives/*.md`. A doctrine change
that relaxes a rule cannot break a green page, but a tightened one can, and this
is the only place it shows.

**A project whose `framework.json` declares an older `record` than the linter
enforces gets ONE `FW` line and exit 3 — expected, not a failure.** The record
migration is its own deliberate step, never a side effect of an update; until
it runs, the FW gate is what keeps the new linter from convicting the old
format, and the pre-commit gate deliberately passes exit 3.

Commit each project separately with the `agent:` prefix, naming the version
reached. Stage ONLY the files you changed — a project may hold unrelated
uncommitted work.

## 5. Make it take effect in THIS session

An update lands on disk; a running session keeps what it loaded at launch. Four
mechanisms, each established by trying it:

| What | How it picks up a change |
|---|---|
| **Scripts** — the bus, both linters, `doctor.sh`, the launchers | **Immediately.** Separate processes, they read the newest file every run. Nothing to do. |
| **`.claude/settings.json`** | Claude hot-reloads permissions and hooks. Codex does not consume this agent-specific settings file. |
| **Claude plugin skills, commands, agents, hooks** | **`/reload-plugins`** — the USER runs it; a session cannot invoke a slash command for itself. Ask for it and say what changed. `--force` if it warns about the prompt cache. |
| **Codex plugin skills and configuration** | Start a new Codex session (or resume after exiting the current process). The CLI has no in-session plugin reload command. |
| **Contract files** (`CLAUDE.md` / `AGENTS.md` and siblings) | **Not reloadable as injected instructions.** Read the changed files for current work; start a fresh session for a clean context. |
| **A skill YOU just published** | Same answer, same reason: **`Read` it** out of the new cache directory. `update_projects.sh` prints the exact paths of the skills this version changed. A reload would be tidier but is the user's to run; a read is yours, and the text you have read is the text you act on. |

Two findings that cost real confusion, worth stating outright:

- **Publishing during a session does not change how that session behaves.** The
  loaded copy stays loaded, so after any release you make, read what you changed
  out of the new cache path before acting on it — otherwise you are following
  the version you superseded, which is exactly the failure this pipeline exists
  to prevent everywhere else. Ask for a reload too, for the components a read
  cannot cover (agents, hooks), and tell Codex users to start a new session, but
  do not wait on it.
- **`/reload-plugins` pins to the moment it runs.** It does not subscribe to
  later versions. Publish 0.11.15 after the user reloaded at 0.11.13 and the
  session still serves 0.11.13 — including this skill. If you have published
  during the session, ask for another reload before trusting any skill text.
- **A reload cannot un-read what is already in context.** It changes what the
  NEXT read returns. So when a contract change matters to work happening right
  now, put the changed clause in the message you send the agent doing that work
  — that is the only zero-latency channel.

`claude --continue` / `--resume` and `codex resume` start fresh processes and
rebuild their project instructions from disk, so either is the clean answer
when behaviour looks a version behind. (`/compact` also re-injects Claude's
project-root contract as a side effect.)

## 6. Report

State: the version before and after PER SCOPE (from the file, not from the
command output), which contract files were synced and which were left alone with
why, what you ported by hand into the derived `.slurm` copies, the doctor result,
the lint result — and then what the user must still do for the running session to
see it: run `/reload-plugins` (the CLI's "Restart to apply changes" overstates
it; a reload is enough, and a restart is only the clean fallback). Say which
contract files you re-read, since those cannot be reloaded at all.
