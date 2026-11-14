#!/usr/bin/env python3
"""Plan survey cases offline or execute one in an isolated simulator stack.

Never attaches to an operator stack; never changes truth, pose, parameters or
operator workspaces. Commands/evidence are retained under simulation/logs.
"""
import argparse
from datetime import datetime, timezone
import gzip
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, urlopen
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parent)]
from gcs.app.competition import generate_run as generate_legacy_run
from gcs.app.run_builder import generate_run as generate_ordered_run

def generate_run(object_map, run, *args, **kwargs):
    return (generate_ordered_run if run.get("steps") else generate_legacy_run)(object_map, run, *args, **kwargs)
from gcs.app.imports import import_points

ROOT=Path(__file__).resolve().parents[2]
LOGS=ROOT/'simulation/logs'


def write(path, data):
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def isolated_output(path):
    path=path.resolve()
    if not path.is_relative_to(LOGS.resolve()):
        raise ValueError('output must be under ignored simulation/logs')
    path.mkdir(parents=True,exist_ok=False)
    return path


def plan(surveys, run_input, output):
    output=isolated_output(output)
    run=json.loads(run_input.read_text())
    write(output/'run-input.json',run)
    reports=[]
    for survey in sorted(surveys.rglob('survey.json')):
        directory=output/survey.parent.name;directory.mkdir()
        (directory/'survey.json').write_bytes(survey.read_bytes())
        if (survey.parent/'changes.json').exists():(directory/'changes.json').write_bytes((survey.parent/'changes.json').read_bytes())
        m=import_points(survey.read_text());write(directory/'imported-map.json',m)
        result=generate_run(m,run)
        write(directory/'generation.json',result)
        report={'case':survey.parent.name,'planning':'generated' if result['success'] else 'search_exhausted' if any(e.get('code')=='search_exhausted' for e in result.get('errors',[])) else 'rejected',
                'planned_route_valid':result.get('validation',{}).get('valid'), 'actual_motion':'not_executed','diagnostics':result['diagnostics']}
        write(directory/'report.json',report);reports.append(report)
        print(report,flush=True)
    write(output/'summary.json',reports)


def command(*args):
    return subprocess.check_output(list(map(str,args)),text=True).strip()


def refuse_operator_runtime():
    containers=[json.loads(line) for line in command('docker','ps','--format','{{json .}}').splitlines()]
    active=[c['Names'] for c in containers if any(k in (c['Names']+' '+c['Image']).lower() for k in ('maritime','ardupilot','survey-'))]
    native=subprocess.run(['pgrep','-af','(^|/)(ardurover|gz sim|sim_vehicle.py)( |$)'],capture_output=True,text=True)
    if active or native.returncode==0:
        raise ValueError('Refusing to replace or overlap active operator runtime: '+', '.join(active)+' '+native.stdout.strip())
    return containers


def execute(args):
    import fcntl
    LOGS.mkdir(exist_ok=True)
    lock_name='.'+args.output.name+'.lock' if args.parallel_isolated else '.launcher.lock'
    with (LOGS/lock_name).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.parallel_isolated:
            # Explicit test-only opt-in: every new service shares a fresh bridge
            # namespace, never host/operator networking, and a unique GZ partition.
            before=[json.loads(line) for line in command('docker','ps','--format','{{json .}}').splitlines()]
        else:
            before=refuse_operator_runtime()
        output=isolated_output(args.output)
        write(output/'containers-before.json',before)
        # Only execute generated, independently map-validated complete runs.
        source=json.loads((args.case/'generation.json').read_text())
        if not source['success'] or not source.get('validation',{}).get('valid'):
            write(output/'report.json',{'planning':'rejected','actual_motion':'not_executed','reason':'Case did not generate a valid complete run'})
            return
        survey=(args.case/'survey.json').read_text()
        (output/'survey.json').write_text(survey)
        (output/'planned-generation.json').write_bytes((args.case/'generation.json').read_bytes())
        if (args.case/'changes.json').exists():
            (output/'changes.json').write_bytes((args.case/'changes.json').read_bytes())
        run=source['draft'];run['attempt']={'mode':'full','start_source':'live'}
        runtime=output/'runtime';runtime.mkdir();(runtime/'generated-worlds').mkdir()
        command(sys.executable,ROOT/'simulation/scripts/render_scenario.py','--scenario',ROOT/'simulation/scenarios/competition.json','--base-world',ROOT/'simulation/worlds/blueboat_rgbd_base.sdf','--output-world',runtime/'generated-worlds/active.sdf','--manifest',runtime/'generated-worlds/active.manifest.json','--cameras','off')
        command(sys.executable,ROOT/'simulation/scripts/render_water.py','--source',runtime/'generated-worlds/active.sdf','--output',runtime/'generated-worlds/water.sdf','--water','calm','--metadata',runtime/'generated-worlds/water.json')
        start=(ROOT/'simulation/container/start-sim.sh').read_text().replace('gz sim -v4 -r', 'gz sim -s -v4 -r')
        (output/'start-headless.sh').write_text(start)
        tag='survey-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')+'-'+str(os.getpid())
        names=[tag+'-sim',tag+'-boat',tag+'-gcs'];started=[]
        write(output/'images.json',{image:json.loads(command('docker','image','inspect',image)) for image in (args.sim_image,args.boat_image,args.gcs_image)})
        write(output/'source.json',{'git_head':command('git','-C',ROOT,'rev-parse','HEAD'),'diff':command('git','-C',ROOT,'diff'),'file_sha256':{str(p.relative_to(ROOT)):__import__('hashlib').sha256(p.read_bytes()).hexdigest() for area in ('gcs/app','gcs/frontend/src','boat/boat_app','shared','simulation/scripts') for p in (ROOT/area).iterdir() if p.is_file() and p.suffix in ('.py','.js','.jsx','.css')},'run_input':run})
        api_base=f'http://127.0.0.1:{args.port}/api/'
        session_key=None
        def api(path,method='GET',body=None):
            if path in ('import','workspace') and method in ('POST','PUT'):
                body={**body,'revision':api('workspace')['revision']}
            req=Request(api_base+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json',**({'X-Planner-Session':session_key} if session_key else {})})
            with urlopen(req,timeout=75) as response:return json.load(response)
        def wait_for(predicate,seconds=120):
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                try:
                    value=predicate()
                    if value:return value
                except (OSError,ValueError):pass
                time.sleep(.5)
            raise TimeoutError('Isolated runtime readiness timed out')
        def operation(path):
            receipt=api(path,'POST');write(output/(path+'-receipt.json'),receipt)
            value=wait_for(lambda: (lambda r:r if r['state'] not in ('pending','running') else None)(api('operations/'+receipt['operation_id'])),60)
            write(output/(path+'-result.json'),value)
            if value['state']!='succeeded':raise ValueError(path+' rejected: '+str(value))
        def latest(truth):
            with truth.open('rb') as stream:
                stream.seek(max(0,truth.stat().st_size-131072));return json.loads(stream.read().split(b'\n')[-2])
        try:
            started.append(names[0])
            command('docker','run','-d','--network','bridge','--name',names[0],'-p',f'127.0.0.1:{args.port}:8082','--user',f'{os.getuid()}:{os.getgid()}',
                    '-v',f'{runtime}:/sim','-v',f'{output}/start-headless.sh:/start-headless.sh:ro','-e','WORLD=water.sdf','-e','RUN_ID=survey','-e','SCENARIO=competition','-e','GZ_PARTITION='+tag,'--entrypoint','bash',args.sim_image,'/start-headless.sh')
            started.append(names[1])
            command('docker','run','-d','--name',names[1],'--network','container:'+names[0],'-v',f'{ROOT}:/repo:ro','-e','PYTHONPATH=/repo/boat:/repo','-e','ROS_LOG_DIR=/tmp/ros','-e','ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST',args.boat_image,'python3','-m','boat_app.node','--ros-args','-p','connection:=udpin:127.0.0.1:14551')
            workspace=output/'workspace';workspace.mkdir()
            started.append(names[2])
            command('docker','run','-d','--name',names[2],'--network','container:'+names[0],'-v',f'{ROOT}/gcs/app:/app/app:ro','-v',f'{ROOT}/shared:/app/shared:ro','-v',f'{ROOT}/gcs/frontend/dist:/app/static:ro','-v',f'{workspace}:/data',args.gcs_image,'uvicorn','app.main:app','--host','0.0.0.0','--port','8082')
            write(output/'containers.json',{name:json.loads(command('docker','inspect',name))[0] for name in started})
            truth=runtime/'runs/survey/truth.jsonl'
            status=wait_for(lambda: (lambda s:s if s.get('position') and s.get('heartbeat_age_s',99)<=3 and s.get('position_age_s',99)<=3 else None)(api('status')),180)
            wait_for(lambda: truth.exists() and truth.stat().st_size>10000)
            # Let estimator/pre-arm checks settle without force arming or tuning.
            settled_start = latest(truth)['time_s']
            wait_for(lambda: latest(truth)['time_s'] >= settled_start+45, 240)
            from scene_snapshot import verify
            from export_map import export
            identity=verify(runtime/'runs/survey/scene')
            physical=export(runtime/'runs/survey/scene',identity['scene_id'],'survey')
            # Physical scene export is evaluator input only, never imported for planning.
            write(output/'physical-truth.json',physical)
            session_key=api('session','POST')['session_id']
            api('import','POST',{'content':survey})
            if 'steps' not in run:
                from shared.run_builder import relationships
                run.update(planning_mode='run',steps=[{'id':task,'type':task,'setup':run['task_setup'][task]} for task in run['selected_tasks']],shared_crossings=[])
                if run.get('share_gate'):
                    run['shared_crossings']=[{k:r[k] for k in ('gate_id','slalom_id','signature')} for r in relationships(import_points(survey),run) if r['compatible']]
            api('workspace','PUT',{'run_draft':run})
            generated=api('generate','POST');write(output/'generation.json',generated)
            if not generated['success']:
                write(output/'report.json',{'planning':'rejected','actual_motion':'not_executed','diagnostics':generated['diagnostics']});return
            validation=api('validate','POST')
            if not validation['valid']:raise ValueError('Generated route validation rejected: '+str(validation))
            approval=api('approve','POST');write(output/'approval.json',approval)
            start_sample=latest(truth);start_s=start_sample['time_s']
            operation('upload');operation('start')
            if args.disconnect_gcs:
                command('docker','stop',names[2])
            deadline=time.monotonic()+approval['envelope']['mission']['timeout_s']+45
            if args.disconnect_gcs:
                # Read boat status inside its network namespace; the GCS stays stopped.
                def boat_status():
                    return json.loads(command('docker','exec',names[1],'python3','-c',"import json,urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8091/status').read().decode())"))
            else:boat_status=lambda:api('status')
            return_draft=None;return_start_s=None
            with (output/'observations.jsonl').open('w') as stream:
                while time.monotonic()<deadline:
                    status=boat_status();stream.write(json.dumps({'wall_time':time.time(),**status})+'\n');stream.flush()
                    inside_return=False
                    if args.return_inside_channel:
                        from shared.task_geometry import channel_geometry
                        from shared.course import contained
                        from shared.geometry import to_local
                        m=import_points(survey)
                        for step in generated['draft'].get('steps',[]):
                            if step['type']=='channel':
                                polygon,_,_=channel_geometry(m,step['setup'])
                                p=to_local(status['position'],m['geographic_reference'])
                                inside_return=contained(p,p,polygon,generated['draft']['clearance_m']+2)
                    if inside_return or ((args.interrupt_after_s or args.return_after_s) and time.monotonic()>=deadline-(approval['envelope']['mission']['timeout_s']+45)+(args.interrupt_after_s or args.return_after_s)):
                        if args.disconnect_gcs:raise ValueError('interrupt check requires GCS connected')
                        operation('stop');time.sleep(6)
                        rejected=False
                        try:api('start','POST')
                        except OSError:rejected=True
                        status=api('status')
                        write(output/'interruption.json',{'restart_rejected':rejected,'status':status,'run_consumed':api('workspace').get('run_consumed')})
                        if not rejected or status.get('state') != 'stopped':
                            raise ValueError('Interruption check failed: stopped run resumed or restart was accepted')
                        if args.return_after_s:break
                        break
                    if status.get('state') in ('complete','failed','stopped','interrupted'):
                        break
                    time.sleep(.5)
            if status.get('state') == 'complete':
                time.sleep(6)  # independent physics must include >=5 s beyond GPS completion
            outbound_end_s=latest(truth)['time_s']
            if args.return_after_s or args.return_after_complete or args.return_inside_channel:
                if args.disconnect_gcs:raise ValueError('Return evaluation requires GCS connected')
                returned=api('return/prepare','POST');write(output/'return-generation.json',returned)
                if not returned['success']:raise ValueError('Return planning rejected: '+str(returned['diagnostics']))
                return_draft=returned['draft']
                if not api('validate','POST')['valid']:raise ValueError('Return validation rejected')
                write(output/'return-approval.json',api('approve','POST'))
                # Explicit disarm is required even if status reports disarmed.
                operation('disarm');operation('upload')
                return_start_s=latest(truth)['time_s'];operation('start')
                return_deadline=time.monotonic()+return_draft['execution_budget_s']+45
                with (output/'return-observations.jsonl').open('w') as stream:
                    while time.monotonic()<return_deadline:
                        status=boat_status();stream.write(json.dumps(status)+'\n');stream.flush()
                        if status.get('state') in ('complete','failed','stopped','interrupted'):break
                        time.sleep(.5)
            if return_draft and status.get('state') == 'complete':
                time.sleep(6)  # retain HOLD samples; no motion command or threshold change
            end_s=latest(truth)['time_s']
            with truth.open('r') as src,gzip.open(output/'physics.jsonl.gz','wt') as dst:
                for line in src:
                    if not line.endswith('\n'):
                        break
                    sample=json.loads(line)
                    if sample['time_s'] > end_s:
                        break
                    if start_s<=sample['time_s']:dst.write(line)
            write(output/'session.json',{'start_s':start_s,'end_s':end_s,'status':status,'scene':identity,'gcs_disconnected':args.disconnect_gcs})
            proof = args.contact_proof
            if proof is None:
                # Qualify contact evidence after the mission window with a
                # disarmed boat; never steer or modify scene objects.
                control = """import json,time,urllib.request
base='http://127.0.0.1:8091/'
for path in ('stop','disarm'):
    receipt=json.load(urllib.request.urlopen(urllib.request.Request(base+path,method='POST')))
    for _ in range(200):
        result=json.load(urllib.request.urlopen(base+'operations/'+receipt['operation_id']))
        if result['state'] not in ('pending','running'):break
        time.sleep(.1)
    if result['state']!='succeeded':raise RuntimeError(result)
print(json.dumps(result))
"""
                write(output/'post-run-disarm.json',json.loads(command('docker','exec',names[1],'python3','-c',control)))
                final_pose=next(p['pose'] for p in latest(truth)['poses'] if p['name']=='blueboat/base_link')
                def set_pose(values):
                    import math
                    x,y,z,roll,pitch,yaw=values
                    req=f'name:"blueboat",position:{{x:{x},y:{y},z:{z}}},orientation:{{z:{math.sin(yaw/2)},w:{math.cos(yaw/2)}}}'
                    response=command('docker','exec',names[0],'gz','service','-s','/world/blueboat_rgbd/set_pose','--reqtype','gz.msgs.Pose','--reptype','gz.msgs.Boolean','--timeout','10000','--req',req)
                    if 'true' not in response:raise ValueError('Contact verification pose service rejected')
                samples=[]
                try:
                    x,y,z=physical['buoys'][0]['world_centre']
                    for lateral in (.35, -.35, .2):
                        offset=truth.stat().st_size
                        set_pose([x,y+lateral,.1,0,0,0])
                        time.sleep(1.5)
                        # Contacts can last only a few physics steps. Inspect
                        # every complete new record, not just the latest tick.
                        with truth.open('rb') as stream:
                            stream.seek(offset)
                            lines=stream.read().split(b'\n')[1:-1]
                        for line in lines:
                            sample=json.loads(line)
                            if sample.get('contacts'):samples.append(sample)
                            if len(samples)>=10:break
                        if samples:break
                finally:
                    set_pose(final_pose)
                restored=wait_for(lambda: (lambda sample: sample if math.dist(next(p['pose'][:2] for p in sample['poses'] if p['name']=='blueboat/base_link'), final_pose[:2])<.1 else None)(latest(truth)),10)
                write(output/'post-probe-restoration.json',{'expected_pose':final_pose,'physics':restored,'boat_status':boat_status()})
                proof=output/'contact-proof.json'
                write(proof,{'scene_id':physical['scene_id'],'run_id':tag,'method':'disarmed contact after mission window; all new physics records scanned; final pose restored','outcome':'passed' if samples else 'inconclusive','samples':samples})
            from survey_evaluation import evaluation_course
            from evaluate_run import evaluate,read_window,verify_contact_evidence
            from footprint import extract
            course=evaluation_course(physical,generated['draft'],proof)
            course['contact_run_id']=tag
            # Freeze actual polygon mounting orientations from physics, independently.
            poses={p['name']:p['pose'] for p in start_sample['poses']}
            for name,obj in course['polygon_obstacles'].items():obj['pose']=poses[name]
            write(output/'evaluation-course.json',course)
            footprint=extract(runtime/'runs/survey/scene/models/blueboat')
            write(output/'hull-footprint.json',footprint)
            try:
                result=evaluate(read_window(output/'physics.jsonl.gz',start_s,outbound_end_s),footprint,verify_contact_evidence(course,output),start_s,outbound_end_s)
            except (ValueError, KeyError, OSError, TypeError) as error:
                result={'outcome':'inconclusive','missing_evidence':[str(error)]}
            write(output/'evaluation.json',result)
            if return_draft:
                return_course=evaluation_course(physical,return_draft,proof)
                return_course['contact_run_id']=tag
                for name,obj in return_course['polygon_obstacles'].items():obj['pose']=poses[name]
                write(output/'return-evaluation-course.json',return_course)
                return_result=evaluate(read_window(output/'physics.jsonl.gz',return_start_s,end_s),footprint,verify_contact_evidence(return_course,output),return_start_s,end_s)
                write(output/'return-evaluation.json',return_result)
            write(output/'report.json',{'planning':'generated','planned_route_valid':generated['validation']['valid'],'actual_motion':'interrupted' if (args.interrupt_after_s or args.return_after_s or args.return_inside_channel) else result['outcome'],'return_motion':return_result['outcome'] if return_draft else 'not_executed','interruption_check':'passed' if (args.interrupt_after_s or args.return_after_s or args.return_inside_channel) else None,'vehicle_state':status.get('state')})
        except Exception as error:
            write(output/'runtime-failure.json',{'reason':str(error)})
            write(output/'report.json',{'planning':'generated','planned_route_valid':True,'actual_motion':'operation_rejected' if 'rejected' in str(error) else 'inconclusive','reason':str(error)})
            raise
        finally:
            # Stop/disarm through the boat even if GCS has been deliberately removed.
            if names[1] in started:
                subprocess.run(['docker','exec',names[1],'python3','-c',"import urllib.request,time; [urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8091/'+p,method='POST')).read() for p in ('stop','disarm')];time.sleep(2)"],capture_output=True)
            for name in reversed(started):
                (output/(name+'.log')).write_text(subprocess.run(['docker','logs',name],capture_output=True,text=True).stdout+subprocess.run(['docker','logs',name],capture_output=True,text=True).stderr)
                subprocess.run(['docker','rm','-f',name],capture_output=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('plan');a.add_argument('--surveys',type=Path,required=True);a.add_argument('--run-input',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('execute');a.add_argument('--case',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a.add_argument('--port',type=int,default=8082);a.add_argument('--sim-image',default='maritime-sim:latest');a.add_argument('--boat-image',default='maritime-boat:latest');a.add_argument('--gcs-image',default='maritime-gcs:latest');a.add_argument('--contact-proof',type=Path);a.add_argument('--disconnect-gcs',action='store_true');a.add_argument('--interrupt-after-s',type=float);a.add_argument('--parallel-isolated',action='store_true',help='Permit active operator services while using an entirely separate bridge network namespace and GZ partition');a.add_argument('--return-after-s',type=float);a.add_argument('--return-after-complete',action='store_true');a.add_argument('--return-inside-channel',action='store_true')
    args=p.parse_args()
    if args.action=='plan':plan(args.surveys,args.run_input,args.output)
    else:execute(args)


if __name__=='__main__':main()
