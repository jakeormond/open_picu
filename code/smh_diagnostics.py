"""Step 2 diagnostics for SMH (St Mary's): how the IDs link, the PICANet link, the time offset, the drug-table versions.

Counts only: nothing returned is an ID, a date or a row value. Shared helpers are in diagnostics.py.
The interventionId-to-measurement tables are mapping work and live in smh_mappings.py, not here.
Notebook: smh_diagnostics.ipynb.

    import smh_diagnostics as SD
    d = SD.load(smh_dir)
    SD.demographics_duplicates(d)       # repeated rows per encounter, encounters per patient
    SD.picanet_link(d)                  # PICANet rows, link to demographics, UniquePtID agreement, PICANet by year
    SD.weight_checks(d)                 # weight and admission time within an encounter; against PICANet weight
    SD.time_offset(smh_dir, d)          # first vitals row against inTime: is inTime local time and the chart time UTC?
    SD.medication_versions(smh_dir)     # medications, medications_furosemide, medications_v2
    SD.drug_coverage_by_year(smh_dir, manifest)   # share of eligible stays with drug rows, by admission year
"""
from pathlib import Path

import numpy as np
import pandas as pd

import diagnostics as D
import inventory as I

DEMO, PIC = "ai_picu_demographics.csv", "ai_picu_piccanet.csv"
DRUG_FILES = ["ai_picu_infusion.csv", "ai_picu_medications.csv", "ai_picu_medications_furosemide.csv",
              "ai_picu_medications_v2.csv"]


def _dir(smh_dir):
    return Path(smh_dir).expanduser()


def load(smh_dir):
    """Demographics (all rows and with exact duplicates removed) and PICANet, read once."""
    smh_dir = _dir(smh_dir)
    raw, _ = I.read(smh_dir / DEMO)
    d1 = raw.drop_duplicates().copy()
    d1["t"] = I.parse_dates(d1["inTime"])[0]
    d1["w"] = pd.to_numeric(d1["Weight"], errors="coerce")
    pic, _ = I.read(smh_dir / PIC)
    return {"dir": smh_dir, "demo_all": raw, "demo": d1, "pic": pic}


def demographics_duplicates(d):
    """Exact duplicate rows, encounters with differing rows (and which columns differ), encounters per patient."""
    raw, d1 = d["demo_all"], d["demo"]
    base = d1.drop(columns=["t", "w"])
    dup = base[base["encounterId"].duplicated(keep=False)]
    return {"rows": pd.DataFrame({"count": [len(raw), len(base), base["encounterId"].nunique(),
                                            base["UniquePtID"].nunique(), dup["encounterId"].nunique()]},
                                 index=["rows", "rows after exact duplicates removed", "encounters", "patients",
                                        "encounters with differing rows"]),
            "most distinct values within an encounter, by column":
                dup.groupby("encounterId").nunique().max().to_frame("distinct values"),
            "encounters per patient": base.groupby("UniquePtID")["encounterId"].nunique()
                                          .value_counts().sort_index().head(8).to_frame("patients")}


def picanet_link(d):
    """PICANet against demographics: rows, link by encounterId, whether UniquePtID agrees, and PICANet membership
    by admission year (the cohort starts in 2013 because PICANet does)."""
    pn, d1 = d["pic"], d["demo"]
    m = pn.merge(d1[["encounterId", "UniquePtID"]].drop_duplicates(), on="encounterId", suffixes=("", "_dem"))
    summary = pd.DataFrame({"value": [len(pn), pn["encounterId"].nunique(),
                                      round(pn["encounterId"].isin(d1["encounterId"]).mean(), 3),
                                      int(pn["PIM3"].isna().sum()) if "PIM3" in pn else None,
                                      round((m["UniquePtID"] == m["UniquePtID_dem"]).mean(), 3)]},
                           index=["PICANet rows", "unique encounterId", "share of PICANet encounters in demographics",
                                  "PIM3 missing", "UniquePtID equal in both files (0 = the two files use different patient IDs)"])
    e = d1.assign(year=d1["t"].dt.year, picanet=d1["encounterId"].isin(pn["encounterId"]))
    return {"link": summary,
            "encounters by admission year and PICANet membership":
                e.groupby(["year", "picanet"])["encounterId"].nunique().unstack(fill_value=0)}


def weight_checks(d):
    """Admission time and weight within an encounter, and weight against the PICANet weight."""
    d1, pn = d["demo"], d["pic"]
    g = d1.groupby("encounterId")
    gap = g["t"].agg(lambda s: (s.max() - s.min()).total_seconds() / 3600)
    ratio = g["w"].agg(lambda s: s.max() / s.min())
    summary = pd.DataFrame({"count": [int((g["inTime"].nunique() > 1).sum()), int((g["Weight"].nunique() > 1).sum()),
                                      int(d1["Weight"].notna().sum() - d1["w"].notna().sum())]},
                           index=["encounters with more than one inTime", "encounters with more than one Weight",
                                  "non-numeric Weight entries"])
    pw = pn.drop_duplicates("encounterId").set_index("encounterId")["Weight"].rename("pn_weight")
    dw = g["w"].agg(["min", "median", "max"]).join(pw, how="inner").dropna(subset=["pn_weight"])
    agree = pd.DataFrame({"share within 5% of PICANet weight":
                          {c: round(((dw[c] - dw["pn_weight"]).abs() / dw["pn_weight"] < 0.05).mean(), 3)
                           for c in ["min", "median", "max"]}})
    return {"summary": summary,
            "inTime spread within an encounter, hours (where > 0)": gap[gap > 0].describe().round(1).to_frame("value"),
            "max/min weight within an encounter (where > 1, finite)":
                ratio[(ratio > 1) & np.isfinite(ratio)].describe().round(3).to_frame("value"),
            f"demographics weight against PICANet weight ({len(dw)} encounters)": agree}


def time_offset(smh_dir, d):
    """Hours from inTime to each encounter's first vitals row, overall and by season. A one-hour shift in summer and
    none in winter means inTime is London local time and utcChartTime is UTC (British Summer Time)."""
    v, _ = I.read(_dir(smh_dir) / "ai_picu_vitals.csv", usecols=["encounterId", "utcChartTime"])
    first = pd.to_datetime(v["utcChartTime"]).groupby(v["encounterId"]).min()
    t_in = d["demo"].drop_duplicates("encounterId").set_index("encounterId")["t"]
    dh = (first - t_in.reindex(first.index)).dt.total_seconds() / 3600
    mo = t_in.reindex(dh.index).dt.month
    return {"first vitals minus inTime, hours": dh.describe().round(2).to_frame("value"),
            "rounded to the hour, most common": dh.round().value_counts().head(8).to_frame("encounters"),
            "May to September": dh[mo.between(5, 9)].round().value_counts().head(4).to_frame("encounters"),
            "November to February": dh[(mo >= 11) | (mo <= 2)].round().value_counts().head(4).to_frame("encounters")}


def medication_versions(smh_dir):
    """Does medications_v2 equal medications plus medications_furosemide? Row counts, and the share of v2 records
    (encounter, time, drug, dose) that appear in the other two."""
    smh_dir = _dir(smh_dir)
    tables = {}
    for f in ["ai_picu_medications.csv", "ai_picu_medications_furosemide.csv", "ai_picu_medications_v2.csv"]:
        df, _ = I.read(smh_dir / f)
        df = df.rename(columns={"encounterID": "enc"})
        df["t"] = I.parse_dates(df["utcChartTime"])[0]
        tables[f] = df[["enc", "t", "Drug_terse", "Dosage_verbose"]].astype(str)
    a, b, v2 = tables.values()
    union = pd.concat([a, b]).drop_duplicates()
    hit = v2.drop_duplicates().merge(union, how="left", indicator=True)["_merge"].eq("both").mean()
    return pd.DataFrame({"value": [len(a), len(b), len(v2), len(a) + len(b), round(hit, 4)]},
                        index=["rows: medications", "rows: furosemide", "rows: v2", "medications + furosemide",
                               "share of v2 records found in medications or furosemide"])


def drug_coverage_by_year(smh_dir, manifest, files=DRUG_FILES):
    """Share of the eligible encounters in `manifest` (smh_manifest output) with at least one row in each drug table,
    by admission year. See diagnostics.coverage_by_year."""
    keys = {}
    for f in files:
        df, _ = I.read(_dir(smh_dir) / f, usecols=lambda c: c.lower() == "encounterid")
        keys[f.replace("ai_picu_", "").replace(".csv", "")] = set(df.iloc[:, 0])
    return D.coverage_by_year(manifest, keys, key_col="encounterId")