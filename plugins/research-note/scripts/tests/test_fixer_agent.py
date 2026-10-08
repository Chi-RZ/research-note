import importlib.util
from pathlib import Path
from types import SimpleNamespace


PLUGIN = Path(__file__).resolve().parents[2]


def _load(monkeypatch, project: Path):
    (project / "project_memory").mkdir()
    (project / ".claude").mkdir()
    (project / ".claude" / "framework.json").write_text("{}\n")
    monkeypatch.setenv("RESEARCH_NOTE_PROJECT_DIR", str(project))
    spec = importlib.util.spec_from_file_location(
        "research_note_fixer_cycle_test", PLUGIN / "fixer" / "fixer_cycle.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _config():
    return {"model": "sonnet", "max_turns": 7, "timeout_min": 3}


def test_fixer_can_launch_codex(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    monkeypatch.setenv("RESEARCH_NOTE_FIXER_AGENT", "codex")
    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/bin/{name}")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(stdout="done", stderr="", returncode=0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    rundir = tmp_path / "logs"
    rundir.mkdir()
    assert mod.run_agent("format", _config(), "repair this", rundir) == "done"
    cmd, kwargs = calls[0]
    assert cmd[:4] == ["codex", "exec", "--ephemeral", "-C"]
    assert cmd[-2:] == ["--approve-for-me", "repair this"]
    assert "--sandbox" not in cmd and "-s" not in cmd
    assert kwargs["cwd"] == tmp_path
    assert kwargs["timeout"] == 180


def test_fixer_can_launch_claude(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    monkeypatch.setenv("RESEARCH_NOTE_FIXER_AGENT", "claude")
    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/bin/{name}")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(stdout="done", stderr="", returncode=0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    rundir = tmp_path / "logs"
    rundir.mkdir()
    mod.run_agent("format", _config(), "repair this", rundir)
    assert calls[0] == [
        "claude", "-p", "repair this", "--model", "sonnet",
        "--max-turns", "7", "--permission-mode", "acceptEdits",
    ]


def test_disabled_dashboard_does_not_start_a_renderer(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    config = tmp_path / ".research-note/project.json"
    config.parent.mkdir(exist_ok=True)
    config.write_text('{"features": {"dashboard": false}}')
    calls = []
    def track_run(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(mod.subprocess, "run", track_run)
    mod.regen_dashboard()
    assert calls == [], "disabled dashboard launched a process"
