// Q Dashboard — render project_memory/dashboard.html in a webview and let its
// jump links open q-pages in an editor tab.
//
// The dashboard HTML is fully self-contained (inline CSS+JS, no external
// resources), so we just read it and hand it to the webview. The dashboard's
// ↗ links post a {path,line} message (via acquireVsCodeApi) on click; we
// listen below and open the q-page at that line in an editor tab — natively,
// over Remote-SSH, no host alias, no command: URIs.

const vscode = require('vscode');
const fs = require('fs');
const path = require('path');

let panel = null;
let timer = null;
let watcher = null;
let lastHtml = '';

const MARKERS = [path.join('.claude', 'framework.json'),
                 path.join('.claude', 'roles.json')];   // pre-v0.4 projects
function hasMarker(dir) { return MARKERS.some(m => fs.existsSync(path.join(dir, m))); }

function wsRoot() {
  const folders = vscode.workspace.workspaceFolders;
  return folders && folders.length ? folders[0].uri.fsPath : process.cwd();
}

// The workspace root is not necessarily the project root — opening the PARENT of the
// repo is a normal thing to do, and then every path built from wsRoot() misses by one
// level. Locate the project by its marker file instead: the workspace itself, else an
// immediate child. gen_dashboard.py already resolves its own root from __file__; this
// makes the extension side agree.
function projectRoot() {
  const ws = wsRoot();
  if (hasMarker(ws)) return ws;
  try {
    for (const d of fs.readdirSync(ws, { withFileTypes: true })) {
      if (d.isDirectory() && hasMarker(path.join(ws, d.name))) {
        return path.join(ws, d.name);
      }
    }
  } catch (e) { /* unreadable workspace dir — fall through to ws */ }
  return ws;
}

function dashboardPath() {
  return path.join(projectRoot(), 'project_memory', 'dashboard.html');
}

function readDashboard() {
  try { return fs.readFileSync(dashboardPath(), 'utf8'); } catch (e) { return ''; }
}

// qdash is a pure VIEWER: the fixer regenerates dashboard.html every cycle, so
// this extension never executes framework code. That removes the whole class of
// failure where a moved/renamed generator left the panel showing STALE, and it
// makes the extension immune to plugin upgrades.
//
// Freshness = watch the file. fs.watch alone is unreliable across editors and
// network filesystems (rename-replace writes, missed events), so a slow mtime
// poll backs it up; both paths funnel through the same content-compare, which
// keeps the user's scroll position when nothing actually changed.
function startAutoRefresh() {
  lastHtml = readDashboard();
  const reloadIfChanged = () => {
    if (!panel) return;
    const html = readDashboard();
    if (html && html !== lastHtml) { lastHtml = html; loadHtml(); }
  };
  try {
    watcher = fs.watch(dashboardPath(), { persistent: false }, reloadIfChanged);
  } catch (e) { watcher = null; }        // file not generated yet — the poll covers it
  timer = setInterval(reloadIfChanged, 15000);
}

function stopAutoRefresh() {
  if (timer) { clearInterval(timer); timer = null; }
  if (watcher) { try { watcher.close(); } catch (e) { /* already gone */ } watcher = null; }
}

async function openAt(p, line) {
  if (!p) return;
  const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(p));
  const ed = await vscode.window.showTextDocument(doc, {
    viewColumn: vscode.ViewColumn.Beside, preview: false
  });
  if (line && line > 0) {
    const pos = new vscode.Position(line - 1, 0);
    ed.selection = new vscode.Selection(pos, pos);
    ed.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.AtTop);
  }
}

function esc(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
}

function loadHtml() {
  if (!panel) return;
  const p = dashboardPath();
  let html;
  try {
    html = fs.readFileSync(p, 'utf8');
    // Freshness is the FILE's age, not this extension's bookkeeping: the fixer
    // owns regeneration, so an old file means the fixer is behind (its own
    // heartbeat check inside the board says why) — never that a viewer failed.
    const ageMin = (Date.now() - fs.statSync(p).mtimeMs) / 60000;
    if (ageMin > 30) {
      html = `<div style="font-family:sans-serif;padding:.6em 1em;background:#7a2020;color:#fff">
        <b>Board is ${ageMin.toFixed(0)} min old</b> — the fixer regenerates it every
        cycle, so check the fixer heartbeat in <code>.fixer/last_run</code>.</div>` + html;
    }
  } catch (e) {
    html = `<html><body style="font-family:sans-serif;padding:2em">
      <h2>Q Dashboard</h2><p>Could not read <code>${esc(p)}</code></p>
      <p>The fixer writes this file every cycle. Not there yet? Run one cycle by
      hand: <code>bash .fixer/run.sh</code></p>
      </body></html>`;
  }
  // The panel may have been disposed (tab closed) between the !panel guard and
  // here, or while an async step was awaited — writing .webview.html on
  // a disposed panel throws "Webview is disposed". Swallow it and clean up.
  try {
    panel.webview.html = html;
  } catch (e) {
    panel = null;
    stopAutoRefresh();
  }
}

// Wire a (new or restored) webview panel: dispose/message handlers, load the
// current HTML, start the 10s auto-refresh. Shared by open + deserialize.
function wirePanel(p, context) {
  panel = p;
  panel.onDidDispose(() => { stopAutoRefresh(); panel = null; }, null, context.subscriptions);
  panel.webview.onDidReceiveMessage(
    (msg) => { if (msg && msg.path) openAt(msg.path, msg.line); },
    null, context.subscriptions
  );
  loadHtml();
  startAutoRefresh();
}

// ---- Ecosystem wiki (same webview pattern; pages live in <project>/wiki/pages) ----

let wikiPanel = null;
let wikiDirOverride = '';   // user-picked pages dir when the marker scan can't see the project

function wikiPagesDir() {
  const d = path.join(projectRoot(), 'wiki', 'pages');
  if (fs.existsSync(path.join(d, 'index.html'))) return d;
  if (wikiDirOverride && fs.existsSync(path.join(wikiDirOverride, 'index.html'))) return wikiDirOverride;
  return '';
}

// Wiki pages are plain static HTML with ONLY relative <a> links: `*.html` between
// node pages, `../../...` out to Q-pages/scripts/logs (kept relative so the wiki
// repo stays portable — no machine-specific absolute paths). A webview follows
// neither — inject a click router: page links re-render in place, everything else
// is resolved against wiki/pages and opened in an editor tab (the same channel the
// dashboard's jump links use). The legacy `file://` branch stays for pages
// generated before the switch to relative links.
const WIKI_JS = `<script>
const vscodeApi = acquireVsCodeApi();
document.addEventListener('click', (e) => {
  const a = e.target && e.target.closest ? e.target.closest('a') : null;
  if (!a) return;
  const href = a.getAttribute('href') || '';
  e.preventDefault();
  if (href.startsWith('file://')) {
    vscodeApi.postMessage({ path: decodeURI(href.replace(/^file:\\/\\//, '')) });
  } else if (href.endsWith('.html')) {
    vscodeApi.postMessage({ nav: href });
  } else if (href) {
    vscodeApi.postMessage({ rel: decodeURI(href) });
  }
});
</script>`;

function loadWikiPage(page) {
  if (!wikiPanel) return;
  const dir = wikiPagesDir();
  let html;
  if (!dir) {
    html = `<html><body style="font-family:sans-serif;padding:2em">
      <h2>Ecosystem Wiki</h2><p>No <code>wiki/pages/index.html</code> found under the
      project root — the rendered-wiki pump is parked on this branch, so there is
      nothing to view yet.</p>
      </body></html>`;
  } else {
    try {
      html = fs.readFileSync(path.join(dir, path.basename(page)), 'utf8') + WIKI_JS;
    } catch (e) {
      html = `<html><body style="font-family:sans-serif;padding:2em">
        <p>Could not read <code>${esc(page)}</code></p></body></html>`;
    }
  }
  try { wikiPanel.webview.html = html; } catch (e) { wikiPanel = null; }
}

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand('qdash.openWiki', async () => {
      if (!wikiPagesDir()) {
        // marker scan can't see the project from this workspace — let the user point at it
        const pick = await vscode.window.showOpenDialog({
          canSelectFiles: false, canSelectFolders: true,
          title: 'Select the wiki/pages folder of your project'
        });
        if (pick && pick.length) wikiDirOverride = pick[0].fsPath;
      }
      if (wikiPanel) {
        try { wikiPanel.reveal(vscode.ViewColumn.One); loadWikiPage('index.html'); return; }
        catch (e) { wikiPanel = null; }
      }
      wikiPanel = vscode.window.createWebviewPanel(
        'qdashwiki', 'Ecosystem Wiki', vscode.ViewColumn.One,
        { enableScripts: true, retainContextWhenHidden: true }
      );
      wikiPanel.onDidDispose(() => { wikiPanel = null; }, null, context.subscriptions);
      wikiPanel.webview.onDidReceiveMessage((msg) => {
        if (!msg) return;
        if (msg.nav) loadWikiPage(msg.nav);
        else if (msg.rel) openAt(path.resolve(wikiPagesDir(), msg.rel), msg.line);
        else if (msg.path) openAt(msg.path, msg.line);
      }, null, context.subscriptions);
      loadWikiPage('index.html');
    }),

    vscode.commands.registerCommand('qdash.open', async () => {
      if (panel) {
        // Reuse the existing panel — unless it was disposed while an async step
        // awaited (reveal on a disposed panel throws "Webview is disposed").
        try { panel.reveal(vscode.ViewColumn.One); loadHtml(); return; }
        catch (e) { panel = null; stopAutoRefresh(); }
      }
      wirePanel(vscode.window.createWebviewPanel(
        'qdash', 'Q Dashboard', vscode.ViewColumn.One,
        { enableScripts: true, retainContextWhenHidden: true }
      ), context);
    }),

    // force a reload from disk (bypasses the content-change gate)
    vscode.commands.registerCommand('qdash.refresh', () => { lastHtml = readDashboard(); loadHtml(); }),

    vscode.commands.registerCommand('qdash.goto', (arg) => {
      if (arg && arg.path) openAt(arg.path, arg.line);
    })
  );

  // After a window reload VSCode restores the webview tab with its stale
  // serialized HTML and does NOT re-run the extension — register a serializer
  // so the restored panel re-hydrates (reload from disk + restart the watcher).
  if (vscode.window.registerWebviewPanelSerializer) {
    context.subscriptions.push(
      vscode.window.registerWebviewPanelSerializer('qdash', {
        async deserializeWebviewPanel(p) { wirePanel(p, context); }
      })
    );
  }
}

function deactivate() {}

module.exports = { activate, deactivate };
