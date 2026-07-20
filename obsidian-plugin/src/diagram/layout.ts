import ELK from "elkjs/lib/elk.bundled.js";
import type { WorkbenchEdge, WorkbenchNode } from "../types/snapshot";

export interface LayoutPositions {
  [id: string]: { x: number; y: number };
}

const elk = new ELK();

export async function layoutElk(
  nodes: WorkbenchNode[],
  edges: WorkbenchEdge[],
  opts?: {
    direction?: "RIGHT" | "DOWN" | "LEFT" | "UP";
    spacing?: number;
    manual?: LayoutPositions;
    pinned?: Set<string>;
  }
): Promise<LayoutPositions> {
  const direction = opts?.direction || "RIGHT";
  const spacing = opts?.spacing ?? 40;
  const manual = opts?.manual || {};
  const pinned = opts?.pinned || new Set<string>();

  const graph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": direction,
      "elk.spacing.nodeNode": String(spacing),
      "elk.layered.spacing.nodeNodeBetweenLayers": String(spacing * 1.5),
      "elk.edgeRouting": "ORTHOGONAL",
    },
    children: nodes.map((n) => {
      const pos = manual[n.id];
      const child: Record<string, unknown> = {
        id: n.id,
        width: 160,
        height: 48,
      };
      if (pos && pinned.has(n.id)) {
        child.x = pos.x;
        child.y = pos.y;
        child.layoutOptions = { "elk.fixed": "true" };
      }
      return child;
    }),
    edges: edges.map((e) => ({
      id: e.id,
      sources: [e.source],
      targets: [e.target],
    })),
  };

  const res = await elk.layout(graph as never);
  const out: LayoutPositions = {};
  for (const c of res.children || []) {
    out[c.id] = { x: c.x ?? 0, y: c.y ?? 0 };
  }
  // apply manual overrides for non-layouted
  for (const [id, p] of Object.entries(manual)) {
    if (pinned.has(id)) out[id] = p;
  }
  return out;
}

/** Fallback grid when ELK fails */
export function layoutGrid(nodes: WorkbenchNode[]): LayoutPositions {
  const out: LayoutPositions = {};
  const cols = Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
  nodes.forEach((n, i) => {
    out[n.id] = {
      x: (i % cols) * 200,
      y: Math.floor(i / cols) * 100,
    };
  });
  return out;
}
