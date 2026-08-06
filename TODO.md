# Open work

Ordered by what blocks what. Everything above the line has to happen before the first
model call.

## Blocking the pilot

### 1. Fill the model registry

Done for four of five services on 2026-08-06: `anthropic`, `openai`, `moonshot` and `xai`
carry resolved identifiers and access dates. The `google` row is still blocked and its
`api_model_id` is empty, so it must be either filled or removed before the schedule is built.

Google returns HTTP 429 on every `generateContent` call with
`generate_content_free_tier_requests, limit: 0`. Authentication and model listing both work,
so this is an account state and not a code fault: the project behind the key has no
billing account, and the free tier grants it no requests. Two ways out, and they are not
equivalent. Attach a billing account to the project, which needs no code change and keeps the
service factor at five levels. Or drop Google, record it here and in `DEVIATIONS.md`, and
carry a four-level service factor through the analysis.

If billing is enabled, the snapshot still has to be chosen and the choice is not free. The
account sees no stable pro-class model in the current generation: `gemini-3.1-pro-preview` is
pro class but a preview, `gemini-3.6-flash` is stable but a smaller class than the other four
services, and `gemini-2.5-pro` is stable pro but a generation behind. Class parity with the
other four argues for the preview, in which case the preview status belongs in the registry
notes and in the manuscript limitations, because a preview snapshot can move under the study.

The table below describes a row. `adapter` decides which request shape is used.

| column | what goes in it |
|---|---|
| `provider` | short label used in run ids, for example `openai`, `anthropic`, `google`, `xai`, `moonshot` |
| `adapter` | `openai_compatible`, `anthropic` or `google` |
| `api_model_id` | the exact API identifier, not a product name. `ChatGPT SOL` is not one |
| `snapshot` | the dated snapshot if the provider exposes one |
| `base_url` | only when it differs from the adapter default, as it does for xAI and Moonshot |
| `key_env` | the environment variable holding the key, for example `OPENAI_API_KEY`. Never the key itself |
| `role_in_study` | `generator`, `decision` or `both` |
| `requested_temperature`, `top_p`, `seed` | leave empty. Empty means the provider default is used, which is what the protocol wants |

Keys live in the shell environment. Nothing in this repository reads a key from a file and
nothing writes one to the ledger.

### 2. Smoke test each provider

Done on 2026-08-06 for the four reachable services. `python -m agenticmcdm.smoke ping`
passes 4/4 and `python -m agenticmcdm.smoke decision` passes 4/4: each service returns
fifteen comparisons over the fixed pair order, on the declared intensity scale, inside the
reason length limit and with no extra fields. Google is untested for the reason in item 1.
Smoke output is discarded and does not enter the study.

Both failures the smoke test caught were in the prompt rather than in any service. The
prompt asked for JSON matching a schema it never supplied, and its placeholder for
`preferred` named the two fields instead of showing that a criterion code goes there. Rerun
both modes after any edit to `prompts/` or `schemas/`.

```bash
python -m agenticmcdm.harness collect --round 1 --dry-run   # renders, hashes, calls nothing
```

### 3. Generate and freeze the fifteen cards

Not yet implemented in the harness. Needs: one call per generator per role using
`prompts/card_generation.txt`, structural validation with `schema_check.check_card`, the
self-reference scan, the human admissibility checklist recorded per card, then freezing to
`protocol/cards/P-<ROLE>-<n>.json` with hashes. The anon index assignment is random within
role and identical across services.

### 4. Domain review of the criteria and the matrix

Someone with the domain background confirms that the six criterion definitions, their units
and the values in `decision_matrix_main.csv` are plausible. The screening only shows the
matrix is mathematically usable, not that it is sensible.

### 5. Archival deposit

GitHub is a working copy, not an archive: history can be rewritten and the repository can be
renamed, made private or deleted. Connect Zenodo to this repository and cut a release, which
mints a versioned DOI. Then record that DOI in the manuscript, in `CITATION.cff` and in
`protocol/DEVIATIONS.md`.

---

## After the pilot

### 6. Analysis layer

Not written. Needs the estimands in `protocol/PROTOCOL.md` section 6 implemented: repeat
stability as a per-cell U-statistic, cross-condition distances as cross products, the paired
procedure distance, declared-priority congruence, criterion-removal impact, the stratified
bootstrap at 9,999 percentile replicates, and the undefined-cell rule.

### 7. Blinding manipulation check

One call per service after collection, per `PROTOCOL.md` section 8. Fifteen binary outcomes
against a chance level of one in five.

### 8. Reference-set recalculation

Add E with fixed weights, recompute every term, and report the two readings separately: an
E-over-D event is a software fault, an A to D inversion is procedure sensitivity.

---

## Known gaps in what exists

- `providers.py` has no rate limiting and no backoff. Add both before running 375 calls.
- The harness runs a round serially. That is deliberate for now, since interleaving providers
  matters more than speed, but a long round will take a while.
- The admissibility checklist is a human pass or fail and is not automated. Items such as
  "no claim that every person in the occupation shares these preferences" need a reader.
- No published numerical example has been reproduced for RGM-AHP, EDAS or TOPSIS. The tests
  cover invariants and hand-checkable cases. Reproducing a cited example needs the source in
  hand rather than a value recalled from memory.
