"""Run against `python app.py serve`. Seed a fresh database first."""
import json
from urllib.request import Request, urlopen


def call(path, parent=1, data=None, teacher=False):
    token = 'demo-teacher' if teacher else f'demo-parent-{parent}'
    req = Request('http://127.0.0.1:8000' + path,
                  data=json.dumps(data).encode() if data is not None else None,
                  headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urlopen(req, timeout=10) as response:
        value = json.load(response)
    print(path, json.dumps(value, indent=2))
    return value


def main():
    call('/children')
    call('/classes')
    print('\nDUPLICATE: returns existing confirmed booking, no extra seat')
    duplicate = call('/bookings', parent=3, data={'student_id': 3, 'class_id': 2})
    assert duplicate['status'] == 'confirmed'
    print('\nLAST SEAT: A selects, B selects, B completes first')
    a = call('/bookings', data={'student_id': 1, 'class_id': 2})
    b = call('/bookings', parent=2, data={'student_id': 2, 'class_id': 2})
    b_paid = call(f"/bookings/{b['id']}/mock-payment", parent=2,
                 data={'idempotency_key': 'demo-B', 'result': 'success'})
    a_paid = call(f"/bookings/{a['id']}/mock-payment",
                 data={'idempotency_key': 'demo-A', 'result': 'success'})
    assert b_paid['status'] == 'confirmed'
    assert (a_paid['status'], a_paid['payment_outcome']) == ('sold_out', 'voided')
    call(f"/bookings/{a['id']}")
    roster = call('/classes/2/roster', teacher=True)
    assert len(roster) == 4
    print('\nPAYMENT FAILURE: class 1 remains empty')
    failure = call('/bookings', data={'student_id': 1, 'class_id': 1})
    call(f"/bookings/{failure['id']}/mock-payment",
         data={'idempotency_key': 'demo-failed', 'result': 'failure'})
    assert call('/classes/1/roster', teacher=True) == []
    print('\nAll HTTP demo assertions passed.')


if __name__ == '__main__':
    main()
