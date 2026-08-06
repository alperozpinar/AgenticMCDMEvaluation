# Deviation log

Every change to anything under `protocol/`, `prompts/` or `schemas/` after the first
archived release is recorded here with its date and reason. A change made after any model
output is visible is recorded as a deviation, never as a correction.

Format: date, what changed, why, and whether any collected data is affected.

## 2026-08-05, initial state

Protocol, criteria, matrices, linguistic scale, schemas and computation layer fixed. No
model has been called. Nothing to declare.

Matrix screening run with this repository's code at 200,000 Dirichlet draws, seed 20260805.
All four acceptance rules passed and the result is archived in
`results/screening_20260805.json`. The matrix is fixed from this point.

## 2026-08-06, response contract narrowed and output format made explicit

Two changes to `prompts/decision_user.txt`, `schemas/decision_response.schema.json` and
`src/agenticmcdm/schema_check.py`, both made before any scheduled call. No ledger row exists
and no collected data is affected. The model outputs seen so far come from
`agenticmcdm.smoke`, which writes nothing to `results/` and whose responses are discarded.

First, `persona_id` and `repetition` were removed from the response contract. The respondent
now returns three keys: `schema_version`, `criterion_comparisons` and
`declared_priority_order`. Both removed fields are attached by the harness from the scheduled
slot. Requesting `repetition` from the model would have placed the collection-round index in
the prompt, which makes the request differ between the repetitions of one cell and breaks the
byte-identity requirement in PROTOCOL.md. A model that volunteers either field now fails with
`E_EXTRA_FIELD`, because volunteering a slot label it was never given is itself a contract
break.

Second, the prompt now carries an explicit OUTPUT CONTRACT block showing the exact key names
and one comparison object. The earlier wording asked for JSON "matching the supplied schema"
without supplying it; every service tested invented its own field names. The block uses
angle-bracket placeholders that describe where a judgment goes and carry no example values
for `preferred`, `intensity` or `reason`, so the format is pinned without anchoring the
answer.

## Open before the first call

- The five providers and their exact API model identifiers are not yet resolved, so
  `models/model_registry.csv` carries headers only.
- Domain review of the criterion definitions, units and values is outstanding.
- The archived release and its versioned DOI have not been created.
