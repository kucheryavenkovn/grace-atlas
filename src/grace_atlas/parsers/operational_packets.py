# FILE: tools/grace_atlas/src/grace_atlas/parsers/operational_packets.py
# VERSION: 0.1.0
# START_MODULE_CONTRACT
#   PURPOSE: Parse operational-packets.xml templates (real packets if present).
#   SCOPE: OperationalPackets templates and any concrete packet instances
#   DEPENDS: grace_atlas.model, _xmlutil
#   LINKS: tools/grace_atlas
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT

"""Parse GRACE operational packets XML."""

from __future__ import annotations

from pathlib import Path

from grace_atlas.model import AtlasGraph, Edge, EdgeType, Node, NodeType, Provenance
from grace_atlas.parsers._xmlutil import (
    child_text,
    local,
    parse_xml,
    short_desc,
    text_of,
)


def parse_operational_packets(path: Path, graph: AtlasGraph) -> None:
    root = parse_xml(path)
    rel = str(path)

    # Templates and any concrete instances under root.
    for section in root:
        section_tag = local(section.tag)
        is_template = section_tag.endswith("Template")
        for packet in section.iter():
            pt = local(packet.tag)
            if pt not in {
                "ExecutionPacket",
                "CheckpointReport",
                "GraphDelta",
                "VerificationDelta",
                "FailurePacket",
            }:
                continue
            # Only treat as node if it has a real module-id or is a named template.
            module_id = child_text(packet, ("module-id", "module_id"))
            purpose = child_text(packet, ("purpose", "PURPOSE"))
            step_ref = child_text(packet, ("step-ref", "step_ref"))
            verification_id = child_text(packet, ("verification-id", "verification_id"))
            status = child_text(packet, ("status",))

            # Skip pure empty shells
            if not any([module_id, purpose, step_ref, verification_id]) and not is_template:
                continue

            packet_id = f"packet:{pt}:{module_id or step_ref or 'template'}"
            if is_template and module_id in {"", "M-EXAMPLE"}:
                packet_id = f"packet-template:{pt}"

            graph.add_node(
                Node(
                    id=packet_id,
                    name=f"{pt} ({module_id or 'template'})",
                    type=NodeType.OPERATIONAL_PACKET,
                    description=short_desc(purpose or text_of(packet), 400),
                    status=status or ("template" if is_template else ""),
                    source="operational-packets",
                    properties={
                        "packet_kind": pt,
                        "module_id": module_id,
                        "step_ref": step_ref,
                        "verification_id": verification_id,
                        "is_template": is_template or module_id in {"", "M-EXAMPLE"},
                    },
                )
            )

            if module_id and module_id != "M-EXAMPLE":
                if module_id not in graph.nodes:
                    graph.add_node(
                        Node(
                            id=module_id,
                            name=module_id,
                            type=NodeType.MODULE,
                            source="operational-packets",
                            properties={"stub": True},
                        )
                    )
                graph.add_edge(
                    Edge(
                        source=packet_id,
                        target=module_id,
                        type=EdgeType.REFERS_TO,
                        relation_source="module-id",
                        provenance=Provenance.DECLARED,
                        artifact_path=rel,
                    )
                )

            if verification_id and verification_id != "V-M-EXAMPLE":
                if verification_id not in graph.nodes:
                    graph.add_node(
                        Node(
                            id=verification_id,
                            name=verification_id,
                            type=NodeType.VERIFICATION,
                            source="operational-packets",
                            properties={"stub": True},
                        )
                    )
                graph.add_edge(
                    Edge(
                        source=packet_id,
                        target=verification_id,
                        type=EdgeType.VERIFIED_BY,
                        relation_source="verification-id",
                        provenance=Provenance.DECLARED,
                        artifact_path=rel,
                    )
                )
