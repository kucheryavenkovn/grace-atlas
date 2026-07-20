# GRACE Workbench for VS Code

Rose-like read-only CASE shell for [GRACE Atlas](../).  
Same contract as the Obsidian plugin: **reads only** `.grace-atlas/model` snapshot (never parses GRACE XML).

## Prerequisites

1. Build the workbench snapshot from the project root:

```powershell
cd D:\git\video2pptx
$env:PYTHONPATH = "tools/grace_atlas/src"
python -m grace_atlas snapshot build --project-root .
```

2. Open the **project root** (not the vault) as a VS Code workspace folder.

## Собрать и установить (рекомендуется: .vsix)

```powershell
cd D:\git\video2pptx\tools\grace_atlas\vscode-extension
npm install
npm run package
# → grace-workbench-0.4.0.vsix
```

В VS Code / Cursor:

1. `Ctrl+Shift+P` → **Extensions: Install from VSIX…**
2. Выберите файл  
   `D:\git\video2pptx\tools\grace_atlas\vscode-extension\grace-workbench-0.4.0.vsix`
3. Перезагрузите окно, если попросит
4. Откройте workspace **корня проекта** (`D:\git\video2pptx`)
5. Command Palette → **GRACE: Open Workbench**

Или из терминала:

```powershell
code --install-extension D:\git\video2pptx\tools\grace_atlas\vscode-extension\grace-workbench-0.4.0.vsix
# Cursor:
# cursor --install-extension ...\grace-workbench-0.4.0.vsix
```

### Только build (без .vsix) + dev

```powershell
npm run build
# F5 из папки vscode-extension → Extension Development Host
# или Extensions: Install from Location… → папка vscode-extension (нужен dist/)
```

## UI

| Surface | Role |
|---------|------|
| Activity bar **GRACE** | Model Browser tree |
| **GRACE: Open Workbench** | 4-pane webview: Browser · Diagram (Cytoscape+ELK) · Inspector · Problems/Trace/History |
| Status bar | Node count / model status |

Selection is synchronized across tree, diagram, inspector, and diagnostics.  
**Open Source** opens the file from snapshot `links.sourceUri` / `source.file` at the recorded line.

## Settings

| Setting | Default | Meaning |
|---------|---------|---------|
| `graceWorkbench.modelPath` | `.grace-atlas/model` | Snapshot directory relative to workspace |
| `graceWorkbench.autoLoad` | `true` | Load snapshot on activate |

## Architecture (same as Obsidian)

```
Python GRACE Core → Workbench Snapshot → VS Code extension (this)
                                      → Obsidian plugin
                                      → CLI
```

No Neo4j, no network, no mandatory LLM. Inferred links are never written.

## Tests

```powershell
npm test
npm run typecheck
```
