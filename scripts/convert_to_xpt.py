#!/usr/bin/env python3
"""Convert the exported SDTM CSV domains to SAS v5 XPORT (.xpt) for CDISC CORE validation.

Reads  : data/sdtm/csv/{DM,VS,LB,CM,PR,MH}.csv
Writes : data/sdtm/xpt/{dm,vs,lb,cm,pr,mh}.xpt

SAS Transport v5 (.xpt) is the format SDTM datasets are submitted to FDA in, and the
format the CDISC CORE conformance engine reads without a manifest (each file carries its
domain name internally). Run from the repo root:

    pip install pandas pyreadstat
    python scripts/convert_to_xpt.py
"""
import os
import pandas as pd
import pyreadstat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "sdtm", "csv")
DST = os.path.join(ROOT, "data", "sdtm", "xpt")
os.makedirs(DST, exist_ok=True)

DOMAINS = ["DM", "VS", "LB", "CM", "PR", "MH"]

for dom in DOMAINS:
    csv_path = os.path.join(SRC, f"{dom}.csv")
    if not os.path.exists(csv_path):
        print(f"  skip {dom}: no {dom}.csv found")
        continue

    # Read raw as strings; empty cells -> missing
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, na_values=[""])
    df.columns = [c.upper() for c in df.columns]

    # Coerce the SDTM variables that must be numeric
    for col in df.columns:
        if col == "AGE" or col.endswith("SEQ") or col.endswith("STRESN"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # xpt v5 hard limit: character values <= 200 chars
    for col in df.columns:
        if df[col].dtype == object:
            mask = df[col].fillna("").str.len() > 200
            n = int(mask.sum())
            if n:
                print(f"  {dom}.{col}: truncating {n} value(s) over 200 chars (xpt v5 limit)")
                df.loc[mask, col] = df.loc[mask, col].str.slice(0, 200)

    out = os.path.join(DST, f"{dom.lower()}.xpt")
    pyreadstat.write_xport(df, out, table_name=dom, file_format_version=5)
    print(f"  wrote {out}  ({len(df)} rows, {len(df.columns)} cols)")

print("Done.")
