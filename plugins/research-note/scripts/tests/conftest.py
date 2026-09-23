"""The linters resolve ROOT at import via projroot (hard exit 2 outside a
project). Point both provider-neutral and legacy project-dir overrides at a
throwaway valid project BEFORE any test module imports them, so the suite runs
from anywhere."""

import os
import tempfile
from pathlib import Path

_fake = Path(tempfile.mkdtemp(prefix="rn-fake-project-"))
(_fake / "project_memory").mkdir()
(_fake / ".claude").mkdir()
(_fake / ".claude" / "framework.json").write_text(
    '{"framework": "research-note", "record": "v3"}')
os.environ["RESEARCH_NOTE_PROJECT_DIR"] = str(_fake)
os.environ["CLAUDE_PROJECT_DIR"] = str(_fake)

# Every record commit now starts a detached dashboard refresh. Off for the whole
# suite, so no background process writes into a test's repository while it
# asserts; the tests about the refresh turn it back on themselves.
os.environ["RN_NO_DASHBOARD_REFRESH"] = "1"
