import type { ModelStatus, SelectionOrigin } from "../types/snapshot";

export interface BrowserFilter {
  text: string;
  types: string[];
  status: string;
  withGapsOnly: boolean;
  currentPhaseOnly: boolean;
}

export interface DiagramFilter {
  depth: number;
  direction: "RIGHT" | "DOWN";
  hideInformational: boolean;
}

export interface WorkbenchState {
  selectedEntityId: string | null;
  selectedEntityType: string | null;
  selectedEdgeId: string | null;
  selectionOrigin: SelectionOrigin | null;
  activeDiagramId: string | null;
  activeDiagramType: string | null;
  expandedTreeNodes: Set<string>;
  browserFilter: BrowserFilter;
  diagramFilter: DiagramFilter;
  navigationHistory: string[];
  historyIndex: number;
  modelStatus: ModelStatus;
  modelHash: string | null;
  lastError: string | null;
}

type Listener = (state: WorkbenchState, change: string) => void;

export function createInitialState(): WorkbenchState {
  return {
    selectedEntityId: null,
    selectedEntityType: null,
    selectedEdgeId: null,
    selectionOrigin: null,
    activeDiagramId: null,
    activeDiagramType: null,
    expandedTreeNodes: new Set(["requirements", "behavior", "architecture"]),
    browserFilter: {
      text: "",
      types: [],
      status: "",
      withGapsOnly: false,
      currentPhaseOnly: false,
    },
    diagramFilter: {
      depth: 3,
      direction: "RIGHT",
      hideInformational: false,
    },
    navigationHistory: [],
    historyIndex: -1,
    modelStatus: "missing",
    modelHash: null,
    lastError: null,
  };
}

/**
 * Selection service + store. Prevents cyclic selection storms by ignoring
 * re-entrant select of the same id within a microtask unless origin is history.
 */
export class WorkbenchStore {
  private state: WorkbenchState = createInitialState();
  private listeners = new Set<Listener>();
  private selecting = false;

  getState(): WorkbenchState {
    return this.state;
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(change: string): void {
    for (const fn of this.listeners) {
      try {
        fn(this.state, change);
      } catch (e) {
        console.error("[GRACE Workbench] listener error", e);
      }
    }
  }

  setModelStatus(status: ModelStatus, error: string | null = null, hash: string | null = null): void {
    this.state = {
      ...this.state,
      modelStatus: status,
      lastError: error,
      modelHash: hash ?? this.state.modelHash,
    };
    this.emit("modelStatus");
  }

  setBrowserFilter(partial: Partial<BrowserFilter>): void {
    this.state = {
      ...this.state,
      browserFilter: { ...this.state.browserFilter, ...partial },
    };
    this.emit("browserFilter");
  }

  setDiagramFilter(partial: Partial<DiagramFilter>): void {
    this.state = {
      ...this.state,
      diagramFilter: { ...this.state.diagramFilter, ...partial },
    };
    this.emit("diagramFilter");
  }

  toggleExpanded(id: string): void {
    const next = new Set(this.state.expandedTreeNodes);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    this.state = { ...this.state, expandedTreeNodes: next };
    this.emit("expanded");
  }

  setExpanded(ids: Iterable<string>): void {
    this.state = { ...this.state, expandedTreeNodes: new Set(ids) };
    this.emit("expanded");
  }

  setActiveDiagram(id: string | null, type: string | null = null): void {
    this.state = {
      ...this.state,
      activeDiagramId: id,
      activeDiagramType: type,
    };
    this.emit("diagram");
  }

  selectEntity(
    id: string | null,
    origin: SelectionOrigin,
    opts?: { type?: string | null; edgeId?: string | null; skipHistory?: boolean }
  ): void {
    if (this.selecting && origin !== "history") {
      // break cycles from diagram↔browser echoes
      if (id === this.state.selectedEntityId) return;
    }
    if (
      id === this.state.selectedEntityId &&
      (opts?.edgeId ?? null) === this.state.selectedEdgeId &&
      origin !== "history"
    ) {
      return;
    }

    this.selecting = true;
    try {
      let history = this.state.navigationHistory;
      let historyIndex = this.state.historyIndex;
      if (id && !opts?.skipHistory && origin !== "history") {
        history = history.slice(0, historyIndex + 1);
        if (history[history.length - 1] !== id) {
          history = [...history, id];
        }
        historyIndex = history.length - 1;
        if (history.length > 200) {
          history = history.slice(-200);
          historyIndex = history.length - 1;
        }
      }
      this.state = {
        ...this.state,
        selectedEntityId: id,
        selectedEntityType: opts?.type ?? this.state.selectedEntityType,
        selectedEdgeId: opts?.edgeId ?? null,
        selectionOrigin: origin,
        navigationHistory: history,
        historyIndex,
      };
      this.emit("selection");
    } finally {
      // release after stack clears so sync listeners can run without re-entry loops
      queueMicrotask(() => {
        this.selecting = false;
      });
    }
  }

  clearSelection(): void {
    this.selectEntity(null, "system", { skipHistory: true });
  }

  goBack(): boolean {
    if (this.state.historyIndex <= 0) return false;
    const historyIndex = this.state.historyIndex - 1;
    const id = this.state.navigationHistory[historyIndex] ?? null;
    this.state = { ...this.state, historyIndex };
    this.selectEntity(id, "history", { skipHistory: true });
    return true;
  }

  goForward(): boolean {
    if (this.state.historyIndex >= this.state.navigationHistory.length - 1) return false;
    const historyIndex = this.state.historyIndex + 1;
    const id = this.state.navigationHistory[historyIndex] ?? null;
    this.state = { ...this.state, historyIndex };
    this.selectEntity(id, "history", { skipHistory: true });
    return true;
  }
}
