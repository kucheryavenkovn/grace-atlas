import { ItemView, WorkspaceLeaf } from "obsidian";
import { VIEW_INSPECTOR } from "../constants";
import type GraceWorkbenchPlugin from "../main";

export class InspectorView extends ItemView {
  private plugin: GraceWorkbenchPlugin;
  private unsub: (() => void) | null = null;

  constructor(leaf: WorkspaceLeaf, plugin: GraceWorkbenchPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return VIEW_INSPECTOR;
  }
  getDisplayText(): string {
    return "GRACE Inspector";
  }
  getIcon(): string {
    return "info";
  }

  async onOpen(): Promise<void> {
    this.unsub = this.plugin.store.subscribe(() => this.render());
    this.render();
  }

  async onClose(): Promise<void> {
    this.unsub?.();
  }

  private render(): void {
    const container = this.containerEl.children[1] as HTMLElement;
    container.empty();
    container.addClass("grace-inspector");
    const state = this.plugin.store.getState();
    const index = this.plugin.index;
    if (!index) {
      container.createDiv({ cls: "grace-empty", text: "No model loaded" });
      return;
    }

    if (state.selectedEdgeId) {
      const edge = index.edgeById.get(state.selectedEdgeId);
      if (edge) {
        container.createEl("h3", { text: "Relation" });
        this.kv(container, {
          id: edge.id,
          relation: edge.relation,
          source: edge.source,
          target: edge.target,
          sourceState: edge.sourceState,
          resolutionState: edge.resolutionState,
          file: edge.provenance?.file || "",
          line: String(edge.provenance?.line ?? ""),
        });
        this.linkEntity(container, edge.source);
        this.linkEntity(container, edge.target);
        return;
      }
    }

    const id = state.selectedEntityId;
    if (!id) {
      container.createDiv({ cls: "grace-empty", text: "Select an entity" });
      return;
    }
    const node = index.nodeById.get(id);
    if (!node) {
      container.createDiv({ cls: "grace-empty", text: `Unknown entity ${id}` });
      return;
    }

    const findings = index.findingsByNode.get(id) || [];
    container.createEl("h3", { text: `${node.id}` });
    container.createDiv({ text: node.displayName });
    this.kv(container, {
      type: node.type,
      status: node.status || "—",
      findings: String(findings.length),
      sourceState: String(node.properties?.source_state || "declared"),
    });

    if (node.description) {
      container.createEl("h4", { text: "Description" });
      container.createDiv({ text: node.description });
    }

    container.createEl("h4", { text: "Properties" });
    const props: Record<string, string> = {};
    for (const [k, v] of Object.entries(node.properties || {})) {
      if (v == null) continue;
      const s = typeof v === "string" ? v : JSON.stringify(v);
      if (s.length > 200) props[k] = s.slice(0, 200) + "…";
      else props[k] = s;
    }
    this.kv(container, props);

    container.createEl("h4", { text: "Relations" });
    const out = index.outgoing.get(id) || [];
    const inc = index.incoming.get(id) || [];
    container.createDiv({ text: `Outgoing (${out.length})` });
    for (const e of out.slice(0, 40)) {
      const a = container.createDiv({ cls: "grace-rel-link" });
      a.setText(`→ [${e.relation}] ${e.target} (${e.sourceState})`);
      a.onclick = () => {
        const n = index.nodeById.get(e.target);
        this.plugin.store.selectEntity(e.target, "inspector", { type: n?.type });
      };
    }
    container.createDiv({ text: `Incoming (${inc.length})` });
    for (const e of inc.slice(0, 40)) {
      const a = container.createDiv({ cls: "grace-rel-link" });
      a.setText(`← [${e.relation}] ${e.source} (${e.sourceState})`);
      a.onclick = () => {
        const n = index.nodeById.get(e.source);
        this.plugin.store.selectEntity(e.source, "inspector", { type: n?.type });
      };
    }

    container.createEl("h4", { text: "Source" });
    this.kv(container, {
      file: node.source?.file || node.links?.sourceUri || "—",
      line: String(node.source?.line ?? "—"),
      note: node.links?.obsidianNote || "—",
      vscode: node.links?.vscodeUri || "—",
    });

    if (findings.length) {
      container.createEl("h4", { text: "Findings" });
      for (const f of findings.slice(0, 20)) {
        container.createDiv({
          cls: `grace-sev-${f.severity}`,
          text: `[${f.severity}] ${f.code}: ${f.message}`,
        });
      }
    }

    const actions = container.createDiv({ cls: "grace-actions" });
    actions.createEl("button", { text: "Focus Diagram" }).onclick = () =>
      this.plugin.openFocusedDiagram(id);
    actions.createEl("button", { text: "Open Note" }).onclick = () => this.plugin.openNote(id);
    actions.createEl("button", { text: "Open Source" }).onclick = () => this.plugin.openSource(id);
    actions.createEl("button", { text: "VS Code" }).onclick = () => this.plugin.openVsCode(id);
    actions.createEl("button", { text: "Traceability" }).onclick = () =>
      this.plugin.activateDiagnosticsTab("traceability");
    actions.createEl("button", { text: "Impact" }).onclick = () => this.plugin.openImpact(id);
    actions.createEl("button", { text: "Copy ID" }).onclick = () =>
      navigator.clipboard.writeText(id);
  }

  private kv(parent: HTMLElement, data: Record<string, string>): void {
    const grid = parent.createDiv({ cls: "grace-kv" });
    for (const [k, v] of Object.entries(data)) {
      grid.createDiv({ cls: "k", text: k });
      grid.createDiv({ cls: "v", text: v });
    }
  }

  private linkEntity(parent: HTMLElement, id: string): void {
    const a = parent.createDiv({ cls: "grace-rel-link", text: id });
    a.onclick = () => {
      const n = this.plugin.index?.nodeById.get(id);
      this.plugin.store.selectEntity(id, "inspector", { type: n?.type });
    };
  }
}
