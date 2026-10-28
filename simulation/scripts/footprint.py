#!/usr/bin/env python3
"""Extract a conservative convex footprint from pinned collision meshes.

Uses STL vertices for the hull and a full rotation sphere for each propulsor.
The sphere remains conservative at every propeller joint angle. Geometry is
relative to base_link/IMU origin, rather than the inertial centre of mass.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET


def hull(points):
    points = sorted(set(points))
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    def half(values):
        result = []
        for p in values:
            while len(result) >= 2 and cross(result[-2], result[-1], p) <= 0:
                result.pop()
            result.append(p)
        return result
    return half(points)[:-1] + half(points[::-1])[:-1]


def stl_vertices(path):
    data = Path(path).read_bytes()
    count = struct.unpack_from('<I', data, 80)[0] if len(data) >= 84 else 0
    if len(data) == 84 + count * 50:
        return [struct.unpack_from('<fff', data, 84 + n * 50 + 12 + i * 12)
                for n in range(count) for i in range(3)]
    return [tuple(map(float, line.split()[1:])) for line in data.decode().splitlines()
            if line.strip().startswith('vertex ')]


def dae_radius(path):
    ns = {'c': 'http://www.collada.org/2005/11/COLLADASchema'}
    tree = ET.parse(path)
    asset = tree.find('c:asset/c:unit', ns)
    scale = float(asset.get('meter', '1')) if asset is not None else 1
    radii = []
    geometries = {g.get('id'): g for g in tree.findall('.//c:geometry', ns)}
    nodes = tree.findall('.//c:visual_scene/c:node', ns)
    for node in nodes:
        if node.find('c:node', ns) is not None:
            raise ValueError('nested DAE nodes unsupported')
        if any(node.find('c:' + tag, ns) is not None for tag in ('translate', 'rotate', 'scale')):
            raise ValueError('unsupported DAE transform representation')
        matrix = node.find('c:matrix', ns)
        values = list(map(float, matrix.text.split())) if matrix is not None else [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
        if len(values) != 16 or values[12:] != [0,0,0,1]:
            raise ValueError('unsupported DAE homogeneous transform')
        for instance in node.findall('c:instance_geometry', ns):
            geometry = geometries[instance.get('url').lstrip('#')]
            position_ids = {i.get('source').lstrip('#') for i in geometry.findall('c:mesh/c:vertices/c:input', ns)
                            if i.get('semantic') == 'POSITION'}
            for source in geometry.findall('c:mesh/c:source', ns):
                if source.get('id') not in position_ids:
                    continue
                coordinates = list(map(float, source.find('c:float_array', ns).text.split()))
                for i in range(0, len(coordinates), 3):
                    point = coordinates[i:i+3] + [1]
                    transformed = [sum(values[row*4+col]*point[col] for col in range(4)) for row in range(3)]
                    radii.append(math.sqrt(sum(v*v for v in transformed)) * scale)
    if not radii:
        raise ValueError('no DAE positions')
    return max(radii)


def extract(directory):
    directory = Path(directory)
    tree = ET.parse(directory / 'model.sdf')
    points, sources, vertical_bounds = [], {'model.sdf': hashlib.sha256((directory / 'model.sdf').read_bytes()).hexdigest()}, []
    for link in tree.findall('./model/link'):
        for collision in link.findall('collision'):
            if collision.find('pose') is not None or collision.find('geometry/mesh/scale') is not None:
                raise ValueError('unsupported collision transform')
            uri = collision.findtext('geometry/mesh/uri', '')
            if not uri.startswith('models://blueboat/'):
                raise ValueError('unsupported collision mesh')
            path = directory / uri[len('models://blueboat/'):]
            sources[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
            if link.get('name') == 'base_link':
                if link.find('pose') is not None:
                    raise ValueError('unsupported hull mounting')
                vertices = stl_vertices(path)
                vertical_bounds.extend(abs(z) for x, y, z in vertices)
                points.extend((x, y) for x, y, z in vertices)
            else:
                pose = list(map(float, link.findtext('pose').split()))
                radius = dae_radius(path)
                vertical_bounds.append(abs(pose[2]) + radius)
                # Circumscribed square encloses the complete rotating prop.
                points.extend((pose[0] + dx*radius, pose[1] + dy*radius)
                              for dx in (-1, 1) for dy in (-1, 1))
    polygon = hull(points)
    if len(polygon) < 3:
        raise ValueError('empty footprint')
    return {'schema_version': 1, 'reference': 'base_link=imu_link', 'reference_offset_m': [0,0,0],
            'method': 'convex hull of hull STL and full-rotation propulsor bounds',
            'polygon': polygon, 'max_abs_z_m': max(vertical_bounds), 'enclosing_radius_m': max(math.hypot(x,y) for x,y in polygon),
            'source_sha256': sources}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(extract(args.model), indent=2) + '\n')
