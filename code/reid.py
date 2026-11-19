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


def coarsen(static, k=10, ethnicity="group", weight=True, n_groups=10, seed=0, merge_dx=False, age_edges=AGE_EDGES, weight_edges=WEIGHT_EDGES, los_edges=LOS_EDGES):
    """Copy of the static table with the candidate Tier 2 coarsening, for the uniqueness check. Columns kept: site, stay_key, age_band,
    sex, ethnicity, diagnosis_group, died, split_group, and weight_band and los_band. Dropped: patient_id, year, t0, pim, pim_version, exact age,
    weight and length of stay.
    - ethnicity='group': six broad groups (White, Asian, Black, Mixed, Other, Not recorded); 'detail': the recorded label, with labels seen in
      fewer than k stays at a site merged into '<group> (merged)'.
    - diagnosis_group: kept as recorded (PICANet groups). Rare groups are handled by `suppress_to_k` at the level of the combination, not here;
      merge_dx=True merges groups seen in fewer than k stays at a site into 'Other (merged)'.
    - sex: values other than Male and Female, or seen in fewer than k stays at the site, become missing.
    - split_group: each patient is assigned at random (per site, fixed seed) to one of n_groups groups; use it for patient-level splits."""
    s = add_bands(static, age_edges, weight_edges, los_edges)
    out = pd.DataFrame({"site": s["site"], "stay_key": s["stay_key"], "age_band": s["age_band"], "los_band": s["los_band"]})
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
    "t2 +los": ["age_band", "sex", "ethnicity", "diagnosis_group", "died", "weight_band", "los_band"],
}


def split_group_sizes(coarse):
    """Stays and groups per site: the number of stays in the smallest and largest split group. Counts only."""
    g = coarse.groupby(["site", "split_group"]).size()
    return g.groupby("site").agg(groups="size", smallest="min", largest="max").reset_index()


# Alternative, coarser bands to compare against the defaults.
AGE_COARSE = [0, 1, 3, 12, 24, 60, 120, 192, np.inf]      # <1m, 1-3m, 3-12m, 1-2y, 2-5y, 5-10y, 10-16y, 16y+
WEIGHT_COARSE = [0, 5, 10, 20, 40, np.inf]
LOS_COARSE = [0, 24, 72, 240, np.inf]


def suppress_to_k(coarse, key_cols, order, k=10, token="(suppressed)"):
    """Local suppression: stays are all kept; for stays whose combination of `key_cols` is shared by fewer than k stays at their site, one
    field at a time (in `order`, least valuable first) is replaced by `token`, recomputing the cells after each field, until no stay is in a
    cell below k or the fields are used up. Returns (frame, report): per field the number of values suppressed, and at the end the stays
    still in cells below k. Counts only. A field in `order` that is not in `key_cols` is still suppressed when it is listed."""
    out = coarse.copy()
    rows = []
    for f in order:
        cols = [c for c in key_cols if c in out.columns]
        size = out.groupby(["site"] + [out[c].astype("string").fillna("(missing)") for c in cols])["stay_key"].transform("size")
        small = size < k
        if f in out.columns and small.any():
            out[f] = out[f].astype("string").mask(small, token)
        rows.append({"field": f, "values_suppressed": int(small.sum()) if f in out.columns else 0})
    cols = [c for c in key_cols if c in out.columns]
    size = out.groupby(["site"] + [out[c].astype("string").fillna("(missing)") for c in cols])["stay_key"].transform("size")
    rows.append({"field": "(stays still below k)", "values_suppressed": int((size < k).sum())})
    return out, pd.DataFrame(rows)


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


def plot_buildup(variants, k=10, order=None, path=None):
    """Share of stays in cells smaller than k as fields are added one by one: one panel per site and pooled, one line per variant (a dict of
    name -> `uniqueness` frame). Shows which field makes the data identifiable and how much coarsening helps."""
    import matplotlib.pyplot as plt
    order = order or list(next(iter(variants.values()))["combination"].unique())
    sites = ["GOSH", "RBH", "SMH", "pooled"]
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.8), sharey=True)
    styles = [("-", "o"), ("--", "s"), (":", "^")]
    for ax, site in zip(axes, sites):
        _ax(ax)
        for (name, df), (ls, mk) in zip(variants.items(), styles):
            d = df[df["site"] == site].set_index("combination").reindex(order)
            ax.plot(range(len(order)), d["share_below_k"] * 100, ls, marker=mk, ms=7, lw=2, color=SITE_COLOUR[site], mfc=SURFACE, mew=2, label=name)
        ax.set_title(site, color=INK, fontsize=11, loc="left")
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels([o.replace("t2 ", "") for o in order], rotation=40, ha="right")
    axes[0].set_ylabel(f"stays in cells smaller than {k} (%)", color=INK2)
    axes[0].legend(frameon=False, fontsize=8, labelcolor=INK2)
    fig.suptitle("Identifiability as static fields are added", color=INK, x=0.01, ha="left", fontsize=12)
    return _save(fig, path)


def plot_suppression(rep, n_stays, path=None):
    """Share of stays that lose each field under local suppression (from `suppress_to_k`'s report); the last row is stays still below k."""
    import matplotlib.pyplot as plt
    r = rep.copy()
    r["share"] = r["values_suppressed"] / n_stays * 100
    fig, ax = plt.subplots(figsize=(7, 3.4))
    _ax(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.barh(r["field"], r["share"], color=CAT[0], height=0.55)
    for y, v in enumerate(r["share"]):
        ax.text(v + 0.5, y, f"{v:.1f}%", va="center", color=INK2, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("stays affected (%)", color=INK2)
    ax.set_title("What local suppression costs", color=INK, loc="left", fontsize=11)
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