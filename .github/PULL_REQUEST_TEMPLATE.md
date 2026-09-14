**What changes, and what it cost when it was wrong**

**Did the test fail before the fix?** Say so — a test written after the fix and
never seen red is the failure mode this repo has hit twice.

- [ ] `python -m pytest plugins/research-note/scripts/tests -q` is green
- [ ] Version bumped in all three manifests, if this is a release
