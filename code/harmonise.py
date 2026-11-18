"""Harmonise and pool (step 8): the concept map -> one long table per site and concept group, in one set of units, on one clock.

Output (row-level, so only ever in derived/harmonised/, git-ignored): one parquet per site and group with the columns
    site, stay_key, concept, hour, value, value_text, flag, source
  hour        hours since the stay's t0 (negative = before admission), true elapsed time (daylight saving handled)
  value       numeric value in the harmonised unit (NaN for text concepts)
  value_text  the recorded text for text concepts (vent mode, rhythm, capillary refill, airway device, pupils, AVPU, sample type)
  flag        '' or what was done to the row: 'x10' (g/dL to g/L), 'x100' (fraction to percent), 'derived' (calculated, not recorded)
  source      which source of the concept the row came from (index into CONCEPTS[concept][site]); several sources only differ
              in meaning for a few concepts (see the concept note)

Rules (all from DATA_ISSUES.md):
  - Cohort: stays over 6 hours (static los_hours > 6) with a t0. Applied here, so the pooled data has one definition.
  - Clock: SMH chart times are UTC, RBH and GOSH are London local, t0 is London local at all three sites. Everything goes to UTC
    before subtracting. The one ambiguous hour a year (clocks back) cannot be placed and its rows are dropped and counted.
  - Haemoglobin values below 30 are g/dL and are multiplied by 10 (g/L is the pooled unit). Haematocrit values up to 1.5 are
    fractions and are multiplied by 100 (percent).
  - Zero is a placeholder, not a measurement, for RBH PIP, mean airway pressure and set rate, and GOSH monitor RR and bilirubin: set missing.
  - GOSH diastolic pressure equal to the systolic pressure of the same time is a copy: set missing.
  - GOSH base excess lost its sign at source: it is replaced by the Van Slyke value from pH and bicarbonate of the same sample, flagged
    'derived'. RBH and SMH keep their recorded values.
  - Tidal volume: the unit text is stripped ("9 ml" -> 9).
  - I:E ratio is x of "1:x": RBH parses the text "a:b" as b / a; SMH takes the larger of the two rows at a time (the pair is 1 and x;
    a single row counts only if above 1); GOSH uses the expiratory part.
  - Text concepts are carried as recorded in value_text, not harmonised (vocabularies differ by site).
Not done here: fluids (own definitions, harmonise_fluids) and drugs (presence only, kept in the availability step).
Counts only leave the SDE: the report returned by harmonise_all has no values.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import concepts as C
import static as ST

TZ = "Europe/London"
MIN_HOURS = 6.0

TEXT = {"vent_mode", "cardiac_rhythm", "airway_device", "pupil_reaction", "avpu", "bg_sample_type", "crt"}
ZERO_MISSING = {("RBH", "pip"), ("RBH", "mean_airway_pressure"), ("RBH", "rr_set"), ("GOSH", "resp_rate_monitor"), ("GOSH", "bilirubin")}
DIA_OF = {"nibp_dia": "nibp_sys", "abp_dia": "abp_sys"}          # GOSH: diastolic copied from systolic
HB = {"bg_hb", "haemoglobin"}
HCT = {"bg_hct"}
SKIP_GROUPS = {"drugs", "fluids"}


# ------------------------------------------------------------------ cohort and clock
def cohort(static, min_hours=MIN_HOURS):
    """Stays over `min_hours` with a t0: columns site, stay_key, t0 (London local) and t0_utc."""
    s = static[(static["los_hours"] > min_hours) & static["t0"].notna()][["site", "stay_key", "t0"]].copy()
    s["stay_key"] = s["stay_key"].astype(str)
    s["t0_utc"] = s["t0"].dt.tz_localize(TZ, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    return s.dropna(subset=["t0_utc"]).reset_index(drop=True)


def to_hours(t_text, site, t0_utc):
    """Hours since t0 for text times: parsed, put on UTC (SMH is UTC already, the others London local), minus t0_utc (a Series aligned
    to t_text). Unparseable or ambiguous times give NaN."""
    t = ST._dt(t_text)
    if site == "SMH":
        tu = t.dt.tz_localize("UTC")
    else:
        tu = t.dt.tz_localize(TZ, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    return (tu - t0_utc).dt.total_seconds() / 3600


# ------------------------------------------------------------------ one concept at one site
def _clean_text(s):
    s = s.astype("string").str.strip()
    return s.mask(s.str.lower().isin(C.MISSING))


def _parse_ie(s):
    """RBH text 'a:b' -> b / a."""
    parts = _clean_text(s).str.split(":", n=1, expand=True)
    if parts.shape[1] < 2:
        return pd.Series(np.nan, index=s.index)
    a, b = (pd.to_numeric(parts[i], errors="coerce") for i in (0, 1))
    return (b / a).where(a > 0)


def _numeric(concept, site, s):
    s = _clean_text(s)
    if concept == "tidal_volume":
        return pd.to_numeric(s.str.extract(r"(-?\d+\.?\d*)")[0], errors="coerce")
    return pd.to_numeric(s, errors="coerce")


def _read_concept(assembled_dir, site, concept, keep, report):
    """All sources of the concept at the site, cohort stays only, with hours and the numeric or text value, before the rules.
    Returns a long frame (stay_key, hour, value, value_text, source)."""
    parts = []
    for i, src in enumerate(C.CONCEPTS[concept][site]):
        df = C._read(assembled_dir, site, src, time=True)
        report["rows_read"] += len(df)
        df["stay"] = df["stay"].astype(str)
        df = df[df["stay"].isin(keep.index)]
        report["rows_in_cohort"] += len(df)
        if concept == "ie_ratio" and site == "SMH":
            v = pd.to_numeric(_clean_text(df["value"]), errors="coerce")
            g = df.assign(v=v).dropna(subset=["v"]).groupby(["stay", "t"], sort=False)["v"].agg(["max", "size"]).reset_index()
            g = g[(g["size"] > 1) | (g["max"] > 1)]
            df = pd.DataFrame({"stay": g["stay"], "t": g["t"], "value": g["max"]})
        df["hour"] = to_hours(df["t"], site, df["stay"].map(keep))
        report["rows_bad_time"] += int(df["hour"].isna().sum())
        df = df.dropna(subset=["hour"])
        if concept in TEXT:
            df["value_text"] = _clean_text(df["value"])
            df["value"] = np.nan
            df = df.dropna(subset=["value_text"])
        elif concept == "ie_ratio" and site == "RBH":
            df["value"] = _parse_ie(df["value"])
            df["value_text"] = pd.NA
        else:
            df["value"] = _numeric(concept, site, df["value"])
            df["value_text"] = pd.NA
        if concept not in TEXT:
            bad = df["value"].isna()
            report["rows_non_numeric"] += int(bad.sum())
            df = df[~bad]
        parts.append(df[["stay", "hour", "value", "value_text"]].assign(source=i))
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["stay", "hour", "value", "value_text", "source"])
    return out.rename(columns={"stay": "stay_key"})


def _paired(assembled_dir, site, other, keep):
    """`other` concept of the same site as a (stay_key, hour, value) frame, for rules that need the same sample."""
    sub = {"rows_read": 0, "rows_in_cohort": 0, "rows_bad_time": 0, "rows_non_numeric": 0}
    df = _read_concept(assembled_dir, site, other, keep, sub)
    return df.dropna(subset=["value"])[["stay_key", "hour", "value"]]


def harmonise_concept(assembled_dir, site, concept, keep, report=None):
    """One concept at one site as a long frame (stay_key, concept, hour, value, value_text, flag, source), rules applied.
    keep: Series stay_key (text) -> t0 in UTC for the cohort stays of the site. report: dict of counters (updated)."""
    rep = report if report is not None else {}
    for k in ("rows_read", "rows_in_cohort", "rows_bad_time", "rows_non_numeric", "rows_set_missing", "rows_converted", "rows_derived", "rows_dup"):
        rep.setdefault(k, 0)
    flag = None                                   # None: flags set row by row below
    if site == "GOSH" and concept == "bg_base_excess":
        ph = _paired(assembled_dir, site, "bg_ph", keep).rename(columns={"value": "ph"})
        hco3 = _paired(assembled_dir, site, "bg_hco3", keep).rename(columns={"value": "hco3"})
        m = ph.merge(hco3, on=["stay_key", "hour"])
        m = m[m["ph"].between(6.5, 7.8) & m["hco3"].between(1, 60)]
        df = m.assign(value=C.derive_base_excess(m["ph"], m["hco3"]), value_text=pd.NA, source=0)[["stay_key", "hour", "value", "value_text", "source"]]
        flag = "derived"
        rep["rows_derived"] += len(df)
    else:
        df = _read_concept(assembled_dir, site, concept, keep, rep)
        if (site, concept) in ZERO_MISSING:
            z = df["value"] == 0
            rep["rows_set_missing"] += int(z.sum())
            df = df[~z]
        if site == "GOSH" and concept in DIA_OF:
            sys_ = _paired(assembled_dir, site, DIA_OF[concept], keep).rename(columns={"value": "sys"}).drop_duplicates(["stay_key", "hour"])
            m = df.merge(sys_, on=["stay_key", "hour"], how="left")
            same = m["value"] == m["sys"]
            rep["rows_set_missing"] += int(same.sum())
            df = df[~same.to_numpy()]
        df = df.assign(flag="")
        if concept in HB:
            low = df["value"] < 30
            df.loc[low, "value"] *= 10
            df.loc[low, "flag"] = "x10"
            rep["rows_converted"] += int(low.sum())
        if concept in HCT:
            frac = df["value"] <= 1.5
            df.loc[frac, "value"] *= 100
            df.loc[frac, "flag"] = "x100"
            rep["rows_converted"] += int(frac.sum())
    if flag is not None:
        df = df.assign(flag=flag)
    df = df.assign(concept=concept)
    n0 = len(df)
    df = df.drop_duplicates(["stay_key", "hour", "value", "value_text", "source"])
    rep["rows_dup"] += n0 - len(df)
    df["hour"] = df["hour"].astype("float32")
    df["value"] = df["value"].astype("float32")
    return df[["stay_key", "concept", "hour", "value", "value_text", "flag", "source"]]


# ------------------------------------------------------------------ all concepts
def harmonise_all(assembled_dir, static, out_dir, concepts=None, sites=C.SITES, groups_skip=SKIP_GROUPS):
    """Write one parquet per site and group to out_dir (derived/harmonised/) and return a counts-only report: per site and concept the
    stays and rows kept, rows read, rows outside the cohort or with a bad time, rows set missing or converted or derived, and the
    percentiles of `hour` (5th, 50th, 95th) as a check on the clock."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    co = cohort(static)
    names = [n for n in C.CONCEPTS if (n in concepts if concepts else C.CONCEPTS[n]["group"] not in groups_skip)]
    rows = []
    for site in sites:
        keep = co[co["site"] == site].set_index("stay_key")["t0_utc"]
        by_group = {}
        for n in names:
            if not C.CONCEPTS[n].get(site):
                continue
            rep = {}
            df = harmonise_concept(assembled_dir, site, n, keep, rep)
            by_group.setdefault(C.CONCEPTS[n]["group"], []).append(df)
            rows.append({"site": site, "concept": n, "cohort_stays": len(keep), "stays": int(df["stay_key"].nunique()), "rows": len(df),
                         **rep, "hour_p5": float(df["hour"].quantile(.05)) if len(df) else np.nan,
                         "hour_median": float(df["hour"].median()) if len(df) else np.nan,
                         "hour_p95": float(df["hour"].quantile(.95)) if len(df) else np.nan})
        for g, parts in by_group.items():
            d = pd.concat(parts, ignore_index=True)
            d.insert(0, "site", site)
            d.to_parquet(out_dir / f"{site}_{g.replace(' ', '_')}.parquet", index=False)
    return pd.DataFrame(rows)


def time_alignment_check(assembled_dir, static, concept="hr", sites=C.SITES):
    """Is the clock right? Per site and season (summer = April to September at t0, winter = November to February): the median hours of the
    first row of `concept` after t0 and the share of stays whose first row is before t0 or more than 24 h after. A time-zone error would
    show as a one-hour difference between summer and winter. Counts and medians only."""
    co = cohort(static)
    out = []
    for site in sites:
        keep = co[co["site"] == site].set_index("stay_key")
        rep = {"rows_read": 0, "rows_in_cohort": 0, "rows_bad_time": 0, "rows_non_numeric": 0}
        df = _read_concept(assembled_dir, site, concept, keep["t0_utc"], rep)
        first = df.groupby("stay_key")["hour"].min()
        m = keep.join(first.rename("first"), how="inner")
        month = m["t0"].dt.month
        for name, mask in (("summer (Apr-Sep)", month.between(4, 9)), ("winter (Nov-Feb)", month.isin([11, 12, 1, 2]))):
            f = m.loc[mask, "first"]
            out.append({"site": site, "season": name, "stays": len(f), "median_first_hour": round(float(f.median()), 2),
                        "p5": round(float(f.quantile(.05)), 2), "p95": round(float(f.quantile(.95)), 2),
                        "pct_before_t0": round(100 * float((f < 0).mean()), 1), "pct_after_24h": round(100 * float((f > 24).mean()), 1)})
    return pd.DataFrame(out)