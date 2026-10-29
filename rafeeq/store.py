from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

from rafeeq.domain import validate_date
from rafeeq.privacy import DIGITS, normalise_mobile, redact, redact_text


DEMO_IDENTITIES = {
    'demo-user': {'application_id': 'MDR-1001', 'last4': '0001', 'mobile': '0550001001'},
    'other-user': {'application_id': 'MDR-2001', 'last4': '0002', 'mobile': '0550002002'},
}
SLA = {'BLD': 15, 'REN': 7, 'SGN': 5, 'FTR': 10, 'EVT': 10}


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS applications(id TEXT PRIMARY KEY, owner TEXT, status TEXT);
            INSERT OR IGNORE INTO applications(id,owner,status) VALUES ('MDR-1001','demo-user','under_review');
            INSERT OR IGNORE INTO applications(id,owner,status) VALUES ('MDR-2001','other-user','needs_info');
            CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, owner TEXT, application TEXT, day TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS inspections(proposal TEXT PRIMARY KEY, application TEXT, day TEXT);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, event TEXT, detail TEXT, at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS identities(owner TEXT PRIMARY KEY, salt TEXT, identity_hash TEXT, mobile_hash TEXT);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, owner TEXT, failed INTEGER DEFAULT 0, verified_until REAL DEFAULT 0, expires REAL);
            CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, session TEXT, role TEXT, content TEXT);
            CREATE TABLE IF NOT EXISTS refunds(id TEXT PRIMARY KEY, application TEXT UNIQUE, amount REAL, status TEXT, proposal TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS escalations(id TEXT PRIMARY KEY, application TEXT UNIQUE, overdue INTEGER, status TEXT, proposal TEXT UNIQUE);
            ''')

            additions = {
                'applications': [('permit_type', "TEXT DEFAULT 'SGN'"), ('fee_paid', 'REAL DEFAULT 750'),
                                 ('submitted', "TEXT DEFAULT '2026-09-01'"), ('duplicate_paid', 'REAL DEFAULT 0')],
                'proposals': [('kind', "TEXT DEFAULT 'inspection'"), ('payload', "TEXT DEFAULT '{}'"), ('session', 'TEXT')],
                'inspections': [('version', 'INTEGER DEFAULT 0')],
                'sessions': [('public', 'INTEGER DEFAULT 0')],
            }
            for table, columns in additions.items():
                existing = {r[1] for r in db.execute(f'PRAGMA table_info({table})')}
                for name, definition in columns:
                    if name not in existing: db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
            for app_id, status, fee, kind in [('MDR-1002','rejected',750,'SGN'),
                                               ('MDR-1003','withdrawn_before_review',1280,'BLD'),
                                               ('MDR-1004','withdrawn_during_review',335,'REN'),
                                               ('MDR-1005','duplicate_payment',750,'SGN')]:
                db.execute('INSERT OR IGNORE INTO applications(id,owner,status,fee_paid,permit_type) VALUES (?,?,?,?,?)',
                           (app_id, 'demo-user', status, fee, kind))
            db.execute("UPDATE applications SET duplicate_paid=750 WHERE id='MDR-1005' AND duplicate_paid=0")
            for owner, identity in DEMO_IDENTITIES.items():
                if not db.execute('SELECT 1 FROM identities WHERE owner=?', (owner,)).fetchone():
                    salt = secrets.token_hex(16)
                    db.execute('INSERT INTO identities VALUES (?,?,?,?)',
                               (owner, salt, self._digest(identity['last4'], salt), self._digest(identity['mobile'], salt)))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db: yield db
        finally: db.close()

    @staticmethod
    def _digest(value, salt):
        return hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), 100_000).hex()

    @staticmethod
    def _session_key(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def create_session(self, public=False) -> str:
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('INSERT INTO sessions(id,expires,public) VALUES (?,?,?)', (self._session_key(token), time.time() + 8 * 3600, int(public)))
        return token

    def session(self, token: str, require_verified=False) -> dict:
        with self.connect() as db:
            row = db.execute('SELECT owner,failed,verified_until,expires,public FROM sessions WHERE id=?', (self._session_key(token),)).fetchone()
        if not row or row[3] <= time.time(): raise ValueError('Session expired or unavailable')
        owner = row[0] if row[2] > time.time() and row[1] < 3 else None
        if require_verified and not owner: raise ValueError('Verify the applicant in the verification form first')
        return {'owner': owner, 'verified': bool(owner), 'locked': row[1] >= 3, 'failed_attempts': row[1], 'reverification_required': bool(row[0] and not owner), 'public': bool(row[4])}

    def verify(self, token: str, application_id: str, last4: str, mobile: str) -> dict:
        self.session(token)
        key = self._session_key(token)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT owner,failed FROM sessions WHERE id=?', (key,)).fetchone()
            if current[1] >= 3: raise ValueError('Verification locked after three failed attempts')
            row = db.execute('SELECT i.owner,i.salt,i.identity_hash,i.mobile_hash FROM identities i JOIN applications a ON a.owner=i.owner WHERE a.id=?', (application_id,)).fetchone()
            try:
                last4 = str(last4).translate(DIGITS)
                mobile = normalise_mobile(mobile)
                valid = len(last4) == 4 and last4.isdigit() and row is not None
                valid = valid and hmac.compare_digest(self._digest(last4, row[1]), row[2]) and hmac.compare_digest(self._digest(mobile, row[1]), row[3])
                valid = valid and current[0] in (None, row[0])
            except ValueError: valid = False
            if valid:
                db.execute('UPDATE sessions SET owner=?,failed=0,verified_until=? WHERE id=?', (row[0], time.time() + 1800, key))
                db.execute('INSERT INTO audit(event,detail) VALUES (?,?)', ('verified', '{}'))
            else:
                db.execute('UPDATE sessions SET failed=failed+1,verified_until=0 WHERE id=?', (key,))
                db.execute('INSERT INTO audit(event,detail) VALUES (?,?)', ('verification_failed', '{}'))
        if not valid: raise ValueError('Invalid verification details')
        return {'verified': True}

    def history(self, token: str) -> list:
        if self.session(token)['reverification_required']:
            return []
        with self.connect() as db:
            rows = db.execute('SELECT role,content FROM messages WHERE session=? ORDER BY id', (self._session_key(token),)).fetchall()
        return [{'role': role, 'content': content} for role, content in rows]

    def remember(self, token: str, question: str, answer: str):
        self.session(token)
        key = self._session_key(token)
        with self.connect() as db:
            db.executemany('INSERT INTO messages(session,role,content) VALUES (?,?,?)',
                           [(key,'user',redact_text(question)[:4000]), (key,'assistant',redact_text(answer)[:4000])])
            rows = db.execute('SELECT id,content FROM messages WHERE session=? ORDER BY id', (key,)).fetchall()
            while len(rows) > 12 or sum(len(r[1]) for r in rows) > 8000:
                remove, rows = rows[:2], rows[2:]
                db.executemany('DELETE FROM messages WHERE id=?', [(r[0],) for r in remove])

    def clear_history(self, token: str):
        self.session(token)
        with self.connect() as db:
            db.execute('DELETE FROM messages WHERE session=?', (self._session_key(token),))

    def counts(self, owner: str) -> dict:
        with self.connect() as db:
            pending = db.execute("SELECT count(*) FROM proposals WHERE owner=? AND status='pending'", (owner,)).fetchone()[0]
            inspections = db.execute('SELECT count(*) FROM inspections i JOIN applications a ON i.application=a.id WHERE a.owner=?', (owner,)).fetchone()[0]
            refunds = db.execute('SELECT count(*) FROM refunds r JOIN applications a ON r.application=a.id WHERE a.owner=?', (owner,)).fetchone()[0]
            escalations = db.execute('SELECT count(*) FROM escalations e JOIN applications a ON e.application=a.id WHERE a.owner=?', (owner,)).fetchone()[0]
        return dict(pending=pending, inspections=inspections, refunds=refunds, escalations=escalations)

    def application(self, application_id: str, owner: str) -> dict:
        with self.connect() as db:
            row = db.execute('SELECT id,status,permit_type,fee_paid,submitted,duplicate_paid FROM applications WHERE id=? AND owner=?', (application_id, owner)).fetchone()
        if not row: raise ValueError('Application unavailable for this applicant')
        return dict(zip(('application_id','status','permit_type','fee_paid','submitted','duplicate_paid'), row)) | {'synthetic': True}

    def inspections(self, application_id: str, owner: str) -> dict:
        self.application(application_id, owner)
        with self.connect() as db:
            rows = db.execute('SELECT proposal,day,version FROM inspections WHERE application=? ORDER BY day', (application_id,)).fetchall()
        return {'inspections': [dict(zip(('inspection_id','day','version'), row)) for row in rows]}

    def _propose(self, application_id, owner, kind, payload, token=None):
        self.application(application_id, owner)
        if token and self.session(token, True)['owner'] != owner: raise ValueError('Applicant mismatch')
        proposal = secrets.token_urlsafe(18)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._check_actor(db, token, owner)
            db.execute('INSERT INTO proposals(id,owner,application,day,status,kind,payload,session) VALUES (?,?,?,?,?,?,?,?)',
                       (proposal, owner, application_id, payload.get('day',''), 'pending', kind, json.dumps(payload), self._session_key(token) if token else None))
            db.execute('INSERT INTO audit(event,detail) VALUES (?,?)', ('proposed', json.dumps({'id':proposal,'kind':kind})))
        return {'proposal_id':proposal,'application_id':application_id,'kind':kind,'status':'pending','requires_approval':True,**payload}

    def _check_actor(self, db, token, owner):
        if token:
            now = time.time()
            if not db.execute('SELECT 1 FROM sessions WHERE id=? AND owner=? AND failed<3 AND verified_until>? AND expires>?',
                              (self._session_key(token), owner, now, now)).fetchone():
                raise ValueError('Verification expired; verify again')

    def propose(self, application_id: str, day: str, owner: str, token=None) -> dict:
        return self._propose(application_id, owner, 'inspection', {'day':validate_date(day)}, token)

    def reschedule(self, inspection_id: str, day: str, owner: str, token=None) -> dict:
        day = validate_date(day)
        with self.connect() as db:
            row = db.execute('SELECT i.application,i.day,i.version FROM inspections i JOIN applications a ON i.application=a.id WHERE i.proposal=? AND a.owner=?', (inspection_id,owner)).fetchone()
        if not row: raise ValueError('Inspection unavailable')
        if row[1] == day: raise ValueError('Choose a different date')
        return self._propose(row[0],owner,'reschedule',{'inspection_id':inspection_id,'day':day,'old_day':row[1],'version':row[2]},token)

    def _refund_amount(self, app):
        fee = app['fee_paid']
        status = app['status']
        if status == 'duplicate_payment':
            if app['duplicate_paid'] <= 0: raise ValueError('No duplicate payment recorded')
            return app['duplicate_paid']
        if status == 'rejected': return max(0, fee-100)
        if status == 'withdrawn_before_review': return fee
        if status == 'withdrawn_during_review': return round(fee/2, 2)
        raise ValueError('This application is not eligible for a refund under POL-06')

    def refund(self, application_id: str, owner: str, token=None) -> dict:
        app = self.application(application_id, owner)
        amount = self._refund_amount(app)
        with self.connect() as db:
            if db.execute('SELECT 1 FROM refunds WHERE application=?',(application_id,)).fetchone(): raise ValueError('Refund already requested')
        return self._propose(application_id,owner,'refund',{'amount_sar':amount,'source':'POL-06','finance_required':amount>1000},token)

    def _overdue(self, app):
        if app['status'] != 'under_review': raise ValueError('Only active, unpaused applications may be escalated')

        from datetime import datetime
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo('Asia/Riyadh')).date()
        start = date.fromisoformat(app['submitted'])
        elapsed = sum((start+timedelta(days=n)).weekday() not in (4,5) for n in range(1,max(0,(today-start).days)+1))
        overdue = elapsed-SLA[app['permit_type']]
        if overdue <= 0: raise ValueError('The application is still within its service period')
        return overdue

    def escalate(self, application_id: str, owner: str, token=None) -> dict:
        app = self.application(application_id,owner)
        overdue = self._overdue(app)
        with self.connect() as db:
            if db.execute('SELECT 1 FROM escalations WHERE application=?',(application_id,)).fetchone(): raise ValueError('Escalation already requested')
        return self._propose(application_id,owner,'escalation',{'overdue_working_days':overdue,'source':'POL-03'},token)

    def pending(self, owner: str, token=None) -> list:
        with self.connect() as db:
            rows = db.execute("SELECT id,application,day,kind,payload FROM proposals WHERE owner=? AND status='pending' AND session IS ?", (owner,self._session_key(token) if token else None)).fetchall()
        return [dict(proposal_id=r[0],application_id=r[1],day=r[2],kind=r[3],details=json.loads(r[4])) for r in rows]

    def decide(self, proposal_id: str, approve: bool, owner: str, token=None) -> dict:
        if type(approve) is not bool: raise ValueError('Approval must be a boolean')
        if token and self.session(token,True)['owner'] != owner: raise ValueError('Applicant mismatch')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._check_actor(db, token, owner)
            row = db.execute("SELECT application,day,kind,payload,session FROM proposals WHERE id=? AND owner=? AND status='pending'", (proposal_id,owner)).fetchone()
            if not row or row[4] != (self._session_key(token) if token else None): raise ValueError('Pending action unavailable')
            application_id, day, kind, payload, _ = row
            payload = json.loads(payload)
            app = self.application(application_id,owner)
            outcome = {'proposal_id':proposal_id,'kind':kind,'status':'approved' if approve else 'rejected','booked':False}
            if approve:
                if kind == 'inspection':
                    validate_date(day)
                    db.execute('INSERT INTO inspections(proposal,application,day) VALUES (?,?,?)',(proposal_id,application_id,day))
                    outcome.update(booked=True,inspection_id=proposal_id,day=day)
                elif kind == 'reschedule':
                    validate_date(day)
                    changed = db.execute('UPDATE inspections SET day=?,version=version+1 WHERE proposal=? AND application=? AND day=? AND version=?',
                                         (day,payload['inspection_id'],application_id,payload['old_day'],payload['version'])).rowcount
                    if changed != 1: raise ValueError('Inspection changed; create a new proposal')
                    outcome.update(rescheduled=True,inspection_id=payload['inspection_id'],day=day)
                elif kind == 'refund':
                    amount = self._refund_amount(app)
                    if amount != payload['amount_sar']: raise ValueError('Refund eligibility changed')
                    status = 'pending_finance' if amount > 1000 else 'approved_request'
                    try: db.execute('INSERT INTO refunds VALUES (?,?,?,?,?)',(proposal_id,application_id,amount,status,proposal_id))
                    except sqlite3.IntegrityError: raise ValueError('Refund already requested') from None
                    outcome.update(amount_sar=amount,refund_status=status,paid=False)
                elif kind == 'escalation':
                    overdue = self._overdue(app)
                    try: db.execute('INSERT INTO escalations VALUES (?,?,?,?,?)',(proposal_id,application_id,overdue,'awaiting_supervisor',proposal_id))
                    except sqlite3.IntegrityError: raise ValueError('Escalation already requested') from None
                    outcome.update(escalated=True,overdue_working_days=overdue)
                else: raise ValueError('Unknown action')
            db.execute('UPDATE proposals SET status=? WHERE id=?',(outcome['status'],proposal_id))
            db.execute('INSERT INTO audit(event,detail) VALUES (?,?)',(outcome['status'],json.dumps(redact({'id':proposal_id,'kind':kind}))))
        return outcome
