"""Step 2 diagnostics for SMH (St Mary's): how the IDs link, the PICANet link, the time offset, the drug-table versions.

Counts only: nothing returned is an ID, a date or a row value. Shared helpers are in diagnostics.py.
The interventionId-to-measurement tables are mapping work and live in smh_mappings.py, not here.
Notebook: smh_diagnostics.ipynb.

    import smh_diagnostics as SD
    d = SD.load(smh_dir)
    SD.demographics_duplicates(d)       # repeated rows per encounter, encounters per patient
    SD.picanet_link(d)                  # PICANet rows, link to demographics, UniquePtID agreement, PICANet by year
    SD.weight_checks(d)                 # weight and admission time within an encounter; against PICANet weight
    SD.time_offset(smh_dir, d)          # first vitals row against inTime: is inTime local time and the chart time UTC?
    SD.medication_versions(smh_dir)     # medications, medications_furosemide, medications_v2
    SD.drug_coverage_by_year(smh_dir, manifest)   # share of eligible stays with drug rows, by admission year
    SD.duplicate_pattern(smh_dir, manifest, "ai_picu_io.csv")   # where the exact duplicate rows sit (assembly removes them)
"""
from pathlib import Path

import numpy as np
import pandas as pd

import assemble as A
import diagnostics as D
import inventory as I

DEMO, PIC = "ai_picu_demographics.csv", "ai_picu_piccanet.csv"
DRUG_FILES = ["ai_picu_infusion.csv", "ai_picu_medications.csv", "ai_picu_medications_furosemide.csv",
              "ai_picu_medications_v2.csv"]


def _dir(smh_dir):
    return Path(smh_dir).expanduser()


def load(smh_dir):
    """Demographics (all rows and with exact duplicates removed) and PICANet, read once."""
    smh_dir = _dir(smh_dir)
    raw, _ = I.read(smh_dir / DEMO)
    d1 = raw.drop_duplicates().copy()
    d1["t"] = I.parse_dates(d1["inTime"])[0]
    d1["w"] = pd.to_numeric(d1["Weight"], errors="coerce")
    pic, _ = I.read(smh_dir / PIC)
    return {"dir": smh_dir, "demo_all": raw, "demo": d1, "pic": pic}


def demographics_duplicates(d):
    """Exact duplicate rows, encounters with differing rows (and which columns differ), encounters per patient."""
    raw, d1 = d["demo_all"], d["demo"]
    base = d1.drop(columns=["t", "w"])
    dup = base[base["encounterId"].duplicated(keep=False)]
    return {"rows": pd.DataFrame({"count": [len(raw), len(base), base["encounterId"].nunique(),
                                            base["UniquePtID"].nunique(), dup["encounterId"].nunique()]},
                                 index=["rows", "rows after exact duplicates removed", "encounters", "patients",
                                        "encounters with differing rows"]),
            "most distinct values within an encounter, by column":
                dup.groupby("encounterId").nunique().max().to_frame("distinct values"),
            "encounters per patient": base.groupby("UniquePtID")["encounterId"].nunique()
                                          .value_counts().sort_index().head(8).to_frame("patients")}


def picanet_link(d):
    """PICANet against demographics: rows, link by encounterId, whether UniquePtID agrees, and PICANet membership
    by admission year (the cohort starts in 2013 because PICANet does)."""
    pn, d1 = d["pic"], d["demo"]
    m = pn.merge(d1[["encounterId", "UniquePtID"]].drop_duplicates(), on="encounterId", suffixes=("", "_dem"))
    summary = pd.DataFrame({"value": [len(pn), pn["encounterId"].nunique(),
                                      round(pn["encounterId"].isin(d1["encounterId"]).mean(), 3),
                                      int(pn["PIM3"].isna().sum()) if "PIM3" in pn else None,
                                      round((m["UniquePtID"] == m["UniquePtID_dem"]).mean(), 3)]},
                           index=["PICANet rows", "unique encounterId", "share of PICANet encounters in demographics",
                                  "PIM3 missing", "UniquePtID equal in both files (0 = the two files use different patient IDs)"])
    e = d1.assign(year=d1["t"].dt.year, picanet=d1["encounterId"].isin(pn["encounterId"]))
    return {"link": summary,
            "encounters by admission year and PICANet membership":
                e.groupby(["year", "picanet"])["encounterId"].nunique().unstack(fill_value=0)}


def weight_checks(d):
    """Admission time and weight within an encounter, and weight against the PICANet weight."""
    d1, pn = d["demo"], d["pic"]
    g = d1.groupby("encounterId")
    gap = g["t"].agg(lambda s: (s.max() - s.min()).total_seconds() / 3600)
    ratio = g["w"].agg(lambda s: s.max() / s.min())
    summary = pd.DataFrame({"count": [int((g["inTime"].nunique() > 1).sum()), int((g["Weight"].nunique() > 1).sum()),
                                      int(d1["Weight"].notna().sum() - d1["w"].notna().sum())]},
                           index=["encounters with more than one inTime", "encounters with more than one Weight",
                                  "non-numeric Weight entries"])
    pw = pn.drop_duplicates("encounterId").set_index("encounterId")["Weight"].rename("pn_weight")
    dw = g["w"].agg(["min", "median", "max"]).join(pw, how="inner").dropna(subset=["pn_weight"])
    agree = pd.DataFrame({"share within 5% of PICANet weight":
                          {c: round(((dw[c] - dw["pn_weight"]).abs() / dw["pn_weight"] < 0.05).mean(), 3)
                           for c in ["min", "median", "max"]}})
    return {"summary": summary,
            "inTime spread within an encounter, hours (where > 0)": gap[gap > 0].describe().round(1).to_frame("value"),
            "max/min weight within an encounter (where > 1, finite)":
                ratio[(ratio > 1) & np.isfinite(ratio)].describe().round(3).to_frame("value"),
            f"demographics weight against PICANet weight ({len(dw)} encounters)": agree}


def time_offset(smh_dir, d):
    """Hours from inTime to each encounter's first vitals row, overall and by season. A one-hour shift in summer and
    none in winter means inTime is London local time and utcChartTime is UTC (British Summer Time)."""
    v, _ = I.read(_dir(smh_dir) / "ai_picu_vitals.csv", usecols=["encounterId", "utcChartTime"])
    first = pd.to_datetime(v["utcChartTime"]).groupby(v["encounterId"]).min()
    t_in = d["demo"].drop_duplicates("encounterId").set_index("encounterId")["t"]
    dh = (first - t_in.reindex(first.index)).dt.total_seconds() / 3600
    mo = t_in.reindex(dh.index).dt.month
    return {"first vitals minus inTime, hours": dh.describe().round(2).to_frame("value"),
            "rounded to the hour, most common": dh.round().value_counts().head(8).to_frame("encounters"),
            "May to September": dh[mo.between(5, 9)].round().value_counts().head(4).to_frame("encounters"),
            "November to February": dh[(mo >= 11) | (mo <= 2)].round().value_counts().head(4).to_frame("encounters")}


def medication_versions(smh_dir):
    """Does medications_v2 equal medications plus medications_furosemide? Row counts, and the share of v2 records
    (encounter, time, drug, dose) that appear in the other two."""
    smh_dir = _dir(smh_dir)
    tables = {}
    for f in ["ai_picu_medications.csv", "ai_picu_medications_furosemide.csv", "ai_picu_medications_v2.csv"]:
        df, _ = I.read(smh_dir / f)
        df = df.rename(columns={"encounterID": "enc"})
        df["t"] = I.parse_dates(df["utcChartTime"])[0]
        tables[f] = df[["enc", "t", "Drug_terse", "Dosage_verbose"]].astype(str)
    a, b, v2 = tables.values()
    union = pd.concat([a, b]).drop_duplicates()
    hit = v2.drop_duplicates().merge(union, how="left", indicator=True)["_merge"].eq("both").mean()
    return pd.DataFrame({"value": [len(a), len(b), len(v2), len(a) + len(b), round(hit, 4)]},
                        index=["rows: medications", "rows: furosemide", "rows: v2", "medications + furosemide",
                               "share of v2 records found in medications or furosemide"])


def _fmt_s(ser):
    """Counts as text with thousands separators (avoids 4.98944e+06 in reports); shares stay as they are."""
    return ser.map(lambda v: f"{v:,}" if isinstance(v, (int, np.integer)) else v).astype(object)


def drug_coverage_by_year(smh_dir, manifest, files=DRUG_FILES):
    """Share of the eligible encounters in `manifest` (smh_manifest output) with at least one row in each drug table,
    by admission year. Keys are normalised on both sides so text and integer ids match. See diagnostics.coverage_by_year."""
    m = manifest.copy()
    m["encounterId"] = A._norm_key(m["encounterId"])
    m["year"] = pd.to_numeric(m["year"])
    keys = {}
    for f in files:
        df, _ = I.read(_dir(smh_dir) / f, usecols=lambda c: c.lower() == "encounterid")
        keys[f.replace("ai_picu_", "").replace(".csv", "")] = set(A._norm_key(df.iloc[:, 0]).dropna())
    return D.coverage_by_year(m, keys, key_col="encounterId")


def duplicate_pattern(smh_dir, manifest, file="ai_picu_io.csv", chunksize=1_000_000):
    """Assembly drops rows that are identical in every column. Are they extraction copies or real repeats?
    For the rows of manifest stays in one SMH table (rows are read as text, as in assembly), counts:
      - how many rows are copies of an earlier row, and how many copies a row has;
      - the distance in file rows from each copy to the identical row before it (next to it in the file, or
        far away: copies made by the extraction usually sit together);
      - how many encounters have any copy, and the share of copies per encounter;
      - copies per 1,000 rows by admission year (a change at one date points to the extraction).
    Counts only. The number of copies should equal 'exact duplicates removed' in the assembly log."""
    path = _dir(smh_dir) / file
    keep_ids = set(A._norm_key(manifest["encounterId"]).dropna())
    year = dict(zip(A._norm_key(manifest["encounterId"]), pd.to_numeric(manifest["year"], errors="coerce")))
    hs, pos, enc = [], [], []
    start = 0
    for chunk in A._chunks(path, chunksize):
        col = "encounterId" if "encounterId" in chunk.columns else "encounterID"
        key = A._norm_key(chunk[col])
        sub = chunk[key.isin(keep_ids)]
        hs.append(A._hash(sub))
        pos.append(start + np.flatnonzero(key.isin(keep_ids).to_numpy()))
        enc.append(key[sub.index].to_numpy())
        start += len(chunk)
    df = pd.DataFrame({"h": np.concatenate(hs), "pos": np.concatenate(pos), "enc": np.concatenate(enc)})
    df["copy"] = df.duplicated("h")
    df["gap"] = df["pos"] - df.groupby("h")["pos"].shift()
    n_copies = df.groupby("h").size()
    overview = pd.Series({
        "rows of manifest stays": len(df), "distinct rows": int(df["h"].nunique()),
        "copies (rows identical to an earlier row)": int(df["copy"].sum()),
        "distinct rows that have a copy": int((n_copies > 1).sum()),
        "share of rows that are copies": round(float(df["copy"].mean()), 3)}, dtype=object).pipe(_fmt_s).to_frame("rows")
    per_row = n_copies.clip(upper=4).astype(str).replace({"4": "4+"}).value_counts().sort_index().rename("distinct rows")
    per_row.index = [f"{i} time" + ("" if i == "1" else "s") + " in the file" for i in per_row.index]
    g = df.loc[df["copy"], "gap"]
    gaps = pd.cut(g, [0, 1, 10, 1000, 100000, np.inf], labels=["next row", "2 to 10 rows back", "11 to 1,000 rows back",
                                                              "1,001 to 100,000 rows back", "over 100,000 rows back"])
    gap_table = gaps.value_counts().reindex(gaps.cat.categories).rename("copies").to_frame()
    e = df.groupby("enc")["copy"].agg(rows="size", copies="sum").astype("int64")
    e["share"] = e["copies"] / e["rows"]
    per_enc = pd.Series({
        "with rows in the table": len(e), "with at least one copy": int((e["copies"] > 0).sum()),
        "median share of copies (those with any)": round(float(e.loc[e["copies"] > 0, "share"].median()), 3),
        "90th percentile of that share": round(float(e.loc[e["copies"] > 0, "share"].quantile(0.9)), 3),
        "highest share": round(float(e["share"].max()), 3)}, dtype=object).pipe(_fmt_s).to_frame("encounters")
    df["year"] = df["enc"].map(year)
    by_year = df.groupby("year")["copy"].agg(rows="size", copies="sum").astype("int64")
    by_year["copies per 1,000 rows"] = (1000 * by_year["copies"] / by_year["rows"]).round(1)
    return {"Copies": overview, "Times each distinct row appears": per_row.to_frame(),
            "Distance to the identical row before it": gap_table, "Encounters affected": per_enc,
            "By admission year": by_year}


def same_key_values(smh_dir, manifest, file="ai_picu_vitals.csv", time_col="utcChartTime",
                    id_cols=("interventionId", "attributeId"), chunksize=1_000_000):
    """Second look at the exact duplicates of one SMH long-format table. Rows of manifest stays that share an
    encounter, a time and a measurement id form a group. Counts how many groups hold a single row, how many
    hold only identical copies, and how many hold different values at the same time (before and after exact
    copies are removed), and how many whole minutes the times are on (the time resolution). Counts only.
      - groups with only identical copies: one reading written several times (extraction copy, or a reading
        logged more often than the time resolution);
      - groups with different values at one time: several real readings per timestamp, which remain after
        assembly removes the exact copies and need a rule at the hourly step.
    id_cols: the columns that identify the measurement (vitals: interventionId, attributeId; vent: interventionId)."""
    path = _dir(smh_dir) / file
    keep_ids = set(A._norm_key(manifest["encounterId"]).dropna())
    h, g, ids, parsed, whole_min = [], [], [], 0, 0
    for chunk in A._chunks(path, chunksize):
        enc_col = "encounterId" if "encounterId" in chunk.columns else "encounterID"
        need = [enc_col, time_col, *id_cols]
        missing = [c for c in need if c not in chunk.columns]
        if missing:
            raise ValueError(f"{file}: no column {missing}. Columns: {list(chunk.columns)}")
        sub = chunk[A._norm_key(chunk[enc_col]).isin(keep_ids)]
        h.append(A._hash(sub))
        g.append(A._hash(sub[need]))
        ids.append(sub[id_cols[0]].astype(str).to_numpy())
        t = I.parse_dates(sub[time_col])[0].dropna()
        parsed += len(t)
        whole_min += int(((t.dt.second == 0) & (t.dt.microsecond == 0)).sum())
    df = pd.DataFrame({"h": np.concatenate(h), "g": np.concatenate(g), "id": np.concatenate(ids)})
    n_rows = df.groupby("g").size()
    n_diff = df.drop_duplicates("h").groupby("g").size().reindex(n_rows.index)
    summary = pd.Series({
        "rows of manifest stays": len(df),
        "groups (encounter, time, measurement id)": len(n_rows),
        "groups with one row": int((n_rows == 1).sum()),
        "groups with several rows, all identical": int(((n_rows > 1) & (n_diff == 1)).sum()),
        "groups with different values at the same time": int((n_diff > 1).sum()),
        "rows in those groups after exact copies are removed": int(n_diff[n_diff > 1].sum())},
        dtype=object).pipe(_fmt_s).to_frame("count")
    spread = n_diff.clip(upper=4).astype(str).replace({"4": "4+"}).value_counts().sort_index().rename("groups").to_frame()
    spread.index = [f"{i} distinct row" + ("" if i == "1" else "s") for i in spread.index]
    resolution = pd.Series({"times that parse": parsed,
                            "times exactly on a whole minute": whole_min,
                            "share on a whole minute": round(whole_min / max(parsed, 1), 3)},
                           dtype=object).pipe(_fmt_s).to_frame("count")
    first_id = df.drop_duplicates("g").set_index("g")["id"]
    total_by_id = first_id.value_counts()
    conflict_by_id = first_id[n_diff[n_diff > 1].index].value_counts()
    by_id = pd.DataFrame({"groups": total_by_id, "with different values": conflict_by_id}).fillna(0).astype(int)
    by_id["share with different values"] = (by_id["with different values"] / by_id["groups"]).round(3)
    by_id = by_id.sort_values("with different values", ascending=False).head(12)
    by_id.index.name = id_cols[0]
    return {"Rows sharing encounter, time and measurement id": summary,
            f"Groups with different values, by {id_cols[0]} (top 12)": by_id,
            "Distinct rows per group, after exact copies are removed": spread,
            "Time resolution": resolution}


def multiplicity_by_encounter(smh_dir, manifest, file="ai_picu_vitals.csv", demo=DEMO, chunksize=1_000_000):
    """Test of one explanation for the exact copies: the extraction joined each table to a per-encounter list
    (for example the weight records) so that every row of an encounter is repeated as many times as the list is
    long. If so, within an encounter nearly every row appears the same number of times, and that number
    (k) is the same for different tables. For the rows of manifest stays in one table, per encounter:
      - the commonest repeat count k, and the share of the encounter's distinct rows that appear exactly k times;
      - how many encounters have each k;
      - k against the number of demographics rows the encounter has in the raw demographics file.
    Counts only."""
    path = _dir(smh_dir) / file
    keep_ids = set(A._norm_key(manifest["encounterId"]).dropna())
    hs, enc = [], []
    for chunk in A._chunks(path, chunksize):
        col = "encounterId" if "encounterId" in chunk.columns else "encounterID"
        key = A._norm_key(chunk[col])
        ok = key.isin(keep_ids)
        hs.append(A._hash(chunk[ok]))
        enc.append(key[ok].to_numpy())
    df = pd.DataFrame({"h": np.concatenate(hs), "enc": np.concatenate(enc)})
    d = df.groupby(["enc", "h"]).size().rename("times").reset_index()      # one row per distinct row
    k = d.groupby("enc")["times"].agg(lambda s: s.value_counts().idxmax())
    share = d.assign(is_k=d["times"] == d["enc"].map(k)).groupby("enc")["is_k"].mean()
    per_k = k.clip(upper=5).astype(str).replace({"5": "5+"}).value_counts().sort_index()
    per_k = per_k.rename("encounters").to_frame()
    per_k.index = [f"repeated {i} time" + ("" if i == "1" else "s") for i in per_k.index]
    affected = share[k > 1]
    uniform = pd.Series({
        "encounters with rows in the table": len(k),
        "encounters whose commonest repeat count is above 1": int((k > 1).sum()),
        "of those, median share of distinct rows at that count": round(float(affected.median()), 3),
        "of those, share of encounters where at least 95% of rows are at that count": round(float((affected >= 0.95).mean()), 3)},
        dtype=object).pipe(_fmt_s).to_frame("value")
    dm = A._norm_key(I.read(_dir(smh_dir) / demo, usecols=lambda c: c.lower() == "encounterid")[0].iloc[:, 0])
    n_demo = dm.value_counts().reindex(k.index).fillna(0).astype(int)
    cross = pd.crosstab(k.clip(upper=5).rename("repeat count k").astype(str).replace({"5": "5+"}),
                        n_demo.clip(upper=4).rename("demographics rows").astype(str).replace({"4": "4+"}))
    return {"Repeat count per encounter": per_k, "How uniform the repeats are within an encounter": uniform,
            "Repeat count against demographics rows per encounter": cross}


def copies_explained_by_join(smh_dir, manifest, file="ai_picu_vitals.csv", demo=DEMO, chunksize=1_000_000):
    """The SMH extraction joined each table to the weight records, so every row of an encounter should
    appear as many times as the encounter has rows in the raw demographics file (n). For the rows of
    manifest stays in one table, splits the exact copies into:
      - explained by the join: for each distinct row, min(times it appears, n) - 1;
      - left over: for each distinct row, max(times it appears - n, 0) (identical rows the join does not explain,
        for example the same value written twice in one minute).
    Counts only. The two add up to the exact duplicates removed at assembly."""
    path = _dir(smh_dir) / file
    keep_ids = set(A._norm_key(manifest["encounterId"]).dropna())
    year = dict(zip(A._norm_key(manifest["encounterId"]), pd.to_numeric(manifest["year"], errors="coerce")))
    hs, enc = [], []
    for chunk in A._chunks(path, chunksize):
        col = "encounterId" if "encounterId" in chunk.columns else "encounterID"
        key = A._norm_key(chunk[col])
        ok = key.isin(keep_ids)
        hs.append(A._hash(chunk[ok]))
        enc.append(key[ok].to_numpy())
    df = pd.DataFrame({"h": np.concatenate(hs), "enc": np.concatenate(enc)})
    d = df.groupby(["enc", "h"]).size().rename("times").reset_index()
    dm = A._norm_key(I.read(_dir(smh_dir) / demo, usecols=lambda c: c.lower() == "encounterid")[0].iloc[:, 0])
    n = dm.value_counts()
    d["n"] = d["enc"].map(n).fillna(1).clip(lower=1).astype(int)
    d["explained"] = np.minimum(d["times"], d["n"]) - 1
    d["left_over"] = np.maximum(d["times"] - d["n"], 0)
    total = int(d["explained"].sum() + d["left_over"].sum())
    out = pd.Series({
        "exact copies": total,
        "explained by the join to the weight records": int(d["explained"].sum()),
        "left over": int(d["left_over"].sum()),
        "share explained": round(float(d["explained"].sum() / max(total, 1)), 4),
        "encounters with copies left over": int(d.loc[d["left_over"] > 0, "enc"].nunique()),
        "encounters in the table": int(d["enc"].nunique())}, dtype=object).pipe(_fmt_s).to_frame("count")
    d["year"] = d["enc"].map(year)
    by_year = d.groupby("year")[["explained", "left_over"]].sum().astype("int64")
    by_year["share explained"] = (by_year["explained"] / (by_year["explained"] + by_year["left_over"]).clip(lower=1)).round(3)
    return {"Exact copies, explained and left over": out, "By admission year": by_year}