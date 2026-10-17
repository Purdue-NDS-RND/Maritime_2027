#!/usr/bin/env python3
"""Create an RGB-D-equipped BlueBoat without changing its dynamics."""

from __future__ import annotations

import argparse
import copy
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET


INSERTED_NAMES = {"zed2i_camera_visual", "zed2i_rgbd_camera"}


def structural(element: ET.Element) -> tuple:
    """Return a whitespace-insensitive representation of an XML subtree."""
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        (element.text or "").strip(),
        tuple(structural(child) for child in element),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boat-model", choices=("single", "dual"), default="single")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_bytes = args.source.read_bytes()
    actual_hash = hashlib.sha256(source_bytes).hexdigest()
    if actual_hash != args.expected_sha256:
        raise SystemExit(
            f"BlueBoat source hash mismatch: expected {args.expected_sha256}, got {actual_hash}"
        )

    source_tree = ET.ElementTree(ET.fromstring(source_bytes))
    original_structure = structural(source_tree.getroot())
    base_link = source_tree.find("./model/link[@name='base_link']")
    if base_link is None:
        raise SystemExit("BlueBoat source has no model/base_link")

    payload_tree = ET.parse(args.payload)
    payload_link = payload_tree.find("./model/link[@name='base_link']")
    if payload_link is None:
        raise SystemExit("Payload document has no model/base_link")

    additions = list(payload_link)
    approved_names = INSERTED_NAMES if args.boat_model == "single" else {
        f"camera_{i}_{kind}" for i in range(2) for kind in ("visual", "rgbd")}
    names = {item.get("name") for item in additions}
    if len(additions) != len(approved_names) or names != approved_names or {item.tag for item in additions} != {"sensor", "visual"}:
        raise SystemExit("Payload must contain exactly the approved sensors and visuals")
    if any(base_link.find(f"./*[@name='{name}']") is not None for name in approved_names):
        raise SystemExit("BlueBoat source already contains an approved payload name")

    for item in additions:
        base_link.append(copy.deepcopy(item))

    audit_root = copy.deepcopy(source_tree.getroot())
    audit_link = audit_root.find("./model/link[@name='base_link']")
    assert audit_link is not None
    for item in list(audit_link):
        if item.get("name") in approved_names:
            audit_link.remove(item)
    if structural(audit_root) != original_structure:
        raise SystemExit("Structural audit failed: non-payload BlueBoat XML changed")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(source_tree, space="  ")
    source_tree.write(args.output, encoding="utf-8", xml_declaration=True)
    print(f"Generated {args.output} from verified BlueBoat source {actual_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
