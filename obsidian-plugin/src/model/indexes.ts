import type {
  SnapshotIndexes,
  WorkbenchEdge,
  WorkbenchFinding,
  WorkbenchNode,
} from "../types/snapshot";

export interface FrontendIndex {
  nodeById: Map<string, WorkbenchNode>;
  edgeById: Map<string, WorkbenchEdge>;
  outgoing: Map<string, WorkbenchEdge[]>;
  incoming: Map<string, WorkbenchEdge[]>;
  findingsByNode: Map<string, WorkbenchFinding[]>;
  nodesByType: Map<string, WorkbenchNode[]>;
  searchText: Map<string, string>;
}

export function buildFrontendIndex(
  nodes: WorkbenchNode[],
  edges: WorkbenchEdge[],
  findings: WorkbenchFinding[],
  diskIndexes?: SnapshotIndexes | null
): FrontendIndex {
  const nodeById = new Map<string, WorkbenchNode>();
  const edgeById = new Map<string, WorkbenchEdge>();
  const outgoing = new Map<string, WorkbenchEdge[]>();
  const incoming = new Map<string, WorkbenchEdge[]>();
  const findingsByNode = new Map<string, WorkbenchFinding[]>();
  const nodesByType = new Map<string, WorkbenchNode[]>();
  const searchText = new Map<string, string>();

  for (const n of nodes) {
    nodeById.set(n.id, n);
    const list = nodesByType.get(n.type) ?? [];
    list.push(n);
    nodesByType.set(n.type, list);
    searchText.set(
      n.id,
      `${n.id} ${n.displayName} ${n.type} ${n.status} ${(n.tags || []).join(" ")}`.toLowerCase()
    );
  }

  for (const e of edges) {
    edgeById.set(e.id, e);
    const o = outgoing.get(e.source) ?? [];
    o.push(e);
    outgoing.set(e.source, o);
    const i = incoming.get(e.target) ?? [];
    i.push(e);
    incoming.set(e.target, i);
  }

  for (const f of findings) {
    if (!f.entityId) continue;
    const list = findingsByNode.get(f.entityId) ?? [];
    list.push(f);
    findingsByNode.set(f.entityId, list);
  }

  // diskIndexes available for future compact lookups
  void diskIndexes;

  return {
    nodeById,
    edgeById,
    outgoing,
    incoming,
    findingsByNode,
    nodesByType,
    searchText,
  };
}

export function searchEntities(
  index: FrontendIndex,
  query: string,
  limit = 50
): WorkbenchNode[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const exact: WorkbenchNode[] = [];
  const prefix: WorkbenchNode[] = [];
  const fuzzy: WorkbenchNode[] = [];
  for (const [id, node] of index.nodeById) {
    if (id.toLowerCase() === q) {
      exact.push(node);
      continue;
    }
    const text = index.searchText.get(id) || "";
    if (id.toLowerCase().startsWith(q) || node.displayName.toLowerCase().startsWith(q)) {
      prefix.push(node);
    } else if (text.includes(q)) {
      fuzzy.push(node);
    }
  }
  return [...exact, ...prefix, ...fuzzy].slice(0, limit);
}
