"""Build the Iris survey scene from the existing competition coordinates."""

import argparse
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import cv2
from cv2 import aruco

from competition_scene import render_objects


ASSETS = Path(__file__).resolve().parent
DICTIONARY = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
COURSE_MARKER_SIDE_M = 0.48
TAKEOFF_MARKER_SIDE_M = 2.0
SURFACE_OFFSET_M = 0.002


def add_marker_visual(link, marker_id, height, size):
    # The 6x6 tag has an additional one-cell white quiet zone on every edge.
    if hasattr(aruco, "generateImageMarker"):
        tag = aruco.generateImageMarker(DICTIONARY, marker_id, 384)
    else:
        tag = aruco.drawMarker(DICTIONARY, marker_id, 384)
    texture = cv2.copyMakeBorder(tag, 64, 64, 64, 64, cv2.BORDER_CONSTANT, value=255)
    filename = f"aruco_{marker_id:02d}.png"
    if not cv2.imwrite(str(ASSETS / filename), cv2.cvtColor(texture, cv2.COLOR_GRAY2BGR)):
        raise RuntimeError(f"Could not write {filename}")

    # Lift the visual off its supporting surface to avoid z-fighting.
    link.append(ET.fromstring(f"""
      <visual name="aruco_{marker_id:02d}">
        <pose>0 0 {height + SURFACE_OFFSET_M} 0 0 0</pose>
        <cast_shadows>false</cast_shadows>
        <geometry><plane><normal>0 0 1</normal><size>{size} {size}</size></plane></geometry>
        <material>
          <ambient>1 1 1 1</ambient><diffuse>1 1 1 1</diffuse>
          <pbr><metal>
            <albedo_map>{ASSETS / filename}</albedo_map>
            <metalness>0</metalness><roughness>1</roughness>
          </metal></pbr>
        </material>
      </visual>
    """))


def add_ground_marker(world, marker_id, source_name, x, y, size):
    model = ET.SubElement(world, "model", name=f"aruco_{marker_id:02d}")
    ET.SubElement(model, "static").text = "true"
    ET.SubElement(model, "pose").text = f"{x} {y} 0 0 0 0"
    link = ET.SubElement(model, "link", name="marker")
    add_marker_visual(link, marker_id, 0, size)
    return marker_id, source_name, x, y, size * 0.75, SURFACE_OFFSET_M


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iris_sdf", type=Path)
    args = parser.parse_args()

    tree = ET.parse(ASSETS / "flat_course.sdf")
    world = tree.find("world")
    course = json.loads((ASSETS / "competition.json").read_text())
    props = render_objects(world, course, [])
    towers = [prop for prop in props if prop["kind"] == "detector"]
    if 1 + len(course["buoys"]) + len(towers) > 50:
        raise SystemExit("Takeoff, buoy and tower markers must fit in DICT_4X4_50")
    rows = [add_ground_marker(world, 0, "takeoff", 0, 0, TAKEOFF_MARKER_SIDE_M)]
    for marker_id, buoy in enumerate(course["buoys"], start=1):
        pose = buoy["pose"]
        rows.append(add_ground_marker(
            world, marker_id, buoy["name"], pose["x"], pose["y"], COURSE_MARKER_SIDE_M
        ))
    for marker_id, tower in enumerate(towers, start=len(rows)):
        name = tower["gazebo_model_name"]
        link = world.find(f"model[@name='{name}']/link[@name='base_link']")
        width, depth, height = tower["size_m"]
        size = min(COURSE_MARKER_SIDE_M, width, depth)
        add_marker_visual(link, marker_id, height, size)
        pose = tower["model_pose"]
        rows.append((marker_id, name, pose["x"], pose["y"], size * 0.75,
                     pose["z"] + height + SURFACE_OFFSET_M))

    ET.indent(tree)
    tree.write(ASSETS / "iris_competition.sdf", encoding="utf-8", xml_declaration=True)
    with (ASSETS / "markers.csv").open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("id", "source_name", "east_m", "north_m", "tag_side_m", "up_m"))
        writer.writerows(rows)
    origin = world.find("spherical_coordinates")
    (ASSETS / "sitl-home.txt").write_text(",".join(
        origin.findtext(field) for field in ("latitude_deg", "longitude_deg", "elevation", "heading_deg")
    ) + "\n")

    iris = ET.parse(args.iris_sdf)
    body = iris.find("./model/link[@name='base_link']")
    if body is None or body.find("sensor[@name='down_camera']") is not None:
        raise SystemExit("Expected an unmodified Iris base_link")
    body.append(ET.parse(ASSETS / "down_camera.sdf").getroot())
    iris.write(args.iris_sdf, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    main()
