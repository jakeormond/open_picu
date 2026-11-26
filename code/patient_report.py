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
  Status (decision 2026-11-25, following Thoral et al.): the Table 2 adversaries (S1 knowledge, `adversary_risk`) are the acceptance test; S3 and
  S4 are reported; S2 is informational, because an adversary does not hold exact observations of a child (PRIVACY_THREAT_MODEL.md, section 1a).

Tests
  outcome_diversity(out_root, name)            S4: for each stay, the outcome of the stays that share its other quasi-identifiers (l-diversity)
  known_observation_attack(out_root, name)     S2 (and S1 as the m = 0 row): how many released stays fit m known observations
  repeat_stay_linkage(out_root, name, static)  S3: can the nearest stay in the same split group be a sibling stay of the same patient
  adversary_risk(out_root, name, static)       Table 2 of Thoral et al.: k, l, average and maximum risk and final risk per adversary
  risk_table(out_root, name, static)           the same, laid out like Table 2 of Thoral et al. (for the data descriptor)
  risk_by_level(out_root, names, static)       the same for several levels (for example k = 2, 5, 10);  suppression_cost(out_root, names)
  privacy_summary(out_root, name, static)      all tests in one table: gate (Table 2), reported (S3, S4), informational (S2)

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
def outcome_diversity(out_root, name, sensitive="died", exclude=()):
    """What the other quasi-identifiers say about the outcome. The cell of a stay is the set of stays that share all released quasi-identifiers
    except `sensitive` (age band, sex, weight band, diagnosis group, ethnicity and PIM band where released). A person who knows a target's
    demographics and that the stay is in the data learns the cell's outcome rate. Rows:
      stays; positive stays (for example the deaths) and the overall rate;
      cells; stays in cells where every stay has the same outcome (l-diversity of 1; the outcome is then certain, for the common outcome as well);
      positive stays in cells where every stay is positive (the outcome of these is certain);
      positive stays in cells with a positive rate of at least 50% and at least 90% (the guess is right more often than not);
      the median cell positive rate among positive stays, against the overall rate (how much the cell tells beyond the base rate).
    exclude: quasi-identifiers the attacker is not given (for example ("pim_band",) to see how much of the result the PIM band explains).
    Counts and shares only. A stay in a cell of one is counted as a cell of one (certain)."""
    st = LR.load_static(out_root, name)
    qi = [c for c in _qi_cols(st) if c != sensitive and c not in exclude]
    cell = _cell_ids(st, qi)
    y = pd.to_numeric(st[sensitive].astype(float), errors="coerce").fillna(0).to_numpy() > 0
    n = np.bincount(cell)[cell]
    pos = np.bincount(cell, weights=y.astype(float))[cell]
    rate = pos / n
    allsame = (pos == 0) | (pos == n)
    base = float(y.mean())
    rows = [("stays", len(st), None),
            (f"{sensitive} (stays)", int(y.sum()), base),
            ("cells", int(cell.max() + 1), None),
            ("stays in one-outcome cells", int(allsame.sum()), float(allsame.mean())),
            (f"{sensitive}: cell all {sensitive}", int((y & (rate == 1)).sum()),
             float((y & (rate == 1)).sum() / max(y.sum(), 1))),
            (f"{sensitive}: cell rate 50% or more", int((y & (rate >= .5)).sum()), float((y & (rate >= .5)).sum() / max(y.sum(), 1))),
            (f"{sensitive}: cell rate 90% or more", int((y & (rate >= .9)).sum()), float((y & (rate >= .9)).sum() / max(y.sum(), 1))),
            (f"{sensitive}: median cell rate", None, float(np.median(rate[y])) if y.any() else np.nan)]
    out = pd.DataFrame(rows, columns=["item", "n", "share_or_rate"])
    out.attrs["fields"] = qi
    out.attrs["smallest_cell"] = int(n.min())
    return out


def outcome_diversity_wildcard(out_root, name, static, sensitive="died", token="(suppressed)"):
    """`outcome_diversity` with the attacker reading the release correctly: a suppressed value matches any true value. The attacker knows a
    target's true coarse demographics (age band, sex, weight band, diagnosis group, ethnicity where released), not the outcome; the target's
    candidates are the released stays whose values equal the target's, or are `token`. The result is the outcome rate of those candidates,
    evaluated for every released stay as a target (its true values are rebuilt from the private key map and the static table with the level's
    own coarsening, before suppression). Rows as in `outcome_diversity`, plus the share of the positive stays whose candidate rate is above
    twice the overall rate. Counts and shares only; this is the S4 number to quote when a level uses suppression, since `outcome_diversity`
    treats the token as a value of its own, which overstates what a person with only demographics can see."""
    cfg = AN.config_from_level(out_root, name)
    st = LR.load_static(out_root, name)
    km = pd.read_parquet(Path(out_root) / "_private" / f"{name}_key_map.parquet")
    km["stay_key"] = km["stay_key"].astype(str)
    co = AN.cohort_static(static)
    co["stay_key"] = co["stay_key"].astype(str)
    co = co.merge(km[["site", "stay_key", "new_stay_key"]], on=["site", "stay_key"], how="inner")
    coarse = AN.R.coarsen(co, k=cfg.k, ethnicity=cfg.ethnicity, weight=True, los=False, n_groups=cfg.n_groups, seed=cfg.seed,
                          age_edges=list(cfg.age_edges), weight_edges=list(cfg.weight_edges))
    coarse["new_stay_key"] = co["new_stay_key"].to_numpy()
    qi = [c for c in _qi_cols(st) if c != sensitive]
    truth = st[["stay_key"]].astype(str).merge(coarse.drop(columns=["stay_key"]).rename(columns={"new_stay_key": "stay_key"}), on="stay_key", how="left")
    rel = np.column_stack([st[c].astype("string").fillna("(missing)").to_numpy(dtype=object) for c in qi])
    tru = np.column_stack([truth[c].astype("string").fillna("(missing)").to_numpy(dtype=object) for c in qi])
    y = pd.to_numeric(st[sensitive].astype(float), errors="coerce").fillna(0).to_numpy() > 0
    wild = rel == token
    key = pd.Series(list(map(tuple, tru)))
    codes, uniq = pd.factorize(key)
    n = np.zeros(len(st))
    pos = np.zeros(len(st))
    for i, u in enumerate(uniq):
        m = np.ones(len(st), dtype=bool)
        for j, v in enumerate(u):
            m &= (rel[:, j] == v) | wild[:, j]
        n_i, p_i = int(m.sum()), int(y[m].sum())
        sel = codes == i
        n[sel], pos[sel] = n_i, p_i
    rate = pos / np.maximum(n, 1)
    base_rate = float(y.mean())
    rows = [("stays", len(st), None), (f"{sensitive} (stays)", int(y.sum()), base_rate),
            (f"{sensitive}: candidates all {sensitive}", int((y & (rate == 1)).sum()), float((y & (rate == 1)).sum() / max(y.sum(), 1))),
            (f"{sensitive}: candidate rate 50% or more", int((y & (rate >= .5)).sum()), float((y & (rate >= .5)).sum() / max(y.sum(), 1))),
            (f"{sensitive}: candidate rate 90% or more", int((y & (rate >= .9)).sum()), float((y & (rate >= .9)).sum() / max(y.sum(), 1))),
            (f"{sensitive}: candidate rate over 2x overall", int((y & (rate > 2 * base_rate)).sum()), float((y & (rate > 2 * base_rate)).sum() / max(y.sum(), 1))),
            (f"{sensitive}: median candidate rate", None, float(np.median(rate[y])) if y.any() else np.nan),
            ("all stays: median candidates", float(np.median(n)), None), ("all stays: smallest candidate set", float(n.min()), None)]
    out = pd.DataFrame(rows, columns=["item", "n", "share_or_rate"])
    out.attrs["fields"] = qi
    return out


def outcome_cells(out_root, name, sensitive="died", min_rate=0.9, exclude=()):
    """The cells behind `outcome_diversity`: one row per combination of quasi-identifiers with at least one `sensitive` stay and a positive rate
    of at least `min_rate`, with the cell's definition (the released values), its number of stays, the number positive and the rate, largest
    number of positive stays first. These are the cells where the outcome is (nearly) certain to someone who knows the demographics. Cell
    definitions and counts only; check the output rules before this table leaves the SDE."""
    st = LR.load_static(out_root, name)
    qi = [c for c in _qi_cols(st) if c != sensitive and c not in exclude]
    cell = _cell_ids(st, qi)
    y = (pd.to_numeric(st[sensitive].astype(float), errors="coerce").fillna(0) > 0).to_numpy()
    t = st[qi].astype("string").fillna("(missing)").assign(_cell=cell, _y=y)
    g = t.groupby(qi, sort=False, dropna=False).agg(stays=("_y", "size"), positive=("_y", "sum")).reset_index()
    g["rate"] = (g["positive"] / g["stays"]).round(3)
    out = g[(g["positive"] > 0) & (g["rate"] >= min_rate)].sort_values(["positive", "stays"], ascending=False).reset_index(drop=True)
    out.attrs["positive_total"] = int(y.sum())
    out.attrs["positive_in_cells"] = int(out["positive"].sum())
    return out


def suppression_vs_outcome(out_root, name, sensitive="died", token="(suppressed)"):
    """Does a suppressed value tell the outcome? For every released quasi-identifier that contains `token`: the stays with it, how many of them
    are `sensitive` (for example died) and what share of all `sensitive` stays carry it. If most stays carrying the token are deaths, the token
    itself discloses the outcome (a small (..., died) cell is suppressed, and the deaths are the rarer value). Counts and shares only."""
    st = LR.load_static(out_root, name)
    y = pd.to_numeric(st[sensitive].astype(float), errors="coerce").fillna(0).to_numpy() > 0
    rows = []
    for c in _qi_cols(st):
        if c == sensitive:
            continue
        m = (st[c].astype("string") == token).fillna(False).to_numpy(dtype=bool)     # a missing value is not the token
        if m.any():
            rows.append({"field": c, "suppressed_stays": int(m.sum()), f"{sensitive}_among_suppressed": float(y[m].mean()),
                         f"{sensitive}_stays_suppressed": int((m & y).sum()), f"share_of_all_{sensitive}": float((m & y).sum() / max(y.sum(), 1)),
                         f"base_{sensitive}_rate": float(y.mean())})
    return pd.DataFrame(rows)


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
def repeat_stay_linkage(out_root, name, static, min_coverage=0.3, tops=(1, 5), use="both", scope="group", chunk=400):
    """Can two stays of the same patient be matched? The level has no patient key at Tier 2, only a split group (patients are assigned to groups
    whole, so the stays of a patient share a group). For every stay that has a sibling (another stay of the same patient, known from the private
    key map and the static table), all other stays of its split group are ranked by distance to it, over the released quasi-identifiers
    (one-hot) and the per-stay mean of every concept present in at least `min_coverage` of the stays (standardised, missing as 0). hit@t is the
    share of stays with a sibling for which a sibling is among the t nearest (column `nearest`). `chance` is what a random order would give. Nearest-neighbour
    only, so a lower bound on what a trained linker would do.
    use: "both" (quasi-identifiers and series means), "static" (quasi-identifiers only) or "series" (series means only): which of what the
    attacker can see drives the linking. scope: "group" (the attacker knows the split group, which the release states) or "all" (candidates
    are every released stay; how much the group itself gives away). Counts and shares only."""
    assert use in ("both", "static", "series") and scope in ("group", "all")
    st = LR.load_static(out_root, name)
    stays = st["stay_key"].astype(str).to_numpy()
    site, pid = LR.labels(out_root, name, static, stays.tolist())
    d = _load_series(out_root, name, stays)
    mean = d.groupby(["stay", "concept"])["value"].mean().unstack("concept").reindex(range(len(stays)))
    mean = mean.loc[:, mean.notna().mean() >= min_coverage]
    Z = ((mean - mean.mean()) / mean.std(ddof=0).replace(0, np.nan)).fillna(0).to_numpy()
    qi = [c for c in _qi_cols(st)]
    S = pd.get_dummies(st[qi].astype("string").fillna("(missing)"), dtype=float).to_numpy()
    X = {"both": np.hstack([S, Z]), "static": S, "series": Z}[use].astype("float32")
    grp = st["split_group"].astype(str).to_numpy() if (scope == "group" and "split_group" in st.columns) else np.zeros(len(st), dtype=str)
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
        for a in range(0, len(idx), chunk):
            rows_ = np.arange(a, min(a + chunk, len(idx)))
            D = sq[rows_, None] + sq[None, :] - 2 * Xg[rows_] @ Xg.T
            D[np.arange(len(rows_)), rows_] = np.inf
            same = P[rows_, None] == P[None, :]
            same[np.arange(len(rows_)), rows_] = False
            n_sib = same.sum(1)
            for r in np.flatnonzero(n_sib > 0):
                n_eval += 1
                order = np.argpartition(D[r], max(tops))[: max(tops)]
                order = order[np.argsort(D[r][order], kind="stable")]
                for t in tops:
                    hits[t] += int(same[r, order[:t]].any())
                    N, s_ = len(idx) - 1, int(n_sib[r])
                    chance[t] += 1.0 - (comb(N - s_, t) / comb(N, t) if N - s_ >= t else 0.0)
    if not n_eval:
        return pd.DataFrame()
    rows = [{"use": use, "scope": scope, "nearest": t, "stays_with_sibling": n_eval, "hit": hits[t] / n_eval, "chance": chance[t] / n_eval}
            for t in tops]
    out = pd.DataFrame(rows)
    out["lift"] = out["hit"] / out["chance"]
    out.attrs["features"] = {"quasi_identifiers": qi, "concepts": list(mean.columns)}
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------
# Risk by adversary, in the form of AmsterdamUMCdb's Table 2 (Thoral et al., Crit Care Med 2021;49:e563)
# ---------------------------------------------------------------------------------------------------------------------------------------
STANDARD_KNOWN = ("sex", "age_band", "weight_band", "died")
ADVERSARIES = {
    # name: (what the adversary knows, risk measure, P(access), P(attempt), sensitive attribute for l-diversity)
    # P(attempt) "acquaintance" is the chance of knowing someone in the data, 1 - (1 - rho)^150 (`acquaintance_risk`).
    "friendly researcher": (STANDARD_KNOWN, "average", 1.0, "acquaintance", "diagnosis_group"),
    "rogue researcher": (STANDARD_KNOWN, "maximum", 1.0, 0.10, "diagnosis_group"),
    "rogue insurer": (("sex", "age_band", "died"), "average", 0.27, 0.10, "diagnosis_group"),
    "informed acquaintance (extension)": (("sex", "age_band", "weight_band", "ethnicity", "diagnosis_group", "died"), "average", 1.0, "acquaintance", None),
}


def acquaintance_risk(n_patients, population, friends=150):
    """P(an adversary knows at least one patient in the data) = 1 - (1 - rho)^friends, rho = patients / population (Dunbar's 150 friends, as in
    Thoral et al.). `population` is the number of people the patients are drawn from: the default in `adversary_risk` is the UK population under 18 (14,403,544, UNICEF data portal, 2023)."""
    return float(1.0 - (1.0 - n_patients / population) ** friends)


def _released_and_truth(out_root, name, static):
    """The released static table of a level and, row for row, the true coarse values of each stay (rebuilt with the level's own coarsening,
    before suppression) from the private key map. Also the number of patients in the level. Used to score a wildcard attacker."""
    cfg = AN.config_from_level(out_root, name)
    st = LR.load_static(out_root, name)
    km = pd.read_parquet(Path(out_root) / "_private" / f"{name}_key_map.parquet")
    km["stay_key"] = km["stay_key"].astype(str)
    co = AN.cohort_static(static)
    co["stay_key"] = co["stay_key"].astype(str)
    co = co.merge(km[["site", "stay_key", "new_stay_key"]], on=["site", "stay_key"], how="inner")
    coarse = AN.R.coarsen(co, k=cfg.k, ethnicity=cfg.ethnicity, weight=True, los=False, n_groups=cfg.n_groups, seed=cfg.seed,
                          age_edges=list(cfg.age_edges), weight_edges=list(cfg.weight_edges))
    coarse["new_stay_key"] = co["new_stay_key"].to_numpy()
    truth = st[["stay_key"]].astype(str).merge(coarse.drop(columns=["stay_key"]).rename(columns={"new_stay_key": "stay_key"}), on="stay_key", how="left")
    n_pat = int(co.drop_duplicates(["site", "patient_id"]).shape[0]) if "patient_id" in co.columns else len(co)
    pid = LR.labels(out_root, name, static, st["stay_key"].astype(str).tolist())[1]
    return cfg, st, truth, n_pat, pid


def _candidates(st, truth, known, sensitive=None, token="(suppressed)", pid=None):
    """For every released stay taken as the target: how many released stays the attacker cannot tell from it (candidates), how many different
    values of `sensitive` those candidates show (suppressed values are not counted; 0 if all are suppressed), and how many candidates have the
    value suppressed. The attacker knows the target's true values of `known`; a released value equal to the true one or equal to `token`
    (suppressed, so it could be anything) keeps a stay a candidate. `pid`: a patient identifier per stay; the number of different patients among the
    candidates is also returned. Returns (candidate stays, distinct values, suppressed candidates, candidate patients, columns)."""
    cols = [c for c in known if c in st.columns]
    n = len(st)
    rel = {c: st[c].astype("string").fillna("(missing)").to_numpy(dtype=object) for c in cols}
    tru = {c: truth[c].astype("string").fillna("(missing)").to_numpy(dtype=object) for c in cols}
    wild = {c: rel[c] == token for c in cols}
    codes, uniq = pd.factorize(pd.Series(list(zip(*[tru[c] for c in cols]))))
    cand = np.zeros(n)
    pat = np.zeros(n)
    pcode = pd.factorize(pd.Series(pid))[0] if pid is not None else None
    lval = np.full(n, np.nan)
    nsup = np.full(n, np.nan)
    has_s = bool(sensitive and sensitive in st.columns)
    if has_s:
        sv = st[sensitive].astype("string").fillna("(missing)").to_numpy(dtype=object)
        sc, _ = pd.factorize(pd.Series(sv))
        sw = sv == token
    for i, u in enumerate(uniq):
        m = np.ones(n, dtype=bool)
        for j, c in enumerate(cols):
            m &= (rel[c] == u[j]) | wild[c]
        sel = codes == i
        cand[sel] = int(m.sum())
        pat[sel] = len(np.unique(pcode[m])) if pcode is not None else int(m.sum())
        if has_s:
            lval[sel] = len(np.unique(sc[m & ~sw]))
            nsup[sel] = int((m & sw).sum())
    return cand, lval, nsup, pat, cols


def adversary_risk(out_root, name, static, adversaries=None, population=14_403_544, threshold=0.05, token="(suppressed)", unit="patients"):
    """AmsterdamUMCdb's Table 2 for one level: for each adversary, what they are assumed to know, k-anonymity, l-diversity, average and
    maximum re-identification risk, and the final risk = P(access) x P(attempt) x P(re-identification), the average risk or the maximum risk
    as the adversary's type says. Every released stay is a target; its candidates are the released stays that match the true values the
    adversary knows, with a suppressed value matching anything (the NULL rule of Ciglic et al.). Rows:
      k_min, k_median       candidates of the least and the typical target (k-anonymity), counted in `unit`: "patients" (default; two stays of one
                            child count once, as the child is found if both fit) or "stays"; k_min_stays is always the count in stays, and
                            share_below_10 the share of targets with fewer than 10 candidates in that unit;
      l_min, l_median       different values of the sensitive attribute (diagnosis group) among the candidates, suppressed values not counted
                            (l-diversity). l_min is the smallest over the targets with at least one known value; targets whose candidates are all
                            suppressed learn nothing and are counted in l_unknown instead;
      l1_certain            share of stays whose candidates all show one diagnosis group and none is suppressed: the diagnosis is known;
      l1_some_suppressed    share whose candidates show one group and some are suppressed: the diagnosis is very likely that group;
      l_unknown             share whose candidates are all suppressed: nothing is learned (this, not disclosure, is what the floor at 1 hides);
      avg_risk, max_risk    mean of 1/candidates over targets, and 1/k_min;
      p_access, p_attempt   the assumptions (see ADVERSARIES; `acquaintance` = `acquaintance_risk(patients, population)`);
      final_risk, ok        the product, and whether it is at most `threshold` (0.05 in the paper's range of 0.05 to 0.10).
    Not in the release, so not used: height, admission date and number of ICU admissions (the paper's rogue insurer knows the last; repeat
    stays are tested as S3, `repeat_stay_linkage`). `population`: the people the patients are drawn from; the default is the UK population under 18 (14,403,544; UNICEF data portal, 2023), so
    cross-check it against the ONS mid-year estimates before quoting the friendly researcher's number. Counts, shares and probabilities only."""
    assert unit in ("patients", "stays")
    cfg, st, truth, n_pat, pid = _released_and_truth(out_root, name, static)
    acq = acquaintance_risk(n_pat, population)
    rows = []
    for adv, (known, kind, p_access, p_attempt, sens) in (adversaries or ADVERSARIES).items():
        cand_stays, lval, nsup, pat, cols = _candidates(st, truth, known, sens, token, pid)
        cand = pat if unit == "patients" else cand_stays
        pa = acq if p_attempt == "acquaintance" else float(p_attempt)
        avg, mx = float(np.mean(1.0 / cand)), float(1.0 / cand.min())
        p_re = avg if kind == "average" else mx
        final = p_access * pa * p_re
        rows.append({"adversary": adv, "knows": ", ".join(cols), "risk_type": kind, "k_min": int(cand.min()), "k_median": float(np.median(cand)), "k_min_stays": int(cand_stays.min()),
                     "share_below_10": float((cand < 10).mean()),
                     "l_min": (float(np.nanmin(lval[lval >= 1])) if (lval >= 1).any() else np.nan) if sens else np.nan, "l_median": float(np.nanmedian(lval)) if sens else np.nan,
                     "l1_certain": float(((lval == 1) & (nsup == 0)).mean()) if sens else np.nan,
                     "l1_some_suppressed": float(((lval == 1) & (nsup > 0)).mean()) if sens else np.nan,
                     "l_unknown": float((lval == 0).mean()) if sens else np.nan,
                     "avg_risk": avg, "max_risk": mx, "p_access": p_access, "p_attempt": pa, "final_risk": final, "ok": bool(final <= threshold)})
    out = pd.DataFrame(rows)
    out.attrs.update(level=name, k=cfg.k, stays=len(st), patients=n_pat, population=population, threshold=threshold, unit=unit)
    return out


_KNOWN_LABELS = {"sex": "Gender", "age_band": "Age", "weight_band": "Weight", "died": "Survival at discharge",
                 "ethnicity": "Ethnicity (extension)", "diagnosis_group": "Diagnosis group (extension)"}


def risk_table(out_root, name, static, **kw):
    """`adversary_risk` laid out like Table 2 of Thoral et al.: one column per adversary; rows for what the adversary is assumed to know, P(access),
    P(intention) (our P(attempt)), the average risk (P(re-identification), k-anonymity and l-diversity, medians over the stays), the maximum risk (the
    same, with the smallest k and l) and the final risk (the average or the maximum risk, as each adversary's type says). Height, admission date and
    number of ICU admissions are the paper's assumed knowledge that our release does not contain. `kw` goes to `adversary_risk` (population, threshold,
    unit, adversaries). The friendly researcher's P(intention) depends on `population`: quote it only with a sourced figure."""
    t = adversary_risk(out_root, name, static, **kw)
    rows = []

    def add(section, item, vals):
        rows.append({"section": section, "item": item, **dict(zip(t["adversary"], vals))})

    knows = [set(k.split(", ")) for k in t["knows"]]
    for col, lab in _KNOWN_LABELS.items():
        if any(col in k for k in knows):
            add("Assumed background knowledge", lab, ["X" if col in k else "" for k in knows])
    for lab in ("Height", "Admission date", "Number of ICU admissions"):
        add("Assumed background knowledge", lab, ["not in release"] * len(t))
    add("Assessment of reidentification risk", "P(access)", list(t["p_access"]))
    add("Assessment of reidentification risk", "P(intention)", list(t["p_attempt"]))
    add("Average risk", "P(reidentification)", list(t["avg_risk"]))
    add("Average risk", "k-anonymity (median)", list(t["k_median"]))
    add("Average risk", "l-diversity (median)", list(t["l_median"]))
    add("Maximum risk", "P(reidentification)", list(t["max_risk"]))
    add("Maximum risk", "k-anonymity (smallest)", list(t["k_min"]))
    add("Maximum risk", "l-diversity (smallest)", list(t["l_min"]))
    add("Maximum risk", "(ours) share of stays with every candidate diagnosis suppressed", list(t["l_unknown"]))
    add("P final risk", "risk type used", list(t["risk_type"]))
    add("P final risk", "P final risk", list(t["final_risk"]))
    out = pd.DataFrame(rows)
    out.attrs.update(t.attrs)
    return out


def risk_by_level(out_root, names, static, **kw):
    """`adversary_risk` for several levels (for example the same level built at k = 2, 5 and 10), one table, with the level and its k."""
    frames = []
    for nm in names:
        t = adversary_risk(out_root, nm, static, **kw)
        t.insert(0, "k", t.attrs["k"])
        t.insert(0, "level", nm)
        frames.append(t)
    return pd.concat(frames, ignore_index=True)


def suppression_cost(out_root, names, token="(suppressed)"):
    """What each level costs in data: stays released, stays deleted below k, and the share of released stays with each quasi-identifier
    suppressed (and the share with any). Read from the released static table and the level's steps file. Counts and shares only."""
    rows = []
    for nm in names:
        st = LR.load_static(out_root, nm)
        cfg = AN.config_from_level(out_root, nm)
        steps = pd.read_csv(LR._level_dir(out_root, nm) / "steps.csv")
        d = steps[(steps["step"] == "static: stays deleted below k") & (steps["item"] == "stays")]["n"]
        deleted = int(d.iloc[0]) if len(d) else 0
        row = {"level": nm, "k": cfg.k, "stays": len(st), "deleted_below_k": deleted, "deleted_share": deleted / max(len(st) + deleted, 1)}
        anyc = pd.Series(False, index=st.index)
        for c in ("weight_band", "ethnicity", "diagnosis_group", "sex"):
            if c in st.columns:
                m = (st[c].astype("string") == token) | st[c].isna() if c == "sex" else (st[c].astype("string") == token)
                row[f"{c}_suppressed"] = float(m.mean())
                anyc |= m.fillna(False)
        row["any_suppressed"] = float(anyc.mean())
        rows.append(row)
    return pd.DataFrame(rows)


def privacy_summary(out_root, name, static, n_targets=300, population=14_403_544, threshold=0.05, p_attempt_link=0.10):
    """One table for a level: every test in the form of the Thoral et al. final-risk table. Columns: test, adversary, measure, value, p_access,
    p_attempt, final_risk, role, status. `role` is what the test is for:
      gate           Table 2 rows (`adversary_risk`): final risk against `threshold`; status pass or fail;
      reported       S3 and S4: the measure is shown with its own risk where one can be formed, no pass or fail yet (S3 final risk = P(attempt) x
                     share of stays whose nearest neighbour in the split group is a sibling, access 1: the data user holds the files);
      informational  S2: how many stays three exact observations single out. Not an acceptance test (PRIVACY_THREAT_MODEL.md, section 1a: an
                     adversary does not hold exact observations of a child; the argument rests on the data-use agreement).
    Counts, shares and probabilities only."""
    rows = []
    t2 = adversary_risk(out_root, name, static, population=population, threshold=threshold)
    for r in t2.itertuples():
        rows.append({"test": "Table 2 (S1)", "adversary": r.adversary, "measure": f"final risk ({r.risk_type}; k_min {r.k_min})", "value": r.final_risk,
                     "p_access": r.p_access, "p_attempt": r.p_attempt, "final_risk": r.final_risk, "role": "gate", "status": "pass" if r.ok else "fail"})
    lk = repeat_stay_linkage(out_root, name, static)
    if len(lk):
        a = lk[lk["nearest"] == 1].iloc[0]
        rows.append({"test": "S3 repeat-stay linkage", "adversary": "data user with two stays", "measure": f"siblings found at nearest 1 (chance {a['chance']:.3f})",
                     "value": float(a["hit"]), "p_access": 1.0, "p_attempt": p_attempt_link, "final_risk": float(p_attempt_link * a["hit"]), "role": "reported", "status": "-"})
    w = outcome_diversity_wildcard(out_root, name, static).set_index("item")
    for item, label in (("died: candidate rate 90% or more", "deaths whose candidates are 90% or more deaths"),
                        ("died: candidate rate over 2x overall", "deaths whose candidates' death rate is over 2x the overall rate")):
        rows.append({"test": "S4 outcome from demographics", "adversary": "data user with demographics", "measure": label, "value": float(w.loc[item, "share_or_rate"]),
                     "p_access": np.nan, "p_attempt": np.nan, "final_risk": np.nan, "role": "reported", "status": "-"})
    ka = known_observation_attack(out_root, name, ms=(3,), n_targets=n_targets)
    if len(ka):
        a = ka[(ka["known"] == "series only") & (ka["m"] == 3)].iloc[0]
        rows.append({"test": "S2 known observations", "adversary": "someone holding 3 exact observations", "measure": "stays singled out by 3 observations", "value": float(a["unique"]),
                     "p_access": np.nan, "p_attempt": np.nan, "final_risk": np.nan, "role": "informational", "status": "-"})
    out = pd.DataFrame(rows)
    out.attrs.update(level=name, threshold=threshold)
    return out