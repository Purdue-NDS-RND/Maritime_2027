"""Single command worker shared by ROS and HTTP. Only this worker owns MAVLink."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import queue
import threading
import time
import uuid

from .executor import MissionError
from .mission import Mission, fields


class Control:
    def __init__(self, controller, directory):
        self.controller = controller
        self.directory = Path(directory)
        self.journal = self.directory / 'operations.json'
        self.lock = threading.RLock()
        self.queue = queue.PriorityQueue()
        self.cancelled = threading.Event()
        self.closing = threading.Event()
        self.sequence = 0
        self.epoch = 0
        self.snapshot = controller.status()
        self.registry = json.loads(self.journal.read_text()) if self.journal.exists() else {'missions': {}, 'operations': {}}
        for operation in self.registry['operations'].values():
            if operation['state'] in ('pending', 'running'):
                operation.update(state='unknown', detail='boat process restarted; inspect actual vehicle state')
        self.controller.cancel_check = self.check_cancel
        self.controller.on_receive = self.refresh
        self.thread = threading.Thread(target=self.run, name='boat-command-owner', daemon=True)
        self.thread.start()

    def check_cancel(self):
        if self.cancelled.is_set() or self.closing.is_set():
            raise MissionError('operation cancelled by STOP or shutdown')

    def refresh(self):
        with self.lock:
            self.snapshot = deepcopy(self.controller.status())
            self.snapshot['snapshot_monotonic_s'] = time.monotonic()

    def status(self):
        with self.lock:
            result = deepcopy(self.snapshot)
        # Ages must advance even if the worker is waiting for a response.
        age = max(0, time.monotonic() - result.pop('snapshot_monotonic_s', time.monotonic()))
        for key in ('heartbeat_age_s', 'position_age_s'):
            if result.get(key) is not None:
                result[key] += age
        return result

    def save(self):
        temporary = self.journal.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.registry, indent=2, allow_nan=False) + '\n')
        temporary.replace(self.journal)

    def operation(self, operation_id):
        with self.lock:
            if operation_id not in self.registry['operations']:
                raise KeyError('unknown operation')
            return deepcopy(self.registry['operations'][operation_id])

    def submit(self, command, envelope=None, mission_id=None):
        with self.lock:
            if self.closing.is_set():
                raise ValueError('boat shutting down')
            mission = None
            if command == 'upload':
                fields(envelope, ('approval_id', 'revision_sha256', 'mission'), 'transfer envelope')
                for key in ('approval_id', 'revision_sha256'):
                    if not isinstance(envelope[key], str) or not envelope[key].strip():
                        raise ValueError(f'{key} required')
                mission = Mission.parse(envelope['mission'])
                if mission_id != mission.mission_id:
                    raise ValueError('mission ID differs from URL')
                sha = hashlib.sha256(json.dumps(envelope, sort_keys=True).encode()).hexdigest()
                old = self.registry['missions'].get(mission_id)
                if old:
                    if old['sha256'] != sha:
                        raise ValueError('mission ID already belongs to conflicting content')
                    return self.operation(old['upload_operation'])
            elif command == 'start':
                old = self.registry['missions'].get(mission_id)
                if old is None:
                    raise ValueError('mission has not been received')
                if old.get('start_operation'):
                    return self.operation(old['start_operation'])
                upload = self.registry['operations'][old['upload_operation']]
                if upload['state'] != 'succeeded' or self.snapshot.get('mission_id') != mission_id or self.snapshot.get('state') != 'uploaded':
                    raise ValueError('mission upload/readback not confirmed in this session')
            elif command not in ('stop', 'disarm'):
                raise ValueError('unknown command')
            operation_id = str(uuid.uuid4())
            operation = {'operation_id': operation_id, 'command': command, 'mission_id': mission_id,
                         'state': 'pending', 'detail': 'received; vehicle acceptance pending'}
            self.registry['operations'][operation_id] = operation
            if command == 'upload':
                self.registry['missions'][mission_id] = {'sha256': sha, 'upload_operation': operation_id,
                                                        'envelope': deepcopy(envelope)}
            elif command == 'start':
                old['start_operation'] = operation_id
            if command == 'stop':
                self.epoch += 1
                self.cancelled.set()
            self.save()
            self.sequence += 1
            self.queue.put((0 if command == 'stop' else 1, self.sequence, self.epoch, operation_id, mission))
            return deepcopy(operation)

    def run(self):
        while not self.closing.is_set():
            try:
                priority, sequence, epoch, operation_id, mission = self.queue.get(timeout=0.05)
            except queue.Empty:
                try:
                    self.controller.tick()
                except Exception as error:
                    # A queued STOP will clear cancellation and confirm HOLD.
                    if not self.cancelled.is_set():
                        self.controller.emit({'event': 'worker_error', 'detail': str(error)})
                self.refresh()
                continue
            with self.lock:
                operation = self.registry['operations'][operation_id]
                operation.update(state='running')
                self.save()
            command = operation['command']
            try:
                if command == 'stop':
                    self.cancelled.clear()
                elif epoch != self.epoch:
                    raise MissionError('operation cancelled by earlier STOP')
                self.check_cancel()
                if command == 'upload':
                    if self.controller.state in ('executing', 'starting', 'stopping'):
                        raise MissionError('stop active mission before replacement')
                    snapshot = self.directory / f'mission-{mission.sha256}.json'
                    snapshot.write_text(json.dumps(mission.as_dict(), indent=2) + '\n')
                    self.controller.upload(mission)
                elif command == 'start':
                    if self.controller.mission is None or self.controller.mission.mission_id != operation['mission_id']:
                        raise MissionError('mission is no longer current')
                    self.controller.start()
                else:
                    getattr(self.controller, command)()
                result = ('succeeded', self.controller.detail)
            except Exception as error:
                result = ('failed', str(error))
            self.refresh()
            with self.lock:
                operation.update(state=result[0], detail=result[1])
                self.save()
            self.queue.task_done()
        # Shutdown safety also belongs to the sole MAVLink worker.
        self.controller.cancel_check = lambda: None
        if self.controller.state in ('executing', 'stopping', 'starting'):
            self.controller.fail('boat application shutting down')
        self.controller.link.close()

    def close(self):
        self.closing.set()
        self.cancelled.set()
        self.thread.join(timeout=20)
        if self.thread.is_alive():
            raise RuntimeError('boat worker did not terminate; control outcome unknown')
        with self.lock:
            for operation in self.registry['operations'].values():
                if operation['state'] in ('pending','running'):
                    operation.update(state='unknown',detail='boat shut down before confirmation; inspect actual state')
            self.save()
