"""GOSH: how do the identifier columns link? Prints counts, patterns and ranges only.

Nothing printed here is an ID, date or row value: ID formats are shown as patterns
(letters -> a, digits -> d) and everything else as counts.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import diagnostics as D
import inventory as I


def candidates(gosh_dir, patterns):
    """Print the relative paths under gosh_dir that match each regex (case-insensitive)."""
    import re
    files = [p.relative_to(gosh_dir).as_posix() for p in Path(gosh_dir).rglob("*") if p.is_file()]
    for pat in patterns:
        print(f"--- {pat}")
        for f in sorted(f for f in files if re.search(pat, f, re.I)):
            print("   ", f)


def _pat(s, n=6):
    vc = I.shapes_of(s).value_counts()
    return "; ".join(f"{k}: {v}" for k, v in vc.head(n).items()) or "all missing"


def _dt(s):
    return I.parse_dates(s)[0]


def _overlap(a, b, name_a, name_b):
    a, b = set(a.dropna().unique()), set(b.dropna().unique())
    print(f"  {name_a}: {len(a):,} distinct; {name_b}: {len(b):,}; "
          f"shared {len(a & b):,} ({100*len(a & b)/max(len(a),1):.1f}% of {name_a}, "
          f"{100*len(a & b)/max(len(b),1):.1f}% of {name_b})")


def check_links(gosh_dir, picanet, picanet_epr, archived, hr_file, parquet, pre_hours=6):
    """All file arguments are paths relative to gosh_dir."""
    d = Path(gosh_dir)
    pic = I.read(d / picanet)[0]
    epr = I.read(d / picanet_epr)[0]
    arc = I.read(d / archived)[0]
    hr = I.read(d / hr_file, usecols=["project_id", "admission_identifier", "observation_datetime"])[0]
    pq = I.read(d / parquet, usecols=["patient_id", "encounter_id", "hour_timestamp"])[0]

    print("\n== 1. ID formats (patterns only)")
    for name, s in [("PICANet project_id", pic["project_id"]),
                    ("HR project_id", hr["project_id"]),
                    ("HR admission_identifier", hr["admission_identifier"]),
                    ("parquet patient_id", pq["patient_id"]),
                    ("parquet encounter_id", pq["encounter_id"])]:
        print(f"  {name}: {_pat(s)}  | missing {100*s.isna().mean():.1f}%")

    print("\n== 2. Do the keys match across tables?")
    _overlap(pic["project_id"], hr["project_id"], "PICANet project_id", "HR project_id")
    _overlap(hr["project_id"], pq["patient_id"], "HR project_id", "parquet patient_id")
    _overlap(hr["admission_identifier"], pq["encounter_id"], "HR admission_identifier", "parquet encounter_id")

    print("\n== 3. admission_identifier structure in the HR file")
    nn = hr.dropna(subset=["admission_identifier"])
    print(f"  rows with admission_identifier: {len(nn):,} of {len(hr):,} ({100*len(nn)/len(hr):.1f}%)")
    per_pt = nn.groupby("project_id")["admission_identifier"].nunique()
    print(f"  admissions per patient: min {per_pt.min()}, median {per_pt.median():g}, max {per_pt.max()}")
    pic_ok = pic.dropna(subset=["project_id"])
    print(f"  distinct admission_identifier: {nn['admission_identifier'].nunique():,}; "
          f"PICANet rows with project_id: {len(pic_ok):,}")
    per_adm = nn.groupby("admission_identifier")["project_id"].nunique()
    print(f"  patients per admission_identifier: max {per_adm.max()}  (1 = identifier is not shared across patients)")

    print("\n== 4. PICANet main vs _eprweights vs archived mapping file")
    print(f"  rows: main {len(pic):,}; eprweights {len(epr):,}; archived {len(arc):,}")
    print(f"  columns only in eprweights: {sorted(set(epr.columns) - set(pic.columns))}")
    print(f"  columns only in main: {sorted(set(pic.columns) - set(epr.columns))}")
    _overlap(pic["project_id"], epr["project_id"], "main project_id", "eprweights project_id")
    _overlap(pic["project_id"], arc["project_id"], "main project_id", "archived project_id")
    pic["_start"], pic["_end"] = _dt(pic["AdDateTime"]), _dt(pic["UnitDisDateTime"])
    epr["_start"] = _dt(epr["AdDateTime"])
    arc["_start"], arc["_end"] = _dt(arc["start_datetime"]), _dt(arc["end_datetime"])
    key = lambda df, s: df["project_id"].astype(str) + "|" + df[s].dt.floor("min").astype(str)
    ks_main, ks_epr, ks_arc = key(pic, "_start"), key(epr, "_start"), key(arc, "_start")
    print(f"  (project_id, admission minute) keys in main: {ks_main.nunique():,}; "
          f"in both main and eprweights: {len(set(ks_main) & set(ks_epr)):,}; "
          f"in both main and archived: {len(set(ks_main) & set(ks_arc)):,}")
    print(f"  duplicate keys within main: {int(ks_main.duplicated().sum())}")
    cols = [c for c in arc.columns if c in epr.columns and c not in ("project_id",)]
    print(f"  columns shared by archived and eprweights: {len(cols)}")

    print(f"\n== 5. HR rows against PICANet windows (start - {pre_hours} h to discharge)")
    w = pic.dropna(subset=["project_id", "_start", "_end"]).copy()
    w["_ws"] = w["_start"] - pd.Timedelta(hours=pre_hours)
    w = w.reset_index().rename(columns={"index": "_row"}).sort_values("_ws")
    h = hr.dropna(subset=["project_id", "observation_datetime"]).copy()
    h["_t"] = _dt(h["observation_datetime"])
    h = h.dropna(subset=["_t"]).sort_values("_t")
    m = pd.merge_asof(h, w[["project_id", "_ws", "_end", "_row"]], left_on="_t", right_on="_ws",
                      by="project_id", direction="backward")
    inside = m["_row"].notna() & (m["_t"] <= m["_end"])
    has_id = m["admission_identifier"].notna()
    print(f"  HR rows: {len(m):,}; inside a PICANet window: {100*inside.mean():.1f}%")
    print(f"  agreement with admission_identifier: inside & id {int((inside & has_id).sum()):,}; "
          f"inside & no id {int((inside & ~has_id).sum()):,}; "
          f"outside & id {int((~inside & has_id).sum()):,}; outside & no id {int((~inside & ~has_id).sum()):,}")
    n_adm = m.loc[inside, "_row"].nunique()
    print(f"  PICANet admissions with at least one HR row inside the window: {n_adm:,} of {len(w):,}")
    print(f"  PICANet admissions with at least one HR row carrying an admission_identifier: "
          f"{m.loc[has_id & m['_row'].notna(), '_row'].nunique():,}")

    print("\n== 6. Parquet against PICANet")
    pqe = pq.dropna(subset=["encounter_id"])
    print(f"  parquet encounters: {pqe['encounter_id'].nunique():,}; PICANet admissions with project_id: {len(w):,}")
    per_enc = pqe.groupby("encounter_id")["patient_id"].nunique()
    print(f"  patients per encounter_id: max {per_enc.max()}")
    t = _dt(pq["hour_timestamp"]).dropna()
    print(f"  hour_timestamp range: {t.min().date()} to {t.max().date()}")
    return {"picanet_windows": w, "hr_matched": m[["project_id", "_t", "_row", "admission_identifier"]]}


def check_windows(gosh_dir, archived, parquet, links, pre_hours=6):
    """Follow-up to check_links. `links` is the dict it returned (kept in memory only)."""
    d = Path(gosh_dir)
    w, m = links["picanet_windows"], links["hr_matched"].copy()
    arc = I.read(d / archived)[0].dropna(subset=["project_id"])
    arc["_start"], arc["_end"] = _dt(arc["start_datetime"]), _dt(arc["end_datetime"])
    arc = arc.dropna(subset=["_start", "_end"])
    arc["_ws"] = arc["_start"] - pd.Timedelta(hours=pre_hours)
    arc = arc.reset_index(drop=True).reset_index().rename(columns={"index": "_arow"}).sort_values("_ws")
    has_id = m["admission_identifier"].notna()

    print("\n== A. Suffix of admission_identifier vs encounter_id (zero-padding?)")
    pad = lambda s: s.dropna().astype(str).str.replace(r"-(\d)$", r"-0\1", regex=True)
    pq = I.read(d / parquet, usecols=["encounter_id"])[0]["encounter_id"]
    _overlap(pad(m["admission_identifier"]), pq, "HR admission_identifier (padded)", "parquet encounter_id")

    print("\n== B. HR rows against the ARCHIVED start/end windows")
    m2 = pd.merge_asof(m.sort_values("_t")[["project_id", "_t", "admission_identifier"]],
                       arc[["project_id", "_ws", "_end", "_arow"]], left_on="_t", right_on="_ws",
                       by="project_id", direction="backward")
    inside = m2["_arow"].notna() & (m2["_t"] <= m2["_end"])
    hid = m2["admission_identifier"].notna()
    print(f"  inside archived window: {100*inside.mean():.1f}% of HR rows")
    print(f"  inside & id {int((inside & hid).sum()):,}; inside & no id {int((inside & ~hid).sum()):,}; "
          f"outside & id {int((~inside & hid).sum()):,}; outside & no id {int((~inside & ~hid).sum()):,}")
    print(f"  archived admissions with an HR row inside: {m2.loc[inside, '_arow'].nunique():,} of {len(arc):,}")

    print("\n== C. Main PICANet start vs archived start, nearest per patient")
    a = w[["project_id", "_start"]].sort_values("_start")
    b = arc[["project_id", "_start"]].rename(columns={"_start": "_astart"}).sort_values("_astart")
    nn = pd.merge_asof(a, b, left_on="_start", right_on="_astart", by="project_id", direction="nearest")
    diff = ((nn["_start"] - nn["_astart"]).abs().dt.total_seconds() / 3600).dropna()
    print(f"  main admissions with an archived start for the same patient: {len(diff):,} of {len(a):,}")
    print(f"  absolute difference: identical to the minute {int((diff < 1/60).sum()):,}; under 1 h {int((diff < 1).sum()):,}; "
          f"1 to 24 h {int(((diff >= 1) & (diff < 24)).sum()):,}; 24 h or more {int((diff >= 24).sum()):,}")

    print("\n== D. HR rows inside the main window but without an identifier: hours since admission start")
    m = m.merge(w[["_row", "_start", "_end"]], on="_row", how="left")
    x = m.loc[~has_id.values & m["_row"].notna().values & (m["_t"] <= m["_end"]).values]
    hrs = (x["_t"] - x["_start"]).dt.total_seconds() / 3600
    print(f"  rows {len(x):,}; hours since start: p1 {hrs.quantile(.01):.1f}, median {hrs.median():.1f}, p99 {hrs.quantile(.99):.1f}")
    with_id = set(m.loc[has_id.values & (m["_t"] <= m["_end"]).values, "_row"].dropna())
    adm = x["_row"].dropna().unique()
    print(f"  admissions involved: {len(adm):,}; of these with no identifier at all: {sum(a not in with_id for a in adm):,}")


def vitals_coverage(gosh_dir, archived, files, pre_hours=6, start_col="start_datetime", end_col="end_datetime"):
    """Admissions with at least one row, per vitals file and in total.
    files: list of paths relative to gosh_dir (each with project_id, admission_identifier,
    observation_datetime). Counts distinct admission_identifier, and, separately, archived
    PICANet windows (start - pre_hours to end) that contain a row, whether or not it has an identifier."""
    d = Path(gosh_dir)
    arc = I.read(d / archived)[0].dropna(subset=["project_id"])
    arc["_start"], arc["_end"] = _dt(arc[start_col]), _dt(arc[end_col])
    arc = arc.dropna(subset=["_start", "_end"])
    arc["_ws"] = arc["_start"] - pd.Timedelta(hours=pre_hours)
    arc = arc.reset_index(drop=True).reset_index().rename(columns={"index": "_arow"}).sort_values("_ws")
    ids, wins, rows = set(), set(), []
    for f in files:
        h = I.read(d / f, usecols=["project_id", "admission_identifier", "observation_datetime"])[0]
        h["_t"] = _dt(h["observation_datetime"])
        h = h.dropna(subset=["project_id", "_t"]).sort_values("_t")
        a = set(h["admission_identifier"].dropna().unique())
        m = pd.merge_asof(h, arc[["project_id", "_ws", "_end", "_arow"]], left_on="_t", right_on="_ws",
                          by="project_id", direction="backward")
        b = set(m.loc[m["_arow"].notna() & (m["_t"] <= m["_end"]), "_arow"])
        ids |= a
        wins |= b
        rows.append({"file": f, "rows": len(h), "admissions by identifier": len(a),
                     "admissions by window": len(b), "cumulative by identifier": len(ids),
                     "cumulative by window": len(wins)})
        del h, m
    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    print(f"\nAny of these files: {len(ids):,} admissions by identifier; "
          f"{len(wins):,} of {len(arc):,} archived windows by time")
    return out


# ---- comparing the three PICANet files ------------------------------------------------
# Renames between files (left name -> right name), used when comparing like with like.
EPR_RENAMES = {"Weight": "weight_picanet",
               "All organ support": "All.organ.support",
               "Organ support free days at day 30": "Organ.support.free.days.at.day.30"}
ARC_RENAMES = {"AdDateTime": "start_datetime", "UnitDisDateTime": "end_datetime"}


def _same(x, y, name):
    """Boolean Series: x and y agree (both present). Dates to the minute, numbers to 1e-6, text case-insensitive."""
    if I.DATE_NAME.search(name) and not pd.api.types.is_numeric_dtype(x):
        x, y = _dt(x).dt.floor("min"), _dt(y).dt.floor("min")
        return x.notna() & y.notna() & (x == y), x.notna(), y.notna()
    xn, yn = pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")
    if xn.notna().sum() >= 0.9 * max(x.notna().sum(), 1) and yn.notna().sum() >= 0.9 * max(y.notna().sum(), 1):
        return xn.notna() & yn.notna() & ((xn - yn).abs() < 1e-6), xn.notna(), yn.notna()
    xs, ys = x.astype("string").str.strip().str.casefold(), y.astype("string").str.strip().str.casefold()
    return xs.notna() & ys.notna() & (xs == ys), xs.notna(), ys.notna()


def _compare_pair(a, b, renames, title):
    rows = []
    for ca in a.columns:
        cb = renames.get(ca, ca)
        if ca.startswith("_") or cb not in b.columns:
            continue
        eq, pa, pb = _same(a[ca].reset_index(drop=True), b[cb].reset_index(drop=True), ca)
        both = int((pa & pb).sum())
        rows.append({"column": ca if ca == cb else f"{ca} / {cb}", "both present": both,
                     "equal": int(eq.sum()), "differ": both - int(eq.sum()),
                     "only left": int((pa & ~pb).sum()), "only right": int((~pa & pb).sum())})
    print(f"\n-- {title}")
    print(pd.DataFrame(rows).to_string(index=False))
    return pd.DataFrame(rows)


def compare_picanet(gosh_dir, picanet, picanet_epr, archived, tol_hours=24):
    """Counts only. How do the main, eprweights and archived PICANet files relate?"""
    d = Path(gosh_dir)
    pic, epr, arc = (I.read(d / f)[0] for f in (picanet, picanet_epr, archived))
    print("== 1. Columns")
    print(f"  main ({len(pic.columns)}): {list(pic.columns)}")
    print(f"  eprweights ({len(epr.columns)}): {list(epr.columns)}")
    print(f"  archived ({len(arc.columns)}): {list(arc.columns)}")
    print("\n== 2. Rows and missing project_id")
    for n, df in [("main", pic), ("eprweights", epr), ("archived", arc)]:
        print(f"  {n}: {len(df):,} rows; project_id missing {int(df['project_id'].isna().sum()):,}; "
              f"{df['project_id'].nunique():,} patients")

    print("\n== 3. main vs eprweights: are the rows the same, in the same order?")
    same_pid = (pic["project_id"].fillna("") == epr["project_id"].fillna("")).mean()
    same_start = (_dt(pic["AdDateTime"]).dt.floor("min") == _dt(epr["AdDateTime"]).dt.floor("min")).mean()
    print(f"  same project_id by row position: {100*same_pid:.2f}%; same admission minute by position: {100*same_start:.2f}%")
    if min(same_pid, same_start) > 0.999:
        a, b = pic, epr
        print("  -> row-aligned; comparing by position")
    else:
        print("  -> not row-aligned; matching on project_id + admission minute")
        pic["_k"] = pic["project_id"] + "|" + _dt(pic["AdDateTime"]).dt.floor("min").astype("string")
        epr["_k"] = epr["project_id"] + "|" + _dt(epr["AdDateTime"]).dt.floor("min").astype("string")
        j = pic.dropna(subset=["project_id"]).drop_duplicates("_k").merge(
            epr.dropna(subset=["project_id"]).drop_duplicates("_k"), on="_k", suffixes=("", "__r"))
        a, b = j[[c for c in pic.columns if c in j.columns]], j[[c + "__r" if c + "__r" in j.columns else c for c in epr.columns if (c + "__r" in j.columns) or c in j.columns]]
        b.columns = [c.removesuffix("__r") for c in b.columns]
    t1 = _compare_pair(a, b, EPR_RENAMES, "main (left) vs eprweights (right), common and renamed columns")
    # weights: three candidate columns in eprweights, placeholder counts
    print("\n  weight columns (missing %, placeholder 999 counts, max):")
    for name, s in [("main Weight", pic.get("Weight")), ("eprweights weight_picanet", epr.get("weight_picanet")),
                    ("eprweights weight_epr", epr.get("weight_epr")), ("eprweights AdmWeight", epr.get("AdmWeight"))]:
        if s is None:
            continue
        sn = pd.to_numeric(s, errors="coerce")
        print(f"    {name}: missing {100*sn.isna().mean():.1f}%; equal to 999: {int((sn == 999).sum()):,}; max {sn.max():g}")

    print("\n== 4. main vs archived: match each main admission to the archived row of the same patient nearest in start time")
    m = pic.dropna(subset=["project_id"]).copy()
    m["_s"] = _dt(m["AdDateTime"])
    m = m.dropna(subset=["_s"]).sort_values("_s")
    ar = arc.dropna(subset=["project_id"]).copy()
    ar["_s"] = _dt(ar["start_datetime"])
    ar = ar.dropna(subset=["_s"]).reset_index().rename(columns={"index": "_aidx"}).sort_values("_s")
    j = pd.merge_asof(m, ar[["project_id", "_s", "_aidx"]].rename(columns={"_s": "_as"}), left_on="_s", right_on="_as",
                      by="project_id", direction="nearest", tolerance=pd.Timedelta(hours=tol_hours))
    ok = j.dropna(subset=["_aidx"])
    print(f"  main admissions matched: {len(ok):,} of {len(j):,}; archived rows used once: "
          f"{ok['_aidx'].nunique():,}; archived rows used by more than one main row: {int(ok['_aidx'].duplicated().sum()):,}")
    print(f"  archived rows not matched to any main admission: {len(arc) - ok['_aidx'].nunique():,} of {len(arc):,}")
    ok = ok.drop_duplicates("_aidx")
    b = arc.loc[ok["_aidx"].astype(int)]
    t2 = _compare_pair(ok.reset_index(drop=True), b.reset_index(drop=True), ARC_RENAMES,
                       "main (left) vs archived (right), common and renamed columns")
    return {"main_vs_epr": t1, "main_vs_archived": t2}


def compare_outcomes(gosh_dir, picanet, archived, tol_hours=24):
    """Main vs archived PICANet: where and how do discharge status, PIM and times differ? Counts only."""
    d = Path(gosh_dir)
    pic, arc = I.read(d / picanet)[0], I.read(d / archived)[0]
    m = pic.dropna(subset=["project_id"]).copy()
    m["_s"], m["_e"] = _dt(m["AdDateTime"]), _dt(m["UnitDisDateTime"])
    m = m.dropna(subset=["_s"]).sort_values("_s")
    ar = arc.dropna(subset=["project_id"]).copy()
    ar["_as"], ar["_ae"] = _dt(ar["start_datetime"]), _dt(ar["end_datetime"])
    ar = ar.dropna(subset=["_as"]).reset_index().rename(columns={"index": "_aidx"}).sort_values("_as")
    j = pd.merge_asof(m, ar[["project_id", "_as", "_ae", "_aidx", "UnitDisStatusDescription", "PIM"]]
                      .rename(columns={"UnitDisStatusDescription": "_astatus", "PIM": "_apim"}),
                      left_on="_s", right_on="_as", by="project_id", direction="nearest",
                      tolerance=pd.Timedelta(hours=tol_hours)).dropna(subset=["_aidx"])
    print(f"matched admissions: {len(j):,}")

    st_m, st_a = j["UnitDisStatusDescription"].astype("string"), j["_astatus"].astype("string")
    sd = (st_m != st_a) & st_m.notna() & st_a.notna()
    print("\n== 1. Discharge status: rows = main, columns = archived (counts)")
    print(pd.crosstab(st_m.fillna("(missing)"), st_a.fillna("(missing)")).to_string())

    pim_m, pim_a = pd.to_numeric(j["PIM"], errors="coerce"), pd.to_numeric(j["_apim"], errors="coerce")
    pd_ = (pim_m - pim_a).abs()
    pdiff = pd_ > 1e-6
    print("\n== 2. PIM differences (absolute difference, admissions that differ)")
    print(f"  differ: {int(pdiff.sum()):,}; of these: < 0.01: {int((pd_[pdiff] < .01).sum()):,}; "
          f"0.01 to 0.1: {int(((pd_[pdiff] >= .01) & (pd_[pdiff] < .1)).sum()):,}; "
          f">= 0.1: {int((pd_[pdiff] >= .1).sum()):,}; median {pd_[pdiff].median():.3g}; max {pd_[pdiff].max():.3g}")
    print(f"  main PIM range {pim_m.min():g} to {pim_m.max():g}; archived {pim_a.min():g} to {pim_a.max():g}")

    dend = (j["_e"] - j["_ae"]).dt.total_seconds() / 3600
    dstart = (j["_s"] - j["_as"]).dt.total_seconds() / 3600
    print("\n== 3. End and start differences, hours (main minus archived)")
    for name, x in [("end", dend), ("start", dstart)]:
        a = x.abs()
        print(f"  {name}: identical {int((a < 1/60).sum()):,}; main later {int((x > 1/60).sum()):,}; "
              f"main earlier {int((x < -1/60).sum()):,}; < 1 h {int(((a >= 1/60) & (a < 1)).sum()):,}; "
              f"1 to 24 h {int(((a >= 1) & (a < 24)).sum()):,}; 1 to 7 days {int(((a >= 24) & (a < 168)).sum()):,}; "
              f">= 7 days {int((a >= 168).sum()):,}")

    print("\n== 4. Do the disagreements coincide? (counts)")
    ed, sdif = dend.abs() > 1/60, dstart.abs() > 1/60
    print(pd.DataFrame({"status differs": sd, "end differs": ed, "start differs": sdif, "PIM differs": pdiff})
          .value_counts().rename("n").reset_index().to_string(index=False))

    print("\n== 5. Which file's times agree with the main file's own `los` (days)?")
    los = pd.to_numeric(j["los"], errors="coerce")
    own = (j["_e"] - j["_s"]).dt.total_seconds() / 86400
    arch = (j["_ae"] - j["_as"]).dt.total_seconds() / 86400
    for name, x in [("main end - main start", own), ("archived end - archived start", arch)]:
        ok = (x - los).abs() < 0.02
        print(f"  {name} equals los (within 0.02 d): {int(ok.sum()):,} of {int(los.notna().sum()):,}"
              f"; among rows where end differs: {int(ok[ed].sum()):,} of {int(ed.sum()):,}")
    return j[["project_id", "_s", "_e", "_as", "_ae", "UnitDisStatusDescription", "_astatus"]]


def _auc(score, label):
    ok = score.notna() & label.notna()
    s, y = score[ok], label[ok].astype(bool)
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = s.rank()
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def compare_status(gosh_dir, picanet, archived, tol_hours=24):
    """Which file's discharge status is plausible? PIM discrimination, deaths on last admission,
    and disagreements by number of admissions per patient. Counts and AUCs only."""
    d = Path(gosh_dir)
    pic, arc = I.read(d / picanet)[0], I.read(d / archived)[0]
    m = pic.dropna(subset=["project_id"]).copy()
    m["_s"] = _dt(m["AdDateTime"])
    m = m.dropna(subset=["_s"]).sort_values("_s")
    ar = arc.dropna(subset=["project_id"]).copy()
    ar["_as"] = _dt(ar["start_datetime"])
    ar = ar.dropna(subset=["_as"]).reset_index().rename(columns={"index": "_aidx"}).sort_values("_as")
    j = pd.merge_asof(m, ar[["project_id", "_as", "_aidx", "UnitDisStatusDescription", "PIM"]]
                      .rename(columns={"UnitDisStatusDescription": "_astatus", "PIM": "_apim"}),
                      left_on="_s", right_on="_as", by="project_id", direction="nearest",
                      tolerance=pd.Timedelta(hours=tol_hours)).dropna(subset=["_aidx"]).reset_index(drop=True)
    dead_m = j["UnitDisStatusDescription"].astype("string").str.casefold().eq("dead")
    dead_a = j["_astatus"].astype("string").str.casefold().eq("dead")
    pim_m, pim_a = pd.to_numeric(j["PIM"], errors="coerce"), pd.to_numeric(j["_apim"], errors="coerce")

    print("== 1. How well does PIM discriminate each status? (AUC; 0.5 = no better than chance)")
    for sname, dead in [("main status", dead_m), ("archived status", dead_a)]:
        print(f"  {sname}: PIM(main) {_auc(pim_m, dead):.3f}; PIM(archived) {_auc(pim_a, dead):.3f}; "
              f"deaths {int(dead.sum()):,}")
    both, only_m, only_a = dead_m & dead_a, dead_m & ~dead_a, dead_a & ~dead_m
    print(f"  median PIM(main): dead in both {pim_m[both].median():.3f}; dead only in main {pim_m[only_m].median():.3f}; "
          f"dead only in archived {pim_m[only_a].median():.3f}; alive in both {pim_m[~dead_m & ~dead_a].median():.3f}")

    print("\n== 2. Does the death sit on the patient's last admission?")
    j["_rank_from_end"] = j.groupby("project_id")["_s"].rank(ascending=False, method="first")
    n_adm = j.groupby("project_id")["_s"].transform("size")
    for sname, dead in [("main", dead_m), ("archived", dead_a)]:
        dd = j[dead]
        per_pt = dd.groupby("project_id").size()
        print(f"  {sname}: dead admissions {len(dd):,}; not the patient's last admission {int((dd['_rank_from_end'] > 1).sum()):,}; "
              f"patients with more than one dead admission {int((per_pt > 1).sum()):,}")

    print("\n== 3. Status disagreements by admissions per patient (counts)")
    dis = dead_m != dead_a
    t = pd.DataFrame({"admissions per patient": n_adm.clip(upper=4).astype(int).astype(str).replace({"4": "4+"}),
                      "disagree": dis})
    print(t.groupby("admissions per patient")["disagree"].agg(["size", "sum"]).rename(
        columns={"size": "admissions", "sum": "status differs"}).to_string())
    return j[["project_id", "_s", "_rank_from_end"]].assign(dead_main=dead_m, dead_arch=dead_a)


# ---- lab coverage by admission year ---------------------------------------------------
def lab_coverage_by_year(gosh_dir, manifest, folder="merged_lab_values", files=None,
                         time_col="observation_datetime", pre_hours=0):
    """Share of the eligible GOSH stays (manifest from manifest.gosh_manifest) that have at least one row in
    each lab file, by admission year, plus a column 'any lab file'. Rows are attached to stays by patient and
    time (manifest.gosh_eligible_rows). files: names inside `folder`; default every CSV there that has
    project_id and the time column. Returns years as the index; counts and shares only."""
    import manifest as M
    d = Path(gosh_dir) / folder
    names = files or sorted(p.name for p in d.glob("*.csv"))
    keys, skipped = {}, []
    for n in names:
        try:
            h, _ = I.read(d / n, usecols=["project_id", time_col])
        except ValueError:                       # a column is missing in this file
            skipped.append(n)
            continue
        e = M.gosh_eligible_rows(h, manifest, time_col=time_col, pre_hours=pre_hours)
        keys[n.replace(".csv", "").replace("merged_", "")] = set(e["stay_id"])
        del h, e
    if skipped:
        print(f"skipped (no project_id or {time_col}): {len(skipped)} files: {skipped}")
    keys["any lab file"] = set().union(*keys.values()) if keys else set()
    return D.coverage_by_year(manifest, keys, key_col="stay_id")