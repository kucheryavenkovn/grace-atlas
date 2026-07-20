import * as path from "path";
import * as vscode from "vscode";
import { VIEW_BROWSER } from "./constants";
import {
  templateImpact,
  templateModuleNeighborhood,
  templateUseCaseTrace,
} from "./model/diagramQuery";
import type { FrontendIndex } from "./model/indexes";
import { ModelLoaderService } from "./services/modelLoader";
import { WorkbenchStore } from "./state/workbenchStore";
import type { LoadedSnapshot } from "./types/snapshot";
import { BrowserTreeProvider } from "./views/browserTreeProvider";
import { WorkbenchPanel } from "./views/workbenchPanel";

let store: WorkbenchStore;
let loader: ModelLoaderService;
let snapshot: LoadedSnapshot | null = null;
let index: FrontendIndex | null = null;
let treeProvider: BrowserTreeProvider;
let statusBar: vscode.StatusBarItem;
let extensionUri: vscode.Uri;

function workspaceRoot(): string | null {
  const folder = vscode.workspace.workspaceFolders?.[0];
  return folder ? folder.uri.fsPath : null;
}

function modelRelative(): string {
  return (
    vscode.workspace.getConfiguration("graceWorkbench").get<string>("modelPath") ||
    ".grace-atlas/model"
  );
}

async function reloadModel(showNotice = true): Promise<void> {
  const root = workspaceRoot();
  if (!root) {
    store.setModelStatus("missing", "Open a workspace folder first");
    treeProvider.setModel(null, null);
    return;
  }
  store.setModelStatus("loading");
  const result = await loader.load(root, modelRelative());
  snapshot = result.snapshot;
  index = result.index;
  store.setModelStatus(
    result.status,
    result.error,
    result.snapshot?.manifest.modelHash ?? null
  );
  treeProvider.setModel(index, snapshot);
  updateStatusBar();
  if (showNotice) {
    if (result.error) {
      void vscode.window.showWarningMessage(`GRACE Workbench: ${result.error}`);
    } else if (result.snapshot) {
      void vscode.window.showInformationMessage(
        `GRACE model: ${result.snapshot.manifest.nodeCount} nodes / ${result.snapshot.manifest.edgeCount} edges`
      );
    }
  }
  WorkbenchPanel.current?.pushFullModel();
}

function updateStatusBar(): void {
  const st = store.getState();
  if (st.modelStatus === "ready" && snapshot) {
    statusBar.text = `$(layers) GRACE ${snapshot.manifest.nodeCount}n`;
    statusBar.tooltip = `hash ${snapshot.manifest.modelHash}\n${snapshot.modelDir}`;
  } else {
    statusBar.text = `$(layers) GRACE ${st.modelStatus}`;
    statusBar.tooltip = st.lastError || st.modelStatus;
  }
  statusBar.show();
}

/**
 * VS Code tree/context commands pass either a string id or a TreeItem-like object.
 */
function resolveEntityId(arg?: unknown): string | null {
  if (typeof arg === "string" && arg.trim()) {
    return arg.trim();
  }
  if (arg && typeof arg === "object") {
    const o = arg as { entityId?: unknown; id?: unknown; label?: unknown };
    if (typeof o.entityId === "string" && o.entityId.trim()) {
      return o.entityId.trim();
    }
    // TreeItem.id is sometimes set
    if (typeof o.id === "string" && o.id.trim() && !o.id.includes(" ")) {
      return o.id.trim();
    }
  }
  return store.getState().selectedEntityId;
}

function selectEntity(id: string, origin: string = "command"): void {
  if (!id) return;
  const node = index?.nodeById.get(id);
  store.selectEntity(id, origin as "command", { type: node?.type });
  treeProvider.refresh();
  WorkbenchPanel.current?.pushSelection();
}

interface ResolvedSource {
  absPath: string;
  line: number | null;
  kind: "code" | "xml" | "path";
}

/**
 * Prefer real code/XML file paths from the snapshot; fall back via implemented_in neighbors.
 */
function resolveSourceLocation(entityId: string): ResolvedSource | null {
  const root = workspaceRoot();
  if (!root || !index) return null;
  const node = index.nodeById.get(entityId);
  if (!node) return null;

  const tryPath = (raw: string | null | undefined, line: number | null): ResolvedSource | null => {
    if (!raw || typeof raw !== "string") return null;
    let p = raw.trim().replace(/\//g, path.sep);
    // Skip non-path provenance labels like "knowledge-graph"
    if (!p.includes(path.sep) && !p.includes("/") && !p.includes("\\") && !p.endsWith(".py") && !p.endsWith(".xml") && !p.endsWith(".md") && !p.endsWith(".json")) {
      if (!path.isAbsolute(p) && !p.startsWith(".")) {
        return null;
      }
    }
    if (p.startsWith("file:")) {
      p = p.slice("file:".length);
    }
    // vscode://file/D:/path:line  → extract path
    if (p.startsWith("vscode://file/")) {
      let rest = p.slice("vscode://file/".length);
      // strip trailing :line
      const m = rest.match(/^(.*?):(\d+)$/);
      if (m) {
        rest = m[1];
        if (line == null) line = Number(m[2]);
      }
      p = rest;
    }
    const abs = path.isAbsolute(p) ? p : path.resolve(root, p);
    return { absPath: abs, line, kind: abs.endsWith(".xml") ? "xml" : "code" };
  };

  // 1) Explicit links / source from snapshot
  const direct =
    tryPath(node.links?.sourceUri, node.source?.line ?? null) ||
    tryPath(node.source?.file, node.source?.line ?? null) ||
    tryPath(
      typeof node.properties?.path === "string" ? node.properties.path : null,
      node.source?.line ?? null
    );
  if (direct) return direct;

  // 2) SourceFile / TestFile: id often "file:rel/path"
  if (node.type === "SourceFile" || node.type === "TestFile") {
    const fromId = node.id.startsWith("file:") ? node.id.slice(5) : node.name || node.displayName;
    const hit = tryPath(fromId, null);
    if (hit) return hit;
  }

  // 3) Module → implemented_in → source file
  for (const e of index.outgoing.get(entityId) || []) {
    if (e.relation === "implemented_in" || e.relation === "has_contract" || e.relation === "has_block") {
      const nested = resolveSourceLocation(e.target);
      if (nested) return nested;
    }
  }
  // 4) Incoming implemented_in (file → module reverse already handled; module as target)
  for (const e of index.incoming.get(entityId) || []) {
    if (e.relation === "implemented_in") {
      const nested = resolveSourceLocation(e.source);
      if (nested) return nested;
    }
  }

  return null;
}

async function openSource(arg?: unknown): Promise<void> {
  const entityId = resolveEntityId(arg);
  if (!entityId) {
    void vscode.window.showWarningMessage("GRACE: select an entity first");
    return;
  }
  if (!index) {
    void vscode.window.showWarningMessage(
      "GRACE: model not loaded. Run snapshot build and GRACE: Reload Model"
    );
    return;
  }
  if (!index.nodeById.has(entityId)) {
    void vscode.window.showWarningMessage(`GRACE: entity not in model: ${entityId}`);
    return;
  }

  const loc = resolveSourceLocation(entityId);
  if (!loc) {
    void vscode.window.showWarningMessage(
      `GRACE: no openable file for ${entityId} (no source/XML path in snapshot)`
    );
    return;
  }

  const uri = vscode.Uri.file(loc.absPath);
  try {
    const doc = await vscode.workspace.openTextDocument(uri);
    const editor = await vscode.window.showTextDocument(doc, { preview: false, viewColumn: vscode.ViewColumn.Beside });
    if (loc.line != null && loc.line > 0) {
      const pos = new vscode.Position(Math.max(0, loc.line - 1), 0);
      editor.selection = new vscode.Selection(pos, pos);
      editor.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenter);
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    void vscode.window.showErrorMessage(`GRACE: cannot open ${loc.absPath} (${msg})`);
  }
}

function openImpact(entityId: string): void {
  const def = templateImpact(entityId);
  store.setActiveDiagram(def.id, def.type);
  selectEntity(entityId, "command");
  WorkbenchPanel.show(extensionUri, store, () => snapshot, () => index, panelHandlers());
}

function panelHandlers() {
  return {
    onSelect: (id: string, origin: string) => selectEntity(id, origin),
    onOpenSource: (id: string) => void openSource(id),
    onOpenImpact: (id: string) => openImpact(id),
    onBack: () => {
      store.goBack();
      treeProvider.refresh();
      WorkbenchPanel.current?.pushSelection();
    },
    onForward: () => {
      store.goForward();
      treeProvider.refresh();
      WorkbenchPanel.current?.pushSelection();
    },
  };
}

async function focusEntity(): Promise<void> {
  if (!index) {
    void vscode.window.showWarningMessage("Model not loaded");
    return;
  }
  const pick = await vscode.window.showQuickPick(
    [...index.nodeById.values()]
      .slice(0, 8000)
      .map((n) => ({
        label: n.id,
        description: `${n.type} · ${n.displayName}`,
        detail: n.status || undefined,
      })),
    {
      matchOnDescription: true,
      matchOnDetail: true,
      placeHolder: "Focus entity by ID or name (e.g. UC-001, M-APP-AUTO)…",
    }
  );
  if (!pick) return;
  selectEntity(pick.label, "command");
  openWorkbench();
}

function openWorkbench(): void {
  WorkbenchPanel.show(extensionUri, store, () => snapshot, () => index, panelHandlers());
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  extensionUri = context.extensionUri;

  store = new WorkbenchStore();
  loader = new ModelLoaderService();
  treeProvider = new BrowserTreeProvider(store);

  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  statusBar.command = "graceWorkbench.open";
  context.subscriptions.push(statusBar);

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider(VIEW_BROWSER, treeProvider)
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("graceWorkbench.open", async () => {
      await reloadModel(false);
      openWorkbench();
    }),
    vscode.commands.registerCommand("graceWorkbench.reload", () => reloadModel(true)),
    vscode.commands.registerCommand("graceWorkbench.focusEntity", () => focusEntity()),
    vscode.commands.registerCommand("graceWorkbench.openSource", async (arg?: unknown) => {
      await openSource(arg);
    }),
    vscode.commands.registerCommand("graceWorkbench.showTraceability", () => {
      openWorkbench();
      // webview defaults to problems; user switches tab — selection already set
    }),
    vscode.commands.registerCommand("graceWorkbench.showImpact", () => {
      const id = store.getState().selectedEntityId;
      if (id) openImpact(id);
      else void vscode.window.showInformationMessage("Select an entity first");
    }),
    vscode.commands.registerCommand("graceWorkbench.navigateBack", () => {
      store.goBack();
      treeProvider.refresh();
      WorkbenchPanel.current?.pushSelection();
    }),
    vscode.commands.registerCommand("graceWorkbench.navigateForward", () => {
      store.goForward();
      treeProvider.refresh();
      WorkbenchPanel.current?.pushSelection();
    }),
    vscode.commands.registerCommand("graceWorkbench.refreshTree", () => treeProvider.refresh()),
    vscode.commands.registerCommand("graceWorkbench.selectEntity", (arg?: unknown) => {
      const id = resolveEntityId(arg);
      if (!id) return;
      selectEntity(id, "tree");
      openWorkbench();
    }),
    vscode.commands.registerCommand("graceWorkbench.openDiagramId", (diagramId: string) => {
      const d = snapshot?.diagramsGenerated.diagrams.find((x) => x.id === diagramId);
      store.setActiveDiagram(diagramId, d?.type || null);
      if (d?.rootEntityIds?.[0]) selectEntity(d.rootEntityIds[0], "command");
      openWorkbench();
    })
  );

  // Prefer focused diagram templates when selecting modules/UCs from tree
  store.subscribe((state, change) => {
    if (change === "selection" && state.selectedEntityId && index) {
      const n = index.nodeById.get(state.selectedEntityId);
      if (!n) return;
      if (n.type === "UseCase" || n.type === "Requirement") {
        const def = templateUseCaseTrace(n.id);
        store.setActiveDiagram(def.id, def.type);
      } else if (n.type === "Module") {
        const def = templateModuleNeighborhood(n.id);
        store.setActiveDiagram(def.id, def.type);
      }
    }
    updateStatusBar();
  });

  const auto = vscode.workspace
    .getConfiguration("graceWorkbench")
    .get<boolean>("autoLoad");
  if (auto !== false) {
    await reloadModel(false);
  } else {
    updateStatusBar();
  }
}

export function deactivate(): void {
  WorkbenchPanel.current?.dispose();
}
