import type { DiagramDefinition, WorkbenchEdge, WorkbenchNode } from "../types/snapshot";
import type { FrontendIndex } from "./indexes";

export interface DiagramGraph {
  nodes: WorkbenchNode[];
  edges: WorkbenchEdge[];
}

/**
 * Expand a diagram definition over the frontend index (no GRACE parsing).
 */
export function buildDiagramGraph(
  index: FrontendIndex,
  def: DiagramDefinition,
  opts?: { depthOverride?: number }
): DiagramGraph {
  const depth = opts?.depthOverride ?? def.query.depth ?? 2;
  const direction = def.query.direction || "both";
  const includeRel = new Set(def.query.includeRelations || []);
  const excludeRel = new Set(def.query.excludeRelations || []);
  const includeTypes = new Set(def.query.includeNodeTypes || []);
  const excludeTypes = new Set(def.query.excludeNodeTypes || []);
  const hidden = new Set(def.hiddenNodeIds || []);
  const hiddenEdges = new Set(def.hiddenEdgeIds || []);

  const selected = new Set<string>();
  const queue: Array<{ id: string; d: number }> = [];
  for (const r of def.rootEntityIds || []) {
    if (index.nodeById.has(r)) {
      selected.add(r);
      queue.push({ id: r, d: 0 });
    }
  }

  const acceptNode = (id: string): boolean => {
    if (hidden.has(id)) return false;
    const n = index.nodeById.get(id);
    if (!n) return false;
    if (excludeTypes.has(n.type)) return false;
    if (includeTypes.size > 0 && !includeTypes.has(n.type)) return false;
    return true;
  };

  const acceptEdge = (e: WorkbenchEdge): boolean => {
    if (hiddenEdges.has(e.id)) return false;
    if (excludeRel.has(e.relation)) return false;
    if (includeRel.size > 0 && !includeRel.has(e.relation)) return false;
    return true;
  };

  while (queue.length) {
    const { id, d } = queue.shift()!;
    if (d >= depth) continue;
    const edges: WorkbenchEdge[] = [];
    if (direction === "outgoing" || direction === "both") {
      edges.push(...(index.outgoing.get(id) || []));
    }
    if (direction === "incoming" || direction === "both") {
      edges.push(...(index.incoming.get(id) || []));
    }
    for (const e of edges) {
      if (!acceptEdge(e)) continue;
      const other = e.source === id ? e.target : e.source;
      if (!acceptNode(other)) continue;
      if (!selected.has(other)) {
        selected.add(other);
        queue.push({ id: other, d: d + 1 });
      }
    }
  }

  const nodes = [...selected]
    .map((id) => index.nodeById.get(id)!)
    .filter(Boolean)
    .sort((a, b) => a.id.localeCompare(b.id));

  const edges: WorkbenchEdge[] = [];
  for (const n of nodes) {
    for (const e of index.outgoing.get(n.id) || []) {
      if (!acceptEdge(e)) continue;
      if (selected.has(e.target) && selected.has(e.source)) {
        edges.push(e);
      }
    }
  }
  // unique
  const seen = new Set<string>();
  const uniq = edges.filter((e) => {
    if (seen.has(e.id)) return false;
    seen.add(e.id);
    return true;
  });

  return { nodes, edges: uniq };
}

export function templateUseCaseTrace(rootId: string): DiagramDefinition {
  return {
    schemaVersion: "1.0.0",
    id: `gen:use_case_trace:${rootId}`,
    name: `Use Case Trace — ${rootId}`,
    type: "use_case_trace",
    rootEntityIds: [rootId],
    query: {
      includeRelations: [
        "related_flow",
        "uses_use_case",
        "implements",
        "implemented_in",
        "verified_by",
        "tested_by",
        "produces_evidence",
      ],
      excludeRelations: [],
      includeNodeTypes: [],
      excludeNodeTypes: [],
      direction: "both",
      depth: 4,
      includeDiagnostics: true,
    },
    layout: { algorithm: "elk-layered", direction: "RIGHT", spacing: 40 },
    hiddenNodeIds: [],
    hiddenEdgeIds: [],
    pinnedNodeIds: [],
    manualPositions: {},
    collapsedGroups: [],
    viewport: { zoom: 1, panX: 0, panY: 0 },
    createdFrom: "template",
    readOnly: false,
  };
}

export function templateModuleNeighborhood(rootId: string): DiagramDefinition {
  return {
    schemaVersion: "1.0.0",
    id: `gen:module_neighborhood:${rootId}`,
    name: `Module Neighborhood — ${rootId}`,
    type: "module_neighborhood",
    rootEntityIds: [rootId],
    query: {
      includeRelations: [
        "depends_on",
        "implements",
        "implemented_in",
        "verified_by",
        "tested_by",
        "has_contract",
        "has_block",
        "planned_in",
      ],
      excludeRelations: [],
      includeNodeTypes: [],
      excludeNodeTypes: [],
      direction: "both",
      depth: 2,
      includeDiagnostics: true,
    },
    layout: { algorithm: "elk-layered", direction: "RIGHT", spacing: 40 },
    hiddenNodeIds: [],
    hiddenEdgeIds: [],
    pinnedNodeIds: [rootId],
    manualPositions: {},
    collapsedGroups: [],
    viewport: { zoom: 1, panX: 0, panY: 0 },
    createdFrom: "template",
    readOnly: false,
  };
}

export function templateImpact(rootId: string): DiagramDefinition {
  return {
    schemaVersion: "1.0.0",
    id: `gen:impact:${rootId}`,
    name: `Impact — ${rootId}`,
    type: "impact",
    rootEntityIds: [rootId],
    query: {
      includeRelations: [
        "implements",
        "implemented_in",
        "depends_on",
        "verified_by",
        "tested_by",
        "related_flow",
        "uses_use_case",
        "planned_in",
      ],
      excludeRelations: [],
      includeNodeTypes: [],
      excludeNodeTypes: [],
      direction: "both",
      depth: 3,
      includeDiagnostics: true,
    },
    layout: { algorithm: "elk-layered", direction: "RIGHT", spacing: 40 },
    hiddenNodeIds: [],
    hiddenEdgeIds: [],
    pinnedNodeIds: [rootId],
    manualPositions: {},
    collapsedGroups: [],
    viewport: { zoom: 1, panX: 0, panY: 0 },
    createdFrom: "template",
    readOnly: false,
  };
}
