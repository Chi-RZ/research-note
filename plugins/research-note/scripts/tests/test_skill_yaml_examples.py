"""A ```yaml example inside a skill must parse as YAML.

The wiki-compile frontmatter example shipped with two defects at once, both of
the kind that a reader copies verbatim and only discovers much later:

  sources:
    - tag:  gaussray_tn: per-amplitude cost of the two routes
      id:   03.014

The tag carries the `<node>: <entry name>` shape, and `": "` ends a plain YAML
scalar — the whole block is unparseable, and nothing says so until something
finally tries to read the file. The id is worse: `03.014` is a valid YAML
float, so it loads as `3.014` and `03.010` loads as `3.01`, colliding with
`03.01`. That one never raises at all.

The spec says these pages use "the same shape the record pages use so one
parser reads both", which is a promise a parser can check.
"""

import re
from pathlib import Path

import pytest

# The ONE third-party import in the suite, and it is not optional to the point
# of this file: the defect being caught is that `03.014` is a valid YAML FLOAT
# and loads as 3.014, which only a real YAML parser sees. A hand-rolled reader
# would pass the very block that broke.
#
# importorskip rather than a plain import: a bare `import yaml` turns a missing
# package into a COLLECTION error, and pytest then abandons the whole run —
# 372 unrelated tests lost to one absent dependency, which is what CI reported.
# A skip is loud in the summary and costs nothing else.
yaml = pytest.importorskip("yaml", reason="PyYAML: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent.parent
BLOCK = re.compile(r"```yaml\n(.*?)```", re.DOTALL)


def blocks():
    for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
        for i, body in enumerate(BLOCK.findall(skill.read_text())):
            # Examples are indented under a bullet; YAML needs them flush.
            lines = [ln for ln in body.split("\n")]
            pad = min((len(ln) - len(ln.lstrip())
                       for ln in lines if ln.strip()), default=0)
            yield skill.relative_to(ROOT), i, "\n".join(ln[pad:] for ln in lines)


def test_there_are_examples_to_check():
    assert list(blocks()), "no ```yaml blocks found — the regex stopped matching"


@pytest.mark.parametrize("rel,i,text", [(a, b, c) for a, b, c in blocks()],
                         ids=lambda v: str(v) if not isinstance(v, str) else "")
def test_yaml_example_parses(rel, i, text):
    doc = text.strip()
    if doc.startswith("---"):                 # frontmatter fences
        doc = doc.strip("-\n")
    try:
        loaded = yaml.safe_load(doc)
    except yaml.YAMLError as e:
        pytest.fail(f"{rel} block {i} does not parse: {e}")
    if isinstance(loaded, dict):
        for s in loaded.get("sources") or []:
            if isinstance(s, dict) and "id" in s:
                assert isinstance(s["id"], str), (
                    f"{rel} block {i}: id {s['id']!r} loaded as "
                    f"{type(s['id']).__name__}, not a string — quote it")
