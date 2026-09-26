# Walkthrough recording plan — approximately 6–7 minutes

Record your own screen and narration with Loom, OBS or another recorder, upload to an accessible video host, and check the sharing link in a signed-out window. This outline is not a recording. Use a fresh seeded database; demo.py expects the seed state. Rehearse so you can explain each decision yourself.

## 0:00–0:45 — Scope and setup

Show README.md and the file tree. Explain: trial bookings only, four seats, no regular enrollment, mock payments, Python standard library plus SQLite, API-first demonstration with a script. Run:

```sh
python app.py seed
python app.py serve
```

If already seeded, stop the server and choose a fresh database using `--db recording.db` before the subcommand.

## 0:45–2:15 — Run the flow

In terminal 2 run `python demo.py`. Scroll through the output rather than letting viewers miss it:

- Parent A sees Alex and Finn.
- Science has four seats; Math has one because three are confirmed.
- Duplicate Casey/Math returns the original confirmed booking.
- A and B each get pending bookings.
- B completes first: confirmed, captured, seat 4.
- A completes next: sold_out, voided, no seat.
- Teacher roster contains exactly four children, including B but not A.
- Failed Science payment leaves its roster empty.

Explain that selecting a class does not reserve a seat. Status is persisted and can be read after submission, not merely printed from client state.

## 2:15–3:30 — Schema and transaction

Open schema.sql. Show the unique child/class pair, valid seat range, required seat for confirmed status, and unique class/seat pair. Explain why a fifth confirmed booking cannot fit.

Open Store.pay in booking.py. Trace BEGIN IMMEDIATE (in connection), ownership check, idempotency lookup, status validation, seat lookup, booking update, payment insertion, commit. Emphasize that no real provider is called and no application mutex is used.

## 3:30–4:45 — Tests

Run `python -m unittest discover -s tests -v`. Show 13 passing tests. Open the ordered B-wins test, then the thread-barrier concurrency test. Explain separate database connections and twelve repetitions. Show the injected failure test proving both writes roll back together. Passing tests support the guarantee; the constraints and transaction establish it.

## 4:45–5:45 — Tradeoffs

Explain that first transaction to allocate wins, not first person to click. Losing payment authorization is only mocked as voided. Real payments need a provider state machine, idempotency, outbox and reconciliation. SQLite serializes all writes; suitable for this small single-host demo. No retries after terminal failure or cancellations in this slice. Tokens are public local-demo fixtures, not real security.

## 5:45–6:45 — AI, monitoring and next steps

Show AI_USAGE.md. Accurately describe AI's role and your own review; add your actual correction and time spent before submission. Mention lock timeouts, sold-out-at-payment rate and payment/roster mismatches as monitoring priorities. Next steps are real auth, UI, payment integration and failure retry semantics. End on the four-student roster and link the public repository in the video's description.

## Publishing checklist

- Review and understand every file, especially booking.py and schema.sql.
- Add actual human time and a genuine review decision; do not invent them.
- Push source (not trials.db or an archive) to a public GitHub repository.
- Verify tests/CI and access to the repo while signed out.
- Record 5–8 minutes, upload, and verify viewing permissions.
- Submit both real URLs. No ZIP submission.
