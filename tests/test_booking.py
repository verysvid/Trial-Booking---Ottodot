import json
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from booking import Store, Problem
from seed import seed
from app import make_handler


class BookingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = seed(Path(self.temp.name) / 'test.db')

    def pending(self, parent=1, child=1, cls=2):
        return self.store.book(parent, child, cls)['id']

    def test_seed_and_failed_payment_roster(self):
        self.assertEqual([4, 1], [c['available_seats'] for c in self.store.classes()])
        self.assertEqual([], self.store.roster(1))
        self.assertEqual('payment_failed', self.store.book(1, 6, 1)['status'])

    def test_exact_required_sequence_b_wins(self):
        a, b = self.pending(), self.pending(2, 2)
        self.assertEqual(3, len(self.store.roster(2)))
        self.assertEqual('confirmed', self.store.pay(2, b, 'B', 'success')['status'])
        result = self.store.pay(1, a, 'A', 'success')
        self.assertEqual(('sold_out', 'voided'), (result['status'], result['payment_outcome']))
        self.assertEqual([3, 4, 5, 2], [r['student_id'] for r in self.store.roster(2)])

    def test_concurrent_last_seat_separate_connections(self):
        # Repeat with independently seeded file databases, no shared Python lock.
        for run in range(12):
            store = seed(Path(self.temp.name) / f'race-{run}.db')
            a, b = store.book(1, 1, 2)['id'], store.book(2, 2, 2)['id']
            barrier = threading.Barrier(2)
            def pay(parent, bid):
                barrier.wait(timeout=5)
                return Store(store.path).pay(parent, bid, f'key-{parent}', 'success')['status']
            with ThreadPoolExecutor(2) as pool:
                futures = [pool.submit(pay, 1, a), pool.submit(pay, 2, b)]
                outcomes = [f.result(timeout=10) for f in futures]
            self.assertCountEqual(['confirmed', 'sold_out'], outcomes)
            self.assertEqual(4, len(store.roster(2)))
            with store.connection() as db:
                self.assertEqual(1, db.execute("SELECT count(*) FROM payment_attempts WHERE outcome='voided'").fetchone()[0])

    def test_duplicate_confirmed_returns_same_booking(self):
        first = self.store.book(3, 3, 2)
        second = self.store.book(3, 3, 2)
        self.assertEqual(first, second)
        self.assertEqual('confirmed', second['status'])
        self.assertEqual(3, len(self.store.roster(2)))

    def test_concurrent_duplicate_submission(self):
        barrier = threading.Barrier(2)
        def book():
            barrier.wait(timeout=5)
            return self.pending()
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: book(), range(2)))
        self.assertEqual(results[0], results[1])

    def test_concurrent_same_payment_is_idempotent(self):
        bid = self.pending()
        barrier = threading.Barrier(2)
        def pay():
            barrier.wait(timeout=5)
            return self.store.pay(1, bid, 'same', 'success')
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(pay), pool.submit(pay)]
            self.assertEqual(futures[0].result(), futures[1].result())
        with self.store.connection() as db:
            self.assertEqual(1, db.execute('SELECT count(*) FROM payment_attempts WHERE booking_id=?', (bid,)).fetchone()[0])

    def test_failure_and_terminal_guard(self):
        bid = self.pending()
        result = self.store.pay(1, bid, 'fail', 'failure')
        self.assertEqual('payment_failed', result['status'])
        self.assertEqual(3, len(self.store.roster(2)))
        self.assertEqual(result, self.store.pay(1, bid, 'fail', 'failure'))
        with self.assertRaises(Problem):
            self.store.pay(1, bid, 'different', 'success')

    def test_key_payload_mismatch_and_ownership(self):
        bid = self.pending()
        with self.assertRaises(Problem) as caught:
            self.store.pay(2, bid, 'key', 'success')
        self.assertEqual(404, caught.exception.status)
        self.store.pay(1, bid, 'key', 'success')
        with self.assertRaises(Problem):
            self.store.pay(1, bid, 'key', 'failure')
        other = self.pending(2, 2, 1)
        with self.assertRaises(Problem):
            self.store.pay(2, other, 'key', 'success')
        with self.assertRaises(Problem):
            self.store.book(2, 1, 1)
        with self.assertRaises(Problem):
            self.store.get(2, bid)

    def test_full_and_started_classes(self):
        a, b = self.pending(), self.pending(2, 2)
        self.store.pay(1, a, 'a', 'success')
        with self.assertRaises(Problem):
            self.store.book(1, 6, 2)
        with self.store.connection(write=True) as db:
            db.execute("UPDATE trial_classes SET starts_at='2000-01-01T00:00:00Z'")
        self.assertEqual([], self.store.classes())
        self.assertEqual('voided', self.store.pay(2, b, 'b', 'success')['payment_outcome'])
        with self.assertRaises(Problem):
            self.store.book(2, 2, 1)

    def test_database_constraints_reject_bypass(self):
        self.store.pay(1, self.pending(), 'last', 'success')
        for sql, params in [
            ("INSERT INTO bookings(student_id,class_id,status,seat) VALUES (2,2,'confirmed',?)", (5,)),
            ("INSERT INTO bookings(student_id,class_id,status,seat) VALUES (2,2,'confirmed',?)", (4,)),
            ("INSERT INTO bookings(student_id,class_id,status) VALUES (2,2,'confirmed')", ()),
            ("INSERT INTO bookings(student_id,class_id) VALUES (3,2)", ()),
            ("UPDATE trial_classes SET capacity=5 WHERE id=2", ()),
        ]:
            with self.assertRaises(sqlite3.IntegrityError), self.store.connection(write=True) as db:
                db.execute(sql, params)

    def test_payment_insert_failure_rolls_back_confirmation(self):
        bid = self.pending()
        with self.store.connection() as db:
            db.execute("""CREATE TRIGGER fail_payment BEFORE INSERT ON payment_attempts
                          BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.pay(1, bid, 'key', 'success')
        self.assertEqual('pending_payment', self.store.get(1, bid)['status'])
        self.assertEqual(3, len(self.store.roster(2)))


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = seed(Path(self.temp.name) / 'api.db')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        def stop():
            self.server.shutdown()
            self.server.server_close()
            thread.join(timeout=5)
        self.addCleanup(stop)

    def request(self, path, body=None, token='demo-parent-1', raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = Request(f'http://127.0.0.1:{self.server.server_port}{path}', data=data,
                      headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response)

    def test_parent_to_payment_to_teacher(self):
        status, children = self.request('/children')
        self.assertEqual(200, status)
        self.assertEqual([1, 6], [r['id'] for r in children])
        status, b = self.request('/bookings', {'student_id': 1, 'class_id': 1})
        self.assertEqual((200, 'pending_payment'), (status, b['status']))
        path = f"/bookings/{b['id']}/mock-payment"
        status, paid = self.request(path, {'idempotency_key': 'http', 'result': 'success'})
        self.assertEqual((200, 'confirmed'), (status, paid['status']))
        self.assertEqual(paid, self.request(f"/bookings/{b['id']}")[1])
        self.assertEqual(403, self.request('/classes/1/roster')[0])
        self.assertEqual(1, len(self.request('/classes/1/roster', token='demo-teacher')[1]))
        self.assertEqual(404, self.request(f"/bookings/{b['id']}", token='demo-parent-2')[0])

    def test_validation(self):
        for data in (b'{', b'[]', b'{"student_id":true,"class_id":1}', b'{}'):
            self.assertEqual(400, self.request('/bookings', raw=data)[0])
        self.assertEqual(401, self.request('/children', token='wrong')[0])
        b = self.request('/bookings', {'student_id': 1, 'class_id': 1})[1]
        for body in ({'result': 'success'}, {'result': 'other', 'idempotency_key': 'x'}):
            self.assertEqual(400, self.request(f"/bookings/{b['id']}/mock-payment", body)[0])


if __name__ == '__main__':
    unittest.main()
