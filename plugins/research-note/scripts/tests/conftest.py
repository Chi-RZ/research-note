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
