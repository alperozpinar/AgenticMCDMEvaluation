# Release notes, v0.2.0

First archived release of the material that actually governs the collected data.

v0.1.0 tagged the initial protocol of 5 August 2026, commit `ba639f1`. Everything that
followed, the model registry, the frozen cards, the collection schedule, the discard of the
first pilot round and the operative prompt version, sat after that tag and outside it. This
release closes that gap.

## What this archive contains

- `protocol/`: PROTOCOL.md, the six criterion definitions with their units and meaningful
  zeros, the fixed performance matrix and its stress variant, the linguistic scale, the card
  admissibility checklist, the fifteen frozen persona cards with their hashes, and the
  deviation log.
- `prompts/` and `schemas/`: the generation and decision prompts and the response contracts,
  at prompt version `structured_v2_icaira`.
- `models/model_registry.csv`: the five hosted service configurations, their API model
  identifiers and access dates. No provider exposed a dated snapshot identifier.
- `src/` and `tests/`: the computation layer. Row-geometric-mean AHP weighting, the
  consistency ratio and the geometric consistency index, EDAS, TOPSIS, and the stochastic
  weight-space screening.
- `results/screening_20260805.json`: the screening report, 200,000 flat-Dirichlet draws under
  seed 20260805.
- `data/`: the run ledger, the archived raw responses, and the pre-study ledger for the
  discarded round.

## Collection status at this release

Collection has begun and no completion has been analysed. Fifteen cards are frozen, pilot
round 1 is complete with twenty-five valid completions, and rounds 2 and 3 are held pending a
domain review of the criteria and the matrix.

This deposit is not a preregistration. It fixes the state of every input from its date
onward. The ordering that matters is in the history: the operative prompt and schema were
fixed at commit `17a03dd` at 04:37:48 UTC on 8 August 2026, and the twenty-five retained
completions were collected from 04:39:07 UTC the same day.

## Changes since v0.1.0

Nine deviation entries, all in `protocol/DEVIATIONS.md`, covering the response contract, the
registry, the retry rule, the checklist wordings, the card freeze, the discard of pilot round
1, and a warning condition that was added and then withdrawn under peer review.

## Licensing

Code under `src/` and `tests/` is MIT. Material under `protocol/`, `prompts/`, `schemas/` and
`results/` is CC-BY-4.0.
