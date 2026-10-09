# The environment contract

Read this when a project develops a library of its own, uses Julia, needs a
second platform, or pins CUDA — the plain path in `SKILL.md` needs none of it.

A spec file in the repo describes the environment, and each machine rebuilds
its own from that file. **No machine is ever compared against another.**
Platform variation lives inside the packages — wheels chosen by markers, JLL
artifacts chosen by architecture — so one spec resolves correctly everywhere,
and what still differs (BLAS backend, CUDA, CPU arch) is written into the log
header rather than aligned.

| language | spec file (committed) | each machine runs | drift shows as |
|---|---|---|---|
| Python | `uv.lock` + `pyproject.toml` | `uv sync` | `uv sync --check` |
| Julia | `Manifest.toml` + `Project.toml` | `Pkg.instantiate()` | a dep whose `source` is missing |

The venv is per machine and never synced: it holds architecture-bound
binaries. Recorded runs use `uv run --no-sync` — a syncing run rewrites
`uv.lock` on any host whose checkout depth differs, dirtying the clone and the
log header's SHA anchor.

## Two checks, and only two

- **Each machine matches its own spec**, checked where the job runs. This is
  what makes a recorded result re-derivable, and it needs no second machine.
- **A library the project is developing** is identified by a commit, not a
  version string — a version stays put across a fortnight of edits. Choose one
  source mode deliberately:

  1. **Git pin — preferred for recorded runs on more than one machine.** Pin a
     fetchable Git remote plus `rev`, moved explicitly by `scripts/bump_lib.sh`.
     The remote can be GitHub, GitLab, a private SSH server or a bare Git repo;
     the SHA belongs to Git, not to GitHub.
  2. **Project workspace — preferred when no external remote exists.** Put the
     library in this repository as a uv workspace member. It stays editable,
     travels with the project, and the project commit identifies both.
  3. **Path editable — development or an intentionally mirrored checkout.**
     Edits take effect at once, but the path is not provenance. The checkout
     must itself be clean Git; for remote runs declare `LIB_<name>_LOCAL` and
     `LIB_<name>_<HOSTKEY>` in `.claude/hpc.env`, and `remote.sh push` holds
     both sides to the same pushed commit. If no shared remote can transport
     that commit, move the library into the project workspace before a formal
     remote run.

  A source tree with neither a Git commit nor a committed project copy is fine
  for a quick smoke, but not for a recorded result: another machine cannot
  identify the bytes that ran.

```toml
[tool.uv.sources]
mylib = { git = "ssh://git@github.com/user/mylib.git", rev = "<sha>" }
```

For local co-development, `uv add --editable ../mylib` records a path source.
Before switching it to a Git pin, commit and push the library, replace the path
source with `git` + `rev`, and run `uv lock`. Changing the pin does not reopen
old entries or schedule a benchmark grid: inspect the diff and run only the
affected sentinel unless the objective explicitly asks for broader coverage.

## A second environment must contain the first

One dependency that exists on only one platform makes a single file unusable —
MKL has no aarch64 build, so a Manifest carrying it fails to instantiate on a
Mac. A variant may therefore exist and may only ADD: every package of the base
appears in it at the same version. Doctor and every push check that
containment file-to-file in git (`JULIA_PROJECT` + `JULIA_PROJECT_VARIANTS` in
`.claude/hpc.env`).

## Consistency across machines

At setup, instantiate on every side and see each report clean. At submit,
`remote.sh push` brings the far side up first (`uv sync`, `Pkg.instantiate()`)
and only then checks, so a host that is merely behind is repaired rather than
reported; what survives is a real difference and stops the submit. A check
that cannot establish its premise — no uv or julia on the far side, the host
unreachable — reports `cannot verify` and asks.

## Pinning rules

- Pin the full dependency list to exact versions taken from a known-good env
  (`uv pip list` there).
- **CUDA jax**: pin `jax-cuda12-plugin[with-cuda]` and `jax-cuda12-pjrt` to the
  exact jax version — plain `jax[cuda12]` leaves the plugin range loose and can
  silently fall back to CPU. Verify with
  `uv run python -c "import jax; print(jax.devices())"` (inside `srun` on
  Slurm) — it must show a CUDA device.
- Julia: commit both tomls, and keep the environment out of the cluster's
  sparse cone if the cluster maintains its own copy — then refresh the mirror
  in the repo by copying the two files back, never by resolving twice.
