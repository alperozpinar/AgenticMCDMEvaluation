# Protocol

Fixed before any model call. Changes after the first archived release are recorded in
`DEVIATIONS.md`, never edited in place.

## 1. What is being separated

Four candidate sources of ranking divergence:

1. the **persona-card condition**, meaning one frozen card text written by one generator
   model for one role;
2. the **hosted model-service condition**, meaning one provider, one API model snapshot,
   that provider's serving stack and its default decoding settings, at the time of the call;
3. the **ranking procedure**, EDAS or TOPSIS, applied to the same weight vector;
4. **repeated execution** of one byte-identical request.

Two naming rules follow from what the design can actually identify.

Each generator writes exactly one card per role, so a generator-role cell contains a single
card. The difference between two such cells therefore mixes the generator's general
card-writing behavior with the particular text it happened to produce. The factor is named
**persona-card condition** and never **generator model effect**. Claims are limited to the
fifteen tested card conditions. Producing several independent cards per generator-role cell,
and nesting card inside generator, is the design that would separate the two; it multiplies
the card-generation budget and is left to a later study.

Providers are called at their documented default decoding settings, seeds are not fixed, and
structured-output handling differs between providers. The observed difference is therefore
not a property of model weights alone. The factor is named **hosted model-service condition**
and never **model effect**. The term *byte-identical request* applies to the repetitions
within one cell, not across providers, whose API wrappers and system layers differ.

## 2. Design and counts

| Factor | Levels |
|---|---|
| Role | CFO, CIO, COO |
| Persona-card condition | one frozen card per role per generator, five generators |
| Hosted model-service condition | the same five snapshots, acting as decision respondents |
| Repetition | five per cell |
| Ranking procedure | EDAS and TOPSIS, within completion |

Cards: 3 roles x 5 generators = 15, each generated once.

Decision completions: 15 cards x 5 services x 5 repetitions = 375.

Derived rankings: 375 x 2 procedures = 750. These are dependent recalculations of the 375
completions and are never reported as a sample size.

Model calls: 375 decision calls + 15 card-generation calls = 390, plus a retry allowance.

### Pilot and its relation to the full study

The pilot covers the CFO role only, with all five generators, all five services and **three**
repetitions: 5 x 5 x 3 = 75 decision completions and 150 derived rankings, plus the five CFO
card-generation calls.

The full study completes the same grid. CFO receives **two further repetitions** so that it
reaches five like the other roles, and CIO and COO are run at five repetitions each:

```
CFO   5 x 5 x 3 (pilot) + 5 x 5 x 2 (completion) = 125
CIO   5 x 5 x 5                                   = 125
COO   5 x 5 x 5                                   = 125
                                              total 375
```

Pilot completions enter the main analysis **only if nothing in `protocol/`, `prompts/` or
`schemas/` changed after the pilot ran**. If anything changed, every pilot completion is
excluded from the primary population and reported separately as a pre-study run. This rule
exists so that the pilot cannot quietly become a tuning stage.

Two files are exempt, and only these two. `protocol/DEVIATIONS.md` is written after the
events it records, so a log that could not be appended to would not be a log. `protocol/
cards/` is written by the freeze step, which happens before the first decision call and never
again. Nothing else under those three directories may move once the pilot has run, and an
addition counts as a change.

Stopping rule for the pilot: it stops when its 75 scheduled slots are complete. It is not
extended, shortened or repeated on the basis of what it shows.

The CFO role runs first because it is the least expensive role to interpret if the pilot
reveals a protocol fault, not because it is expected to produce the largest divergence. No
prediction is registered about which role diverges most. A dominant cost priority could
just as easily pull services toward the same alternative and reduce divergence.

## 3. Call scheduling and temporal blocking

Hosted services vary with time, load and backend version, so an unrandomized call order
would let time move together with a factor.

- The 375 slots are laid out before collection as 5 **collection rounds**, each round holding
  one slot for every (card, service) cell: 15 cards x 5 services = 75 slots per round.
- The execution order of the 75 slots inside a round is randomized once, before collection,
  with a recorded seed.
- Repetition index means collection round. Repetitions of one cell therefore land in
  different rounds and are spread over time rather than issued back to back.
- Rounds are separated by at least one hour, and the whole collection spans at least two
  calendar days, so the measured quantity is short-to-medium term service variability rather
  than variability within a single minute. The realized spacing is reported.
- Providers are interleaved within a round rather than run in provider blocks.
- A transport failure with no model output is retried once in the same slot; both physical
  requests are kept. A schema failure is not a transport failure and is never retried.
- If a provider snapshot changes during collection, that provider's block stops. Completed
  slots keep their recorded snapshot, the change is entered in `DEVIATIONS.md`, and no two
  snapshots are merged under one label.
- Every record carries the UTC timestamp, the round, and the position within the round, so a
  time effect can be examined after the fact.

## 4. Elicitation

Six criteria give fifteen unordered pairs, presented in the fixed order in `criteria.yaml`.
For each pair the respondent returns the preferred criterion, one intensity label, and a
reason of at most 25 words. It then returns exactly three ordered criterion codes as its
declared priorities.

The label-to-number mapping is in `linguistic_scale.yaml`. The respondent sees labels only.
Reciprocals and the unit diagonal are constructed in code.

The prompt contains no instruction to be consistent. Hidden reasoning is not requested.
Tools, web access and memory are disabled and every completion runs in a new session.

**The short reasons are not analyzed.** They are collected so that the published decision
trace has a human-readable component beside each judgment. No measure in this protocol reads
them, and no claim is made from them. Treating them as evidence of the respondent's decision
process would contradict the reason the trace is external in the first place.

## 5. Validity and population rules

- `first_attempt_valid`: the slot's first semantic response satisfies the schema. Primary
  population.
- `repair_only`: schema-valid response after the single fixed repair request. Sensitivity
  population, never primary.
- `complete_pair`: member of `first_attempt_valid` for which both weights and both rankings
  compute.
- Cells are never topped up with replacement completions.
- A cell holding fewer than two members of `complete_pair` contributes nothing to an
  equal-weight aggregate; the aggregate element containing it is reported as **undefined**
  rather than renormalized over the surviving cells. This rule applies to every table and
  figure that aggregates across cells.

## 6. Estimands

Let `m` index the five hosted model-service conditions, `c` the fifteen persona-card
conditions, `r` the repetitions and `p` the two ranking procedures. Let `d(.,.)` be the
generalized Kendall distance over the six alternative pairs, with the tie tolerance in
`linguistic_scale.yaml`.

**E1, repeat stability.** Within cell `(m, c, p)`:

```
theta_rep(m,c,p) = mean over r < s of d( R(m,c,r,p), R(m,c,s,p) )
```

a U-statistic over the cell's completions, not `n choose 2` independent observations.
Aggregate with equal weight over `c` within a role, then over roles.

**E2, persona-card condition difference.** For two card conditions `c` and `c'` of the same
role, holding `m` and `p` fixed, use all cross products of their completions:

```
theta_card(m,c,c',p) = (1 / (n_mc * n_mc')) * sum over r, s of d( R(m,c,r,p), R(m,c',s,p) )
```

Repetition indices are never paired across conditions, because repetition means collection
round and carries no correspondence between different cells. Average over the ten unordered
card pairs within a role, then over `m` with equal weight, then over roles.

**E3, hosted model-service difference.** The same cross-product construction with `m` and
`m'` varying and `c` fixed.

**E4, ranking-procedure difference.** Within one completion the two procedures produce one
paired distance:

```
theta_proc(m,c,r) = d( R(m,c,r,EDAS), R(m,c,r,TOPSIS) )
```

Average over `r` within a cell, then over cells with equal weight.

E4 is a within-completion paired quantity while E1 to E3 are cross-completion U-statistics.
They are reported in one table only with that difference stated in the caption, because they
do not have the same sampling structure.

**E5, declared-priority congruence.** For each completion and procedure, the fractional
top-three overlap between the three declared criteria and (a) the computed weight order and
(b) the criterion-removal impact order.

## 7. Interactions and the diagonal

The one-factor-at-a-time comparisons above are the primary reporting. Three conditional
contrasts are registered in addition, reported as conditional differences and never as
tests:

1. persona-card condition by hosted model-service condition;
2. role by hosted model-service condition;
3. hosted model-service condition by ranking procedure.

The same five snapshots act as generators and as decision respondents, so the grid has a
diagonal: cells where a service answers a card written by the same snapshot. **Self-authored
and other-authored card conditions are compared as a registered conditional contrast.** This
is reported as a difference between two sets of tested cells, not as a test of whether
blinding worked.

## 8. Blinding and its manipulation check

The card reaching a decision respondent carries no generator identity. Identifiers are
neutral within-role indices assigned at random and held constant across services, and card
text is screened for self-reference before freezing.

After collection, in a separate session that enters no other analysis:

- each of the five services is shown all fifteen anonymized cards in one prompt;
- it is asked to name **exactly three** cards it believes it wrote, one per role;
- accuracy is scored per role as correct or not, giving five services x three roles = fifteen
  binary outcomes;
- chance level is one in five per role, so twenty percent;
- the reported quantity is the count of correct identifications out of fifteen, with the
  exact binomial interval against chance;
- the same snapshot is used as in the main run, and this is recorded.

This is a supporting check with a known limitation: seeing fifteen cards side by side allows
comparative style inference that a single-card decision session does not. It can therefore
overstate what a respondent could infer during the actual run, and it could equally
understate it. **No conclusion of the form "blinding was successful" is drawn.** The result
is reported as a bounded, one-sided piece of evidence.

## 9. Intervals

- Stratified bootstrap resampling completions inside each fixed cell, keeping both
  procedures, the consistency indices and the declared priorities attached to their source
  completion.
- 9,999 replicates, seed recorded in the analysis script.
- Percentile intervals. BCa is not used, because with five completions per cell the
  acceleration estimate is unstable.
- A cell with fewer than two eligible completions makes its aggregate element undefined; no
  interval is produced for an undefined element.
- Resampling with replacement inside a five-element cell will draw duplicates. That is the
  intended behavior and is why the interval is narrow evidence: **it covers run-to-run
  variability within a fixed cell and nothing else.** It carries no uncertainty about which
  card or which service was chosen, because those are fixed conditions.
- Point estimates, raw cell distributions and exact denominators are the primary reporting.
  Intervals are supporting.
- No confirmatory test and no p-value.

## 10. Criterion-removal impact

For criterion `j` and one procedure:

1. remove `j` from the weight vector and from the performance matrix;
2. renormalize the remaining five weights to sum to one;
3. rerun the full ranking on the reduced matrix;
4. compare against the original winner set `W0`.

Margin of the original winner set:

```
M(scores) = min over a in W0 of score(a) - max over b not in W0 of score(b)
```

Removal impact is `I(j) = M(original) - M(after removing j)`. A larger positive value means
removing `j` weakened the original winner set more. If every alternative is in `W0` the
margin is undefined and the impact for that completion is recorded as undefined. If the
winner set changes after removal, `M` is still evaluated against the original `W0`, so the
value may be negative; negative values are kept and ranked as they are.

Ties in the ranking of `I(j)` are handled by fractional top-three membership: criteria
strictly above a boundary tie score 1, strictly below score 0, and a tied block of `t`
criteria competing for `q` remaining places scores `q/t` each.

Removing a criterion changes the EDAS average and the TOPSIS ideal points as well as the
weights, so `I(j)` is a property of the whole pipeline and not a measure of a criterion's
intrinsic importance. Impacts are compared within a procedure and never numerically across
procedures, because the two score scales are not commensurable.

## 11. Warnings

A warning record is emitted when:

- the consistency ratio reaches 0.10;
- the appraisal-score gap between the leading and second alternative falls below 0.01, with
  the same summary repeated at 0.005 and at 0.02;
- fewer than four of the five completions in a full cell share the modal winner set, stated
  as a count because five completions admit only five proportions;
- the first semantic response fails the schema, or a repair is used;
- a provider snapshot changes during collection;
- the withheld dominated alternative outranks its dominator, which is a software fault.

The three appraisal-gap values are reported together rather than as one threshold, because
EDAS and TOPSIS score differences are not on a common scale and no single margin can be
justified for both.

## 12. Reference-set recalculation

The withheld alternative E is added to the four main alternatives with the weight vector
held fixed, and every term is recomputed from scratch.

Two separate things are read from this, and they are not the same kind of result.

- **E never outranks D** is a software validation check. Both procedures preserve dominance
  under positive weights, which `tests/test_mcdm.py` asserts directly. An E-over-D event
  means the code is wrong.
- **An inversion among A to D after E is added** is a genuine reference-set sensitivity of
  the ranking procedures, because E moves the EDAS average and the TOPSIS ideal points. It
  is reported as a property of the procedures, not as respondent behavior.

The recalculated ranking is not directly comparable with the main ranking, since the
reference set differs.

## 13. What is not claimed

No human reference, no expert consensus, no correct preference vector. The study cannot say
which service decided better and does not try to.

The decision trace is recalculable end to end. That is a property of the computation layer.
It is not evidence about why a respondent produced a particular judgment, and the audit is
described as an **external decision-trace audit** rather than as an explanation of the
respondent's reasoning.

The measured quantity is case-conditioned criterion importance under a professional-role
card. The respondent sees the performance matrix, so its judgments can be shaped by the
value ranges in that matrix. It is not a general role preference.
