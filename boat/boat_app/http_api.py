"""Loopback development HTTP transport; no MAVLink access on HTTP threads."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import unquote, urlsplit


def serve(control, port=8091):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, value):
            data = json.dumps(value, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def handle_request(self):
            # Reject browser-origin cross-site requests to the control API.
            if self.headers.get('Origin') is not None:
                return self.reply(403, {'detail': 'browser requests must use the GCS backend'})
            parts = [unquote(part) for part in urlsplit(self.path).path.strip('/').split('/')]
            try:
                if self.command == 'GET' and parts == ['status']:
                    return self.reply(200, control.status())
                if self.command == 'GET' and len(parts) == 2 and parts[0] == 'operations':
                    return self.reply(200, control.operation(parts[1]))
                if self.command == 'PUT' and len(parts) == 2 and parts[0] == 'missions':
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 262144:
                        raise ValueError('mission request size must be 1..262144 bytes')
                    self.connection.settimeout(5)
                    envelope = json.loads(self.rfile.read(length))
                    return self.reply(202, control.submit('upload', envelope, parts[1]))
                if self.command == 'POST':
                    if len(parts) == 3 and parts[0] == 'missions' and parts[2] == 'start':
                        return self.reply(202, control.submit('start', mission_id=parts[1]))
                    if parts in (['stop'], ['disarm']):
                        return self.reply(202, control.submit(parts[0]))
                return self.reply(404, {'detail': 'unknown endpoint'})
            except KeyError as error:
                self.reply(404, {'detail': str(error)})
            except (ValueError, TypeError) as error:
                self.reply(409, {'detail': str(error)})
        do_GET = do_POST = do_PUT = handle_request
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    threading.Thread(target=server.serve_forever, name='boat-http', daemon=True).start()
    return server
