import { ItemView, Menu, WorkspaceLeaf } from "obsidian";
import { BROWSER_ROOTS, TYPE_ICONS, VIEW_BROWSER } from "../constants";
import type GraceWorkbenchPlugin from "../main";
import type { WorkbenchNode } from "../types/snapshot";

export class ModelBrowserView extends ItemView {
  private plugin: GraceWorkbenchPlugin;
  private rootEl: HTMLElement | null = null;
  private unsub: (() => void) | null = null;

  constructor(leaf: WorkspaceLeaf, plugin: GraceWorkbenchPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return VIEW_BROWSER;
  }
  getDisplayText(): string {
    return "Модель GRACE";
  }
  getIcon(): string {
    return "layers";
  }

  async onOpen(): Promise<void> {
    const container = this.containerEl.children[1] as HTMLElement;
    container.empty();
    container.addClass("grace-workbench-root");
    this.rootEl = container;
    this.unsub = this.plugin.store.subscribe(() => this.render());
    this.render();
  }

  async onClose(): Promise<void> {
    this.unsub?.();
    this.unsub = null;
    this.rootEl = null;
  }

  private render(): void {
    if (!this.rootEl) return;
    const el = this.rootEl;
    el.empty();
    const state = this.plugin.store.getState();
    const toolbar = el.createDiv({ cls: "grace-wb-toolbar" });
    const search = toolbar.createEl("input", {
      type: "search",
      attr: { placeholder: "Фильтр ID / имени…" },
      value: state.browserFilter.text,
    });
    search.oninput = () => {
      this.plugin.store.setBrowserFilter({ text: search.value });
    };
    const gapsBtn = toolbar.createEl("button", { text: state.browserFilter.withGapsOnly ? "Gaps ✓" : "Gaps" });
    gapsBtn.onclick = () =>
      this.plugin.store.setBrowserFilter({ withGapsOnly: !state.browserFilter.withGapsOnly });

    const status = toolbar.createSpan({
      cls: `grace-wb-status ${state.modelStatus}`,
      text: state.modelStatus,
    });
    void status;

    const tree = el.createDiv({ cls: "grace-tree" });
    const index = this.plugin.index;
    if (!index) {
      tree.createDiv({ cls: "grace-empty", text: state.lastError || "Модель не загружена" });
      return;
    }

    const filterText = state.browserFilter.text.trim().toLowerCase();
    const withGaps = state.browserFilter.withGapsOnly;

    const matchNode = (n: WorkbenchNode): boolean => {
      if (withGaps && !(n.tags || []).includes("has_gaps") && !(index.findingsByNode.get(n.id)?.length)) {
        return false;
      }
      if (!filterText) return true;
      const hay = `${n.id} ${n.displayName}`.toLowerCase();
      return hay.includes(filterText);
    };

    for (const root of BROWSER_ROOTS) {
      this.renderCategory(tree, root.id, root.label, root.types || [], root.special, matchNode, 0);
    }
  }

  private renderCategory(
    parent: HTMLElement,
    id: string,
    label: string,
    types: string[],
    special: "diagnostics" | "diagrams" | undefined,
    matchNode: (n: WorkbenchNode) => boolean,
    depth: number
  ): void {
    const state = this.plugin.store.getState();
    const index = this.plugin.index!;
    let children: WorkbenchNode[] = [];
    let count = 0;

    if (special === "diagnostics") {
      const findings = this.plugin.snapshot?.diagnostics.findings || [];
      count = findings.length;
    } else if (special === "diagrams") {
      count = this.plugin.snapshot?.diagramsGenerated.diagrams.length || 0;
    } else {
      for (const t of types) {
        for (const n of index.nodesByType.get(t) || []) {
          if (matchNode(n)) children.push(n);
        }
      }
      children.sort((a, b) => a.id.localeCompare(b.id));
      count = children.length;
    }

    if (count === 0 && !special) return;

    const expanded = state.expandedTreeNodes.has(id);
    const row = parent.createDiv({ cls: "grace-tree-node" });
    row.style.paddingLeft = `${6 + depth * 12}px`;
    row.createSpan({ cls: "grace-tree-twisty", text: expanded ? "▾" : "▸" });
    row.createSpan({ cls: "grace-tree-label", text: label });
    row.createSpan({ cls: "grace-tree-badge", text: String(count) });
    row.onclick = () => this.plugin.store.toggleExpanded(id);

    if (!expanded) return;

    if (special === "diagnostics") {
      const bySev = ["error", "warning", "info"] as const;
      for (const sev of bySev) {
        const findings = (this.plugin.snapshot?.diagnostics.findings || []).filter(
          (f) => f.severity === sev
        );
        if (!findings.length) continue;
        const sid = `diag-${sev}`;
        const open = state.expandedTreeNodes.has(sid);
        const r = parent.createDiv({ cls: "grace-tree-node" });
        r.style.paddingLeft = `${18 + depth * 12}px`;
        r.createSpan({ cls: "grace-tree-twisty", text: open ? "▾" : "▸" });
        r.createSpan({ cls: "grace-tree-label", text: sev });
        r.createSpan({ cls: `grace-tree-badge ${sev}`, text: String(findings.length) });
        r.onclick = () => this.plugin.store.toggleExpanded(sid);
        if (open) {
          // show sample entities
          const sample = findings.slice(0, 40);
          for (const f of sample) {
            if (!f.entityId) continue;
            const n = index.nodeById.get(f.entityId);
            this.renderEntityRow(parent, n || {
              id: f.entityId,
              type: "Finding",
              displayName: f.message.slice(0, 40),
              description: "",
              status: f.severity,
              properties: {},
              tags: [],
              source: null,
              links: {},
            }, depth + 2);
          }
        }
      }
      return;
    }

    if (special === "diagrams") {
      const diagrams = this.plugin.snapshot?.diagramsGenerated.diagrams || [];
      // group generated
      const gen = diagrams.filter((d) => d.createdFrom === "generated").slice(0, 80);
      for (const d of gen) {
        const r = parent.createDiv({ cls: "grace-tree-node" });
        r.style.paddingLeft = `${18 + depth * 12}px`;
        r.createSpan({ cls: "grace-tree-twisty", text: " " });
        r.createSpan({ cls: "grace-tree-label", text: d.name });
        r.onclick = (ev) => {
          ev.stopPropagation();
          this.plugin.openDiagram(d.id);
        };
      }
      return;
    }

    // group by type
    const byType = new Map<string, WorkbenchNode[]>();
    for (const n of children) {
      const list = byType.get(n.type) || [];
      list.push(n);
      byType.set(n.type, list);
    }
    for (const [type, nodes] of [...byType.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      const tid = `${id}:${type}`;
      const open = state.expandedTreeNodes.has(tid) || !!state.browserFilter.text;
      const r = parent.createDiv({ cls: "grace-tree-node" });
      r.style.paddingLeft = `${18 + depth * 12}px`;
      r.createSpan({ cls: "grace-tree-twisty", text: open ? "▾" : "▸" });
      r.createSpan({ cls: "grace-tree-label", text: type });
      r.createSpan({ cls: "grace-tree-badge", text: String(nodes.length) });
      r.onclick = (ev) => {
        ev.stopPropagation();
        this.plugin.store.toggleExpanded(tid);
      };
      if (!open) continue;
      // lazy: cap visible rows; filter narrows set
      const limit = state.browserFilter.text ? 200 : 80;
      for (const n of nodes.slice(0, limit)) {
        this.renderEntityRow(parent, n, depth + 2);
      }
      if (nodes.length > limit) {
        const more = parent.createDiv({ cls: "grace-tree-node" });
        more.style.paddingLeft = `${30 + depth * 12}px`;
        more.createSpan({
          cls: "grace-tree-label",
          text: `… ещё ${nodes.length - limit} (воспользуйтесь поиском)`,
        });
      }
    }
  }

  private renderEntityRow(parent: HTMLElement, n: WorkbenchNode, depth: number): void {
    const state = this.plugin.store.getState();
    const index = this.plugin.index!;
    const selected = state.selectedEntityId === n.id;
    const row = parent.createDiv({
      cls: `grace-tree-node${selected ? " selected" : ""}`,
    });
    row.style.paddingLeft = `${6 + depth * 12}px`;
    row.createSpan({ cls: "grace-tree-twisty", text: " " });
    const icon = TYPE_ICONS[n.type] || "•";
    row.createSpan({
      cls: "grace-tree-label",
      text: `${icon} ${n.id} — ${n.displayName || ""}`.slice(0, 80),
    });
    const fc = index.findingsByNode.get(n.id)?.length || 0;
    if (fc) {
      const sev = index.findingsByNode.get(n.id)!.some((f) => f.severity === "error")
        ? "error"
        : "warning";
      row.createSpan({ cls: `grace-tree-badge ${sev}`, text: String(fc) });
    }
    row.onclick = (ev) => {
      ev.stopPropagation();
      this.plugin.store.selectEntity(n.id, "browser", { type: n.type });
    };
    row.ondblclick = (ev) => {
      ev.stopPropagation();
      this.plugin.openFocusedDiagram(n.id);
    };
    row.oncontextmenu = (ev) => {
      ev.preventDefault();
      const menu = new Menu();
      menu.addItem((i) =>
        i.setTitle("Показать на диаграмме").onClick(() => this.plugin.openFocusedDiagram(n.id))
      );
      menu.addItem((i) =>
        i.setTitle("Открыть заметку").onClick(() => this.plugin.openNote(n.id))
      );
      menu.addItem((i) =>
        i.setTitle("Открыть исходник").onClick(() => this.plugin.openSource(n.id))
      );
      menu.addItem((i) =>
        i.setTitle("Трассируемость").onClick(() => {
          this.plugin.store.selectEntity(n.id, "browser", { type: n.type });
          this.plugin.activateDiagnosticsTab("traceability");
        })
      );
      menu.addItem((i) =>
        i.setTitle("Impact").onClick(() => this.plugin.openImpact(n.id))
      );
      menu.addItem((i) =>
        i.setTitle("Копировать ID").onClick(() => navigator.clipboard.writeText(n.id))
      );
      menu.showAtMouseEvent(ev);
    };
  }
}
