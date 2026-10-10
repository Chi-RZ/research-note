# Contributing

Issues and pull requests are welcome. For a substantial behavior change,
please open an issue first so the intended scope is clear.

## Tests

Install the test dependencies:

```bash
python -m pip install pytest pyyaml
```

For parser, policy and configuration changes, run the fast core suite:

```bash
python -m pytest plugins/research-note/scripts/tests -q -m "not integration"
```

If the change touches shell entrypoints, Git transactions, setup, update,
rollback or worktrees, also run the integration suite:

```bash
python -m pytest plugins/research-note/scripts/tests -q -m integration
```

The tests do not require Claude Code or Codex to be installed.
Documentation-only changes do not need the Python suite.

## Pull requests

Describe the problem, the resulting behavior and how you checked it. Update the
relevant documentation when behavior changes. Keep unrelated changes in
separate pull requests.

When changing a contract or workflow, explain the invariant in the code and
update the user-facing documentation that relies on it.

## Maintainer release steps

Keep the version equal in:

```text
.claude-plugin/marketplace.json
plugins/research-note/.claude-plugin/plugin.json
plugins/research-note/.codex-plugin/plugin.json
```

After changing a contract template, refresh its migration history:

```bash
python3 plugins/research-note/scripts/contracts.py record-history
```

Commit and push the release before testing an update from the public
marketplace.
