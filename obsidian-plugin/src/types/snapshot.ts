/** Workbench snapshot types (mirrors Python schema; no GRACE XML parsing). */

export interface SourceLoc {
  file: string;
  line: number | null;
  column: number | null;
}

export interface NodeLinks {
  obsidianNote?: string | null;
  sourceUri?: string | null;
  vscodeUri?: string | null;
}

export interface WorkbenchNode {
  id: string;
  type: string;
  displayName: string;
  description: string;
  status: string;
  properties: Record<string, unknown>;
  tags: string[];
  source: SourceLoc | null;
  links: NodeLinks;
}

export interface WorkbenchEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  sourceState: string;
  resolutionState: string;
  provenance: {
    file?: string;
    line?: number | null;
    description?: string;
  };
}

export interface WorkbenchFinding {
  id: string;
  code: string;
  severity: string;
  message: string;
  entityId: string;
  sourceState: string;
  source: { file: string; line: number | null };
  related: string[];
  details: Record<string, unknown>;
  suggestedAction: string;
  phaseRelevance?: unknown;
  userJourneyRelevance?: unknown;
  actionable: boolean;
}

export interface DiagramDefinition {
  schemaVersion: string;
  id: string;
  name: string;
  type: string;
  rootEntityIds: string[];
  query: {
    includeRelations: string[];
    excludeRelations: string[];
    includeNodeTypes: string[];
    excludeNodeTypes: string[];
    direction: "incoming" | "outgoing" | "both";
    depth: number;
    includeDiagnostics: boolean;
  };
  layout: {
    algorithm: string;
    direction: string;
    spacing: number;
  };
  hiddenNodeIds: string[];
  hiddenEdgeIds: string[];
  pinnedNodeIds: string[];
  manualPositions: Record<string, { x: number; y: number }>;
  collapsedGroups: string[];
  viewport: { zoom: number; panX: number; panY: number };
  createdFrom: string;
  readOnly: boolean;
  unresolvedNodeIds?: string[];
}

export interface SnapshotManifest {
  schemaVersion: string;
  generatorVersion: string;
  project: { id: string; name: string; root: string };
  generatedAt: string;
  modelHash: string;
  nodeCount: number;
  edgeCount: number;
  diagnosticCount: number;
  files: Record<string, string>;
}

export interface SnapshotIndexes {
  nodeById: Record<string, number>;
  incomingByNode: Record<string, string[]>;
  outgoingByNode: Record<string, string[]>;
  childrenByNode: Record<string, string[]>;
  parentByNode: Record<string, string>;
  diagnosticsByNode: Record<string, number[]>;
  nodesByType: Record<string, string[]>;
  nodesByStatus: Record<string, string[]>;
  nodesByPhase: Record<string, string[]>;
  diagramsByRoot: Record<string, string[]>;
  sourceFilesByNode: Record<string, string[]>;
}

export interface WorkbenchModel {
  schemaVersion: string;
  nodes: WorkbenchNode[];
  edges: WorkbenchEdge[];
}

export interface LoadedSnapshot {
  manifest: SnapshotManifest;
  model: WorkbenchModel;
  diagnostics: { schemaVersion: string; summary: Record<string, unknown>; findings: WorkbenchFinding[] };
  indexes: SnapshotIndexes;
  diagramsGenerated: { schemaVersion: string; diagrams: DiagramDefinition[] };
  provenance: Record<string, unknown> | null;
  modelDir: string;
}

export type ModelStatus =
  | "loading"
  | "ready"
  | "stale"
  | "invalid"
  | "missing"
  | "incompatible";

export type SelectionOrigin =
  | "browser"
  | "diagram"
  | "inspector"
  | "diagnostics"
  | "command"
  | "history"
  | "system";
