"""Synthetic data with dates relative to setup, so the demo does not expire."""
from datetime import datetime, timedelta, timezone
from booking import Store


def seed(path):
    store = Store(path)
    store.initialize()
    start = (datetime.now(timezone.utc) + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    with store.connection(write=True) as db:
        db.executemany('INSERT INTO parents VALUES (?,?)', [(1, 'Parent A'), (2, 'Parent B'), (3, 'Seed Parent')])
        db.executemany('INSERT INTO students VALUES (?,?,?)',
                       [(1, 1, 'Alex'), (2, 2, 'Blair'), (3, 3, 'Casey'), (4, 3, 'Dev'),
                        (5, 3, 'Em'), (6, 1, 'Finn')])
        db.executemany('INSERT INTO trial_classes(id,title,starts_at) VALUES (?,?,?)',
                       [(1, 'Science: Light Lab', start), (2, 'Math: Number Puzzles', start)])
    for child in (3, 4, 5):
        b = store.book(3, child, 2)
        store.pay(3, b['id'], f'seed-{child}', 'success')
    failed = store.book(1, 6, 1)
    store.pay(1, failed['id'], 'seed-failure', 'failure')
    return store
