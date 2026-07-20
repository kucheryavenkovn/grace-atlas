/**
 * GRACE Workbench webview client (bundled as IIFE).
 * Reads snapshot via postMessage — never parses GRACE XML.
 */
import cytoscape, { type Core } from "cytoscape";
import ELK from "elkjs/lib/elk.bundled.js";
import {
  buildDiagramGraph,
  templateImpact,
  templateModuleNeighborhood,
  templateUseCaseTrace,
} from "../model/diagramQuery";
import { buildFrontendIndex, searchEntities, type FrontendIndex } from "../model/indexes";
import type {
  DiagramDefinition,
  WorkbenchEdge,
  WorkbenchFinding,
  WorkbenchNode,
} from "../types/snapshot";

declare function acquireVsCodeApi(): {
  postMessage(msg: unknown): void;
  getState(): unknown;
  setState(s: unknown): void;
};

const vscode = acquireVsCodeApi();
const elk = new ELK();

interface ModelPayload {
  type: "model";
  status: string;
  error: string | null;
  modelHash: string | null;
  depth: number;
  selectedEntityId: string | null;
  snapshot: {
    manifest: { nodeCount: number; edgeCount: number; modelHash: string };
    nodes: WorkbenchNode[];
    edges: WorkbenchEdge[];
    findings: WorkbenchFinding[];
    diagrams: DiagramDefinition[];
  } | null;
}

interface SelectionPayload {
  type: "selection";
  selectedEntityId: string | null;
  selectedEdgeId: string | null;
  activeDiagramId: string | null;
  depth: number;
  history: string[];
  historyIndex: number;
}

let index: FrontendIndex | null = null;
let findings: WorkbenchFinding[] = [];
let diagrams: DiagramDefinition[] = [];
let selectedId: string | null = null;
let depth = 3;
let filterText = "";
let bottomTab: "problems" | "trace" | "history" = "problems";
let history: string[] = [];
let historyIndex = -1;
let cy: Core | null = null;
let lastDiagramKey = "";

const el = {
  status: document.getElementById("status")!,
  tree: document.getElementById("tree")!,
  inspector: document.getElementById("inspector")!,
  bottom: document.getElementById("bottom")!,
  search: document.getElementById("search") as HTMLInputElement,
  depth: document.getElementById("depth") as HTMLSelectElement,
  cy: document.getElementById("cy")!,
};

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
    default:
      return "round-rectangle";
  }
}

function resolveDef(id: string): DiagramDefinition {
  const node = index?.nodeById.get(id);
  if (!node) return templateImpact(id);
  if (node.type === "UseCase" || node.type === "Requirement") return templateUseCaseTrace(id);
  if (node.type === "Module") return templateModuleNeighborhood(id);
  return templateImpact(id);
}

async function renderDiagram(): Promise<void> {
  if (!index || !selectedId) {
    if (cy) {
      cy.destroy();
      cy = null;
    }
    return;
  }
  const def = resolveDef(selectedId);
  const key = `${selectedId}|${depth}|${def.type}`;
  const g = buildDiagramGraph(index, def, { depthOverride: depth });

  let positions: Record<string, { x: number; y: number }> = {};
  try {
    const laid = await elk.layout({
      id: "root",
      layoutOptions: {
        "elk.algorithm": "layered",
        "elk.direction": "RIGHT",
        "elk.spacing.nodeNode": "40",
        "elk.layered.spacing.nodeNodeBetweenLayers": "60",
      },
      children: g.nodes.map((n) => ({ id: n.id, width: 150, height: 46 })),
      edges: g.edges.map((e) => ({
        id: e.id,
        sources: [e.source],
        targets: [e.target],
      })),
    } as never);
    for (const c of laid.children || []) {
      positions[c.id] = { x: c.x ?? 0, y: c.y ?? 0 };
    }
  } catch {
    g.nodes.forEach((n, i) => {
      positions[n.id] = { x: (i % 6) * 180, y: Math.floor(i / 6) * 90 };
    });
  }

  const elements = [
    ...g.nodes.map((n) => ({
      data: {
        id: n.id,
        label: `${n.id}\n${(n.displayName || "").slice(0, 28)}`,
        type: n.type,
      },
      position: positions[n.id] || { x: 0, y: 0 },
    })),
    ...g.edges.map((e) => ({
      data: {
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.relation,
        sourceState: e.sourceState,
        resolutionState: e.resolutionState,
      },
    })),
  ];

  if (cy) {
    cy.destroy();
    cy = null;
  }

  cy = cytoscape({
    container: el.cy,
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
          "line-color": "#4a7ab5",
          "target-arrow-color": "#4a7ab5",
        },
      },
    ],
    layout: { name: "preset" },
    wheelSensitivity: 0.2,
  });

  cy.nodes().forEach((node) => {
    node.style("shape", shapeForType(String(node.data("type") || "")));
  });
  cy.edges().forEach((edge) => {
    const ss = String(edge.data("sourceState") || "declared");
    const rs = String(edge.data("resolutionState") || "resolved");
    if (rs === "unresolved") {
      edge.style({ "line-style": "dashed", "line-color": "#c44", "target-arrow-color": "#c44" });
    } else if (ss === "inferred") {
      edge.style({ "line-style": "dashed", "line-color": "#888", "target-arrow-color": "#888" });
    }
  });

  cy.on("tap", "node", (ev) => {
    const id = ev.target.id();
    vscode.postMessage({ type: "select", id, origin: "diagram" });
  });
  cy.on("dbltap", "node", (ev) => {
    vscode.postMessage({ type: "select", id: ev.target.id(), origin: "diagram" });
  });

  if (selectedId && cy.$id(selectedId).nonempty()) {
    cy.$id(selectedId).select();
    cy.center(cy.$id(selectedId));
  } else {
    cy.fit(undefined, 40);
  }
  lastDiagramKey = key;
}

function renderTree(): void {
  el.tree.innerHTML = "";
  if (!index) {
    el.tree.innerHTML = `<div class="empty">No model</div>`;
    return;
  }

  const q = filterText.trim().toLowerCase();
  if (q) {
    const hits = searchEntities(index, q, 80);
    for (const n of hits) {
      appendEntity(el.tree, n);
    }
    return;
  }

  const groups: Array<[string, string[]]> = [
    ["Use Cases", ["UseCase"]],
    ["Modules", ["Module"]],
    ["Requirements", ["Requirement", "Constraint", "Risk"]],
    ["Verification", ["Verification", "CriticalFlow", "Evidence"]],
    ["Source Files", ["SourceFile", "TestFile"]],
    ["Phases", ["Phase", "Step", "OperationalPacket"]],
  ];

  for (const [label, types] of groups) {
    const nodes: WorkbenchNode[] = [];
    for (const t of types) {
      nodes.push(...(index.nodesByType.get(t) || []));
    }
    if (!nodes.length) continue;
    nodes.sort((a, b) => a.id.localeCompare(b.id));
    const cat = document.createElement("div");
    cat.className = "tree-node cat";
    cat.textContent = `${label} (${nodes.length})`;
    el.tree.appendChild(cat);
    for (const n of nodes.slice(0, 60)) {
      appendEntity(el.tree, n);
    }
    if (nodes.length > 60) {
      const more = document.createElement("div");
      more.className = "tree-node";
      more.textContent = `… +${nodes.length - 60} (use search)`;
      el.tree.appendChild(more);
    }
  }
}

function appendEntity(parent: HTMLElement, n: WorkbenchNode): void {
  const row = document.createElement("div");
  row.className = "tree-node" + (selectedId === n.id ? " selected" : "");
  const fc = index?.findingsByNode.get(n.id)?.length || 0;
  row.textContent = `${n.id} — ${n.displayName}${fc ? ` ⚠${fc}` : ""}`;
  row.title = n.type;
  row.onclick = () => vscode.postMessage({ type: "select", id: n.id, origin: "browser" });
  parent.appendChild(row);
}

function renderInspector(): void {
  if (!index || !selectedId) {
    el.inspector.innerHTML = `<div class="empty">Select an entity</div>`;
    return;
  }
  const n = index.nodeById.get(selectedId);
  if (!n) {
    el.inspector.innerHTML = `<div class="empty">Unknown ${selectedId}</div>`;
    return;
  }
  const fc = index.findingsByNode.get(n.id) || [];
  const out = index.outgoing.get(n.id) || [];
  const inc = index.incoming.get(n.id) || [];

  let html = `<h3 style="margin:0 0 4px">${esc(n.id)}</h3>
    <div>${esc(n.displayName)}</div>
    <div class="kv">
      <div class="k">type</div><div class="v">${esc(n.type)}</div>
      <div class="k">status</div><div class="v">${esc(n.status || "—")}</div>
      <div class="k">findings</div><div class="v">${fc.length}</div>
      <div class="k">source</div><div class="v">${esc(n.source?.file || n.links?.sourceUri || "—")}</div>
      <div class="k">line</div><div class="v">${n.source?.line ?? "—"}</div>
    </div>`;
  if (n.description) {
    html += `<h4>Description</h4><div>${esc(n.description)}</div>`;
  }
  html += `<h4>Outgoing (${out.length})</h4>`;
  for (const e of out.slice(0, 30)) {
    html += `<span class="rel" data-id="${esc(e.target)}">→ [${esc(e.relation)}] ${esc(e.target)} (${esc(e.sourceState)})</span>`;
  }
  html += `<h4>Incoming (${inc.length})</h4>`;
  for (const e of inc.slice(0, 30)) {
    html += `<span class="rel" data-id="${esc(e.source)}">← [${esc(e.relation)}] ${esc(e.source)} (${esc(e.sourceState)})</span>`;
  }
  if (fc.length) {
    html += `<h4>Findings</h4>`;
    for (const f of fc.slice(0, 15)) {
      html += `<div class="sev-${esc(f.severity)}">[${esc(f.severity)}] ${esc(f.code)}: ${esc(f.message)}</div>`;
    }
  }
  el.inspector.innerHTML = html;
  el.inspector.querySelectorAll(".rel").forEach((node) => {
    node.addEventListener("click", () => {
      const id = (node as HTMLElement).dataset.id;
      if (id) vscode.postMessage({ type: "select", id, origin: "inspector" });
    });
  });
}

function renderBottom(): void {
  if (!index) {
    el.bottom.innerHTML = "";
    return;
  }
  if (bottomTab === "history") {
    el.bottom.innerHTML = history
      .map(
        (id, i) =>
          `<div class="tree-node${i === historyIndex ? " selected" : ""}" data-id="${esc(id)}">${i === historyIndex ? "▶ " : ""}${esc(id)}</div>`
      )
      .join("");
    el.bottom.querySelectorAll("[data-id]").forEach((node) => {
      node.addEventListener("click", () => {
        const id = (node as HTMLElement).dataset.id;
        if (id) vscode.postMessage({ type: "select", id, origin: "history" });
      });
    });
    return;
  }

  if (bottomTab === "trace") {
    if (!selectedId) {
      el.bottom.innerHTML = `<div class="empty">Select an entity</div>`;
      return;
    }
    const out = index.outgoing.get(selectedId) || [];
    const inc = index.incoming.get(selectedId) || [];
    let html = `<div><b>Downstream</b></div>`;
    for (const e of out) {
      html += `<div class="rel" data-id="${esc(e.target)}">${esc(e.relation)} → ${esc(e.target)} [${esc(e.sourceState)}]</div>`;
    }
    html += `<div style="margin-top:8px"><b>Upstream</b></div>`;
    for (const e of inc) {
      html += `<div class="rel" data-id="${esc(e.source)}">${esc(e.relation)} ← ${esc(e.source)} [${esc(e.sourceState)}]</div>`;
    }
    el.bottom.innerHTML = html;
    el.bottom.querySelectorAll(".rel").forEach((node) => {
      node.addEventListener("click", () => {
        const id = (node as HTMLElement).dataset.id;
        if (id) vscode.postMessage({ type: "select", id, origin: "diagnostics" });
      });
    });
    return;
  }

  // problems
  let list = findings;
  if (selectedId) list = list.filter((f) => f.entityId === selectedId);
  let html = `<div>${selectedId ? `Findings for ${esc(selectedId)}` : "All findings"}: ${list.length}</div>
    <table><tr><th>sev</th><th>code</th><th>entity</th><th>message</th></tr>`;
  for (const f of list.slice(0, 150)) {
    html += `<tr class="clickable" data-id="${esc(f.entityId)}">
      <td class="sev-${esc(f.severity)}">${esc(f.severity)}</td>
      <td>${esc(f.code)}</td>
      <td>${esc(f.entityId)}</td>
      <td>${esc(f.message.slice(0, 100))}</td>
    </tr>`;
  }
  html += `</table>`;
  el.bottom.innerHTML = html;
  el.bottom.querySelectorAll("tr.clickable").forEach((row) => {
    row.addEventListener("click", () => {
      const id = (row as HTMLElement).dataset.id;
      if (id) vscode.postMessage({ type: "select", id, origin: "diagnostics" });
    });
  });
}

function esc(s: string): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function onSelectionChanged(forceDiagram = false): Promise<void> {
  renderTree();
  renderInspector();
  renderBottom();
  const key = `${selectedId}|${depth}`;
  if (forceDiagram || key !== lastDiagramKey) {
    await renderDiagram();
  } else if (cy && selectedId) {
    cy.elements().unselect();
    if (cy.$id(selectedId).nonempty()) {
      cy.$id(selectedId).select();
      cy.center(cy.$id(selectedId));
    }
  }
}

window.addEventListener("message", (event) => {
  const msg = event.data as ModelPayload | SelectionPayload;
  if (msg.type === "model") {
    el.status.textContent = msg.error
      ? `${msg.status}: ${msg.error}`
      : `${msg.status}${msg.snapshot ? ` · ${msg.snapshot.manifest.nodeCount}n/${msg.snapshot.manifest.edgeCount}e` : ""}`;
    el.status.className = `status ${msg.status}`;
    depth = msg.depth || 3;
    el.depth.value = String(depth);
    selectedId = msg.selectedEntityId;
    if (msg.snapshot) {
      findings = msg.snapshot.findings || [];
      diagrams = msg.snapshot.diagrams || [];
      index = buildFrontendIndex(msg.snapshot.nodes, msg.snapshot.edges, findings);
    } else {
      index = null;
      findings = [];
      diagrams = [];
    }
    void onSelectionChanged(true);
  } else if (msg.type === "selection") {
    selectedId = msg.selectedEntityId;
    depth = msg.depth || depth;
    el.depth.value = String(depth);
    history = msg.history || [];
    historyIndex = msg.historyIndex ?? -1;
    void onSelectionChanged(true);
  }
});

el.search.addEventListener("input", () => {
  filterText = el.search.value;
  renderTree();
});
el.search.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && index && el.search.value.trim()) {
    const hits = searchEntities(index, el.search.value, 1);
    if (hits[0]) vscode.postMessage({ type: "select", id: hits[0].id, origin: "command" });
  }
});
el.depth.addEventListener("change", () => {
  depth = Number(el.depth.value);
  vscode.postMessage({ type: "setDepth", depth });
  void renderDiagram();
});
document.getElementById("btnBack")!.onclick = () => vscode.postMessage({ type: "back" });
document.getElementById("btnFwd")!.onclick = () => vscode.postMessage({ type: "forward" });
document.getElementById("btnFit")!.onclick = () => cy?.fit(undefined, 40);
document.getElementById("btnSource")!.onclick = () => {
  if (selectedId) vscode.postMessage({ type: "openSource", id: selectedId });
};
document.getElementById("btnImpact")!.onclick = () => {
  if (selectedId) vscode.postMessage({ type: "impact", id: selectedId });
};
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    bottomTab = (tab as HTMLElement).dataset.tab as typeof bottomTab;
    renderBottom();
  });
});

vscode.postMessage({ type: "ready" });
void diagrams; // keep for future diagram catalog UI
