# Zenodo deposit, operator checklist

Order matters. Zenodo's GitHub integration archives only releases created AFTER the switch is
enabled for this repository, and the switch is per repository. Another project already being
connected does not connect this one.

1. Zenodo, Account, GitHub. If `AgenticMCDMEvaluation` is not listed, press "Sync now".
   Turn the switch ON for this repository.
2. Only then, on GitHub, draft a release: tag `v0.2.0`, target the current `master` head,
   title "v0.2.0", body from `RELEASE_v0.2.0.md`.
3. Publish. Zenodo mints two DOIs: a concept DOI covering all versions, and a version DOI for
   v0.2.0.
4. Report the VERSION DOI (the one specific to v0.2.0, not the concept DOI).

## What gets recorded once the version DOI is known

- `protocol/DEVIATIONS.md`: a deposit entry with the DOI and the date.
- `CITATION.cff`: the `doi` field. `version` and `date-released` are already set to 0.2.0 and
  2026-08-27; correct the date if the release is cut on another day.
- Manuscript Section III-F: the deposit line in the timeline.
- Manuscript Declarations: the sentence that currently says the deposit was not in place.
- Manuscript Section V-B: keep the statement that this is not a registered report. The deposit
  follows the start of collection and does not change that.

## Metadata already prepared

`.zenodo.json` carries the three authors with affiliations, the description, the keywords and
the licence, so the Zenodo record does not fall back to GitHub metadata and name the account
owner as the only author. The record licence is set to CC-BY-4.0 because the material is what
the paper cites; the dual licensing is stated in the description. Say so if you would rather
the record carried MIT.
