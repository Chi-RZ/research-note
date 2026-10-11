# Maintaining research-note

Run these commands from the repository root.

## Local development and releases

After releasing `0.1.0`, start the next cycle on your local `dev` branch and set
the development version once:

```bash
python3 tools/set_version.py 0.1.1-dev.1
```

This synchronizes the Claude and Codex plugin manifests and the Claude
marketplace entry. Daily edits need no further version changes. To try the
current checkout, including uncommitted plugin edits, update a test project:

```bash
bash plugins/research-note/scripts/update_projects.sh --source "$PWD/plugins/research-note" /path/to/project
```

The declared version and an automatic content digest identify each installation.
Source edits take effect only on the next update. Other projects keep their
selected builds; older development builds remain available in the shared store
and native caches.

When ready, merge dev into main and set the formal version:

```bash
python3 tools/set_version.py 0.1.1
```

Merging does not change the version automatically. Run the relevant checks,
commit the release and tag that commit `v0.1.1`. Published tags and version
contents stay fixed. Push main and the tag when publication is intended.
Projects can then use `--latest` (remote main) or `--version 0.1.1` (the tag).
For the initial public release, use `0.1.0` instead of the next-cycle examples.

After changing a contract template, refresh its migration history:

```bash
python3 plugins/research-note/scripts/contracts.py record-history
```

For installation changes, the optional native test also covers an actual dev
branch, repeated same-version builds, and the merge to a formal main release:

```bash
python3 plugins/research-note/scripts/tests/native_project_releases.py --workspace /path/to/test-workspace
```

It requires Claude, Codex, Git and uv, makes no model calls, and retains its
fixtures and native caches for inspection. Claude configuration is isolated;
temporary Codex trust entries are removed afterward.
