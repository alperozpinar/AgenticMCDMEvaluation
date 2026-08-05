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

## Open before the first call

- The five providers and their exact API model identifiers are not yet resolved, so
  `models/model_registry.csv` carries headers only.
- Domain review of the criterion definitions, units and values is outstanding.
- The archived release and its versioned DOI have not been created.
