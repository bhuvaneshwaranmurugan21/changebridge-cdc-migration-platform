#!/usr/bin/env python3
"""Render deterministic views from committed Stage 3 architecture authorities."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def write(path: Path, content: str, *, check: bool) -> None:
    if check:
        if not path.exists() or path.read_text() != content:
            raise SystemExit(f"generated artifact drift: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def svg_document(title: str, nodes: list[str]) -> str:
    width = 1200
    box_width = 440
    box_height = 58
    x = (width - box_width) // 2
    y0 = 90
    gap = 92
    height = y0 + gap * max(len(nodes), 1) + 50
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        (
            '<defs><marker id="arrow" markerWidth="10" markerHeight="10" '
            'refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" '
            'fill="#334155"/></marker></defs>'
        ),
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        (
            '<text x="600" y="42" text-anchor="middle" font-family="Arial" '
            f'font-size="24" font-weight="700" fill="#0f172a">{html.escape(title)}</text>'
        ),
    ]
    positions: list[tuple[int, int]] = []
    for index, label in enumerate(nodes):
        y = y0 + index * gap
        positions.append((x, y))
        parts.append(
            f'<rect x="{x}" y="{y}" width="{box_width}" height="{box_height}" '
            'rx="8" fill="#e0f2fe" stroke="#0369a1" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{width // 2}" y="{y + 35}" text-anchor="middle" '
            'font-family="Arial" font-size="16" fill="#0f172a">'
            f"{html.escape(label)}</text>"
        )
    for index in range(len(nodes) - 1):
        source_x, source_y = positions[index]
        target_x, target_y = positions[index + 1]
        center_x = source_x + box_width // 2
        parts.append(
            f'<line x1="{center_x}" y1="{source_y + box_height}" '
            f'x2="{target_x + box_width // 2}" y2="{target_y - 4}" '
            'stroke="#334155" stroke-width="2" marker-end="url(#arrow)"/>'
        )
    parts.append("</svg>\n")
    return "\n".join(parts)


def plane_svg(components: list[dict[str, Any]]) -> str:
    plane_order = ["data", "control", "evidence"]
    colors = {
        "data": ("#dcfce7", "#15803d"),
        "control": ("#e0f2fe", "#0369a1"),
        "evidence": ("#fef3c7", "#b45309"),
    }
    width = 1500
    column_width = 460
    box_height = 44
    max_nodes = max(
        sum(1 for item in components if item["plane"] == plane) for plane in plane_order
    )
    height = 120 + max_nodes * 62
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        (
            '<text x="750" y="42" text-anchor="middle" font-family="Arial" '
            'font-size="24" font-weight="700" fill="#0f172a">'
            "ChangeBridge responsibility planes</text>"
        ),
    ]
    for column, plane in enumerate(plane_order):
        x = 20 + column * 500
        fill, stroke = colors[plane]
        parts.append(
            f'<rect x="{x}" y="65" width="{column_width}" height="{height - 85}" '
            f'rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{x + column_width // 2}" y="96" text-anchor="middle" '
            'font-family="Arial" font-size="20" font-weight="700" fill="#0f172a">'
            f"{plane.upper()} PLANE</text>"
        )
        plane_components = [item for item in components if item["plane"] == plane]
        for row, item in enumerate(plane_components):
            y = 115 + row * 62
            parts.append(
                f'<rect x="{x + 20}" y="{y}" width="{column_width - 40}" '
                f'height="{box_height}" rx="6" fill="#ffffff" stroke="{stroke}"/>'
            )
            parts.append(
                f'<text x="{x + column_width // 2}" y="{y + 27}" '
                'text-anchor="middle" font-family="Arial" font-size="14" '
                f'fill="#0f172a">{html.escape(str(item["id"]))}</text>'
            )
    parts.append("</svg>\n")
    return "\n".join(parts)


def responsibility_doc(components: list[dict[str, Any]]) -> str:
    lines = [
        "# Responsibility model",
        "",
        "This view is generated from `architecture/components.json`.",
        "The machine-readable file is authoritative.",
        "",
        "![Responsibility planes](../../architecture/diagrams/responsibility-planes.svg)",
        "",
        "Transport moves records, storage holds data, the control plane decides",
        "correctness and publication, and the evidence plane records defensible claims.",
        "",
    ]
    for plane in ("data", "control", "evidence"):
        lines.extend([f"## {plane.title()} plane", ""])
        for item in [value for value in components if value["plane"] == plane]:
            requirements = ", ".join(f"`{value}`" for value in item["requirement_ids"])
            lines.extend(
                [
                    f"### `{item['id']}`",
                    "",
                    str(item["responsibility"]),
                    "",
                    f"- Implementation: `{item['implementation_status']}`",
                    f"- Does not own: {', '.join(item['non_responsibilities'])}",
                    f"- Retry boundary: {item['retry_boundary']}",
                    (f"- Failure: `{item['failure_signal']}`; {item['quarantine_behavior']}"),
                    f"- Requirements: {requirements}",
                    "",
                ]
            )
    return "\n".join(lines)


def adr_index_doc(decisions: list[dict[str, Any]]) -> str:
    lines = [
        "# Architecture decisions",
        "",
        "All decisions are `Accepted` and `DESIGN_ONLY`.",
        "The machine-readable index is `architecture/adr-index.json`.",
        "",
    ]
    for decision in decisions:
        path = Path(str(decision["path"])).name
        lines.append(f"- [{decision['id']}: {decision['title']}]({path})")
    lines.extend(
        [
            "",
            "A later ADR must explicitly name any superseded record and trigger",
            "requirement, claim, model, diagram, and validation review.",
            "",
        ]
    )
    return "\n".join(lines)


def build(root: Path, *, check: bool) -> None:
    components = load_json(root / "architecture/components.json")["components"]
    generation = load_json(root / "architecture/generation-state-machine.json")
    checkpoint = load_json(root / "architecture/checkpoint-state-machine.json")
    adrs = load_json(root / "architecture/adr-index.json")["decisions"]

    write(
        root / "docs/architecture/RESPONSIBILITY_MODEL.md",
        responsibility_doc(components),
        check=check,
    )
    write(root / "docs/adr/README.md", adr_index_doc(adrs), check=check)
    write(
        root / "architecture/diagrams/responsibility-planes.svg",
        plane_svg(components),
        check=check,
    )
    generation_path = [
        "CREATED",
        "SNAPSHOT_LOADING",
        "CDC_APPLYING",
        "SEALED",
        "PROVING",
        "PROVEN",
        "PUBLISHED",
    ]
    generation_ids = {state["id"] for state in generation["states"]}
    if not set(generation_path).issubset(generation_ids):
        raise ValueError("generation happy path is incomplete")
    write(
        root / "architecture/diagrams/generation-lifecycle.svg",
        svg_document("Canonical generation lifecycle", generation_path),
        check=check,
    )
    checkpoint_path = [
        "FRONTIER_PROPOSED",
        "TARGET_COMMIT_IN_PROGRESS",
        "TARGET_COMMIT_DURABLE",
        "CHECKPOINT_COMMIT_IN_PROGRESS",
        "CHECKPOINT_DURABLE",
    ]
    checkpoint_ids = {state["id"] for state in checkpoint["states"]}
    if not set(checkpoint_path).issubset(checkpoint_ids):
        raise ValueError("checkpoint happy path is incomplete")
    write(
        root / "architecture/diagrams/checkpoint-recovery.svg",
        svg_document("Target commit before checkpoint", checkpoint_path),
        check=check,
    )
    proof_path = [
        "SEALED GENERATION",
        "INDEPENDENT GATES",
        "SEALED PROOF MANIFEST",
        "CAS POINTER",
        "CONSUMER VERIFICATION",
    ]
    write(
        root / "architecture/diagrams/proof-publication.svg",
        svg_document("Proof-gated publication", proof_path),
        check=check,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    build(args.root.resolve(), check=args.check)
    message = "architecture views are current" if args.check else "architecture views rendered"
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
