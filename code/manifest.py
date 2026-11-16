"""Stay manifests: which stays are eligible, one row per stay, per site.

Rules (agreed 2026-11-15):
  1. admitted in or after MIN_YEAR (2013);
  2. in the NEW PICANet file (the old PICANet file is not used);
     GOSH: in the _eprweights PICANet file with a project_id (the main file is identical, the
     archived file has unreliable discharge status and is not used);
  3. has real vitals (at least one vitals row with a chart time; GOSH: at least one row in the
     core vitals files between admission start and discharge, attached by patient and time).
The manifest holds only stays that pass all three. The waterfall records how many
stays each rule removed. Raw files are never modified.

Notebook use (inventory.py must be importable as `inventory`):
    import manifest as M
    rbh_m, rbh_w = M.rbh_manifest(rbh_dir)
    smh_m, smh_w = M.smh_manifest(smh_dir)
    M.print_waterfall(rbh_w, "RBH"); M.print_waterfall(smh_w, "SMH")
    rbh_m.to_csv(open_picu_dir/"RBH_manifest.csv", index=False)
    vit = M.eligible_rows(pd.read_csv(rbh_dir/"ai_picu_vitals.csv"), rbh_m, "RBH")
    gosh_m, gosh_w = M.gosh_manifest(gosh_dir)
    M.print_waterfall(gosh_w, "GOSH")
"""
import pandas as pd

import inventory as I

MIN_YEAR = 2013
RBH_TIME_FMT = "%d%b%Y:%H:%M:%S.%f"      # 01JAN2020:12:34:56.78


# ---------------------------------------------------------------- helpers
def rbh_stay_key(study_id):
    """'NND:12345:1234567890' -> '12345:1234567890' (patient + admission time, prefix removed).
    The same stay can carry NIC in one table and NND in another, so never join on the prefix."""
    return study_id.astype(str).str.split(":", n=1).str[1]


def _steps():
    return []


def _add(steps, name, n, note=""):
    prev = steps[-1]["stays"] if steps else None
    steps.append({"step": name, "stays": int(n),
                  "removed": None if prev is None else int(prev - n), "note": note})


def print_waterfall(steps, site=""):
    df = pd.DataFrame(steps)
    print(f"{site} waterfall")
    print(I.df_text(df, index=False))


def _vitals_stays(path, key_col, time_col):
    """Set of stay keys with at least one vitals row that has a chart time.
    Reads two columns only."""
    df, _ = I.read(path, usecols=[key_col, time_col])
    return set(df.loc[df[time_col].notna(), key_col])


# ---------------------------------------------------------------- RBH
def rbh_manifest(rbh_dir, min_year=MIN_YEAR):
    """One row per RBH stay (patient + admission time). Returns (manifest, waterfall steps)."""
    rbh_dir = I.Path(rbh_dir).expanduser()
    dem, _ = I.read(rbh_dir / "ai_picu_demographics.csv")
    dem = dem.drop_duplicates("studyID")
    dem["stay_key"] = rbh_stay_key(dem["studyID"])
    dem["adm_time"] = pd.to_datetime(dem["PICUadm_dttm"], format=RBH_TIME_FMT, errors="coerce")

    # one row per stay; keep every studyID (NIC and NND) so tables can be filtered later
    g = dem.groupby("stay_key", sort=False)
    stays = g.agg(studyIDs=("studyID", "|".join), PATIENT_RK=("PATIENT_RK", "first"),
                  PAS_AD_RK=("PAS_AD_RK", "first"), adm_time=("adm_time", "min")).reset_index()
    stays["year"] = stays["adm_time"].dt.year

    pic_new, _ = I.read(rbh_dir / "ai_picu_piccanet.csv", usecols=["studyID"])
    pic_old, _ = I.read(rbh_dir / "ai_picu_piccanet_old.csv", usecols=["studyID"])
    new_keys = set(rbh_stay_key(pic_new["studyID"]))
    old_keys = set(rbh_stay_key(pic_old["studyID"]))
    vit_keys = set(rbh_stay_key(pd.Series(sorted(
        _vitals_stays(rbh_dir / "ai_picu_vitals.csv", "studyID", "chartTime")))))

    steps = _steps()
    _add(steps, "all stays (patient + admission time)", len(stays),
         f"{int(stays['adm_time'].isna().sum())} with no parseable admission time (dropped below)")
    m = stays[stays["year"] >= min_year]
    _add(steps, f"admitted {min_year} or later", len(m))
    in_old_only = m[~m["stay_key"].isin(new_keys) & m["stay_key"].isin(old_keys)]
    m = m[m["stay_key"].isin(new_keys)]
    _add(steps, "in new PICANet", len(m),
         f"{len(in_old_only)} stays admitted {min_year}+ are in old PICANet only (dropped)")
    m = m[m["stay_key"].isin(vit_keys)]
    _add(steps, "has real vitals (a row with a chart time)", len(m))
    return m.reset_index(drop=True), steps


# ---------------------------------------------------------------- SMH
def smh_manifest(smh_dir, min_year=MIN_YEAR):
    """One row per SMH encounter. Returns (manifest, waterfall steps)."""
    smh_dir = I.Path(smh_dir).expanduser()
    dem, _ = I.read(smh_dir / "ai_picu_demographics.csv")
    dem["adm_time"] = pd.to_datetime(dem["inTime"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    stays = dem.groupby("encounterId", sort=False).agg(
        UniquePtID=("UniquePtID", "first"), adm_time=("adm_time", "min")).reset_index()
    stays["year"] = stays["adm_time"].dt.year   # London local time, not UTC

    pic, _ = I.read(smh_dir / "ai_picu_piccanet.csv", usecols=["encounterId"])
    pic_keys = set(pic["encounterId"])
    header = I.read(smh_dir / "ai_picu_vitals.csv", max_rows=5)[0].columns
    cols = ["encounterId", "utcChartTime"] + (["terseForm"] if "terseForm" in header else [])
    vit, _ = I.read(smh_dir / "ai_picu_vitals.csv", usecols=cols)
    ok = vit["utcChartTime"].notna()
    if "terseForm" in cols:
        ok &= vit["terseForm"].notna()
    vit_keys = set(vit.loc[ok, "encounterId"])

    steps = _steps()
    _add(steps, "all encounters", len(stays),
         f"{int(stays['adm_time'].isna().sum())} with no parseable admission time (dropped below)")
    m = stays[stays["year"] >= min_year]
    _add(steps, f"admitted {min_year} or later", len(m))
    m = m[m["encounterId"].isin(pic_keys)]
    _add(steps, "in PICANet", len(m))
    m = m[m["encounterId"].isin(vit_keys)]
    _add(steps, "has real vitals (a row with a chart time and a value)", len(m))
    return m.reset_index(drop=True), steps


def describe(manifest, patient_col):
    """Where the manifest leaves us: stays per admission year, patients, repeat stays.
    patient_col: 'PATIENT_RK' (RBH), 'UniquePtID' (SMH) or 'project_id' (GOSH)."""
    per_year = manifest.groupby("year").size().rename("stays").to_frame()
    per_pt = manifest.groupby(patient_col).size()
    print(f"{len(manifest)} stays, {per_pt.shape[0]} patients; "
          f"{int((per_pt > 1).sum())} patients with more than one stay "
          f"(max {int(per_pt.max())})")
    return per_year


# ---------------------------------------------------------------- GOSH
GOSH_PICANET = "PICANet_ALL_patients_SR_011024_projectID_eprweights.csv"
GOSH_VITALS = [f"merged_values/{n}_merged.csv" for n in (
    "HR", "PulseRate", "RespiratoryRate", "SpO2", "Temperature",
    "Invasive_systolic_BP", "Invasive_diastolic_BP", "Invasive_mean_BP",
    "Non-Invasive_systolic_BP", "Non-Invasive_diastolic_BP", "Non-Invasive_mean_BP")]
SENS_HOURS = 6          # the supplier's margin before admission, reported as a sensitivity


def _ns(s):
    return s.astype("datetime64[ns]")


def gosh_manifest(gosh_dir, picanet=GOSH_PICANET, vitals_files=GOSH_VITALS,
                  min_year=MIN_YEAR, pre_hours=0):
    """One row per GOSH admission = one PICANet row (patient + admission time).
    Vitals are attached by patient and time: a row counts if its time lies between
    (admission start - pre_hours) and discharge. `pre_hours` is the margin before admission
    (0 = only charting from admission start). The waterfall also reports the counts with a
    0 h and a 6 h margin and the supplier's admission_identifier count, for information.
    Returns (manifest, waterfall steps)."""
    gosh_dir = I.Path(gosh_dir).expanduser()
    pic, _ = I.read(gosh_dir / picanet)
    pic = pic.reset_index(drop=True)
    pic["picanet_row"] = pic.index
    pic["adm_time"] = _ns(I.parse_dates(pic["AdDateTime"])[0])
    pic["disch_time"] = _ns(I.parse_dates(pic["UnitDisDateTime"])[0])
    pic["year"] = pic["adm_time"].dt.year

    steps = _steps()
    _add(steps, "all PICANet rows (_eprweights)", len(pic))
    st = pic[pic["project_id"].notna()]
    _add(steps, "has a project_id (can be linked to other tables)", len(st),
         f"{len(pic) - len(st)} rows have no project_id")
    st = st[st["adm_time"].notna() & st["disch_time"].notna()]
    _add(steps, "admission and discharge times parse", len(st))
    st = st[st["year"] >= min_year]
    _add(steps, f"admitted {min_year} or later", len(st))

    # attach vitals rows by patient and time; one pass over the files
    margin = max(SENS_HOURS, pre_hours)
    w = st.assign(_ws=st["adm_time"] - pd.Timedelta(hours=margin))[
        ["project_id", "_ws", "adm_time", "disch_time", "picanet_row"]].sort_values("_ws")
    chosen, zero, six, ids = set(), set(), set(), set()
    for f in vitals_files:
        h, _ = I.read(gosh_dir / f, usecols=["project_id", "admission_identifier", "observation_datetime"])
        ids |= set(h["admission_identifier"].dropna().unique())
        h = h.dropna(subset=["project_id"]).copy()
        h["_t"] = _ns(I.parse_dates(h["observation_datetime"])[0])
        h = h.dropna(subset=["_t"]).sort_values("_t")
        a = pd.merge_asof(h[["project_id", "_t"]], w, left_on="_t", right_on="_ws", by="project_id",
                          direction="backward")
        a = a[a["picanet_row"].notna() & (a["_t"] <= a["disch_time"])]
        before = (a["adm_time"] - a["_t"]).dt.total_seconds() / 3600     # hours before admission
        chosen |= set(a.loc[before <= pre_hours, "picanet_row"])
        zero |= set(a.loc[before <= 0, "picanet_row"])
        six |= set(a.loc[before <= SENS_HOURS, "picanet_row"])
        del h, a
    m = st[st["picanet_row"].isin(chosen)].copy()
    _add(steps, f"has real vitals (a row between {pre_hours} h before admission and discharge)", len(m),
         f"with a 0 h margin: {len(zero)}; with a {SENS_HOURS} h margin: {len(six)}; "
         f"supplier admission_identifier (distinct, all admissions): {len(ids)}")
    m["stay_id"] = m["project_id"] + "|" + m["adm_time"].dt.strftime("%Y%m%d%H%M%S")
    cols = ["stay_id", "project_id", "picanet_row", "adm_time", "disch_time", "year"]
    return m[cols].reset_index(drop=True), steps


def gosh_eligible_rows(df, manifest, time_col="observation_datetime", pre_hours=0):
    """Rows of a GOSH table (needs project_id and a time column) that fall inside a manifest
    stay, with the stay_id added. Rows outside every stay are dropped."""
    t = _ns(I.parse_dates(df[time_col])[0])
    x = df.assign(_t=t).dropna(subset=["project_id", "_t"]).sort_values("_t")
    w = manifest.assign(_ws=_ns(manifest["adm_time"] - pd.Timedelta(hours=pre_hours)))[
        ["project_id", "_ws", "disch_time", "stay_id"]].sort_values("_ws")
    x = pd.merge_asof(x, w, left_on="_t", right_on="_ws", by="project_id", direction="backward")
    return x[x["stay_id"].notna() & (x["_t"] <= x["disch_time"])].drop(columns=["_t", "_ws", "disch_time"])


# ---------------------------------------------------------------- filtering other tables
def eligible_rows(df, manifest, site):
    """Rows of any table whose stay is in the manifest.
    GOSH: by patient and time (see gosh_eligible_rows).
    RBH: matches on patient + admission time from studyID (either prefix).
    SMH: matches on encounterId (encounterID in the medication files)."""
    if site.upper() == "GOSH":
        return gosh_eligible_rows(df, manifest)
    if site.upper() == "RBH":
        return df[rbh_stay_key(df["studyID"]).isin(set(manifest["stay_key"]))]
    col = "encounterId" if "encounterId" in df.columns else "encounterID"
    return df[df[col].isin(set(manifest["encounterId"]))]