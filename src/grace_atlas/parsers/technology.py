# FILE: tools/grace_atlas/src/grace_atlas/parsers/technology.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Parse technology.xml into Technology constraint nodes.
#   SCOPE: TechnologyStack dependencies, tools, version constraints
#   DEPENDS: grace_atlas.model, _xmlutil
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Parse GRACE technology stack XML."""

from __future__ import annotations

from pathlib import Path

from grace_atlas.model import AtlasGraph, Edge, EdgeType, Node, NodeType, Provenance
from grace_atlas.parsers._xmlutil import attr, local, parse_xml, short_desc, text_of


def parse_technology(path: Path, graph: AtlasGraph) -> None:
    root = parse_xml(path)
    rel = str(path)

    runtime = ""
    language = ""
    for child in root:
        tag = local(child.tag)
        if tag == "Runtime":
            runtime = text_of(child)
        elif tag == "Language":
            language = text_of(child)
        elif tag == "Framework":
            graph.add_node(
                Node(
                    id="tech:framework",
                    name="Framework",
                    type=NodeType.TECHNOLOGY,
                    description=short_desc(text_of(child)),
                    source="technology",
                    properties={"kind": "framework"},
                )
            )
        elif tag in {"Dependencies", "OptionalDependencies"}:
            for dep in child.iter():
                if local(dep.tag) != "dep":
                    continue
                name = attr(dep, "name", "NAME")
                if not name:
                    continue
                version = attr(dep, "version", "VERSION")
                purpose = attr(dep, "purpose", "PURPOSE")
                nid = f"tech:{name}"
                graph.add_node(
                    Node(
                        id=nid,
                        name=name,
                        type=NodeType.TECHNOLOGY,
                        description=short_desc(purpose or f"{name} {version}".strip()),
                        source="technology",
                        properties={
                            "kind": "dependency",
                            "version": version,
                            "optional": tag == "OptionalDependencies",
                        },
                    )
                )
        elif tag == "VersionConstraints":
            for c in child:
                if local(c.tag) != "constraint":
                    continue
                lib = attr(c, "lib", "name", default="constraint")
                reason = attr(c, "reason", default="")
                nid = f"tech-constraint:{lib}"
                graph.add_node(
                    Node(
                        id=nid,
                        name=f"Constraint: {lib}",
                        type=NodeType.CONSTRAINT,
                        description=short_desc(
                            f"{lib} min={attr(c, 'min')} max={attr(c, 'max')} — {reason}"
                        ),
                        source="technology",
                        properties={
                            "lib": lib,
                            "min": attr(c, "min"),
                            "max": attr(c, "max"),
                            "reason": reason,
                        },
                    )
                )
        elif tag == "Tooling":
            for tool in child:
                if local(tool.tag) != "tool":
                    continue
                name = attr(tool, "name", default="tool")
                value = attr(tool, "value", default="")
                version = attr(tool, "version", default="")
                nid = f"tech-tool:{name}"
                graph.add_node(
                    Node(
                        id=nid,
                        name=name,
                        type=NodeType.TECHNOLOGY,
                        description=short_desc(f"{value} {version}".strip()),
                        source="technology",
                        properties={"kind": "tool", "value": value, "version": version},
                    )
                )

    if runtime or language:
        graph.add_node(
            Node(
                id="tech:runtime",
                name=runtime or language or "Runtime",
                type=NodeType.TECHNOLOGY,
                description=short_desc(f"Runtime: {runtime}; Language: {language}"),
                source="technology",
                properties={"kind": "runtime", "language": language, "runtime": runtime},
            )
        )
        # Soft constraint edge from project modules is deferred (no single project node).
        graph.meta["technology_runtime"] = runtime
        graph.meta["technology_language"] = language
        # Mark modules as constrained by runtime (inferred, single edge to tech:runtime via meta only).
        _ = EdgeType.CONSTRAINED_BY
        _ = Provenance
        _ = rel
