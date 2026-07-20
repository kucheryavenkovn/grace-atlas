import { App, FuzzySuggestModal } from "obsidian";
import type { WorkbenchNode } from "../types/snapshot";
import type { FrontendIndex } from "../model/indexes";
import { searchEntities } from "../model/indexes";

export class FocusEntityModal extends FuzzySuggestModal<WorkbenchNode> {
  private index: FrontendIndex;
  private onPick: (node: WorkbenchNode) => void;

  constructor(app: App, index: FrontendIndex, onPick: (node: WorkbenchNode) => void) {
    super(app);
    this.index = index;
    this.onPick = onPick;
    this.setPlaceholder("Focus entity by ID or name…");
  }

  getItems(): WorkbenchNode[] {
    // FuzzySuggestModal filters via getItemText; provide all is heavy — use search on empty
    return [...this.index.nodeById.values()].slice(0, 5000);
  }

  getItemText(item: WorkbenchNode): string {
    return `${item.id} ${item.displayName} ${item.type} ${item.status}`;
  }

  onChooseItem(item: WorkbenchNode): void {
    this.onPick(item);
  }
}

/** Exact ID prefer helper for tests / commands */
export function resolveEntityQuery(index: FrontendIndex, query: string): WorkbenchNode | null {
  const hits = searchEntities(index, query, 10);
  return hits[0] || null;
}
