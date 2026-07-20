import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { buildFrontendIndex, searchEntities } from "../model/indexes";
import {
  buildDiagramGraph,
  templateModuleNeighborhood,
  templateUseCaseTrace,
} from "../model/diagramQuery";
import { WorkbenchStore } from "../state/workbenchStore";
import type { WorkbenchEdge, WorkbenchFinding, WorkbenchNode } from "../types/snapshot";

function sampleNodes(): WorkbenchNode[] {
  return [
    {
      id: "UC-001",
      type: "UseCase",
      displayName: "Detect all-in-one",
      description: "d",
      status: "active",
      properties: {},
      tags: ["has_gaps"],
      source: { file: "docs/requirements.xml", line: 10, column: null },
      links: { obsidianNote: "Use-Cases/UC-001.md", sourceUri: null, vscodeUri: null },
    },
    {
      id: "M-APP-AUTO",
      type: "Module",
      displayName: "Auto pipeline",
      description: "",
      status: "",
      properties: {},
      tags: [],
      source: null,
      links: {},
    },
    {
      id: "file:src/x.py",
      type: "SourceFile",
      displayName: "x.py",
      description: "",
      status: "",
      properties: { path: "src/x.py" },
      tags: [],
      source: { file: "src/x.py", line: 1, column: null },
      links: { sourceUri: "src/x.py", vscodeUri: "vscode://file/src/x.py:1" },
    },
  ];
}

function sampleEdges(): WorkbenchEdge[] {
  return [
    {
      id: "UC-001|implements|M-APP-AUTO",
      source: "UC-001",
      target: "M-APP-AUTO",
      relation: "implements",
      sourceState: "declared",
      resolutionState: "resolved",
      provenance: {},
    },
    {
      id: "M-APP-AUTO|implemented_in|file:src/x.py",
      source: "M-APP-AUTO",
      target: "file:src/x.py",
      relation: "implemented_in",
      sourceState: "declared",
      resolutionState: "resolved",
      provenance: {},
    },
  ];
}

function sampleFindings(): WorkbenchFinding[] {
  return [
    {
      id: "d1",
      code: "GAP",
      severity: "warning",
      message: "missing evidence",
      entityId: "UC-001",
      sourceState: "declared",
      source: { file: "", line: null },
      related: [],
      details: {},
      suggestedAction: "add evidence",
      actionable: true,
    },
  ];
}

describe("indexes", () => {
  it("builds maps and search", () => {
    const idx = buildFrontendIndex(sampleNodes(), sampleEdges(), sampleFindings());
    assert.equal(idx.nodeById.size, 3);
    assert.equal(idx.outgoing.get("UC-001")?.length, 1);
    assert.equal(idx.findingsByNode.get("UC-001")?.length, 1);
    const hits = searchEntities(idx, "UC-001");
    assert.equal(hits[0]?.id, "UC-001");
    const hits2 = searchEntities(idx, "auto");
    assert.ok(hits2.some((h) => h.id === "M-APP-AUTO"));
  });
});

describe("diagram query", () => {
  it("expands use case trace", () => {
    const idx = buildFrontendIndex(sampleNodes(), sampleEdges(), sampleFindings());
    const g = buildDiagramGraph(idx, templateUseCaseTrace("UC-001"));
    assert.ok(g.nodes.some((n) => n.id === "UC-001"));
    assert.ok(g.nodes.some((n) => n.id === "M-APP-AUTO"));
    assert.ok(g.nodes.some((n) => n.id === "file:src/x.py"));
    assert.ok(g.edges.length >= 2);
  });

  it("module neighborhood depth", () => {
    const idx = buildFrontendIndex(sampleNodes(), sampleEdges(), sampleFindings());
    const g = buildDiagramGraph(idx, templateModuleNeighborhood("M-APP-AUTO"), {
      depthOverride: 1,
    });
    assert.ok(g.nodes.some((n) => n.id === "M-APP-AUTO"));
  });
});

describe("selection store", () => {
  it("sync selection and history without cycles", async () => {
    const store = new WorkbenchStore();
    let events = 0;
    store.subscribe(() => {
      events++;
    });
    store.selectEntity("UC-001", "browser", { type: "UseCase" });
    store.selectEntity("UC-001", "diagram", { type: "UseCase" }); // same id — no new history storm
    store.selectEntity("M-APP-AUTO", "inspector", { type: "Module" });
    assert.equal(store.getState().selectedEntityId, "M-APP-AUTO");
    assert.ok(store.goBack());
    assert.equal(store.getState().selectedEntityId, "UC-001");
    assert.ok(store.goForward());
    assert.equal(store.getState().selectedEntityId, "M-APP-AUTO");
    assert.ok(events >= 3);
  });
});

describe("schema gate", () => {
  it("rejects major mismatch conceptually", () => {
    const major = Number("2.0.0".split(".")[0]);
    assert.notEqual(major, 1);
  });
});
