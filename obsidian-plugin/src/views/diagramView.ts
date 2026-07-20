import { ItemView, WorkspaceLeaf } from "obsidian";
import { VIEW_DIAGRAM } from "../constants";
import { CytoscapeHost } from "../diagram/cytoscapeHost";
import {
  buildDiagramGraph,
  templateImpact,
  templateModuleNeighborhood,
  templateUseCaseTrace,
} from "../model/diagramQuery";
import type GraceWorkbenchPlugin from "../main";
import type { DiagramDefinition } from "../types/snapshot";

export class DiagramView extends ItemView {
  private plugin: GraceWorkbenchPlugin;
  private host: CytoscapeHost | null = null;
  private cyEl: HTMLElement | null = null;
  private unsub: (() => void) | null = null;
  private lastKey = "";

  constructor(leaf: WorkspaceLeaf, plugin: GraceWorkbenchPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return VIEW_DIAGRAM;
  }
  getDisplayText(): string {
    return "Диаграмма GRACE";
  }
  getIcon(): string {
    return "git-fork";
  }

  async onOpen(): Promise<void> {
    const container = this.containerEl.children[1] as HTMLElement;
    container.empty();
    container.addClass("grace-workbench-root");

    const toolbar = container.createDiv({ cls: "grace-wb-toolbar" });
    toolbar.createEl("button", { text: "Вписать" }).onclick = () => this.host?.fit();
    toolbar.createEl("button", { text: "Layout" }).onclick = () => {
      this.lastKey = "";
      this.rebuild();
    };
    const depthSel = toolbar.createEl("select");
    for (const d of [1, 2, 3, 4]) {
      depthSel.createEl("option", { text: `глубина ${d}`, value: String(d) });
    }
    depthSel.value = String(this.plugin.store.getState().diagramFilter.depth);
    depthSel.onchange = () => {
      this.plugin.store.setDiagramFilter({ depth: Number(depthSel.value) });
      this.lastKey = "";
      this.rebuild();
    };

    const hostWrap = container.createDiv({ cls: "grace-diagram-host" });
    this.cyEl = hostWrap.createDiv({ cls: "cy" });
    const legend = hostWrap.createDiv({ cls: "grace-diagram-legend" });
    legend.setText(
      "Формы: UC — эллипс · Module — скругл. · File — прямоуг. · V — ромб · Req — hex\n" +
        "Рёбра: сплошная=declared · пунктир=inferred · красный пунктир=unresolved"
    );
    // simple minimap placeholder
    const mini = hostWrap.createDiv({ cls: "grace-minimap" });
    mini.setText("Обзор");

    this.host = new CytoscapeHost(this.cyEl, {
      onSelectNode: (id) => {
        const n = this.plugin.index?.nodeById.get(id);
        this.plugin.store.selectEntity(id, "diagram", { type: n?.type });
      },
      onSelectEdge: (id) => {
        this.plugin.store.selectEntity(
          this.plugin.store.getState().selectedEntityId,
          "diagram",
          { edgeId: id }
        );
      },
      onDblClickNode: (id) => this.plugin.openFocusedDiagram(id),
    });

    this.unsub = this.plugin.store.subscribe((_s, change) => {
      if (change === "selection") {
        const id = this.plugin.store.getState().selectedEntityId;
        if (id) this.host?.focus(id);
        // rebuild if selection changed roots implicitly
        this.maybeRebuildOnSelection();
      } else if (change === "diagram" || change === "diagramFilter" || change === "modelStatus") {
        this.lastKey = "";
        this.rebuild();
      }
    });
    await this.rebuild();
  }

  async onClose(): Promise<void> {
    this.unsub?.();
    this.host?.destroy();
    this.host = null;
    this.cyEl = null;
  }

  private maybeRebuildOnSelection(): void {
    const state = this.plugin.store.getState();
    if (!state.activeDiagramId && state.selectedEntityId) {
      // auto focused diagram
      this.lastKey = "";
      void this.rebuild();
    }
  }

  private resolveDefinition(): DiagramDefinition | null {
    const state = this.plugin.store.getState();
    const index = this.plugin.index;
    if (!index) return null;

    if (state.activeDiagramId) {
      const found = this.plugin.snapshot?.diagramsGenerated.diagrams.find(
        (d) => d.id === state.activeDiagramId
      );
      if (found) return found;
    }

    const id = state.selectedEntityId;
    if (!id) return null;
    const node = index.nodeById.get(id);
    if (!node) return null;
    if (node.type === "UseCase" || node.type === "Requirement") {
      return templateUseCaseTrace(id);
    }
    if (node.type === "Module") {
      return templateModuleNeighborhood(id);
    }
    return templateImpact(id);
  }

  private async rebuild(): Promise<void> {
    if (!this.host || !this.plugin.index) return;
    const def = this.resolveDefinition();
    if (!def) {
      return;
    }
    const depth = this.plugin.store.getState().diagramFilter.depth;
    const key = `${def.id}|${depth}|${def.rootEntityIds.join(",")}`;
    if (key === this.lastKey) {
      const sel = this.plugin.store.getState().selectedEntityId;
      if (sel) this.host.focus(sel);
      return;
    }
    this.lastKey = key;
    const g = buildDiagramGraph(this.plugin.index, def, { depthOverride: depth });
    const findings = new Map<string, number>();
    for (const n of g.nodes) {
      findings.set(n.id, this.plugin.index.findingsByNode.get(n.id)?.length || 0);
    }
    this.plugin.log.info("diagram build", {
      id: def.id,
      nodes: g.nodes.length,
      edges: g.edges.length,
    });
    await this.host.render(g.nodes, g.edges, {
      direction: this.plugin.store.getState().diagramFilter.direction,
      selectedId: this.plugin.store.getState().selectedEntityId,
      findingCounts: findings,
      manual: def.manualPositions,
      pinned: new Set(def.pinnedNodeIds || []),
    });
  }
}
