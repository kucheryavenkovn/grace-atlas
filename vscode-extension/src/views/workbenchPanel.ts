import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import type { FrontendIndex } from "../model/indexes";
import type { WorkbenchStore } from "../state/workbenchStore";
import type { LoadedSnapshot } from "../types/snapshot";

export class WorkbenchPanel {
  public static current: WorkbenchPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];
  private unsub: (() => void) | null = null;

  private constructor(
    panel: vscode.WebviewPanel,
    private extensionUri: vscode.Uri,
    private store: WorkbenchStore,
    private getSnapshot: () => LoadedSnapshot | null,
    private getIndex: () => FrontendIndex | null,
    private handlers: {
      onSelect: (id: string, origin: string) => void;
      onOpenSource: (id: string) => void;
      onOpenImpact: (id: string) => void;
      onBack: () => void;
      onForward: () => void;
    }
  ) {
    this.panel = panel;
    this.panel.webview.html = this.getHtml(this.panel.webview);
    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

    this.panel.webview.onDidReceiveMessage(
      (msg: { type: string; id?: string; origin?: string; depth?: number }) => {
        switch (msg.type) {
          case "ready":
            this.pushFullModel();
            break;
          case "select":
            if (msg.id) this.handlers.onSelect(msg.id, msg.origin || "diagram");
            break;
          case "openSource":
            // Always pass string id (extension resolves TreeItem separately)
            if (typeof msg.id === "string" && msg.id) this.handlers.onOpenSource(msg.id);
            break;
          case "impact":
            if (msg.id) this.handlers.onOpenImpact(msg.id);
            break;
          case "back":
            this.handlers.onBack();
            break;
          case "forward":
            this.handlers.onForward();
            break;
          case "setDepth":
            if (typeof msg.depth === "number") {
              this.store.setDiagramFilter({ depth: msg.depth });
              this.pushSelection();
            }
            break;
          default:
            break;
        }
      },
      null,
      this.disposables
    );

    this.unsub = this.store.subscribe((_s, change) => {
      if (change === "selection" || change === "diagram" || change === "diagramFilter") {
        this.pushSelection();
      }
      if (change === "modelStatus") {
        this.pushFullModel();
      }
    });
  }

  static show(
    extensionUri: vscode.Uri,
    store: WorkbenchStore,
    getSnapshot: () => LoadedSnapshot | null,
    getIndex: () => FrontendIndex | null,
    handlers: WorkbenchPanel["handlers"]
  ): WorkbenchPanel {
    if (WorkbenchPanel.current) {
      WorkbenchPanel.current.panel.reveal(vscode.ViewColumn.One);
      WorkbenchPanel.current.pushFullModel();
      return WorkbenchPanel.current;
    }

    const panel = vscode.window.createWebviewPanel(
      "graceWorkbench",
      "GRACE Workbench",
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(extensionUri, "dist")],
      }
    );

    WorkbenchPanel.current = new WorkbenchPanel(
      panel,
      extensionUri,
      store,
      getSnapshot,
      getIndex,
      handlers
    );
    return WorkbenchPanel.current;
  }

  pushFullModel(): void {
    const snap = this.getSnapshot();
    const state = this.store.getState();
    void this.panel.webview.postMessage({
      type: "model",
      status: state.modelStatus,
      error: state.lastError,
      modelHash: state.modelHash,
      depth: state.diagramFilter.depth,
      selectedEntityId: state.selectedEntityId,
      snapshot: snap
        ? {
            manifest: snap.manifest,
            nodes: snap.model.nodes,
            edges: snap.model.edges,
            findings: snap.diagnostics.findings,
            diagrams: snap.diagramsGenerated.diagrams,
          }
        : null,
    });
  }

  pushSelection(): void {
    const state = this.store.getState();
    void this.panel.webview.postMessage({
      type: "selection",
      selectedEntityId: state.selectedEntityId,
      selectedEdgeId: state.selectedEdgeId,
      activeDiagramId: state.activeDiagramId,
      depth: state.diagramFilter.depth,
      history: state.navigationHistory,
      historyIndex: state.historyIndex,
    });
  }

  dispose(): void {
    WorkbenchPanel.current = undefined;
    this.unsub?.();
    this.panel.dispose();
    while (this.disposables.length) {
      this.disposables.pop()?.dispose();
    }
  }

  private getHtml(webview: vscode.Webview): string {
    const scriptUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.extensionUri, "dist", "webview.js")
    );
    const csp = [
      "default-src 'none'",
      `style-src ${webview.cspSource} 'unsafe-inline'`,
      `script-src ${webview.cspSource}`,
      `img-src ${webview.cspSource} data:`,
      `font-src ${webview.cspSource} data:`,
    ].join("; ");

    // Ensure webview bundle exists (dev hint)
    const bundlePath = path.join(this.extensionUri.fsPath, "dist", "webview.js");
    const bundleNote = fs.existsSync(bundlePath) ? "" : "<!-- webview.js missing: run npm run build -->";

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>GRACE Workbench</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: var(--vscode-editor-background);
      --fg: var(--vscode-editor-foreground);
      --border: var(--vscode-panel-border, #444);
      --muted: var(--vscode-descriptionForeground);
      --accent: var(--vscode-focusBorder);
      --list-hover: var(--vscode-list-hoverBackground);
      --list-active: var(--vscode-list-activeSelectionBackground);
      --error: var(--vscode-errorForeground, #f66);
      --warn: var(--vscode-editorWarning-foreground, #db0);
      font-family: var(--vscode-font-family);
      font-size: 12px;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; height: 100%; background: var(--bg); color: var(--fg); }
    #app { display: flex; flex-direction: column; height: 100%; }
    .toolbar {
      display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
      padding: 6px 8px; border-bottom: 1px solid var(--border);
    }
    .toolbar input[type="search"] {
      flex: 1; min-width: 140px;
      background: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      border: 1px solid var(--vscode-input-border, var(--border));
      padding: 4px 8px;
    }
    button {
      background: var(--vscode-button-secondaryBackground, #3a3a3a);
      color: var(--vscode-button-secondaryForeground, #fff);
      border: none; padding: 4px 8px; cursor: pointer; border-radius: 2px;
    }
    button:hover { filter: brightness(1.1); }
    .status { opacity: 0.85; font-size: 11px; }
    .status.ready { color: #6c6; }
    .status.missing, .status.invalid, .status.incompatible { color: var(--error); }
    .main {
      flex: 1; display: grid;
      grid-template-columns: 260px 1fr 300px;
      grid-template-rows: 1fr 220px;
      min-height: 0;
    }
    .browser { grid-row: 1 / 3; border-right: 1px solid var(--border); overflow: auto; }
    .diagram { border-bottom: 1px solid var(--border); position: relative; min-height: 0; }
    .inspector { border-left: 1px solid var(--border); overflow: auto; padding: 8px; }
    .bottom { grid-column: 2 / 4; border-top: 1px solid var(--border); display: flex; flex-direction: column; min-height: 0; }
    .pane-title {
      padding: 4px 8px; font-weight: 600; border-bottom: 1px solid var(--border);
      background: var(--vscode-sideBar-background, transparent);
    }
    .tree-node {
      padding: 2px 8px; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .tree-node:hover { background: var(--list-hover); }
    .tree-node.selected { background: var(--list-active); }
    .tree-node.cat { opacity: 0.9; font-weight: 600; }
    #cy { width: 100%; height: calc(100% - 28px); }
    .tabs { display: flex; gap: 4px; padding: 4px 6px; border-bottom: 1px solid var(--border); }
    .tab { padding: 2px 8px; cursor: pointer; border-radius: 3px; opacity: 0.8; }
    .tab.active { background: var(--accent); color: #fff; opacity: 1; }
    .tab-body { flex: 1; overflow: auto; padding: 6px 8px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 2px 6px; border-bottom: 1px solid var(--border); vertical-align: top; }
    tr.clickable:hover { background: var(--list-hover); cursor: pointer; }
    .sev-error { color: var(--error); font-weight: 600; }
    .sev-warning { color: var(--warn); }
    .kv { display: grid; grid-template-columns: 100px 1fr; gap: 2px 8px; margin: 6px 0; }
    .kv .k { opacity: 0.7; }
    .rel { color: var(--accent); cursor: pointer; display: block; padding: 1px 0; }
    .rel:hover { text-decoration: underline; }
    .empty { opacity: 0.65; font-style: italic; padding: 12px; }
    .legend {
      position: absolute; right: 8px; bottom: 8px; font-size: 10px; opacity: 0.85;
      background: var(--bg); border: 1px solid var(--border); padding: 4px 6px; max-width: 200px;
    }
  </style>
</head>
<body>
  ${bundleNote}
  <div id="app">
    <div class="toolbar">
      <input id="search" type="search" placeholder="Filter / jump ID…" />
      <button id="btnBack" title="Back">←</button>
      <button id="btnFwd" title="Forward">→</button>
      <label>depth
        <select id="depth">
          <option value="1">1</option>
          <option value="2">2</option>
          <option value="3" selected>3</option>
          <option value="4">4</option>
        </select>
      </label>
      <button id="btnFit">Fit</button>
      <button id="btnSource">Open Source</button>
      <button id="btnImpact">Impact</button>
      <span id="status" class="status">loading</span>
    </div>
    <div class="main">
      <div class="browser">
        <div class="pane-title">Model Browser</div>
        <div id="tree"></div>
      </div>
      <div class="diagram">
        <div class="pane-title">Diagram</div>
        <div id="cy"></div>
        <div class="legend">solid=declared · dashed=inferred · red=unresolved</div>
      </div>
      <div class="inspector">
        <div class="pane-title">Inspector</div>
        <div id="inspector" class="empty">Select an entity</div>
      </div>
      <div class="bottom">
        <div class="tabs">
          <span class="tab active" data-tab="problems">Problems</span>
          <span class="tab" data-tab="trace">Traceability</span>
          <span class="tab" data-tab="history">History</span>
        </div>
        <div id="bottom" class="tab-body"></div>
      </div>
    </div>
  </div>
  <script src="${scriptUri}"></script>
</body>
</html>`;
  }
}
