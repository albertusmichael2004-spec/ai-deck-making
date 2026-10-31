// Studio for VS Code.
// Run: starts run.py with the project venv directly in a terminal, so it does not
// wait for the Python extension's interpreter discovery (70-240 s after a window
// opens on this machine).
// Deck Preview: shows the Studio working deck in a webview and records click
// annotations through the Studio CLI (`studio annotate ...`). The extension never
// edits decks itself; revisions still run through Studio's QA-gated workflows.
const vscode = require("vscode");
const childProcess = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const WATCH_INTERVAL_MS = 2000;

function studioRoot() {
  for (const folder of vscode.workspace.workspaceFolders || []) {
    if (fs.existsSync(path.join(folder.uri.fsPath, ".studio-root"))) return folder.uri.fsPath;
  }
  return null;
}

function projectPython(root) {
  const venv = path.join(root, ".venv", "Scripts", "python.exe");
  return fs.existsSync(venv) ? venv : "python";
}

let studioTerminal = null;

function runInTerminal(root, others) {
  if (studioTerminal && studioTerminal.exitStatus === undefined) {
    studioTerminal.show();
    return;
  }
  if (studioTerminal) studioTerminal.dispose();
  // The terminal process is Python itself: no shell profile or venv activation runs first.
  studioTerminal = vscode.window.createTerminal({
    name: others ? "Studio (Others)" : "Studio",
    cwd: root,
    shellPath: projectPython(root),
    shellArgs: [path.join(root, "run.py"), "--in-terminal", ...(others ? ["--others"] : [])],
    env: { PYTHONUTF8: "1" },
  });
  studioTerminal.show();
}

function runStudio(root, args) {
  const python = projectPython(root);
  const env = Object.assign({}, process.env, {
    PYTHONUTF8: "1",
    PYTHONPATH: [path.join(root, "src"), path.join(root, "runtime", "python_packages")].join(path.delimiter),
  });
  return new Promise((resolve, reject) => {
    const child = childProcess.spawn(python, ["-m", "cli.main", "--root", root, ...args], { cwd: root, env, windowsHide: true });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => (stderr += chunk));
    child.on("error", reject);
    child.on("close", (code) => {
      let value = null;
      try { value = JSON.parse(stdout); } catch (error) { /* reported below */ }
      if (code === 0 && value !== null) return resolve(value);
      const message = value && value.message ? value.message : (stderr.trim().split("\n").pop() || "Studio command failed");
      reject(new Error(message));
    });
  });
}

class PreviewPanel {
  static current = null;

  static async show(context, root, projectId) {
    if (PreviewPanel.current && PreviewPanel.current.projectId === projectId) {
      PreviewPanel.current.panel.reveal(vscode.ViewColumn.Beside);
      return PreviewPanel.current;
    }
    if (PreviewPanel.current) PreviewPanel.current.panel.dispose();
    PreviewPanel.current = new PreviewPanel(context, root, projectId);
    await PreviewPanel.current.load(false);
    return PreviewPanel.current;
  }

  constructor(context, root, projectId) {
    this.root = root;
    this.projectId = projectId;
    this.canonical = null;
    this.loading = null;
    this.panel = vscode.window.createWebviewPanel("studioDeckPreview", "Deck Preview: " + projectId, vscode.ViewColumn.Beside, {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.file(root), vscode.Uri.joinPath(context.extensionUri, "media")],
    });
    this.panel.webview.html = this.html(context);
    this.panel.webview.onDidReceiveMessage((message) => this.receive(message));
    this.panel.onDidDispose(() => {
      this.unwatch();
      if (PreviewPanel.current === this) PreviewPanel.current = null;
    });
  }

  html(context) {
    const webview = this.panel.webview;
    const media = (name) => webview.asWebviewUri(vscode.Uri.joinPath(context.extensionUri, "media", name));
    const nonce = crypto.randomBytes(16).toString("hex");
    return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${webview.cspSource}; style-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="${media("preview.css")}"><title>Deck Preview</title></head>
<body><div id="app"></div><script nonce="${nonce}" src="${media("preview.js")}"></script></body></html>`;
  }

  post(message) { this.panel.webview.postMessage(message); }

  async load(refresh) {
    if (this.loading) return this.loading;
    this.post({ type: "status", text: refresh ? "Re-rendering slides with PowerPoint…" : "Preparing preview (first render can take a minute)…", busy: true });
    this.loading = vscode.window.withProgress({ location: vscode.ProgressLocation.Window, title: "Studio deck preview" }, async () => {
      try {
        const preview = await runStudio(this.root, ["annotate", "preview", this.projectId, ...(refresh ? ["--refresh"] : [])]);
        for (const slide of preview.slides) slide.src = this.panel.webview.asWebviewUri(vscode.Uri.file(slide.image)).toString();
        this.watch(preview.canonical);
        this.post({ type: "preview", preview });
        await this.annotations();
      } catch (error) {
        this.post({ type: "status", text: error.message, error: true });
      } finally {
        this.loading = null;
      }
    });
    return this.loading;
  }

  async annotations() {
    const value = await runStudio(this.root, ["annotate", "list", this.projectId]);
    this.post({ type: "annotations", annotations: value.annotations });
  }

  // Polling is deliberate: projects/ is excluded from VS Code file watching and
  // OneDrive replaces files in ways native watchers can miss.
  watch(canonical) {
    if (this.canonical === canonical) return;
    this.unwatch();
    this.canonical = canonical;
    fs.watchFile(canonical, { interval: WATCH_INTERVAL_MS }, (current, previous) => {
      if (current.mtimeMs !== previous.mtimeMs || current.size !== previous.size) this.load(false);
    });
  }

  unwatch() {
    if (this.canonical) fs.unwatchFile(this.canonical);
    this.canonical = null;
  }

  async receive(message) {
    try {
      if (message.type === "refresh") return await this.load(true);
      if (message.type === "save") {
        const args = ["annotate", "add", this.projectId, "--slide=" + message.slideId, "--text=" + message.text];
        for (const objectId of message.objectIds) args.push("--object=" + objectId);
        if (message.region) args.push("--region=" + message.region.map((value) => value.toFixed(4)).join(","));
        await runStudio(this.root, args);
        this.post({ type: "saved" });
        return await this.annotations();
      }
      if (message.type === "mark") {
        await runStudio(this.root, ["annotate", message.status === "done" ? "done" : "dismiss", this.projectId, ...message.ids.map((id) => "--id=" + id)]);
        return await this.annotations();
      }
      if (message.type === "copyRequest") {
        const text = `Revise Studio project ${this.projectId} using my pending deck annotations. Run \`studio annotate request ${this.projectId}\`, change only the annotated objects, then mark them done after the revision passes QA.`;
        await vscode.env.clipboard.writeText(text);
        vscode.window.showInformationMessage("Revision request copied. Paste it into Claude Code, Codex or the Studio chat.");
      }
    } catch (error) {
      this.post({ type: "status", text: error.message, error: true });
    }
  }
}

async function chooseProject(root) {
  const listing = await runStudio(root, ["project", "list"]);
  const projects = listing.projects.filter((row) => row.deck_exists);
  if (!projects.length) throw new Error("No Studio project has a working deck yet. Import a target PPTX first.");
  if (projects.length === 1) return projects[0].project_id;
  const items = projects
    .map((row) => ({ label: row.name || row.project_id, description: row.project_id === listing.active_project ? "active" : row.category, detail: row.target_name || row.canonical, projectId: row.project_id }))
    .sort((a, b) => (b.description === "active") - (a.description === "active"));
  const picked = await vscode.window.showQuickPick(items, { placeHolder: "Choose the deck to preview" });
  return picked ? picked.projectId : null;
}

function activate(context) {
  const root = studioRoot();
  if (!root) return;
  const open = async () => {
    try {
      const projectId = await chooseProject(root);
      if (projectId) await PreviewPanel.show(context, root, projectId);
    } catch (error) {
      vscode.window.showErrorMessage("Deck Preview: " + error.message);
    }
  };
  context.subscriptions.push(
    vscode.commands.registerCommand("studio.run", () => runInTerminal(root, false)),
    vscode.commands.registerCommand("studio.runOthers", () => runInTerminal(root, true)),
    vscode.commands.registerCommand("studioPreview.open", open),
    vscode.commands.registerCommand("studioPreview.refresh", () => (PreviewPanel.current ? PreviewPanel.current.load(true) : open())),
    vscode.window.onDidCloseTerminal((terminal) => { if (terminal === studioTerminal) studioTerminal = null; }),
  );
  // Shows the fast Run action on run.py/main.py's editor ▷ button (see package.json menus).
  vscode.commands.executeCommand("setContext", "studio.workspace", true);
  const buttons = [
    ["$(play) Studio", "Start AI Presentation Studio (project venv, no interpreter discovery wait)", "studio.run", 51],
    ["$(preview) Deck Preview", "Open the Studio working deck and annotate it", "studioPreview.open", 50],
  ];
  for (const [text, tooltip, command, priority] of buttons) {
    const button = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, priority);
    Object.assign(button, { text, tooltip, command });
    button.show();
    context.subscriptions.push(button);
  }
}

function deactivate() {
  if (PreviewPanel.current) PreviewPanel.current.unwatch();
}

module.exports = { activate, deactivate };
