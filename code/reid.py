# ======================================================================================
# Re-identification review (pipeline step 9). Counts only: how many stays are unique or in small cells on combinations of the static
# fields, how many patients have repeat stays, and which category values occur at one site only. Nothing here changes data.
# Bands are the candidate Tier 2 coarsening (anonymisation_design.md, section 4); change them here and rerun to see the effect.
# ======================================================================================
import numpy as np
import pandas as pd

AGE_EDGES = [0, 1, 3, 12] + list(range(24, 217, 12)) + [np.inf]          # months: <1, 1-3, 3-12, then yearly to 18 years
WEIGHT_EDGES = [0, 3, 5, 8, 10, 15, 20, 30, 40, 60, np.inf]              # kg
LOS_EDGES = [0, 12, 24, 48, 72, 120, 240, 500, np.inf]                    # hours
COMBOS = {
    "age+sex": ["age_band", "sex"],
    "+ethnicity": ["age_band", "sex", "ethnicity"],
    "+diagnosis": ["age_band", "sex", "diagnosis_group"],
    "+weight": ["age_band", "sex", "weight_band"],
    "+outcome": ["age_band", "sex", "diagnosis_group", "died"],
    "+year": ["age_band", "sex", "diagnosis_group", "year"],
    "all": ["age_band", "sex", "ethnicity", "diagnosis_group", "weight_band", "died", "year"],
}


def add_bands(static, age_edges=AGE_EDGES, weight_edges=WEIGHT_EDGES, los_edges=LOS_EDGES):
    """Copy of the static table with age_band, weight_band and los_band added (strings; missing stays missing)."""
    s = static.copy()
    for col, edges, new in (("age_months", age_edges, "age_band"), ("weight_kg", weight_edges, "weight_band"), ("los_hours", los_edges, "los_band")):
        if col in s.columns:
            s[new] = pd.cut(pd.to_numeric(s[col], errors="coerce"), edges, right=False).astype("string")
    return s


def uniqueness(static, combos=COMBOS, k=10, by_site=True, pooled=True):
    """For each combination of fields and each site (and pooled): stays, distinct cells, stays that are the only one in their cell, stays in
    cells smaller than k, the share of stays in such cells, and the smallest cell. Missing values count as their own category. Counts only."""
    s = add_bands(static)
    groups = ([(site, g) for site, g in s.groupby("site")] if by_site else []) + ([("pooled", s)] if pooled else [])
    rows = []
    for name, cols in combos.items():
        cols = [c for c in cols if c in s.columns]
        for label, g in groups:
            size = g.groupby([g[c].astype("string").fillna("(missing)") for c in cols])["stay_key"].transform("size")
            rows.append({"combination": name, "site": label, "stays": len(g), "cells": int(g.groupby([g[c].astype("string").fillna("(missing)") for c in cols]).ngroups),
                         "unique_stays": int((size == 1).sum()), f"stays_in_cells_below_{k}": int((size < k).sum()),
                         "share_below_k": round(float((size < k).mean()), 4), "smallest_cell": int(size.min())})
    return pd.DataFrame(rows)


def repeat_patients(static):
    """Stays per patient by site: patients, patients with 2 or more stays, the share of stays that belong to a repeat patient, and the largest
    number of stays. Bears on whether a patient key can be released (stays of one patient stay linked)."""
    rows = []
    for site, g in static.groupby("site"):
        n = g.groupby("patient_id")["stay_key"].nunique()
        rows.append({"site": site, "patients": len(n), "patients_2plus_stays": int((n >= 2).sum()),
                     "share_stays_of_repeat_patients": round(float(n[n >= 2].sum() / n.sum()), 4), "max_stays": int(n.max())})
    return pd.DataFrame(rows)


def rare_categories(static, cols=("ethnicity", "diagnosis_group", "sex"), k=10):
    """Category values of each column seen in fewer than k stays at a site: how many values, and how many stays they cover. The values themselves
    are listed only when they cover at least k stays pooled (so a rare label is never printed)."""
    rows = []
    for c in cols:
        if c not in static.columns:
            continue
        for site, g in static.groupby("site"):
            vc = g[c].astype("string").fillna("(missing)").value_counts()
            small = vc[vc < k]
            rows.append({"column": c, "site": site, "categories": len(vc), f"categories_below_{k}": len(small), "stays_in_them": int(small.sum())})
    return pd.DataFrame(rows)


def site_only_values(static, cols=("ethnicity", "diagnosis_group", "sex", "pim_version", "died"), min_stays=10):
    """Category values seen at one site only (a fingerprint: the value tells you the site). Per column: values at one site only and the stays
    they cover. Values shown only when covering at least min_stays stays."""
    rows = []
    sites = static["site"].nunique()
    for c in cols:
        if c not in static.columns:
            continue
        t = static.assign(v=static[c].astype("string").fillna("(missing)")).groupby("v")["site"].agg(["nunique", "size"])
        one = t[t["nunique"] == 1]
        rows.append({"column": c, "values_one_site_only": len(one), "stays_in_them": int(one["size"].sum()),
                     "shown": ", ".join(one[one["size"] >= min_stays].index.astype(str)[:10])})
    return pd.DataFrame(rows)


def feature_availability_uniqueness(avail, k=10):
    """Wrapper for concepts.pattern_uniqueness on the availability table (stays whose set of recorded concepts is unique). Kept here so the
    whole review runs from one notebook."""
    import concepts as C
    return C.pattern_uniqueness(avail, min_count=k)


# ---------------------------------------------------------------------------------------------------------------------------------
# Candidate Tier 2 coarsening (a preview on a copy; nothing is written). Decisions of 2026-11-19 (Jake): no year and no era; a coarse
# split_group replaces the patient key; pim_version dropped; diagnosis groups below k merged; sex values below k set to missing.
# ---------------------------------------------------------------------------------------------------------------------------------
NOT_RECORDED = ("not stated", "unknown", "(missing)", "")


def ethnicity_group(label):
    """Broad group of a recorded ethnicity label (PICANet style labels). Missing, 'Not stated' and 'Unknown' become 'Not recorded'."""
    if label is None or pd.isna(label):
        return "Not recorded"
    t = str(label).strip().lower()
    if t in NOT_RECORDED:
        return "Not recorded"
    for key, grp in (("white and", "Mixed"), ("mixed", "Mixed"), ("white", "White"), ("asian", "Asian"), ("chinese", "Asian"),
                     ("black", "Black"), ("arab", "Other"), ("other", "Other")):
        if key in t:
            return grp
    return "Other"


def coarsen(static, k=10, ethnicity="group", weight=True, los=False, n_groups=10, seed=0, merge_dx=False, age_edges=AGE_EDGES, weight_edges=WEIGHT_EDGES, los_edges=LOS_EDGES):
    """Copy of the static table with the candidate Tier 2 coarsening, for the uniqueness check. Columns kept: site, stay_key, age_band,
    sex, ethnicity, diagnosis_group, died, split_group, weight_band (weight=True) and los_band (los=True; off by default: length of stay is
    not a Tier 2 static field). Dropped: patient_id, year, t0, pim, pim_version, exact age,
    weight and length of stay.
    - ethnicity='group': six broad groups (White, Asian, Black, Mixed, Other, Not recorded); 'detail': the recorded label, with labels seen in
      fewer than k stays at a site merged into '<group> (merged)'.
    - diagnosis_group: kept as recorded (PICANet groups). Rare groups are handled by `suppress_to_k` at the level of the combination, not here;
      merge_dx=True merges groups seen in fewer than k stays at a site into 'Other (merged)'.
    - sex: values other than Male and Female, or seen in fewer than k stays at the site, become missing.
    - split_group: each patient is assigned at random (per site, fixed seed) to one of n_groups groups; use it for patient-level splits."""
    s = add_bands(static, age_edges, weight_edges, los_edges)
    out = pd.DataFrame({"site": s["site"], "stay_key": s["stay_key"], "age_band": s["age_band"]})
    if los:
        out["los_band"] = s["los_band"]
    if weight:
        out["weight_band"] = s["weight_band"]
    sex = s["sex"].astype("string")
    cnt = sex.groupby([s["site"], sex]).transform("size")
    out["sex"] = sex.where(sex.isin(["Male", "Female"]) & (cnt >= k))
    eth = s["ethnicity"].map(ethnicity_group).astype("string") if ethnicity == "group" else s["ethnicity"].astype("string")
    if ethnicity == "detail":
        n = eth.groupby([s["site"], eth]).transform("size")
        eth = eth.where(n >= k, s["ethnicity"].map(ethnicity_group).astype("string") + " (merged)")
    out["ethnicity"] = eth.fillna("Not recorded")
    dx = s["diagnosis_group"].astype("string")
    if merge_dx:
        n = dx.groupby([s["site"], dx]).transform("size")
        dx = dx.where(n >= k, "Other (merged)")
    out["diagnosis_group"] = dx
    out["died"] = s["died"]
    rng = np.random.default_rng(seed)
    sg = pd.Series(index=s.index, dtype="Int64")
    for site, g in s.groupby("site"):
        pats = g["patient_id"].astype(str).unique()
        m = dict(zip(pats, rng.integers(0, n_groups, len(pats))))
        sg[g.index] = g["patient_id"].astype(str).map(m).to_numpy()
    out["split_group"] = sg
    return out


T2_COMBOS = {
    "t2 age+sex": ["age_band", "sex"],
    "t2 +ethnicity": ["age_band", "sex", "ethnicity"],
    "t2 +diagnosis": ["age_band", "sex", "ethnicity", "diagnosis_group"],
    "t2 +outcome": ["age_band", "sex", "ethnicity", "diagnosis_group", "died"],
    "t2 +weight": ["age_band", "sex", "ethnicity", "diagnosis_group", "died", "weight_band"],
}
T2_COMBOS_WITH_LOS = {**T2_COMBOS, "t2 +LOS (not released)": ["age_band", "sex", "ethnicity", "diagnosis_group", "died", "weight_band", "los_band"]}


def split_group_sizes(coarse):
    """Stays and groups per site: the number of stays in the smallest and largest split group. Counts only."""
    g = coarse.groupby(["site", "split_group"]).size()
    return g.groupby("site").agg(groups="size", smallest="min", largest="max").reset_index()


# Alternative, coarser bands to compare against the defaults.
AGE_COARSE = [0, 1, 3, 12, 24, 60, 120, 192, np.inf]      # <1m, 1-3m, 3-12m, 1-2y, 2-5y, 5-10y, 10-16y, 16y+
WEIGHT_COARSE = [0, 5, 10, 20, 40, np.inf]
LOS_COARSE = [0, 24, 72, 240, np.inf]


def cell_size(frame, cols, by_site=False, unit=None):
    """Size of the cell of each row: stays that share the values of `cols` (and the site if by_site), or, if `unit` names a column (a patient
    identifier), the number of different units (patients) in the cell. Missing counts as a value."""
    keys = ([frame["site"]] if by_site else []) + [frame[c].astype("string").fillna("(missing)") for c in cols]
    g = frame.groupby(keys)
    return g[unit].transform("nunique") if unit else g["stay_key"].transform("size")


def suppress_to_k(coarse, key_cols, order, k=10, token="(suppressed)", by_site=True, spread=(), unit=None):
    """Local suppression: stays are all kept; for stays whose combination of `key_cols` is shared by fewer than k stays at their site, one
    field at a time (in `order`, least valuable first) is replaced by `token`, recomputing the cells after each field, until no stay is in a
    cell below k or the fields are used up. by_site=True counts cells within each site (the site is a visible column); by_site=False counts
    them across all sites (the site column is not released). Returns (frame, report): per field the number of values suppressed, and at the end the stays
    still in cells below k. Counts only. A field in `order` that is not in `key_cols` is still suppressed when it is listed.
    unit: None counts stays in a cell; the name of a patient-identifier column counts the different patients, so two stays of one child do not make a cell of two.
    spread: key columns that do not decide *which* stays are suppressed (for example ("died",)). A stay is suppressed when any stay that shares
    its other key columns is in a small cell, so the suppressed token is not carried only by the rarer value of the spread column. Without it,
    the stays suppressed for being in a small (..., died) cell are nearly all deaths, and "(suppressed)" then tells the outcome."""
    out = coarse.copy()
    rows = []
    for f in order:
        cols = [c for c in key_cols if c in out.columns]
        size = cell_size(out, cols, by_site, unit)
        small = size < k
        if spread and small.any():
            rest = [c for c in cols if c not in spread]
            grp = ([out["site"]] if by_site else []) + [out[c].astype("string").fillna("(missing)") for c in rest]
            small = small.groupby(grp).transform("any") if grp else pd.Series(True, index=out.index)
        if f in out.columns and small.any():
            out[f] = out[f].astype("string").mask(small, token)
        rows.append({"field": f, "values_suppressed": int(small.sum()) if f in out.columns else 0})
    cols = [c for c in key_cols if c in out.columns]
    size = cell_size(out, cols, by_site, unit)
    rows.append({"field": "(stays still below k)", "values_suppressed": int((size < k).sum())})
    return out, pd.DataFrame(rows)


# What the adversaries of the risk table (patient_report.ADVERSARIES) know; the l-diversity rule below protects against each of them.
L_KNOWN_SETS = (("sex", "age_band", "weight_band", "died"), ("sex", "age_band", "died"))


def _l_candidates(released, truth, known, sensitive, token):
    """For every stay taken as the target (true values of `known` from `truth`): the stays it cannot be told from in the release (a suppressed
    value matches anything), as a list of (rows of the targets, boolean mask of the candidates) per distinct true combination, and the number
    of different known values of `sensitive` among the candidates."""
    cols = [c for c in known if c in released.columns]
    n = len(released)
    rel = {c: released[c].astype("string").fillna("(missing)").to_numpy(dtype=object) for c in cols}
    tru = {c: truth[c].astype("string").fillna("(missing)").to_numpy(dtype=object) for c in cols}
    codes, uniq = pd.factorize(pd.Series(list(zip(*[tru[c] for c in cols]))))
    sv = released[sensitive].astype("string").fillna("(missing)").to_numpy(dtype=object)
    sc, _ = pd.factorize(pd.Series(sv))
    sw = sv == token
    for i, u in enumerate(uniq):
        m = np.ones(n, dtype=bool)
        for j, c in enumerate(cols):
            m &= (rel[c] == u[j]) | (rel[c] == token)
        yield np.flatnonzero(codes == i), m, len(np.unique(sc[m & ~sw]))


def enforce_l_diversity(released, truth, known_sets=L_KNOWN_SETS, sensitive="diagnosis_group", token="(suppressed)", max_iter=10):
    """l-diversity of at least 2 for `sensitive` (the minimum of AmsterdamUMCdb). For each adversary in `known_sets`, every stay is a target
    and its candidates are the released stays that fit what the adversary knows (a suppressed value fits anything). If the candidates show
    exactly one known value of `sensitive` (the value is certain, or very likely when some candidates are suppressed), the sensitive field
    is suppressed for all the candidates, so the adversary learns nothing about it. Repeated until no target is left with one value, as
    suppressing changes other targets' candidates. `truth` has the true values of the known columns, one row per stay_key (before suppression).
    Returns (frame, report): report rows are the stays suppressed, the rounds used and the targets still with one value (0 when done)."""
    out = released.copy()
    tr = out[["stay_key"]].merge(truth.drop_duplicates("stay_key"), on="stay_key", how="left")
    total, rounds, left = 0, 0, 0
    for _ in range(max_iter + 1):
        bad = np.zeros(len(out), dtype=bool)
        n_bad = 0
        for known in known_sets:
            for rows, m, l in _l_candidates(out, tr, known, sensitive, token):
                if l == 1:
                    bad |= m
                    n_bad += len(rows)
        left = n_bad
        new = bad & (out[sensitive].astype("string") != token).fillna(True).to_numpy()
        if not n_bad or _ == max_iter:
            break
        out.loc[bad, sensitive] = token
        total += int(new.sum())
        rounds += 1
    return out, pd.DataFrame([{"item": f"{sensitive} suppressed for l >= 2", "n": total}, {"item": "rounds", "n": rounds},
                              {"item": "targets still with one known value", "n": left}])


# ---------------------------------------------------------------------------------------------------------------------------------
# Tables of what is merged, and figures for presenting the review. Figures show shares and counts that are already aggregates; the tail of
# the repeat-patient plot is capped at 5+ so no rare count is shown. Check every figure with the output checker before it leaves the SDE.
# ---------------------------------------------------------------------------------------------------------------------------------
INK, INK2, GRID, BASE, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7", "#fcfcfb"
SITE_COLOUR = {"GOSH": "#2a78d6", "RBH": "#eb6834", "SMH": "#1baf7a", "pooled": "#0b0b0b"}   # validated categorical slots 1 to 3, pooled in ink
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6", "#898781"]


def _ax(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(BASE)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    return ax


def _save(fig, path):
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=200, facecolor=SURFACE)
    return fig


def group_table(static, col="ethnicity", mapper=ethnicity_group, k=10):
    """Recorded labels, the group each is mapped to, and stays per site (counts under k shown as '<k'). One row per label."""
    t = pd.crosstab(static[col].astype("string").fillna("(missing)"), static["site"])
    t.insert(0, "group", [mapper(None if v == "(missing)" else v) for v in t.index])
    show = t.copy()
    for c in t.columns[1:]:
        show[c] = t[c].map(lambda v: "-" if v == 0 else (f"<{k}" if v < k else str(v)))
    return show.sort_values("group", kind="stable")


def merge_table(static, col="diagnosis_group", k=10):
    """Category values with stays per site (under k shown as '<k') and the sites at which the value would be merged into 'Other (merged)'."""
    t = pd.crosstab(static[col].astype("string").fillna("(missing)"), static["site"])
    out = t.copy()
    for c in t.columns:
        out[c] = t[c].map(lambda v: "-" if v == 0 else (f"<{k}" if v < k else str(v)))
    out["merged_at"] = [", ".join(c for c in t.columns if 0 < t.loc[i, c] < k) for i in t.index]
    return out.assign(_n=t.sum(axis=1)).sort_values("_n", ascending=False).drop(columns="_n")


def plot_buildup(variants, k=10, order=None, path=None, absolute=False):
    """Share of stays in cells smaller than k as fields are added one by one: one panel per site and pooled, one line per variant (a dict of
    name -> `uniqueness` frame). Shows which field makes the data identifiable and how much coarsening helps. absolute=True plots the number of
    stays in such cells instead of the share (log scale)."""
    import matplotlib.pyplot as plt
    order = order or list(next(iter(variants.values()))["combination"].unique())
    sites = ["GOSH", "RBH", "SMH", "pooled"]
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.8), sharey=True)
    styles = [("-", "o"), ("--", "s"), (":", "^")]
    for ax, site in zip(axes, sites):
        _ax(ax)
        for (name, df), (ls, mk) in zip(variants.items(), styles):
            d = df[df["site"] == site].set_index("combination").reindex(order)
            y = d[f"stays_in_cells_below_{k}"] if absolute else d["share_below_k"] * 100
            ax.plot(range(len(order)), y, ls, marker=mk, ms=7, lw=2, color=SITE_COLOUR[site], mfc=SURFACE, mew=2, label=name)
        ax.set_title(site, color=INK, fontsize=11, loc="left")
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels([o.replace("t2 ", "") for o in order], rotation=40, ha="right")
    if absolute:
        axes[0].set_yscale("log")
    axes[0].set_ylabel(f"stays in cells smaller than {k}" + (" (number, log scale)" if absolute else " (%)"), color=INK2)
    axes[0].legend(frameon=False, fontsize=8, labelcolor=INK2)
    fig.suptitle("Identifiability as static fields are added", color=INK, x=0.01, ha="left", fontsize=12)
    return _save(fig, path)


def plot_suppression(rep, n_stays, path=None, title=None):
    """How many stays are still in a cell smaller than k at each stage of local suppression: before any suppression, then after each field in
    turn has been blanked (from `suppress_to_k`'s report). The stays that lose a field are the ones counted at the stage before it, so the
    first bar is also the number of stays that lose the first field."""
    import matplotlib.pyplot as plt
    fields = list(rep["field"].iloc[:-1])
    vals = list(rep["values_suppressed"])
    labels = ["Before any suppression"] + [f"After blanking {f.replace('_', ' ')}" for f in fields]
    share = [v / n_stays * 100 for v in vals]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    _ax(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.barh(labels, share, color=CAT[0], height=0.55)
    for y, (v, sh) in enumerate(zip(vals, share)):
        ax.text(sh + 0.6, y, f"{v:,} stays ({sh:.1f}%)", va="center", color=INK2, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, max(share) * 1.35)
    ax.set_xlabel("stays in a cell smaller than 10 (%)", color=INK2)
    ax.set_title(title or "Local suppression: rare stays remaining after each field is blanked", color=INK, loc="left", fontsize=11)
    fig.text(0.01, 0.01, "Each field is blanked for the stays still in a small cell before that step.", color=INK2, fontsize=8)
    return _save(fig, path)


def plot_repeat(static, cap=5, path=None):
    """Stays per patient by site as a share of patients; 5 or more are pooled so no rare count is shown."""
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 3.6))
    _ax(ax)
    sites = [s for s in ("GOSH", "RBH", "SMH") if s in set(static["site"])]
    w = 0.8 / len(sites)
    for i, site in enumerate(sites):
        n = static[static["site"] == site].groupby("patient_id")["stay_key"].nunique().clip(upper=cap)
        sh = n.value_counts(normalize=True).reindex(range(1, cap + 1)).fillna(0) * 100
        ax.bar(np.arange(cap) + i * w - 0.4 + w / 2, sh.to_numpy(), width=w * 0.92, color=SITE_COLOUR[site], label=site)
    ax.set_xticks(range(cap))
    ax.set_xticklabels([str(i) for i in range(1, cap)] + [f"{cap}+"])
    ax.set_xlabel("stays per patient", color=INK2)
    ax.set_ylabel("patients (%)", color=INK2)
    ax.legend(frameon=False, labelcolor=INK2)
    ax.set_title("Patients with repeat stays", color=INK, loc="left", fontsize=11)
    return _save(fig, path)


def plot_composition(static, col="ethnicity", mapper=ethnicity_group, path=None):
    """Share of stays in each group by site (a 100% horizontal stacked bar per site), groups made with `mapper`."""
    import matplotlib.pyplot as plt
    g = static[col].map(mapper) if mapper else static[col].astype("string").fillna("(missing)")
    t = pd.crosstab(static["site"], g, normalize="index") * 100
    cols = [c for c in t.sum().sort_values(ascending=False).index]
    fig, ax = plt.subplots(figsize=(8, 3))
    _ax(ax)
    ax.grid(axis="y", visible=False)
    left = np.zeros(len(t))
    for i, c in enumerate(cols):
        ax.barh(t.index, t[c], left=left, color=CAT[i % len(CAT)], label=c, height=0.6, edgecolor=SURFACE, linewidth=2)
        left += t[c].to_numpy()
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("stays (%)", color=INK2)
    ax.legend(frameon=False, ncol=len(cols), fontsize=8, labelcolor=INK2, loc="upper center", bbox_to_anchor=(0.5, -0.3))
    ax.set_title(f"{col.replace('_', ' ').capitalize()} groups by site", color=INK, loc="left", fontsize=11)
    return _save(fig, path)


def plot_pooling(uniq, k=10, path=None):
    """Number of stays in cells smaller than k for each combination: the three sites counted separately (cells inside each site, the situation
    when the site is a released column) against all stays pooled (cells across sites, when the site is not visible). `uniq` is a `uniqueness`
    frame with the site rows and the pooled rows."""
    import matplotlib.pyplot as plt
    col = f"stays_in_cells_below_{k}"
    order = list(uniq["combination"].unique())
    sep = uniq[uniq["site"] != "pooled"].groupby("combination")[col].sum().reindex(order)
    pool = uniq[uniq["site"] == "pooled"].set_index("combination")[col].reindex(order)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    _ax(ax)
    x = np.arange(len(order))
    ax.bar(x - 0.2, sep.to_numpy(), width=0.38, color=CAT[0], label="cells within each site")
    ax.bar(x + 0.2, pool.to_numpy(), width=0.38, color=CAT[1], label="cells across all sites")
    ax.set_yscale("symlog", linthresh=10)
    ax.set_xticks(x)
    ax.set_xticklabels([o.replace("t2 ", "") for o in order], rotation=30, ha="right")
    ax.set_ylabel(f"stays in cells smaller than {k}", color=INK2)
    ax.legend(frameon=False, labelcolor=INK2, fontsize=9)
    ax.set_title("Pooling sites shrinks the number of rare stays", color=INK, loc="left", fontsize=11)
    return _save(fig, path)


def plot_scope(uniq, combination="all", k=10, path=None):
    """Stays in cells smaller than k for one combination, counted two ways: within each site (stacked by site, the total over the three sites) and
    across all sites pooled. Use it on the frame from `uniqueness` after suppression to show why pooling matters when the site is not visible."""
    import matplotlib.pyplot as plt
    col = f"stays_in_cells_below_{k}"
    u = uniq[uniq["combination"] == combination].set_index("site")[col]
    sites = [s for s in ("GOSH", "RBH", "SMH") if s in u.index]
    fig, ax = plt.subplots(figsize=(6, 4))
    _ax(ax)
    bottom = 0
    for site in sites:
        v = int(u[site])
        ax.bar(0, v, bottom=bottom, color=SITE_COLOUR[site], width=0.55, label=site, edgecolor=SURFACE, linewidth=2)
        ax.text(0, bottom + v / 2, f"{site} {v}", ha="center", va="center", color="#ffffff", fontsize=9)
        bottom += v
    ax.text(0, bottom + max(bottom, 1) * 0.02, str(int(bottom)), ha="center", va="bottom", color=INK, fontsize=10)
    pooled = int(u["pooled"])
    ax.bar(1, pooled, color=INK, width=0.55)
    ax.text(1, pooled + max(bottom, 1) * 0.02, str(pooled), ha="center", va="bottom", color=INK, fontsize=10)
    ax.set_ylim(0, max(bottom, pooled, 1) * 1.15)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["cells within each site\n(site is visible)", "cells across all sites\n(site is not visible)"])
    ax.set_ylabel(f"stays in cells smaller than {k}", color=INK2)
    ax.set_title("Rare stays after suppression", color=INK, loc="left", fontsize=11)
    return _save(fig, path)


# ---------------------------------------------------------------------------------------------------------------------------------
# Site inference. Decision (Jake, 2026-11-19): the release is pooled and the site is not a column; anonymisation also has to make the site hard
# to infer, for example by dropping features that exist at one site only. These checks measure how well the site can still be guessed.
# ---------------------------------------------------------------------------------------------------------------------------------
def concept_coverage(avail):
    """For each concept: the sites that collect it at all (not <NA> in the availability table). Concepts collected at only some sites tell
    the user which site a stay is from. Names and site lists only."""
    sites = sorted(set(avail.index.get_level_values("site")))
    rows = []
    for c in avail.columns:
        have = [s for s in sites if avail.xs(s, level="site")[c].notna().any()]
        rows.append({"concept": c, "sites": ", ".join(have), "n_sites": len(have)})
    return pd.DataFrame(rows).sort_values(["n_sites", "concept"])


def pattern_site_share(avail, min_count=10):
    """Availability patterns (the set of concepts a stay has, site left out): the share of stays whose pattern occurs at one site only, and the
    share whose pattern occurs at one site only with fewer than min_count stays. Counts only."""
    a = avail.copy()
    pat = a.astype("string").fillna("-").replace({"True": "1", "False": "0"}).apply(lambda r: "".join(r), axis=1)
    site = pd.Series(a.index.get_level_values("site"), index=a.index)
    nsites = pat.groupby(pat).transform(lambda s: site[s.index].nunique())
    return {"stays": len(a), "share_pattern_at_one_site_only": round(float((nsites == 1).mean()), 4)}


def site_inference(X, site, cv=5, drop_one=True, seed=0, groups=None, numeric=()):
    """How well the site can be guessed from the columns of X (one row per stay; categorical and boolean columns are one-hot encoded, missing
    values count as a category). Cross-validated accuracy of a gradient-boosting classifier against the baseline of always guessing the largest
    site, and per-site recall. drop_one=True also reports the accuracy with each column left out, to show which columns give the site away.
    groups: one label per row (for example site and patient) so that all stays of a patient fall in the same fold; without it a patient's
    stays can be in both training and test folds, which makes the site look easier to guess than it is. numeric: names of columns to use as
    numbers (missing stays missing; the classifier handles it) instead of as categories, for value summaries. Needs scikit-learn. Counts only;
    no values from X are shown."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import cross_val_predict, StratifiedKFold, StratifiedGroupKFold
    y = pd.Series(np.asarray(site)).astype(str)
    numeric_set = set(numeric)

    def acc(cols):
        num = [c for c in cols if c in numeric_set]
        Z = pd.get_dummies(X[[c for c in cols if c not in numeric_set]].astype("string").fillna("(missing)"), dtype=float)
        if num:
            Z = pd.concat([Z, X[num].astype("float64")], axis=1)
        folds = StratifiedGroupKFold(cv, shuffle=True, random_state=seed) if groups is not None else StratifiedKFold(cv, shuffle=True, random_state=seed)
        p = cross_val_predict(HistGradientBoostingClassifier(random_state=seed, max_iter=100), Z.to_numpy(), y.to_numpy(),
                              cv=folds, groups=None if groups is None else np.asarray(groups))
        return float((p == y.to_numpy()).mean()), pd.Series(p == y.to_numpy()).groupby(y.to_numpy()).mean()

    a, per = acc(list(X.columns))
    out = {"accuracy": round(a, 4), "baseline": round(float(y.value_counts(normalize=True).iloc[0]), 4), "recall_by_site": per.round(3)}
    if drop_one:
        out["accuracy_without"] = pd.Series({c: round(acc([k for k in X.columns if k != c])[0], 4) for c in X.columns}).sort_values()
    return out


def plot_site_inference(res_all, res_without, without_label="diagnosis group", path=None):
    """Two panels for presenting the site-inference test. Left: accuracy of guessing the site from all columns, and with each column left out in
    turn (`res_all`, from `site_inference` with drop_one=True), against the baseline of always guessing the largest site; the column named
    `without_label` is highlighted. Right: recall for each site with all columns and without that column (`res_without`, its recall_by_site)."""
    import matplotlib.pyplot as plt
    base = res_all["baseline"] * 100
    acc = res_all["accuracy_without"] * 100
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4), gridspec_kw={"width_ratios": [1.3, 1]})
    _ax(a1)
    a1.grid(axis="x", color=GRID, linewidth=0.8)
    a1.grid(axis="y", visible=False)
    names = ["All columns"] + [f"Without {c.replace('_', ' ')}" for c in acc.index]
    vals = [res_all["accuracy"] * 100] + list(acc.values)
    cols = [CAT[0]] + [CAT[1] if c.replace("_", " ") == without_label else CAT[0] for c in acc.index]
    order = np.argsort(vals)[::-1]
    names, vals, cols = [names[i] for i in order], [vals[i] for i in order], [cols[i] for i in order]
    a1.barh(names, vals, color=cols, height=0.6)
    for y, v in enumerate(vals):
        a1.text(v + 0.6, y, f"{v:.1f}%", va="center", color=INK2, fontsize=9)
    a1.axvline(base, color=INK, linewidth=1.5, linestyle="--", label=f"always guess the largest site ({base:.1f}%)")
    a1.legend(frameon=False, labelcolor=INK2, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.17))
    a1.invert_yaxis()
    a1.set_xlim(0, 100)
    a1.set_xlabel("stays whose site is guessed correctly (%)", color=INK2)
    a1.set_title("How well the site can be guessed from the static fields", color=INK, loc="left", fontsize=11)
    _ax(a2)
    sites = [s for s in ("GOSH", "RBH", "SMH") if s in res_all["recall_by_site"].index]
    x = np.arange(len(sites))
    a2.bar(x - 0.2, res_all["recall_by_site"].reindex(sites) * 100, width=0.38, color=CAT[0], label="all columns")
    a2.bar(x + 0.2, res_without["recall_by_site"].reindex(sites) * 100, width=0.38, color=CAT[1], label=f"without {without_label}")
    a2.set_xticks(x)
    a2.set_xticklabels(sites)
    a2.set_ylim(0, 100)
    a2.set_ylabel("stays of the site guessed correctly (%)", color=INK2)
    a2.legend(frameon=False, labelcolor=INK2, fontsize=9)
    a2.set_title("Recall by site", color=INK, loc="left", fontsize=11)
    return _save(fig, path)


def plot_site_variants(res, title="How well the site can be guessed from which concepts a stay has", path=None):
    """Compare several `site_inference` results (a dict of name -> result, for example the availability table with progressively fewer
    concepts). Left: accuracy per variant against the baseline of always guessing the largest site. Right: recall by site for each variant."""
    import matplotlib.pyplot as plt
    names = list(res)
    base = next(iter(res.values()))["baseline"] * 100
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 3.8), gridspec_kw={"width_ratios": [1.2, 1]})
    _ax(a1)
    a1.grid(axis="x", color=GRID, linewidth=0.8)
    a1.grid(axis="y", visible=False)
    acc = [res[n]["accuracy"] * 100 for n in names]
    a1.barh(names, acc, color=CAT[0], height=0.55)
    for y, v in enumerate(acc):
        a1.text(v + 0.8, y, f"{v:.1f}%", va="center", color=INK2, fontsize=9)
    a1.axvline(base, color=INK, linewidth=1.5, linestyle="--", label=f"always guess the largest site ({base:.1f}%)")
    a1.legend(frameon=False, labelcolor=INK2, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.17))
    a1.invert_yaxis()
    a1.set_xlim(0, 110)
    a1.set_xlabel("stays whose site is guessed correctly (%)", color=INK2)
    a1.set_title(title, color=INK, loc="left", fontsize=11)
    _ax(a2)
    sites = [s for s in ("GOSH", "RBH", "SMH") if s in next(iter(res.values()))["recall_by_site"].index]
    w = 0.8 / len(names)
    for i, n in enumerate(names):
        a2.bar(np.arange(len(sites)) + i * w - 0.4 + w / 2, res[n]["recall_by_site"].reindex(sites) * 100, width=w * 0.92, color=CAT[i % len(CAT)], label=n)
    a2.set_xticks(range(len(sites)))
    a2.set_xticklabels(sites)
    a2.set_ylim(0, 100)
    a2.set_ylabel("stays of the site guessed correctly (%)", color=INK2)
    a2.legend(frameon=False, labelcolor=INK2, fontsize=8, loc="lower center", bbox_to_anchor=(0.5, -0.42), ncol=1)
    a2.set_title("Recall by site", color=INK, loc="left", fontsize=11)
    return _save(fig, path)


def plot_group_drop(acc, baseline, reference="none removed", title="Which concept group gives the site away?", path=None):
    """Accuracy of guessing the site from the shared concepts' availability with one concept group removed at a time (a Series of accuracies in
    0 to 1, with the entry `reference` for nothing removed), against the baseline of always guessing the largest site. The label of each bar
    shows the accuracy and the change from the reference."""
    import matplotlib.pyplot as plt
    a = acc.sort_values() * 100
    ref = acc[reference] * 100
    fig, ax = plt.subplots(figsize=(8, 3.8))
    _ax(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    cols = [INK2 if n == reference else CAT[0] for n in a.index]
    ax.barh(list(a.index), a.values, color=cols, height=0.55)
    for y, (n, v) in enumerate(a.items()):
        txt = f"{v:.1f}%" if n == reference else f"{v:.1f}%  ({v - ref:+.1f} points)"
        ax.text(v + 0.8, y, txt, va="center", color=INK2, fontsize=9)
    ax.axvline(baseline * 100, color=INK, linewidth=1.5, linestyle="--", label=f"always guess the largest site ({baseline * 100:.1f}%)")
    ax.legend(frameon=False, labelcolor=INK2, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.17))
    ax.set_xlim(0, 112)
    ax.set_xlabel("stays whose site is guessed correctly (%)", color=INK2)
    ax.set_title(title, color=INK, loc="left", fontsize=11)
    return _save(fig, path)