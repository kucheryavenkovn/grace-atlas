# GRACE graphs (Graphviz + Mermaid)

**Language:** [Русский](README.md) · [English](README.en.md)

Standalone scripts (Python stdlib only) that read GRACE XML from `docs/` (or project root) and write diagrams.

Lives in **grace-atlas** so any GRACE project can use it:

```text
tools/grace_graphs/generate_grace_graphs.py
examples/grace-graphs/          # fixture sample (DOT/PNG/SVG/Mermaid)
```

**Does not** modify GRACE XML.  
Optional: Graphviz `dot` for PNG/SVG.

GRACE methodology: [osovv/grace-marketplace](https://github.com/osovv/grace-marketplace).

## Source artifacts

| File | Used for |
|------|----------|
| `docs/knowledge-graph.xml` | modules, depends, CrossLink |
| `docs/development-plan.xml` | modules, DF-*, Phase-*, step-* |
| `docs/requirements.xml` | UC-* + RelatedFlows |
| `docs/verification-plan.xml` | V-M-*, VF-* |

## Run

```powershell
# from repo root — writes DOT + Mermaid + PNG + SVG (if Graphviz installed)
python tools/grace_graphs/generate_grace_graphs.py --project-root .

# subset
python tools/grace_graphs/generate_grace_graphs.py --project-root . --only overview,modules-deps-core,phases-steps

# DOT + Mermaid only (skip PNG/SVG)
python tools/grace_graphs/generate_grace_graphs.py --project-root . --skip-render

# only one raster format
python tools/grace_graphs/generate_grace_graphs.py --project-root . --formats svg
python tools/grace_graphs/generate_grace_graphs.py --project-root . --formats png

# list graphs
python tools/grace_graphs/generate_grace_graphs.py --list
```

Requires **Graphviz** (`dot`) for PNG/SVG:

```powershell
winget install Graphviz.Graphviz
# or portable under tools/grace_graphs/.graphviz/ (gitignored)
```

Default output: `docs/grace-graphs/`

```text
docs/grace-graphs/
  README.md                 # index + PNG previews + Mermaid
  dot/                      # Graphviz source
  svg/                      # vector renders
  png/                      # raster renders
  mermaid/                  # .mmd + .md
```

## Graphs

| Name | Content |
|------|---------|
| `overview` | Counts + hub edges |
| `modules-deps` | All `M-*` depends_on |
| `modules-deps-core` | Subset of connected modules (≤40) |
| `modules-verification` | Module ↔ V-M-* |
| `use-cases-flows` | UC / DF / VF |
| `phases-steps` | Phase → step → verification |
| `cross-links` | CrossLink sample from knowledge-graph |

## Render Graphviz (optional)

Install [Graphviz](https://graphviz.org/) so `dot` is on `PATH`:

```powershell
New-Item -ItemType Directory -Force -Path docs/grace-graphs/svg | Out-Null
dot -Tsvg docs/grace-graphs/dot/modules-deps-core.dot -o docs/grace-graphs/svg/modules-deps-core.svg
dot -Tpng docs/grace-graphs/dot/phases-steps.dot -o docs/grace-graphs/png/phases-steps.png
```

Mermaid files open in GitHub, Obsidian (Mermaid), or [mermaid.live](https://mermaid.live).
