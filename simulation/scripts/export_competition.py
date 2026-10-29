"""Export the supported fixed collision primitives from a competition snapshot."""
import math
import xml.etree.ElementTree as ET
from shared.geometry import finite, to_gps, transform_polygon


def export_objects(world, manifest, reference):
    models = {m.get('name'): m for m in world.findall('./world/model') if m.get('name') != 'water_surface'}
    records = []
    objects = [*manifest['buoys'], *manifest['props']]
    if set(models) != {o['name'] for o in objects}:
        raise ValueError('unexpected or missing competition models')
    for item in objects:
        model = models[item['name']]
        pose = [finite(float(v)) for v in model.findtext('pose').split()]
        expected = item['model_pose']
        if pose != [expected[k] for k in ('x','y','z')] + [0,0,expected['yaw_rad']]:
            raise ValueError('manifest/world pose mismatch')
        if model.findtext('static') != 'true' or len(model.findall('link')) != 1:
            raise ValueError('unsupported competition model')
        link = model.find('link')
        if any(float(v) != 0 for v in link.findtext('pose', '0 0 0 0 0 0').split()):
            raise ValueError('unsupported link transform')
        collisions = link.findall('collision')
        if len(collisions) != 1:
            raise ValueError('unsupported competition collision count')
        collision = collisions[0]
        mount = [finite(float(v)) for v in collision.findtext('pose').split()]
        if len(mount) != 6 or mount[:2] != [0,0] or mount[3:] != [0,0,0]:
            raise ValueError('unsupported collision transform')
        record = {'id':item['name'], 'category':item['category'], 'task':item['task'],
                  'centre':to_gps(*pose[:2], reference), 'world_centre':pose[:3]}
        cylinder = collision.find('geometry/cylinder')
        box = collision.find('geometry/box')
        if cylinder is not None:
            radius, height = (finite(float(cylinder.findtext(k))) for k in ('radius','length'))
            if not (0 < radius < 10 and 0 < height < 10):
                raise ValueError('invalid cylinder')
            record.update(type='cylinder', radius_m=radius, height_m=height)
        elif box is not None:
            size = [finite(float(v)) for v in box.findtext('size').split()]
            if len(size) != 3 or not all(0 < v < 10 for v in size):
                raise ValueError('invalid box')
            x, y, height = size
            polygon = transform_polygon([(-x/2,-y/2),(x/2,-y/2),(x/2,y/2),(-x/2,y/2)], *pose[:2], pose[5])
            record.update(type='polygon', footprint=[to_gps(*p,reference) for p in polygon], height_m=height)
        else:
            raise ValueError('unsupported collision primitive')
        if abs(mount[2]-height/2) > 1e-9:
            raise ValueError('unsupported collision height')
        records.append(record)
    buoy_names = {o['name'] for o in manifest['buoys']}
    stations = []
    for item in manifest['stations']:
        station = {k:v for k,v in item.items() if k != 'world_position'}
        station['position'] = to_gps(*item['world_position'], reference)
        stations.append(station)
    start = manifest['boat_pose']
    boat_pose = [float(v) for v in world.find('./world/include/pose').text.split()]
    if boat_pose != [start[k] for k in ('x','y','z')] + [0,0,start['yaw_rad']]:
        raise ValueError('manifest/world boat pose mismatch')
    return {'schema_version':2, 'buoys':[r for r in records if r['id'] in buoy_names],
            'obstacles':[r for r in records if r['id'] not in buoy_names], 'stations':stations,
            'start_pose':{'position':to_gps(start['x'],start['y'],reference),
                          'heading_deg':(90-math.degrees(start['yaw_rad']))%360},
            'source':manifest['source'], 'approximation_notes':manifest['approximation_notes']}
