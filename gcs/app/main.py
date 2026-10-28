"""FastAPI backend; boat HTTP is the sole vehicle interface."""
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from fastapi import FastAPI, HTTPException, Request as IncomingRequest
from fastapi.staticfiles import StaticFiles
from .workspace import Workspace
from shared.clearance import validate_route

workspace = Workspace(os.getenv('GCS_DATA', '/data'), os.getenv('GCS_PROFILES', '/profiles'))
app = FastAPI()


@app.middleware('http')
async def same_origin(request: IncomingRequest, call_next):
    origin = request.headers.get('origin')
    if origin and origin not in ('http://localhost:8080', 'http://127.0.0.1:8080'):
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


@app.get('/api/profiles')
def profiles():
    return [json.loads(path.read_text()) for path in workspace.profiles.glob('*.json')]


@app.post('/api/validate')
def validate():
    return checked(workspace.validate)


@app.post('/api/approve')
def approve():
    return checked(workspace.approve)


def validate_actual_start(approval):
    status = boat('/status')
    if status.get('position_age_s') is None or status['position_age_s'] > 3 or status.get('heartbeat_age_s') is None or status['heartbeat_age_s'] > 3:
        raise HTTPException(409, 'fresh vehicle position/heartbeat required')
    # Validate the actual start connection as well as the frozen planned start.
    draft = {**approval['inputs']['draft'], 'start': status['position'], 'start_heading_deg': status.get('heading_deg')}
    result = checked(validate_route, approval['inputs']['map'], draft, approval['inputs']['profile'])
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


@app.get('/api/operations/{operation_id}')
def operation(operation_id: str):
    return boat('/operations/' + quote(operation_id, safe=''))


static = Path(os.getenv('GCS_STATIC', '/app/static'))
if static.is_dir():
    app.mount('/', StaticFiles(directory=static, html=True), name='frontend')
