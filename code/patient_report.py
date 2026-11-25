"""Patient-level privacy report on the files that `anonymise.run` wrote. Like `level_report`, everything is measured on the released tables of a
level (what a data user sees); site labels and patient identities come from the private key map and the static table and are used only to
score the attacks. Inside the SDE only; counts, shares and sizes leave, never rows.

THREAT MODEL (what the tests assume; see PRIVACY_THREAT_MODEL.md)
  The attacker holds the released files of one level and nothing else from the SDE (no keys, no site labels, no other level). The target is a
  person who had a PICU stay in the three hospitals. The attacker may know:
    S1  the target's demographics: age band, sex, weight band, diagnosis group and outcome (and ethnicity if the level releases it);
    S2  in addition, a few exact measurements from the stay (concept, hour since admission, value), as from a parent's chart, a clinician's
        memory, or a published case; the attacker does not know which record is the target's and wants to single it out;
    S3  that a patient had more than one stay (the attacker holds two stays and wants to know whether they belong to the same child);
    S4  the demographics only, and wants to learn the outcome (attribute disclosure).
  The tests are conservative on one axis (the attacker knows the exact hour and the exact value of every observation) and limited on others
  (observations are chosen at random, not for being rare; no linkage to outside data; no knowledge of a date, which the release does not hold).
  A result is therefore a statement about this attacker, not a guarantee.

Tests
  outcome_diversity(out_root, name)            S4: for each stay, the outcome of the stays that share its other quasi-identifiers (l-diversity)
  known_observation_attack(out_root, name)     S2 (and S1 as the m = 0 row): how many released stays fit m known observations
  repeat_stay_linkage(out_root, name, static)  S3: can the nearest stay in the same split group be a sibling stay of the same patient

Typical use (notebook patient_report.ipynb):
    import patient_report as PR
    PR.outcome_diversity(out_root, "tier2_merge_drop3_pre_epic")
    PR.known_observation_attack(out_root, "tier2_merge_drop3_pre_epic")
    PR.repeat_stay_linkage(out_root, "tier2_merge_drop3_pre_epic", static)
"""
from __future__ import annotations

from math import comb
from pathlib import Path

import numpy as np
import pandas as pd

import anonymise as AN
import level_report as LR


def _qi_cols(st):
    return [c for c in AN.QUASI + ["pim_band"] if c in st.columns]


def _cell_ids(st, cols):
    """An integer per combination of the columns (missing counts as a value)."""
    key = pd.concat([st[c].astype("string").fillna("(missing)") for c in cols], axis=1)
    return key.groupby(list(key.columns), sort=False).ngroup().to_numpy()


# ---------------------------------------------------------------------------------------------------------------------------------------
# S4: attribute disclosure (l-diversity)
# ---------------------------------------------------------------------------------------------------------------------------------------
def outcome_diversity(out_root, name, sensitive="died"):
    """What the other quasi-identifiers say about the outcome. The cell of a stay is the set of stays that share all released quasi-identifiers
    except `sensitive` (age band, sex, weight band, diagnosis group, ethnicity and PIM band where released). A person who knows a target's
    demographics and that the stay is in the data learns the cell's outcome rate. Rows:
      stays; positive stays (for example the deaths) and the overall rate;
      cells; stays in cells where every stay has the same outcome (l-diversity of 1; the outcome is then certain, for the common outcome as well);
      positive stays in cells where every stay is positive (the outcome of these is certain);
      positive stays in cells with a positive rate of at least 50% and at least 90% (the guess is right more often than not);
      the median cell positive rate among positive stays, against the overall rate (how much the cell tells beyond the base rate).
    Counts and shares only. A stay in a cell of one is counted as a cell of one (certain)."""
    st = LR.load_static(out_root, name)
    qi = [c for c in _qi_cols(st) if c != sensitive]
    cell = _cell_ids(st, qi)
    y = pd.to_numeric(st[sensitive].astype(float), errors="coerce").fillna(0).to_numpy() > 0
    n = np.bincount(cell)[cell]
    pos = np.bincount(cell, weights=y.astype(float))[cell]
    rate = pos / n
    allsame = (pos == 0) | (pos == n)
    base = float(y.mean())
    rows = [("stays", len(st), None),
            (f"{sensitive} stays", int(y.sum()), base),
            ("cells", int(cell.max() + 1), None),
            ("stays in cells where all stays have the same outcome", int(allsame.sum()), float(allsame.mean())),
            (f"{sensitive} stays alone in their cell or in cells where all are {sensitive}", int((y & (rate == 1)).sum()),
             float((y & (rate == 1)).sum() / max(y.sum(), 1))),
            (f"{sensitive} stays in cells with rate of at least 50%", int((y & (rate >= .5)).sum()), float((y & (rate >= .5)).sum() / max(y.sum(), 1))),
            (f"{sensitive} stays in cells with rate of at least 90%", int((y & (rate >= .9)).sum()), float((y & (rate >= .9)).sum() / max(y.sum(), 1))),
            (f"median cell {sensitive} rate among {sensitive} stays", None, float(np.median(rate[y])) if y.any() else np.nan)]
    out = pd.DataFrame(rows, columns=["item", "n", "share_or_rate"])
    out.attrs["fields"] = qi
    out.attrs["smallest_cell"] = int(n.min())
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------
# S2: the attacker knows a few measurements
# ---------------------------------------------------------------------------------------------------------------------------------------
def _load_series(out_root, name, stays):
    """All numeric series rows of a level (not drugs): stay (position in `stays`), concept, hour, value."""
    parts = []
    for f in LR._released_files(out_root, name, drugs=False):
        d = pd.read_parquet(f, columns=["stay_key", "concept", "hour", "value"])
        d = d[pd.to_numeric(d["value"], errors="coerce").notna()]
        parts.append(d)
    if not parts:
        return pd.DataFrame(columns=["stay", "concept", "hour", "value"])
    d = pd.concat(parts, ignore_index=True)
    d["stay"] = pd.Categorical(d["stay_key"].astype(str), categories=list(stays)).codes.astype("int32")
    d = d[d["stay"] >= 0]
    out = pd.DataFrame({"stay": d["stay"].to_numpy(), "concept": d["concept"].astype(str).to_numpy(),
                        "hour": d["hour"].astype("float64").to_numpy(), "value": pd.to_numeric(d["value"]).astype("float64").to_numpy()})
    return out.sort_values("stay", kind="stable").reset_index(drop=True)


def known_observation_attack(out_root, name, ms=(1, 3, 5, 10), n_targets=500, rel_tol=0.0, seed=0, k=10):
    """An attacker knows m measurements of one stay, each as (concept, hour since admission, value), and counts the released stays that contain
    every one of them. For each of `n_targets` random stays (with at least max(ms) numeric rows) and each m, m rows are drawn at random from
    the stay's own rows, nested (the first 3 are among the first 5). A stay fits an observation if it has a row of that concept at that hour with
    a value within rel_tol of the known one (rel_tol 0: equal; 0.05: within 5%, for an attacker with rounded knowledge). The candidate set is
    the stays that fit all m; it always contains the target.
      series only             candidates among all released stays
      series + static fields  candidates that also share the target's released quasi-identifiers (the attacker knows those too)
    Row m = 0 is the static fields alone. Columns: targets, unique (share of targets whose candidate set is just the target), below_k (share whose
    set is smaller than k, so the target is not hidden in a group of k), median and 10th percentile of the candidate set size.
    Conservative on the values and the hour (exact), not on the choice of observations (random, not the rarest). Counts and shares only."""
    rng = np.random.default_rng(seed)
    st = LR.load_static(out_root, name)
    stays = st["stay_key"].astype(str).to_numpy()
    cell = _cell_ids(st, _qi_cols(st))
    d = _load_series(out_root, name, stays)
    mmax = max(ms)
    cnt = np.bincount(d["stay"].to_numpy(), minlength=len(stays))
    eligible = np.flatnonzero(cnt >= mmax)
    if not len(eligible):
        return pd.DataFrame()
    tg = rng.choice(eligible, size=min(n_targets, len(eligible)), replace=False)
    off = np.r_[0, np.cumsum(cnt)]
    rows = []
    for t in tg:
        pick = off[t] + rng.choice(cnt[t], size=mmax, replace=False)
        rows.append(pd.DataFrame({"tgt": t, "j": np.arange(mmax), "row": pick}))
    Q = pd.concat(rows, ignore_index=True)
    Q = Q.join(d[["concept", "hour", "value"]], on="row").rename(columns={"value": "vq"})
    by_concept = {c: g[["stay", "hour", "value"]] for c, g in d.groupby("concept")}
    found = []
    for c, q in Q.groupby("concept"):
        m = q[["tgt", "j", "hour", "vq"]].merge(by_concept[c], on="hour")
        m = m[(m["value"] - m["vq"]).abs() <= 1e-6 + rel_tol * m["vq"].abs()]
        found.append(m[["tgt", "j", "stay"]].drop_duplicates())
    M = pd.concat(found, ignore_index=True)
    size_static = np.bincount(cell)[cell]
    out = []
    out.append({"known": "static fields only", "m": 0, "targets": len(tg), "unique": float((size_static[tg] == 1).mean()),
                "below_k": float((size_static[tg] < k).mean()), "median_candidates": float(np.median(size_static[tg])),
                "p10_candidates": float(np.percentile(size_static[tg], 10))})
    for m in ms:
        sub = M[M["j"] < m]
        c = sub.groupby(["tgt", "stay"]).size()
        ok = c[c == m].reset_index()[["tgt", "stay"]]
        ok["same_cell"] = cell[ok["stay"].to_numpy()] == cell[ok["tgt"].to_numpy()]
        for label, frame in (("series only", ok), ("series + static fields", ok[ok["same_cell"]])):
            n = frame.groupby("tgt").size().reindex(tg).fillna(0).to_numpy()
            out.append({"known": label, "m": m, "targets": len(tg), "unique": float((n <= 1).mean()), "below_k": float((n < k).mean()),
                        "median_candidates": float(np.median(n)), "p10_candidates": float(np.percentile(n, 10))})
    res = pd.DataFrame(out)
    res.attrs.update({"rel_tol": rel_tol, "k": k, "seed": seed, "stays": len(stays)})
    return res


# ---------------------------------------------------------------------------------------------------------------------------------------
# S3: linking two stays of one patient
# ---------------------------------------------------------------------------------------------------------------------------------------
def repeat_stay_linkage(out_root, name, static, min_coverage=0.3, tops=(1, 5)):
    """Can two stays of the same patient be matched? The level has no patient key at Tier 2, only a split group (patients are assigned to groups
    whole, so the stays of a patient share a group). For every stay that has a sibling (another stay of the same patient, known from the private
    key map and the static table), all other stays of its split group are ranked by distance to it, over the released quasi-identifiers
    (one-hot) and the per-stay mean of every concept present in at least `min_coverage` of the stays (standardised, missing as 0). hit@t is the
    share of stays with a sibling for which a sibling is among the t nearest. `chance` is what a random order would give. Nearest-neighbour
    only, so a lower bound on what a trained linker would do. Counts and shares only."""
    st = LR.load_static(out_root, name)
    stays = st["stay_key"].astype(str).to_numpy()
    site, pid = LR.labels(out_root, name, static, stays.tolist())
    d = _load_series(out_root, name, stays)
    mean = d.groupby(["stay", "concept"])["value"].mean().unstack("concept").reindex(range(len(stays)))
    mean = mean.loc[:, mean.notna().mean() >= min_coverage]
    Z = ((mean - mean.mean()) / mean.std(ddof=0).replace(0, np.nan)).fillna(0).to_numpy()
    qi = [c for c in _qi_cols(st)]
    S = pd.get_dummies(st[qi].astype("string").fillna("(missing)"), dtype=float).to_numpy()
    X = np.hstack([S, Z])
    grp = st["split_group"].astype(str).to_numpy() if "split_group" in st.columns else np.zeros(len(st), dtype=str)
    hits = {t: 0 for t in tops}
    chance = {t: 0.0 for t in tops}
    n_eval = 0
    for g in np.unique(grp):
        idx = np.flatnonzero(grp == g)
        if len(idx) < 3:
            continue
        P = pid[idx]
        Xg = X[idx]
        sq = (Xg ** 2).sum(1)
        D = sq[:, None] + sq[None, :] - 2 * Xg @ Xg.T
        np.fill_diagonal(D, np.inf)
        same = P[:, None] == P[None, :]
        np.fill_diagonal(same, False)
        n_sib = same.sum(1)
        for i in np.flatnonzero(n_sib > 0):
            n_eval += 1
            order = np.argsort(D[i], kind="stable")[: len(idx) - 1]
            for t in tops:
                hits[t] += int(same[i, order[:t]].any())
                N, s = len(idx) - 1, int(n_sib[i])
                chance[t] += 1.0 - (comb(N - s, t) / comb(N, t) if N - s >= t else 0.0)
    if not n_eval:
        return pd.DataFrame()
    rows = [{"test": f"nearest {t} in split group contains a stay of the same patient", "stays_with_sibling": n_eval,
             "hit": hits[t] / n_eval, "chance": chance[t] / n_eval} for t in tops]
    out = pd.DataFrame(rows)
    out["lift"] = out["hit"] / out["chance"]
    out.attrs["features"] = {"quasi_identifiers": qi, "concepts": list(mean.columns)}
    return out
