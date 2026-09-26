"""Trial-only domain service. Every request uses a separate SQLite connection."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


class Problem(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Store:
    def __init__(self, path):
        self.path = str(path)

    @contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        try:
            if write:
                # Acquire the writer lock BEFORE reading available seats.
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except BaseException:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    def initialize(self):
        # Exclusive creation avoids silently replacing an existing demo database.
        with open(self.path, 'xb'):
            pass
        with self.connection() as db:
            db.executescript(Path(__file__).with_name('schema.sql').read_text())

    @staticmethod
    def _owned(db, parent_id, booking_id):
        row = db.execute('''SELECT b.* FROM bookings b JOIN students s ON s.id=b.student_id
                            WHERE b.id=? AND s.parent_id=?''', (booking_id, parent_id)).fetchone()
        if row is None:
            raise Problem(404, 'Booking not found for this parent')
        return dict(row)

    @staticmethod
    def _view(db, booking):
        row = db.execute('SELECT outcome FROM payment_attempts WHERE booking_id=?',
                         (booking['id'],)).fetchone()
        return {**booking, 'payment_outcome': row['outcome'] if row else None}

    def children(self, parent_id):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM students WHERE parent_id=?', (parent_id,))]

    def classes(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute('''SELECT c.*, 4-count(b.id) AS available_seats
                FROM trial_classes c LEFT JOIN bookings b ON b.class_id=c.id AND b.status='confirmed'
                WHERE c.starts_at > ? GROUP BY c.id ORDER BY c.starts_at''', (self.now(),))]

    @staticmethod
    def now():
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    def book(self, parent_id, student_id, class_id):
        with self.connection(write=True) as db:
            if not db.execute('SELECT 1 FROM students WHERE id=? AND parent_id=?',
                              (student_id, parent_id)).fetchone():
                raise Problem(404, 'Child not found for this parent')
            existing = db.execute('SELECT * FROM bookings WHERE student_id=? AND class_id=?',
                                  (student_id, class_id)).fetchone()
            if existing:
                return self._view(db, dict(existing))  # Natural-key idempotency.
            trial = db.execute('SELECT * FROM trial_classes WHERE id=?', (class_id,)).fetchone()
            if trial is None:
                raise Problem(404, 'Class not found')
            if trial['starts_at'] <= self.now():
                raise Problem(409, 'Class has already started')
            if db.execute("SELECT count(*) FROM bookings WHERE class_id=? AND status='confirmed'",
                          (class_id,)).fetchone()[0] >= 4:
                raise Problem(409, 'Class is full')
            row = db.execute('INSERT INTO bookings(student_id,class_id) VALUES (?,?) RETURNING *',
                             (student_id, class_id)).fetchone()
            return self._view(db, dict(row))

    def get(self, parent_id, booking_id):
        with self.connection() as db:
            return self._view(db, self._owned(db, parent_id, booking_id))

    def pay(self, parent_id, booking_id, key, result):
        if not isinstance(key, str) or not 1 <= len(key.strip()) <= 128:
            raise Problem(400, 'idempotency_key must contain 1–128 nonblank characters')
        if result not in ('success', 'failure'):
            raise Problem(400, 'result must be success or failure')
        with self.connection(write=True) as db:
            booking = self._owned(db, parent_id, booking_id)
            prior = db.execute('SELECT * FROM payment_attempts WHERE idempotency_key=?', (key,)).fetchone()
            if prior:
                if prior['booking_id'] != booking_id or prior['requested_result'] != result:
                    raise Problem(409, 'Idempotency key was used for a different request')
                return self._view(db, booking)
            if booking['status'] != 'pending_payment':
                raise Problem(409, 'Booking is terminal; repeat the original payment key to retrieve its result')
            seat = None
            if result == 'failure':
                status, outcome = 'payment_failed', 'failed'
            else:
                trial = db.execute('SELECT starts_at FROM trial_classes WHERE id=?',
                                   (booking['class_id'],)).fetchone()
                occupied = {r[0] for r in db.execute('SELECT seat FROM bookings WHERE class_id=? AND seat IS NOT NULL',
                                                   (booking['class_id'],))}
                free = sorted(set(range(1, 5)) - occupied)
                if free and trial['starts_at'] > self.now():
                    seat, status, outcome = free[0], 'confirmed', 'captured'
                else:
                    status, outcome = 'sold_out', 'voided'
            # Mock authorization/capture only; no network calls inside this transaction.
            db.execute('UPDATE bookings SET status=?,seat=? WHERE id=?', (status, seat, booking_id))
            db.execute('''INSERT INTO payment_attempts(booking_id,idempotency_key,requested_result,outcome)
                          VALUES (?,?,?,?)''', (booking_id, key, result, outcome))
            return self._view(db, self._owned(db, parent_id, booking_id))

    def roster(self, class_id):
        with self.connection() as db:
            if not db.execute('SELECT 1 FROM trial_classes WHERE id=?', (class_id,)).fetchone():
                raise Problem(404, 'Class not found')
            return [dict(r) for r in db.execute('''SELECT b.id AS booking_id,s.id AS student_id,s.name,b.seat
                FROM bookings b JOIN students s ON s.id=b.student_id
                WHERE b.class_id=? AND b.status='confirmed' ORDER BY b.seat''', (class_id,))]
