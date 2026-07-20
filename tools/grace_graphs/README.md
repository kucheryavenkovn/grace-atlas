# GRACE graphs (Graphviz + Mermaid)

**Язык:** [Русский](README.md) · [English](README.en.md)

Автономные скрипты (только Python stdlib): читают GRACE XML из `docs/` (или корня проекта) и пишут диаграммы.

Живут в **grace-atlas**, чтобы любой GRACE-проект мог их использовать:

```text
tools/grace_graphs/generate_grace_graphs.py
examples/grace-graphs/          # пример с фикстуры (DOT/PNG/SVG/Mermaid)
```

**Не** изменяют GRACE XML.  
Опционально: Graphviz `dot` для PNG/SVG.

Методология GRACE: [osovv/grace-marketplace](https://github.com/osovv/grace-marketplace).

## Исходные артефакты

| Файл | Для чего |
|------|----------|
| `docs/knowledge-graph.xml` | modules, depends, CrossLink |
| `docs/development-plan.xml` | modules, DF-*, Phase-*, step-* |
| `docs/requirements.xml` | UC-* + RelatedFlows |
| `docs/verification-plan.xml` | V-M-*, VF-* |

## Запуск

```powershell
# из корня репозитория — DOT + Mermaid + PNG + SVG (если установлен Graphviz)
python tools/grace_graphs/generate_grace_graphs.py --project-root .

# подмножество
python tools/grace_graphs/generate_grace_graphs.py --project-root . --only overview,modules-deps-core,phases-steps

# только DOT + Mermaid (без PNG/SVG)
python tools/grace_graphs/generate_grace_graphs.py --project-root . --skip-render

# один растровый формат
python tools/grace_graphs/generate_grace_graphs.py --project-root . --formats svg
python tools/grace_graphs/generate_grace_graphs.py --project-root . --formats png

# список графов
python tools/grace_graphs/generate_grace_graphs.py --list
```

Для PNG/SVG нужен **Graphviz** (`dot`):

```powershell
winget install Graphviz.Graphviz
# или portable в tools/grace_graphs/.graphviz/ (в gitignore)
```

Выход по умолчанию: `docs/grace-graphs/`

```text
docs/grace-graphs/
  README.md
  dot/
  svg/
  png/
  mermaid/
```

## Графы

| Имя | Содержание |
|-----|------------|
| `overview` | Счётчики + hub-рёбра |
| `modules-deps` | Все `M-*` depends_on |
| `modules-deps-core` | Связное подмножество (≤40) |
| `modules-verification` | Module ↔ V-M-* |
| `use-cases-flows` | UC / DF / VF |
| `phases-steps` | Phase → step → verification |
| `cross-links` | CrossLink из knowledge-graph |

## Render Graphviz (опционально)

Установите [Graphviz](https://graphviz.org/), чтобы `dot` был в `PATH`:

```powershell
New-Item -ItemType Directory -Force -Path docs/grace-graphs/svg | Out-Null
dot -Tsvg docs/grace-graphs/dot/modules-deps-core.dot -o docs/grace-graphs/svg/modules-deps-core.svg
dot -Tpng docs/grace-graphs/dot/phases-steps.dot -o docs/grace-graphs/png/phases-steps.png
```

Файлы Mermaid открываются на GitHub, в Obsidian (Mermaid) или на [mermaid.live](https://mermaid.live).
