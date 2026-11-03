"""Boat HTTP owns commands; passive MAVLink supplies map telemetry."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from fastapi import FastAPI, HTTPException, Request as IncomingRequest
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from .workspace import Workspace, sha
from .imports import import_points
from .planner import suggest, generate
from .course_setup import prepare_task
from .settings import effective_settings
from .attempts import capture_start, check_remaining_snapshot, suggest_remaining
from .telemetry import Telemetry, TelemetryConfig
from shared.clearance import validate_route

workspace = Workspace(os.getenv('GCS_DATA', '/data'))
GCS_SESSION_ID = str(uuid.uuid4())


@asynccontextmanager
async def lifespan(app):
    telemetry = Telemetry(TelemetryConfig.from_env())
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
    if origin and origin not in (os.getenv('GCS_ORIGIN','http://localhost:8080'), 'http://127.0.0.1:8080'):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={'detail': 'cross-origin request rejected'})
    return await call_next(request)


def boat(path, method='GET', body=None):
    data = None if body is None else json.dumps(body, allow_nan=False).encode()
    request = Request('http://127.0.0.1:8091' + path, data=data, method=method,
                      headers={'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=5) as response:
            return json.load(response)
    except HTTPError as error:
        raise HTTPException(error.code, json.loads(error.read()).get('detail', 'boat rejected command')) from error
    except (URLError, TimeoutError) as error:
        raise HTTPException(503, 'boat request outcome unknown; query status/operations before retrying start') from error


def checked(function, *args):
    try:
        return function(*args)
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise HTTPException(422, str(error)) from error


@app.get('/api/workspace')
def read():
    return workspace.read()


@app.put('/api/workspace')
def edit(data: dict):
    return checked(workspace.edit, data)


@app.post('/api/import')
def import_map(data: dict):
    object_map = checked(import_points, data['content'], data.get('format', 'json'))
    return checked(workspace.edit, {'map': object_map, 'new_import': True, 'course': {}})


@app.get('/api/examples/competition')
def competition_example():
    path=Path(os.getenv('GCS_EXAMPLES',str(Path(__file__).resolve().parents[1]/'examples')))/'competition-gps-map.json'
    return checked(lambda: json.loads(path.read_text()))


@app.post('/api/course/prepare')
def prepare(data: dict):
    state=workspace.read()
    if not state.get('map'):
        raise HTTPException(422,'Load a map first')
    settings = {**(data.get('settings') or state.get('draft') or {})}
    if state.get('settings_configured'):
        settings.update(effective_settings(state['game_settings'], data['task']))
    return checked(prepare_task,state['map'],data['task'],settings)


@app.post('/api/course/suggest')
def suggestions(data: dict):
    return checked(suggest, workspace.read()['map'], data['direction'])


@app.post('/api/course/geometry')
def geometry():
    from shared.task_geometry import resolve_geometry
    state=workspace.read()
    draft={**state['draft'],'attempt':{'mode':'full'}}
    resolved=checked(resolve_geometry,state['map'],draft)
    return {key:resolved.get(key) for key in ('derived_sections','channel') if key in resolved}


@app.post('/api/course/remaining')
def remaining():
    state=workspace.read()
    draft=state['draft']
    status=boat('/status') if draft.get('attempt',{}).get('start_source','live')=='live' else None
    draft=checked(capture_start,draft,status)
    return checked(suggest_remaining,state['map'],draft)


@app.post('/api/generate')
def generate_route():
    with workspace.lock:
        state = workspace.read()
        if not state.get('map') or not state.get('draft'):
            raise HTTPException(422, 'import map and select a task first')
        state=checked(workspace.edit, {'draft': state['draft']})
        draft=state['draft']
        if draft.get('geometry_version')==2:
            status=boat('/status') if draft.get('attempt',{}).get('start_source','live')=='live' else None
            draft=checked(capture_start,draft,status)
            checked(check_remaining_snapshot,state['map'],draft)
        result = checked(generate, state['map'], draft)
        if result['success']:
            result['workspace'] = checked(workspace.edit, {'draft': result['draft']})
        return result


@app.post('/api/validate')
def validate():
    return checked(workspace.validate)


@app.post('/api/approve')
def approve():
    return checked(workspace.approve)


def validate_actual_start(approval):
    status = boat('/status')
    import math
    if not status.get('position') or any(not isinstance(status.get(k),(int,float)) or not math.isfinite(status[k]) or not 0<=status[k]<=3 for k in ('position_age_s','heartbeat_age_s')):
        raise HTTPException(409, 'fresh vehicle position/heartbeat required')
    # Validate the actual start connection as well as the frozen planned start.
    draft = {**approval['inputs']['draft'], 'start': status['position'], 'start_heading_deg': status.get('heading_deg')}
    try:
        result = validate_route(approval['inputs']['map'], draft)
    except (ValueError,KeyError,TypeError) as error:
        raise HTTPException(409, str(error)) from error
    if not result['valid']:
        raise HTTPException(409, result)


@app.post('/api/upload')
def upload():
    approval = checked(workspace.approved)
    validate_actual_start(approval)
    envelope = approval['envelope']
    return boat('/missions/' + quote(envelope['mission']['mission_id'], safe=''), 'PUT', envelope)


@app.post('/api/start')
def start():
    approval = checked(workspace.approved)
    validate_actual_start(approval)
    return boat('/missions/' + quote(approval['envelope']['mission']['mission_id'], safe='') + '/start', 'POST')


@app.post('/api/stop')
def stop():
    return boat('/stop', 'POST')


@app.post('/api/disarm')
def disarm():
    return boat('/disarm', 'POST')


@app.get('/api/status')
def status():
    return boat('/status')


@app.get('/api/telemetry')
def telemetry_snapshot(request: IncomingRequest):
    return {**request.app.state.telemetry.snapshot(), 'gcs_session_id': GCS_SESSION_ID}


async def telemetry_events(telemetry):
    # One latest snapshot per tick. No client queue can accumulate an old track.
    while True:
        yield 'data: ' + json.dumps({**telemetry.snapshot(), 'gcs_session_id': GCS_SESSION_ID}, allow_nan=False) + '\n\n'
        await asyncio.sleep(0.2)


@app.get('/api/telemetry/events')
async def live_telemetry(request: IncomingRequest):
    return StreamingResponse(telemetry_events(request.app.state.telemetry),
                             media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.get('/api/operations/{operation_id}')
def operation(operation_id: str):
    return boat('/operations/' + quote(operation_id, safe=''))


static = Path(os.getenv('GCS_STATIC', '/app/static'))
if static.is_dir():
    app.mount('/', StaticFiles(directory=static, html=True), name='frontend')
