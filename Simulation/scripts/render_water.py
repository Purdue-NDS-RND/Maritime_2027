#!/usr/bin/env python3
"""Apply an existing water preset to a generated copy of any supported scene."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

PRESETS = {'calm': 'blueboat_calm.sdf', 'normal': 'blueboat_waves.sdf',
           'harsh': 'blueboat_harbor.sdf'}


def render(source, output, preset, metadata=None):
    template = Path(__file__).resolve().parents[1]/'worlds'/PRESETS[preset]
    wave = ET.parse(template).find('.//model[@name="water_surface"]/plugin/wave')
    tree = ET.parse(source)
    water = tree.find('.//model[@name="water_surface"]')
    if water is None:
        raise ValueError('Selected world has no supported water_surface model')
    blocks = water.findall('./plugin/wave') + water.findall('./link/visual/plugin/wave')
    if len(blocks) != 2:
        raise ValueError('Expected both physical and visual wave definitions')
    parameters = {key: wave.findtext(key) for key in ('algorithm', 'amplitude', 'period', 'direction')}
    for block in blocks:
        for key, value in parameters.items():
            element = block.find(key)
            if element is None:
                raise ValueError(f'Missing water parameter: {key}')
            element.text = value
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space='  ')
    tree.write(output, encoding='utf-8', xml_declaration=True)
    if metadata:
        metadata.write_text(json.dumps({'preset': preset, **parameters}, indent=2)+'\n')
    print(f'Water: {preset}; amplitude={parameters["amplitude"]} m, period={parameters["period"]} s')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--water', choices=PRESETS, required=True)
    parser.add_argument('--metadata', type=Path)
    args = parser.parse_args()
    render(args.source, args.output, args.water, args.metadata)


if __name__ == '__main__':
    main()
