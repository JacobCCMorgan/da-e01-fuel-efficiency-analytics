"""Local ELD event simulator with immutable snapshots and stable paging.

This is an explicitly simulated source, not a real ELD vendor integration.
SQLite is only the simulator's paging index, not the operational database.
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager, closing
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .common import digest, json_text


def cursor_token(snapshot: str, last_seq: int) -> str:
    return base64.urlsafe_b64encode(json_text([snapshot, last_seq]).encode()).decode()


def read_cursor(token: str, snapshot: str) -> int:
    value = json.loads(base64.urlsafe_b64decode(token.encode()))
    if not isinstance(value, list) or len(value) != 2 or value[0] != snapshot:
        raise ValueError('cursor does not match source snapshot')
    if not isinstance(value[1], int) or value[1] < 0:
        raise ValueError('invalid cursor sequence')
    return value[1]


def index_events(source: Path, index: Path) -> str:
    source, index = Path(source), Path(index)
    snapshot = digest(source)
    index.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(index)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)')
        old = db.execute("SELECT value FROM metadata WHERE key='snapshot'").fetchone()
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone()
        if old and old[0] == snapshot and exists:
            return snapshot
    temp = index.with_suffix('.building.sqlite')
    if temp.exists():
        temp.unlink()
    with closing(sqlite3.connect(temp)) as db:
        db.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)')
        db.execute('DROP TABLE IF EXISTS staging')
        db.execute('CREATE TABLE staging (source_line INTEGER, available_time TEXT, event_id TEXT, revision INTEGER, body TEXT)')
        batch = []
        with source.open() as stream:
            for n, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    at = str(event.get('available_time') or '')
                    event_id = str(event.get('event_id') or '')
                    revision = int(event.get('revision') or 0)
                except (ValueError, TypeError, AttributeError):
                    event = {'transport_error': 'invalid_json', 'raw_line': line.rstrip()}
                    at, event_id, revision = '', '', 0
                batch.append((n, at, event_id, revision, json_text(event)))
                if len(batch) == 5000:
                    db.executemany('INSERT INTO staging VALUES (?,?,?,?,?)', batch)
                    batch.clear()
        if batch:
            db.executemany('INSERT INTO staging VALUES (?,?,?,?,?)', batch)
        db.execute('DROP TABLE IF EXISTS events')
        db.execute('CREATE TABLE events (seq INTEGER PRIMARY KEY, source_line INTEGER, available_time TEXT, body TEXT)')
        db.execute('INSERT INTO events(source_line,available_time,body) SELECT source_line,available_time,body FROM staging ORDER BY available_time,event_id,revision,source_line')
        db.execute('CREATE INDEX events_available ON events(available_time,seq)')
        db.execute('DROP TABLE staging')
        db.execute("INSERT OR REPLACE INTO metadata VALUES ('snapshot',?)", (snapshot,))
        db.commit()
    os.replace(temp,index)
    return snapshot


def make_handler(index: Path, snapshot: str):
    faults_seen = set()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def send_json(self, status, payload, headers=None):
            body = json_text(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == '/health':
                with sqlite3.connect(index) as db:
                    total = db.execute('SELECT count(*) FROM events').fetchone()[0]
                self.send_json(200, {'status':'ok','source_kind':'synthetic_eld_api','snapshot':snapshot,'total_events':total})
                return
            if u.path != '/v1/events':
                self.send_json(404, {'error':'not_found'})
                return
            q = parse_qs(u.query)
            try:
                limit = int(q.get('limit', ['2000'])[0])
                if limit < 1 or limit > 10000:
                    raise ValueError('limit must be between 1 and 10000')
                last = read_cursor(q['cursor'][0], snapshot) if 'cursor' in q else 0
                since = q.get('available_since', [''])[0]
                if since:
                    datetime.fromisoformat(since.replace('Z','+00:00'))
            except (ValueError, TypeError, KeyError):
                self.send_json(409 if 'cursor' in q else 400, {'error':'invalid_query_or_snapshot_cursor'})
                return
            # Deliberate fault injection is documented and only used in tests.
            fault = q.get('test_fault', [''])[0]
            marker = (fault, last)
            with lock:
                first_fault = bool(fault and marker not in faults_seen)
                if first_fault:
                    faults_seen.add(marker)
            if first_fault and fault in ('once_429','once_503'):
                self.send_json(int(fault[-3:]), {'error':'simulated_transient'}, {'Retry-After':'0'})
                return
            if first_fault and fault == 'once_slow':
                time.sleep(.15)
            with sqlite3.connect(index) as db:
                found = db.execute('SELECT seq,source_line,body FROM events WHERE seq>? AND available_time>=? ORDER BY seq LIMIT ?', (last, since, limit+1)).fetchall()
            page, more = found[:limit], len(found)>limit
            events = [{'source_sequence':x[0],'source_line':x[1],'envelope':json.loads(x[2])} for x in page]
            last_seen = page[-1][0] if page else last
            self.send_json(200, {'source_kind':'synthetic_eld_api','snapshot':snapshot,'items':events,'next_cursor':cursor_token(snapshot,last_seen) if more else None,'checkpoint_cursor':cursor_token(snapshot,last_seen)})

    return Handler


@contextmanager
def serve(root: Path, port: int = 0):
    root = Path(root)
    index = root / 'data/api/event_index.sqlite'
    snapshot = index_events(root/'data/raw/events.jsonl', index)
    server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(index, snapshot))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

