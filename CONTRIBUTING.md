# Contributing

Issues and pull requests are welcome. For larger changes, discuss the approach
in an issue first.

In a pull request, describe the problem, what changed and how you checked it.
Update the relevant documentation when behavior changes.

## Checks

For code changes, install the test dependencies and run the fast core suite:

```bash
python -m pip install pytest pyyaml
python -m pytest plugins/research-note/scripts/tests -q -m "not integration"
```

For setup, update, rollback, shell or Git/worktree changes, also run:

```bash
python -m pytest plugins/research-note/scripts/tests -q -m integration
```

These tests do not need Claude or Codex. Documentation-only changes need a
content and link check, not the Python suite.

## Releases

Use `python3 tools/set_version.py VERSION`, run the relevant checks, then commit
and tag `vVERSION`.
