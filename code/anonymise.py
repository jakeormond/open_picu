"""Step 10: anonymisation. Turns the harmonised files (derived/harmonised/) and the static table into releasable tables at a chosen
de-identification level. Everything runs inside the SDE; the outputs stay in derived/ until they have been through output checking.

One function does the work, `run(harmonised_dir, static, out_root, cfg)`, and one object, `Config`, says what a level is. Two presets exist
(`TIER1`, `TIER2`) and any other level, such as an ablation for the privacy and utility study, is a preset with some fields changed:
`preset("tier2", time_resolution_hours=1.0)`. Nothing else in this module needs to change to produce a new level.

What a run does, in order (each step logs counts only):
  1. cohort: the static rows for the stays in the cohort (`harmonise.cohort`, the rule used for the harmonised files);
  2. keys: new random stay keys (and, at Tier 1, patient keys), one draw for all sites so keys never collide and their order says nothing
     about the site; the mapping from old to new keys is written to `<out_root>/_private/` and is never part of a release;
  3. static table: Tier 1 keeps the exact fields; Tier 2 coarsens them (`reid.coarsen`), applies local suppression (`reid.suppress_to_k`) and
     replaces the patient key by `split_group`;
  4. series tables (vitals, vent, labs, blood gas, fluids, ...) and drugs, file by file: allow-list of columns; concepts dropped or
     renamed; GOSH drug rows with a number and no unit dropped (Tier 2); new keys; time resolution; the note-like scan on text; rare text values mapped
     to "rare" (Tier 2); `source` kept only where a concept has several sources (Tier 2); rows sorted by the new key, which is random;
  5. checks (below). A failed check stops the run, deletes the staging folder and raises `CheckFailed`; nothing is released.

Checks (counts only; never a value or an ID in a message):
  allow-list: no column outside the allow-list of the level (names of columns are reported, never values)
  ids: no original stay key or patient ID, as a whole value or as a token of a longer string, in any string column; no 32-character hex
       string (the SMH patient ID is an unsalted MD5)
  dates: no datetime column and no date-like string
  free text: no string column (other than `value_raw`) with many distinct long strings (a warning, not a stop, where the level keeps rare
       strings as recorded); no `value_raw` or `value_text` that the note scan flags
  text counts (Tier 2): no `value_text` string other than "rare" seen in fewer than k stays at a site and concept
  hour range: no |hour| beyond a year
  small cells (Tier 2 static): stays in cells below k on the released quasi-identifiers, against `max_small_share`
  rows: rows in = rows out + rows dropped by each rule, for every file; every series stay is in the static table; static rows = cohort stays.
The checks only test against the IDs this module is given (static `stay_key` and `patient_id`, and `extra_ids`). They cannot find a name
or an ID they do not know about; that is why the allow-list is the main safeguard and the checks are the backstop.

Output folder layout:
  <out_root>/<cfg.name>/static.parquet, <group>.parquet (Tier 2, pooled) or <SITE>_<group>.parquet (Tier 1), config.json, steps.csv, checks.csv
  <out_root>/_private/<cfg.name>_key_map.parquet  (site, stay_key, new_stay_key, patient_key)   never released
Reports hold counts only and can go to `reports/`.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field, asdict, replace, fields
from pathlib import Path

import numpy as np
import pandas as pd

import reid as R

SITES = ("GOSH", "RBH", "SMH")

# Concepts recorded at one site only that are proposed for removal in the pooled release (anonymisation_design.md, 2026-11-20): three have a
# near-identical common concept, `ps_peep` is a set inspiratory pressure (not a PEEP), `compliance_dynamic` can be derived at every site.
ONE_SITE_DROP = ("pulse_rate", "resp_rate_monitor", "bg_base_excess_recorded", "ps_peep", "compliance_dynamic")
# Concepts not usable at all three sites (in the concept map ten have a source at one site only, nine at two sites, and `bg_sample_type` at
# three but too little data at one; `intake_iv` is a derived fluid concept with no GOSH source). The "common features only" release leaves
# them out. SITE_PATTERN_DROP: two concepts dropped by hand because they gave the site away (`inr`, `cardiac_rhythm`). Used by `level_report.release_manifest` to say why a concept was removed; the level's own
# `drop_concepts` is what actually removes them, and is stored in its config.json.
FEW_SITES = ("bg_venous_sat", "avpu", "bg_cvo2", "ett_cuff", "ett_depth", "ett_route", "gcs", "inhaled_no", "plateau_pressure", "temp_peripheral",
             "bg_hct", "bg_sample_type", "chloride", "crt", "cvp", "insp_time", "intake_iv", "pupil_reaction", "pupil_size", "urine_output")
SITE_PATTERN_DROP = ("inr", "cardiac_rhythm")


# --------------------------------------------------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------------------------------------------------
@dataclass
class Config:
    """One de-identification level. Fields and what they do:
    name                   folder name of the output.
    k                      small-cell threshold (stays) used by coarsening, suppression and the text rule. BDAU does no output checking, so 10.
    seed                   seed for the keys and the split groups (a different seed gives unrelated keys; use a different seed per level).
    site_column            keep a `site` column (Tier 1) or release one pooled table with no site (Tier 2).
    patient_key            "key": a random patient key (Tier 1); "split_group": one of `n_groups` random groups per site (Tier 2).
    keep_year, keep_provenance, keep_pim_version, keep_src_row   keep these columns (admission year; ethnicity, weight and length of stay
                           sources; the PIM version label; the row number in the assembled table).
    source_mode            "all": keep `source` everywhere; "multi": only for concepts with more than one source at some site (blank
                           elsewhere); "none": drop the column.
    pim_mode               "raw", "band" (pooled quantile bands, `pim_bands` of them) or "drop".
    static_mode            "exact" (Tier 1) or "coarse" (Tier 2: bands, groups, suppression).
    ethnicity, age_edges, weight_edges, suppress_order   coarse-mode settings (see `reid.coarsen`, `reid.suppress_to_k`).
    drop_static            static fields left out of the level altogether: any of "ethnicity", "weight", "diagnosis_group" (with their source
                           columns). Age, sex and outcome are not optional. A dropped field is also left out of the small-cell checks and suppression.
    time_resolution_hours  None keeps `hour` as recorded; a number rounds it to that step (1.0 = whole hours).
    one_row_per_hour       with time_resolution_hours: numeric (non-drug) rows of one stay, concept and source that land in the same time step are
                           replaced by one row holding their median (value_raw of a merged row is blanked). Removes how often a site records.
    drop_concepts, rename_concepts   concepts removed or renamed in every table.
    text_rare_rule         strings of `value_text` seen in fewer than k stays at a site and concept become "rare".
    raw_max_len            the note scan flags text longer than this unless it is a common string (see `note_like`).
    drop_gosh_unitless     drop the GOSH drug rows that have a number and no unit (G17: infusion table constants; the `filtered_ALL` table values are
                           not weight-scaled doses either). Rows with no number (administration records) are kept.
    drop_gosh_caboodle     drop the GOSH fluid rows from the Epic-era hourly table (source `gosh_caboodle`): its intake is about a sixth of the other
                           sources' daily volume per kg and its net balance is negative (DATA_ISSUES G16). Also makes `source` single-valued for the
                           fluid concepts, so it is blanked at Tier 2, where the source names (rbh_io, smh_io, gosh_*) would give the site away.
    gosh_epic_cutoff       None, or a date ("2019-04-20"): GOSH stays whose t0 is on or after it are left out of the level altogether (static, series,
                           drugs, key map). GOSH moved to Epic at that date and the later stays lack blood gas, ventilator mode, tidal volume, I:E
                           ratio and diastolic pressures, and have the incomplete caboodle fluids (FLUIDS.md; `harmonise.gosh_era_comparison`).
    suppress_outcome_blind  suppress a field for every stay that shares the other quasi-identifiers (age, sex, diagnosis group, ethnicity) of a
                           stay in a small cell, whatever its outcome. Default False suppresses only the stays in the small (..., died) cell, which
                           are nearly all deaths, so "(suppressed)" then reveals the outcome (`patient_report.outcome_cells`).
    k                      Tier 2: the smallest group of stays that may share the released quasi-identifiers (age band, sex, ethnicity, diagnosis group,
                           outcome, weight band). The target for the patient-level review is k = 2 with the average risk reported (see
                           `patient_report.adversary_risk`); raise it when the cost is small.
    text_k                 Tier 2 free-text rule: a `value_text` or `value_raw` string seen in fewer than this many stays at a site and concept is
                           'rare' (replaced). Kept apart from `k` so that a low k for the static table does not weaken it. Default 10.
    k_unit                 Tier 2: what k counts. "stays" (default) counts stays in a cell; "patients" counts different patients, so two stays of one
                           child do not make a cell of two (the child would be found). Applies to suppression, deletion and the small-cell check.
    min_l                  Tier 2: 1 (off) or 2. With 2, after local suppression and deletion, the diagnosis group is suppressed wherever candidates
                           of one of the risk-table adversaries (`reid.L_KNOWN_SETS`) would otherwise all show the same diagnosis group
                           (`reid.enforce_l_diversity`); the minimum l-diversity of AmsterdamUMCdb. Needs the diagnosis group in the level.
    delete_below_k         after local suppression, delete the stays that are still in a cell below k from the level altogether (static, series,
                           drugs, key map), as AmsterdamUMCdb did. The number deleted is logged ("static: stays deleted below k").
    max_small_share        Tier 2 static check: largest accepted share of stays in cells below k (None: report only)."""
    name: str = "tier1"
    k: int = 10
    text_k: int = 10
    delete_below_k: bool = False
    k_unit: str = "stays"
    min_l: int = 1
    seed: int = 1
    site_column: bool = True
    patient_key: str = "key"
    n_groups: int = 10
    keep_year: bool = True
    keep_provenance: bool = True
    keep_pim_version: bool = True
    keep_src_row: bool = True
    source_mode: str = "all"
    pim_mode: str = "raw"
    pim_bands: int = 10
    static_mode: str = "exact"
    ethnicity: str = "group"
    age_edges: tuple = tuple(R.AGE_COARSE)
    weight_edges: tuple = tuple(R.WEIGHT_COARSE)
    suppress_order: tuple = ("weight_band", "ethnicity", "diagnosis_group")
    drop_static: tuple = ()
    time_resolution_hours: float | None = None
    one_row_per_hour: bool = False
    drop_concepts: tuple = ()
    rename_concepts: dict = field(default_factory=dict)
    text_rare_rule: bool = False
    raw_max_len: int = 40
    drop_gosh_unitless: bool = False
    drop_gosh_caboodle: bool = False
    gosh_epic_cutoff: object = None
    suppress_outcome_blind: bool = False
    max_small_share: float | None = None

    def validate(self):
        bad = []
        if self.static_mode not in ("exact", "coarse"):
            bad.append("static_mode must be 'exact' or 'coarse'")
        if self.patient_key not in ("key", "split_group"):
            bad.append("patient_key must be 'key' or 'split_group'")
        if self.gosh_epic_cutoff is not None:
            try:
                pd.Timestamp(self.gosh_epic_cutoff)
            except (ValueError, TypeError):
                bad.append("gosh_epic_cutoff must be None or a date such as '2019-04-20'")
        if self.source_mode not in ("all", "multi", "none"):
            bad.append("source_mode must be 'all', 'multi' or 'none'")
        if self.pim_mode not in ("raw", "band", "drop"):
            bad.append("pim_mode must be 'raw', 'band' or 'drop'")
        if self.patient_key == "split_group" and self.static_mode != "coarse":
            bad.append("split_group needs static_mode='coarse'")
        if self.static_mode == "coarse" and (self.keep_year or self.keep_provenance or self.keep_pim_version or self.pim_mode == "raw"):
            bad.append("coarse mode has no year, provenance columns, pim_version or raw pim")
        if self.static_mode == "exact" and self.patient_key != "key":
            bad.append("exact mode uses patient_key='key'")
        if self.time_resolution_hours is not None and self.time_resolution_hours <= 0:
            bad.append("time_resolution_hours must be positive")
        if self.one_row_per_hour and not self.time_resolution_hours:
            bad.append("one_row_per_hour needs time_resolution_hours")
        if self.k_unit not in ("stays", "patients"):
            bad.append("k_unit must be 'stays' or 'patients'")
        if self.min_l not in (1, 2):
            bad.append("min_l must be 1 (off) or 2")
        if self.min_l == 2 and (self.static_mode != "coarse" or "diagnosis_group" in self.drop_static):
            bad.append("min_l=2 needs static_mode='coarse' and the diagnosis group in the level")
        if self.k < 2:
            bad.append("k must be at least 2")
        unknown = [f for f in self.drop_static if f not in DROPPABLE]
        if unknown:
            bad.append(f"drop_static can only hold {sorted(DROPPABLE)}, not {unknown}")
        if bad:
            raise ValueError("; ".join(bad))
        return self

    def to_json(self):
        def enc(o):
            if isinstance(o, float) and np.isinf(o):
                return "inf"
            if isinstance(o, (tuple, list)):
                return [enc(x) for x in o]
            if isinstance(o, dict):
                return {k: enc(v) for k, v in o.items()}
            return o
        return json.dumps(enc(asdict(self)), indent=2)


TIER1 = Config(name="tier1", seed=1, rename_concepts={"ps_peep": "ps_target_pressure"})
TIER2 = Config(name="tier2", seed=2, site_column=False, patient_key="split_group", keep_year=False, keep_provenance=False,
               keep_pim_version=False, keep_src_row=False, source_mode="multi", pim_mode="drop", static_mode="coarse",
               drop_concepts=ONE_SITE_DROP, text_rare_rule=True, drop_gosh_unitless=True, drop_gosh_caboodle=True, max_small_share=0.001)
PRESETS = {"tier1": TIER1, "tier2": TIER2,
           "tier2_pim": replace(TIER2, name="tier2_pim", pim_mode="band", seed=3),
           "tier2_hourly": replace(TIER2, name="tier2_hourly", time_resolution_hours=1.0, seed=4),
           "tier2_no_ethnicity": replace(TIER2, name="tier2_no_ethnicity", drop_static=("ethnicity",), seed=6)}


def config_from_level(out_root, level, /, **changes):
    """The Config a released level was made with (read from its config.json), with `changes` applied and validated. Use it to make a variant of
    a level exactly as it was made: config_from_level(out_root, "tier2_merge_drop3_pre_epic", name="x", time_resolution_hours=1.0, seed=16)."""
    d = json.loads((Path(out_root) / level / "config.json").read_text())
    kinds = {f.name: f.default for f in fields(Config)}
    def dec(v):
        if v == "inf":
            return float("inf")
        return tuple(dec(x) for x in v) if isinstance(v, list) else v
    for k, v in list(d.items()):
        d[k] = tuple(dec(x) for x in v) if isinstance(v, list) and isinstance(kinds.get(k), tuple) else dec(v)
    return replace(Config(**{**d}), **changes).validate()


def preset(base, /, **changes):
    """A copy of the preset `base` with some fields changed (and validated): preset("tier2", name="tier2_k20", k=20, seed=5). `name` is the
    new level's folder name; give each level its own name and seed."""
    return replace(PRESETS[base], **changes).validate()


class CheckFailed(Exception):
    """Raised when a check fails. `.checks` is the DataFrame of all checks run so far (counts only)."""
    def __init__(self, checks):
        self.checks = checks
        bad = checks[checks["status"] == "FAIL"]
        super().__init__("anonymisation stopped, failed checks: " + "; ".join(f"{r.check} [{r.scope}] n={r.n}" for r in bad.itertuples()))


# --------------------------------------------------------------------------------------------------------------------------------
# Allow-lists (derived from the config, so a level cannot carry a column it did not ask for)
# --------------------------------------------------------------------------------------------------------------------------------
SERIES_COLS = ["stay_key", "concept", "hour", "value", "value_text", "value_raw", "flag"]
DRUG_COLS = ["stay_key", "concept", "hour", "value", "unit", "kind", "route", "value_raw"]


def allowed_series(cfg, kind="series"):
    """Columns a series table (kind 'series', which includes fluids) or the drug table (kind 'drugs') may have at this level."""
    cols = list(DRUG_COLS if kind == "drugs" else SERIES_COLS)
    if cfg.site_column:
        cols.insert(0, "site")
    if cfg.source_mode != "none":
        cols.append("source")
    if cfg.keep_src_row:
        cols.append("src_row")
    return cols


# Optional static fields a level can leave out, and the columns each one covers (exact and coarse modes).
DROPPABLE = {"ethnicity": ("ethnicity", "ethnicity_source"), "weight": ("weight_kg", "weight_band", "weight_source"),
             "diagnosis_group": ("diagnosis_group",)}


def dropped_static_columns(cfg):
    """Names of the static columns that `cfg.drop_static` removes."""
    return {c for f in cfg.drop_static for c in DROPPABLE[f]}


def allowed_static(cfg):
    """Columns the static table may have at this level."""
    if cfg.static_mode == "exact":
        cols = ["stay_key", "patient_key", "age_months", "sex", "ethnicity", "weight_kg", "los_hours", "died", "diagnosis_group"]
        if cfg.keep_year:
            cols.append("year")
        if cfg.keep_provenance:
            cols += ["ethnicity_source", "weight_source", "los_source"]
        if cfg.keep_pim_version:
            cols.append("pim_version")
    else:
        cols = ["stay_key", "split_group", "age_band", "sex", "ethnicity", "weight_band", "died", "diagnosis_group"]
    if cfg.pim_mode == "raw":
        cols.append("pim")
    elif cfg.pim_mode == "band":
        cols.append("pim_band")
    if cfg.site_column:
        cols.insert(0, "site")
    return [c for c in cols if c not in dropped_static_columns(cfg)]


# --------------------------------------------------------------------------------------------------------------------------------
# Text rules
# --------------------------------------------------------------------------------------------------------------------------------
DATE_RE = r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/.-]\d{1,2}[/.-](?:\d{4}|\d{2})\b"
HEX_RE = r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{32}(?![0-9A-Fa-f])"


def note_like(s, max_len=40, common=None):
    """True for strings that look like a typed note rather than a recorded value. Hard rules (always): contains a date, an e-mail or web
    address, or a run of seven or more digits (a phone or ID number). Soft rules: longer than `max_len`, or more than three words of three or
    more letters; these do not apply to `common` strings, the entries seen in at least k stays, which are vocabulary (a vent mode or airway
    device typed the same way in many stays), not notes. A heuristic: it cannot recognise a name. Missing values are False. Works on the
    distinct strings, so it is quick on long columns."""
    s = pd.Series(s, copy=False).astype("string")
    u = pd.Series(s.dropna().unique(), dtype="string")
    hard = u.str.contains(DATE_RE, regex=True) | u.str.contains(r"@|https?://|www\.|\d{7,}", regex=True)
    soft = (u.str.len() > max_len) | (u.str.count(r"[A-Za-z]{3,}") > 3)
    if common is not None and len(common):
        soft = soft & ~u.isin(list(common))
    hit = (hard | soft).fillna(False).astype(bool)
    return s.isin(list(u[hit])).fillna(False).astype(bool)


def common_strings(df, col, k):
    """Strings of `col` seen in at least k stays of `df`: the recorded vocabulary, exempt from the soft note rules."""
    if col == "stay_key":
        return set()
    t = df.loc[df[col].notna(), [col, "stay_key"]].drop_duplicates()
    n = t.groupby(col).size()
    return set(n[n >= k].index.astype(str))


def _rare_pairs(df, col, k):
    """The (concept, string) pairs of `col` seen in fewer than k stays, as a MultiIndex."""
    t = df.loc[df[col].notna(), ["concept", col, "stay_key"]].drop_duplicates()
    n = t.groupby(["concept", col]).size()
    return n[n < k].index


def _in_pairs(df, col, pairs):
    """Boolean array: rows whose (concept, `col`) is in `pairs`. Only rows with a value in `col` are looked at."""
    m = np.zeros(len(df), dtype=bool)
    has = df[col].notna().to_numpy()
    if len(pairs) and has.any():
        m[has] = pd.MultiIndex.from_frame(df.loc[has, ["concept", col]]).isin(pairs)
    return m


# --------------------------------------------------------------------------------------------------------------------------------
# Cohort and keys
# --------------------------------------------------------------------------------------------------------------------------------
def cohort_static(static):
    """The static rows for the cohort stays (the rule used for the harmonised files). stay_key is text."""
    import harmonise as H
    co = H.cohort(static)[["site", "stay_key"]]
    s = static.assign(stay_key=static["stay_key"].astype(str))
    return s.merge(co, on=["site", "stay_key"], how="inner").reset_index(drop=True)


def source_ids(co, extra=()):
    """Every original identifier this module knows: static stay keys and patient IDs (as text), plus `extra`."""
    ids = set(co["stay_key"].dropna().astype(str)) | set(co["patient_id"].dropna().astype(str)) | {str(x) for x in extra}
    return {i for i in ids if i.strip()}


MIN_ID_LEN = 5
# Columns in which a number is never a legitimate value: a short original ID found here as a whole value is a real leak (an unmapped key or a
# label that carries one). Columns that hold small numbers legitimately (source, value_raw, value_text) are not tested for short IDs.
ID_COLUMNS = ("stay_key", "patient_key", "concept", "flag", "unit", "kind", "route", "site")


def testable_ids(ids, min_len=MIN_ID_LEN):
    """The IDs the checks look for: those with at least `min_len` characters. A shorter ID (a stay key that is a one-digit or few-digit number)
    cannot be told from an ordinary small number such as a source index, so matching it would only produce false alarms. The number of IDs
    left out is logged by `run`. They are still tested, as whole values, in the key and label columns (`ID_COLUMNS`)."""
    return {i for i in ids if len(i) >= min_len}


def _draw(rng, n, taken, prefix):
    """n distinct random keys (prefix + 8 digits) not in `taken`; the numbers come from one shuffled range, so order carries no meaning."""
    nums = rng.permutation(4 * n + 100)
    out, seen = [], set()
    for v in nums:
        key = f"{prefix}{int(v):08d}"
        if key not in taken and key not in seen:
            out.append(key)
            seen.add(key)
            if len(out) == n:
                return out
    raise RuntimeError("could not draw enough keys")


def make_keys(co, cfg, ids):
    """Random key map for the cohort stays: site, stay_key (original), new_stay_key and, at Tier 1, patient_key. One draw for all sites.
    A patient is the pair (site, patient_id); a stay with no patient_id is its own patient. No linkage across sites is made."""
    rng = np.random.default_rng(cfg.seed)
    co = co.sort_values(["site", "stay_key"]).reset_index(drop=True)
    km = co[["site", "stay_key"]].copy()
    km["new_stay_key"] = _draw(rng, len(km), ids, "S")
    km["patient_key"] = pd.NA
    if cfg.patient_key == "key":
        pid = co["patient_id"].astype("string").str.strip()
        label = pid.where(pid.notna() & (pid != ""), "(stay)" + co.index.astype(str))
        codes, uniques = pd.factorize(co["site"].astype(str) + "|" + label.astype(str))
        keys = _draw(rng, len(uniques), ids | set(km["new_stay_key"]), "P")
        km["patient_key"] = np.array(keys, dtype=object)[codes]
    km["patient_key"] = km["patient_key"].astype("string")
    return km


# --------------------------------------------------------------------------------------------------------------------------------
# Static table
# --------------------------------------------------------------------------------------------------------------------------------
def patient_ids(co):
    """site, stay_key and `_pid`, an identifier of the patient (site and patient_id; a stay with no patient_id counts as its own patient)."""
    pid = co["patient_id"].astype("string") if "patient_id" in co.columns else pd.Series(pd.NA, index=co.index, dtype="string")
    own = "stay:" + co["stay_key"].astype("string")
    pid = co["site"].astype("string") + ":" + pid.where(pid.notna() & (pid.str.strip() != ""), own)
    return pd.DataFrame({"site": co["site"], "stay_key": co["stay_key"], "_pid": pid})


def build_static(co, km, cfg, return_truth=False):
    """The static table at this level, and a list of log rows. Tier 1 (exact): original fields with new keys. Tier 2 (coarse): bands,
    broad ethnicity groups, split_group, local suppression across all sites (`by_site=False`), then no site column."""
    log = []
    truth = None
    if cfg.static_mode == "exact":
        s = co.merge(km, on=["site", "stay_key"], how="inner")
        s["stay_key"] = s["new_stay_key"]
        out = s
    else:
        coarse = R.coarsen(co, k=cfg.k, ethnicity=cfg.ethnicity, weight=True, los=False, n_groups=cfg.n_groups, seed=cfg.seed,
                           age_edges=list(cfg.age_edges), weight_edges=list(cfg.weight_edges))
        gone = dropped_static_columns(cfg)
        key_cols = [c for c in ["age_band", "sex", "ethnicity", "diagnosis_group", "died", "weight_band"] if c not in gone]
        order = [c for c in cfg.suppress_order if c not in gone]
        truth = coarse.copy()
        unit = None
        if cfg.k_unit == "patients":
            coarse = coarse.merge(patient_ids(co), on=["site", "stay_key"], how="left")
            unit = "_pid"
        coarse, rep = R.suppress_to_k(coarse, key_cols, order, k=cfg.k, by_site=False, spread=("died",) if cfg.suppress_outcome_blind else (), unit=unit)
        coarse = coarse.drop(columns=["_pid"], errors="ignore")
        for r in rep.itertuples():
            log.append({"step": "static: local suppression", "item": r.field, "n": int(r.values_suppressed)})
        out = coarse.merge(co[["site", "stay_key", "pim"]], on=["site", "stay_key"], how="left")
        out = out.merge(km[["site", "stay_key", "new_stay_key"]], on=["site", "stay_key"], how="inner")
        out["stay_key"] = out["new_stay_key"]
    if cfg.pim_mode == "band":
        out["pim_band"] = pd.qcut(pd.to_numeric(out["pim"], errors="coerce"), cfg.pim_bands, labels=False, duplicates="drop")
        out["pim_band"] = (out["pim_band"] + 1).astype("Int64")
    cols = [c for c in allowed_static(cfg) if c in out.columns]
    out = out[cols].copy()
    for c in out.columns:
        if str(out[c].dtype) == "category":
            out[c] = out[c].astype("string")
    log.append({"step": "static: rows", "item": "stays", "n": len(out)})
    out = out.sort_values("stay_key").reset_index(drop=True)
    if return_truth:
        if truth is not None:
            truth = truth.merge(km[["site", "stay_key", "new_stay_key"]], on=["site", "stay_key"], how="inner").drop(columns="stay_key").rename(columns={"new_stay_key": "stay_key"})
        return out, log, truth
    return out, log


# --------------------------------------------------------------------------------------------------------------------------------
# Series and drug tables
# --------------------------------------------------------------------------------------------------------------------------------
CABOODLE_SOURCE = "gosh_caboodle"
SITE_WORDS = r"(?i)rbh|smh|gosh|brompton|st\.? ?mary|ormond"


def multi_source_concepts(harmonised_dir, sites=SITES, drop_sources=()):
    """Concepts that have more than one distinct `source` value at some site (series, fluids and drugs), not counting rows whose source is in
    drop_sources (rows the level removes). Reads only two columns."""
    multi = set()
    for site in sites:
        for f in sorted(Path(harmonised_dir).glob(f"{site}_*.parquet")):
            if f.stem.endswith("_rejected"):
                continue
            d = pd.read_parquet(f, columns=["concept", "source"])
            d = d[~d["source"].isin(drop_sources)]
            n = d.groupby("concept")["source"].nunique()
            multi |= set(n[n > 1].index)
    return multi


def transform_series(df, site, kind, keymap, cfg, multi):
    """One site's file at this level. Returns (frame, log). The frame keeps a `site` column; the caller drops it (Tier 2) after the checks
    that need it. keymap: {original stay key: new key} for this site. multi: concepts with several sources."""
    df = df.copy()
    if "site" not in df.columns:
        df.insert(0, "site", site)
    log = {"site": site, "kind": kind, "rows_in": len(df)}
    allowed = allowed_series(cfg, kind)
    log["columns_dropped"] = ",".join(c for c in df.columns if c not in allowed and c != "site")
    log["drop_concept"] = log["drop_drug_rule"] = log["drop_caboodle"] = log["drop_not_cohort"] = log["time_rounded_rows"] = log["rows_merged_hourly"] = 0
    log["text_note_nulled"] = log["text_rare_mapped"] = log["raw_note_nulled"] = log["raw_rare_nulled"] = log["source_blanked"] = 0

    m = df["concept"].isin(cfg.drop_concepts)
    log["drop_concept"] = int(m.sum())
    df = df[~m]
    if kind == "drugs" and cfg.drop_gosh_unitless and site == "GOSH":
        m = df["value"].notna() & (df["unit"].isna() | (df["unit"].astype("string").str.strip() == ""))
        log["drop_drug_rule"] = int(m.sum())
        df = df[~m]
    if cfg.drop_gosh_caboodle and site == "GOSH" and "source" in df.columns:
        m = df["source"] == CABOODLE_SOURCE
        log["drop_caboodle"] = int(m.sum())
        df = df[~m]
    sk = df["stay_key"].astype(str)
    m = ~sk.isin(keymap.keys())
    log["drop_not_cohort"] = int(m.sum())
    df = df[~m].copy()
    df["stay_key"] = sk[~m].map(keymap)
    if cfg.rename_concepts:
        df["concept"] = df["concept"].replace(cfg.rename_concepts)

    if cfg.time_resolution_hours:
        r = cfg.time_resolution_hours
        new = (np.round(df["hour"].astype("float64") / r) * r).astype("float32")
        log["time_rounded_rows"] = int((new != df["hour"]).sum())
        df["hour"] = new

    if "value_text" in df.columns:
        common = common_strings(df, "value_text", cfg.text_k)
        if cfg.text_rare_rule:                       # rare strings become "rare" first; what is left is vocabulary
            rare = _rare_pairs(df, "value_text", cfg.text_k)
            m = _in_pairs(df, "value_text", rare)
            log["text_rare_mapped"] = int(m.sum())
            if "value_raw" in df.columns:
                df.loc[m, "value_raw"] = pd.NA
            df.loc[m, "value_text"] = "rare"
        m = note_like(df["value_text"], cfg.raw_max_len, common | {"rare"}).to_numpy()
        log["text_note_nulled"] = int(m.sum())
        df.loc[m, "value_text"] = pd.NA
    if "value_raw" in df.columns:
        m = note_like(df["value_raw"], cfg.raw_max_len, common_strings(df, "value_raw", cfg.text_k)).to_numpy()
        log["raw_note_nulled"] = int(m.sum())
        df.loc[m, "value_raw"] = pd.NA
        if cfg.text_rare_rule and "value_text" in df.columns:
            textc = df.loc[df["value_text"].notna(), "concept"].unique()
            sub = df[df["concept"].isin(textc)]
            rare = _rare_pairs(sub, "value_raw", cfg.text_k)
            m = _in_pairs(df, "value_raw", rare) & df["concept"].isin(textc).to_numpy()
            log["raw_rare_nulled"] = int(m.sum())
            df.loc[m, "value_raw"] = pd.NA
    if cfg.source_mode == "multi" and "source" in df.columns:
        m = ~df["concept"].isin(multi)
        log["source_blanked"] = int((m & df["source"].notna()).sum())
        df.loc[m, "source"] = pd.NA
    if cfg.one_row_per_hour and cfg.time_resolution_hours and kind != "drugs":
        num = df["value"].notna()
        if "value_text" in df.columns:
            num &= df["value_text"].isna()
        keys = [c for c in ("stay_key", "concept", "hour", "source") if c in df.columns]
        sub = df[num]
        size = sub.groupby(keys, dropna=False)["value"].transform("size")
        sub = sub.assign(value=sub.groupby(keys, dropna=False)["value"].transform("median"))
        if "value_raw" in sub.columns:
            sub.loc[size > 1, "value_raw"] = pd.NA
        sub = sub.drop_duplicates(keys)
        log["rows_merged_hourly"] = int(num.sum() - len(sub))
        df = pd.concat([df[~num], sub]).sort_index()
    log["rows_out"] = len(df)
    return df, log


# --------------------------------------------------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------------------------------------------------
def _chk(check, scope, n, ok, note=""):
    return {"check": check, "scope": scope, "n": int(n), "status": "pass" if ok else "FAIL", "note": note}


def check_frame(df, scope, cfg, ids, allowed, max_abs_hour=24 * 365, short_ids=frozenset()):
    # max_abs_hour: run() passes the longest cohort stay plus two days, so a long stay is not mistaken for a bad time.
    # short_ids: original IDs under MIN_ID_LEN characters; only tested as whole values in ID_COLUMNS (see there).
    """Checks on a final output frame (after the site column is dropped where the level has none). Returns a list of check rows."""
    rows = []
    extra = [c for c in df.columns if c not in allowed]
    rows.append(_chk("allow-list", scope, len(extra), not extra, ("columns not allowed: " + ",".join(extra)) if extra else ""))
    dt = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    str_cols = [c for c in df.columns if df[c].dtype == object or pd.api.types.is_string_dtype(df[c])]
    n_date = n_hex = n_id = n_tok = 0
    free, id_cols = [], []
    for c in str_cols:
        u = pd.Series(df[c].dropna().unique()).astype("string")
        if not len(u):
            continue
        n_date += int(u.str.contains(DATE_RE, regex=True).sum())
        n_hex += int(u.str.contains(HEX_RE, regex=True).sum())
        a = int(u.isin(ids).sum())
        hx = int(u.str.contains(HEX_RE, regex=True).sum())
        tok = u.str.findall(r"[A-Za-z0-9]{6,}").explode().dropna()
        b = int(tok[tok.isin(ids)].index.nunique())
        if short_ids and c in ID_COLUMNS:
            a += int(u.isin(short_ids).sum())
        n_id += a
        n_tok += b
        if a + b + hx:
            id_cols.append(f"{c}({a + b + hx})")
        if c != "value_raw" and len(u) > 200 and float(u.str.len().mean()) > 12:
            free.append(c)
    rows.append(_chk("dates", scope, len(dt) + n_date, not dt and n_date == 0, f"datetime columns {len(dt)}, date-like strings {n_date}"))
    rows.append(_chk("ids", scope, n_id + n_tok + n_hex, n_id + n_tok + n_hex == 0,
                     f"whole-value matches {n_id}, token matches {n_tok}, 32-character hex strings {n_hex} (distinct strings; short IDs only as whole values in key and label columns)" + (("; in columns " + ",".join(id_cols)) if id_cols else "")))
    notes = 0
    for c in ("value_raw", "value_text"):
        if c in df.columns:
            notes += int(note_like(pd.Series(df[c].dropna().unique()), cfg.raw_max_len, common_strings(df, c, cfg.text_k)).sum())
    ft = _chk("free text", scope, len(free) + notes, not free and notes == 0,
              ("many long strings in: " + ",".join(free) + "; " if free else "") + f"note-like strings {notes}")
    if free and notes == 0 and not cfg.text_rare_rule:
        ft["status"] = "WARN"          # Tier 1: recorded strings stay as recorded (inside the SDE); the Tier 2 rule maps the rare tail
    rows.append(ft)
    if not cfg.site_column and "source" in df.columns:
        bad = int(df["source"].dropna().astype("string").drop_duplicates().str.contains(SITE_WORDS, regex=True).sum())
        rows.append(_chk("source labels", scope, bad, bad == 0, "distinct `source` values that name a site or hospital (none allowed without a site column)"))
    if "hour" in df.columns:
        h = pd.to_numeric(df["hour"], errors="coerce")
        bad = int((h.abs() > max_abs_hour).sum())
        rows.append(_chk("hour range", scope, bad, bad == 0, f"rows with |hour| above {max_abs_hour:.0f} (longest stay in the cohort plus 48 hours)"))
    return rows


def check_text_counts(df, scope, k):
    """Tier 2: no `value_text` string other than 'rare' seen in fewer than k stays at its site and concept. Needs the site column."""
    if "value_text" not in df.columns:
        return []
    t = df.loc[df["value_text"].notna() & (df["value_text"] != "rare"), ["site", "concept", "value_text", "stay_key"]].drop_duplicates()
    n = t.groupby(["site", "concept", "value_text"]).size()
    bad = int((n < k).sum())
    return [_chk("text counts", scope, bad, bad == 0, f"strings seen in fewer than {k} stays at a site and concept")]


QUASI = ["age_band", "sex", "ethnicity", "diagnosis_group", "died", "weight_band"]


def check_small_cells(static_out, cfg, unit=None):
    """Tier 2 static: stays in cells below k on the released quasi-identifiers (all sites together), against `max_small_share`. With `unit` (a
    Series of patient identifiers aligned with the table) k counts different patients."""
    cols = [c for c in QUASI + (["pim_band"] if "pim_band" in static_out.columns else []) if c in static_out.columns]
    n = int(stays_below_k(static_out, cfg.k, unit).sum())
    share = n / max(len(static_out), 1)
    ok = cfg.max_small_share is None or share <= cfg.max_small_share
    note = f"{share:.4%} of {len(static_out)} stays in cells below {cfg.k} on {','.join(cols)}; threshold " + ("none (report only)" if cfg.max_small_share is None else f"{cfg.max_small_share:.4%}")
    return [_chk("small cells", "static", n, ok, note)]


def stays_below_k(static_out, k, unit=None):
    """Boolean Series: stays whose combination of released quasi-identifiers (as in `check_small_cells`) is shared by fewer than k stays, or, if
    `unit` (a Series of patient identifiers aligned with `static_out`) is given, by fewer than k different patients."""
    cols = [c for c in QUASI + (["pim_band"] if "pim_band" in static_out.columns else []) if c in static_out.columns]
    f = static_out[cols + ["stay_key"]].copy()
    if unit is not None:
        f["_pid"] = unit.to_numpy()
    return R.cell_size(f, cols, False, "_pid" if unit is not None else None) < k


def split_group_report(static_out):
    """Stays in the smallest and largest split group (counts only)."""
    if "split_group" not in static_out.columns:
        return []
    g = static_out.groupby("split_group").size()
    return [{"step": "static: split groups", "item": "groups", "n": int(len(g))}, {"step": "static: split groups", "item": "smallest group", "n": int(g.min())},
            {"step": "static: split groups", "item": "largest group", "n": int(g.max())}]


# --------------------------------------------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------------------------------------------
def _groups(harmonised_dir, site):
    return [f.stem[len(site) + 1:] for f in sorted(Path(harmonised_dir).glob(f"{site}_*.parquet")) if not f.stem.endswith("_rejected")]


def run(harmonised_dir, static, out_root, cfg, sites=SITES, reports_dir=None, extra_ids=()):
    """Produce the level `cfg` from the harmonised files and the static table. Returns (steps, checks), DataFrames of counts only. Raises
    CheckFailed (and releases nothing) if any check fails. Existing output of the same name is replaced only when every check passed."""
    cfg.validate()
    out_root = Path(out_root)
    stage = out_root / f"{cfg.name}.staging"
    final = out_root / cfg.name
    private = out_root / "_private"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    private.mkdir(parents=True, exist_ok=True)
    steps, checks = [], []

    def stop_if_failed():
        if any(c["status"] == "FAIL" for c in checks):
            frame = pd.DataFrame(checks)
            if reports_dir is not None:
                Path(reports_dir).mkdir(parents=True, exist_ok=True)
                frame.to_csv(Path(reports_dir) / f"anonymise_{cfg.name}_checks.csv", index=False)
            shutil.rmtree(stage, ignore_errors=True)
            raise CheckFailed(frame)

    co = cohort_static(static)
    co = co[co["site"].isin(sites)].reset_index(drop=True)
    ids_all = source_ids(co, extra_ids)                  # IDs of every cohort stay, also those the level leaves out
    hour_limit = float(pd.to_numeric(co["los_hours"], errors="coerce").max()) + 48.0
    n_epic = 0
    if cfg.gosh_epic_cutoff:
        m = (co["site"] == "GOSH") & (pd.to_datetime(co["t0"]) >= pd.Timestamp(cfg.gosh_epic_cutoff))
        n_epic = int(m.sum())
        co = co[~m].reset_index(drop=True)
    ids = testable_ids(ids_all)
    short_ids = frozenset(ids_all - ids)
    if cfg.gosh_epic_cutoff:
        steps.append({"step": "cohort", "item": f"GOSH stays left out (t0 on or after {cfg.gosh_epic_cutoff})", "n": n_epic})
    steps.append({"step": "cohort", "item": "stays", "n": len(co)})
    steps.append({"step": "checks", "item": f"original IDs too short to test (under {MIN_ID_LEN} characters)", "n": len(ids_all) - len(ids)})
    km = make_keys(co, cfg, ids_all)
    km.to_parquet(private / f"{cfg.name}_key_map.parquet", index=False)
    steps.append({"step": "keys", "item": "stay keys", "n": len(km)})

    st, log, truth = build_static(co, km, cfg, return_truth=True)
    pidmap = None
    if cfg.k_unit == "patients" and cfg.static_mode == "coarse":
        pm = patient_ids(co).merge(km[["site", "stay_key", "new_stay_key"]], on=["site", "stay_key"])
        pidmap = pm.set_index("new_stay_key")["_pid"]
    if cfg.delete_below_k and cfg.static_mode == "coarse":
        gone = stays_below_k(st, cfg.k, st["stay_key"].map(pidmap) if pidmap is not None else None)
        gone_keys = set(st.loc[gone, "stay_key"])
        n_pat = int(co.merge(km[km["new_stay_key"].isin(gone_keys)][["site", "stay_key"]], on=["site", "stay_key"]).drop_duplicates(["site", "patient_id"]).shape[0]) if "patient_id" in co.columns else 0
        km_gone = km[km["new_stay_key"].isin(gone_keys)][["site", "stay_key"]]
        co = co.merge(km_gone.assign(_gone=1), on=["site", "stay_key"], how="left")
        co = co[co["_gone"].isna()].drop(columns="_gone").reset_index(drop=True)
        km = km[~km["new_stay_key"].isin(gone_keys)].reset_index(drop=True)
        km.to_parquet(private / f"{cfg.name}_key_map.parquet", index=False)
        st = st[~gone].reset_index(drop=True)
        log.append({"step": "static: stays deleted below k", "item": "stays", "n": int(gone.sum())})
        log.append({"step": "static: stays deleted below k", "item": "patients with a stay deleted", "n": n_pat})
    if cfg.min_l >= 2 and truth is not None:
        st, lrep = R.enforce_l_diversity(st, truth)
        for r in lrep.itertuples():
            log.append({"step": "static: l-diversity", "item": r.item, "n": int(r.n)})
        left = int(lrep.loc[lrep["item"] == "targets still with one known value", "n"].iloc[0])
        checks.append(_chk("l-diversity", "static", left, left == 0, "targets whose candidates show exactly one diagnosis group (min_l = 2)"))
    steps += log + split_group_report(st)
    checks += check_frame(st, "static", cfg, ids, allowed_static(cfg), hour_limit, short_ids)
    checks.append(_chk("rows", "static", abs(len(st) - len(co)), len(st) == len(co), f"static rows {len(st)}, cohort stays {len(co)}"))
    if cfg.static_mode == "coarse":
        checks += check_small_cells(st, cfg, st["stay_key"].map(pidmap) if pidmap is not None else None)
    stop_if_failed()
    st.to_parquet(stage / "static.parquet", index=False)
    new_keys = set(st["stay_key"])

    multi = multi_source_concepts(harmonised_dir, sites, (CABOODLE_SOURCE,) if cfg.drop_gosh_caboodle else ()) if cfg.source_mode == "multi" else set()
    if cfg.source_mode == "multi":
        steps.append({"step": "source", "item": "concepts with several sources", "n": len(multi)})
    kmaps = {s: dict(zip(g["stay_key"], g["new_stay_key"])) for s, g in km.groupby("site")}

    names = sorted({g for s in sites for g in _groups(harmonised_dir, s)})
    for g in names:
        kind = "drugs" if g == "drugs" else "series"
        parts = []
        for site in sites:
            f = Path(harmonised_dir) / f"{site}_{g}.parquet"
            if not f.exists():
                continue
            out, lg = transform_series(pd.read_parquet(f), site, kind, kmaps.get(site, {}), cfg, multi)
            dropped = sum(lg[k] for k in ("drop_concept", "drop_drug_rule", "drop_caboodle", "drop_not_cohort", "rows_merged_hourly"))
            checks.append(_chk("rows", f"{site}_{g}", lg["rows_in"] - dropped - lg["rows_out"], lg["rows_in"] - dropped == lg["rows_out"],
                               f"in {lg['rows_in']}, dropped {dropped}, out {lg['rows_out']}"))
            if kind == "drugs" and site == "GOSH" and cfg.drop_gosh_unitless:
                checks.append(_chk("drug rule", f"{site}_{g}", lg["drop_drug_rule"], lg["drop_drug_rule"] > 0,
                                   "GOSH drug rows with a number and no unit dropped (G17); zero means the rule matched nothing"))
            if cfg.text_rare_rule:
                checks += check_text_counts(out, f"{site}_{g}", cfg.text_k)
            steps.append({"step": f"series {site}_{g}", "item": "rows in", "n": lg["rows_in"]})
            steps += [{"step": f"series {site}_{g}", "item": k, "n": v} for k, v in lg.items() if isinstance(v, (int, np.integer)) and k not in ("rows_in",)]
            if lg["columns_dropped"]:
                steps.append({"step": f"series {site}_{g}", "item": "columns dropped: " + lg["columns_dropped"], "n": 0})
            parts.append(out)
        if not parts:
            continue
        if cfg.site_column:
            units = [(f"{p['site'].iloc[0]}_{g}" if len(p) else f"{g}", p) for p in parts]
        else:
            units = [(g, pd.concat(parts, ignore_index=True))]
        for label, d in units:
            keep = [c for c in allowed_series(cfg, kind) if c in d.columns]
            d = d[keep].sort_values(["stay_key", "concept", "hour"], kind="stable").reset_index(drop=True)
            checks += check_frame(d, label, cfg, ids, allowed_series(cfg, kind), hour_limit, short_ids)
            orphan = int((~d["stay_key"].isin(new_keys)).sum())
            checks.append(_chk("rows", label + " keys", orphan, orphan == 0, "rows whose stay is not in the static table"))
            stop_if_failed()
            d.to_parquet(stage / f"{label}.parquet", index=False)
            steps.append({"step": f"write {label}", "item": "rows", "n": len(d)})

    st_frame, ck_frame = pd.DataFrame(steps), pd.DataFrame(checks)
    st_frame.to_csv(stage / "steps.csv", index=False)
    ck_frame.to_csv(stage / "checks.csv", index=False)
    (stage / "config.json").write_text(cfg.to_json())
    if reports_dir is not None:
        Path(reports_dir).mkdir(parents=True, exist_ok=True)
        st_frame.to_csv(Path(reports_dir) / f"anonymise_{cfg.name}_steps.csv", index=False)
        ck_frame.to_csv(Path(reports_dir) / f"anonymise_{cfg.name}_checks.csv", index=False)
    stop_if_failed()
    if final.exists():
        shutil.rmtree(final)
    stage.rename(final)
    return st_frame, ck_frame


def diagnose(harmonised_dir, static, cfg, site, group, extra_ids=(), min_hour=None):
    """Counts-only explanation of a failed ids or hour check for one file. Returns (ids, hours):
    ids: one row per string column and kind of ID (the site it belongs to, stay key or patient ID) that has hits: distinct strings that equal it (whole) or contain it (token), and rows affected; an empty table means no hits against any site's IDs.
    hours: rows with |hour| above a year, how many belong to stays longer than a year, and how many lie beyond the stay's own length by more
    than 48 hours (or before -48), by concept. No values or IDs are shown."""
    allco = cohort_static(static)
    co = allco[allco["site"] == site]
    pools = {}
    for sj, g in allco.groupby("site"):
        pools[(sj, "stay_key")] = testable_ids(set(g["stay_key"].astype(str)))
        pools[(sj, "patient_id")] = testable_ids(set(g["patient_id"].dropna().astype(str)))
    pools[("extra", "stay_key")] = testable_ids({str(x) for x in extra_ids})
    all_ids = set().union(*pools.values())
    raw = pd.read_parquet(Path(harmonised_dir) / f"{site}_{group}.parquet")
    km = make_keys(allco, cfg, source_ids(allco, extra_ids))
    kmap = dict(zip(km[km["site"] == site]["stay_key"], km[km["site"] == site]["new_stay_key"]))
    df, _ = transform_series(raw, site, "drugs" if group == "drugs" else "series", kmap, cfg, set())
    rows = []
    for c in [c for c in df.columns if df[c].dtype == object or pd.api.types.is_string_dtype(df[c])]:
        u = pd.Series(df[c].dropna().unique()).astype("string")
        tok = u.str.findall(r"[A-Za-z0-9]{6,}").explode().dropna()
        hx = set(u[u.str.contains(HEX_RE, regex=True)])
        allhits = set(u[u.isin(all_ids)]) | set(u[tok[tok.isin(all_ids)].index.unique()]) | hx
        n_rows = int(df[c].isin(allhits).sum())
        if hx:
            rows.append({"column": c, "id_site": "-", "id_kind": "hex32", "whole": len(hx), "token": 0, "rows_affected": n_rows})
        for (sj, kind), pool in pools.items():
            whole = set(u[u.isin(pool)])
            part = set(u[tok[tok.isin(pool)].index.unique()]) - whole
            if whole or part:
                rows.append({"column": c, "id_site": sj, "id_kind": kind, "whole": len(whole), "token": len(part), "rows_affected": n_rows})
    ids = pd.DataFrame(rows, columns=["column", "id_site", "id_kind", "whole", "token", "rows_affected"])
    los = co.set_index("stay_key")["los_hours"].astype("float64")
    r = raw.assign(los=raw["stay_key"].astype(str).map(los))
    big = r["hour"].abs() > 24 * 365
    out = r[big]
    hours = pd.DataFrame({"rows_over_a_year": [len(out)], "stays": [out["stay_key"].nunique()],
                          "stays_longer_than_a_year": [out.loc[out["los"] > 24 * 365, "stay_key"].nunique()],
                          "rows_beyond_own_stay": [int(((r["hour"] > r["los"] + 48) | (r["hour"] < -48)).sum())],
                          "rows_without_los": [int(r["los"].isna().sum())]})
    by_concept = out.groupby("concept").size().sort_values(ascending=False).head(10).rename("rows").reset_index()
    return ids, hours, by_concept


def diagnose_text(harmonised_dir, static, cfg, site, group, top=10):
    """Counts-only profile of the string columns of one output file, to explain a failed free-text check. Returns (columns, concepts):
    columns: per string column the distinct strings, mean and longest length, distinct strings over 40 characters, and distinct strings the
    note scan flags; concepts: for `value_text` and `value_raw`, the concepts with the most distinct strings (names of concepts only)."""
    allco = cohort_static(static)
    km = make_keys(allco, cfg, source_ids(allco))
    kmap = dict(zip(km[km["site"] == site]["stay_key"], km[km["site"] == site]["new_stay_key"]))
    raw = pd.read_parquet(Path(harmonised_dir) / f"{site}_{group}.parquet")
    df, _ = transform_series(raw, site, "drugs" if group == "drugs" else "series", kmap, cfg, set())
    rows, per = [], []
    for c in [c for c in df.columns if df[c].dtype == object or pd.api.types.is_string_dtype(df[c])]:
        u = pd.Series(df[c].dropna().unique()).astype("string")
        if not len(u):
            continue
        rows.append({"column": c, "distinct": len(u), "mean_len": round(float(u.str.len().mean()), 1), "max_len": int(u.str.len().max()),
                     "over_40_chars": int((u.str.len() > 40).sum()), "note_like": int(note_like(u, cfg.raw_max_len, common_strings(df, c, cfg.text_k) if "stay_key" in df.columns else None).sum())})
        if c in ("value_text", "value_raw"):
            g = df.dropna(subset=[c]).groupby("concept")[c].agg(distinct="nunique", mean_len=lambda x: round(float(x.str.len().mean()), 1))
            per.append(g.assign(column=c).sort_values("distinct", ascending=False).head(top).reset_index())
    return pd.DataFrame(rows), (pd.concat(per, ignore_index=True) if per else pd.DataFrame())


def text_vocabulary(harmonised_dir, sites=SITES, k=10):
    """How much of each recorded text vocabulary is rare: per site and concept with `value_text`, the distinct strings, how many are seen in
    fewer than k stays, the rows and stays that carry a rare string and their shares. Counts only (no strings). This is what the Tier 2
    rule changes, and what a `value_group` mapping would have to cover."""
    rows = []
    for site in sites:
        for f in sorted(Path(harmonised_dir).glob(f"{site}_*.parquet")):
            if f.stem.endswith(("_rejected", "_drugs")):
                continue
            d = pd.read_parquet(f, columns=["stay_key", "concept", "value_text"])
            d = d[d["value_text"].notna()]
            if d.empty:
                continue
            n_stays = d.groupby(["concept", "value_text"])["stay_key"].nunique().rename("stays")
            d = d.join(n_stays, on=["concept", "value_text"])
            d["rare"] = d["stays"] < k
            for c, g in d.groupby("concept"):
                u = g.drop_duplicates("value_text")
                rows.append({"site": site, "concept": c, "distinct": len(u), "distinct_rare": int(u["rare"].sum()), "rows": len(g),
                             "rows_rare": int(g["rare"].sum()), "share_rows_rare": round(float(g["rare"].mean()), 4), "stays": g["stay_key"].nunique(),
                             "stays_with_rare": g.loc[g["rare"], "stay_key"].nunique()})
    out = pd.DataFrame(rows)
    if len(out):
        out["share_stays_with_rare"] = (out["stays_with_rare"] / out["stays"]).round(4)
    return out


def load_level(out_root, name, group=None, site=None):
    """Read an output of `run`: group None gives the static table; otherwise that group (Tier 1 files also need `site`)."""
    d = Path(out_root) / name
    if group is None:
        return pd.read_parquet(d / "static.parquet")
    return pd.read_parquet(d / (f"{site}_{group}.parquet" if site else f"{group}.parquet"))