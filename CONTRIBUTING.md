# Contributing

## Run the tests first — there is nothing to set up

```bash
pip install pytest
python -m pytest plugins/research-note/scripts/tests -q
```

373 tests, about 30 seconds. No dependencies beyond `pytest` itself: the code
is standard-library Python, POSIX shell and git. The suite builds its own
repositories and its own fake `HOME`, and it never calls the `claude` or `codex`
CLIs — every test that needs one stubs it. So it passes on a machine with
neither agent installed, which is also how CI runs it.

If that command is green on your machine, you can change anything here and know
whether you broke it.

## The one habit that matters

**Write the test first, and watch it fail against the unfixed code.** Not as
ceremony — as the only way to know the test tests the thing. Two of this
repo's own tests were written, passed immediately, and turned out to assert
nothing:

- one keyed on a phrase that the worst copy of the rule never used;
- one stubbed both sides of a two-sided lookup with the same value, so the run
  bailed before reaching the assertion and a conditional check never executed.

Both were caught by running the fixture by hand and reading what actually
happened. Neither would have been caught by a green suite.

So: make the change red, then make it green. Say in the commit message that you
did.

## Where the reasoning lives

`DESIGN.md` explains why the plugin has the shape it has — what a node, a page
and an entry are, why gates sit where they sit, why there are two agents. It is
the map. Read the section that governs whatever you are about to change.

It is also **under test**: `test_design_is_current.py` pins its census tables
(lint codes, scripts, hooks, skills) to the code. Add a lint code and DESIGN's
table goes red until you classify it. That is deliberate — the document went 28
releases out of date before anything watched it.

What the tests deliberately do NOT pin is the prose. Classification and
rationale are judgement; a test cannot grade them, and pretending otherwise
would make the document worse.

## Commit messages

`<type>(<scope>): <what changed and why it mattered> (<version>)`

```
fix(hpc): remote.sh forwards the phase binding, so a remote launch can record (0.29.1)
feat(lint): a commit touching src/ must leave src/INDEX.md current (0.29.0)
docs(design): DESIGN catches up to the machine, and is put under test (0.29.3)
```

The body is where this repo keeps its memory. Say what broke, how it was found,
and what it cost — those sentences end up quoted in code comments years later,
and they are the reason a stranger can tell a deliberate constraint from an
accident. `git log` is the best documentation here; keep it that way.

## Releasing

The version lives in **three** files and a test pins two of them:

```
.claude-plugin/marketplace.json
plugins/research-note/.claude-plugin/plugin.json
plugins/research-note/.codex-plugin/plugin.json
```

**Push is the channel, not the last tidying step.** Every agent's marketplace is
a clone of this repository's remote, so an unpushed commit is invisible to every
installation — including the author's own machine. Commit, push, then update.

`scripts/update_projects.sh` carries an installed version into every registered
project. Run it from the cache of the version you just published, not from a
checkout: it repoints `research-note.pluginRoot`, and a copy can only point at
what it can see.

## Scope

Bug reports are most useful with three things: the output of
`scripts/doctor.sh`, the plugin version, and which agent (Claude, Codex, or
both). Those three answer most of the first round of questions.

Changes that add a *mechanism* are worth discussing in an issue first — this
framework's own rule is that a gate belongs only where the failure it prevents
would otherwise be silent, and most good ideas are guidance, not gates.
