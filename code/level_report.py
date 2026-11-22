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
    """One table: per variant the accuracy, the baseline, the gain over the baseline (percentage points) and the recall for each site."""
    rows = []
    for label, r in res.items():
        row = {"variant": label, "features": r["features"], "accuracy": r["accuracy"], "baseline": r["baseline"],
               "gain_pts": round((r["accuracy"] - r["baseline"]) * 100, 1)}
        row.update({f"recall_{s}": float(v) for s, v in r["recall_by_site"].items()})
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