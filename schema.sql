PRAGMA foreign_keys = ON;
CREATE TABLE parents (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE students (
    id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL REFERENCES parents(id), name TEXT NOT NULL
);
CREATE TABLE trial_classes (
    id INTEGER PRIMARY KEY, title TEXT NOT NULL, starts_at TEXT NOT NULL,
    capacity INTEGER NOT NULL DEFAULT 4 CHECK(capacity = 4)
);
CREATE TABLE bookings (
    id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id),
    class_id INTEGER NOT NULL REFERENCES trial_classes(id),
    status TEXT NOT NULL DEFAULT 'pending_payment'
        CHECK(status IN ('pending_payment','confirmed','payment_failed','sold_out')),
    seat INTEGER CHECK(seat BETWEEN 1 AND 4),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    CHECK((status = 'confirmed' AND seat IS NOT NULL) OR (status != 'confirmed' AND seat IS NULL)),
    UNIQUE(student_id, class_id),
    UNIQUE(class_id, seat)
);
CREATE TABLE payment_attempts (
    id INTEGER PRIMARY KEY, booking_id INTEGER NOT NULL UNIQUE REFERENCES bookings(id),
    idempotency_key TEXT NOT NULL UNIQUE,
    requested_result TEXT NOT NULL CHECK(requested_result IN ('success','failure')),
    outcome TEXT NOT NULL CHECK(outcome IN ('captured','failed','voided')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
