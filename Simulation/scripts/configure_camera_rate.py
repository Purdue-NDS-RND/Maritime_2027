#!/usr/bin/env python3
"""Create a run-owned model copy with only RGB-D acquisition cadence changed."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


def configure(source, output, rate):
    if not 8 <= rate <= 60:
        raise ValueError('CAMERA_FPS must be finite and between 8 and 60')
    tree = ET.parse(source/'model.sdf')
    cameras = tree.findall('.//sensor[@type="rgbd_camera"]')
    if not cameras:
        raise ValueError('No RGB-D cameras in the selected boat model')
    for sensor in cameras:
        field = sensor.find('update_rate')
        if field is None:
            raise ValueError('RGB-D camera has no declared update_rate')
        field.text = f'{rate:g}'
    shutil.copytree(source, output)
    tree.write(output/'model.sdf', encoding='utf-8', xml_declaration=True)
    return dict(rate_hz=rate, cameras=[c.get('name') for c in cameras],
                source_sha256=hashlib.sha256((source/'model.sdf').read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rate', type=float, required=True)
    args = parser.parse_args()
    metadata = configure(args.source, args.output, args.rate)
    (args.output.parent/'camera-rate.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(f'RGB-D capture: {args.rate:g} Hz simulation time; geometry and calibration preserved')


if __name__ == '__main__':
    main()
