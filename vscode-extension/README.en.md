# GRACE Workbench for VS Code

**Language:** [Русский](README.md) · [English](README.en.md)

Rose-like read-only CASE shell for [GRACE Atlas](../).  
Same contract as the Obsidian plugin: **reads only** `.grace-atlas/model` snapshot (never parses GRACE XML).

## Prerequisites

1. Build the workbench snapshot from the project root:

```powershell
$env:PYTHONPATH = "src"   # from grace-atlas root, or tools/grace_atlas/src from host
python -m grace_atlas snapshot build --project-root .
```

2. Open the **project root** (not the vault) as a VS Code workspace folder.

## Build and install (recommended: .vsix)

```powershell
cd vscode-extension
npm install
npm run package
# → grace-workbench-0.4.0.vsix
```

In VS Code / Cursor:

1. `Ctrl+Shift+P` → **Extensions: Install from VSIX…**
2. Select `grace-workbench-0.4.0.vsix`
3. Reload if prompted
4. Open the **project root** workspace
5. Command Palette → **GRACE: Open Workbench**

Or:

```powershell
code --install-extension path\to\grace-workbench-0.4.0.vsix
```

Release binaries: https://github.com/kucheryavenkovn/grace-atlas/releases/tag/v0.4.0

### Dev only (no .vsix)

```powershell
npm run build
# F5 from vscode-extension folder → Extension Development Host
```

## UI

| Surface | Role |
|---------|------|
| Activity bar **GRACE** | Model Browser tree |
| **GRACE: Open Workbench** | 4-pane webview: Browser · Diagram · Inspector · Problems/Trace/History |
| Status bar | Node count / model status |

## Settings

| Setting | Default | Meaning |
|---------|---------|---------|
| `graceWorkbench.modelPath` | `.grace-atlas/model` | Snapshot dir relative to workspace |
| `graceWorkbench.autoLoad` | `true` | Load snapshot on activate |

## Architecture

```
Python GRACE Core → Workbench Snapshot → VS Code extension (this)
                                      → Obsidian plugin
                                      → CLI
```

No Neo4j, no network, no mandatory LLM. Inferred links are never written by the UI.

## Tests

```powershell
npm test
npm run typecheck
```
