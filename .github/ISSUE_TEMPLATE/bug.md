---
name: Bug report
about: Something behaves differently from what the docs say
---

**What happened, and what you expected instead**

**The three things that answer most follow-up questions**

```
# plugin version
claude plugin list        # or: codex plugin list

# the wiring check — run inside the affected project
bash "$(git config --get research-note.pluginRoot)/scripts/doctor.sh"
```

- Agent: Claude / Codex / both
- OS: Linux / macOS

**How to reproduce**, as far as you can narrow it.
