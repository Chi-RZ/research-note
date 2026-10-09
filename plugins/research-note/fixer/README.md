# Fixer operations

**Everything is the owner's job; the cycle only raises a hand.** Whoever
launched a job watches it, pulls its artifacts, analyzes it and writes the
record — with the context to know what any of it means. The daemon repairs
nothing, commits nothing on anyone's behalf, and fetches nothing; it reports.

**The cycle is a SCANNER.** It reads the record, stamps `attention:` on an objective whose loop went quiet while jobs were in flight, and refreshes the dashboard. It does not repair pages: the record bus (`scripts/record_sync.sh`) lints every write and commits it, and all four launch venues record at launch, so the backlogs the agent tiers existed to clear are no longer produced. Both tiers ship disabled in `config.json`; the code stays for the case where a real backlog appears that nothing else catches.

The lint-fixer runs either as a **crontab entry** (`register_cron.sh
[PROJECT_DIR] [CADENCE_MIN]`) or as a **detached background daemon**
(`start_fixer_daemon.sh [PROJECT_DIR]` — a `while … run_fixer.sh; sleep 600`
loop, flock-idempotent). A **SessionStart hook** re-runs the daemon starter,
so a container rebuild self-heals on the next session. Both paths are
serialized by the same lock, so running both never overlaps cycles.

**Two dormant repair tiers.** Both ship disabled. If a project explicitly
enables them, the **format** tier repairs mechanical lint and the **analyze**
tier acts as a delayed **orphan safety net**, not the default analyzer. The
session that submits jobs watches and analyzes them itself, with full context;
the fixer must never race a living owner. An
unanalyzed terminal entry qualifies only after `attention_after_min` (default
30 min) of silence on BOTH heartbeats: the page mtime and its newest
file://-linked log. Stage 1 stamps the owning objective's frontmatter
`attention:` line (one `memory:` commit, no agent; no owning objective → no
write, the dashboard renders stale states on its own). Stage 2 — only with
`fallback_analyze.enabled` (default off) — sends items whose evidence age
exceeds `after_hours` (default 24 h) to the real analyze agent.

**All fixer-owned runtime state lives in `<project>/.fixer/`** (gitignored):
`host`, `ledger.jsonl`, `last_run`, `last_error`, `lock`, `daemon.lock`,
`cron.log`, `logs/`. Record writes serialize on the core lock at
`.research-note/state/record.lock`. The code directory holds only code + `config.json` defaults —
a `<project>/.fixer/config.json` shallow-overrides them per project. State
sits outside the code dir because a plugin install path carries a version
number and is replaced on upgrade; project state must survive that.

Headless fixer agents also need the workspace trusted in the selected agent.
Set `RESEARCH_NOTE_FIXER_AGENT=claude` or `codex` to force a backend; the
default chooses the agent that launched the session and otherwise prefers an
available Codex CLI. Both repair tiers remain disabled by default.

**Symptom if broken:** background scans and attention stamps stop, while edit
and commit lint still works — check the mtime of `.fixer/last_run` and the
contents of `.fixer/last_error`.

**Provenance rule:** the fixer never invents record content. E5 (anchored
Motivation) and E9 (Date) on an existing entry are repairable ONLY from
evidence (git history for the date, explicit references for the anchor);
when the evidence is not there, PARK the item for the user instead of
fabricating provenance.
