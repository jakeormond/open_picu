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
  - Window: rows from 24 h before t0 to the end of the stay plus 1 h are kept (stay_window). The end is the recorded length of stay
    (PICANet), and at RBH the later of that and the ward out time, because RBH vitals run past the PICANet length in about 10% of stays and
    RBH labs, blood gas and fluids also hold hospital time before and after the PICU record. The rows removed are counted per concept
    (rows_outside_window); nothing else is removed by the window.
Fluids are in harmonise_fluids (own definitions, below). Drugs are not here (presence only, kept in the availability step).
Counts only leave the SDE: the report returned by harmonise_all has no values.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import concepts as C
import static as ST

TZ = "Europe/London"
MIN_HOURS = 6.0

TEXT = {"vent_mode", "cardiac_rhythm", "airway_device", "pupil_reaction", "avpu", "bg_sample_type", "crt", "ett_route", "ett_cuff"}
# SMH ETT_paed holds size (3.5), depth ('12cm'), route (Oral, Nasal) and cuff (Cuffed, Un-cuffed) in one source: each kind goes to its own concept.
_ETT_OTHER = r"cm\s*$|^(oral|nasal|cuffed|un-cuffed)$"
VALUE_KEEP = {("SMH", "ett_depth"): r"^\d+(\.\d+)?\s*cm$", ("SMH", "ett_route"): r"^(oral|nasal)$", ("SMH", "ett_cuff"): r"^(cuffed|un-cuffed)$"}
VALUE_DROP = {("SMH", "ett_size"): _ETT_OTHER}
ZERO_MISSING = {("RBH", "pip"), ("RBH", "mean_airway_pressure"), ("RBH", "rr_set"), ("GOSH", "resp_rate_monitor"), ("GOSH", "bilirubin")}
DIA_OF = {"nibp_dia": "nibp_sys", "abp_dia": "abp_sys"}          # GOSH: diastolic copied from systolic
HB = {"bg_hb", "haemoglobin"}
HCT = {"bg_hct"}
SKIP_GROUPS = {"drugs", "fluids"}
NO_DEDUP = {"pupil_size", "pupil_reaction"}     # two eyes share one concept and the eye is not identified (SMH two attributes, GOSH one column): identical rows are kept
# Range flags: rows outside (low, high) get the flag "range"; the value is never changed or removed. Limits are in the units of the harmonised value.
# Agreed concepts only; add a concept here to flag it. insp_time: seconds (GOSH also holds a percentage near 33, probably HFOV); albumin g/L; cvp mmHg; hr per minute; resp_rate_total per minute.
RANGE = {"insp_time": (0.05, 5.0), "albumin": (5.0, 60.0), "cvp": (-10.0, 40.0), "hr": (20.0, 300.0), "resp_rate_total": (1.0, 120.0)}


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
    return _hours_from_parsed(ST._dt(t_text), site, t0_utc)


def _hours_from_parsed(t, site, t0_utc):
    """As to_hours, for times that are already datetimes."""
    if site == "SMH":
        tu = t.dt.tz_localize("UTC")
    else:
        tu = t.dt.tz_localize(TZ, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    return (tu - t0_utc).dt.total_seconds() / 3600


# ------------------------------------------------------------------ one concept at one site
def _clean_text(s):
    s = s.astype("string").str.strip()
    return s.mask(s.str.lower().isin(C.MISSING))


def _f64(s):
    """Numbers as plain float64 (NaN for missing). Text columns read as pandas 'string' give nullable numbers and nullable booleans
    (with NA) from to_numeric and comparisons, which break masks and inversions, so everything numeric is cast here."""
    return pd.to_numeric(s, errors="coerce").astype("float64")


def _parse_ie(s):
    """RBH text 'a:b' -> b / a."""
    parts = _clean_text(s).str.split(":", n=1, expand=True)
    if parts.shape[1] < 2:
        return pd.Series(np.nan, index=s.index)
    a, b = (_f64(parts[i]) for i in (0, 1))
    return (b / a).where(a > 0)


def _numeric(concept, site, s):
    s = _clean_text(s)
    if concept in ("tidal_volume", "ett_depth"):
        return _f64(s.str.extract(r"(-?\d+\.?\d*)")[0])
    return _f64(s)


def _read_concept(assembled_dir, site, concept, keep, report, rejected=None):
    """All sources of the concept at the site, cohort stays only, with hours and the numeric or text value, before the rules.
    Returns a long frame (stay_key, hour, value, value_text, source, src_row, value_raw). `src_row` is the row number in the assembled
    source table; `value_raw` is the recorded text where parsing changed it (a unit stripped from tidal volume, RBH 'a:b' I:E), else empty.
    Rows with a time and something recorded that is not a number are appended to `rejected` (a list) with the reason non_numeric and the
    recorded text; empty cells (nothing recorded; most rows of the wide RBH and SMH tables for any one variable) are only counted, as rows_empty."""
    parts = []
    for i, src in enumerate(C.CONCEPTS[concept][site]):
        df = C._read(assembled_dir, site, src, time=True)
        report["rows_read"] += len(df)
        df["stay"] = df["stay"].astype(str)
        df = df[df["stay"].isin(keep.index)]
        df["src_row"] = df.index.to_numpy(dtype="int64")
        report["rows_in_cohort"] += len(df)
        if concept == "ie_ratio" and site == "SMH":
            v = _f64(_clean_text(df["value"]))
            g = (df.assign(v=v).dropna(subset=["v"]).groupby(["stay", "t"], sort=False)
                 .agg(value=("v", "max"), size=("v", "size"), src_row=("src_row", "first")).reset_index())
            g = g[(g["size"] > 1) | (g["value"] > 1)]
            df = g[["stay", "t", "value", "src_row"]].copy()
        if (site, concept) in VALUE_KEEP or (site, concept) in VALUE_DROP:
            hit = _clean_text(df["value"]).str.contains(VALUE_KEEP.get((site, concept)) or VALUE_DROP[(site, concept)], case=False, regex=True, na=False).to_numpy(dtype=bool)
            df = df[hit if (site, concept) in VALUE_KEEP else ~hit]
        df["hour"] = to_hours(df["t"], site, df["stay"].map(keep))
        report["rows_bad_time"] += int(df["hour"].isna().sum())
        df = df.dropna(subset=["hour"])
        df["value_raw"] = pd.Series(pd.NA, index=df.index, dtype="string")
        if concept in TEXT:
            df["value_text"] = _clean_text(df["value"])
            df["value"] = np.nan
            df = df.dropna(subset=["value_text"])
        else:
            raw = df["value"]
            if concept == "ie_ratio" and site == "RBH":
                df["value"] = _parse_ie(raw)
            else:
                df["value"] = _numeric(concept, site, raw)
            raw = _clean_text(raw)
            parsed = (df["value"].notna() & _f64(raw).isna()).to_numpy(dtype=bool)       # the number was cut out of text
            df.loc[parsed, "value_raw"] = raw[parsed]
            df["value_text"] = pd.NA
            empty = raw.isna().to_numpy(dtype=bool)                                         # nothing recorded in the cell
            bad = df["value"].isna().to_numpy(dtype=bool)
            report["rows_empty"] = report.get("rows_empty", 0) + int(empty.sum())
            report["rows_non_numeric"] += int((bad & ~empty).sum())                         # something recorded that is not a number
            bad_present = bad & ~empty
            if rejected is not None and bad_present.any():
                rejected.append(pd.DataFrame({"stay_key": df.loc[bad_present, "stay"], "concept": concept, "hour": df.loc[bad_present, "hour"].astype("float32"),
                                              "value_raw": raw[bad_present], "reason": "non_numeric", "source": str(i), "src_row": df.loc[bad_present, "src_row"]}))
            df = df[~bad]
        parts.append(df[["stay", "hour", "value", "value_text", "value_raw", "src_row"]].assign(source=str(i)))
    cols = ["stay", "hour", "value", "value_text", "value_raw", "src_row", "source"]
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)
    return out.rename(columns={"stay": "stay_key"})


def _paired(assembled_dir, site, other, keep):
    """`other` concept of the same site as a (stay_key, hour, value) frame, for rules that need the same sample."""
    sub = {"rows_read": 0, "rows_in_cohort": 0, "rows_bad_time": 0, "rows_non_numeric": 0}
    df = _read_concept(assembled_dir, site, other, keep, sub)
    return df.dropna(subset=["value"])[["stay_key", "hour", "value"]]


PRE_HOURS = 24.0
TRAIL_HOURS = 1.0


def stay_window(assembled_dir, static, pre_hours=PRE_HOURS, trail_hours=TRAIL_HOURS):
    """The window of every cohort stay, hours since t0: start = -pre_hours, end = recorded length of stay + trail_hours; at RBH the end is
    the later of the recorded length and the ward out time (WARD_OUT_dttm of the vitals table, relative to t0). Returns a DataFrame with
    site, stay_key, start_h, end_h."""
    co = cohort(static)
    los = static.assign(stay_key=static["stay_key"].astype(str)).set_index(["site", "stay_key"])["los_hours"].astype("float64")
    w = co[["site", "stay_key"]].copy()
    w["end_h"] = pd.Series(list(zip(w["site"], w["stay_key"])), index=w.index).map(los)
    p = Path(assembled_dir) / "RBH" / "ai_picu_vitals.parquet"
    if p.exists():
        have = C.SM._cols(p, ("stay_key", "WARD_OUT_dttm"))
        if len(have) == 2:
            v = pd.read_parquet(p, columns=list(have)).drop_duplicates("stay_key")
            v["stay_key"] = v["stay_key"].astype(str)
            keep = co[co["site"] == "RBH"].set_index("stay_key")["t0_utc"]
            v = v[v["stay_key"].isin(keep.index)]
            wo = _hours_from_parsed(C._to_dt(v["WARD_OUT_dttm"]), "RBH", v["stay_key"].map(keep))
            wo = pd.Series(wo.to_numpy(), index=v["stay_key"].to_numpy())
            m = w["site"] == "RBH"
            ward_out = w.loc[m, "stay_key"].map(wo)
            w.loc[m, "end_h"] = np.fmax(w.loc[m, "end_h"], ward_out)
    w["end_h"] = w["end_h"] + trail_hours
    w["start_h"] = -pre_hours
    return w.reset_index(drop=True)


def _rej(df, concept, reason, raw=None):
    """Rows removed by a value rule, for the rejected-rows file: the recorded value as text, the reason and where it came from."""
    return pd.DataFrame({"stay_key": df["stay_key"], "concept": concept, "hour": df["hour"].astype("float32"),
                         "value_raw": pd.Series(raw if raw is not None else df["value"].round(6).astype(str).to_numpy(), index=df.index, dtype="string"),
                         "reason": reason, "source": df["source"], "src_row": df["src_row"]})


def harmonise_concept(assembled_dir, site, concept, keep, report=None, window=None, rejected=None):
    """One concept at one site as a long frame (stay_key, concept, hour, value, value_text, value_raw, flag, source, src_row), rules applied.
    keep: Series stay_key (text) -> t0 in UTC for the cohort stays of the site. report: dict of counters (updated).
    rejected: a list that receives the rows removed by a value rule (non_numeric, zero_missing, diastolic_copy) with their recorded text.
    value_raw holds the recorded value as text wherever the harmonised value differs from it (x10, x100, parsed text); src_row is the row
    number in the assembled source table (empty for derived rows)."""
    rep = report if report is not None else {}
    for k in ("rows_read", "rows_in_cohort", "rows_bad_time", "rows_non_numeric", "rows_outside_window", "rows_set_missing", "rows_converted", "rows_derived", "rows_dup", "rows_range_flag", "rows_empty"):
        rep.setdefault(k, 0)
    flag = None                                   # None: flags set row by row below
    if site == "GOSH" and concept == "bg_base_excess":
        ph = _paired(assembled_dir, site, "bg_ph", keep).rename(columns={"value": "ph"})
        hco3 = _paired(assembled_dir, site, "bg_hco3", keep).rename(columns={"value": "hco3"})
        m = ph.merge(hco3, on=["stay_key", "hour"])
        m = m[m["ph"].between(6.5, 7.8) & m["hco3"].between(1, 60)]
        df = m.assign(value=C.derive_base_excess(m["ph"], m["hco3"]), value_text=pd.NA, value_raw=pd.NA, src_row=pd.NA, source="0")[
            ["stay_key", "hour", "value", "value_text", "value_raw", "src_row", "source"]]
        flag = "derived"
        rep["rows_derived"] += len(df)
    else:
        df = _read_concept(assembled_dir, site, concept, keep, rep, rejected)
        if (site, concept) in ZERO_MISSING:
            z = (df["value"] == 0).to_numpy(dtype=bool)
            rep["rows_set_missing"] += int(z.sum())
            if rejected is not None and z.any():
                rejected.append(_rej(df[z], concept, "zero_missing", "0"))
            df = df[~z]
        if site == "GOSH" and concept in DIA_OF:
            sys_ = _paired(assembled_dir, site, DIA_OF[concept], keep).rename(columns={"value": "sys"}).drop_duplicates(["stay_key", "hour"])
            m = df.merge(sys_, on=["stay_key", "hour"], how="left")
            same = (m["value"] == m["sys"]).fillna(False).to_numpy(dtype=bool)
            rep["rows_set_missing"] += int(same.sum())
            if rejected is not None and same.any():
                rejected.append(_rej(df[same], concept, "diastolic_copy"))
            df = df[~same]
        df = df.assign(flag="")
        if concept in HB:
            low = (df["value"] < 30).to_numpy(dtype=bool)
            df.loc[low, "value_raw"] = df.loc[low, "value"].round(6).astype(str)
            df.loc[low, "value"] *= 10
            df.loc[low, "flag"] = "x10"
            rep["rows_converted"] += int(low.sum())
        if concept in HCT:
            frac = (df["value"] <= 1.5).to_numpy(dtype=bool)
            df.loc[frac, "value_raw"] = df.loc[frac, "value"].round(6).astype(str)
            df.loc[frac, "value"] *= 100
            df.loc[frac, "flag"] = "x100"
            rep["rows_converted"] += int(frac.sum())
    if flag is not None:
        df = df.assign(flag=flag)
    if concept in RANGE:
        lo, hi = RANGE[concept]
        out = ((df["value"] < lo) | (df["value"] > hi)).to_numpy(dtype=bool)
        f = df["flag"].astype("string").fillna("").to_numpy()
        df = df.assign(flag=np.where(out, np.where(f == "", "range", pd.Series(f).astype(str) + ";range"), f))
        rep["rows_range_flag"] += int(out.sum())
    if window is not None:
        outside = (df["hour"] < window["start_h"]) | (df["hour"] > df["stay_key"].map(window["end"]))
        rep["rows_outside_window"] += int(outside.sum())
        df = df[~outside]
    df = df.assign(concept=concept)
    n0 = len(df)
    if concept not in NO_DEDUP:
        df = df.drop_duplicates(["stay_key", "hour", "value", "value_text", "source"])
    rep["rows_dup"] += n0 - len(df)
    df["hour"] = df["hour"].astype("float32")
    df["value"] = df["value"].astype("float32")
    df["value_raw"] = df["value_raw"].astype("string")
    df["src_row"] = df["src_row"].astype("Int32")
    return df[["stay_key", "concept", "hour", "value", "value_text", "value_raw", "flag", "source", "src_row"]]


# ------------------------------------------------------------------ all concepts
def harmonise_all(assembled_dir, static, out_dir, concepts=None, sites=C.SITES, groups_skip=SKIP_GROUPS, apply_window=True):
    """Write one parquet per site and group to out_dir (derived/harmonised/) and return a counts-only report: per site and concept the
    stays and rows kept, rows read, rows outside the cohort, with a bad time or outside the stay window (stay_window), rows set missing or converted or derived, and the
    percentiles of `hour` (5th, 50th, 95th) as a check on the clock.
    concepts=None runs everything and rewrites the files. With a list of concepts only those are recomputed: their old rows are replaced
    inside the existing site and group files and their report rows in `_report.csv`; everything else is left as it is. The returned report is
    always the whole report. Use the list after changing a rule for some concepts (a full run takes minutes).
    Also writes `{site}_rejected.parquet`: the rows removed by a value rule (non_numeric, zero_missing, diastolic_copy) with the recorded text
    and `src_row`, so every change can be checked against the original. Rows outside the cohort or the stay window are selections, not
    changes, and are only counted. The rejected files can hold free text (non-numeric entries): they are handled at anonymisation."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    co = cohort(static)
    wins = stay_window(assembled_dir, static) if apply_window else None
    names = [n for n in C.CONCEPTS if (n in concepts if concepts else C.CONCEPTS[n]["group"] not in groups_skip)]
    partial = bool(concepts)
    rows = []
    for site in sites:
        keep = co[co["site"] == site].set_index("stay_key")["t0_utc"]
        win = None if wins is None else {"start_h": -PRE_HOURS, "end": wins[wins["site"] == site].set_index("stay_key")["end_h"]}
        by_group = {}
        rej = []
        for n in names:
            if not C.CONCEPTS[n].get(site):
                continue
            rep = {}
            df = harmonise_concept(assembled_dir, site, n, keep, rep, window=win, rejected=rej)
            by_group.setdefault(C.CONCEPTS[n]["group"], []).append(df)
            rows.append({"site": site, "concept": n, "cohort_stays": len(keep), "stays": int(df["stay_key"].nunique()), "rows": len(df),
                         **rep, "hour_p5": float(df["hour"].quantile(.05)) if len(df) else np.nan,
                         "hour_median": float(df["hour"].median()) if len(df) else np.nan,
                         "hour_p95": float(df["hour"].quantile(.95)) if len(df) else np.nan})
        for g, parts in by_group.items():
            d = pd.concat(parts, ignore_index=True)
            d.insert(0, "site", site)
            path = out_dir / f"{site}_{g.replace(' ', '_')}.parquet"
            if partial and path.exists():
                old = pd.read_parquet(path)
                d = pd.concat([old[~old["concept"].isin(d["concept"].unique())], d], ignore_index=True)
            d.to_parquet(path, index=False)
        rj = pd.concat(rej, ignore_index=True) if rej else pd.DataFrame(columns=["stay_key", "concept", "hour", "value_raw", "reason", "source", "src_row"])
        rj["src_row"] = rj["src_row"].astype("Int32")
        rj.insert(0, "site", site)
        rpath = out_dir / f"{site}_rejected.parquet"
        if partial and rpath.exists():
            old = pd.read_parquet(rpath)
            rj = pd.concat([old[~old["concept"].isin(names)], rj], ignore_index=True)
        rj.to_parquet(rpath, index=False)
    new = pd.DataFrame(rows)
    rp = out_dir / "_report.csv"
    if partial and rp.exists():
        old = pd.read_csv(rp)
        old = old.merge(new[["site", "concept"]].assign(_new=1), on=["site", "concept"], how="left")
        new = pd.concat([old[old["_new"].isna()].drop(columns="_new"), new], ignore_index=True)
    new.to_csv(rp, index=False)
    return new


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


# ====================================================================================================================================
# Fluids: hourly ml (value = the hourly amount recorded at `hour`; which end of the hour each source's time marks is not documented), long format.
#   intake_total   RBH Total_In_ex_dialysis (as recorded); SMH io fluidIn hourTotal (an hourly amount, checked with fluid_definition_check); GOSH differenced Total_fluids (pre-Epic)
#                  and caboodle hourly_intake_ml (Epic era)
#   intake_iv      IV infusion + colloids + drug volume, without blood products, enteral or TPN. RBH IV_Infusion + IV_Meds + Colloids;
#                  SMH ids 1851 + 2047 + 2101 (hourTotal); not at GOSH (totals only). May under-count at RBH up to about 2016 (R6).
#   output_total, urine_output (RBH, SMH), net_balance (RBH Net_Body_Balance, SMH balance ids; GOSH: differenced LOS Net Body Balance and
#                  caboodle intake minus output).
# GOSH pre-Epic: hourly = this row minus the previous one of the stay; at a fall of a running total that resets (the 24 h totals) the value
# itself; the first row of a stay has no previous and is dropped. `flag` 'gap' marks an amount that spans more than 1.5 h.
# Nothing is removed: `flag` 'outlier' marks hours above the `percentile` of |ml per kg| per site, concept and source (needs the stay's weight).
# ====================================================================================================================================
CABOODLE = "July2026extraction_by_alex__pAIC__merged_balance__caboodle_fluid_balance"
SMH_FLUID_IDS = {"intake_total": "fluidIn", "output_total": "fluidOut", "urine_output": "urineOutput", "net_balance": "fluidBalance"}
SMH_IV_IDS = ["ivInfusionTotal", "colloids", "drugVolumeTotal"]
GAP_HOURS = 1.5


def _fluid_frame(df, site, concept, source, keep, rep):
    """df: stay, t (text), value -> long frame in cohort with hours; counts updated."""
    df = df.copy()
    df["stay"] = df["stay"].astype(str)
    rep["rows_read"] += len(df)
    df = df[df["stay"].isin(keep.index)]
    rep["rows_in_cohort"] += len(df)
    df["hour"] = _hours_from_parsed(C._to_dt(df["t"]) if df["t"].dtype != "datetime64[ns]" else df["t"], site, df["stay"].map(keep))
    rep["rows_bad_time"] += int(df["hour"].isna().sum())
    df = df.dropna(subset=["hour", "value"])
    if "flag" not in df:
        df["flag"] = ""
    return pd.DataFrame({"stay_key": df["stay"], "concept": concept, "hour": df["hour"], "value": df["value"].astype(float),
                         "value_text": pd.NA, "flag": df["flag"], "source": source})


def _num(s):
    return _f64(_clean_text(s))


def _fluids_rbh(assembled_dir, keep, rep):
    p = Path(assembled_dir) / "RBH" / "ai_picu_io.parquet"
    cols = ["stay_key", "chartTime", "Total_In_ex_dialysis", "IV_Infusion", "IV_Meds", "Colloids", "Total_Out_ex_dialysis", "Urine_Output", "Net_Body_Balance"]
    df = pd.read_parquet(p, columns=C.SM._cols(p, cols))
    df.columns = ["stay", "t"] + cols[2:]
    for c in cols[2:]:
        df[c] = _num(df[c])
    df["intake_iv"] = df[["IV_Infusion", "IV_Meds", "Colloids"]].sum(axis=1, min_count=1)
    m = {"intake_total": "Total_In_ex_dialysis", "intake_iv": "intake_iv", "output_total": "Total_Out_ex_dialysis",
         "urine_output": "Urine_Output", "net_balance": "Net_Body_Balance"}
    return [_fluid_frame(df[["stay", "t"]].assign(value=df[col]), "RBH", c, "rbh_io", keep, rep) for c, col in m.items()]


def _fluids_smh(assembled_dir, keep, rep):
    base = Path(assembled_dir) / "SMH"
    p = C.SM._path(base, "io")
    cols = ["encounterId", "interventionId", "utcChartTime", "hourTotal"]
    df = pd.read_parquet(p, columns=C.SM._cols(p, cols))
    df.columns = ["stay", "id", "t", "value"]
    df["id"] = df["id"].astype("string").str.strip()
    df["value"] = _num(df["value"])
    df = df.dropna(subset=["value"]).drop_duplicates(["stay", "id", "t", "value"])
    out = []
    for c, key in SMH_FLUID_IDS.items():
        sub = df[df["id"].isin(C.SM.IO[key])].groupby(["stay", "t"], sort=False)["value"].first().reset_index()
        out.append(_fluid_frame(sub, "SMH", c, "smh_io", keep, rep))
    ids = [i for k in SMH_IV_IDS for i in C.SM.IO[k]]
    sub = df[df["id"].isin(ids)].groupby(["stay", "t", "id"], sort=False)["value"].first().groupby(["stay", "t"], sort=False).sum().reset_index()
    out.append(_fluid_frame(sub, "SMH", "intake_iv", "smh_io", keep, rep))
    return out


def _differenced(df, resets):
    """df: stay, t (parsed), cum. Hourly amounts from a running total, per stay in time order. resets=True: a fall is a reset and the value
    itself is the amount (the 24 h totals); False: a plain difference (the stay-long balance, which can fall)."""
    df = df.sort_values(["stay", "t"]).drop_duplicates(["stay", "t", "cum"])
    g = df.groupby("stay", sort=False)
    prev, prev_t = g["cum"].shift(1), g["t"].shift(1)
    d = df.assign(prev=prev, gap=(df["t"] - prev_t).dt.total_seconds() / 3600).dropna(subset=["prev"])
    val = d["cum"] - d["prev"]
    if resets:
        val = val.where(d["cum"] >= d["prev"], d["cum"])
    return d.assign(value=val, flag=np.where(d["gap"] > GAP_HOURS, "gap", ""))[["stay", "t", "value", "flag"]]


def _fluids_gosh(assembled_dir, keep, rep):
    base = Path(assembled_dir) / "GOSH"
    out = []
    for table, label, concept, resets in ((C._BAL + "Total_fluids", "Total Fluids In (24hrs)", "intake_total", True),
                                          (C._BAL + "Total_fluids", "Total Fluids Out (24hrs)", "output_total", True),
                                          (C._BAL + "Net_Bal", "LOS Net Body Balance", "net_balance", False)):
        p = base / f"{table}.parquet"
        df = pd.read_parquet(p, columns=C.SM._cols(p, ("stay_id", "start_datetime", "shortLabel", "cumTotal")))
        df.columns = ["stay", "t", "label", "cum"]
        df = df[df["label"] == label].drop(columns="label")
        df["stay"] = df["stay"].astype(str)
        df = df[df["stay"].isin(keep.index)]
        df["cum"] = _num(df["cum"])
        df["t"] = C._to_dt(df["t"])
        d = _differenced(df.dropna(subset=["cum", "t"]), resets)
        out.append(_fluid_frame(d, "GOSH", concept, "gosh_diff", keep, rep))
    p = base / f"{CABOODLE}.parquet"
    df = pd.read_parquet(p, columns=C.SM._cols(p, ("stay_id", "hour_start", "hourly_intake_ml", "hourly_output_ml")))
    df.columns = ["stay", "t", "i", "o"]
    df["i"], df["o"] = _num(df["i"]), _num(df["o"])
    out.append(_fluid_frame(df[["stay", "t"]].assign(value=df["i"]), "GOSH", "intake_total", "gosh_caboodle", keep, rep))
    out.append(_fluid_frame(df[["stay", "t"]].assign(value=df["o"]), "GOSH", "output_total", "gosh_caboodle", keep, rep))
    out.append(_fluid_frame(df[["stay", "t"]].assign(value=df["i"] - df["o"]), "GOSH", "net_balance", "gosh_caboodle", keep, rep))
    return out


def harmonise_fluids(assembled_dir, static, out_dir, percentile=99.9, sites=C.SITES, apply_window=True):
    """Write {site}_fluids.parquet to out_dir and return (report, caps). `hour` is the time of the hourly record.
    report: per site, concept and source: stays, rows, rows read, outside cohort, bad time, rows flagged gap and outlier.
    caps: per site, concept and source the cap (ml per kg per hour at the `percentile`) used for the 'outlier' flag, the share of rows above it, and
          the 99th, 99.99th percentile and maximum of the same quantity, as a check that the cap is not arbitrary. Counts and ratios only."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    co = cohort(static)
    wins = stay_window(assembled_dir, static) if apply_window else None
    w = static.assign(stay_key=static["stay_key"].astype(str)).set_index(["site", "stay_key"])["weight_kg"].astype("float64")
    builders = {"RBH": _fluids_rbh, "SMH": _fluids_smh, "GOSH": _fluids_gosh}
    rows, caps = [], []
    for site in sites:
        keep = co[co["site"] == site].set_index("stay_key")["t0_utc"]
        rep = {"rows_read": 0, "rows_in_cohort": 0, "rows_bad_time": 0}
        df = pd.concat(builders[site](assembled_dir, keep, rep), ignore_index=True)
        n_out = pd.Series(dtype="int64")
        if wins is not None:
            end = df["stay_key"].map(wins[wins["site"] == site].set_index("stay_key")["end_h"])
            outside = (df["hour"] < -PRE_HOURS) | (df["hour"] > end)
            n_out = df[outside].groupby(["concept", "source"]).size()
            df = df[~outside].reset_index(drop=True)
        wt = pd.Series(list(zip([site] * len(df), df["stay_key"])), index=df.index).map(w)
        perkg = (df["value"].abs() / wt.where(wt > 0))
        df["flag"] = df["flag"].astype(str)
        for c, src in df[["concept", "source"]].drop_duplicates().itertuples(index=False):
            sel = (df["concept"] == c) & (df["source"] == src)
            m = sel & perkg.notna() & (df["value"] != 0)
            if m.sum() == 0:
                continue
            cap = float(perkg[m].quantile(percentile / 100))
            above = m & (perkg > cap)
            df.loc[above, "flag"] = np.where(df.loc[above, "flag"] == "", "outlier", df.loc[above, "flag"] + "+outlier")
            caps.append({"site": site, "concept": c, "source": src, "weighted_nonzero_rows": int(m.sum()), "cap_ml_per_kg_h": round(cap, 1),
                         "pct_above_cap": round(100 * float(above.sum() / m.sum()), 3), "p99": round(float(perkg[m].quantile(.99)), 1),
                         "p99_99": round(float(perkg[m].quantile(.9999)), 1), "max": round(float(perkg[m].max()), 1),
                         "rows_without_weight": int((sel & wt.isna()).sum())})
        for (c, src), g in df.groupby(["concept", "source"]):
            rows.append({"site": site, "concept": c, "source": src, "stays": int(g["stay_key"].nunique()), "rows": len(g),
                         "rows_outside_window": int(n_out.get((c, src), 0)), "rows_gap": int(g["flag"].str.contains("gap").sum()), "rows_outlier": int(g["flag"].str.contains("outlier").sum()),
                         "hour_median": float(g["hour"].median()), **{k: rep[k] for k in ("rows_read", "rows_in_cohort", "rows_bad_time")}})
        df["hour"] = df["hour"].astype("float32")
        df["value"] = df["value"].astype("float32")
        df.insert(0, "site", site)
        df.to_parquet(out_dir / f"{site}_fluids.parquet", index=False)
    return pd.DataFrame(rows), pd.DataFrame(caps)


FLUID_CONCEPTS = ("intake_total", "intake_iv", "output_total", "urine_output", "net_balance")


def fluid_definition_check(harmonised_dir, static, sites=C.SITES):
    """Do the fluid concepts mean the same thing at each site? Reads {site}_fluids.parquet and returns two tables (counts and summaries only).

    profile, per site, concept and source:
      stays, rows; rows_per_hour (median over stays of rows / hours from first to last row: about 1 for an hourly record, well below 1 for
      totals recorded a few times a day); pct_zero; median_nonzero and p95_nonzero (ml); median_nonzero_per_kg (ml per kg per row);
      rows_per_day and median_day_per_kg (median over stay-days of the summed values per kg, which for a true hourly amount is the daily volume,
      a few tens to about 150 ml/kg for intake in children, and far too large for a 24 h total repeated hourly); pct_nondecreasing (share of
      consecutive hourly pairs of non-zero values where the value does not fall: about 50% for hourly amounts, near 100% for a running total).
    identities, per site and source: how often the concepts agree where they are recorded in the same hour:
      net_equals_in_minus_out (|net - (intake - output)| <= 1 ml), iv_le_total (intake_iv <= intake_total), urine_le_output (urine_output <=
      output_total), each with the number of hours compared.
    A source whose median_day_per_kg is about 24 times another's, or whose pct_nondecreasing is near 100%, holds running or 24 h totals and
    needs differencing; two sources of one concept that disagree in median_day_per_kg are not one series."""
    harmonised_dir = Path(harmonised_dir)
    w = static.assign(stay_key=static["stay_key"].astype(str)).set_index(["site", "stay_key"])["weight_kg"].astype("float64")
    prof, ident = [], []
    for site in sites:
        f = harmonised_dir / f"{site}_fluids.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f, columns=["stay_key", "concept", "hour", "value", "source"])
        d = d[d["value"].notna() & d["concept"].isin(FLUID_CONCEPTS)].copy()
        d["stay_key"] = d["stay_key"].astype(str)
        d["hour"] = d["hour"].astype("float64")
        d["value"] = d["value"].astype("float64")
        wt = pd.Series(list(zip([site] * len(d), d["stay_key"])), index=d.index).map(w)
        d["kg"] = wt.where(wt > 0)
        d["day"] = np.floor(d["hour"] / 24)
        for (c, src), g in d.groupby(["concept", "source"]):
            g = g.sort_values(["stay_key", "hour"])
            per = g.groupby("stay_key")["hour"].agg(n="size", span=lambda x: x.max() - x.min() + 1)
            nz = g[g["value"] != 0]
            pair = g.groupby("stay_key")[["hour", "value"]].diff()
            both = (pair["hour"] > 0) & (pair["hour"] <= 1.5) & (g["value"] != 0) & (g.groupby("stay_key")["value"].shift(1) != 0)
            day = g.groupby(["stay_key", "day"]).agg(total=("value", "sum"), n=("value", "size"), kg=("kg", "first"))
            prof.append({"site": site, "concept": c, "source": src, "stays": int(g["stay_key"].nunique()), "rows": len(g),
                         "rows_per_hour": round(float((per["n"] / per["span"]).clip(upper=1).median()), 3),
                         "pct_zero": round(100 * float((g["value"] == 0).mean()), 1),
                         "median_nonzero": round(float(nz["value"].median()), 1) if len(nz) else np.nan,
                         "p95_nonzero": round(float(nz["value"].quantile(.95)), 1) if len(nz) else np.nan,
                         "median_nonzero_per_kg": round(float((nz["value"] / nz["kg"]).median()), 2) if nz["kg"].notna().any() else np.nan,
                         "rows_per_day": round(float(day["n"].median()), 1),
                         "median_day_per_kg": round(float((day["total"] / day["kg"]).median()), 1) if day["kg"].notna().any() else np.nan,
                         "pct_nondecreasing": round(100 * float((g["value"] >= g.groupby("stay_key")["value"].shift(1))[both].mean()), 1) if both.sum() else np.nan})
        for src, g in d.groupby("source"):
            wide = g.pivot_table(index=["stay_key", "hour"], columns="concept", values="value", aggfunc="first")
            row = {"site": site, "source": src}
            for name, cols, test in (("net_equals_in_minus_out", ("net_balance", "intake_total", "output_total"),
                                      lambda x: (x["net_balance"] - (x["intake_total"] - x["output_total"])).abs() <= 1),
                                     ("iv_le_total", ("intake_iv", "intake_total"), lambda x: x["intake_iv"] <= x["intake_total"] + 1e-6),
                                     ("urine_le_output", ("urine_output", "output_total"), lambda x: x["urine_output"] <= x["output_total"] + 1e-6)):
                if all(c in wide for c in cols):
                    x = wide[list(cols)].dropna()
                    row[name] = round(100 * float(test(x).mean()), 1) if len(x) else np.nan
                    row[name + "_hours"] = len(x)
            if len(row) > 2:
                ident.append(row)
    return pd.DataFrame(prof), pd.DataFrame(ident)


EPIC_SWITCH = "2019-04-20"


def gosh_era_comparison(harmonised_dir, static, cutoff=EPIC_SWITCH, min_stays=10, site="GOSH"):
    """GOSH before and after the Epic switch (stays whose t0 is before / on or after `cutoff`, London local time), for every concept in the
    harmonised files of the site (all groups, drugs included). Per concept:
      n_pre, n_post          stays of each era in the cohort (same on every row)
      stays_pre, stays_post  stays with at least one row of the concept
      share_pre, share_post  those as shares of the era's stays; change_pts = post minus pre in percentage points
      median_pre, median_post  median over stays of the per-stay mean value, and shift = (post - pre) / typical spread of the pre era
                             (IQR / 1.349 of per-stay means), ks = Kolmogorov-Smirnov distance; only if both eras have at least min_stays stays
      flag                   'absent after' (post share under a tenth of the pre share), 'thin after' (under half), 'new after' (pre share under
                             half the post share), 'values differ' (|shift| above 1 or ks above 0.3), else blank. Only for concepts with at least
                             20% of stays in the larger-share era.
    Tells which concepts are missing, thin or different after the switch, before deciding whether to drop the era or single concepts.
    Counts, shares and summary values only. Needs scipy."""
    from scipy.stats import ks_2samp
    harmonised_dir = Path(harmonised_dir)
    co = cohort(static)
    co = co[co["site"] == site]
    era = pd.Series(np.where(co["t0"] >= pd.Timestamp(cutoff), "post", "pre"), index=co["stay_key"].astype(str).to_numpy())
    n = era.value_counts()
    parts = []
    for f in sorted(harmonised_dir.glob(f"{site}_*.parquet")):
        if f.stem.endswith("_rejected"):
            continue
        d = pd.read_parquet(f, columns=["stay_key", "concept", "value"])
        d["stay_key"] = d["stay_key"].astype(str)
        d = d[d["stay_key"].isin(era.index)]
        d["value"] = pd.to_numeric(d["value"], errors="coerce")
        parts.append(d.groupby(["concept", "stay_key"], observed=True)["value"].agg(m="mean", rows="size").reset_index())
    if not parts:
        return pd.DataFrame()
    m = pd.concat(parts, ignore_index=True)
    m["era"] = m["stay_key"].map(era)
    rows = []
    for c, g in m.groupby("concept", observed=True):
        a, b = g[g["era"] == "pre"], g[g["era"] == "post"]
        sp, sq = len(a) / n.get("pre", np.nan), len(b) / n.get("post", np.nan)
        row = {"concept": c, "stays_pre": len(a), "stays_post": len(b), "share_pre": round(sp, 3), "share_post": round(sq, 3),
               "change_pts": round(100 * (sq - sp), 1)}
        va, vb = a["m"].dropna().to_numpy(), b["m"].dropna().to_numpy()
        flag = ""
        if len(va) >= min_stays and len(vb) >= min_stays:
            spread = (np.percentile(va, 75) - np.percentile(va, 25)) / 1.349
            shift = (np.median(vb) - np.median(va)) / spread if spread > 0 else (np.inf if np.median(vb) != np.median(va) else 0.0)
            ks = float(ks_2samp(va, vb).statistic)
            row.update({"median_pre": round(float(np.median(va)), 3), "median_post": round(float(np.median(vb)), 3),
                        "shift": round(float(shift), 2), "ks": round(ks, 3)})
            if abs(shift) > 1 or ks > 0.3:
                flag = "values differ"
        if max(sp, sq) >= 0.2:
            if sq < 0.1 * sp:
                flag = "absent after"
            elif sq < 0.5 * sp:
                flag = "thin after"
            elif sp < 0.5 * sq:
                flag = "new after"
        elif flag:
            flag = ""
        row["flag"] = flag
        rows.append(row)
    out = pd.DataFrame(rows)
    out["_o"] = out["flag"].map({"absent after": 0, "thin after": 1, "new after": 2, "values differ": 3, "": 4})
    out = out.sort_values(["_o", "change_pts"]).drop(columns="_o").reset_index(drop=True)
    out.insert(1, "n_pre", int(n.get("pre", 0)))
    out.insert(2, "n_post", int(n.get("post", 0)))
    return out


def window_check(harmonised_dir, static, sites=C.SITES, assembled_dir=None):
    """Do harmonised rows lie inside the stay? For every harmonised file (all groups, fluids included), per site and concept: the rows, and
    the percent of rows more than 24 h before t0, from 24 h before up to t0, inside the stay (t0 to its length) and after the end of the stay.
    The end is `los_hours` of the static table, or, if `assembled_dir` is given, the end of the window applied by stay_window.
    Counts and percents only; nothing is removed."""
    harmonised_dir = Path(harmonised_dir)
    los = static.assign(stay_key=static["stay_key"].astype(str)).set_index(["site", "stay_key"])["los_hours"].astype("float64")
    if assembled_dir is not None:             # measure against the window actually applied (stay_window), not the recorded length alone
        w = stay_window(assembled_dir, static)
        los = w.set_index(["site", "stay_key"])["end_h"]
    out = []
    for site in sites:
        for f in sorted(harmonised_dir.glob(f"{site}_*.parquet")):
            if f.stem.endswith("_rejected"):
                continue
            d = pd.read_parquet(f, columns=["stay_key", "concept", "hour"])
            ends = pd.Series(list(zip([site] * len(d), d["stay_key"].astype(str))), index=d.index).map(los)
            h = d["hour"].astype("float64")
            d = d.assign(before24=h < -24, pre=(h >= -24) & (h < 0), inside=(h >= 0) & (h <= ends), after=h > ends)
            g = d.groupby("concept")
            res = pd.DataFrame({"rows": g.size(), "pct_before_24h": 100 * g["before24"].mean(), "pct_pre_t0": 100 * g["pre"].mean(),
                                "pct_inside": 100 * g["inside"].mean(), "pct_after_end": 100 * g["after"].mean()}).round(1)
            res.insert(0, "site", site)
            out.append(res.reset_index())
    return pd.concat(out, ignore_index=True)


def stay_span_check(harmonised_dir, static, concepts=("hr", "spo2", "intake_total", "bg_ph", "sodium"), sites=C.SITES):
    """Where do the rows of a stay lie compared with its recorded length? Per site and concept, per stay: the first and last `hour` against
    `los_hours`. Reports the stays, the percent whose last row is more than 1 h and more than 24 h after the recorded end (and the median and
    95th percentile of that excess among them, in hours), and the percent whose first row is more than 24 h and more than 168 h before t0
    (with the median first hour). Tells apart a few stays with a long tail (overlapping episodes under one stay key) from a length of stay
    that is systematically too short. Counts, percents and hours only."""
    harmonised_dir = Path(harmonised_dir)
    los = static.assign(stay_key=static["stay_key"].astype(str)).set_index(["site", "stay_key"])["los_hours"].astype("float64")
    out = []
    for site in sites:
        parts = []
        for f in sorted(harmonised_dir.glob(f"{site}_*.parquet")):
            if f.stem.endswith("_rejected"):
                continue
            d = pd.read_parquet(f, columns=["stay_key", "concept", "hour"])
            parts.append(d[d["concept"].isin(concepts)])
        d = pd.concat(parts, ignore_index=True)
        d["hour"] = d["hour"].astype("float64")
        g = d.groupby(["concept", "stay_key"])["hour"].agg(first="min", last="max").reset_index()
        g["los"] = pd.Series(list(zip([site] * len(g), g["stay_key"].astype(str))), index=g.index).map(los)
        g["excess"] = g["last"] - g["los"]
        for c, x in g.groupby("concept"):
            late = x[x["excess"] > 1]
            out.append({"site": site, "concept": c, "stays": len(x),
                        "pct_last_after_end_1h": round(100 * float((x["excess"] > 1).mean()), 1),
                        "pct_last_after_end_24h": round(100 * float((x["excess"] > 24).mean()), 1),
                        "median_excess_h": round(float(late["excess"].median()), 1) if len(late) else np.nan,
                        "p95_excess_h": round(float(late["excess"].quantile(.95)), 1) if len(late) else np.nan,
                        "pct_first_before_24h": round(100 * float((x["first"] < -24).mean()), 1),
                        "pct_first_before_168h": round(100 * float((x["first"] < -168).mean()), 1),
                        "median_first_h": round(float(x["first"].median()), 1), "median_los_h": round(float(x["los"].median()), 1)})
    return pd.DataFrame(out)


def rbh_end_check(assembled_dir, static):
    """RBH only: why do vitals run past the recorded length of stay? From the vitals table (ward in and out times, ward length `LOS`,
    clinical unit, admission key) for the stays of the cohort:
      - stays with more than one distinct WARD_IN (several ward episodes under one stay key) and with more than one admission key;
      - ward in relative to t0 (5th, 50th, 95th percentile, hours) and ward out relative to t0, against the static length of stay;
      - the percent of stays whose last heart rate lies more than 1 h after the static end, and more than 1 h after the ward out.
    Counts, percents and hours only."""
    co = cohort(static)
    keep = co[co["site"] == "RBH"].set_index("stay_key")["t0_utc"]
    los = static[static["site"] == "RBH"].assign(stay_key=lambda d: d["stay_key"].astype(str)).set_index("stay_key")["los_hours"].astype("float64")
    p = Path(assembled_dir) / "RBH" / "ai_picu_vitals.parquet"
    cols = ["stay_key", "chartTime", "WARD_IN_dttm", "WARD_OUT_dttm", "LOS", "PAS_AD_RK", "HR"]
    df = pd.read_parquet(p, columns=C.SM._cols(p, cols))
    df.columns = cols[:len(df.columns)] if len(df.columns) == len(cols) else df.columns
    df["stay_key"] = df["stay_key"].astype(str)
    df = df[df["stay_key"].isin(keep.index)]
    out = {}
    g = df.groupby("stay_key")
    out["stays"] = len(g)
    out["pct_stays_with_2plus_ward_in"] = round(100 * float((g["WARD_IN_dttm"].nunique() > 1).mean()), 1)
    out["pct_stays_with_2plus_admission_keys"] = round(100 * float((g["PAS_AD_RK"].nunique() > 1).mean()), 1)
    first = df.drop_duplicates("stay_key").set_index("stay_key")
    t0 = keep.reindex(first.index)
    wi = _hours_from_parsed(C._to_dt(first["WARD_IN_dttm"]), "RBH", t0)
    wo = _hours_from_parsed(C._to_dt(first["WARD_OUT_dttm"]), "RBH", t0)
    for name, s in (("ward_in_minus_t0_h", wi), ("ward_out_minus_t0_h", wo)):
        out[name + "_p5_p50_p95"] = tuple(round(float(s.quantile(q)), 1) for q in (.05, .5, .95))
    st = los.reindex(first.index)
    out["pct_ward_out_within_1h_of_static_end"] = round(100 * float(((wo - st).abs() <= 1).mean()), 1)
    out["pct_ward_out_more_than_24h_after_static_end"] = round(100 * float(((wo - st) > 24).mean()), 1)
    out["pct_ward_out_more_than_24h_before_static_end"] = round(100 * float(((wo - st) < -24).mean()), 1)
    hr = df.dropna(subset=["HR"])
    last = _hours_from_parsed(C._to_dt(hr["chartTime"]), "RBH", hr["stay_key"].map(keep)).groupby(hr["stay_key"]).max()
    out["pct_last_hr_more_than_1h_after_static_end"] = round(100 * float(((last - st.reindex(last.index)) > 1).mean()), 1)
    out["pct_last_hr_more_than_1h_after_ward_out"] = round(100 * float(((last - wo.reindex(last.index)) > 1).mean()), 1)
    return pd.Series(out)


def rbh_unit_check(assembled_dir, static):
    """RBH only: where do the vitals rows of each clinical unit lie compared with the stay? Per `clinicalUnit` (heart rate rows of the
    cohort stays): rows, stays, and the percent of rows more than 24 h before t0, from 24 h before up to t0, inside the stay (t0 to the
    static `los_hours`) and after the static end. Counts and percents only."""
    co = cohort(static)
    keep = co[co["site"] == "RBH"].set_index("stay_key")["t0_utc"]
    los = static[static["site"] == "RBH"].assign(stay_key=lambda d: d["stay_key"].astype(str)).set_index("stay_key")["los_hours"].astype("float64")
    p = Path(assembled_dir) / "RBH" / "ai_picu_vitals.parquet"
    df = pd.read_parquet(p, columns=["stay_key", "chartTime", "clinicalUnit", "HR"])
    df["stay_key"] = df["stay_key"].astype(str)
    df = df[df["stay_key"].isin(keep.index) & df["HR"].notna()].copy()
    df["hour"] = _hours_from_parsed(C._to_dt(df["chartTime"]), "RBH", df["stay_key"].map(keep))
    end = df["stay_key"].map(los)
    df = df.assign(before24=df["hour"] < -24, pre=(df["hour"] >= -24) & (df["hour"] < 0), inside=(df["hour"] >= 0) & (df["hour"] <= end),
                   after=df["hour"] > end)
    g = df.groupby("clinicalUnit")
    return pd.DataFrame({"rows": g.size(), "stays": g["stay_key"].nunique(), "pct_before_24h": 100 * g["before24"].mean(),
                         "pct_pre_t0": 100 * g["pre"].mean(), "pct_inside": 100 * g["inside"].mean(),
                         "pct_after_end": 100 * g["after"].mean()}).round(1).sort_values("rows", ascending=False)


# ------------------------------------------------------------------ distributions across sites
QUANTILES = (0.001, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 0.999)
QNAMES = ("p0.1", "p1", "p5", "p25", "p50", "p75", "p95", "p99", "p99.9")


def distribution_check(harmonised_dir, sites=C.SITES, concepts=None, min_stays=10):
    """Per site and concept (fluids per source, in `source`): stays, rows, quantiles of `value` from p0.1 to p99.9, the share of zero, negative and
    flagged rows, and the median number of rows per stay. Numeric concepts only. The minimum and maximum are not reported (a single row);
    combinations seen in fewer than `min_stays` stays are left out. Counts and ranges only. Returns the long table."""
    harmonised_dir = Path(harmonised_dir)
    rows = []
    for site in sites:
        for f in sorted(harmonised_dir.glob(f"{site}_*.parquet")):
            if f.stem.endswith(("_rejected", "_drugs")):      # the drug files have no flag column (unit and kind instead)
                continue
            d = pd.read_parquet(f, columns=["stay_key", "concept", "value", "flag", "source"])
            d = d[d["value"].notna()]
            d["flag"] = d["flag"].fillna("").astype("string")
            d["src"] = d["source"].astype("string") if f.stem.endswith("_fluids") else ""
            for (key, src), g in d.groupby(["concept", "src"], sort=False):
                stays = g["stay_key"].nunique()
                if stays < min_stays:
                    continue
                v = g["value"].astype("float64").to_numpy()
                q = np.quantile(v, QUANTILES)
                fl = g["flag"]
                flagged = (fl != "")
                rows.append({"site": site, "concept": key, "source": src, "stays": stays, "rows": len(g), "rows_per_stay_median": float(g.groupby("stay_key").size().median()),
                             **dict(zip(QNAMES, q.astype(float))),
                             "pct_zero": round(100 * float((v == 0).mean()), 2), "pct_negative": round(100 * float((v < 0).mean()), 2),
                             "pct_flagged": round(100 * float(flagged.mean()), 2),
                             "flags": ", ".join(f"{k}:{n}" for k, n in fl[flagged].value_counts().items())})
            del d
    return pd.DataFrame(rows)


def compare_sites(detail, sites=C.SITES, ratio=3.0, zero_gap=20.0, tail_ratio=10.0):
    """One row per concept with p5 / median / p95 per site and flags for what to look at (not errors, just places to look):
    scale (largest median more than `ratio` times the smallest, or a sign change), spread (IQR ratio above `ratio`),
    tail (at a site: p99.9 more than `tail_ratio` times p99, or p99 more than 3 times p95, or p95 more than `tail_ratio` times p75), zeros (share of zeros differs by more than `zero_gap` points).
    `looks_ok` is True when nothing is flagged. Needs sites to share a concept to compare; others are listed with a single site."""
    rows = []
    detail = detail.sort_values("stays", ascending=False).drop_duplicates(["concept", "site"])      # fluids: the source with most stays
    for name, g in detail.groupby("concept", sort=False):
        g = g.set_index("site")
        row = {"concept": name, "sites": len(g)}
        for s in sites:
            row[s] = f"{g.loc[s, 'p5']:.4g} / {g.loc[s, 'p50']:.4g} / {g.loc[s, 'p95']:.4g}" if s in g.index else ""
        med, iqr = g["p50"], g["p75"] - g["p25"]
        pos = med[med > 0]
        row["scale"] = bool(len(g) > 1 and (((med > 0).any() and (med < 0).any()) or (len(pos) == len(med) and med.max() / med.min() > ratio)))
        ip = iqr[iqr > 0]
        row["spread"] = bool(len(ip) > 1 and ip.max() / ip.min() > ratio)
        row["tail"] = bool((((g["p99"] > 0) & (g["p99.9"] > tail_ratio * g["p99"]))
                            | ((g["p95"] > 0) & (g["p99"] > 3 * g["p95"]))
                            | ((g["p75"] > 0) & (g["p95"] > tail_ratio * g["p75"]))).any())
        row["zeros"] = bool(len(g) > 1 and g["pct_zero"].max() - g["pct_zero"].min() > zero_gap)
        row["looks_ok"] = not (row["scale"] or row["spread"] or row["tail"] or row["zeros"])
        rows.append(row)
    return pd.DataFrame(rows)


def source_check(harmonised_dir, site, concept, min_stays=10):
    """Quantiles of one concept at one site split by source (the position of the source in the concept map, with its description), to
    find a source that holds a different quantity or unit. Counts and ranges only."""
    f = Path(harmonised_dir) / f"{site}_{C.CONCEPTS[concept]['group'].replace(' ', '_')}.parquet"
    d = pd.read_parquet(f, columns=["stay_key", "concept", "value", "source"])
    d = d[(d["concept"] == concept) & d["value"].notna()]
    rows = []
    for src, g in d.groupby("source"):
        if g["stay_key"].nunique() < min_stays:
            continue
        q = np.quantile(g["value"].astype("float64"), QUANTILES)
        desc = C.CONCEPTS[concept][site][int(src)] if str(src).isdigit() and int(src) < len(C.CONCEPTS[concept][site]) else ""
        rows.append({"source": src, "description": str(desc)[-70:], "stays": g["stay_key"].nunique(), "rows": len(g), **dict(zip(QNAMES, q.astype(float)))})
    return pd.DataFrame(rows)


def values_above(harmonised_dir, site, concept, above, top=15, min_stays=10):
    """The most common values above a limit for one concept and site, with rows and stays (values in fewer than `min_stays` stays are
    left out). Shows placeholder values (the same number again and again) and the share of rows above the limit. Counts only."""
    f = Path(harmonised_dir) / f"{site}_{C.CONCEPTS[concept]['group'].replace(' ', '_')}.parquet"
    d = pd.read_parquet(f, columns=["stay_key", "concept", "value"])
    d = d[(d["concept"] == concept) & d["value"].notna()]
    hi = d[d["value"] > above]
    print(f"{site} {concept}: {len(hi)} of {len(d)} rows ({100 * len(hi) / max(len(d), 1):.2f}%) above {above}")
    g = hi.groupby("value")
    out = pd.DataFrame({"rows": g.size(), "stays": g["stay_key"].nunique()}).sort_values("rows", ascending=False)
    return out[out["stays"] >= min_stays].head(top)


def ie_check(harmonised_dir, site="SMH", values=(1.1, 1.4, 1.5, 1.9, 2, 4, 11, 12, 14, 15, 16, 19), min_stays=10):
    """For the recorded I:E values listed, the ratio implied by the set rate and inspiratory time at the same chart time,
    expiratory over inspiratory = (60 / rate - inspiratory time) / inspiratory time (as in the recorded 1:x). Shows whether a recorded
    '14' behaves like 1.4 or like 4. Rows with a rate and inspiratory time only. Counts and quantiles only."""
    g = C.CONCEPTS["ie_ratio"]["group"].replace(" ", "_")
    d = pd.read_parquet(Path(harmonised_dir) / f"{site}_{g}.parquet", columns=["stay_key", "concept", "hour", "value"])
    w = {n: d[d["concept"] == n].drop(columns="concept").rename(columns={"value": n}).drop_duplicates(["stay_key", "hour"]) for n in ("ie_ratio", "rr_set", "insp_time")}
    m = w["ie_ratio"].merge(w["rr_set"], on=["stay_key", "hour"]).merge(w["insp_time"], on=["stay_key", "hour"])
    m = m[(m["rr_set"] > 0) & (m["insp_time"] > 0) & (60 / m["rr_set"] > m["insp_time"])]
    m["implied"] = (60 / m["rr_set"] - m["insp_time"]) / m["insp_time"]
    rows = []
    for v in values:
        s = m[np.isclose(m["ie_ratio"], v)]
        if s["stay_key"].nunique() < min_stays:
            continue
        q = s["implied"].quantile([.25, .5, .75])
        rows.append({"recorded": v, "rows": len(s), "stays": s["stay_key"].nunique(), "implied_p25": q.iloc[0], "implied_median": q.iloc[1], "implied_p75": q.iloc[2]})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ drugs (as recorded)
def _drug_kind(unit):
    """What a recorded drug value is, from its unit alone (a lookup, nothing converted): rate_per_kg (mg/kg/hr, microg/kg/min, units/kg/min),
    rate (mg/hr, micrograms/hr), pump_rate (ml/hr), concentration (mg/ml), weight (kg), volume (ml), amount (mg, microgram, units, drops,
    application), unspecified (no unit), other."""
    if unit is None or pd.isna(unit) or str(unit).strip() == "":
        return "unspecified"
    u = str(unit).lower().replace(" ", "")
    if "/kg/" in u:
        return "rate_per_kg"
    if u in ("ml/hr", "ml/h", "ml/min"):
        return "pump_rate"
    if u.endswith("/ml"):
        return "concentration"
    if u.endswith("/hr") or u.endswith("/h") or u.endswith("/min"):
        return "rate"
    if u == "kg":
        return "weight"
    if u == "ml":
        return "volume"
    if any(u.startswith(a) for a in ("mg", "mcg", "microg", "ug", "unit", "drop", "appl", "g")):
        return "amount"
    return "other"


def _read_drug(assembled_dir, site, src):
    """Rows of one drug source: stay, t (row time text), raw (the recorded value as text), unit, route, src_row. Filtered to the drug by the
    source's label rule. RBH: Dose with Dose_Unit (meds also Route). SMH: the number and unit are cut out of Dosage_verbose ('9 mcg/kg/hr').
    GOSH: valueNumber with unitOfMeasure; the medication administration table has no dose value, so raw holds prn_dose where present."""
    base = Path(assembled_dir) / site
    names = lambda p: {n.lower(): n for n in C.pq.ParquetFile(p).schema.names}
    if site == "RBH":
        p = base / f"ai_picu_{src[0]}.parquet"
        stay, label, value, unit, route, prn = "stay_key", src[2], src[1], "Dose_Unit", "Route", None
    elif site == "SMH":
        p = C.SM._path(base, src[0])
        stay, label, value, unit, route, prn = "encounterId", src[1], "Dosage_verbose", None, None, None
    else:
        p = base / f"{src[0]}.parquet"
        admin = src[0].endswith("medication_admins")
        stay, label, value, unit, route, prn = "stay_id", src[2], (None if admin else src[1]), (None if admin else "unitOfMeasure"), ("route_name" if admin else None), ("prn_dose" if admin else None)
    nm = names(p)
    tcol = C.time_column(p)
    want = [c for c in (stay, label, value, unit, route, prn, tcol) if c and c.lower() in nm]
    df = pd.read_parquet(p, columns=[nm[c.lower()] for c in dict.fromkeys(want)])
    df.columns = [c.lower() for c in df.columns]
    get = lambda c: df[c.lower()] if c and c.lower() in df.columns else pd.Series(pd.NA, index=df.index, dtype="string")
    keep = C._label_mask(get(label), src[-1])
    out = pd.DataFrame({"stay": get(stay).astype(str), "t": get(tcol), "raw": _clean_text(get(value or prn)),
                        "unit": get(unit).astype("string").str.strip(), "route": get(route).astype("string").str.strip(), "src_row": df.index.to_numpy(dtype="int64")})
    return out[keep.to_numpy(dtype=bool)].copy()


def harmonise_drugs(assembled_dir, static, out_dir, sites=C.SITES, apply_window=True):
    """Drug records as recorded, nothing converted or pooled: one parquet per site (`{site}_drugs.parquet`) with site, stay_key, concept,
    hour, value (the recorded number, float32), unit (as recorded), kind (from the unit, see _drug_kind), route, value_raw (the recorded text
    where the number was cut out of text, or the text where it is not a number), source, src_row. The same record in two tables (RBH `meds`
    and `infusion`, `sedation` and `sedation_old`) is kept once. Records with no dose written (about half of some SMH infusions, probably starts and stops) are kept with an empty value. Window rule as for the other concepts. Returns (report, units): rows, stays and the
    rows dropped by each rule by site and drug concept, and rows and stays by site, drug concept, kind and unit. Counts only."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    co = cohort(static)
    wins = stay_window(assembled_dir, static) if apply_window else None
    names = [n for n in C.CONCEPTS if C.CONCEPTS[n]["group"] == "drugs"]
    rep_rows, unit_rows = [], []
    for site in sites:
        keep = co[co["site"] == site].set_index("stay_key")["t0_utc"]
        win = None if wins is None else wins[wins["site"] == site].set_index("stay_key")["end_h"]
        parts = []
        for n in names:
            c = {"rows_read": 0, "rows_bad_time": 0, "rows_outside_window": 0, "rows_dup": 0, "rows_empty": 0}                    # rows_empty: records with no dose recorded (kept)
            frames = []
            for i, src in enumerate(C.CONCEPTS[n].get(site, [])):
                df = _read_drug(assembled_dir, site, src)
                c["rows_read"] += len(df)
                df = df[df["stay"].isin(keep.index)].copy()
                df["hour"] = to_hours(df["t"], site, df["stay"].map(keep))
                c["rows_bad_time"] += int(df["hour"].isna().sum())
                df = df.dropna(subset=["hour"])
                c["rows_empty"] += int(df["raw"].isna().sum())          # records with no dose written: kept, as the record of a drug event
                if site == "SMH":
                    ex = df["raw"].str.extract(r"^\s*(-?\d+(?:\.\d+)?)\s*(.*?)\s*$")
                    df = df.assign(value=_f64(ex[0]), unit=ex[1].mask(ex[1].fillna("") == ""), value_raw=df["raw"])
                else:
                    v = _f64(df["raw"])
                    df = df.assign(value=v, value_raw=df["raw"].where(v.isna()))
                df["source"] = str(i)
                frames.append(df)
            if not frames:
                continue
            d = pd.concat(frames, ignore_index=True)
            if win is not None:
                outside = ((d["hour"] < -PRE_HOURS) | (d["hour"] > d["stay"].map(win))).to_numpy(dtype=bool)
                c["rows_outside_window"] += int(outside.sum())
                d = d[~outside]
            n0 = len(d)
            d = d.drop_duplicates(["stay", "hour", "value", "unit", "value_raw"])
            c["rows_dup"] += n0 - len(d)
            d["concept"] = n
            d["kind"] = d["unit"].map(_drug_kind)
            parts.append(d)
            rep_rows.append({"site": site, "concept": n, "stays": d["stay"].nunique(), "rows": len(d), **c})
        if parts:
            allp = pd.concat(parts, ignore_index=True)
            allp = allp.rename(columns={"stay": "stay_key"})
            allp["hour"] = allp["hour"].astype("float32")
            allp["value"] = allp["value"].astype("float32")
            allp["src_row"] = allp["src_row"].astype("Int32")
            for col in ("unit", "route", "value_raw"):
                allp[col] = allp[col].astype("string")
            allp.insert(0, "site", site)
            allp[["site", "stay_key", "concept", "hour", "value", "unit", "kind", "route", "value_raw", "source", "src_row"]].to_parquet(out_dir / f"{site}_drugs.parquet", index=False)
            u = allp.assign(unit=allp["unit"].fillna("(none)")).groupby(["concept", "kind", "unit"])
            unit_rows += [{"site": site, "concept": cn, "kind": k, "unit": un, "stays": s["stay_key"].nunique(), "rows": len(s)} for (cn, k, un), s in u]
    return pd.DataFrame(rep_rows), pd.DataFrame(unit_rows)


def load_pooled(harmonised_dir, sites=C.SITES, groups=None, concepts=None, drugs=False, columns=None):
    """The three sites stacked into one frame, read from the per-site files (no pooled file is written). Stay keys are unique only within a
    site, so the frame carries `stay_uid` = site + ":" + stay_key; use it, never `stay_key` alone, to group stays. No patient linkage across
    sites is attempted or implied. groups: list of file groups (for example ["vitals", "labs"]; None = every group file except rejected,
    fluids and drugs); concepts: keep only these concepts; drugs=True loads the drug files instead (they have unit, kind and route)."""
    d = Path(harmonised_dir)
    frames = []
    for site in sites:
        if drugs:
            files = [d / f"{site}_drugs.parquet"]
        else:
            files = sorted(d.glob(f"{site}_*.parquet"))
            files = [f for f in files if not f.stem.endswith(("_rejected", "_drugs"))]
            if groups is not None:
                files = [f for f in files if f.stem[len(site) + 1:] in groups]
        for f in files:
            if not f.exists():
                continue
            df = pd.read_parquet(f, columns=columns)
            if concepts is not None:
                df = df[df["concept"].isin(concepts)]
            frames.append(df)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(out) and "site" in out.columns and "stay_key" in out.columns:
        out.insert(0, "stay_uid", out["site"].astype(str) + ":" + out["stay_key"].astype(str))
    return out


_AMT = {"mg": 1.0, "g": 1000.0, "mcg": 1e-3, "microg": 1e-3, "microgram": 1e-3, "micrograms": 1e-3, "ug": 1e-3, "ng": 1e-6,
        "nanog": 1e-6, "nanogram": 1e-6, "nanograms": 1e-6, "unit": 1.0, "units": 1.0, "iu": 1.0, "mmol": 1.0, "ml": 1.0}
_TIME = {"hr": 1.0, "h": 1.0, "hour": 1.0, "min": 60.0, "minute": 60.0, "sec": 3600.0, "s": 3600.0, "day": 1 / 24, "24hr": 1 / 24}


def drug_unit_lookup(harmonised_dir, sites=C.SITES, min_stays=10):
    """Lookup of the drug units as recorded, for users who want to convert doses themselves. One row per unit string seen in at least
    `min_stays` stays at a site (rarer strings are not listed): rows, stays, kind, the parsed amount unit, per_kg, time unit, `base_unit`
    and `factor`: multiply the recorded value by `factor` to get the value in `base_unit`. Base units: mg (or units, mmol) for amounts,
    mg/ml (or units/ml) for concentrations, mg/h and mg/kg/h for rates, ml/h for pump rates, kg and ml unchanged. Strings that do not
    parse (drops, applications, no unit) have an empty factor; nothing is guessed. Counts only, no values. The harmonised data are never
    converted."""
    import re
    rows = []
    for site in sites:
        f = Path(harmonised_dir) / f"{site}_drugs.parquet"
        if not f.exists():
            continue
        df = pd.read_parquet(f, columns=["stay_key", "unit", "kind"])
        df["unit"] = df["unit"].astype("string").fillna("(none)")
        g = df.groupby("unit")
        res = pd.DataFrame({"rows": g.size(), "stays": g["stay_key"].nunique(), "kind": g["kind"].first()}).reset_index()
        res = res[res["stays"] >= min_stays]
        for _, r in res.iterrows():
            u = str(r["unit"]).lower().replace(" ", "")
            amt = tm = fac = base = None
            perkg = False
            m = re.fullmatch(r"([a-z]+)(/kg)?/([0-9]*[a-z]+)", u)
            if m and m.group(3) == "ml" and m.group(1) in _AMT and not m.group(2):
                amt, fac = m.group(1), _AMT[m.group(1)]                                  # concentration
                base = "units/ml" if amt in ("unit", "units", "iu") else ("mmol/ml" if amt == "mmol" else "mg/ml")
            elif m and m.group(1) in _AMT and m.group(3) in _TIME:
                amt, perkg, tm = m.group(1), bool(m.group(2)), m.group(3)
                fac = _AMT[amt] * _TIME[tm]
                unit = "ml" if amt == "ml" else ("units" if amt in ("unit", "units", "iu") else ("mmol" if amt == "mmol" else "mg"))
                base = f"{unit}/kg/h" if perkg else f"{unit}/h"
            elif u in _AMT and u != "ml":
                amt, fac = u, _AMT[u]                                                    # plain amount
                base = "units" if u in ("unit", "units", "iu") else ("mmol" if u == "mmol" else "mg")
            elif u in ("kg", "ml"):
                amt, fac, base = u, 1.0, u
            rows.append({"site": site, "unit": r["unit"], "rows": r["rows"], "stays": r["stays"], "kind": r["kind"],
                         "amount_unit": amt, "per_kg": perkg if amt else None, "time_unit": tm, "base_unit": base, "factor": fac})
    return pd.DataFrame(rows)


def pair_check(harmonised_dir, site, a, b, tol=None, min_stays=10):
    """Are two concepts at one site the same measurement? Pairs the hourly values of `a` and `b` by stay and hour (mean within the hour) and
    reports, as counts and summary statistics only: pairs, stays, correlation, the median, 5th and 95th percentile of a - b, and the share of
    pairs within `tol` of each other (tol=None: not reported). Stays with fewer than `min_stays`... are not hidden individually; only the totals
    are shown. If a and b are nearly equal, one of them is redundant and can be dropped."""
    d = Path(harmonised_dir)
    frames = []
    for f in sorted(d.glob(f"{site}_*.parquet")):
        if f.stem.endswith(("_rejected", "_drugs")):
            continue
        t = pd.read_parquet(f, columns=["stay_key", "concept", "hour", "value"], filters=[("concept", "in", [a, b])])
        if len(t):
            frames.append(t)
    if not frames:
        return pd.DataFrame()
    t = pd.concat(frames)
    t["h"] = np.floor(t["hour"].astype("float64"))
    w = t.groupby(["stay_key", "h", "concept"])["value"].mean().unstack("concept").dropna(subset=[a, b])
    if len(w) == 0:
        return pd.DataFrame([{"site": site, "pairs": 0}])
    diff = w[a] - w[b]
    out = {"site": site, "a": a, "b": b, "pairs": len(w), "stays": w.index.get_level_values("stay_key").nunique(),
           "corr": round(float(w[a].corr(w[b])), 4), "median_diff": round(float(diff.median()), 4),
           "p5_diff": round(float(diff.quantile(.05)), 4), "p95_diff": round(float(diff.quantile(.95)), 4)}
    if tol is not None:
        out[f"share_within_{tol}"] = round(float((diff.abs() <= tol).mean()), 4)
    return pd.DataFrame([out])


def availability_released(harmonised_dir, static, sites=C.SITES):
    """Stay x concept table of booleans computed from the harmonised files (what a user of the release would see): does the stay have at least one
    row of the concept? <NA> means the site has no source for the concept (not collected), False means collected but absent for the stay. Non-drug
    concepts only; one row per stay of the static table (index site, stay_key). Unlike `concepts.availability` it uses the harmonised data, so
    the window rule, the unit filters and the rejected rows are already applied."""
    names = [n for n in C.CONCEPTS if C.CONCEPTS[n]["group"] != "drugs"]
    parts = []
    for site in sites:
        keys = static.loc[static["site"] == site, "stay_key"].astype(str).tolist()
        have = {}
        for f in sorted(Path(harmonised_dir).glob(f"{site}_*.parquet")):
            if f.stem.endswith(("_rejected", "_drugs")):
                continue
            t = pd.read_parquet(f, columns=["stay_key", "concept"]).drop_duplicates()
            for c, g in t.groupby("concept"):
                have.setdefault(c, set()).update(g["stay_key"].astype(str))
        df = pd.DataFrame(index=pd.MultiIndex.from_product([[site], keys], names=["site", "stay_key"]))
        for n in names:
            if not C.CONCEPTS[n][site]:
                df[n] = pd.array([pd.NA] * len(keys), dtype="boolean")
            else:
                s = have.get(n, set())
                df[n] = pd.array([k in s for k in keys], dtype="boolean")
        parts.append(df)
    return pd.concat(parts)


# ---------------------------------------------------------------------------------------------------------------------------------------
# Are the units and scales the same across sites once age is taken into account?
# ---------------------------------------------------------------------------------------------------------------------------------------
AGE_BANDS = (("<1y", 0, 12), ("1-4y", 12, 60), ("5-11y", 60, 144), ("12y+", 144, 10_000))
_UNIT_FACTORS = {"x10": 10.0, "x100": 100.0, "x1000": 1000.0, "x88.4 (creatinine mg/dL-umol/L)": 88.4, "x18 (glucose mg/dL-mmol/L)": 18.0}
_KPA_CONCEPTS = ("bg_po2", "bg_pco2", "etco2")       # kPa against mmHg (x7.5) is only offered for these


def _factor_hint(ratio, concept=""):
    """Name of a common unit factor that `ratio` is within 7% of (either way round), else ''. Only factors of 10 or more are offered for any
    concept (smaller ones match ordinary case-mix differences by chance); kPa against mmHg only for the gas concepts."""
    if not np.isfinite(ratio) or ratio <= 0:
        return ""
    r = max(ratio, 1 / ratio)
    factors = dict(_UNIT_FACTORS)
    if concept in _KPA_CONCEPTS:
        factors["x7.5 (kPa-mmHg)"] = 7.50062
    for label, f in factors.items():
        if abs(r / f - 1) < 0.07:
            return label
    return ""


def _stay_medians(harmonised_dir, static, sites, concepts=None, drop_flags=("range", "outlier")):
    """One row per site, stay and concept: the median of the numeric `value` over the stay, with the stay's age band. Rows flagged as range or
    outlier are left out. Fluids are left out (running totals and flows are not a level)."""
    st = static[["site", "stay_key", "age_months"]].copy()
    st["stay_key"] = st["stay_key"].astype(str)
    st["age_band"] = pd.cut(pd.to_numeric(st["age_months"], errors="coerce"), [b[1] for b in AGE_BANDS] + [AGE_BANDS[-1][2]], right=False,
                            labels=[b[0] for b in AGE_BANDS])
    out = []
    for site in sites:
        for f in sorted(Path(harmonised_dir).glob(f"{site}_*.parquet")):
            if f.stem.endswith(("_rejected", "_drugs", "_fluids")):
                continue
            d = pd.read_parquet(f, columns=["stay_key", "concept", "value", "flag"])
            d = d[d["value"].notna()]
            if concepts is not None:
                d = d[d["concept"].isin(concepts)]
            d = d[~d["flag"].fillna("").isin(drop_flags)]
            d["stay_key"] = d["stay_key"].astype(str)
            m = d.groupby(["stay_key", "concept"], sort=False, observed=True)["value"].median().rename("value").reset_index()
            m.insert(0, "site", site)
            out.append(m)
    m = pd.concat(out, ignore_index=True)
    return m.merge(st, on=["site", "stay_key"], how="left")


def unit_consistency(harmonised_dir, static, sites=C.SITES, concepts=None, min_stays=30, flag_ratio=1.3):
    """One row per numeric concept that at least two sites share: the median of the stays' medians at each site (`med_<site>`), the crude ratio
    of the largest to the smallest, and the age-adjusted ratio: within each age band (<1y, 1-4y, 5-11y, 12y+) where every shared site has at
    least `min_stays` stays, the largest to smallest site median, averaged (geometric, weighted by the smallest site count). `unit_hint` names a
    common unit factor (x10, x88.4 ...) if the adjusted ratio is within 7% of it. `flag` is True when the adjusted ratio is above `flag_ratio`.
    A ratio near 1 after age adjustment says the sites record one quantity in one unit; a large one says a unit, assay or practice difference
    (not which). Counts and medians only. Returns the table, sorted by adjusted ratio."""
    m = _stay_medians(harmonised_dir, static, sites, concepts)
    rows = []
    for c, g in m.groupby("concept", sort=False):
        n = g.groupby("site")["value"].size()
        use = [s for s in sites if n.get(s, 0) >= min_stays]
        if len(use) < 2:
            continue
        g = g[g["site"].isin(use)]
        med = g.groupby("site")["value"].median()
        row = {"concept": c, "sites": ",".join(use), **{f"med_{s}": round(float(med[s]), 4) if s in med.index else np.nan for s in sites},
               **{f"stays_{s}": int(n.get(s, 0)) for s in sites}}
        pos = med[med > 0]
        row["crude_ratio"] = round(float(pos.max() / pos.min()), 3) if len(pos) == len(med) else np.nan
        logs, ws = [], []
        for b, _, _ in AGE_BANDS:
            gb = g[g["age_band"] == b]
            cnt = gb.groupby("site")["value"].size().reindex(use).fillna(0)
            if (cnt < min_stays).any():
                continue
            mb = gb.groupby("site")["value"].median()
            if (mb <= 0).any():
                continue
            logs.append(np.log(mb.max() / mb.min()))
            ws.append(cnt.min())
        row["bands_used"] = len(logs)
        row["adjusted_ratio"] = round(float(np.exp(np.average(logs, weights=ws))), 3) if logs else np.nan
        signed = bool((med <= 0).any())      # a median at or below zero (base excess): a ratio of medians means nothing
        if signed:
            row["adjusted_ratio"] = np.nan
        row["signed"] = signed
        row["unit_hint"] = "" if signed else (_factor_hint(row["adjusted_ratio"], c) or _factor_hint(row["crude_ratio"], c))
        row["flag"] = bool(row["adjusted_ratio"] > flag_ratio) if (logs and not signed) else np.nan
        rows.append(row)
    return pd.DataFrame(rows).sort_values("adjusted_ratio", ascending=False, na_position="last").reset_index(drop=True)


def concept_by_age(harmonised_dir, static, concept, sites=C.SITES, quantiles=(0.1, 0.5, 0.9)):
    """One concept: per site and age band, the number of stays and the quantiles of the stays' medians. For looking at a single concept across
    age (creatinine rises with age, so a site with older children has higher values). Counts and quantiles only."""
    m = _stay_medians(harmonised_dir, static, sites, [concept])
    rows = []
    for (s, b), g in m.groupby(["site", "age_band"], observed=True):
        rows.append({"site": s, "age_band": b, "stays": len(g), **{f"p{int(q * 100)}": round(float(g["value"].quantile(q)), 3) for q in quantiles}})
    return pd.DataFrame(rows).sort_values(["age_band", "site"]).reset_index(drop=True)