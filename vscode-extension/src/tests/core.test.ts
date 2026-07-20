import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { buildFrontendIndex, searchEntities } from "../model/indexes";
import { buildDiagramGraph, templateUseCaseTrace } from "../model/diagramQuery";
import { WorkbenchStore } from "../state/workbenchStore";
import type { WorkbenchEdge, WorkbenchFinding, WorkbenchNode } from "../types/snapshot";

const nodes: WorkbenchNode[] = [
  {
    id: "UC-001",
    type: "UseCase",
    displayName: "Detect",
    description: "",
    status: "",
    properties: {},
    tags: [],
    source: null,
    links: {},
  },
  {
    id: "M-APP-AUTO",
    type: "Module",
    displayName: "Auto",
    description: "",
    status: "",
    properties: {},
    tags: [],
    source: null,
    links: {},
  },
];

const edges: WorkbenchEdge[] = [
  {
    id: "UC-001|implements|M-APP-AUTO",
    source: "UC-001",
    target: "M-APP-AUTO",
    relation: "implements",
    sourceState: "declared",
    resolutionState: "resolved",
    provenance: {},
  },
];

const findings: WorkbenchFinding[] = [];

describe("vscode grace workbench shared core", () => {
  it("indexes and search", () => {
    const idx = buildFrontendIndex(nodes, edges, findings);
    assert.equal(searchEntities(idx, "UC-001")[0]?.id, "UC-001");
  });

  it("diagram expansion", () => {
    const idx = buildFrontendIndex(nodes, edges, findings);
    const g = buildDiagramGraph(idx, templateUseCaseTrace("UC-001"));
    assert.ok(g.nodes.some((n) => n.id === "M-APP-AUTO"));
  });

  it("selection history", () => {
    const store = new WorkbenchStore();
    store.selectEntity("UC-001", "tree", { type: "UseCase" });
    store.selectEntity("M-APP-AUTO", "command", { type: "Module" });
    assert.ok(store.goBack());
    assert.equal(store.getState().selectedEntityId, "UC-001");
  });
});
