# GRACE Atlas Phase 3 — Human CASE / Rose-like Workbench Plan

**Status file:** `docs/phase3-status.md`  
**Scope:** evolve GRACE Atlas from Obsidian Vault generator into a human-oriented CASE/workbench (Rational Rose–like).  
**Constraint:** no git commit/push without explicit user request.

## Architecture (canonical)

```
GRACE XML + source markup + tests
           ↓
    Python GRACE Core
           ↓
  Normalized ProjectGraph
           ↓
  Enrichment + Diagnostics
           ↓
    Workbench Snapshot
           ↓
 ┌─────────┼──────────────────┐
 │         │                  │
Obsidian  Obsidian Plugin    CLI/API
Vault     Rose-like UI       Queries
```

**Rules:**
- Python Core is the only GRACE interpreter.
- Plugin reads normalized snapshot only (never parses GRACE XML).
- No Neo4j, no network required, no mandatory LLM.
- Inferred links never become declared without confirmation.
- XML writes only via GracePatch: preview → lint → confirm → atomic apply → audit.

## Phases

| Phase | Name | Goal |
|-------|------|------|
| 0 | Investigation | Git state, architecture, baseline tests |
| 3A | Read-only shell | Snapshot + Obsidian plugin (4 panels, selection sync) |
| 3B | Diagram catalog | DiagramDefinition, templates, user diagrams, export |
| 3C | Controlled editing | GracePatch pipeline, preview, audit, reverse patch |
| 3D | Round-trip | Fingerprints, drift, impact, incremental scan |

## Phase 3A steps

1. Current state and architecture  
2. Workbench snapshot (Python)  
3. Obsidian plugin skeleton  
4. Model Loader  
5. Workbench Store + Selection Service  
6. Model Browser  
7. Diagram View (Cytoscape)  
8. ELK layout  
9. Inspector  
10. Diagnostics / Traceability  
11. Search and commands  
12. Tests and manual acceptance  

## Phase 3B steps

1. DiagramDefinition  
2. Diagram Catalog  
3. Templates  
4. Drag-and-drop  
5. Layout persistence  
6. Multiple tabs  
7. Export  
8. Tests  

## Phase 3C steps

1. GracePatch schema  
2. Patch Planner  
3. Preview  
4. Temporary validation  
5. Atomic apply  
6. Audit  
7. UI forms  
8. Reverse patch  
9. Fixture-only integration tests  

## Phase 3D steps

1. Fingerprints  
2. Incremental scanner  
3. Drift model  
4. Impact engine  
5. Impact diagrams  
6. Change sets  
7. Evidence freshness  
8. Suggested patches  
9. Round-trip dashboard  
10. Tests  

## Output locations

| Artifact | Path |
|----------|------|
| Snapshot | `.grace-atlas/model/` |
| User diagrams | `.grace-atlas/user/diagrams/` |
| Audit log | `.grace-atlas/user/audit/patch-history.jsonl` |
| Vault (unchanged role) | `.grace-atlas/vault/` |
| Plugin source | `tools/grace_atlas/obsidian-plugin/` |

## Critical constraints (never violate)

1. Do not mutate real GRACE XML without patch pipeline + confirmation.  
2. Do not duplicate Python graph logic in TypeScript.  
3. Do not remove Markdown/Bases/Canvas exporters.  
4. Do not break existing CLI (`build`, `status`, `trace`, `show`, `gaps`, `open`).  
5. Do not auto-accept inferred relations.  
6. Do not commit/push/merge/rebase without explicit user command.  

## Acceptance after each phase

1. Run tests  
2. Smoke on real Video2PPTX  
3. Progress report in `docs/phase3-status.md`  
4. Record acceptance criteria and honest limitations  
5. Proceed only when prior phase is architecturally complete  
