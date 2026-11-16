"""Assemble the eligible tables for one site: keep only rows of manifest stays, drop exact
duplicate rows, write one parquet file per source table.

Nothing is dropped except (a) rows of stays that are not in the manifest and (b) rows that are
exact duplicates of an earlier row. All columns and values are kept. Every column is written as
text, exactly as in the source, so nothing is re-typed or re-formatted at this stage.
Anonymisation (keys, times, free text, small cells) is a later module.

Linking:
  RBH   studyID -> stay key (prefix NIC/NND removed). The kept studyID column is replaced by
        `stay_key`; rows that differ only in the prefix are merged (counted separately).
  SMH   encounterId (encounterID in the medication files).
  GOSH  project_id + time: a row belongs to the manifest stay of that patient whose window
        (admission start - pre_hours to discharge) contains the row's time. `stay_id` is added.
        Tables with no project_id or no recognised time column are skipped and listed.

Notebook use:
    import assemble as A
    A.list_tables("GOSH", gosh_dir)                      # preview, reads only headers
    log = A.assemble_site("GOSH", gosh_dir, derived/"assembled", gosh_m)
    log                                                   # counts only
Reruns skip tables whose output exists unless overwrite=True.
"""
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import inventory as I
import manifest as M

DEFAULT_EXCLUDE = {
    "RBH": r"piccanet_old",
    "SMH": r"ai_picu_medications\.csv$|ai_picu_medications_furosemide\.csv$",   # v2 = both combined
    "GOSH": r"lab_components|Archived|raw_lab_values|PICANet|processing|\.ipynb_checkpoints",
}
GOSH_TIME_COLS = ["observation_datetime", "hour_start"]   # tried in this order; override per table with time_cols


# ---------------------------------------------------------------- reading
def _encoding(path):
    try:
        with open(path, encoding="utf-8") as f:
            f.read(1_000_000)
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def _chunks(path, chunksize):
    """CSV as text in chunks. Empty fields become missing; everything else is kept verbatim."""
    return pd.read_csv(path, dtype=str, chunksize=chunksize, encoding=_encoding(path),
                       keep_default_na=False, na_values=[""], low_memory=False)


def _norm_key(s):
    """IDs as comparable text: numeric-looking IDs lose any '.0'; others are stripped."""
    s = s.astype("string").str.strip()
    num = pd.to_numeric(s, errors="coerce")
    if s.notna().sum() and num.notna().sum() == s.notna().sum():
        return num.astype("Int64").astype("string")
    return s


# ---------------------------------------------------------------- what to process
def _files(site, src_dir, include=None, exclude=None):
    src = Path(src_dir).expanduser()
    exclude = DEFAULT_EXCLUDE.get(site.upper(), "") if exclude is None else exclude
    it = src.rglob("*.csv") if site.upper() == "GOSH" else src.glob("*.csv")
    out = []
    for p in sorted(it):
        rel = p.relative_to(src).as_posix()
        if include and not re.search(include, rel):
            continue
        if exclude and re.search(exclude, rel, re.I):
            continue
        out.append((rel, p))
    return out


def _key_columns(site, cols, tcol=None):
    """(key description, usable?) for a table's header. tcol: a GOSH time column chosen by name."""
    site = site.upper()
    if site == "RBH":
        return "studyID", "studyID" in cols
    if site == "SMH":
        k = "encounterId" if "encounterId" in cols else "encounterID"
        return k, k in cols
    t = [tcol] if tcol in cols else [c for c in GOSH_TIME_COLS if c in cols]
    return f"project_id + {t[0] if t else '(no time column)'}", "project_id" in cols and bool(t)


def _tcol(cols, rel, time_cols):
    """The GOSH time column for one table: named in time_cols, else the first default found."""
    c = (time_cols or {}).get(rel)
    return c if c in cols else next((c for c in GOSH_TIME_COLS if c in cols), None)


def list_tables(site, src_dir, include=None, exclude=None, time_cols=None):
    """Preview: which tables would be assembled, and which cannot be linked to a stay."""
    rows = []
    for rel, p in _files(site, src_dir, include, exclude):
        cols = list(pd.read_csv(p, nrows=0, encoding=_encoding(p)).columns)
        key, ok = _key_columns(site, cols, _tcol(cols, rel, time_cols))
        rows.append({"table": rel, "size MB": round(p.stat().st_size / 1e6, 1), "key": key,
                     "linkable": ok, "columns": len(cols)})
    df = pd.DataFrame(rows)
    print(I.df_text(df, index=False))
    return df


# ---------------------------------------------------------------- row filters
def _make_filter(site, manifest, gosh_pre_hours):
    site = site.upper()
    if site == "RBH":
        keep = set(manifest["stay_key"])

        def f(df, tc=None):
            key = M.rbh_stay_key(df["studyID"])
            out = df[key.isin(keep)].copy()
            out.insert(0, "stay_key", key[out.index])
            return out
        return f
    if site == "SMH":
        keep = set(_norm_key(manifest["encounterId"]).dropna())

        def f(df, tc=None):
            col = "encounterId" if "encounterId" in df.columns else "encounterID"
            return df[_norm_key(df[col]).isin(keep)]
        return f

    def f(df, tc):
        return M.gosh_eligible_rows(df, manifest, time_col=tc, pre_hours=gosh_pre_hours)
    return f


def _hash(df):
    return pd.util.hash_pandas_object(df, index=False).to_numpy()


def _new(h, seen):
    """Mask of rows whose hash is neither repeated within this chunk nor already seen."""
    first = ~pd.Series(h).duplicated().to_numpy()
    return first & ~np.isin(h, seen)


# ---------------------------------------------------------------- one table
def _assemble_table(site, rel, path, out_path, flt, chunksize, tcol=None):
    t0 = time.time()
    n_in = n_elig = n_exact = n_prefix = n_out = 0
    seen_o = np.empty(0, dtype=np.uint64)
    seen_n = np.empty(0, dtype=np.uint64)
    writer, schema = None, None
    for chunk in _chunks(path, chunksize):
        n_in += len(chunk)
        sub = flt(chunk, tcol)
        n_elig += len(sub)
        if sub.empty:
            continue
        if site.upper() == "RBH":
            norm = sub.drop(columns=["studyID"])
            sub_out = norm
            h_o = _hash(sub.drop(columns=["stay_key"]))
            h_n = _hash(norm)
        else:
            sub_out = sub
            h_o = h_n = _hash(sub)
        new_o = _new(h_o, seen_o)
        new_n = _new(h_n, seen_n) if site.upper() == "RBH" else new_o
        n_exact += int((~new_o).sum())
        n_prefix += int((~new_n & new_o).sum())
        seen_o = np.concatenate([seen_o, h_o[new_o]])
        if site.upper() == "RBH":
            seen_n = np.concatenate([seen_n, h_n[new_n]])
        keep = sub_out[new_n]
        n_out += len(keep)
        if schema is None:
            schema = pa.schema([(c, pa.string()) for c in keep.columns])
            writer = pq.ParquetWriter(out_path, schema)
        if len(keep):
            writer.write_table(pa.Table.from_pandas(keep[list(schema.names)], schema=schema,
                                                    preserve_index=False))
    if writer is not None:
        writer.close()
    return {"table": rel, "rows read": n_in, "in manifest stays": n_elig,
            "exact duplicates removed": n_exact, "merged (prefix only)": n_prefix,
            "rows written": n_out, "seconds": round(time.time() - t0)}


def _assemble_gosh_picanet(src_dir, out_dir, manifest, picanet):
    path = Path(src_dir).expanduser() / picanet
    df = pd.read_csv(path, dtype=str, encoding=_encoding(path), keep_default_na=False, na_values=[""])
    df["picanet_row"] = df.index
    keep = df.merge(manifest[["picanet_row", "stay_id"]], on="picanet_row", how="inner")
    keep = keep.drop(columns=["picanet_row"]).astype("string")
    out = Path(out_dir) / "GOSH" / "PICANet_eprweights.parquet"
    keep.to_parquet(out, index=False)
    return {"table": picanet, "rows read": len(df), "in manifest stays": len(keep),
            "exact duplicates removed": 0, "merged (prefix only)": 0, "rows written": len(keep), "seconds": 0}


# ---------------------------------------------------------------- one site
def assemble_site(site, src_dir, out_dir, manifest, include=None, exclude=None,
                  chunksize=1_000_000, overwrite=False, gosh_pre_hours=0,
                  gosh_picanet=M.GOSH_PICANET, time_cols=None):
    """Assemble every linkable table of one site. Returns a counts-only log (also printed).
    out_dir/<SITE>/<table path with '/' as '__'>.parquet. Row-level: keep out_dir in derived/.
    time_cols (GOSH): {relative table path: time column} for tables whose time column is not one
    of the defaults, e.g. {"merged_balance/Net_Bal.csv": "<column>"}."""
    site = site.upper()
    out = Path(out_dir) / site
    out.mkdir(parents=True, exist_ok=True)
    flt = _make_filter(site, manifest, gosh_pre_hours)
    log, skipped = [], []
    if site == "GOSH":
        log.append(_assemble_gosh_picanet(src_dir, out_dir, manifest, gosh_picanet))
    for rel, path in _files(site, src_dir, include, exclude):
        cols = list(pd.read_csv(path, nrows=0, encoding=_encoding(path)).columns)
        tcol = _tcol(cols, rel, time_cols) if site == "GOSH" else None
        key, ok = _key_columns(site, cols, tcol)
        if not ok:
            skipped.append((rel, key))
            continue
        out_path = out / (rel.replace("/", "__").removesuffix(".csv") + ".parquet")
        if out_path.exists() and not overwrite:
            print(f"skip (exists): {rel}")
            continue
        row = _assemble_table(site, rel, path, out_path, flt, chunksize, tcol)
        log.append(row)
        print(f"{rel}: read {row['rows read']:,}, in stays {row['in manifest stays']:,}, "
              f"duplicates {row['exact duplicates removed']:,}, written {row['rows written']:,} "
              f"({row['seconds']} s)")
    df = pd.DataFrame(log)
    if skipped:
        print("\nNot assembled (no usable key):")
        for rel, key in skipped:
            print(f"  {rel}  (needs {key})")
    return df


def time_candidates(site, src_dir, include=None, exclude=None, time_cols=None, n=2000):
    """For tables that cannot be linked yet: print every column whose name looks like a date or
    time, with the shape of its values (letters -> a, digits -> d). No values are printed."""
    for rel, p in _files(site, src_dir, include, exclude):
        cols = list(pd.read_csv(p, nrows=0, encoding=_encoding(p)).columns)
        if _key_columns(site, cols, _tcol(cols, rel, time_cols))[1]:
            continue
        df = pd.read_csv(p, nrows=n, dtype=str, encoding=_encoding(p))
        print(f"{rel}  ({len(cols)} columns; project_id: {'project_id' in cols})")
        found = [c for c in cols if I.DATE_NAME.search(c)]
        for c in found:
            vc = I.shapes_of(df[c]).value_counts()
            print(f"    {c}: " + "; ".join(f"{k} ({v})" for k, v in vc.head(3).items()))
        if not found:
            print("    no column name looks like a date or time; columns: " + ", ".join(cols))


def time_column_check(src_dir, rel, columns, n=500_000):
    """Counts only: how do several time columns of one table relate? For each column: share parsed,
    range, and share of patients with a single value (a per-admission constant, not a row time);
    for each pair: share of rows equal to the minute."""
    path = Path(src_dir).expanduser() / rel
    df = pd.read_csv(path, nrows=n, dtype=str, encoding=_encoding(path), keep_default_na=False, na_values=[""])
    print(f"{rel}: {len(df):,} rows sampled")
    missing = [c for c in columns if c not in df.columns]
    columns = [c for c in columns if c in df.columns]
    if missing:
        print(f"  not in this table: {missing}")
        print("  date-like columns here: " + (", ".join(c for c in df.columns if I.DATE_NAME.search(c)) or "none by name")
              + f"\n  all columns: {list(df.columns)}")
    if not columns:
        return
    t = {c: I.parse_dates(df[c])[0].dt.floor("min") for c in columns}
    for c in columns:
        x = t[c]
        per_pt = x.groupby(df["project_id"]).nunique()
        print(f"  {c}: parsed {100*x.notna().mean():.1f}%; {x.min()} to {x.max()}; "
              f"patients with one distinct value: {100*(per_pt <= 1).mean():.1f}%")
    for i, a in enumerate(columns):
        for b in columns[i + 1:]:
            ok = t[a].notna() & t[b].notna()
            print(f"  {a} == {b}: {100*(t[a][ok] == t[b][ok]).mean():.1f}% of {int(ok.sum()):,} rows")


def summarise_log(log, top=8):
    """Compact view of an assembly log: totals, tables with duplicates removed, and the tables that
    keep the smallest share of their rows. Counts only."""
    d = log.copy()
    d["% kept in stays"] = (100 * d["in manifest stays"] / d["rows read"].clip(lower=1)).round(1)
    print(f"{len(d)} tables; rows read {int(d['rows read'].sum()):,}; in manifest stays "
          f"{int(d['in manifest stays'].sum()):,}; exact duplicates removed {int(d['exact duplicates removed'].sum()):,}; "
          f"merged by prefix {int(d['merged (prefix only)'].sum()):,}; rows written {int(d['rows written'].sum()):,}")
    dup = d[(d["exact duplicates removed"] > 0) | (d["merged (prefix only)"] > 0)].sort_values(
        ["exact duplicates removed", "merged (prefix only)"], ascending=False)
    print(f"\nTables with duplicates or prefix merges: {len(dup)}")
    if len(dup):
        print(I.df_text(dup[["table", "rows read", "exact duplicates removed", "merged (prefix only)", "rows written"]], index=False))
    print(f"\nLowest share of rows in stays (top {top}):")
    print(I.df_text(d.sort_values("% kept in stays")[["table", "rows read", "in manifest stays", "% kept in stays"]].head(top), index=False))
    return d


def per_stay_conflicts(parquet_path, key):
    """For one assembled table: rows per stay, and which columns take different values between the
    rows of the same stay. Counts only. key: 'stay_key' (RBH), 'encounterId'/'encounterID' (SMH),
    'stay_id' (GOSH)."""
    df = pd.read_parquet(parquet_path)
    n = df.groupby(key).size()
    print(f"{Path(parquet_path).name}: {len(df):,} rows, {len(n):,} stays")
    print("  rows per stay: " + "; ".join(f"{k}: {v}" for k, v in
          n.clip(upper=4).astype(str).replace({"4": "4+"}).value_counts().sort_index().items()))
    multi = n[n > 1].index
    if len(multi) == 0:
        return
    sub = df[df[key].isin(multi)]
    rows = []
    for c in df.columns:
        if c == key:
            continue
        k = int((sub.groupby(key)[c].nunique(dropna=True) > 1).sum())
        if k:
            rows.append({"column": c, "stays where it differs": k})
    print(f"  stays with more than one row: {len(multi):,}; columns that differ between their rows:")
    print(I.df_text(pd.DataFrame(rows).sort_values("stays where it differs", ascending=False), index=False)
          if rows else "  none (rows differ only in missing values)")