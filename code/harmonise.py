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
    if concept == "tidal_volume":
        return _f64(s.str.extract(r"(-?\d+\.?\d*)")[0])
    return _f64(s)


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
            v = _f64(_clean_text(df["value"]))
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
        parts.append(df[["stay", "hour", "value", "value_text"]].assign(source=str(i)))
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["stay", "hour", "value", "value_text", "source"])
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


def harmonise_concept(assembled_dir, site, concept, keep, report=None, window=None):
    """One concept at one site as a long frame (stay_key, concept, hour, value, value_text, flag, source), rules applied.
    keep: Series stay_key (text) -> t0 in UTC for the cohort stays of the site. report: dict of counters (updated)."""
    rep = report if report is not None else {}
    for k in ("rows_read", "rows_in_cohort", "rows_bad_time", "rows_non_numeric", "rows_outside_window", "rows_set_missing", "rows_converted", "rows_derived", "rows_dup"):
        rep.setdefault(k, 0)
    flag = None                                   # None: flags set row by row below
    if site == "GOSH" and concept == "bg_base_excess":
        ph = _paired(assembled_dir, site, "bg_ph", keep).rename(columns={"value": "ph"})
        hco3 = _paired(assembled_dir, site, "bg_hco3", keep).rename(columns={"value": "hco3"})
        m = ph.merge(hco3, on=["stay_key", "hour"])
        m = m[m["ph"].between(6.5, 7.8) & m["hco3"].between(1, 60)]
        df = m.assign(value=C.derive_base_excess(m["ph"], m["hco3"]), value_text=pd.NA, source="0")[["stay_key", "hour", "value", "value_text", "source"]]
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
            same = (m["value"] == m["sys"]).fillna(False).to_numpy(dtype=bool)
            rep["rows_set_missing"] += int(same.sum())
            df = df[~same]
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
    if window is not None:
        outside = (df["hour"] < window["start_h"]) | (df["hour"] > df["stay_key"].map(window["end"]))
        rep["rows_outside_window"] += int(outside.sum())
        df = df[~outside]
    df = df.assign(concept=concept)
    n0 = len(df)
    df = df.drop_duplicates(["stay_key", "hour", "value", "value_text", "source"])
    rep["rows_dup"] += n0 - len(df)
    df["hour"] = df["hour"].astype("float32")
    df["value"] = df["value"].astype("float32")
    return df[["stay_key", "concept", "hour", "value", "value_text", "flag", "source"]]


# ------------------------------------------------------------------ all concepts
def harmonise_all(assembled_dir, static, out_dir, concepts=None, sites=C.SITES, groups_skip=SKIP_GROUPS, apply_window=True):
    """Write one parquet per site and group to out_dir (derived/harmonised/) and return a counts-only report: per site and concept the
    stays and rows kept, rows read, rows outside the cohort, with a bad time or outside the stay window (stay_window), rows set missing or converted or derived, and the
    percentiles of `hour` (5th, 50th, 95th) as a check on the clock."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    co = cohort(static)
    wins = stay_window(assembled_dir, static) if apply_window else None
    names = [n for n in C.CONCEPTS if (n in concepts if concepts else C.CONCEPTS[n]["group"] not in groups_skip)]
    rows = []
    for site in sites:
        keep = co[co["site"] == site].set_index("stay_key")["t0_utc"]
        win = None if wins is None else {"start_h": -PRE_HOURS, "end": wins[wins["site"] == site].set_index("stay_key")["end_h"]}
        by_group = {}
        for n in names:
            if not C.CONCEPTS[n].get(site):
                continue
            rep = {}
            df = harmonise_concept(assembled_dir, site, n, keep, rep, window=win)
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


# ====================================================================================================================================
# Fluids: hourly ml (value = the hourly amount recorded at `hour`; which end of the hour each source's time marks is not documented), long format.
#   intake_total   RBH Total_In_ex_dialysis (as recorded); SMH io 'Total In 24hr' hourTotal; GOSH differenced Total_fluids (pre-Epic)
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