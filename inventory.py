#!/usr/bin/env python3
"""Inventory the CSV files in a folder: structure, counts, ranges, missingness.
Prints no row-level data. ID-like columns get counts only.

Usage:
  python3 inventory.py <csv_dir> --out <output_dir> [--max-rows N]
"""
import argparse
import re
import warnings
from datetime import date
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

ID_HINT = re.compile(r"id|mrn|nhs|number|episode|admission|patient|spell|key", re.I)
MAX_CAT = 25      # list values when a column has at most this many unique values
MAX_LEN = 40      # ...and the average string length is at most this


def read(path, max_rows):
    for enc in ("utf-8", "latin-1"):
        try:
            df = pd.read_csv(path, low_memory=False, encoding=enc, nrows=max_rows)
            return df, enc
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"cannot decode {path}")


def pattern(v):
    """Shape of a value (digits -> d, letters -> a), so formats show without values."""
    return re.sub(r"[A-Za-z]", "a", re.sub(r"\d", "d", str(v)))


def looks_like_date(s):
    sample = s.dropna().astype(str).head(1000)
    if sample.empty or sample.str.len().median() < 6:
        return False
    return pd.to_datetime(sample, errors="coerce", dayfirst=True).notna().mean() > 0.9


def counts_text(s):
    vc = s.value_counts(dropna=True).head(MAX_CAT)
    return "; ".join(f"{k}: {v}" for k, v in vc.items())


def profile_column(s, name):
    n, nn = len(s), int(s.notna().sum())
    info = {
        "column": name,
        "dtype": str(s.dtype),
        "missing %": round(100 * (1 - nn / n), 1) if n else None,
        "unique": int(s.nunique(dropna=True)),
        "detail": "",
    }
    if nn == 0:
        info["detail"] = "all missing"
    elif pd.api.types.is_bool_dtype(s):
        info["detail"] = counts_text(s)
    elif pd.api.types.is_numeric_dtype(s):
        q = s.quantile([0.01, 0.5, 0.99])
        d = (f"min {s.min():g}; p1 {q[0.01]:g}; median {q[0.5]:g}; "
             f"p99 {q[0.99]:g}; max {s.max():g}")
        if info["unique"] <= 15 and not ID_HINT.search(name):
            d += " | values -> " + counts_text(s)
        info["detail"] = d
    else:
        if looks_like_date(s):
            parsed = pd.to_datetime(s, errors="coerce", dayfirst=True)
            first = s.dropna().iloc[0]
            info["detail"] = (f"datetime {parsed.min()} to {parsed.max()} "
                              f"(parsed day-first); format {pattern(first)}")
        else:
            avg_len = s.dropna().astype(str).str.len().mean()
            if (info["unique"] <= MAX_CAT and avg_len <= MAX_LEN
                    and not ID_HINT.search(name)):
                info["detail"] = counts_text(s)
            else:
                info["detail"] = f"avg length {avg_len:.0f}"
    info["detail"] = str(info["detail"]).replace("|", "/")
    return info


def md_table(rows, cols):
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def inventory_site(csv_dir, max_rows=None):
    """Profile every CSV in csv_dir. Returns a dict of DataFrames and ID sets."""
    files = sorted(Path(csv_dir).expanduser().glob("*.csv"))
    summary, profiles, col_files, id_sets = [], {}, {}, {}
    for f in files:
        df, enc = read(f, max_rows)
        summary.append({
            "file": f.name,
            "size MB": round(f.stat().st_size / 1e6, 1),
            "rows": len(df),
            "columns": df.shape[1],
            "duplicate rows": int(df.duplicated().sum()),
            "encoding": enc,
        })
        profiles[f.name] = pd.DataFrame([profile_column(df[c], c) for c in df.columns])
        for c in df.columns:
            key = c.strip().lower()
            col_files.setdefault(key, {})[f.name] = int(df[c].nunique())
            if ID_HINT.search(c) and df[c].nunique() < 5_000_000:
                id_sets.setdefault(f.name, {})[key] = set(df[c].dropna().unique())
    return {"summary": pd.DataFrame(summary), "profiles": profiles,
            "col_files": col_files, "id_sets": id_sets}


def shared_columns(inv):
    """Columns that appear in more than one file, with unique counts per file."""
    rows = {c: v for c, v in inv["col_files"].items() if len(v) > 1}
    return pd.DataFrame(rows).T.sort_index()


def id_overlap(inv, base="ai_picu_demographics.csv"):
    """Share of each file's unique IDs that also appear in the base file."""
    ids, out = inv["id_sets"], []
    for col, base_ids in ids.get(base, {}).items():
        for fn, cols in ids.items():
            if fn != base and col in cols and cols[col]:
                out.append({"column": col, "file": fn, "unique ids": len(cols[col]),
                            "% in base": round(100 * len(cols[col] & base_ids) / len(cols[col]), 1)})
    return pd.DataFrame(out)


def write_report(inv, site, out_path):
    """Write the Markdown report (same content as the earlier script)."""
    parts = [f"# Inventory: {site}", f"Generated {date.today()}", "",
             "# Files at a glance", "", md_table(inv["summary"].to_dict("records"),
             list(inv["summary"].columns)), ""]
    for fn, prof in inv["profiles"].items():
        parts += [f"## {fn}", "", md_table(prof.to_dict("records"), list(prof.columns)), ""]
    parts += ["## Columns shared between files", "", shared_columns(inv).to_markdown()
              if hasattr(pd.DataFrame, "to_markdown") else shared_columns(inv).to_string(), ""]
    Path(out_path).write_text("\n".join(parts) + "\n")