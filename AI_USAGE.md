# AI usage

## Tools and provenance

OpenAI Codex in ChatGPT Work generated this implementation, seed data, tests, README and walkthrough outline from the assignment. It used a local Python runtime for tests and an HTTP demo, Git for the local repository, and web search to check the official SQLite transaction documentation. No other AI tool is claimed. The human submitter's independent review has not been observed in this session.

## What AI accelerated

AI produced a runnable dependency-free vertical slice and the concurrent last-seat test together. Repeating two simultaneous payments against independent SQLite connections made the core race behavior quick to verify, while database constraints enforce the actual guarantee.

## Corrections to AI output

During the AI-assisted session, the initial test command was run from the parent folder and failed discovery. It was corrected to run from the repository root. A redundant inherited test class in the generated test file was removed rather than counting duplicate test execution as additional coverage. The first separate-process demo attempt lost its server between execution calls; the verification harness was corrected to run server and client within the same process lifetime. The full HTTP demo then passed.

These are corrections made during the AI session, not a fabricated account of the human submitter rejecting AI advice. Before submission, add a genuine example of a design or code decision you personally challenged, if the evaluator expects your own disagreement with AI.

## Verification performed

- 13 unittest tests passed on Python 3.12.14, including 12 simultaneous race iterations.
- The exact specified B-before-A payment sequence was asserted.
- Direct SQL constraint-bypass attempts were rejected.
- An injected payment-write error rolled back confirmation.
- The live HTTP demo passed its duplicate, race, failure and roster assertions.
- Mock payment, demo authentication, terminal failure and SQLite scaling limitations are documented explicitly.

## What to change next time

Start by writing the state transition table and acceptance tests with the human author, then ask AI for the smallest implementation that satisfies them. Require the author to explain the transaction and real-payment limitations in their own words before recording. Keep an actual time log and record human review decisions as they happen. Do not treat generated documentation or passing tests as independent review.
