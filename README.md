# Ottodot trial booking

A dependency-free Python + SQLite JSON API for **trial booking only**. Parents choose a child and class, submit a booking, record a mock payment, and retrieve status. Teachers retrieve the confirmed roster. No regular enrollment and no real money.

## Run in two minutes

Requires Python 3.11+ with SQLite 3.35+ (tested on Python 3.12.14). No pip packages, Docker, Node, or database server required. Commands work on Windows, macOS, and Linux; use `python3` if your machine calls Python that.

From this repository's root:

```sh
python app.py seed
python -m unittest discover -s tests -v
python app.py serve
```

Leave the server running. In a second terminal in the same folder:

```sh
python demo.py
python app.py roster 2
```

`demo.py` exercises the real HTTP API and asserts the duplicate, last-seat and payment-failure results. The API binds only to `127.0.0.1:8000`. Stop with Ctrl+C. Seeding refuses to overwrite any existing database. To repeat from scratch, stop the server and use a new filename:

```sh
python app.py --db fresh.db seed
python app.py --db fresh.db serve
```

`demo.py` assumes port 8000 and the original seed state; run once per fresh database. Tests always create and clean up their own temporary databases.

## Synthetic data

| Data | IDs and purpose |
| --- | --- |
| Parent A | Parent 1; children Alex (1) and Finn (6) |
| Parent B | Parent 2; child Blair (2) |
| Seed Parent | Parent 3; children Casey (3), Dev (4), Em (5) |
| Science: Light Lab | Class 1; zero confirmed, four available seats |
| Math: Number Puzzles | Class 2; exactly three confirmed, one available seat |
| Failed payment | Finn/class 1 has `payment_failed`; absent from roster |
| Duplicate example | Submit Casey/class 2 again; returns the existing confirmed booking |

Classes start seven days after setup, in UTC. Availability is derived from confirmed bookings, never a cached counter.

## Backend design

`app.py` handles HTTP validation and demo identity; `booking.py` contains the transactional domain service; `schema.sql` contains constraints; `seed.py` creates synthetic data. The CLI roster is a trusted local operator interface.

| Table | Key fields and rules |
| --- | --- |
| parents | id, name |
| students | id, parent_id foreign key, name |
| trial_classes | id, title, starts_at (canonical UTC), capacity fixed at 4 |
| bookings | id, student_id, class_id, status, seat, created_at |
| payment_attempts | id, booking_id, idempotency_key, requested_result, outcome, created_at |

`UNIQUE(student_id, class_id)` permits one booking record per child/class across all statuses. Duplicate submission returns that same record, including when already confirmed. This intentionally does not offer another attempt after a terminal failure.

Confirmed bookings **must** have a seat numbered 1–4. Other statuses **must** have a NULL seat. `UNIQUE(class_id, seat)` ensures there can be at most four confirmed bookings per class, even if application validation is bypassed. Foreign keys are enabled on every connection. Seat numbers are internal capacity tokens, not physical classroom seats.

### API

Demo credentials are public fixtures, **not production authentication**: `Authorization: Bearer demo-parent-1` (or 2/3), and `Bearer demo-teacher`. A parent cannot read or pay for another parent's booking through the API. Never expose this server publicly with these tokens. Roster responses omit parent contact details.

| Method/path | Input / identity | Output |
| --- | --- | --- |
| GET /health | None | Demo health |
| GET /classes | None | Future classes and current available seats; includes full classes with 0 |
| GET /children | Parent token | That parent's children |
| POST /bookings | Parent token; student_id, class_id | Existing or new booking |
| GET /bookings/{id} | Owning parent token | Status and payment outcome |
| POST /bookings/{id}/mock-payment | Owning parent token; idempotency_key, result: success/failure | Final booking and mock payment outcome |
| GET /classes/{id}/roster | Teacher token | Confirmed students only |

Example JSON booking body: `{"student_id":1,"class_id":2}`.
Example payment body: `{"idempotency_key":"attempt-A","result":"success"}`.
IDs are positive integers. Payment keys must be nonblank and at most 128 characters. The client must keep the same key when retrying after a timeout.

Successful operations, including duplicate submission and recorded payment failure, return HTTP 200 with the business status. Invalid input returns 400, missing identity 401, unauthorized roster access 403, absent/unowned resources 404, terminal-state/key conflicts/full or started class at submission 409, and database lock timeout 503. A lost response can safely be retried with the same request. Same key with a different booking or result is rejected. New keys cannot charge an already-finalized booking.

### States and payment semantics

| From | Event | To | Payment outcome | On roster? |
| --- | --- | --- | --- | --- |
| pending_payment | Mock success and available future class | confirmed | captured | Yes |
| pending_payment | Mock failure | payment_failed | failed | No |
| pending_payment | Mock success but no seat, or class started | sold_out | voided | No |

All three final statuses are terminal in this slice. There is one payment attempt per booking. `sold_out` means the class is no longer bookable, including after its start time. A mock success represents authorization; capture is recorded only when a seat can be allocated. The losing authorization is recorded as voided. No external provider is contacted, no payment is actually captured or refunded. Payment outcome and booking transition commit or roll back together.

### Last-seat race: explicit walkthrough

1. There are three confirmed students. A submits a pending booking; it holds no seat.
2. B also submits a pending booking; it holds no seat.
3. B completes mock payment. `BEGIN IMMEDIATE` obtains SQLite's writer lock **before** reading occupancy. It allocates seat 4, confirms B, records captured, and commits.
4. A completes mock payment. After obtaining the same database writer lock, A reads the committed occupancy. No seat exists: A becomes sold_out and its mock authorization is voided.

If both arrive simultaneously, the database serializes the writers. Whichever acquires the transaction first wins; network arrival or the time the parent selected a class does not establish priority. At most one can win. Separate service instances use the same file and rely on SQLite, not an in-process mutex. The seat constraints provide a second line of defense.

Why this choice: short atomic transactions make the core invariant easy to reason about and test without a reservation scheduler. [SQLite documents one writer at a time and BEGIN IMMEDIATE](https://www.sqlite.org/lang_transaction.html). No check-then-write happens outside the transaction.

Tradeoffs: a parent can reach payment and discover the seat is gone; there is no selection-time guarantee. SQLite serializes unrelated class writes too; use one host and a local database file, not independent database copies or a shared network filesystem. A lock waits up to five seconds, then the API asks the caller to retry. Pending rows can accumulate but do not consume capacity. Real payment capture is not atomic with a local database transaction: production needs authorization/capture orchestration, durable provider-event deduplication, an outbox, and reconciliation/void/refund handling. Do not replace the mock with a network call while holding this transaction.

### Where checks belong

| Layer | Responsibility |
| --- | --- |
| UI/client | Show available seats and final status, label payment as mock, disable duplicate clicks for convenience, retain retry key. Displayed availability is advisory. This slice uses a CLI HTTP client. |
| Backend | Validate input and ownership, reject past/full classes, enforce state transitions, transactionally allocate a seat, deduplicate payment requests. |
| Database | Foreign keys; one child/class booking; four unique seat tokens; status/seat consistency; unique payment key and one attempt per booking. |
| Background jobs | None required for mock correctness. Production: payment reconciliation, outbox retries and retention/cleanup of abandoned pending records. Never infer confirmation from a client redirect. |

## Verification

`python -m unittest discover -s tests -v` currently runs **13 tests**, including:

- Required ordered race: A selects, B selects, B wins, A is voided.
- Twelve repeated simultaneous last-seat races against separate connections and fresh on-disk databases, with a thread barrier (no timing sleeps).
- Concurrent duplicate submissions and concurrent replays of one payment key.
- Duplicate confirmed booking, failed payment, changed payment payload and terminal-state guards.
- Parent ownership, teacher access, malformed input and full/started classes.
- Direct SQL attempts to bypass capacity, seat consistency and uniqueness.
- Injected payment insert failure to prove seat allocation rolls back.
- An actual HTTP parent-booking-payment-status-teacher-roster flow.

GitHub Actions runs the same suite on Python 3.12. Automated verification was run locally; CI status is not claimed before publishing. `demo.py` also passed against the HTTP server. Concurrency tests are evidence, not a substitute for the database invariant.

## Scope, assumptions, and time

This is a backend-led take-home slice, not a hosted product. Fixed four-student capacity, UTC start times, synthetic identities, one booking/attempt per child/class, and a trusted local teacher/operator are deliberate assumptions. The assignment allowed a mock payment and API/script instead of a frontend.

Cut: regular enrollment, frontend polish, real payment integration, retrying failed payments, cancellations, seat-hold expiry, rescheduling, email, login UI and production deployment. The stricter no-retry rule is a scope tradeoff, not an accidental inability to handle a duplicate.

Time spent: generated and verified during one AI-assisted working session on 25 September 2026. No human implementation time was provided or independently tracked; the submitter should add their actual review and recording time rather than claim an invented total.

After release I would monitor confirmation failures, sold-out-at-payment rate, payment/booking mismatches, duplicate-key conflicts, transaction latency and lock timeouts, and roster count/seat invariants. Avoid logging children's names or tokens in operational metrics.

With more time: authenticated parent/teacher sessions, a minimal accessible UI, retryable payment attempts, a real provider with signed webhooks and reconciliation, cancellation rules, and PostgreSQL per-class locking when throughput warrants it. Validate product expectations around selection-time holds before implementing them.

## Submission

The source includes AI_USAGE.md and WALKTHROUGH.md (a 5–8 minute recording outline). Submit a **public GitHub repository URL and your recorded video URL**. Neither an archive nor a script is a substitute for the requested video. Public publishing and a human walkthrough remain separate submission steps until their real URLs exist.
