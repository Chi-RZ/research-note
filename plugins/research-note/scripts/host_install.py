"""Install the selected release through native hosts without global enablement."""
from __future__ import annotations

import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time


def claude(project: Path, *args: str):
    result = subprocess.run(["claude", "plugin", *args, "--json"], cwd=project,
                            capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise ValueError(f"Claude plugin {' '.join(args)} failed: {result.stderr or result.stdout}")
    return json.loads(result.stdout)


def codex_skills(project: Path) -> dict:
    """Discover and materialize project plugins; respect native project trust."""
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(["codex", "app-server", "--stdio"], cwd=project,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log)
        pending = b""

        def rpc(number, method, params):
            nonlocal pending
            process.stdin.write((json.dumps({"id": number, "method": method, "params": params}) + "\n").encode())
            process.stdin.flush()
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    message = json.loads(line)
                    if message.get("id") == number:
                        if "error" in message:
                            raise ValueError(f"Codex {method}: {message['error']}")
                        return message["result"]
                ready, _, _ = select.select([process.stdout], [], [], max(0, deadline - time.monotonic()))
                if ready:
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        raise ValueError("Codex app-server stopped before plugin verification")
                    pending += chunk
            raise ValueError(f"Codex {method} timed out")

        try:
            rpc(1, "initialize", {"clientInfo": {"name": "research-note-update", "version": "0.1.0"},
                                  "capabilities": {"experimentalApi": True}})
            process.stdin.write(b'{"method":"initialized"}\n')
            process.stdin.flush()
            rpc(2, "plugin/list", {"cwds": [str(project)], "marketplaceKinds": ["local"]})
            return rpc(3, "skills/list", {"cwds": [str(project)], "forceReload": True})
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            process.stdin.close()
            process.stdout.close()


def sync_hosts(project: Path, pin: dict, root: Path) -> dict:
    """Verify native installation or explicitly report absent/untrusted hosts.

    Claude's registry records project scope. Codex materializes project config
    via app-server rather than `plugin add`, which would enable it globally.
    A native install record is not evidence that an existing session reloaded.
    """
    from project_runtime import write_json
    selector = pin["selector"]
    report = {"selector": selector, "version": pin["version"], "sha256": pin["sha256"]}
    newly_installed = False
    try:
        if shutil.which("claude"):
            before = claude(project, "list")
            matching = [p for p in before if p.get("id") == selector and p.get("scope") == "project"
                        and p.get("projectPath") == str(project)]
            claude(project, "marketplace", "add", str(root.parents[1]), "--scope", "project")
            newly_installed = not matching
            claude(project, "install", selector, "--scope", "project")
            installed = claude(project, "list")
            entries = [p for p in installed if p.get("id") == selector and p.get("scope") == "project"
                       and p.get("projectPath") == str(project) and p.get("enabled") is True]
            if not entries or entries[0].get("version") != pin["version"]:
                raise ValueError("Claude native project installation differs from selected release")
            entry = entries[0]
            actual = Path(entry.get("readFromFolder") or entry["installPath"])
            if not actual.is_dir():
                raise ValueError("Claude installed plugin source is missing")
            if actual.resolve() != root.resolve():
                from project_runtime import digest
                if digest(actual) != pin["sha256"]:
                    raise ValueError("Claude installed content differs from selected release")
            report["claude"] = {"status": "installed", "source": str(actual), "cache": entry.get("installPath")}
        else:
            report["claude"] = {"status": "pending", "reason": "CLI absent; project configuration prepared"}
        if shutil.which("codex"):
            data = codex_skills(project)
            loaded = [skill for row in data.get("data", []) for skill in row.get("skills", [])
                      if skill.get("pluginId") == selector]
            expected = {p.parent.name: p for p in (root / "skills").glob("*/SKILL.md")}
            if loaded:
                paths = {Path(skill["path"]).parent.name: Path(skill["path"]) for skill in loaded}
                if set(paths) != set(expected) or any(paths[name].read_bytes() != src.read_bytes()
                                                      for name, src in expected.items()):
                    raise ValueError("Codex loaded skills differ from selected release")
                caches = {p.parents[2] for p in paths.values()}
                from project_runtime import digest
                if len(caches) != 1 or any(digest(cache) != pin["sha256"] for cache in caches):
                    raise ValueError("Codex installed content differs from selected release")
                report["codex"] = {"status": "loaded", "cache": str(next(iter(caches))),
                                    "skills": sorted(str(p) for p in paths.values())}
            else:
                report["codex"] = {"status": "pending", "reason": "project configuration not loaded; check native trust and plugin diagnostics"}
        else:
            report["codex"] = {"status": "pending", "reason": "CLI absent; project configuration prepared"}
        from project_runtime import check
        if (project / ".research-note/plugin-lock.json").exists():
            errors = check(project)
            if errors:
                raise ValueError("native installation changed project bindings: " + "; ".join(errors))
        write_json(project / ".research-note/state/host-install.json", report)
    except BaseException as failure:
        if newly_installed:
            # Remove only the new project-scoped registration. An immutable
            # shared marketplace/cache can remain for another project's use.
            try:
                claude(project, "uninstall", selector, "--scope", "project")
            except (OSError, ValueError, subprocess.SubprocessError) as cleanup:
                raise ValueError(f"{failure}; could not remove the new Claude project registration: {cleanup}") from failure
        raise
    for host in ("claude", "codex"):
        entry = report[host]
        print(f"{host}: {entry['status']}" + (f" — {entry['reason']}" if entry.get("reason") else ""))
    return report
