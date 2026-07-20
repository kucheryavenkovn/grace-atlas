import {
  Notice,
  Plugin,
  TFile,
  WorkspaceLeaf,
} from "obsidian";
import {
  VIEW_BROWSER,
  VIEW_DIAGNOSTICS,
  VIEW_DIAGRAM,
  VIEW_INSPECTOR,
} from "./constants";
import { FocusEntityModal } from "./commands/focusEntityModal";
import {
  templateImpact,
  templateModuleNeighborhood,
  templateUseCaseTrace,
} from "./model/diagramQuery";
import type { FrontendIndex } from "./model/indexes";
import { LogService } from "./services/logService";
import { ModelLoaderService } from "./services/modelLoader";
import { WorkbenchStore } from "./state/workbenchStore";
import type { LoadedSnapshot } from "./types/snapshot";
import { ModelBrowserView } from "./views/browserView";
import { DiagnosticsView } from "./views/diagnosticsView";
import { DiagramView } from "./views/diagramView";
import { InspectorView } from "./views/inspectorView";

interface PluginSettings {
  autoOpenWorkbench: boolean;
}

const DEFAULT_SETTINGS: PluginSettings = {
  autoOpenWorkbench: false,
};

export default class GraceWorkbenchPlugin extends Plugin {
  settings: PluginSettings = DEFAULT_SETTINGS;
  store = new WorkbenchStore();
  log = new LogService();
  loader!: ModelLoaderService;
  snapshot: LoadedSnapshot | null = null;
  index: FrontendIndex | null = null;
  diagnosticsTab: "problems" | "traceability" | "relations" | "history" | "log" = "problems";

  async onload(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    this.loader = new ModelLoaderService(this.app);

    this.registerView(VIEW_BROWSER, (leaf) => new ModelBrowserView(leaf, this));
    this.registerView(VIEW_DIAGRAM, (leaf) => new DiagramView(leaf, this));
    this.registerView(VIEW_INSPECTOR, (leaf) => new InspectorView(leaf, this));
    this.registerView(VIEW_DIAGNOSTICS, (leaf) => new DiagnosticsView(leaf, this));

    this.addCommand({
      id: "open-workbench",
      name: "GRACE: Open Workbench",
      callback: () => void this.openWorkbenchLayout(),
    });
    this.addCommand({
      id: "reload-model",
      name: "GRACE: Reload Model",
      callback: () => void this.reloadModel(),
    });
    this.addCommand({
      id: "focus-entity",
      name: "GRACE: Focus Entity",
      callback: () => this.openFocusModal(),
    });
    this.addCommand({
      id: "open-model-browser",
      name: "GRACE: Open Model Browser",
      callback: () => void this.activateView(VIEW_BROWSER, "left"),
    });
    this.addCommand({
      id: "open-diagram",
      name: "GRACE: Open Diagram",
      callback: () => void this.activateView(VIEW_DIAGRAM, "main"),
    });
    this.addCommand({
      id: "open-inspector",
      name: "GRACE: Open Inspector",
      callback: () => void this.activateView(VIEW_INSPECTOR, "right"),
    });
    this.addCommand({
      id: "open-diagnostics",
      name: "GRACE: Open Diagnostics",
      callback: () => void this.activateView(VIEW_DIAGNOSTICS, "main"),
    });
    this.addCommand({
      id: "open-vscode",
      name: "GRACE: Open Current Entity in VS Code",
      callback: () => {
        const id = this.store.getState().selectedEntityId;
        if (id) this.openVsCode(id);
      },
    });
    this.addCommand({
      id: "open-source",
      name: "GRACE: Open Current Entity Source",
      callback: () => {
        const id = this.store.getState().selectedEntityId;
        if (id) this.openSource(id);
      },
    });
    this.addCommand({
      id: "show-traceability",
      name: "GRACE: Show Traceability",
      callback: () => this.activateDiagnosticsTab("traceability"),
    });
    this.addCommand({
      id: "show-impact",
      name: "GRACE: Show Impact",
      callback: () => {
        const id = this.store.getState().selectedEntityId;
        if (id) this.openImpact(id);
      },
    });
    this.addCommand({
      id: "nav-back",
      name: "GRACE: Navigate Back",
      callback: () => this.store.goBack(),
    });
    this.addCommand({
      id: "nav-forward",
      name: "GRACE: Navigate Forward",
      callback: () => this.store.goForward(),
    });

    this.addRibbonIcon("layers", "GRACE Workbench", () => {
      void this.openWorkbenchLayout();
    });

    this.app.workspace.onLayoutReady(() => {
      void this.reloadModel();
    });

    this.log.info("plugin loaded");
  }

  onunload(): void {
    this.log.info("plugin unload");
  }

  async reloadModel(): Promise<void> {
    this.store.setModelStatus("loading");
    this.log.info("snapshot load start");
    const result = await this.loader.load();
    this.snapshot = result.snapshot;
    this.index = result.index;
    this.store.setModelStatus(
      result.status,
      result.error,
      result.snapshot?.manifest.modelHash ?? null
    );
    if (result.error) {
      this.log.warn("snapshot load issue", { error: result.error });
      new Notice(`GRACE Workbench: ${result.error}`);
    } else if (result.snapshot) {
      this.log.info("snapshot ready", {
        nodes: result.snapshot.manifest.nodeCount,
        edges: result.snapshot.manifest.edgeCount,
        hash: result.snapshot.manifest.modelHash,
      });
      new Notice(
        `GRACE model ready: ${result.snapshot.manifest.nodeCount} nodes / ${result.snapshot.manifest.edgeCount} edges`
      );
    }
  }

  async openWorkbenchLayout(): Promise<void> {
    await this.reloadModel();
    // Obsidian layout: left browser, main diagram, right inspector, main split diagnostics
    await this.activateView(VIEW_BROWSER, "left");
    await this.activateView(VIEW_DIAGRAM, "main");
    await this.activateView(VIEW_INSPECTOR, "right");
    // diagnostics as additional leaf in main split when possible
    const diagLeaf = this.app.workspace.getLeaf("split");
    await diagLeaf.setViewState({ type: VIEW_DIAGNOSTICS, active: false });
    this.log.info("workbench layout opened");
  }

  async activateView(type: string, place: "left" | "right" | "main"): Promise<void> {
    const { workspace } = this.app;
    let leaf: WorkspaceLeaf | null = null;
    const existing = workspace.getLeavesOfType(type);
    if (existing.length) {
      leaf = existing[0];
    } else {
      if (place === "left") leaf = workspace.getLeftLeaf(false);
      else if (place === "right") leaf = workspace.getRightLeaf(false);
      else leaf = workspace.getLeaf("tab");
      if (!leaf) leaf = workspace.getLeaf(true);
      await leaf.setViewState({ type, active: true });
    }
    workspace.revealLeaf(leaf);
  }

  openFocusModal(): void {
    if (!this.index) {
      new Notice("Model not loaded");
      return;
    }
    new FocusEntityModal(this.app, this.index, (node) => {
      this.store.selectEntity(node.id, "command", { type: node.type });
      void this.openWorkbenchLayout();
    }).open();
  }

  openFocusedDiagram(entityId: string): void {
    const node = this.index?.nodeById.get(entityId);
    if (!node) return;
    let def = templateImpact(entityId);
    if (node.type === "UseCase" || node.type === "Requirement") {
      def = templateUseCaseTrace(entityId);
    } else if (node.type === "Module") {
      def = templateModuleNeighborhood(entityId);
    }
    this.store.setActiveDiagram(def.id, def.type);
    this.store.selectEntity(entityId, "command", { type: node.type });
    void this.activateView(VIEW_DIAGRAM, "main");
  }

  openDiagram(diagramId: string): void {
    const d = this.snapshot?.diagramsGenerated.diagrams.find((x) => x.id === diagramId);
    this.store.setActiveDiagram(diagramId, d?.type || null);
    if (d?.rootEntityIds?.[0]) {
      const n = this.index?.nodeById.get(d.rootEntityIds[0]);
      this.store.selectEntity(d.rootEntityIds[0], "command", { type: n?.type });
    }
    void this.activateView(VIEW_DIAGRAM, "main");
  }

  openImpact(entityId: string): void {
    const def = templateImpact(entityId);
    this.store.setActiveDiagram(def.id, def.type);
    const n = this.index?.nodeById.get(entityId);
    this.store.selectEntity(entityId, "command", { type: n?.type });
    void this.activateView(VIEW_DIAGRAM, "main");
    this.activateDiagnosticsTab("traceability");
  }

  activateDiagnosticsTab(tab: DiagnosticsView extends never ? string : "traceability" | "problems" | "relations" | "history" | "log"): void {
    this.diagnosticsTab = tab;
    void this.activateView(VIEW_DIAGNOSTICS, "main").then(() => {
      const leaves = this.app.workspace.getLeavesOfType(VIEW_DIAGNOSTICS);
      for (const leaf of leaves) {
        const v = leaf.view;
        if (v instanceof DiagnosticsView) {
          v.setTab(tab);
        }
      }
    });
  }

  async openNote(entityId: string): Promise<void> {
    const node = this.index?.nodeById.get(entityId);
    const rel = node?.links?.obsidianNote;
    if (!rel) {
      new Notice("No note link for entity");
      return;
    }
    const file = this.app.vault.getAbstractFileByPath(rel);
    if (file instanceof TFile) {
      await this.app.workspace.getLeaf(false).openFile(file);
    } else {
      new Notice(`Note not found: ${rel}`);
    }
  }

  openSource(entityId: string): void {
    const node = this.index?.nodeById.get(entityId);
    const uri = node?.links?.sourceUri || node?.source?.file;
    if (!uri) {
      new Notice("No source path");
      return;
    }
    // Prefer vault-relative note for source files
    void this.openNote(entityId);
    this.log.info("open source", { entityId, uri });
  }

  openVsCode(entityId: string): void {
    const node = this.index?.nodeById.get(entityId);
    const uri = node?.links?.vscodeUri;
    if (!uri) {
      new Notice("No VS Code URI");
      return;
    }
    window.open(uri);
    this.log.info("open vscode", { entityId });
  }
}


