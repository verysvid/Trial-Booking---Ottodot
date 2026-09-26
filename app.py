"""Dependency-free JSON API and CLI. Local synthetic demo, not a production server."""
import argparse
import json
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from booking import Store, Problem
from seed import seed


def positive(value):
    if type(value) is not int or value < 1:
        raise Problem(400, 'IDs must be positive integers')
    return value


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.dispatch()

        def do_POST(self):
            self.dispatch()

        def dispatch(self):
            try:
                path = urlsplit(self.path).path
                if self.command == 'GET' and path == '/health':
                    response = {'status': 'ok', 'mode': 'mock-payment-demo'}
                elif self.command == 'GET' and path == '/classes':
                    response = store.classes()
                elif self.command == 'GET' and (match := re.fullmatch(r'/classes/(\d+)/roster', path)):
                    if self.headers.get('Authorization') != 'Bearer demo-teacher':
                        raise Problem(403, 'Teacher demo token required')
                    response = store.roster(int(match[1]))
                else:
                    # Fixed synthetic credentials, explicitly not production authentication.
                    auth = self.headers.get('Authorization', '')
                    if auth not in ('Bearer demo-parent-1', 'Bearer demo-parent-2', 'Bearer demo-parent-3'):
                        raise Problem(401, 'Parent demo token required')
                    parent = int(auth[-1])
                    body = {}
                    if self.command == 'POST':
                        try:
                            length = int(self.headers.get('Content-Length', '0'))
                        except ValueError:
                            raise Problem(400, 'Invalid Content-Length')
                        if not 1 <= length <= 4096:
                            raise Problem(400, 'Expected a JSON object of at most 4096 bytes')
                        try:
                            body = json.loads(self.rfile.read(length))
                        except (ValueError, UnicodeError):
                            raise Problem(400, 'Malformed JSON')
                        if not isinstance(body, dict):
                            raise Problem(400, 'Expected a JSON object')
                    if self.command == 'GET' and path == '/children':
                        response = store.children(parent)
                    elif self.command == 'POST' and path == '/bookings':
                        response = store.book(parent, positive(body.get('student_id')), positive(body.get('class_id')))
                    elif self.command == 'GET' and (match := re.fullmatch(r'/bookings/(\d+)', path)):
                        response = store.get(parent, int(match[1]))
                    elif self.command == 'POST' and (match := re.fullmatch(r'/bookings/(\d+)/mock-payment', path)):
                        response = store.pay(parent, int(match[1]), body.get('idempotency_key'), body.get('result'))
                    else:
                        raise Problem(404, 'Route not found')
                self.reply(200, response)
            except Problem as exc:
                self.reply(exc.status, {'error': str(exc)})
            except sqlite3.OperationalError as exc:
                if 'locked' in str(exc).lower() or 'busy' in str(exc).lower():
                    self.reply(503, {'error': 'Database busy; retry the same request and payment key'})
                else:
                    self.log_error('Database failure: %s', exc)
                    self.reply(500, {'error': 'Database error'})

        def reply(self, status, value):
            payload = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(payload)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='trials.db')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('seed')
    server = sub.add_parser('serve')
    server.add_argument('--port', default=8000, type=int)
    roster = sub.add_parser('roster')
    roster.add_argument('class_id', type=int)
    args = parser.parse_args()
    if args.command == 'seed':
        seed(args.db)
        print('Seeded. Class 1: four seats available. Class 2: one seat available.')
    elif args.command == 'roster':
        print(json.dumps(Store(args.db).roster(args.class_id), indent=2))
    else:
        from pathlib import Path
        if not Path(args.db).is_file():
            parser.error('Database missing: run seed first')
        print(f'Mock trial API: http://127.0.0.1:{args.port}', flush=True)
        ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(Store(args.db))).serve_forever()


if __name__ == '__main__':
    main()
