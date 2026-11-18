"""Do the demographics times agree with the PICANet times? (RBH and SMH)

At GOSH a stay is defined by the PICANet admission and discharge times. At RBH and SMH the manifest
takes the admission time from the demographics table and uses PICANet only for membership. Before
pooling the sites we need one stay definition, so this measures how far the two sources disagree.

Counts only: nothing printed is an ID, date or row value.

Notebook use:
    import picanet_times as PT
    PT.check_times(rbh_dir, "RBH", demo_adm="PICUadm_dttm", los_col="LOSHours", los_unit="hours",
                   manifest=rbh_m)
    PT.check_times(smh_dir, "SMH", demo_adm="inTime", manifest=smh_m)
If a column name is wrong, the function lists the date-like columns of each table and stops.
"""
from pathlib import Path

import pandas as pd

import inventory as I
import manifest as M

SITES = {
    "RBH": {"key": "studyID", "demo": "ai_picu_demographics.csv", "pic": "ai_picu_piccanet.csv"},
    "SMH": {"key": "encounterId", "demo": "ai_picu_demographics.csv", "pic": "ai_picu_piccanet.csv"},
}


def _ns(s):
    return s.astype("datetime64[ns]")


def _stay_key(site, df, key_col):
    return M.rbh_stay_key(df[key_col]) if site == "RBH" else df[key_col].astype("string")


def _series(site, df, key_col, col):
    """One time per stay (first row), indexed by stay key."""
    t = _ns(I.parse_dates(df[col])[0])
    s = pd.Series(t.to_numpy(), index=_stay_key(site, df, key_col).to_numpy())
    return s[~s.index.duplicated(keep="first")]


def _buckets(d, name):
    """d: timedelta Series (first minus second). Counts of how far apart the two sources are."""
    h = d.dt.total_seconds() / 3600
    a = h.abs()
    print(f"  {name}: compared {len(h):,}; identical to the minute {int((a < 1/60).sum()):,}; "
          f"under 1 h {int(((a >= 1/60) & (a < 1)).sum()):,}; 1 to 24 h {int(((a >= 1) & (a < 24)).sum()):,}; "
          f"24 h or more {int((a >= 24).sum()):,}")
    plus = int((((h - 1).abs() < 1/60) | ((h + 1).abs() < 1/60)).sum())
    print(f"      exactly one hour apart (clock or time-zone shift): {plus:,}; "
          f"first later {int((h > 1/60).sum()):,}, first earlier {int((h < -1/60).sum()):,}")


def check_times(src_dir, site, demo_adm, pic_adm="AdDateTime", pic_dis="UnitDisDateTime",
                demo_dis=None, los_col=None, los_unit="hours", manifest=None):
    """demo_adm / demo_dis: columns in the demographics table. pic_adm / pic_dis: columns in the
    new PICANet table. los_col: a length-of-stay column in the PICANet table (los_unit 'hours' or
    'days'). manifest: the site manifest, to repeat the key counts on its stays only."""
    site = site.upper()
    cfg = SITES[site]
    src = Path(src_dir).expanduser()
    demo, _ = I.read(src / cfg["demo"])
    pic, _ = I.read(src / cfg["pic"])

    need = [("demographics", demo, demo_adm), ("PICANet", pic, pic_adm)]
    if demo_dis:
        need.append(("demographics", demo, demo_dis))
    bad = [(n, c) for n, df, c in need if c and c not in df.columns]
    if bad:
        print(f"Column(s) not found: {bad}. Date-like columns in each table:")
        for n, df in [("demographics", demo), ("PICANet", pic)]:
            print(f"  {n}: {[c for c in df.columns if I.DATE_NAME.search(c)] or 'none by name'}")
            print(f"      all columns: {list(df.columns)}")
        return None

    d_adm = _series(site, demo, cfg["key"], demo_adm)
    p_adm = _series(site, pic, cfg["key"], pic_adm)
    both = d_adm.index.intersection(p_adm.index)
    print(f"{site}: stays in demographics {len(d_adm):,}; in PICANet {len(p_adm):,}; in both {len(both):,}")

    print("\n== 1. Admission time: demographics minus PICANet")
    ok = both[d_adm[both].notna() & p_adm[both].notna()]
    _buckets(d_adm[ok] - p_adm[ok], "all stays in both")
    if manifest is not None:
        mk = set(manifest["stay_key" if site == "RBH" else "encounterId"].astype("string"))
        okm = [k for k in ok if k in mk]
        _buckets(d_adm[okm] - p_adm[okm], "manifest stays")
        y_d, y_p = d_adm[okm].dt.year, p_adm[okm].dt.year
        print(f"  admission year differs between the two sources: {int((y_d != y_p).sum()):,}")
        print(f"  manifest stays whose PICANet admission is before 2013: {int((y_p < M.MIN_YEAR).sum()):,}")
    y_d, y_p = d_adm[ok].dt.year, p_adm[ok].dt.year
    print(f"  all stays in both: demographics year >= {M.MIN_YEAR} but PICANet year earlier: "
          f"{int(((y_d >= M.MIN_YEAR) & (y_p < M.MIN_YEAR)).sum()):,}; the reverse: "
          f"{int(((y_d < M.MIN_YEAR) & (y_p >= M.MIN_YEAR)).sum()):,}")

    print("\n== 2. Discharge time and length of stay (PICANet)")
    if pic_dis not in pic.columns:
        print(f"  {pic_dis} not in the PICANet table. Date-like columns: "
              f"{[c for c in pic.columns if I.DATE_NAME.search(c)] or 'none by name'}; all columns: {list(pic.columns)}")
        return None
    p_dis = _series(site, pic, cfg["key"], pic_dis)
    k = p_adm.index.intersection(p_dis.index)
    dur = (p_dis[k] - p_adm[k]).dt.total_seconds() / 86400
    print(f"  PICANet discharge present on {int(p_dis[k].notna().sum()):,} of {len(k):,} stays; "
          f"discharge before admission: {int((dur < 0).sum()):,}; "
          f"median stay {dur.median():.2f} days; over 100 days: {int((dur > 100).sum()):,}")
    if los_col:
        if los_col not in pic.columns:
            print(f"  {los_col} not in PICANet table. Columns: {list(pic.columns)}")
        else:
            los = pd.Series(pd.to_numeric(pic[los_col], errors="coerce").to_numpy(),
                            index=_stay_key(site, pic, cfg["key"]).to_numpy())
            los = los[~los.index.duplicated(keep="first")]
            los_d = los[k] / (24 if los_unit == "hours" else 1)
            okl = los_d.notna() & dur.notna()
            print(f"  discharge minus admission equals {los_col} (within 0.02 d): "
                  f"{int(((dur[okl] - los_d[okl]).abs() < 0.02).sum()):,} of {int(okl.sum()):,}")
    if demo_dis:
        d_dis = _series(site, demo, cfg["key"], demo_dis)
        kk = d_dis.index.intersection(p_dis.index)
        kk = kk[d_dis[kk].notna() & p_dis[kk].notna()]
        print("\n== 3. Discharge time: demographics minus PICANet")
        _buckets(d_dis[kk] - p_dis[kk], "all stays in both")
    return None


def discharge_diagnostic(src_dir, site, pic_adm="AdDateTime", pic_dis="UnitDisDateTime", los_col="LOSHours"):
    """Why is the PICANet discharge time odd? Shows the formats of the two columns (letters as a,
    digits as d), then how discharge minus admission compares with the length-of-stay column.
    Counts only."""
    site = site.upper()
    cfg = SITES[site]
    pic, _ = I.read(Path(src_dir).expanduser() / cfg["pic"])
    for c in (pic_adm, pic_dis):
        s = pic[c]
        vc = I.shapes_of(s).value_counts().head(3)
        _, how = I.parse_dates(s)
        print(f"{c}: missing {int(s.isna().sum()):,} of {len(s):,}; parsed as {how}; shapes: "
              + "; ".join(f"{k} ({v})" for k, v in vc.items()))
    a, b = _ns(I.parse_dates(pic[pic_adm])[0]), _ns(I.parse_dates(pic[pic_dis])[0])
    h = (b - a).dt.total_seconds() / 3600
    ok = h.notna()
    print(f"\ndischarge minus admission, hours ({int(ok.sum()):,} rows):")
    print(f"  exactly zero {int((h[ok] == 0).sum()):,}; negative {int((h[ok] < 0).sum()):,}; "
          f"positive {int((h[ok] > 0).sum()):,}")
    for lo, hi in [(0, 1), (1, 24), (24, 168), (168, 1e9)]:
        print(f"  |difference| from {lo} to {hi if hi < 1e9 else 'more'} h: "
              f"negative {int(((-h[ok] >= lo) & (-h[ok] < hi) & (h[ok] < 0)).sum()):,}; "
              f"positive {int(((h[ok] >= lo) & (h[ok] < hi) & (h[ok] > 0)).sum()):,}")
    if los_col in pic.columns:
        los = pd.to_numeric(pic[los_col], errors="coerce")
        k = ok & los.notna()
        print(f"\n{los_col}: present on {int(los.notna().sum()):,} rows; median {los[k].median():.1f}")
        r = (h[k] - los[k]).abs()
        print(f"  |discharge - admission - {los_col}| under 1 h: {int((r < 1).sum()):,}; "
              f"1 to 24 h: {int(((r >= 1) & (r < 24)).sum()):,}; 24 h or more: {int((r >= 24).sum()):,}")
        adm_plus = a[k] + pd.to_timedelta(los[k], unit="h")
        print(f"  admission + {los_col} against PICANet discharge: same day {int((adm_plus.dt.normalize() == b[k].dt.normalize()).sum()):,} of {int(k.sum()):,}")


def first_vitals_offset(src_dir, demo_adm, manifest, pic_adm="AdDateTime",
                        vitals_file="ai_picu_vitals.csv", vitals_time="chartTime"):
    """RBH only. For each manifest stay: hours from each candidate admission time (demographics,
    PICANet) to the stay's first vitals row. The better t0 puts the first vitals nearer zero.
    Counts only."""
    src = Path(src_dir).expanduser()
    demo, _ = I.read(src / SITES["RBH"]["demo"])
    pic, _ = I.read(src / SITES["RBH"]["pic"])
    t_d = _series("RBH", demo, "studyID", demo_adm)
    t_p = _series("RBH", pic, "studyID", pic_adm)
    v, _ = I.read(src / vitals_file, usecols=["studyID", vitals_time])
    v["_t"] = _ns(I.parse_dates(v[vitals_time])[0])
    v["_k"] = M.rbh_stay_key(v["studyID"])
    first = v.dropna(subset=["_t"]).groupby("_k")["_t"].min()
    keys = [k for k in manifest["stay_key"] if k in first.index]
    print(f"manifest stays with vitals: {len(keys):,}")
    for name, t0 in [("demographics admission", t_d), ("PICANet admission", t_p)]:
        kk = [k for k in keys if k in t0.index and pd.notna(t0[k])]
        h = (first[kk] - t0[kk]).dt.total_seconds() / 3600
        print(f"\nfirst vitals minus {name} (hours), {len(kk):,} stays: median {h.median():.2f}; "
              f"5th to 95th percentile {h.quantile(.05):.2f} to {h.quantile(.95):.2f}")
        print(f"  within 1 h of zero: {int((h.abs() <= 1).sum()):,}; first vitals more than 6 h before: "
              f"{int((h < -6).sum()):,}; more than 24 h after: {int((h > 24).sum()):,}")


def discharge_timeofday(src_dir, site, pic_adm="AdDateTime", pic_dis="UnitDisDateTime", los_col="LOSHours"):
    """Hypothesis test: does the PICANet discharge column carry the right time of day but the wrong
    date? Compares its time of day with the time of day of admission + length of stay. Counts only."""
    cfg = SITES[site.upper()]
    pic, _ = I.read(Path(src_dir).expanduser() / cfg["pic"])
    a, b = _ns(I.parse_dates(pic[pic_adm])[0]), _ns(I.parse_dates(pic[pic_dis])[0])
    los = pd.to_numeric(pic[los_col], errors="coerce")
    k = a.notna() & b.notna() & los.notna()
    exp = a[k] + pd.to_timedelta(los[k], unit="h")
    d = (b[k] - exp).dt.total_seconds() / 3600
    fold = ((d + 12) % 24) - 12            # difference in time of day, -12 to +12 h
    print(f"{int(k.sum()):,} rows with admission, discharge and {los_col}")
    print(f"  time of day of discharge vs admission + {los_col}: within 5 min {int((fold.abs() <= 5/60).sum()):,}; "
          f"within 1 h {int((fold.abs() <= 1).sum()):,}; more than 6 h apart {int((fold.abs() > 6).sum()):,}")
    print(f"  discharge on the same calendar date as admission: {int((b[k].dt.normalize() == a[k].dt.normalize()).sum()):,}; "
          f"as admission + {los_col}: {int((b[k].dt.normalize() == exp.dt.normalize()).sum()):,}")


def check_los(src_dir, site, pic_los="LOSHours", out_file="ai_picu_outcomes.csv", out_los="LOS"):
    """How does the outcomes table's length of stay compare with PICANet's, per stay? Tries the
    same unit and days-against-hours. Counts only."""
    site = site.upper()
    cfg = SITES[site]
    src = Path(src_dir).expanduser()
    pic, _ = I.read(src / cfg["pic"])
    out, _ = I.read(src / out_file)
    if out_los not in out.columns:
        print(f"{out_los} not in {out_file}. Columns: {list(out.columns)}")
        return
    p = pd.Series(pd.to_numeric(pic[pic_los], errors="coerce").to_numpy(), index=_stay_key(site, pic, cfg["key"]).to_numpy())
    o = pd.Series(pd.to_numeric(out[out_los], errors="coerce").to_numpy(), index=_stay_key(site, out, cfg["key"]).to_numpy())
    p, o = p[~p.index.duplicated()], o[~o.index.duplicated()]
    k = p.index.intersection(o.index)
    k = k[p[k].notna() & o[k].notna()]
    print(f"stays with both: {len(k):,}; PICANet {pic_los} median {p[k].median():.1f}; outcomes {out_los} median {o[k].median():.1f}")
    for name, x in [("same unit", o[k]), ("outcomes in days (x24)", o[k] * 24)]:
        r = (x - p[k]).abs()
        print(f"  {name}: within 1 h of PICANet {int((r < 1).sum()):,}; 1 to 24 h {int(((r >= 1) & (r < 24)).sum()):,}; "
              f"24 h or more {int((r >= 24).sum()):,}")
    print(f"  stays in PICANet without {pic_los}: {int(p.isna().sum()):,}; of these with {out_los} in outcomes: "
          f"{int(o.reindex(p.index[p.isna()]).notna().sum()):,}")