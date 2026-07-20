import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import type { WorkbenchEdge, WorkbenchNode } from "../types/snapshot";
import { layoutElk, layoutGrid, type LayoutPositions } from "./layout";
import { TYPE_ICONS } from "../constants";

export interface CyHostOptions {
  onSelectNode: (id: string) => void;
  onSelectEdge: (id: string) => void;
  onDblClickNode: (id: string) => void;
}

function shapeForType(type: string): string {
  switch (type) {
    case "UseCase":
      return "ellipse";
    case "Module":
      return "round-rectangle";
    case "SourceFile":
    case "TestFile":
      return "rectangle";
    case "Verification":
      return "diamond";
    case "Requirement":
      return "hexagon";
    case "Phase":
      return "tag";
    default:
      return "round-rectangle";
  }
}

function edgeStyle(sourceState: string, resolution: string): Partial<cytoscape.Css.Edge> {
  if (resolution === "unresolved") {
    return { "line-style": "dashed", "line-color": "#c44", "target-arrow-color": "#c44" };
  }
  if (sourceState === "inferred") {
    return { "line-style": "dashed", "line-color": "#888", "target-arrow-color": "#888" };
  }
  if (sourceState === "derived") {
    return { "line-style": "solid", "line-color": "#6a8", "target-arrow-color": "#6a8", opacity: 0.75 };
  }
  return { "line-style": "solid", "line-color": "#4a7ab5", "target-arrow-color": "#4a7ab5" };
}

export class CytoscapeHost {
  private cy: Core | null = null;
  private container: HTMLElement;
  private opts: CyHostOptions;

  constructor(container: HTMLElement, opts: CyHostOptions) {
    this.container = container;
    this.opts = opts;
  }

  destroy(): void {
    if (this.cy) {
      this.cy.destroy();
      this.cy = null;
    }
  }

  getCy(): Core | null {
    return this.cy;
  }

  async render(
    nodes: WorkbenchNode[],
    edges: WorkbenchEdge[],
    opts?: {
      direction?: "RIGHT" | "DOWN";
      selectedId?: string | null;
      findingCounts?: Map<string, number>;
      manual?: LayoutPositions;
      pinned?: Set<string>;
    }
  ): Promise<void> {
    let positions: LayoutPositions;
    try {
      positions = await layoutElk(nodes, edges, {
        direction: opts?.direction || "RIGHT",
        manual: opts?.manual,
        pinned: opts?.pinned,
      });
    } catch {
      positions = layoutGrid(nodes);
    }

    const findings = opts?.findingCounts || new Map<string, number>();
    const elements: ElementDefinition[] = [];
    for (const n of nodes) {
      const icon = TYPE_ICONS[n.type] || n.type.slice(0, 2);
      const fc = findings.get(n.id) || 0;
      const label = `${icon} ${n.id}\n${(n.displayName || "").slice(0, 28)}${fc ? ` ⚠${fc}` : ""}`;
      elements.push({
        data: {
          id: n.id,
          label,
          type: n.type,
          status: n.status,
        },
        position: positions[n.id] || { x: 0, y: 0 },
      });
    }
    for (const e of edges) {
      elements.push({
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          label: e.relation,
          sourceState: e.sourceState,
          resolutionState: e.resolutionState,
        },
      });
    }

    if (this.cy) {
      this.cy.destroy();
      this.cy = null;
    }

    this.cy = cytoscape({
      container: this.container,
      elements,
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "text-wrap": "wrap",
            "text-max-width": "140px",
            "font-size": 10,
            "text-valign": "center",
            "text-halign": "center",
            width: 150,
            height: 46,
            "background-color": "#2b3a4a",
            color: "#e8eef5",
            "border-width": 2,
            "border-color": "#6a8fb5",
            shape: "round-rectangle",
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-color": "#f0c040",
            "border-width": 3,
            "background-color": "#3a4f66",
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            label: "data(label)",
            "font-size": 8,
            color: "#9ab",
            "text-rotation": "autorotate",
            "line-color": "#4a7ab5",
            "target-arrow-color": "#4a7ab5",
          },
        },
      ],
      layout: { name: "preset" },
      wheelSensitivity: 0.2,
      minZoom: 0.15,
      maxZoom: 3,
    });

    // per-type shapes via batch
    this.cy.nodes().forEach((node) => {
      const t = String(node.data("type") || "");
      node.style("shape", shapeForType(t));
    });
    this.cy.edges().forEach((edge) => {
      const st = edgeStyle(
        String(edge.data("sourceState") || "declared"),
        String(edge.data("resolutionState") || "resolved")
      );
      edge.style(st);
    });

    this.cy.on("tap", "node", (ev) => {
      const id = ev.target.id();
      this.opts.onSelectNode(id);
    });
    this.cy.on("tap", "edge", (ev) => {
      this.opts.onSelectEdge(ev.target.id());
    });
    this.cy.on("dbltap", "node", (ev) => {
      this.opts.onDblClickNode(ev.target.id());
    });

    if (opts?.selectedId && this.cy.$id(opts.selectedId).nonempty()) {
      this.cy.$id(opts.selectedId).select();
      this.cy.center(this.cy.$id(opts.selectedId));
    } else {
      this.cy.fit(undefined, 40);
    }
  }

  focus(id: string): void {
    if (!this.cy) return;
    const n = this.cy.$id(id);
    if (n.nonempty()) {
      this.cy.elements().unselect();
      n.select();
      this.cy.animate({ center: { eles: n }, duration: 200 });
    }
  }

  fit(): void {
    this.cy?.fit(undefined, 40);
  }
}
