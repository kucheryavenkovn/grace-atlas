import { ItemView, WorkspaceLeaf } from "obsidian";
import { VIEW_DIAGNOSTICS } from "../constants";
import type GraceWorkbenchPlugin from "../main";
import type { WorkbenchFinding } from "../types/snapshot";

type TabId = "problems" | "traceability" | "relations" | "history" | "log";

export class DiagnosticsView extends ItemView {
  private plugin: GraceWorkbenchPlugin;
  private unsub: (() => void) | null = null;
  private tab: TabId = "problems";
  private filterText = "";
  private severity = "";

  constructor(leaf: WorkspaceLeaf, plugin: GraceWorkbenchPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return VIEW_DIAGNOSTICS;
  }
  getDisplayText(): string {
    return "Диагностика GRACE";
  }
  getIcon(): string {
    return "alert-triangle";
  }

  setTab(tab: TabId): void {
    this.tab = tab;
    this.render();
  }

  async onOpen(): Promise<void> {
    this.unsub = this.plugin.store.subscribe(() => this.render());
    this.plugin.log.subscribe(() => {
      if (this.tab === "log") this.render();
    });
    this.render();
  }

  async onClose(): Promise<void> {
    this.unsub?.();
  }

  private render(): void {
    const container = this.containerEl.children[1] as HTMLElement;
    container.empty();
    container.addClass("grace-diagnostics");

    const tabs = container.createDiv({ cls: "grace-tabs" });
    const tabDefs: Array<[TabId, string]> = [
      ["problems", "Проблемы"],
      ["traceability", "Трассируемость"],
      ["relations", "Связи"],
      ["history", "История"],
      ["log", "Журнал"],
    ];
    for (const [id, label] of tabDefs) {
      const t = tabs.createSpan({
        cls: `grace-tab${this.tab === id ? " active" : ""}`,
        text: label,
      });
      t.onclick = () => {
        this.tab = id;
        this.render();
      };
    }

    const body = container.createDiv();
    switch (this.tab) {
      case "problems":
        this.renderProblems(body);
        break;
      case "traceability":
        this.renderTraceability(body);
        break;
      case "relations":
        this.renderRelations(body);
        break;
      case "history":
        this.renderHistory(body);
        break;
      case "log":
        this.renderLog(body);
        break;
    }
  }

  private renderProblems(body: HTMLElement): void {
    const toolbar = body.createDiv({ cls: "grace-wb-toolbar" });
    const search = toolbar.createEl("input", {
      type: "search",
      attr: { placeholder: "Фильтр проблем…" },
      value: this.filterText,
    });
    search.oninput = () => {
      this.filterText = search.value;
      this.render();
    };
    const sev = toolbar.createEl("select");
    for (const s of ["", "error", "warning", "info"]) {
      sev.createEl("option", {
        text: s ? s : "все severity",
        value: s,
      });
    }
    sev.value = this.severity;
    sev.onchange = () => {
      this.severity = sev.value;
      this.render();
    };

    const selected = this.plugin.store.getState().selectedEntityId;
    let findings: WorkbenchFinding[] = this.plugin.snapshot?.diagnostics.findings || [];
    if (selected) {
      findings = findings.filter((f) => f.entityId === selected);
    }
    if (this.severity) {
      findings = findings.filter((f) => f.severity === this.severity);
    }
    if (this.filterText.trim()) {
      const q = this.filterText.toLowerCase();
      findings = findings.filter(
        (f) =>
          f.message.toLowerCase().includes(q) ||
          f.code.toLowerCase().includes(q) ||
          (f.entityId || "").toLowerCase().includes(q)
      );
    }

    body.createDiv({
      text: selected
        ? `Findings для ${selected}: ${findings.length}`
        : `Findings: ${findings.length} (выберите сущность для фильтра)`,
    });

    const table = body.createEl("table", { cls: "grace-table" });
    const head = table.createEl("tr");
    for (const h of ["sev", "код", "сущность", "сообщение", "источник"]) {
      head.createEl("th", { text: h });
    }
    for (const f of findings.slice(0, 200)) {
      const tr = table.createEl("tr", { cls: "clickable" });
      tr.createEl("td", { cls: `grace-sev-${f.severity}`, text: f.severity });
      tr.createEl("td", { text: f.code });
      tr.createEl("td", { text: f.entityId || "" });
      tr.createEl("td", { text: f.message.slice(0, 120) });
      tr.createEl("td", { text: f.source?.file || "" });
      tr.onclick = () => {
        if (f.entityId) {
          const n = this.plugin.index?.nodeById.get(f.entityId);
          this.plugin.store.selectEntity(f.entityId, "diagnostics", { type: n?.type });
        }
      };
    }
  }

  private renderTraceability(body: HTMLElement): void {
    const id = this.plugin.store.getState().selectedEntityId;
    const index = this.plugin.index;
    if (!id || !index) {
      body.createDiv({ cls: "grace-empty", text: "Выберите сущность" });
      return;
    }
    body.createEl("h4", { text: `Трассируемость: ${id}` });
    const out = index.outgoing.get(id) || [];
    const inc = index.incoming.get(id) || [];
    body.createDiv({ text: "Вниз по потоку" });
    for (const e of out) {
      const line = body.createDiv({ cls: "grace-rel-link" });
      line.setText(`${e.relation} → ${e.target} [${e.sourceState}/${e.resolutionState}]`);
      line.onclick = () =>
        this.plugin.store.selectEntity(e.target, "diagnostics", {
          type: index.nodeById.get(e.target)?.type,
        });
    }
    body.createDiv({ text: "Вверх по потоку" });
    for (const e of inc) {
      const line = body.createDiv({ cls: "grace-rel-link" });
      line.setText(`${e.relation} ← ${e.source} [${e.sourceState}/${e.resolutionState}]`);
      line.onclick = () =>
        this.plugin.store.selectEntity(e.source, "diagnostics", {
          type: index.nodeById.get(e.source)?.type,
        });
    }
    const findings = index.findingsByNode.get(id) || [];
    if (findings.length) {
      body.createDiv({ text: `Gaps: ${findings.map((f) => f.code).join(", ")}` });
    }
  }

  private renderRelations(body: HTMLElement): void {
    this.renderTraceability(body);
  }

  private renderHistory(body: HTMLElement): void {
    const st = this.plugin.store.getState();
    body.createEl("h4", { text: "История навигации" });
    st.navigationHistory.forEach((id, i) => {
      const row = body.createDiv({
        cls: `grace-rel-link${i === st.historyIndex ? " selected" : ""}`,
        text: `${i === st.historyIndex ? "▶ " : ""}${id}`,
      });
      row.onclick = () => {
        const n = this.plugin.index?.nodeById.get(id);
        this.plugin.store.selectEntity(id, "history", { type: n?.type, skipHistory: true });
      };
    });
    const nav = body.createDiv({ cls: "grace-actions" });
    nav.createEl("button", { text: "Назад" }).onclick = () => this.plugin.store.goBack();
    nav.createEl("button", { text: "Вперёд" }).onclick = () => this.plugin.store.goForward();
  }

  private renderLog(body: HTMLElement): void {
    const entries = this.plugin.log.getEntries().slice().reverse();
    for (const e of entries.slice(0, 100)) {
      body.createDiv({
        text: `${e.ts} [${e.level}] ${e.message} ${e.data ? JSON.stringify(e.data) : ""}`,
      });
    }
  }
}
