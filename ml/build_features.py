#!/usr/bin/env python3
"""Build a de-identified, leakage-aware patient feature table for diabetes-phenotype modeling.

This mirrors the Databricks `gold.patient_features` layer in pandas so the ML step is
runnable offline (no Databricks workspace needed). Reads the Synthea CSV export and writes
`ml/patient_features.csv`.

Target  : has_diabetes — type-2 diabetes mellitus (incl. its complications), EXCLUDING
          prediabetes. (Synthea labels prediabetes as "Prediabetes (finding)", which the
          naive `.contains("diabetes")` would wrongly include.)

Features: demographics + general healthcare utilization, chosen to avoid leakage:
  - INCLUDED : age, is_male, income, healthcare_expenses, healthcare_coverage,
               encounter_count, procedure_count, observation_count
  - EXCLUDED : condition counts (would contain the diabetes diagnosis itself — direct
               leakage); medication_count (too tightly coupled to diabetes treatment —
               circular); race/ethnicity (protected attributes, excluded from models by the
               project's de-identification stance, consistent with gold.patient_features).
"""
import os
import argparse
import pandas as pd
import numpy as np

# Fixed reference date so ages are reproducible (matches the project's "today").
REFERENCE_DATE = pd.Timestamp("2026-06-27")


def _age(birth, death):
    end = death.fillna(REFERENCE_DATE)
    years = (end - birth).dt.days / 365.25
    age = np.floor(years).astype("Int64")
    return age.clip(upper=90)  # HIPAA Safe Harbor: top-code at 90


def _count_by_patient(path, name):
    df = pd.read_csv(path, usecols=["PATIENT"], dtype=str)
    return df.groupby("PATIENT").size().rename(name)


def build_features(csv_dir: str) -> pd.DataFrame:
    pats = pd.read_csv(
        os.path.join(csv_dir, "patients.csv"),
        dtype=str,
        usecols=["Id", "BIRTHDATE", "DEATHDATE", "GENDER", "INCOME",
                 "HEALTHCARE_EXPENSES", "HEALTHCARE_COVERAGE"],
    )
    pats["BIRTHDATE"] = pd.to_datetime(pats["BIRTHDATE"], errors="coerce")
    pats["DEATHDATE"] = pd.to_datetime(pats["DEATHDATE"], errors="coerce")

    feats = pd.DataFrame({"patient_id": pats["Id"]})
    feats["age"] = _age(pats["BIRTHDATE"], pats["DEATHDATE"])
    feats["is_male"] = (pats["GENDER"] == "M").astype(int)
    feats["income"] = pd.to_numeric(pats["INCOME"], errors="coerce")
    feats["healthcare_expenses"] = pd.to_numeric(pats["HEALTHCARE_EXPENSES"], errors="coerce")
    feats["healthcare_coverage"] = pd.to_numeric(pats["HEALTHCARE_COVERAGE"], errors="coerce")

    # general utilization counts (NOT conditions, NOT medications)
    for fname, col in [("encounters.csv", "encounter_count"),
                       ("procedures.csv", "procedure_count"),
                       ("observations.csv", "observation_count")]:
        counts = _count_by_patient(os.path.join(csv_dir, fname), col)
        feats = feats.merge(counts, left_on="patient_id", right_index=True, how="left")

    feats[["encounter_count", "procedure_count", "observation_count"]] = (
        feats[["encounter_count", "procedure_count", "observation_count"]].fillna(0).astype(int)
    )

    # target: type-2 diabetes + complications, excluding prediabetes
    cond = pd.read_csv(os.path.join(csv_dir, "conditions.csv"), dtype=str,
                       usecols=["PATIENT", "DESCRIPTION"])
    desc = cond["DESCRIPTION"].str.lower()
    is_dm = desc.str.contains("diabet") & ~desc.str.contains("prediabetes")
    diabetic_patients = set(cond.loc[is_dm, "PATIENT"])
    feats["has_diabetes"] = feats["patient_id"].isin(diabetic_patients).astype(int)

    return feats


def main():
    ap = argparse.ArgumentParser()
    default_csv = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "synthea", "output", "csv")
    ap.add_argument("--csv-dir", default=default_csv, help="Synthea CSV export directory")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   "patient_features.csv"))
    args = ap.parse_args()

    feats = build_features(args.csv_dir)
    feats.to_csv(args.out, index=False)
    n, pos = len(feats), int(feats["has_diabetes"].sum())
    print(f"wrote {args.out}: {n} patients, {len(feats.columns)} cols")
    print(f"diabetes prevalence: {pos}/{n} = {pos / n:.1%}")


if __name__ == "__main__":
    main()
