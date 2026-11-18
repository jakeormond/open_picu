"""Stay-level (static) tables: one row per stay, one schema across sites.

Step 1 (this file so far): describe the columns of the assembled static tables, so the column
mapping between sites is written from what is really there. Counts only; category counts under
10 are shown as '<10'.

Notebook use:
    import static as S
    S.describe_columns(out_dir / "RBH" / "ai_picu_piccanet.parquet")
"""
from pathlib import Path

import pandas as pd

import inventory as I

SMALL = 10
MAX_CATS = 8


def _cats(s):
    vc = s.value_counts(dropna=True)
    return "; ".join(f"{k}: {v if v >= SMALL else '<10'}" for k, v in vc.items())


def describe_columns(path):
    """One line per column: non-null %, distinct values, value shape, and categories if few."""
    df = pd.read_parquet(path)
    print(f"{Path(path).name}: {len(df):,} rows, {df.shape[1]} columns")
    rows = []
    for c in df.columns:
        s = df[c]
        n = int(s.nunique(dropna=True))
        shape = I.shapes_of(s).value_counts().head(1)
        detail = _cats(s) if 0 < n <= MAX_CATS else (f"shape {shape.index[0]}" if len(shape) else "")
        rows.append({"column": c, "non-null %": round(100 * s.notna().mean(), 1), "distinct": n, "detail": detail})
    print(I.df_text(pd.DataFrame(rows), index=False))
    print()


# ======================================================================================
# Step 2: the stay-level table. One row per stay, one schema for all sites.
#
# Rules (agreed 2026-11-17):
#   - PICANet fields first, demographics only as a fallback for fields PICANet lacks.
#   - Weight: PICANet weight if valid, else the median of the stay's valid demographics weights
#     (GOSH: weight_picanet, then weight_epr, then AdmWeight). Valid = 0.3 to 200 kg, so the 999
#     placeholder becomes missing. weight_source records which source was used.
#   - Length of stay (hours): PICANet where present, else the outcomes table. los_source records it.
#   - t0 = the hospital's recorded PICU admission: RBH demographics PICUadm_dttm, SMH inTime
#     (identical to PICANet AdDateTime), GOSH PICANet AdDateTime.
#   - died: RBH picuMortality, SMH isDeceased (outcomes tables), GOSH UnitDisStatusDescription.
#   - Stays with two PICANet rows (after exact duplicates are gone) are excluded, since the rows
#     disagree on admission or discharge.
#   - Ethnicity: PICANet only. The demographics vocabularies differ and are kept as x_ columns.
#   - Free text (SecDescriptions, EthnicOther, primaryDiagnosis) is not carried into this table.
#   - Site-specific fields keep an x_ prefix; they are not part of the pooled schema.
# ======================================================================================
import numpy as np

MISSING = {"", "NA", "NULL", "nan", "NaN", "None"}
WEIGHT_RANGE = (0.3, 200.0)
COMMON = ["site", "stay_key", "patient_id", "t0", "year", "age_months", "sex", "ethnicity", "ethnicity_source",
          "weight_kg", "weight_source", "los_hours", "los_source", "died", "diagnosis_group",
          "pim", "pim_version"]


def _clean(s):
    s = s.astype("string").str.strip()
    return s.mask(s.isin(MISSING))


def _num(s):
    return pd.to_numeric(_clean(s), errors="coerce")


def _dt(s):
    return I.parse_dates(_clean(s))[0].astype("datetime64[ns]")


def _weight(s):
    w = _num(s)
    return w.where((w >= WEIGHT_RANGE[0]) & (w <= WEIGHT_RANGE[1]))


def _coalesce(cands, index):
    """cands: [(name, Series aligned to index)]. First non-missing value and where it came from."""
    val = pd.Series(np.nan, index=index, dtype="float64")
    src = pd.Series(pd.NA, index=index, dtype="string")
    for name, s in cands:
        s = pd.Series(s, index=index)
        m = val.isna() & s.notna()
        val[m] = s[m].astype("float64")
        src[m] = name
    return val, src


def _sex_from_code(s):
    n = _num(s)
    return n.map({1: "Male", 2: "Female"}).where(n.isna() | n.isin([1, 2]), "Other").astype("string")


def _sex_from_text(s):
    t = _clean(s).str.casefold()
    return t.map({"male": "Male", "female": "Female"}).where(t.isna() | t.isin(["male", "female"]), "Other").astype("string")


# RBH demographics use a different (census-style) ethnicity vocabulary from PICANet. It is only used
# to fill stays where PICANet says Not stated / Unknown or has no record. Labels not listed here are
# left unmapped (counted in the log).
RBH_ETHNICITY_MAP = {
    "White British": "White British", "White Irish": "White Irish", "White Any other": "White other",
    "Mixed White and Black Caribbean": "Mixed White and Black Caribbean",
    "Mixed White and Black African": "Mixed White and Black African",
    "Mixed White and Asian": "Mixed White and Asian", "Mixed Any other": "Mixed other",
    "Asian or Asian British Indian": "Asian Indian", "Asian or Asian British Pakistani": "Asian Pakistani",
    "Asian or Asian British Bangladeshi": "Asian Bangladeshi", "Asian or Asian British Any other": "Asian other",
    "Black or Black British Caribbean": "Black Caribbean", "Black or Black British African": "Black African",
    "Black or Black British Any other": "Black other", "Other Ethnic Chinese": "Chinese",
    "Other Ethnic Any other": "Other",
}
NOT_STATED = {"Not stated", "Unknown"}


def _eth_picanet(s):
    """PICANet ethnicity with 'Unknown' folded into 'Not stated'; missing stays missing."""
    t = _clean(s)
    return t.mask(t.isin(NOT_STATED), "Not stated")


def _first_notna(*series):
    out = series[0].copy()
    for s in series[1:]:
        out = out.where(out.notna(), s)
    return out


def _by_stay(df, key):
    return df.drop_duplicates(key).set_index(key)


def _median_weight(df, key, col):
    w = _weight(df[col])
    return w.groupby(df[key]).median()


def build_rbh(assembled_dir):
    a = Path(assembled_dir) / "RBH"
    dem, out, pic = (pd.read_parquet(a / f"ai_picu_{n}.parquet") for n in ("demographics", "outcomes", "piccanet"))
    n_pic = pic.groupby("stay_key").size()
    conflict = n_pic[n_pic > 1].index
    stays = pd.Index(dem["stay_key"].unique()).difference(conflict)
    d, o, p = (_by_stay(x, "stay_key").reindex(stays) for x in (dem, out, pic))
    wdemo = _median_weight(dem, "stay_key", "Weight_kg").reindex(stays)
    df = pd.DataFrame(index=stays)
    df["site"] = "RBH"
    df["patient_id"] = d["PATIENT_RK"]
    df["t0"] = _dt(d["PICUadm_dttm"])
    df["age_months"] = _first_notna(_num(p["AgeMonths"]), _num(d["Age_mth"]))
    df["sex"] = _first_notna(_sex_from_code(p["Gender"]), _sex_from_code(d["Gender"]))
    eth_p = _eth_picanet(p["EthnicDescription"])
    dem_raw = _clean(d["Ethnicity"])
    eth_d = dem_raw.map(RBH_ETHNICITY_MAP).astype("string")
    use_d = (eth_p.isna() | (eth_p == "Not stated")) & eth_d.notna()
    df["ethnicity"] = eth_p.mask(use_d, eth_d)
    df["ethnicity"] = df["ethnicity"].where(df["ethnicity"].notna() | ~dem_raw.eq("Not stated"), "Not stated")
    df["ethnicity_source"] = pd.Series(np.where(use_d, "demographics", np.where(eth_p.notna(), "picanet", None)), index=stays, dtype="string")
    unmapped = dem_raw[dem_raw.notna() & ~dem_raw.isin(list(RBH_ETHNICITY_MAP) + ["Not stated"])]
    print(f"RBH ethnicity: filled from demographics for {int(use_d.sum()):,} stays; "
          f"demographics labels not in the map: {int(unmapped.nunique())} ({int(len(unmapped))} stays)")
    df["weight_kg"], df["weight_source"] = _coalesce([("picanet", _weight(p["Weight"])), ("demographics_median", wdemo)], stays)
    df["los_hours"], df["los_source"] = _coalesce([("picanet", _num(p["LOSHours"])), ("outcomes", _num(o["picuLOS"]))], stays)
    df["died"] = _num(o["picuMortality"])
    df["diagnosis_group"] = _clean(p["PrimaryDiagnosisGroup"])
    df["pim"], df["pim_version"] = _num(p["PIM3"]), "PIM3"
    df["x_ventilation_status"] = _clean(p["VentilationStatus"])
    df["x_intube_days"], df["x_trach_days"] = _num(p["InTubeDays"]), _num(p["TrachDays"])
    df["x_unplanned_extubation"] = _num(p["UnplannedExtubation"])
    df["x_ethnicity_demographics"] = _clean(d["Ethnicity"])
    return _finish(df, "RBH", len(conflict))


def build_smh(assembled_dir):
    a = Path(assembled_dir) / "SMH"
    dem, out, pic = (pd.read_parquet(a / f"ai_picu_{n}.parquet") for n in ("demographics", "outcomes", "piccanet"))
    n_pic = pic.groupby("encounterId").size()
    conflict = n_pic[n_pic > 1].index
    stays = pd.Index(dem["encounterId"].unique()).difference(conflict)
    d, o, p = (_by_stay(x, "encounterId").reindex(stays) for x in (dem, out, pic))
    wdemo = _median_weight(dem, "encounterId", "Weight").reindex(stays)
    df = pd.DataFrame(index=stays)
    df["site"] = "SMH"
    df["patient_id"] = d["UniquePtID"]
    df["t0"] = _first_notna(_dt(p["AdDateTime"]), _dt(d["inTime"]))
    df["age_months"] = _first_notna(_num(p["Age"]), _num(d["Age"]))
    df["sex"] = _first_notna(_sex_from_text(p["SexDescription"]), _sex_from_text(p["gender"]), _sex_from_text(d["gender"]))
    df["ethnicity"] = _eth_picanet(p["EthnicDescription"])
    df["ethnicity_source"] = pd.Series(np.where(df["ethnicity"].notna(), "picanet", None), index=stays, dtype="string")
    df["weight_kg"], df["weight_source"] = _coalesce([("picanet", _weight(p["Weight"])), ("demographics_median", wdemo)], stays)
    df["los_hours"], df["los_source"] = _coalesce([("picanet", _num(p["LOSHours"])), ("outcomes", _num(o["LOS"]))], stays)
    df["died"] = _num(o["isDeceased"])
    df["diagnosis_group"] = _clean(p["PrimaryDiagnosisGroup"])
    df["pim"], df["pim_version"] = _num(p["PIM3"]), "PIM3"
    df["x_intube_days"], df["x_trach_days"] = _num(p["InTubeDays"]), _num(p["TrachDays"])
    df["x_sepsis_diagnosis"] = _num(dem.groupby("encounterId")["SepsisDiagnosis"].max().reindex(stays))
    df["x_ethnicity_demographics"] = _clean(d["ethnicGroup"])
    return _finish(df, "SMH", len(conflict))


def build_gosh(assembled_dir):
    e = pd.read_parquet(Path(assembled_dir) / "GOSH" / "PICANet_eprweights.parquet")
    e = e.set_index("stay_id")
    stays = e.index
    df = pd.DataFrame(index=stays)
    df["site"] = "GOSH"
    df["patient_id"] = e["project_id"]
    df["t0"] = _dt(e["AdDateTime"])
    df["age_months"] = _num(e["adm_age_m"])
    df["sex"] = _sex_from_text(e["SexDescription"])
    df["ethnicity"] = _eth_picanet(e["EthnicDescription"])
    df["ethnicity_source"] = pd.Series(np.where(df["ethnicity"].notna(), "picanet", None), index=stays, dtype="string")
    df["weight_kg"], df["weight_source"] = _coalesce(
        [("picanet", _weight(e["weight_picanet"])), ("epr", _weight(e["weight_epr"])), ("admweight", _weight(e["AdmWeight"]))], stays)
    df["los_hours"] = _num(e["los"]) * 24
    df["los_source"] = pd.Series(np.where(df["los_hours"].notna(), "picanet", None), index=stays, dtype="string")
    status = _clean(e["UnitDisStatusDescription"]).str.casefold()
    df["died"] = status.map({"dead": 1, "alive": 0}).astype("float64")
    df["diagnosis_group"] = _clean(e["PrimaryDiagnosisGroup"])
    df["pim"], df["pim_version"] = _num(e["PIM"]), "unspecified (column PIM)"
    df["x_gestation"] = _num(e["Gest"])
    df["x_admission_type"] = _clean(e["AdmType"])
    for c in ["RespiratorySupport", "CardiovascularSupport", "RenalSupport", "NeurologySupport",
              "MetabolicSupport", "OtherSupport"]:
        df[f"x_{c}"] = _num(e[c])
    df["x_all_organ_support"] = _num(e["All.organ.support"])
    df["x_organ_support_free_days_30"] = _num(e["Organ.support.free.days.at.day.30"])
    return _finish(df, "GOSH", 0)


def _finish(df, site, n_conflict):
    df = df.copy()
    df["year"] = df["t0"].dt.year
    df["stay_key"] = df.index
    df = df.reset_index(drop=True)
    first = [c for c in COMMON if c in df.columns]
    df = df[first + [c for c in df.columns if c not in first]]
    print(f"{site}: {len(df):,} stays; excluded for conflicting PICANet rows: {n_conflict}")
    for c in ("weight_source", "los_source"):
        print(f"  {c}: " + "; ".join(f"{k}: {v}" for k, v in df[c].value_counts(dropna=False).items()))
    print(f"  died: " + "; ".join(f"{k:g}: {v}" for k, v in df['died'].value_counts().sort_index().items())
          + f"; missing {int(df['died'].isna().sum())}")
    return df


def build_all(assembled_dir):
    """Static tables for the three sites: {'RBH': df, 'SMH': df, 'GOSH': df}."""
    return {"RBH": build_rbh(assembled_dir), "SMH": build_smh(assembled_dir), "GOSH": build_gosh(assembled_dir)}


def coverage(static):
    """Non-null % of each pooled column by site, and the number of distinct values. Counts only."""
    rows = []
    for c in COMMON[2:]:
        r = {"column": c}
        for site, df in static.items():
            r[f"{site} non-null %"] = round(100 * df[c].notna().mean(), 1)
            r[f"{site} distinct"] = int(df[c].nunique())
        rows.append(r)
    print(I.df_text(pd.DataFrame(rows), index=False))
    xs = {site: [c for c in df.columns if c.startswith("x_")] for site, df in static.items()}
    for site, cols in xs.items():
        print(f"\nsite-specific columns, {site}: {cols}")


def pool(static):
    """The pooled candidate: common columns of all sites stacked. Row-level; keep in derived/."""
    return pd.concat([df[COMMON] for df in static.values()], ignore_index=True)


def category_table(static, col):
    """Category counts of one column, sites side by side. Counts under 10 are shown as '<10'."""
    parts = {site: df[col].value_counts(dropna=False) for site, df in static.items()}
    t = pd.concat(parts, axis=1).fillna(0).astype(int)
    t.index = t.index.map(lambda v: "(missing)" if pd.isna(v) else str(v))
    t = t.sort_values(t.columns.tolist(), ascending=False)
    show = t.map(lambda v: "-" if v == 0 else ("<10" if v < SMALL else str(v)))
    print(I.df_text(show, index=True))
    print(f"categories: " + ", ".join(f"{s} {int((t[s] > 0).sum())}" for s in t.columns))
    return t


def pim_by_year(static):
    """PIM distribution by site and admission year (5th percentile, median, 95th percentile; counts).
    A change of PIM version at a site would show as a step in the percentiles in one year."""
    for site, df in static.items():
        g = df.dropna(subset=["pim"]).groupby("year")["pim"]
        t = pd.DataFrame({"n": g.size(), "p5": g.quantile(.05).round(4), "median": g.median().round(4),
                          "p95": g.quantile(.95).round(4)})
        print(f"{site} (version recorded: {df['pim_version'].iloc[0]})")
        print(I.df_text(t, index=True))
        print()