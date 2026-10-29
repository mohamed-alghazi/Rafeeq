from __future__ import annotations
import json
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from rafeeq.domain import validate_date


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS applications(id TEXT PRIMARY KEY, owner TEXT, status TEXT);
            INSERT OR IGNORE INTO applications VALUES ('MDR-1001','demo-user','under_review');
            INSERT OR IGNORE INTO applications VALUES ('MDR-2001','other-user','needs_info');
            CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, owner TEXT, application TEXT, day TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS inspections(proposal TEXT PRIMARY KEY, application TEXT, day TEXT);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, event TEXT, detail TEXT, at TEXT DEFAULT CURRENT_TIMESTAMP);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def counts(self, owner: str) -> dict:
        """Evaluation evidence; deliberately not a model-facing tool."""
        with self.connect() as db:
            pending = db.execute("SELECT count(*) FROM proposals WHERE owner=? AND status='pending'", (owner,)).fetchone()[0]
            inspections = db.execute('SELECT count(*) FROM inspections i JOIN proposals p ON i.proposal=p.id WHERE p.owner=?', (owner,)).fetchone()[0]
        return {'pending': pending, 'inspections': inspections}

    def application(self, application_id: str, owner: str) -> dict:
        with self.connect() as db:
            row = db.execute('SELECT id,status FROM applications WHERE id=? AND owner=?', (application_id, owner)).fetchone()
        if not row: raise ValueError('Application not found for this applicant')
        return {'application_id': row[0], 'status': row[1], 'synthetic': True}

    def propose(self, application_id: str, day: str, owner: str) -> dict:
        self.application(application_id, owner)
        day = validate_date(day)
        proposal = secrets.token_urlsafe(18)
        with self.connect() as db:
            db.execute('INSERT INTO proposals VALUES (?,?,?,?,?)', (proposal, owner, application_id, day, 'pending'))
            db.execute('INSERT INTO audit(event,detail) VALUES (?,?)', ('proposed', json.dumps({'id': proposal})))
        return {'proposal_id': proposal, 'application_id': application_id, 'day': day, 'status': 'pending', 'requires_approval': True}

    def pending(self, owner: str) -> list:
        with self.connect() as db:
            rows = db.execute("SELECT id,application,day FROM proposals WHERE owner=? AND status='pending'", (owner,)).fetchall()
        return [dict(zip(('proposal_id','application_id','day'), row)) for row in rows]

    def decide(self, proposal_id: str, approve: bool, owner: str) -> dict:
        if type(approve) is not bool:
            raise ValueError('Approval must be a boolean')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT application,day FROM proposals WHERE id=? AND owner=? AND status='pending'", (proposal_id, owner)).fetchone()
            if not row: raise ValueError('Pending proposal not found')
            self.application(row[0], owner)
            status = 'approved' if approve else 'rejected'
            if approve:
                validate_date(row[1])
                db.execute('INSERT INTO inspections VALUES (?,?,?)', (proposal_id, *row))
            db.execute('UPDATE proposals SET status=? WHERE id=?', (status, proposal_id))
            db.execute('INSERT INTO audit(event,detail) VALUES (?,?)', (status, json.dumps({'id': proposal_id})))
        return {'proposal_id': proposal_id, 'status': status, 'booked': approve}
