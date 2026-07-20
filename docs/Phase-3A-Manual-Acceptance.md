# Phase 3A — Manual Acceptance Checklist (Obsidian GUI)

Automated UI control of Obsidian is not available in CI. Use this checklist after:

```powershell
cd D:\git\video2pptx
$env:PYTHONPATH = "tools/grace_atlas/src"
python -m grace_atlas snapshot build --project-root .
# plugin already built: tools/grace_atlas/obsidian-plugin
# copy main.js, manifest.json, styles.css → vault .obsidian/plugins/grace-workbench
```

Open vault: `.grace-atlas/vault` as Obsidian vault.

## Prerequisites

- [ ] Snapshot exists: `.grace-atlas/model/manifest.json`
- [ ] Plugin files present under `.obsidian/plugins/grace-workbench/`
- [ ] Plugin enabled in Obsidian settings

## Scenarios

- [ ] **Open Workbench** command lays out Browser / Diagram / Inspector / Diagnostics
- [ ] Model status shows `ready` with ~1500+ nodes
- [ ] Search/filter finds **UC-001**
- [ ] Select UC-001 → Inspector shows type UseCase + relations
- [ ] Diagram shows neighborhood for UC-001
- [ ] Problems tab filters to selected entity findings when entity selected
- [ ] Click related module in Inspector → selection syncs to browser/diagram
- [ ] Navigate Back / Forward works
- [ ] Open Focused Diagram on **M-APP-AUTO** shows module neighborhood
- [ ] Open Note opens generated Markdown card
- [ ] Open Source / VS Code uses snapshot links (if path available)
- [ ] Focus Entity modal finds entities by ID
- [ ] GRACE XML under `docs/*.xml` unchanged (no writes from plugin)
- [ ] Existing Bases/Canvas/Markdown still present after `grace-atlas build`

## Expected

| Check | Expected |
|-------|----------|
| schemaVersion | 1.0.0 |
| Plugin offline | no network required |
| XML mutation | none in Phase 3A |

## Known limitations

- Full multi-pane layout depends on Obsidian Workspace API; exact positions may vary.
- ELK layout may be slow on very large depth=4 diagrams; reduce depth in toolbar.
- Minimap is a simplified overview panel, not a full Cytoscape minimap extension.
