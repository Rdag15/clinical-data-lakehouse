# CDISC CORE Conformance Validation

The six SDTM domains (`DM`, `VS`, `LB`, `CM`, `PR`, `MH`) were exported to **SAS Transport
v5 (`.xpt`)** and validated with the open-source [CDISC CORE rules
engine](https://github.com/cdisc-org/cdisc-rules-engine) against the full **SDTMIG v3.4**
rule set:

```bash
./core validate -s sdtmig -v 3-4 -d data/sdtm/xpt
```

Full machine-readable report: [`validation/sdtmig-3-4-report.xlsx`](validation/sdtmig-3-4-report.xlsx).

## Scoreboard

| Result | Rules | Meaning |
|--------|------:|---------|
| ✅ Passed | **118** | data conforms |
| ⚠️ Issues | **14** | findings raised (triaged below) |
| ⛔ Errored | **2** | rule needed inputs not supplied (Define-XML / CT package) |
| ⏭️ Skipped | **296** | rule N/A — requires Define-XML, a Trial Summary (TS) dataset, CT packages, or domains not present |

Run time ≈ 59s. The 296 skips matter as much as the passes: a third of the v3.4 rule set
assumes a *complete submission package*. This project supplies six data domains in
isolation, so those rules have nothing to bind to — expected, not a gap.

## The key insight

The raw finding count looks large (~150K) but **collapses to ~6 root causes** — the
high-volume rules fire **once per record**, not once per distinct problem. `EPOCH`-missing
alone accounts for 65,443 of them: one structural gap × every row in five domains.

**A spotless pass on real-world data would be the suspicious result** — it would mean the
LOINC→CDISC and dictionary mappings had been invented rather than honestly left as a
documented gap. The value isn't a green checkmark; it's reading 150K findings, compressing
them to their root causes, and sorting each into *expected / cosmetic / real* with a reason.

---

## Triage

### Bucket 1 — Expected RWD→SDTM artifacts (the trial machinery observational data lacks)

These are "violations" only because real-world/EHR data has no protocol. Each is defensible.

| Rule | Finding | Why it's expected |
|------|---------|-------------------|
| CORE-000701 | `EPOCH` missing (65,443) | EPOCH labels a protocol epoch (screening/treatment/follow-up). RWD has no protocol epochs. Permissible, not required. |
| CORE-000767 | `FAOBJ` ≠ `--DECOD` (25,073, CM/PR/MH) | Rule cross-references a Findings-About (FA) companion dataset that doesn't exist here. |
| CORE-000236 / 000250 | MH dates on/after `RFSTDTC` (6,841) | `RFSTDTC` is set to first encounter; in EHR data "history" includes ongoing/concurrent conditions. No true enrollment anchor cleanly separates *prior* from *during* — a genuine modeling nuance of observational data. |
| CORE-000739 | `EX` (Exposure) dataset absent (6) | No investigational product — it's an observational cohort. |
| CORE-000699 / 000334 | `LBCAT`/`LBSCAT`/`LBSPEC`/`LBMETHOD` absent (3) | Permissible grouping variables the source EHR doesn't carry. |
| CORE-001081 | Role-vs-Define-XML — *errored* | No Define-XML supplied. |

### Bucket 2 — Structural / metadata (trivially fixable, cosmetic)

| Rule | Finding | Fix |
|------|---------|-----|
| CORE-000852 | `DM` variable order (1) | one `.select()` reorder to the IG-specified column order |
| CORE-000328 / 000321 / 000776 | study-day `--DY` / `--ENDY` missing (9) | derivable from `RFSTDTC` — but moot here, since Safe Harbor reduced dates to year-only, so day-level derivation is intentionally unavailable |
| CORE-000929 | DOMAIN-vs-CT — *errored* | errored (not failed) because no controlled-terminology package was configured for the run |

> Note the link between **CORE-000328 and the de-identification design**: the missing
> study-day variables are a *direct consequence* of the Safe Harbor date generalization.
> The two standards interact, and that interaction is documented rather than papered over.

### Bucket 3 — Genuine mapping work (the LOINC lab long-tail)

This is the cluster that, in a real CRO workflow, you'd actually go fix — and it's the
honest seam of the project.

| Rule | Finding | Root cause |
|------|---------|-----------|
| CORE-000220 | `--TESTCD` format (28,960) | raw LOINC codes (`182626`, `20859`) sit in a field expecting short CDISC test codes — too long, start with digits |
| CORE-000199 | `--TEST` > 40 chars (21,111) | LOINC long names exceed SDTM's 40-char limit |
| CORE-000303 | `LBTESTCD` ↔ `LBTEST` not 1:1 (871) | a real consistency issue to clean |

**The fix is a LOINC → CDISC lab-test-code crosswalk.** Building the full LOINC universe
into the CDISC lab codelist is exactly the hard, manual terminology work CROs staff for, so
the high-frequency vitals were mapped and the lab tail was left documented rather than faked.

#### What "done right" looks like — Vital Signs (VS)

VS shows the contrast: **89% of vitals mapped to clean CDISC Controlled Terminology** —
`BMI`, `DIABP`, `HEIGHT`, `HR`, `PAIN`, `RESP`, `SPO2`, `SYSBP`, `TEMP`, `WEIGHT`. The
remaining ~11% are LOINC codes in the documented fallback. So VS isn't "broken" — it's
mapped where the concept set is small and known, and explicitly flagged where it isn't.

---

## Documented mapping substitutions

Called out here the way a real **Study Data Reviewer's Guide** would, rather than hidden:

- **`--DECOD` holds raw SNOMED/RxNorm codes** instead of MedDRA (events) / WHODrug (meds)
  dictionary terms — those dictionaries require licenses not warranted for synthetic data.
- **All conditions → MH** rather than split between MH and AE — without a protocol-defined
  study start there's no clean "arising during treatment" boundary, so MH is the defensible
  default for RWD.
- **`RFSTDTC` = first encounter year** — a synthesized reference-start frame, since RWD has
  no enrollment date.

## Reproducing

```bash
pip install pandas pyreadstat
python scripts/convert_to_xpt.py                 # data/sdtm/csv → data/sdtm/xpt
./core validate -s sdtmig -v 3-4 -d data/sdtm/xpt
```

CORE binaries: <https://github.com/cdisc-org/cdisc-rules-engine/releases>.
