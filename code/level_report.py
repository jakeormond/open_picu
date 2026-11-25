"""Per-level privacy report on the files that `anonymise.run` wrote. Everything is measured on the released tables, not on the harmonised data:
what a user of the release can see. Inside the SDE only; counts, shares and accuracies leave, never rows.

Two questions per level:
  1. Static fields: how many stays sit in small cells on the released quasi-identifiers (`cell_summary`).
  2. Site inference: how well a classifier can guess which hospital a stay came from, from the released static fields, from which concepts
     (and drugs) a stay has any rows of, and from both together (`site_report`). The site labels come from the private key map, used only to
     score the guesses; the released files carry no site at Tier 2.

The classifier is the one used in step 9 (`reid.site_inference`): gradient boosting, 100 iterations, untuned, one-hot with missing as a
category, 5-fold cross-validation grouped by patient (site and patient ID, taken from the static table and the key map) so a patient's stays
are never in both training and test folds. The baseline is always guessing the largest site. Accuracy is a lower bound on what an attacker
with a better model could do.

Typical use (notebook level_report.ipynb):
    import level_report as LR
    res = LR.site_report(out_root, "tier2", static)            # dict of variant -> result, plus counts
    LR.summary(res)                                             # table of accuracy, baseline and recall by site
    LR.cell_summary(out_root, "tier2")                          # small-cell shares
    LR.plot(res, path=...)                                      # figure (needs the output check before it leaves the SDE)

Which concepts give the site away, and do shared concepts differ across sites (a large shift can be a processing problem):
    LR.concept_coverage_released(out_root, "tier2")             # share of each site's stays with the concept; n_sites
    LR.single_concept_accuracy(out_root, "tier2")               # site guessed from one concept's presence alone
    LR.removal_curve(out_root, "tier2", static)                 # accuracy as the most revealing concepts are removed
    LR.concept_shift(out_root, "tier2")                         # per-site value quantiles, shift, KS, unit-factor hint
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import anonymise as AN
import reid as R

QUASI = AN.QUASI


def _level_dir(out_root, name):
    return Path(out_root) / name


def load_static(out_root, name):
    """The released static table of a level (stay_key is the new key)."""
    return pd.read_parquet(_level_dir(out_root, name) / "static.parquet")


def cell_summary(out_root, name, ks=(5, 10, 20)):
    """Stays in small cells of the released quasi-identifiers (age band, sex, ethnicity, diagnosis group, outcome, weight band, and the PIM band
    if released), all sites together: for each k the number and share of stays in cells below k, and the smallest cell. Counts only."""
    st = load_static(out_root, name)
    cols = [c for c in QUASI + ["pim_band"] if c in st.columns]
    size = st.groupby([st[c].astype("string").fillna("(missing)") for c in cols])["stay_key"].transform("size")
    rows = [{"k": k, "stays_in_cells_below_k": int((size < k).sum()), "share": round(float((size < k).mean()), 5)} for k in ks]
    out = pd.DataFrame(rows)
    out.attrs["fields"] = cols
    out.attrs["smallest_cell"] = int(size.min())
    out.attrs["stays"] = len(st)
    return out


def _presence(out_root, name, stays, drugs):
    """Stay x concept booleans from the released files of a level: does the stay have at least one row of the concept? Non-drug files when
    drugs=False, the drug file when drugs=True. This is all a user of a pooled release can see (a concept never recorded at a site looks the
    same as a concept absent for a stay)."""
    parts = []
    for f in sorted(_level_dir(out_root, name).glob("*.parquet")):
        if f.stem == "static":
            continue
        if f.stem.endswith("drugs") != drugs:
            continue
        parts.append(pd.read_parquet(f, columns=["stay_key", "concept"]).drop_duplicates())
    if not parts:
        return pd.DataFrame(index=stays)
    t = pd.concat(parts, ignore_index=True).drop_duplicates()
    wide = pd.crosstab(t["stay_key"], t["concept"]) > 0
    return wide.reindex(stays).fillna(False)


def labels(out_root, name, static, stays):
    """Site and patient group for each released stay, from the private key map and the static table. Returns (site, groups)."""
    km = pd.read_parquet(Path(out_root) / "_private" / f"{name}_key_map.parquet")
    km["stay_key"] = km["stay_key"].astype(str)
    co = AN.cohort_static(static)[["site", "stay_key", "patient_id"]]
    km = km.merge(co, on=["site", "stay_key"], how="left").set_index("new_stay_key")
    site = km.loc[stays, "site"].astype(str)
    pid = km.loc[stays, "patient_id"].astype("string")
    fallback = pd.Series([f"stay{i}" for i in range(len(stays))], index=site.index, dtype="string")
    groups = site + ":" + pid.where(pid.notna() & (pid.str.strip() != ""), fallback)
    return site.to_numpy(), groups.to_numpy()


def site_report(out_root, name, static, include_drugs=True, seed=0):
    """Site inference on the released files of a level. Returns a dict: variant name -> `reid.site_inference` result (accuracy, baseline,
    recall by site), with the number of stays and feature columns in each result under "stays" and "features". Variants: released static
    fields; which concepts a stay has; static fields and concepts; and, if include_drugs, static fields, concepts and which drugs."""
    st = load_static(out_root, name)
    stays = st["stay_key"].astype(str).tolist()
    st = st.assign(stay_key=stays).set_index("stay_key")
    site, groups = labels(out_root, name, static, stays)
    avail = _presence(out_root, name, stays, drugs=False).add_prefix("has_")
    variants = {"static fields": st, "concepts present": avail, "static + concepts": st.join(avail)}
    if include_drugs:
        dr = _presence(out_root, name, stays, drugs=True).add_prefix("drug_")
        variants["static + concepts + drugs"] = st.join(avail).join(dr)
    out = {}
    for label, X in variants.items():
        r = R.site_inference(X.reset_index(drop=True), site, drop_one=False, seed=seed, groups=groups)
        r["stays"], r["features"] = len(X), X.shape[1]
        out[label] = r
    return out


def summary(res):
    """One table: per variant the accuracy, the baseline, the gain over the baseline (percentage points), the balanced accuracy (mean of the
    recall of each site; chance is 1 / number of sites whatever the site sizes, so levels with different site mixes can be compared) and the
    recall for each site."""
    rows = []
    for label, r in res.items():
        rec = {s: float(v) for s, v in r["recall_by_site"].items()}
        row = {"variant": label, "features": r["features"], "accuracy": r["accuracy"], "baseline": r["baseline"],
               "gain_pts": round((r["accuracy"] - r["baseline"]) * 100, 1),
               "balanced_acc": round(float(np.mean(list(rec.values()))), 4)}
        row.update({f"recall_{s}": v for s, v in rec.items()})
        rows.append(row)
    return pd.DataFrame(rows)


def plot(res, title="Guessing the site from the released files", path=None):
    """Figure of the variants (accuracy against the baseline, and recall by site). Make sure it passes the output check before it leaves."""
    return R.plot_site_variants(res, title=title, path=path)


# ---------------------------------------------------------------------------------------------------------------------------------------
# Which concepts give the site away, and do shared concepts differ across sites?
# ---------------------------------------------------------------------------------------------------------------------------------------

def stay_sites(out_root, name):
    """Site of each released stay (index: new stay key), from the private key map. Used to score and to split, never released."""
    km = pd.read_parquet(Path(out_root) / "_private" / f"{name}_key_map.parquet")
    return km.drop_duplicates("new_stay_key").set_index("new_stay_key")["site"].astype(str)


def _released_files(out_root, name, drugs=False):
    return [f for f in sorted(_level_dir(out_root, name).glob("*.parquet"))
            if f.stem != "static" and f.stem.endswith("drugs") == drugs]


def concept_coverage_released(out_root, name, drugs=False, min_share=0.01):
    """For each concept in the released files: the share of each site's stays with at least one row (a site's stays are counted from the key map),
    the largest difference between sites (`spread`), the number of sites where the share is at least min_share, and the sites. A concept with n_sites == 1 identifies its site by being present."""
    site = stay_sites(out_root, name)
    n_site = site.value_counts()
    parts = [pd.read_parquet(f, columns=["stay_key", "concept"]).drop_duplicates() for f in _released_files(out_root, name, drugs)]
    if not parts:
        return pd.DataFrame(columns=["concept", "n_sites", "sites"])
    t = pd.concat(parts, ignore_index=True).drop_duplicates()
    t["site"] = t["stay_key"].map(site)
    cnt = t.groupby(["concept", "site"]).size().unstack("site").reindex(columns=n_site.index).fillna(0)
    share = cnt.div(n_site, axis=1)
    out = share.add_prefix("share_").round(4)
    out["spread"] = (share.max(axis=1) - share.min(axis=1)).round(4)     # largest minus smallest site share
    out["n_sites"] = (share >= min_share).sum(axis=1)
    out["sites"] = share.apply(lambda r: ", ".join(r.index[r >= min_share]), axis=1)
    return out.reset_index().sort_values(["n_sites", "concept"]).reset_index(drop=True)


def single_concept_accuracy(out_root, name, drugs=False):
    """Site guessed from one concept's presence alone: for each concept the best possible accuracy using only 'has / does not have rows of this
    concept' (best site for each of the two groups), against the baseline of always guessing the largest site. Exact, no model; counts only.
    gain_pts is the accuracy minus the baseline in percentage points; the concepts at the top are the ones that give the site away."""
    site = stay_sites(out_root, name)
    stays = site.index
    base = float(site.value_counts(normalize=True).max())
    wide = _presence(out_root, name, stays, drugs=drugs)
    rows = []
    for c in wide.columns:
        has = wide[c].to_numpy()
        ct = pd.crosstab(has, site.to_numpy())
        acc = float(ct.max(axis=1).sum() / len(site))
        rows.append({"concept": c, "stays_with": int(has.sum()), "share_with": round(float(has.mean()), 4),
                     "accuracy": round(acc, 4), "gain_pts": round((acc - base) * 100, 1)})
    out = pd.DataFrame(rows).sort_values("gain_pts", ascending=False).reset_index(drop=True)
    out.attrs["baseline"] = base
    return out


def removal_curve(out_root, name, static, steps=(0, 3, 6, 10, 15, 20, 30), seed=0):
    """Accuracy of guessing the site from which concepts a stay has, as the most revealing concepts (ranked by single_concept_accuracy) are
    removed from the feature set: steps = how many of the top concepts to leave out. Shows how many concepts have to go (or be merged) before
    the site is no longer certain. Uses the same classifier and folds as site_report; needs scikit-learn."""
    st = load_static(out_root, name)
    stays = st["stay_key"].astype(str).tolist()
    site, groups = labels(out_root, name, static, stays)
    wide = _presence(out_root, name, stays, drugs=False)
    order = list(single_concept_accuracy(out_root, name)["concept"])
    rows = []
    for n in steps:
        keep = [c for c in wide.columns if c not in set(order[:n])]
        if not keep:
            rows.append({"removed": n, "concepts_left": 0, "accuracy": float("nan")})
            continue
        r = R.site_inference(wide[keep].add_prefix("has_").reset_index(drop=True), site, drop_one=False, seed=seed, groups=groups)
        rows.append({"removed": n, "concepts_left": len(keep), "accuracy": r["accuracy"], "baseline": r["baseline"],
                     "last_removed": order[n - 1] if n else ""})
    return pd.DataFrame(rows)


_SCALES = {"x10": 10.0, "x100": 100.0, "x1000": 1000.0, "x60": 60.0, "x7.5 (kPa/mmHg)": 7.50062, "x1.8 (C/F)": 1.8}


def _scale_hint(ratio):
    """Name of a common unit factor the ratio of two medians is within 5% of (either way round), else ''."""
    if not np.isfinite(ratio) or ratio <= 0:
        return ""
    r = max(ratio, 1 / ratio)
    for label, f in _SCALES.items():
        if abs(r / f - 1) < 0.05:
            return label
    return ""


def concept_shift(out_root, name, min_stays=10, drugs=False):
    """For each numeric concept recorded at two or more sites (at least min_stays stays each): the distribution of the per-stay median value at
    each site (p5, p25, p50, p75, p95), and how far apart the sites are.
      shift   largest difference between two sites' medians, in units of the typical within-site spread (median over sites of IQR / 1.349 of the per-stay medians)
      ks      largest two-sample Kolmogorov-Smirnov distance between two sites (0 identical, 1 disjoint)
      ratio   the median ratio for that pair; scale_hint names a common unit factor (x10, x100, x1000, x60, kPa/mmHg, C/F) if the ratio is
              within 5% of one, which would point at a unit or processing problem rather than a real difference
    Sorted by shift, largest first. Reads value from the released files, per-stay medians only; quantiles of per-stay values leave the SDE as
    summary counts after the output check, never rows. Needs scipy."""
    from scipy.stats import ks_2samp
    site = stay_sites(out_root, name)
    parts = []
    for f in _released_files(out_root, name, drugs):
        d = pd.read_parquet(f, columns=["stay_key", "concept", "value"])
        d = d[pd.to_numeric(d["value"], errors="coerce").notna()]
        d["value"] = pd.to_numeric(d["value"])
        parts.append(d.groupby(["stay_key", "concept"], observed=True)["value"].median().rename("m").reset_index())
    if not parts:
        return pd.DataFrame()
    m = pd.concat(parts, ignore_index=True)
    m["site"] = m["stay_key"].map(site)
    rows = []
    for c, g in m.groupby("concept", observed=True):
        per = {s: v["m"].to_numpy() for s, v in g.groupby("site") if len(v) >= min_stays}
        if len(per) < 2:
            continue
        row = {"concept": c, "n_sites": len(per)}
        for s, a in per.items():
            q = np.percentile(a, [5, 25, 50, 75, 95])
            row.update({f"{s}_n": len(a), f"{s}_p5": q[0], f"{s}_p25": q[1], f"{s}_p50": q[2], f"{s}_p75": q[3], f"{s}_p95": q[4]})
        spread = float(np.median([(np.percentile(a, 75) - np.percentile(a, 25)) / 1.349 for a in per.values()]))   # typical within-site spread
        best = (-1.0, None, None)
        ks = 0.0
        names = sorted(per)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                diff = abs(np.median(per[a]) - np.median(per[b]))
                z = diff / spread if spread > 0 else (np.inf if diff > 0 else 0.0)
                if z > best[0]:
                    best = (z, a, b)
                ks = max(ks, float(ks_2samp(per[a], per[b]).statistic))
        z, a, b = best
        ma, mb = np.median(per[a]), np.median(per[b])
        ratio = (ma / mb) if mb not in (0, 0.0) else float("nan")
        row.update({"shift": round(float(z), 2), "ks": round(ks, 3), "pair": f"{a} vs {b}", "ratio": round(float(ratio), 3) if np.isfinite(ratio) else np.nan,
                    "scale_hint": _scale_hint(ratio)})
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    lead = ["concept", "n_sites", "shift", "ks", "pair", "ratio", "scale_hint"]
    return out[lead + [c for c in out.columns if c not in lead]].sort_values("shift", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------------------------------------------------------------------
# Cached site report (the classifier takes minutes per level)
# ---------------------------------------------------------------------------------------------------------------------------------------

def _cache_path(out_root, name, include_drugs, seed):
    return Path(out_root) / "_private" / f"site_report_{name}_drugs{int(include_drugs)}_seed{seed}.pkl"


def cached_site_report(out_root, name, static, include_drugs=True, seed=0, refresh=False):
    """`site_report`, saved after the first run and reloaded afterwards. The cache (accuracies and recalls only, no rows) sits in
    <out_root>/_private and is rebuilt when refresh=True or when any released file of the level is newer than it (the level was run again).
    Prints which of the two happened."""
    import pickle
    p = _cache_path(out_root, name, include_drugs, seed)
    files = list(_level_dir(out_root, name).glob("*.parquet")) + [Path(out_root) / "_private" / f"{name}_key_map.parquet"]
    if p.exists() and not refresh and p.stat().st_mtime >= max(f.stat().st_mtime for f in files):
        print(f"{name}: loaded from cache ({p.name})")
        with open(p, "rb") as fh:
            return pickle.load(fh)
    res = site_report(out_root, name, static, include_drugs=include_drugs, seed=seed)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as fh:
        pickle.dump(res, fh)
    print(f"{name}: computed and saved ({p.name})")
    return res


def compare_levels(out_root, names, static, **kw):
    """One table of `summary` for several levels, using the cache. Returns (table, dict of results)."""
    res = {n: cached_site_report(out_root, n, static, **kw) for n in names}
    tab = pd.concat([summary(r).assign(level=n) for n, r in res.items()], ignore_index=True)
    return tab[["level"] + [c for c in tab.columns if c != "level"]], res


def drugs_only_report(out_root, name, static, seed=0, refresh=False):
    """Site inference from which drugs a stay has any rows of, and nothing else (`site_report` only has the drug columns together with static
    fields and concepts). Same classifier, folds and cache rule as `cached_site_report`; the cache file is separate. Returns {"drugs only": result}
    with the usual keys. Pair it with `single_concept_accuracy(out_root, name, drugs=True)`, which says which drugs give the site away."""
    import pickle
    p = Path(out_root) / "_private" / f"drugs_only_{name}_seed{seed}.pkl"
    files = list(_level_dir(out_root, name).glob("*.parquet")) + [Path(out_root) / "_private" / f"{name}_key_map.parquet"]
    if p.exists() and not refresh and p.stat().st_mtime >= max(f.stat().st_mtime for f in files):
        print(f"{name}: drugs only loaded from cache")
        with open(p, "rb") as fh:
            return pickle.load(fh)
    st = load_static(out_root, name)
    stays = st["stay_key"].astype(str).tolist()
    site, groups = labels(out_root, name, static, stays)
    X = _presence(out_root, name, stays, drugs=True).add_prefix("drug_")
    r = R.site_inference(X.reset_index(drop=True), site, drop_one=False, seed=seed, groups=groups)
    r["stays"], r["features"] = len(X), X.shape[1]
    res = {"drugs only": r}
    with open(p, "wb") as fh:
        pickle.dump(res, fh)
    print(f"{name}: drugs only computed and saved")
    return res


# ---------------------------------------------------------------------------------------------------------------------------------------
# Site inference from values and recording pattern, not only from what is present
# ---------------------------------------------------------------------------------------------------------------------------------------

def _value_features(out_root, name, stays):
    """Per stay and concept, from the numeric series rows of the released files (not drugs): the median value, the number of rows and the median
    gap in hours between consecutive rows. Returns three stay x concept frames indexed by `stays`. Not the series itself."""
    parts = []
    for f in _released_files(out_root, name, drugs=False):
        d = pd.read_parquet(f, columns=["stay_key", "concept", "hour", "value"])
        d["value"] = pd.to_numeric(d["value"], errors="coerce")
        d = d[d["value"].notna()]
        d["stay_key"] = d["stay_key"].astype(str).astype("category")
        d["concept"] = d["concept"].astype(str).astype("category")
        parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    d["stay_key"] = d["stay_key"].astype(str)
    d["concept"] = d["concept"].astype(str)
    d = d.sort_values(["stay_key", "concept", "hour"], kind="stable")
    g = d.groupby(["stay_key", "concept"], sort=False)
    med = g["value"].median().unstack("concept")
    n = g["value"].size().unstack("concept")
    d["gap"] = g["hour"].diff()
    gap = d.groupby(["stay_key", "concept"], sort=False)["gap"].median().unstack("concept")
    return [x.reindex(stays) for x in (med, n, gap)]


def value_report(out_root, name, static, include_drugs=True, seed=0, refresh=False, drop=()):
    """Site inference that sees values and recording pattern as well as presence (`site_report` sees only presence). Per stay and concept:
    the median value ("med_"), the number of rows ("n_") and the median gap in hours between rows ("gap_"), used as numbers, missing where the
    stay has no row of the concept. Variants, each with the stay's concept-presence columns:
      concepts + median values
      concepts + values + recording pattern (rows and gaps)
      everything: static fields, concepts, drugs (presence), values and recording pattern.
    Compare with the `site_report` variants for the same level: the difference is what values and recording pattern add. Not used: text strings,
    drug units and routes, the series itself. Same classifier and folds as `site_report`. The result is cached like `cached_site_report`.
    drop: concepts the attacker is not given (presence, value and pattern), to test how much of the result rests on them; the cache name then
    carries the dropped concepts."""
    import pickle
    p = Path(out_root) / "_private" / f"value_report_{name}_drugs{int(include_drugs)}_seed{seed}{'_drop_' + '-'.join(sorted(drop)) if drop else ''}.pkl"
    files = list(_level_dir(out_root, name).glob("*.parquet")) + [Path(out_root) / "_private" / f"{name}_key_map.parquet"]
    if p.exists() and not refresh and p.stat().st_mtime >= max(f.stat().st_mtime for f in files):
        print(f"{name}: value report loaded from cache")
        with open(p, "rb") as fh:
            return pickle.load(fh)
    st = load_static(out_root, name)
    stays = st["stay_key"].astype(str).tolist()
    st = st.assign(stay_key=stays).set_index("stay_key")
    site, groups = labels(out_root, name, static, stays)
    avail = _presence(out_root, name, stays, drugs=False).drop(columns=list(drop), errors="ignore").add_prefix("has_")
    med, n, gap = [x.drop(columns=list(drop), errors="ignore") for x in _value_features(out_root, name, stays)]
    vals = med.add_prefix("med_")
    pattern = n.add_prefix("n_").join(gap.add_prefix("gap_"))
    variants = {"concepts + median values": avail.join(vals),
                "concepts + values + recording pattern": avail.join(vals).join(pattern)}
    full = st.join(avail)
    if include_drugs:
        full = full.join(_presence(out_root, name, stays, drugs=True).add_prefix("drug_"))
    variants["everything (static, drugs, values, pattern)"] = full.join(vals).join(pattern)
    out = {}
    for label, X in variants.items():
        num = [c for c in X.columns if c.startswith(("med_", "n_", "gap_"))]
        r = R.site_inference(X.reset_index(drop=True), site, drop_one=False, seed=seed, groups=groups, numeric=num)
        r["stays"], r["features"] = len(X), X.shape[1]
        out[label] = r
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as fh:
        pickle.dump(out, fh)
    print(f"{name}: value report computed and saved")
    return out


def concept_importance(out_root, name, static, seed=0, repeats=3, refresh=False):
    """Which concepts give the site away to a value-aware attacker. One classifier per fold (stays of a patient stay together) is fitted on
    every concept's presence, median value, row count and gap; then, on the held-out stays, the columns of one concept are shuffled across
    stays and the fall in accuracy is recorded (percentage points, mean over folds and `repeats` shuffles; negative is noise). Columns:
      all      the concept's presence, value and recording pattern shuffled together (what the attacker loses without that concept)
      values   only its median value shuffled
      pattern  only its row count and gap shuffled
    Shuffling understates a concept whose information is shared with another (for example two blood-gas values); read it as a ranking, not a
    sum. Counts only. Cached as `_private/concept_importance_<name>_seed<seed>.pkl`."""
    import pickle
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import StratifiedGroupKFold
    p = Path(out_root) / "_private" / f"concept_importance_{name}_seed{seed}.pkl"
    files = list(_level_dir(out_root, name).glob("*.parquet")) + [Path(out_root) / "_private" / f"{name}_key_map.parquet"]
    if p.exists() and not refresh and p.stat().st_mtime >= max(f.stat().st_mtime for f in files):
        print(f"{name}: concept importance loaded from cache")
        with open(p, "rb") as fh:
            return pickle.load(fh)
    st = load_static(out_root, name)
    stays = st["stay_key"].astype(str).tolist()
    site, groups = labels(out_root, name, static, stays)
    avail = _presence(out_root, name, stays, drugs=False).astype(float)
    med, n, gap = _value_features(out_root, name, stays)
    concepts = [c for c in avail.columns if c in med.columns]
    parts = {"has": avail[concepts], "med": med[concepts], "n": n[concepts], "gap": gap[concepts]}
    X = pd.concat([v.add_prefix(k + "_") for k, v in parts.items()], axis=1)
    cols = {c: {"all": [f"{k}_{c}" for k in parts], "values": [f"med_{c}"], "pattern": [f"n_{c}", f"gap_{c}"]} for c in concepts}
    Z = X.to_numpy(dtype="float64")
    idx = {c: i for i, c in enumerate(X.columns)}
    y = np.asarray(site).astype(str)
    rng = np.random.default_rng(seed)
    drops = {c: {k: [] for k in ("all", "values", "pattern")} for c in concepts}
    folds = StratifiedGroupKFold(5, shuffle=True, random_state=seed)
    for tr, te in folds.split(Z, y, groups=np.asarray(groups)):
        m = HistGradientBoostingClassifier(random_state=seed, max_iter=100).fit(Z[tr], y[tr])
        base = float((m.predict(Z[te]) == y[te]).mean())
        for c in concepts:
            for kind, cs in cols[c].items():
                ci = [idx[k] for k in cs]
                for _ in range(repeats):
                    W = Z[te].copy()
                    W[:, ci] = W[rng.permutation(len(te))][:, ci]
                    drops[c][kind].append(base - float((m.predict(W) == y[te]).mean()))
    out = pd.DataFrame({c: {k: round(100 * float(np.mean(v)), 2) for k, v in d.items()} for c, d in drops.items()}).T
    out = out.sort_values("all", ascending=False)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as fh:
        pickle.dump(out, fh)
    print(f"{name}: concept importance computed and saved")
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------
# Figures for the site-inference work (all from cached reports; counts and percentages only)
# ---------------------------------------------------------------------------------------------------------------------------------------
_VARIANT_LABELS = {"static fields": "Static fields", "concepts present": "Which concepts are present",
                   "static + concepts + drugs": "Static + concepts + drugs present",
                   "concepts + median values": "Concepts + median values",
                   "concepts + values + recording pattern": "Concepts + values + recording pattern",
                   "everything (static, drugs, values, pattern)": "Everything (static, drugs, values, pattern)"}


def _all_variants(out_root, name, static):
    """Presence-only and value-aware results of one level in one dict (both from the cache; computed if missing)."""
    res = dict(cached_site_report(out_root, name, static))
    res.update(value_report(out_root, name, static))
    return {k: res[k] for k in _VARIANT_LABELS if k in res}


def fig_attacker_ladder(out_root, name, static, path=None):
    """Horizontal bars: balanced accuracy of guessing the site (mean recall over the sites) for what the attacker is given, from least to
    most. The dashed line is chance (one in the number of sites). The sets are not strictly nested (static fields appear in three of them),
    the label says what each holds."""
    import matplotlib.pyplot as plt
    res = _all_variants(out_root, name, static)
    t = summary(res).set_index("variant")
    vals = (t["balanced_acc"] * 100).sort_values()
    n_sites = len([c for c in t.columns if c.startswith("recall_")])
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    R._ax(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=R.GRID, linewidth=0.8)
    y = np.arange(len(vals))
    ax.barh(y, vals.values, color=R.CAT[0], height=0.62)
    for yi, v in zip(y, vals.values):
        ax.text(v + 0.8, yi, f"{v:.1f}%", va="center", fontsize=9, color=R.INK)
    ax.axvline(100 / n_sites, color=R.INK2, linestyle="--", linewidth=1)
    ax.text(100 / n_sites + 0.8, -0.62, f"chance {100 / n_sites:.0f}%", fontsize=8.5, color=R.INK2, va="center")
    ax.set_ylim(-0.9, len(vals) - 0.4)
    ax.set_yticks(y)
    ax.set_yticklabels([_VARIANT_LABELS[v] for v in vals.index], fontsize=9, color=R.INK)
    ax.set_xlim(0, 108)
    ax.set_xlabel("Balanced accuracy of guessing the site (%)", color=R.INK2, fontsize=9)
    ax.set_title(f"What an attacker needs to guess the site ({name})", loc="left", fontsize=11, color=R.INK, pad=10)
    return R._save(fig, path)


def fig_site_recall(out_root, name, static, path=None):
    """Grouped bars: recall for each site (the share of that site's stays guessed correctly) for each attacker variant."""
    import matplotlib.pyplot as plt
    t = summary(_all_variants(out_root, name, static))
    sites = [c.replace("recall_", "") for c in t.columns if c.startswith("recall_")]
    fig, ax = plt.subplots(figsize=(9, 3.9))
    R._ax(ax)
    w = 0.8 / len(sites)
    x = np.arange(len(t))
    for i, s in enumerate(sites):
        v = t[f"recall_{s}"] * 100
        ax.bar(x + (i - (len(sites) - 1) / 2) * w, v, width=w * 0.92, color=R.CAT[i], label=s)
        for xi, vi in zip(x + (i - (len(sites) - 1) / 2) * w, v):
            ax.text(xi, vi + 1, f"{vi:.0f}", ha="center", fontsize=7.5, color=R.INK2)
    ax.axhline(100 / len(sites), color=R.INK2, linestyle="--", linewidth=1)
    ax.set_xticks(x)
    import textwrap
    ax.set_xticklabels([textwrap.fill(_VARIANT_LABELS[v], 17) for v in t["variant"]], fontsize=7.5, color=R.INK)
    ax.set_ylim(0, 108)
    ax.set_ylabel("Stays of the site guessed correctly (%)", color=R.INK2, fontsize=9)
    ax.legend(frameon=False, fontsize=9, ncol=len(sites), loc="upper left")
    ax.set_title(f"Recall by site ({name})", loc="left", fontsize=11, color=R.INK, pad=10)
    return R._save(fig, path)


def fig_removal(out_root, name, static, drops, variants=("concepts + values + recording pattern", "everything (static, drugs, values, pattern)"), path=None):
    """Balanced accuracy of the value-aware attacker when groups of concepts are removed. `drops`: label -> list of concepts, in the order shown
    (the first point is no concepts removed). Reads or fills the `value_report` cache. Shows that removing concepts does not hide the site."""
    import matplotlib.pyplot as plt
    pts = {"none removed": ()} | {k: tuple(v) for k, v in drops.items()}
    rows = {}
    for label, d in pts.items():
        t = summary(value_report(out_root, name, static, drop=d)).set_index("variant")
        rows[label] = {v: float(t.loc[v, "balanced_acc"]) * 100 for v in variants}
    n_sites = len([c for c in summary(value_report(out_root, name, static)).columns if c.startswith("recall_")])
    fig, ax = plt.subplots(figsize=(8.5, 3.9))
    R._ax(ax)
    x = np.arange(len(pts))
    for i, v in enumerate(variants):
        y = [rows[k][v] for k in pts]
        ax.plot(x, y, marker="o", color=R.CAT[i], linewidth=2, markersize=6, label=_VARIANT_LABELS[v].split(" (")[0])
        for xi, yi in zip(x, y):
            ax.text(xi, yi + 2.2 if i == 0 else yi - 4.6, f"{yi:.1f}", ha="center", fontsize=8, color=R.INK2)
    ax.axhline(100 / n_sites, color=R.INK2, linestyle="--", linewidth=1)
    ax.text(0, 100 / n_sites + 1.5, f"chance {100 / n_sites:.0f}%", fontsize=8.5, color=R.INK2)
    ax.set_xticks(x)
    import textwrap
    ax.set_xticklabels([textwrap.fill(k, 16) for k in pts], fontsize=8, color=R.INK)
    ax.set_xlim(-0.3, len(pts) - 1 + 0.3)
    ax.legend(frameon=False, fontsize=9, loc="center right", bbox_to_anchor=(1.0, 0.55))
    ax.set_ylim(0, 108)
    ax.set_ylabel("Balanced accuracy (%)", color=R.INK2, fontsize=9)
    ax.set_title(f"Removing the most revealing concepts does not hide the site ({name})", loc="left", fontsize=11, color=R.INK, pad=10)
    return R._save(fig, path)


def fig_concept_by_age(by_age, concept="creatinine", unit="umol/L", path=None):
    """One concept across age bands, one line per site: median of the stays' medians with the 10th to 90th percentile as a bar. `by_age` is
    the table from `harmonise.concept_by_age`. Separates a site difference that holds in every age band (assay or unit) from case mix."""
    import matplotlib.pyplot as plt
    order = [b[0] for b in __import__("harmonise").AGE_BANDS]
    sites = sorted(by_age["site"].unique())
    fig, ax = plt.subplots(figsize=(8, 3.9))
    R._ax(ax)
    x = np.arange(len(order))
    for i, s in enumerate(sites):
        g = by_age[by_age["site"] == s].set_index("age_band").reindex(order)
        xs = x + (i - (len(sites) - 1) / 2) * 0.12
        ax.vlines(xs, g["p10"], g["p90"], color=R.CAT[i], linewidth=3, alpha=0.35)
        ax.plot(xs, g["p50"], marker="o", color=R.CAT[i], linewidth=2, markersize=6, label=s)
    ax.set_xticks(x)
    ax.set_xticklabels(order, fontsize=9, color=R.INK)
    ax.set_xlim(-0.4, len(order) - 1 + 0.4)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.set_ylabel(f"{concept} ({unit})", color=R.INK2, fontsize=9)
    ax.set_xlabel("Age band", color=R.INK2, fontsize=9)
    ax.set_title(f"{concept.capitalize()} by site and age (dot: median; bar: 10th to 90th percentile)", loc="left", fontsize=10.5, color=R.INK, pad=10)
    return R._save(fig, path)


def site_figures(out_root, name, static, drops, by_age, outdir):
    """Make the four figures and save them as PNG in `outdir`. Returns the paths."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    made = {}
    for key, fn in (("attacker_ladder", lambda p: fig_attacker_ladder(out_root, name, static, p)),
                    ("site_recall", lambda p: fig_site_recall(out_root, name, static, p)),
                    ("removal", lambda p: fig_removal(out_root, name, static, drops, path=p)),
                    ("creatinine_by_age", lambda p: fig_concept_by_age(by_age, path=p))):
        made[key] = outdir / f"site_{key}_{name}.png"
        fn(made[key])
    return made


# ---------------------------------------------------------------------------------------------------------------------------------------
# What is in a release: the concept list
# ---------------------------------------------------------------------------------------------------------------------------------------
def release_manifest(out_root, name, min_share=0.01):
    """The concept list of a released level, from its files and its stored config. Returns a dict of tables:
      kept     one row per concept in the release: file group (vitals, vent, ...), kind (numeric, text or both), stays, rows, share of each
               site's stays that have it, `n_sites` (sites with at least `min_share`), `merged_from` (original concepts renamed to it)
      removed  one row per concept the level leaves out (`drop_concepts`) with the reason (one site only; not at all three sites; a
               site-specific pattern; or other) and `mapped_at`, the sites that have a source for it in the concept map (empty for a derived
               concept such as intake_iv). The reason is the list the concept is on, `mapped_at` is the check
      renamed  the merges (`rename_concepts`): original concept -> concept in the release
      drugs    one row per drug concept: stays and share of each site's stays
    The config is read from the level's config.json, so the lists follow whatever was run. To bring a concept back, take it out of
    `drop_concepts` and re-run the level. Counts only."""
    cfg = AN.config_from_level(out_root, name)
    cov = concept_coverage_released(out_root, name, min_share=min_share)
    info = []
    for f in _released_files(out_root, name, drugs=False):
        d = pd.read_parquet(f, columns=[c for c in ("stay_key", "concept", "value", "value_text") if c in pd.read_parquet(f).columns])
        num = d["value"].notna()
        txt = d["value_text"].notna() if "value_text" in d.columns else pd.Series(False, index=d.index)
        d = d.assign(_n=num, _t=txt)
        g = d.groupby("concept").agg(rows=("stay_key", "size"), stays=("stay_key", "nunique"), _n=("_n", "any"), _t=("_t", "any"))
        g["kind"] = np.where(g["_n"] & g["_t"], "both", np.where(g["_t"], "text", "numeric"))
        g["group"] = f.stem
        info.append(g[["group", "kind", "stays", "rows"]])
    info = pd.concat(info).reset_index()
    kept = info.merge(cov, on="concept", how="left")
    inv = {}
    for old, new in cfg.rename_concepts.items():
        inv.setdefault(new, []).append(old)
    kept["merged_from"] = kept["concept"].map(lambda c: ", ".join(sorted(inv.get(c, []))))
    kept = kept.sort_values(["group", "concept"]).reset_index(drop=True)
    why = {}
    for c in AN.ONE_SITE_DROP:
        why[c] = "one site only"
    for c in AN.FEW_SITES:
        why[c] = "not at all three sites"
    for c in AN.SITE_PATTERN_DROP:
        why[c] = "site-specific pattern"
    removed = pd.DataFrame({"concept": list(cfg.drop_concepts)})
    removed["reason"] = removed["concept"].map(why).fillna("other")
    import concepts as CM
    removed["mapped_at"] = removed["concept"].map(lambda c: ", ".join(s for s in CM.SITES if CM.CONCEPTS.get(c, {}).get(s)))
    removed = removed.sort_values(["reason", "concept"]).reset_index(drop=True)
    renamed = pd.DataFrame({"original": list(cfg.rename_concepts), "released_as": list(cfg.rename_concepts.values())})
    drugs = concept_coverage_released(out_root, name, drugs=True, min_share=min_share)
    return {"kept": kept, "removed": removed, "renamed": renamed, "drugs": drugs}
