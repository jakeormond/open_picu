"""Step 2 diagnostics for RBH: how the IDs link, which PICANet file is right, what the times mean.

Shared helpers (show, write_report, compare_keys, coverage_by_year) are in diagnostics.py.
Counts only: nothing returned or printed is an ID, a date or a row value. Each function answers one
question that the manifest (step 3) relies on, and returns a small table. Notebook: rbh_diagnostics.ipynb.

    import rbh_diagnostics as RD
    d = RD.load(rbh_dir)                         # demographics and the vitals key/time columns, read once
    RD.id_hierarchy(d)                           # patients, admissions, studyIDs: how many of each per the other
    RD.study_id_structure(d)                     # prefix:PATIENT_RK:admission-time-in-SAS-seconds
    RD.empty_studies(d)                          # studyIDs with no timestamped vitals, by prefix and year
    RD.placeholder_rows(d)                       # why: one row with an empty chartTime per such studyID
    RD.picanet_versions(rbh_dir, d)              # new vs old PICANet at stay level (diagnostics.compare_keys)
    RD.picanet_old_vs_new(rbh_dir, d)            # could the old PICANet file be combined with the new one?
    RD.prefix_twins(rbh_dir)                     # NIC/NND copies of the same stay, per file
    RD.sedation_twins(rbh_dir)                   # how alike the two copies of a stay are in sedation
    RD.encounter_keys(rbh_dir)                   # the encounterId in the drug tables: is it a stay key?
    RD.vitals_times(d)                           # intv_hr, LOS and ward times against each other
    RD.multi_study_admissions(d)                 # admissions with more than one studyID
    RD.drug_coverage_by_year(rbh_dir, manifest)  # share of eligible stays with drug rows, by admission year
    RD.drug_by_year(rbh_dir, manifest)           # which drugs, per year, in one drug table
    RD.rows_by_month(rbh_dir, file)              # the month a table changes
"""
from pathlib import Path

import pandas as pd

import diagnostics as D
import inventory as I
import manifest as M

DEMO = "ai_picu_demographics.csv"
PIC_NEW, PIC_OLD = "ai_picu_piccanet.csv", "ai_picu_piccanet_old.csv"
DRUG_FILES = ["ai_picu_infusion.csv", "ai_picu_meds.csv", "ai_picu_sedation.csv", "ai_picu_sedation_old.csv"]
VITALS_COLS = ["studyID", "PAS_AD_RK", "chartTime", "WARD_IN_dttm", "WARD_OUT_dttm", "intv_hr", "LOS",
               "clinicalUnit"]


def _dir(rbh_dir):
    return Path(rbh_dir).expanduser()


def _prefix(s):
    return s.astype(str).str.split(":").str[0]


def _stay(s):
    """studyID -> 'PATIENT_RK:admission seconds' (prefix removed). Same as manifest.rbh_stay_key."""
    return M.rbh_stay_key(s)


def _years(keys):
    """Admission year from the stay key's last part (SAS seconds since 1960-01-01)."""
    secs = pd.Series([int(k.split(":")[1]) for k in keys], dtype="int64")
    return (pd.Timestamp("1960-01-01") + pd.to_timedelta(secs, unit="s")).dt.year


def load(rbh_dir):
    """Read demographics and the key and time columns of vitals once. Dates are parsed."""
    rbh_dir = _dir(rbh_dir)
    demo, _ = I.read(rbh_dir / DEMO)
    demo["adm"] = I.parse_dates(demo["PICUadm_dttm"])[0]
    v, _ = I.read(rbh_dir / "ai_picu_vitals.csv", usecols=VITALS_COLS)
    for c in ["chartTime", "WARD_IN_dttm", "WARD_OUT_dttm"]:
        v[c] = I.parse_dates(v[c])[0]
    return {"dir": rbh_dir, "demo": demo, "vitals": v}


# ------------------------------------------------------------------ 1. IDs
def id_hierarchy(d):
    """How many studyIDs per hospital admission (PAS_AD_RK), per patient, and rows repeated per studyID."""
    demo = d["demo"]
    per_adm = demo.groupby("PAS_AD_RK")["studyID"].nunique().value_counts().sort_index()
    per_pat = demo.groupby("PATIENT_RK")["studyID"].nunique().describe()
    dup = demo[demo.duplicated("studyID", keep=False)]
    return {"studyIDs per admission (PAS_AD_RK): number of admissions": per_adm.rename_axis("studyIDs").to_frame("admissions"),
            "studyIDs per patient": per_pat.round(2).to_frame("value"),
            "rows sharing a studyID": pd.DataFrame({"rows": [len(dup)], "studyIDs": [dup["studyID"].nunique()]})}


def study_id_structure(d):
    """studyID = prefix : PATIENT_RK : admission time in SAS seconds. Checks each claim, counts only."""
    demo = d["demo"]
    parts = demo["studyID"].str.split(":", expand=True)
    mid, last = parts[1].astype("int64"), parts[2].astype("int64")
    ref = (demo["adm"] - pd.Timestamp("1960-01-01")).dt.total_seconds()
    return {"prefixes": parts[0].value_counts().rename_axis("prefix").to_frame("studyIDs"),
            "checks": pd.DataFrame({
                "share of rows": [(mid == demo["PATIENT_RK"]).mean(), (mid == demo["PAS_AD_RK"]).mean(),
                                  ((last - ref).abs() == 0).mean()]},
                index=["middle part equals PATIENT_RK", "middle part equals PAS_AD_RK",
                       "last part equals PICUadm_dttm in SAS seconds"]).round(3)}


def empty_studies(d):
    """StudyIDs with no timestamped vitals row: by prefix and by admission year."""
    demo, v = d["demo"].drop_duplicates("studyID").copy(), d["vitals"]
    n = v.groupby("studyID")["chartTime"].count()
    demo["empty"] = demo["studyID"].map(n).fillna(0).eq(0)
    demo["prefix"] = _prefix(demo["studyID"])
    demo["year"] = demo["adm"].dt.year
    return {"by prefix": demo.groupby("prefix")["empty"].agg(empty="sum", studyIDs="size"),
            "by admission year": pd.crosstab(demo["year"], demo["empty"], colnames=["empty"])}


def placeholder_rows(d):
    """Why there are 1990s ward-in dates in the clinical tables: a studyID with no measurement appears as
    a single row with a ward-in time and an empty chartTime (the extract starts from demographics).
    Checks that the rows with an empty chartTime are exactly those studyIDs."""
    v = d["vitals"]
    nulls = v[v["chartTime"].isna()]
    has_any = v.groupby("studyID")["chartTime"].count()
    only_null = (has_any == 0).sum()
    return pd.DataFrame({"count": [len(v), len(nulls), int(nulls["studyID"].nunique()), int(only_null),
                                   int((nulls.groupby("studyID").size() == 1).sum())]},
                        index=["vitals rows", "rows with an empty chartTime", "studyIDs with such a row",
                               "studyIDs with no chartTime at all", "of those with an empty row: exactly one row"])


# ------------------------------------------------------------------ 2. PICANet versions and twins
def picanet_versions(rbh_dir, d):
    """New against old PICANet at stay level (prefix removed), with the admission years of the stays in one only."""
    rbh_dir = _dir(rbh_dir)
    new = set(_stay(I.read(rbh_dir / PIC_NEW, usecols=["studyID"])[0]["studyID"]))
    old = set(_stay(I.read(rbh_dir / PIC_OLD, usecols=["studyID"])[0]["studyID"]))
    return D.compare_keys(new, old, ("new", "old"), others={"in demographics": set(_stay(d["demo"]["studyID"]))},
                          year_of=_years)


PIC_COLS = ["AgeDays", "Gender", "Weight", "AdDateTime", "UnitDisDateTime", "LOSHours", "PrimaryDiagnosisGroup",
            "PIM3", "VentilationStatus", "InTubeDays", "TrachDays", "EventID"]


def picanet_old_vs_new(rbh_dir, d):
    """Could the old PICANet file be combined with the new one? Two questions, counts only.
    1. For stays in both files: per column, how often both are filled and equal, both filled and different, or
       only one is filled (a stay is the studyID with the prefix removed; its rows are combined, first filled value).
    2. For stays in the old file only (and in demographics): how many carry any PICANet content at all, against
       the same measure for stays in both. An empty row is a stay that PICANet lists but has no audit data for."""
    rbh_dir = _dir(rbh_dir)

    def stays(f):
        x, _ = I.read(rbh_dir / f)
        x["stay"] = _stay(x["studyID"])
        return x.groupby("stay")[PIC_COLS].first()
    new, old = stays(PIC_NEW), stays(PIC_OLD)
    both = new.index.intersection(old.index)
    rows = []
    for c in PIC_COLS:
        a, b = new.loc[both, c], old.loc[both, c]
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            same = (a - b).abs() < 1e-6
        else:
            same = a.astype(str) == b.astype(str)
        both_f = a.notna() & b.notna()
        rows.append({"column": c, "both filled, equal": int((both_f & same).sum()),
                     "both filled, different": int((both_f & ~same).sum()),
                     "only new filled": int((a.notna() & b.isna()).sum()),
                     "only old filled": int((a.isna() & b.notna()).sum())})
    coh = set(_stay(d["demo"]["studyID"]))
    old_only = old.index.difference(new.index).intersection(list(coh))
    has = old[PIC_COLS].notna().any(axis=1)
    content = pd.DataFrame({"stays": [len(both), len(old_only)],
                            "with any PICANet content": [int(has.loc[both].sum()), int(has.loc[old_only].sum())],
                            "with PIM3": [int(old.loc[both, "PIM3"].notna().sum()),
                                          int(old.loc[old_only, "PIM3"].notna().sum())]},
                           index=["in both files (old file's values)", "old only, in demographics"])
    return {"agreement on stays in both files": pd.DataFrame(rows), "content of old-only stays": content}


def prefix_twins(rbh_dir):
    """Per file: studyIDs, distinct stays, and stays that appear under both prefixes (NIC and NND)."""
    rbh_dir, rows = _dir(rbh_dir), []
    for f in sorted(rbh_dir.glob("*.csv")):
        ids = I.read(f, usecols=lambda c: c.lower() == "studyid")[0]
        if ids.empty:
            continue
        u = ids.iloc[:, 0].dropna().drop_duplicates()
        p = u.str.split(":", expand=True)
        stay = p[1] + ":" + p[2]
        rows.append({"file": f.name, "studyIDs": len(u), "stays": stay.nunique(),
                     "stays under both prefixes": int((p.groupby(stay)[0].nunique() == 2).sum())})
    return pd.DataFrame(rows)


def sedation_twins(rbh_dir):
    """For stays present under both prefixes in sedation.csv: do the two copies hold the same records?"""
    sed = I.read(_dir(rbh_dir) / "ai_picu_sedation.csv",
                 usecols=lambda c: c.lower() in ("studyid", "charttime", "drug", "dose"))[0]
    sed.columns = sed.columns.str.lower()
    p = sed["studyid"].str.split(":", expand=True)
    sed["prefix"], sed["stay"] = p[0], p[1] + ":" + p[2]
    both = sed.groupby("stay")["prefix"].nunique()
    sb = sed[sed["stay"].isin(both[both == 2].index)]
    if sb.empty:
        return pd.DataFrame({"count": [0]}, index=["stays under both prefixes"])
    n = sb.groupby(["stay", "prefix"]).size().unstack()
    cols = ["stay", "charttime", "drug", "dose"]
    a = sb.loc[sb.prefix == "NIC", cols].drop_duplicates()
    b = sb.loc[sb.prefix == "NND", cols].drop_duplicates()
    both_n = len(a.merge(b, on=cols))
    return pd.DataFrame({"count": [len(n), round((n["NIC"] == n["NND"]).mean(), 3), both_n, len(a), len(b)]},
                        index=["stays under both prefixes", "share with equal row counts in both copies",
                               "records in both copies", "distinct records, NIC copy",
                               "distinct records, NND copy"])


def picanet_vs_picu_rows(d, rbh_dir):
    """Stays with any vitals row in the PICU unit against membership of the new PICANet file."""
    v = d["vitals"]
    has_picu = v["clinicalUnit"].eq("RBH-PICU").groupby(v["studyID"]).any()
    pn = set(I.read(_dir(rbh_dir) / PIC_NEW, usecols=["studyID"])[0]["studyID"])
    return pd.crosstab(has_picu.rename("any PICU row"), has_picu.index.isin(pn),
                       colnames=["in new PICANet"])


def encounter_keys(rbh_dir):
    """The encounterId of the drug tables against PAS_AD_RK and studyID: is it a stay key?"""
    rows = []
    for f in ["infusion", "meds", "sedation"]:
        x = I.read(_dir(rbh_dir) / f"ai_picu_{f}.csv", usecols=["studyID", "PAS_AD_RK", "encounterId"])[0].drop_duplicates()
        rows.append({"table": f,
                     "encounterIds per PAS_AD_RK (max)": x.groupby("PAS_AD_RK")["encounterId"].nunique().max(),
                     "PAS_AD_RK per encounterId (max)": x.groupby("encounterId")["PAS_AD_RK"].nunique().max(),
                     "studyIDs per encounterId (max)": x.groupby("encounterId")["studyID"].nunique().max()})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ 3. Times
def vitals_times(d):
    """intv_hr and LOS against the ward times; rows with an inverted ward stay; vitals rows by year."""
    v = d["vitals"]
    hrs = (v["chartTime"] - v["WARD_IN_dttm"]).dt.total_seconds() / 3600
    stay = v.drop_duplicates("studyID")
    los_h = (stay["WARD_OUT_dttm"] - stay["WARD_IN_dttm"]).dt.total_seconds() / 3600
    return {"intv_hr minus hours since WARD_IN": (v["intv_hr"] - hrs).describe().round(3).to_frame("value"),
            "LOS divided by (WARD_OUT - WARD_IN) in hours": (stay["LOS"] / los_h).describe().round(3).to_frame("value"),
            "stays with WARD_OUT before WARD_IN": pd.DataFrame({"count": [int((los_h < 0).sum())]}),
            "vitals rows by year": v["chartTime"].dt.year.value_counts().sort_index().to_frame("rows")}


def multi_study_admissions(d):
    """Hospital admissions (PAS_AD_RK) with more than one studyID in vitals: how their times relate."""
    v = d["vitals"]
    g = v.groupby("PAS_AD_RK").agg(n_study=("studyID", "nunique"), n_in=("WARD_IN_dttm", "nunique"),
                                   n_out=("WARD_OUT_dttm", "nunique"))
    multi = g[g.n_study > 1]
    s = (v.groupby(["PAS_AD_RK", "studyID"])["chartTime"].agg(["min", "max"]).reset_index()
         .sort_values(["PAS_AD_RK", "min"]))
    s["prev_max"] = s.groupby("PAS_AD_RK")["max"].shift()
    gap = (s["min"] - s["prev_max"]).dt.total_seconds() / 3600
    return {"admissions with more than one studyID": pd.DataFrame({"count": [len(multi)]}),
            "distinct WARD_IN per such admission": multi["n_in"].value_counts().sort_index().to_frame("admissions"),
            "studyIDs starting before the previous one ended": pd.DataFrame({"count": [int((s["min"] < s["prev_max"]).sum())]}),
            "gap to previous studyID, hours": gap.describe().round(1).to_frame("value")}


# ------------------------------------------------------------------ 4. New: do the drug tables thin out after 2018?
def drug_coverage_by_year(rbh_dir, manifest, files=DRUG_FILES):
    """Share of the eligible stays in `manifest` (rbh_manifest output) with at least one row in each drug table,
    by admission year. See diagnostics.coverage_by_year."""
    keys = {f.replace("ai_picu_", "").replace(".csv", ""):
            set(_stay(I.read(_dir(rbh_dir) / f, usecols=["studyID"])[0]["studyID"].drop_duplicates()))
            for f in files}
    return D.coverage_by_year(manifest, keys)


def drug_by_year(rbh_dir, manifest, file="ai_picu_infusion.csv"):
    """Eligible stays with at least one row of each drug in `file`, by admission year (drug names are labels,
    not patient data). Shows which drugs vanish when a table thins out."""
    df = I.read(_dir(rbh_dir) / file, usecols=["studyID", "Drug"])[0].drop_duplicates()
    df["stay_key"] = _stay(df["studyID"])
    df = df.merge(manifest[["stay_key", "year"]], on="stay_key").drop_duplicates(["stay_key", "Drug"])
    return df.groupby(["year", "Drug"]).size().unstack(fill_value=0)


def rows_by_month(rbh_dir, file="ai_picu_infusion.csv", start="2018-06", end="2019-12"):
    """Rows per calendar month of chartTime between start and end: finds the month a table changes."""
    t = I.parse_dates(I.read(_dir(rbh_dir) / file, usecols=["chartTime"])[0]["chartTime"])[0].dropna()
    return t.dt.to_period("M").value_counts().sort_index().loc[start:end].to_frame("rows")