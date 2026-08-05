# AgenticMCDMEvaluation

Protocol, stimulus material and computation code for an experiment that separates the
sources of ranking divergence in a hybrid large-language-model and multi-criteria decision
pipeline.

A persona card describes a professional role. A hosted language model reads that card and a
fixed performance matrix, then returns fifteen pairwise criterion comparisons and three
declared priorities. Everything after that point is deterministic code in this repository:
weights by row geometric mean, consistency by two indices, and ranking by EDAS and TOPSIS
from the same weight vector.

The design question is which part of that pipeline moves the ranking. Four candidates are
separated: the model that writes the card, the model that supplies the judgments, the
ranking procedure, and repeated execution of one byte-identical request.

## Status

Pre-collection. No experimental data exists yet. Present state:

- [x] Protocol, criteria, performance matrix and linguistic scale fixed in `protocol/`
- [x] Response and card schemas fixed in `schemas/`
- [x] Computation layer implemented and unit tested in `src/agenticmcdm/`
- [ ] Screening of the performance matrix run with this code and archived in `results/`
- [ ] Model registry filled with exact API identifiers in `models/model_registry.csv`
- [ ] Archived release with a versioned DOI
- [ ] Data collection

Nothing in `protocol/` changes after the archived release without a dated entry in
`protocol/DEVIATIONS.md`.

## Why this repository is separate from the manuscript

The manuscript states the design in summary form and cites this repository for the
operational detail: the full admissibility checklist, the analysis populations, the repair
and missingness rules, and the complete warning list. Keeping them apart means the paper can
stay inside a conference page limit while the rules that make the design reproducible remain
citable and complete.

## Layout

```
protocol/    design decisions, criteria, matrices, scale, checklist, deviation log
prompts/     the exact English prompts sent to the models
schemas/     JSON schemas for the persona card and the structured response
models/      run registry: provider, exact API model id, snapshot, settings
src/         deterministic computation: AHP weights, consistency, EDAS, TOPSIS, screening
tests/       unit tests and invariant checks for the computation layer
run/         collection schedule
results/     screening output and, later, analysis output
```

## Install and test

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

## Screening the matrix

The performance matrix is a designed stimulus, not data. Before any model is called it has
to be shown that the matrix can express a difference between the two ranking procedures, and
that no single alternative wins almost everywhere. That check is stochastic weight-space
acceptability analysis:

```bash
.venv/bin/python -m agenticmcdm.screening --draws 500000 --seed 20260805 \
    --out results/screening_20260805.json
```

Acceptance, fixed in advance: at least three alternatives win somewhere, no alternative wins
more than 80 percent of the sampled weight space, and EDAS and TOPSIS select different
winners in at least 5 percent of it.

## What this study does not claim

There is no human reference, no expert consensus and no correct preference vector. The study
cannot say which model decides better, and does not try to. Every comparison is a statement
about disagreement between tested systems under one fictional case.

The decision trace is recalculable end to end. That is a property of the computation layer,
not evidence about why a model produced a particular judgment.

## License

MIT for the code. The protocol text, prompts and stimulus material are released under
CC BY 4.0. See `LICENSE`.
