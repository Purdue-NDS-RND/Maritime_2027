"""Page-session planning; boat-owned commands and passive live telemetry."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import json
import math
import os
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from fastapi import FastAPI, HTTPException, Request as IncomingRequest
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from .sessions import SessionWorkspace, return_inputs
from .planner import generate
from .course_setup import prepare_task
from .course_compiler import compile_course
from .course_files import load_course, save_course
from .attempts import capture_start
from .run_builder import generate_run
from .telemetry import Telemetry
from .connections import Connections
from shared.clearance import validate_route
from shared.run_builder import digest, relationships, task_input, validate_run
from shared.task_geometry import resolve_geometry

GCS_SESSION_ID = str(uuid.uuid4())
CONNECTIONS = Connections.from_env()
sessions = {}
operations = {}
registry_lock = threading.RLock()


@asynccontextmanager
async def lifespan(app):
    global CONNECTIONS
    CONNECTIONS = Connections.from_env()
    telemetry = Telemetry(CONNECTIONS.telemetry)
    app.state.telemetry = telemetry
    telemetry.start()
    try:
        yield
    finally:
        telemetry.stop()


app = FastAPI(lifespan=lifespan)


@app.middleware('http')
async def same_origin(request: IncomingRequest, call_next):
    origin = request.headers.get('origin')
    if origin and origin not in (os.getenv('GCS_ORIGIN', 'http://localhost:8080'), 'http://127.0.0.1:8080'):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={'detail': 'cross-origin request rejected'})
    return await call_next(request)


def boat(path, method='GET', body=None):
    data = None if body is None else json.dumps(body, allow_nan=False).encode()
    request = Request(CONNECTIONS.boat_url+path, data=data, method=method, headers={'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=5) as response:
            return json.load(response)
    except HTTPError as error:
        raise HTTPException(error.code, json.loads(error.read()).get('detail', 'boat rejected command')) from error
    except (URLError, TimeoutError, ConnectionError) as error:
        raise HTTPException(503, 'boat request outcome unknown; query status/operations before retrying start') from error


def checked(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (ValueError, KeyError, TypeError, OSError, IndexError) as error:
        raise HTTPException(422, str(error)) from error


def session(request):
    value = sessions.get(request.headers.get('x-planner-session'))
    if value is None:
        raise HTTPException(409, 'Planner session expired: start a new empty session')
    return value


@app.post('/api/session')
def create_session():
    key = str(uuid.uuid4())
    with registry_lock:
        sessions[key] = SessionWorkspace()
    return {'session_id': key, 'backend_id': GCS_SESSION_ID, 'workspace': sessions[key].read()}


@app.post('/api/reset')
def reset(request: IncomingRequest):
    return session(request).reset()


@app.get('/api/workspace')
def read(request: IncomingRequest):
    return session(request).read()


@app.put('/api/workspace')
def edit(request: IncomingRequest, data: dict):
    return checked(session(request).edit, data)


@app.post('/api/import')
def import_map(request: IncomingRequest, data: dict):
    w = session(request)
    value = checked(load_course, data['content'], data.get('format', 'json'))
    return checked(w.import_course, value, data.get('revision'))


@app.post('/api/map/history')
def map_history(request: IncomingRequest, data: dict):
    return checked(session(request).history, data.get('direction'), data.get('revision'))


@app.put('/api/course/hints')
def course_hints(request: IncomingRequest, data: dict):
    return checked(session(request).set_hints, data.get('hints', {}), data.get('revision'))


@app.post('/api/course/compile')
async def compile_map(request: IncomingRequest, data: dict):
    w = session(request)
    state, token = checked(w.begin_compilation, data.get('revision'))
    result = await run_in_threadpool(checked, compile_course, state['map'], state['compiler_hints'])
    if await request.is_disconnected():
        raise HTTPException(409, 'Interrupted compilation discarded')
    return checked(w.publish_compilation, result, token)


@app.post('/api/course/select')
def select_course(request: IncomingRequest, data: dict):
    if data.get('clear'):
        return checked(session(request).clear_assignment, data.get('task'), data.get('revision'))
    return checked(session(request).select_compilation, data.get('task'), data.get('candidate_id'), data.get('revision'))


@app.get('/api/course/file')
def course_file(request: IncomingRequest):
    return checked(save_course, session(request).read())


@app.get('/api/examples/competition')
def competition_example():
    path = Path(os.getenv('GCS_EXAMPLES', str(Path(__file__).resolve().parents[1]/'examples')))/'competition-gps-map.json'
    return checked(lambda: json.loads(path.read_text()))


@app.post('/api/course/prepare')
def prepare(request: IncomingRequest, data: dict):
    state = session(request).read()
    if not state['map']:
        raise HTTPException(422, 'Load a map first')
    assignment = state['course_assignments'].get(data['task'])
    accepted = assignment['roles'] if assignment and assignment['status']=='accepted' else None
    return checked(prepare_task, state['map'], data['task'], {**state['run_draft']['settings'], **data.get('settings', {})}, accepted)


@app.post('/api/course/geometry')
def geometry(request: IncomingRequest, data: dict):
    state = session(request).read()
    step = next((s for s in state['run_draft']['steps'] if s['id'] == data.get('instance_id')), None)
    if not step:
        raise HTTPException(422, 'Select a card instance first')
    d = checked(task_input, state['run_draft'], step, state['run_draft']['start'], True)
    resolved = checked(resolve_geometry, state['map'], d)
    return {k: resolved[k] for k in ('derived_sections', 'channel') if k in resolved}


@app.post('/api/run/relationship')
def run_relationship(request: IncomingRequest):
    state = session(request).read()
    return checked(relationships, state['map'], state['run_draft'])


@app.post('/api/generate')
def generate_route(request: IncomingRequest):
    w = session(request)
    state, token = w.begin_generation()
    draft = state['run_draft']
    if not state['map'] or draft.get('planning_mode') != 'run':
        raise HTTPException(422, 'Load a map and build a run first; returns use Return now')
    status = boat('/status') if draft.get('attempt', {}).get('start_source', 'live') == 'live' else None
    result = checked(generate_run, state['map'], draft, status)
    if result['success']:
        result['workspace'] = checked(w.publish, result['draft'], token)
    else:
        result['workspace'] = w.read()
    return result


@app.post('/api/validate')
def validate(request: IncomingRequest):
    return checked(session(request).validate)


@app.post('/api/approve')
def approve(request: IncomingRequest):
    return checked(session(request).approve)


def fresh_vehicle():
    status = boat('/status')
    if not status.get('position') or any(not isinstance(status.get(k), (int,float)) or not math.isfinite(status[k]) or not 0 <= status[k] <= 3 for k in ('position_age_s', 'heartbeat_age_s')):
        raise HTTPException(409, 'Fresh vehicle position and heartbeat required (at most three seconds)')
    return status


def validate_actual_start(approval):
    status = fresh_vehicle()
    d = approval['inputs']['draft']
    if d.get('planning_mode') == 'run':
        result = checked(validate_run, approval['inputs']['map'], d, status['position'])
    else:
        from shared.geometry import to_local
        ref = approval['inputs']['map']['geographic_reference']
        if math.dist(to_local(d['start'], ref), to_local(status['position'], ref)) > 1:
            raise HTTPException(409, 'Boat moved more than 1 m from approved return start: prepare again')
        result = checked(validate_route, approval['inputs']['map'], {**d, 'start': status['position']})
    if not result['valid']:
        raise HTTPException(409, result)
    return status


def record(value, w, command, approval=None):
    if value.get('operation_id'):
        operations[value['operation_id']] = (w, command, deepcopy(approval), w.authority_epoch)
    if value.get('state') == 'succeeded' and value.get('operation_id'):
        reconcile(value['operation_id'], value)
    return value


def reconcile(operation_id, value):
    entry = operations.get(operation_id)
    if entry and value.get('state') == 'succeeded':
        w, command, approval, epoch = entry
        if command == 'start':
            w.start_succeeded(approval)
        elif command == 'upload' and epoch == w.authority_epoch:
            w.uploaded_id = approval['envelope']['approval_id']
        elif command == 'disarm' and epoch == w.authority_epoch:
            w.disarm_epoch = epoch
        operations.pop(operation_id, None)
    elif value.get('state') in ('failed', 'cancelled', 'unknown'):
        operations.pop(operation_id, None)
    return value


@app.post('/api/upload')
def upload(request: IncomingRequest):
    w = session(request)
    approval = checked(w.approved)
    status = validate_actual_start(approval)
    if status.get('armed') is not False or status.get('mode') == 10:
        raise HTTPException(409, 'Explicitly disarm outside AUTO before replacement upload')
    if approval['inputs']['draft'].get('planning_mode') == 'return' and getattr(w, 'disarm_epoch', None) != w.authority_epoch:
        raise HTTPException(409, 'Explicit Disarm confirmation required after preparing this return')
    envelope = approval['envelope']
    return record(boat('/missions/'+quote(envelope['mission']['mission_id'], safe=''), 'PUT', envelope), w, 'upload', approval)


@app.post('/api/start')
def start(request: IncomingRequest):
    w = session(request)
    with w.lock:
        approval = checked(w.approved)
        status = validate_actual_start(approval)
        mission_id = approval['envelope']['approval_id']
        if getattr(w, 'uploaded_id', None) != mission_id or status.get('mission_id') != mission_id or status.get('state') != 'uploaded':
            raise HTTPException(409, 'Confirmed upload/readback of this approval required before Start')
        if w.cancelled.is_set():
            raise HTTPException(409, 'Start interrupted by Stop; generate and approve again')
        w.state.update(run_consumed=True, approval=None, execution={'mission_id':mission_id, 'generation_identity':approval['inputs']['draft'].get('generation_identity')})
        w.authority_epoch += 1
        epoch = w.authority_epoch
        w.started_approval = mission_id
    if w.cancelled.is_set() or epoch != w.authority_epoch:
        raise HTTPException(409, 'Start interrupted by Stop')
    try:
        value = boat('/missions/'+quote(mission_id, safe='')+'/start', 'POST')
    finally:
        if w.cancelled.is_set() or epoch != w.authority_epoch:
            boat('/stop', 'POST')
    return record(value, w, 'start', approval)


@app.post('/api/stop')
def stop(request: IncomingRequest):
    # Priority command never waits for a planner lock or valid page session.
    w = sessions.get(request.headers.get('x-planner-session'))
    if w:
        w.cancelled.set()
    try:
        return boat('/stop', 'POST')
    finally:
        w = sessions.get(request.headers.get('x-planner-session'))
        if w:
            w.consume_run()


@app.post('/api/disarm')
def disarm(request: IncomingRequest):
    value = boat('/disarm', 'POST')
    w = sessions.get(request.headers.get('x-planner-session'))
    return record(value, w, 'disarm') if w else value


def return_water(object_map, run):
    waters = []
    for step in run.get('steps', []):
        if step['type'] == 'channel':
            if not step['setup'].get('course_confirmed'):
                raise ValueError('Confirm current channel water restrictions before preparing return')
            d = task_input(run, step, run['start'], True)
            resolved = resolve_geometry(object_map, d)
            first = resolved['derived_sections'][0]
            water = {'polygon': resolved['channel'], 'opening': [first['a'], first['b']], 'direction': first['direction']}
            if water not in waters:
                waters.append(water)
    return waters


@app.post('/api/return/prepare')
def prepare_return(request: IncomingRequest, data: dict | None = None):
    w = session(request)
    if not w.read()['return_target']:
        raise HTTPException(409, 'Return now needs a successfully started run in this page session')
    w.cancelled.set()
    try:
        receipt = boat('/stop', 'POST')
    finally:
        w.consume_run()
    if data:
        checked(w.edit, data)
    # Clear prior geometry before waiting for HOLD, even on later failure.
    state, token = w.begin_generation()
    target = deepcopy(state['return_target'])
    stop_id = receipt.get('operation_id')
    deadline = time.monotonic()+15
    while True:
        operation = boat('/operations/'+quote(stop_id, safe='')) if stop_id else receipt
        if operation.get('state') in ('failed', 'unknown', 'cancelled'):
            raise HTTPException(409, 'Return HOLD failed: '+operation.get('detail', operation['state']))
        status = fresh_vehicle()
        speed = status.get('speed_m_s')
        if operation.get('state') == 'succeeded' and status.get('mode') == 4 and isinstance(speed, (int,float)) and math.isfinite(speed) and 0 <= speed <= .2:
            break
        if time.monotonic() >= deadline:
            raise HTTPException(409, 'Return requires confirmed HOLD and reported speed ≤0.20 m/s; timed out without movement')
        time.sleep(.1)
    run = checked(return_inputs, state)
    if not state['map'] or not run.get('sizes_confirmed'):
        raise HTTPException(422, 'Review the current map before preparing return')
    water = checked(return_water, state['map'], run)
    draft = {**deepcopy(run['settings']), 'settings': deepcopy(run['settings']), 'planning_mode': 'return', 'task': 'custom',
             'start': deepcopy(status['position']), 'finish': target, 'return_target': target, 'waypoints': [],
             'finish_radius_m': 1, 'sizes_confirmed': True, 'course_confirmed': True,
             'planning_area': deepcopy(run['planning_area']), 'navigation_water': water, 'execution_budget_s': run['execution_budget_s'],
             'attempt': {'mode': 'full', 'start_source': 'live'}}
    draft = capture_start(draft, status)
    result = checked(generate, state['map'], draft, navigation=True)
    if not result['success']:
        return {**result, 'workspace': w.read()}
    generated = result['draft']
    generated['generation_identity'] = digest(generated)
    result['workspace'] = checked(w.publish, generated, token)
    return result


@app.get('/api/status')
def status():
    return boat('/status')


@app.get('/api/connections')
def connections():
    return CONNECTIONS.snapshot()


@app.get('/api/telemetry')
def telemetry_snapshot(request: IncomingRequest):
    return {**request.app.state.telemetry.snapshot(), 'gcs_session_id': GCS_SESSION_ID}


async def telemetry_events(telemetry):
    while True:
        yield 'data: '+json.dumps({**telemetry.snapshot(), 'gcs_session_id': GCS_SESSION_ID}, allow_nan=False)+'\n\n'
        await asyncio.sleep(.2)


@app.get('/api/telemetry/events')
async def live_telemetry(request: IncomingRequest):
    return StreamingResponse(telemetry_events(request.app.state.telemetry), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.get('/api/operations/{operation_id}')
def operation(operation_id: str):
    return reconcile(operation_id, boat('/operations/'+quote(operation_id, safe='')))


static = Path(os.getenv('GCS_STATIC', '/app/static'))
if static.is_dir():
    app.mount('/', StaticFiles(directory=static, html=True), name='frontend')
