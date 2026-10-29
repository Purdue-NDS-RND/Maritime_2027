"""Fixed competition props. Dimensions are estimates recorded in competition.json."""
import math
import re
import xml.etree.ElementTree as ET

COLOURS = {'red':'0.85 0.02 0.02 1', 'green':'0.02 0.8 0.1 1',
           'blue':'0.03 0.25 0.95 1', 'orange':'1 0.4 0 1',
           'purple':'0.65 0.1 0.8 1', 'yellow':'1 0.9 0 1',
           'cyan':'0 0.9 0.95 1', 'zebra':'1 1 1 1',
           'black':'0.02 0.02 0.02 1', 'brown':'0.4 0.22 0.08 1'}


def render_objects(world, config, buoys):
    objects = []
    for item in [*buoys, *config['props']]:
        pose = item.get('resolved_pose', item.get('pose'))
        name = item['name']
        if not isinstance(name,str) or not re.fullmatch(r'[a-z][a-z0-9_]*',name):
            raise SystemExit('Invalid competition identity')
        if not all(type(pose.get(k)) in (int,float) and math.isfinite(pose[k]) for k in ('x','y','z','yaw_deg')):
            raise SystemExit('Invalid competition pose')
        if item['category'] not in COLOURS:
            raise SystemExit('Invalid competition colour')
        if not (-80 <= pose['x'] <= 12 and -28 <= pose['y'] <= 5):
            raise SystemExit('Competition object outside approved course bounds: ' + name)
        kind = item.get('kind', 'buoy')
        model = ET.SubElement(world, 'model', name=name)
        ET.SubElement(model, 'static').text = 'true'
        yaw = math.radians(pose['yaw_deg'])
        ET.SubElement(model, 'pose').text = f"{pose['x']} {pose['y']} {pose['z']} 0 0 {yaw}"
        link = ET.SubElement(model, 'link', name='base_link')
        if kind in ('buoy', 'target'):
            radius = item.get('radius_m', .24)
            height = item.get('height_m', .76)
            if not (0 < radius < 10 and 0 < height < 10):
                raise SystemExit('Invalid competition cylinder')
            shape = f'<cylinder><radius>{radius}</radius><length>{height}</length></cylinder>'
        else:
            size = item['size_m']
            if len(size) != 3 or not all(type(v) in (float, int) and math.isfinite(v) and 0 < v < 10 for v in size):
                raise SystemExit('Invalid competition box')
            height = size[2]
            shape = '<box><size>' + ' '.join(map(str, size)) + '</size></box>'
        for tag in ('collision', 'visual'):
            element = ET.SubElement(link, tag, name='body_' + tag)
            ET.SubElement(element, 'pose').text = f'0 0 {height/2} 0 0 0'
            geometry = ET.SubElement(element, 'geometry')
            geometry.append(ET.fromstring(shape))
            if tag == 'visual':
                material = ET.SubElement(element, 'material')
                for field in ('ambient', 'diffuse'):
                    ET.SubElement(material, field).text = COLOURS[item['category']]
        if item['category'] == 'zebra':
            # A 2 inch wide spiral, constructed from short black surface patches.
            for i in range(96):
                angle = i * math.pi / 16
                stripe = ET.SubElement(link, 'visual', name=f'stripe_{i}')
                ET.SubElement(stripe, 'pose').text = f'{.241*math.cos(angle)} {.241*math.sin(angle)} {.06+i*.0066} 0 0 {angle}'
                ET.SubElement(stripe, 'geometry').append(ET.fromstring('<box><size>0.012 0.055 0.0508</size></box>'))
                material = ET.SubElement(stripe, 'material')
                for field in ('ambient', 'diffuse'):
                    ET.SubElement(material, field).text = COLOURS['black']
        objects.append({**item, 'gazebo_model_name':name, 'model_pose':{**pose, 'yaw_rad':yaw}})
    names = [o['name'] for o in objects]
    if len(set(names)) != len(names):
        raise SystemExit('Duplicate competition object identity')
    return objects
