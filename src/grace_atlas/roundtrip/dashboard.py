# FILE: tools/grace_atlas/src/grace_atlas/roundtrip/dashboard.py
# VERSION: 0.4.0
# PURPOSE: Markdown Round-Trip Status dashboard for vault fallback.

"""Round-trip markdown dashboard."""

from __future__ import annotations

from typing import Any

from grace_atlas.config import AtlasConfig
from grace_atlas.exporters.markdown import GENERATED_BANNER
from grace_atlas.roundtrip.drift import compute_drift


def render_roundtrip_dashboard(config: AtlasConfig, drift: dict[str, Any] | None = None) -> str:
    data = drift or compute_drift(config, rescan=False)
    items = data.get("items") or []
    by_cat: dict[str, int] = {}
    for it in items:
        c = str(it.get("category") or "other")
        by_cat[c] = by_cat.get(c, 0) + 1
    lines = [
        GENERATED_BANNER,
        "",
        "---",
        "generated: true",
        "tags: [grace-atlas, grace/roundtrip, grace/index]",
        "---",
        "",
        "# Round-Trip Status",
        "",
        "> GRACE model ↔ source markup ↔ files ↔ tests ↔ evidence. "
        "Inferred items never become declared without GracePatch confirmation.",
        "",
        f"**Drift items:** {len(items)}  |  **Fingerprint files:** {data.get('fingerprintFileCount', 0)}",
        "",
        "## Categories",
        "",
        "| Category | Count |",
        "|----------|------:|",
    ]
    for cat, n in sorted(by_cat.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"| `{cat}` | {n} |")
    lines.extend(
        [
            "",
            "## Top items",
            "",
        ]
    )
    for it in items[:40]:
        conf = it.get("confidence", 1.0)
        lines.append(
            f"- **[{it.get('category')}]** ({conf:.2f}) {it.get('summary')} "
            f"— `{it.get('sourceState', 'inferred')}`"
        )
    suggestions = data.get("suggestions") or []
    lines.extend(["", "## Suggested patches (inferred — not applied)", ""])
    if not suggestions:
        lines.append("_No suggestions._")
    for s in suggestions[:30]:
        lines.append(
            f"- **{s.get('kind')}** ({s.get('confidence', 0):.2f}) {s.get('reason')} "
            f"[sourceState={s.get('sourceState')}]"
        )
    lines.extend(
        [
            "",
            "## Commands",
            "",
            "```bash",
            "python -m grace_atlas scan --project-root .",
            "python -m grace_atlas drift --project-root .",
            "python -m grace_atlas impact M-APP-AUTO --project-root .",
            "python -m grace_atlas snapshot build --project-root .",
            "```",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def write_roundtrip_dashboard(config: AtlasConfig) -> str:
    from pathlib import Path

    vault = config.resolve_vault()
    path = vault / "Dashboards" / "Round-Trip-Status.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = render_roundtrip_dashboard(config)
    path.write_text(text, encoding="utf-8", newline="\n")
    return str(path)
