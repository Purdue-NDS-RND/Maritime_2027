#!/usr/bin/env python3
"""Create an evaluation specification for the fixed slalom, never a route."""
import argparse
import json
import hashlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from shared.geometry import to_local


def course(object_map, finish, task, contact_evidence):
    reference=object_map['geographic_reference']
    buoys={b['id']:{'radius_m':b['radius_m']} for b in object_map['buoys']}
    positions={b['id']:to_local(b['centre'],reference)for b in object_map['buoys']}
    def gate(letter):
        red,green='slalom_'+letter+'_red','slalom_'+letter+'_green'
        r,g=positions[red],positions[green]
        if abs(r[0]-g[0])>.001:raise ValueError('unsupported gate orientation')
        return {'id':'gate_'+letter,'kind':'gate','x':r[0],
                'y_min':r[1]+buoys[red]['radius_m'],'y_max':g[1]-buoys[green]['radius_m']}
    passages=[gate('a')]
    if task=='slalom':
        for i in range(1,5):
            colour='red'if i%2 else 'green';name=f'slalom_turn_{i}_{colour}'
            passages.append({'id':name,'kind':'turn','x':positions[name][0],'buoy':name,
                             'side':'left'if colour=='red'else 'right'})
        passages.append(gate('b'))
    return {'schema_version':1,'scene_id':object_map['scene_id'],'buoys':buoys,'passages':passages,
            'minimum_clearance_m':.25,'timeout_s':300,'contact_recorder_verified':bool(contact_evidence),
            'contact_verification_evidence':contact_evidence,
            'finish':{'x':finish[0],'y':finish[1],'radius_m':1,'speed_m_s':.2,'settle_s':5}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('object_map',type=Path);parser.add_argument('--finish-x',type=float,required=True)
    parser.add_argument('--finish-y',type=float,required=True);parser.add_argument('--task',choices=('gate_only','slalom'),required=True)
    parser.add_argument('--contact-evidence',default='');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    object_map=json.loads(args.object_map.read_text())
    result=course(object_map,(args.finish_x,args.finish_y),args.task,args.contact_evidence)
    if args.contact_evidence:
        path=Path(args.contact_evidence).resolve()
        proof=json.loads(path.read_text())
        if proof.get('outcome')!='passed' or proof.get('scene_id')!=object_map['scene_id'] or not any(s.get('contacts') for s in proof.get('samples',[])):
            raise ValueError('contact verification evidence is missing, mismatched or inconclusive')
        result['contact_verification_evidence']=str(path)
        result['contact_verification_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result,indent=2)+'\n')
