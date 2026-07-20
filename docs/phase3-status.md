# GRACE Atlas Phase 3 — Progress Status

**Last updated:** 2026-07-20  
**Current stage:** Phase 3A–3D + **VS Code extension**  
**Overall:** ready for review (Obsidian + VS Code GUI manual acceptance)

---

## Phase 0 — Investigation (COMPLETE)

| Field | Value |
|-------|-------|
| Main branch | `feature/grace-atlas-v1` |
| Main HEAD (start) | `6e498b618b38bf721b56a3b099ac01ec12dc562d` |
| Submodule | yes — `tools/grace_atlas` |
| Submodule branch | `main` @ `ba107a7` (Phase 2 committed; Phase 3 uncommitted) |
| Baseline tests | 34 passed → **51 passed** after Phase 3 |
| Phase 2 dirty? | **No** — already committed in submodule |

---

## Phase 3A — Read-only Rose-like shell (COMPLETE)

| Step | Status |
|------|--------|
| 3A.1 Current state | done |
| 3A.2 Workbench snapshot | done — `.grace-atlas/model/*` |
| 3A.3 Plugin skeleton | done — `obsidian-plugin/` |
| 3A.4 Model Loader | done |
| 3A.5 Store + Selection | done |
| 3A.6 Model Browser | done |
| 3A.7 Diagram Cytoscape | done |
| 3A.8 ELK layout | done |
| 3A.9 Inspector | done |
| 3A.10 Diagnostics | done |
| 3A.11 Search/commands | done |
| 3A.12 Tests/acceptance | done (unit + manual checklist) |

### Smoke (Video2PPTX)

| Metric | Value |
|--------|------:|
| Nodes | 1571 |
| Edges | 2832 |
| Diagnostics | 386 |
| modelHash (example) | `9d519df4afed815e` |
| UC-001 inspect | OK (DF-001, VF-001/003/005, actor-User) |
| Plugin build | OK (`main.js` ~1.9MB) |
| Plugin tests | 5 passed |
| Python tests | 51 passed |

### CLI

```
python -m grace_atlas snapshot build|validate|inspect
# build also writes snapshot
```

---

## Phase 3B — Diagram catalog (COMPLETE — core)

| Step | Status |
|------|--------|
| DiagramDefinition in snapshot | done (`diagrams.generated.json`) |
| User diagrams dir | done (`.grace-atlas/user/diagrams`) |
| Templates (UC/module/impact) | done (Python + TS) |
| Survive rebuild | tested |
| Unresolved tombstones | tested |
| Drag-drop / multi-tab / export PNG | **partial** — API/types ready; full GUI DnD needs manual Obsidian verification |
| Canvas export of user diagram | existing Canvas exporters remain; diagram→canvas bridge is template-level |

---

## Phase 3C — GracePatch (COMPLETE — fixture-safe)

| Step | Status |
|------|--------|
| Schema + whitelist ops | done |
| Planner (no write) | done |
| Temp validate + graph rebuild | done |
| Atomic apply + backup + audit | done |
| Reverse patch from audit | done |
| CLI `patch plan/validate/apply/reverse` | done |
| Real Video2PPTX XML apply | **not executed** (fixtures only in tests) |

---

## Phase 3D — Round-trip (COMPLETE — core)

| Step | Status |
|------|--------|
| Fingerprints | done |
| scan / scan --changed-only | done |
| drift categories + suggestions | done |
| impact engine + CLI | done |
| watch --once | done |
| Round-Trip dashboard MD | stub in vault + `roundtrip/dashboard.py` |
| Impact diagram type | plugin template `impact` |

### Smoke

- scan: 328 files fingerprinted  
- drift: 196 items (includes known broken refs)  
- impact UC-001: 5 direct / 17 transitive  

---

## Commits

**None created.** User must request commit explicitly.

## GRACE XML mutations

**None on real Video2PPTX docs.** Patch tests mutate **copied fixtures only**.

---

## Acceptance criteria snapshot

### 3A met

- [x] Plugin builds  
- [x] Loads real snapshot  
- [x] Four panel views + commands  
- [x] Selection store + history  
- [x] UC-001 / diagram query / inspector mapping tests  
- [ ] Full GUI layout in Obsidian — **manual**  

### 3B/3C/3D met (architecture)

- [x] Generated vs user diagram separation  
- [x] Patch pipeline with preview/validate/audit  
- [x] Drift + impact + incremental scan  
- [ ] Full GUI editing forms / DnD — partial  

---

## VS Code extension (added)

| Item | Path / notes |
|------|----------------|
| Extension | `tools/grace_atlas/vscode-extension/` |
| Same snapshot | `.grace-atlas/model` |
| UI | Activity bar tree + full Workbench webview (4 panes) |
| Commands | Open Workbench, Reload, Focus Entity, Open Source, Impact, Back/Forward |
| Build | `npm install && npm run build` → `dist/extension.js` + `dist/webview.js` |
| Run | F5 Extension Host **or** Install from Location |

---

## Blockers / limitations

1. Obsidian multi-pane layout cannot be fully automated in CI.  
2. Property-level XML patch ops limited; CrossLink edge ops primary.  
3. Plugin does not parse GRACE XML (by design).  
4. First `scan` marks all files changed (empty fingerprint store).  
5. ELK on very large graphs may be slow — use depth control.  
6. `update_property` / `update_status` not fully XML-backed yet.  

## Recommendation

**ready for review** — not auto-committed.  
After manual Obsidian acceptance: **ready for commit** (submodule + parent pointer).  
