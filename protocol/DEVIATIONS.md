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

## 2026-08-06, model registry fixed at five services

All five rows in `models/model_registry.csv` are filled and dated: `claude-opus-5`,
`gpt-5.6-sol`, `gemini-3.1-pro-preview`, `kimi-k3` and `grok-4.5`. Both smoke modes pass 5/5.
No scheduled call has been made, so nothing is affected.

The Google snapshot is a preview and this is a known weakness rather than an oversight. The
account exposes no stable pro-class model in the current generation and `gemini-2.5-pro` is
closed to new users, so the choice was between a preview at the same class as the other four
services and a stable model one class below them. Class parity was preferred, because a
service factor whose levels differ in class confounds the comparison the study is built on.
The cost is that a preview snapshot can change during collection. The access date is
recorded, and if the snapshot is observed to change mid-collection that is a deviation to be
logged here and the affected cells recollected.

## 2026-08-06, retry refined and rounds made resumable

Section 3 says a transport failure with no model output is retried once in the same slot and
both physical requests are kept. The retry count is unchanged. Three refinements sit under
it, all made before any scheduled call, so no collected data is affected.

A wait now separates the two attempts, and it uses the provider's own Retry-After when one
was sent, capped at 120 seconds. Retrying a rate limit in the same instant reproduces it.

The retry is no longer issued when the provider's status describes the request rather than
the moment. A 400, 401, 403 or 404 means the request as constructed is not acceptable, and
sending it again cannot change that. This narrows "retried once" to the transient failures
the rule was written for; a rejected request is now recorded and the round stops. Stopping is
new and it is protective: without it a wrong key spends 75 slots proving the same point.

Because a round can now stop partway, it has to be resumable without recalling what it
already recorded. A slot is skipped on a rerun once it has produced model output, or once its
one permitted retry has been spent. A slot whose only record is a single failed first attempt
is not skipped, since that is exactly what an aborted round leaves behind.

Client-side rate limiting was considered and not implemented. Quota is managed on the API
subscriptions, and a second throttle here would only interact with the first unpredictably.

Concurrency was also considered and rejected on protocol grounds rather than effort. Section
3 randomises the execution order within a round, interleaves providers across it, and records
each call's position so a time effect can be examined afterwards. Concurrent execution would
collapse the realised order into a few moments and void all three. At the measured call rates
a round takes about 47 minutes, comfortably inside the hour that separates rounds.

## 2026-08-07, checklist items K6, K7 and K8 given operative wordings

The fifteen card-generation calls were made and all fifteen candidates were structurally
valid. Two of them, Anthropic's CFO and COO cards, used the one structural repair the
checklist allows: the first attempt carried an extra `professional_background_note` field.
Both physical requests are kept.

Reading the candidates against the checklist showed that three items were worded so loosely
that each admitted a reading under which no card conforming to the frozen card schema could
ever pass. K6 forbade an explicit ordering of the six criteria while the schema requires
`decision_priorities` as an ordered array. K8 forbade factual claims beyond the registered
case while the schema requires `organizational_constraints`, and the registered case
describes the four platforms rather than the buying organization, so every conforming card
adds context the case omits. K7 named hard thresholds without saying what makes a statement
one.

Checklist version 2 states the operative wording for all three. K6 now names the six
registered criteria by code or registered name as what may not be ordered. K7 applies the
test of whether a statement would remove an alternative in the registered matrix from
consideration. K8 restricts the prohibition to claims about the alternatives, the criterion
values or the market.

This clarification was written after the cards existed and is recorded as a deviation rather
than as a correction, which is the honest label. Two things bear on how much weight it
should carry. Each wording is derived from the card schema, which was frozen before any
generation call, rather than from what the cards turned out to say. And the alternative did
not avoid the problem: regenerating the cards under a stricter reading would still have meant
choosing the reading after seeing model output.

Under version 2 all fifteen candidates pass every item, and the recorded verdicts are in
`run/card_admissibility.csv`.

## 2026-08-07, cards frozen and a pre-collection descriptive added

The fifteen cards are frozen in `protocol/cards/`. The within-role indices were drawn at
freeze time from seed 20260806 and the generator-to-index mapping is in
`protocol/cards/_assignment.csv`. That file never enters a prompt.

A descriptive was added that was not in the original protocol: the lexical overlap between
the frozen cards, in `results/card_similarity.json`. It gates nothing and no decision
depends on it. It is reported because the persona-card factor can only move a ranking if the
cards differ, and a reader who sees a small E2 is entitled to know what the cards looked like
before any decision call was made. Adding it before collection rather than after is the
point: it cannot be chosen later to suit a result.

Because each generator writes one card per role, every card pair sits in one of three cells.
Same role and different generator averages 0.179 Jaccard overlap over 30 pairs. Different
role and same generator averages 0.183 over 15 pairs. Different role and different generator
averages 0.118 over 60 pairs. Role and writer therefore lift overlap above the floor by
almost the same amount, 1.51 against 1.55, and the two most similar pairs in the whole set
are cards of different roles written by the same generator.

Two consequences are worth stating before collection rather than after. The persona-card
factor has real material to work with, since same-role cards share less than a fifth of
their vocabulary. And a generator's wording is about as recognisable as the role it
describes, which is a reason to expect the section 8 manipulation check to score above
chance. The protocol already refuses to conclude that blinding succeeded; this is a
quantitative reason to keep that refusal.

The measure is lexical rather than semantic, so it bounds one direction only: high overlap
would show similar wording, while low overlap leaves open that two cards express the same
priorities in different words.

## Open before the first call

- Domain review of the criterion definitions, units and values is outstanding.
- The archived release and its versioned DOI have not been created.
