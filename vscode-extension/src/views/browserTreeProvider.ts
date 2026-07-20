import * as vscode from "vscode";
import { BROWSER_ROOTS, TYPE_ICONS } from "../constants";
import type { FrontendIndex } from "../model/indexes";
import type { WorkbenchStore } from "../state/workbenchStore";
import type { LoadedSnapshot, WorkbenchNode } from "../types/snapshot";

export type TreeNodeKind = "root" | "type" | "entity" | "diag-sev" | "diagram";

export class GraceTreeItem extends vscode.TreeItem {
  constructor(
    public readonly kind: TreeNodeKind,
    label: string,
    collapsible: vscode.TreeItemCollapsibleState,
    public readonly entityId?: string,
    public readonly meta?: string
  ) {
    super(label, collapsible);
  }
}

export class BrowserTreeProvider implements vscode.TreeDataProvider<GraceTreeItem> {
  private _onDidChange = new vscode.EventEmitter<GraceTreeItem | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChange.event;

  private index: FrontendIndex | null = null;
  private snapshot: LoadedSnapshot | null = null;

  constructor(private store: WorkbenchStore) {
    store.subscribe(() => this.refresh());
  }

  setModel(index: FrontendIndex | null, snapshot: LoadedSnapshot | null): void {
    this.index = index;
    this.snapshot = snapshot;
    this.refresh();
  }

  refresh(): void {
    this._onDidChange.fire();
  }

  getTreeItem(element: GraceTreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: GraceTreeItem): GraceTreeItem[] {
    if (!this.index) {
      const status = this.store.getState().modelStatus;
      const err = this.store.getState().lastError;
      return [
        new GraceTreeItem(
          "root",
          err || `Model: ${status}. Run snapshot build.`,
          vscode.TreeItemCollapsibleState.None
        ),
      ];
    }

    if (!element) {
      return BROWSER_ROOTS.map((r) => {
        const count = this.countRoot(r);
        const item = new GraceTreeItem(
          "root",
          `${r.label} (${count})`,
          count > 0
            ? vscode.TreeItemCollapsibleState.Collapsed
            : vscode.TreeItemCollapsibleState.None,
          undefined,
          r.id
        );
        item.contextValue = "graceRoot";
        return item;
      });
    }

    if (element.kind === "root" && element.meta) {
      const root = BROWSER_ROOTS.find((r) => r.id === element.meta);
      if (!root) return [];
      if (root.special === "diagnostics") {
        return (["error", "warning", "info"] as const).map((sev) => {
          const n = (this.snapshot?.diagnostics.findings || []).filter((f) => f.severity === sev)
            .length;
          const item = new GraceTreeItem(
            "diag-sev",
            `${sev} (${n})`,
            n > 0
              ? vscode.TreeItemCollapsibleState.Collapsed
              : vscode.TreeItemCollapsibleState.None,
            undefined,
            sev
          );
          return item;
        });
      }
      if (root.special === "diagrams") {
        const diagrams = (this.snapshot?.diagramsGenerated.diagrams || []).slice(0, 100);
        return diagrams.map((d) => {
          const item = new GraceTreeItem(
            "diagram",
            d.name,
            vscode.TreeItemCollapsibleState.None,
            d.rootEntityIds?.[0],
            d.id
          );
          item.command = {
            command: "graceWorkbench.openDiagramId",
            title: "Open diagram",
            arguments: [d.id],
          };
          item.contextValue = "graceDiagram";
          return item;
        });
      }
      // group by type
      const byType = new Map<string, WorkbenchNode[]>();
      for (const t of root.types || []) {
        for (const n of this.index.nodesByType.get(t) || []) {
          const list = byType.get(t) || [];
          list.push(n);
          byType.set(t, list);
        }
      }
      return [...byType.entries()]
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([type, nodes]) => {
          const item = new GraceTreeItem(
            "type",
            `${type} (${nodes.length})`,
            vscode.TreeItemCollapsibleState.Collapsed,
            undefined,
            type
          );
          item.contextValue = "graceType";
          return item;
        });
    }

    if (element.kind === "type" && element.meta) {
      const nodes = [...(this.index.nodesByType.get(element.meta) || [])].sort((a, b) =>
        a.id.localeCompare(b.id)
      );
      return nodes.slice(0, 500).map((n) => this.entityItem(n));
    }

    if (element.kind === "diag-sev" && element.meta) {
      const findings = (this.snapshot?.diagnostics.findings || [])
        .filter((f) => f.severity === element.meta)
        .slice(0, 100);
      const items: GraceTreeItem[] = [];
      for (const f of findings) {
        if (!f.entityId) continue;
        const n = this.index.nodeById.get(f.entityId);
        if (n) items.push(this.entityItem(n, f.code));
        else {
          const item = new GraceTreeItem(
            "entity",
            f.entityId,
            vscode.TreeItemCollapsibleState.None,
            f.entityId
          );
          item.description = f.code;
          item.contextValue = "graceEntity";
          item.command = {
            command: "graceWorkbench.selectEntity",
            title: "Select",
            arguments: [f.entityId],
          };
          items.push(item);
        }
      }
      return items;
    }

    return [];
  }

  private entityItem(n: WorkbenchNode, extra?: string): GraceTreeItem {
    const icon = TYPE_ICONS[n.type] || "•";
    const fc = this.index?.findingsByNode.get(n.id)?.length || 0;
    const label = `${icon} ${n.id}`;
    const item = new GraceTreeItem("entity", label, vscode.TreeItemCollapsibleState.None, n.id);
    item.description = [n.displayName, extra, fc ? `⚠${fc}` : ""].filter(Boolean).join(" · ");
    item.tooltip = `${n.type} ${n.id}\n${n.displayName}`;
    item.contextValue = "graceEntity";
    item.id = `entity:${n.id}`;
    item.command = {
      command: "graceWorkbench.selectEntity",
      title: "Select",
      arguments: [n.id],
    };
    // Inline "open source" icon — pass id string, not TreeItem-only
    item.resourceUri = undefined;
    const selected = this.store.getState().selectedEntityId === n.id;
    if (selected) {
      item.iconPath = new vscode.ThemeIcon("circle-filled");
    }
    return item;
  }

  private countRoot(root: (typeof BROWSER_ROOTS)[0]): number {
    if (!this.index) return 0;
    if (root.special === "diagnostics") {
      return this.snapshot?.diagnostics.findings.length || 0;
    }
    if (root.special === "diagrams") {
      return this.snapshot?.diagramsGenerated.diagrams.length || 0;
    }
    let n = 0;
    for (const t of root.types || []) {
      n += this.index.nodesByType.get(t)?.length || 0;
    }
    return n;
  }
}
