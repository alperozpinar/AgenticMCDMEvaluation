# Open work

Ordered by what blocks what. Everything above the line has to happen before the first
model call.

## Blocking the pilot

### 1. Fill the model registry

Done for all five services on 2026-08-06. Each row carries a resolved identifier and an
access date: `claude-opus-5`, `gpt-5.6-sol`, `gemini-3.1-pro-preview`, `kimi-k3`, `grok-4.5`.

Google was blocked until billing was attached to the project behind the key. Every
`generateContent` call returned HTTP 429 with
`generate_content_free_tier_requests, limit: 0` while authentication and model listing both
worked, which is an account state rather than a code fault. It answers normally now.

One choice there is worth revisiting before the pilot. The account exposes no stable
pro-class model in the current generation, and `gemini-2.5-pro` is closed to new users, so
the alternatives were `gemini-3.1-pro-preview`, pro class but a preview, and
`gemini-3.6-flash`, stable but a smaller class than the other four services. Class parity
won, which buys a comparison between five frontier-class services and pays for it with a
snapshot that can move under the study. The preview status is recorded in the registry notes
and belongs in the manuscript limitations. Switching to `gemini-3.6-flash` is a one-cell edit
if snapshot stability is judged the more important of the two.

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

Done on 2026-08-06 for all five services. `python -m agenticmcdm.smoke ping` passes 5/5 and
`python -m agenticmcdm.smoke decision` passes 5/5: each service returns fifteen comparisons
over the fixed pair order, on the declared intensity scale, inside the reason length limit
and with no extra fields. Smoke output is discarded and does not enter the study.

Measured decision-call wall times were 17.8, 21.3, 22.5, 89.5 and 37.2 seconds, averaging
37.7. Moonshot is the outlier by a wide margin. A round is 75 slots, so at that average a
round runs about 47 minutes and the five rounds total near four hours of wall time. That
total is not a problem to solve: `PROTOCOL.md` section 3 already spaces the rounds at least
an hour apart and spans the collection over at least two calendar days, so the four hours
were always going to be spread across days rather than spent in one sitting.

Both failures the smoke test caught were in the prompt rather than in any service. The
prompt asked for JSON matching a schema it never supplied, and its placeholder for
`preferred` named the two fields instead of showing that a criterion code goes there. Rerun
both modes after any edit to `prompts/` or `schemas/`.

```bash
python -m agenticmcdm.harness collect --round 1 --dry-run   # renders, hashes, calls nothing
```

### 3. Generate and freeze the fifteen cards

Done on 2026-08-07. All fifteen are frozen in `protocol/cards/` with the index assignment in
`_assignment.csv` under seed 20260806. Two cards used the one structural repair the checklist
allows. The eleven admissibility items are recorded in `run/card_admissibility.csv` against
checklist version 2, whose K6, K7 and K8 wordings are a logged deviation.

`results/card_similarity.json` records what the cards looked like before any decision call.
Role and writer lift lexical overlap above the floor by almost the same amount, which says
the persona-card factor has material to work with and that a generator's wording is about as
recognisable as the role it describes.

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

- Client-side rate limiting is deliberately absent. Quota is managed on the API subscriptions
  themselves, and a throttle here would only duplicate that badly. What is present is the
  wait before the one permitted retry, which honours the provider's own Retry-After.
- The harness runs a round serially, and this is a design requirement rather than an
  unfinished optimisation. `PROTOCOL.md` section 3 randomises the execution order inside a
  round, interleaves providers across it, and records each call's position so a time effect
  can be examined afterwards. Running slots concurrently would collapse the realised order
  into a handful of moments and take all three of those properties with it. A round is about
  47 minutes at the measured rates, which is well inside the hour that separates rounds.
- The admissibility checklist is a human pass or fail and is not automated. Items such as
  "no claim that every person in the occupation shares these preferences" need a reader.
- No published numerical example has been reproduced for RGM-AHP, EDAS or TOPSIS. The tests
  cover invariants and hand-checkable cases. Reproducing a cited example needs the source in
  hand rather than a value recalled from memory.
