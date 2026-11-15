"""Stay manifests: which stays are eligible, one row per stay, per site.

Rules (agreed 2026-11-15):
  1. admitted in or after MIN_YEAR (2013);
  2. in the NEW PICANet file (the old PICANet file is not used);
  3. has real vitals (at least one vitals row with a chart time).
The manifest holds only stays that pass all three. The waterfall records how many
stays each rule removed. Raw files are never modified.

Notebook use (inventory.py must be importable as `inventory`):
    import manifest as M
    rbh_m, rbh_w = M.rbh_manifest(rbh_dir)
    smh_m, smh_w = M.smh_manifest(smh_dir)
    M.print_waterfall(rbh_w, "RBH"); M.print_waterfall(smh_w, "SMH")
    rbh_m.to_csv(open_picu_dir/"RBH_manifest.csv", index=False)
    vit = M.eligible_rows(pd.read_csv(rbh_dir/"ai_picu_vitals.csv"), rbh_m, "RBH")
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
    patient_col: 'PATIENT_RK' (RBH) or 'UniquePtID' (SMH)."""
    per_year = manifest.groupby("year").size().rename("stays").to_frame()
    per_pt = manifest.groupby(patient_col).size()
    print(f"{len(manifest)} stays, {per_pt.shape[0]} patients; "
          f"{int((per_pt > 1).sum())} patients with more than one stay "
          f"(max {int(per_pt.max())})")
    return per_year


# ---------------------------------------------------------------- filtering other tables
def eligible_rows(df, manifest, site):
    """Rows of any table whose stay is in the manifest.
    RBH: matches on patient + admission time from studyID (either prefix).
    SMH: matches on encounterId (encounterID in the medication files)."""
    if site.upper() == "RBH":
        return df[rbh_stay_key(df["studyID"]).isin(set(manifest["stay_key"]))]
    col = "encounterId" if "encounterId" in df.columns else "encounterID"
    return df[df[col].isin(set(manifest["encounterId"]))]