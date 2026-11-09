"""Inventory the CSV files of one site: structure, counts, ranges, missingness.

Functions for use from a notebook (see inventory.ipynb):

    import inventory as I
    inv = I.inventory_site(csv_dir)          # profile every CSV in a folder
    inv["summary"]                           # one row per file
    inv["profiles"]["some_file.csv"]         # one row per column
    I.shared_columns(inv)                    # columns appearing in several files
    I.id_overlap(inv)                        # ID overlap against the demographics file
    I.write_report(inv, "RBH", out_path)     # Markdown report

No row-level data is returned. ID-like columns get counts only.
"""
import re
import warnings
from datetime import date
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

ID_HINT = re.compile(r"id|mrn|nhs|number|episode|admission|patient|spell|key|_rk", re.I)
MAX_CAT = 40      # list values when a column has at most this many unique values
MAX_LEN = 40      # ...and the average string length is at most this


def read(path, max_rows=None):
    for enc in ("utf-8", "latin-1"):
        try:
            df = pd.read_csv(path, low_memory=False, encoding=enc, nrows=max_rows)
            return df, enc
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"cannot decode {path}")


def pattern(v):
    """Shape of a value (letters -> a, digits -> d), so formats show without values."""
    return re.sub(r"\d", "d", re.sub(r"[A-Za-z]", "a", str(v)))


SAS_FMT = "%d%b%Y:%H:%M:%S.%f"   # e.g. 01JAN2020:12:34:56.78 (SAS datetime)


def parse_dates(s):
    """Parse a string column to datetimes. Returns (parsed Series, name of format used).
    Tries the SAS datetime format first, then generic day-first parsing."""
    sas = pd.to_datetime(s, format=SAS_FMT, errors="coerce")
    if sas.notna().sum() >= 0.9 * s.notna().sum():
        return sas, "SAS datetime DDMONYYYY:HH:MM:SS.ff"
    return pd.to_datetime(s, errors="coerce", dayfirst=True), "generic, day-first"


def looks_like_date(s):
    sample = s.dropna().astype(str).head(1000)
    if sample.empty or sample.str.len().median() < 6:
        return False
    return parse_dates(sample)[0].notna().mean() > 0.9


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
            parsed, how = parse_dates(s)
            first = s.dropna().iloc[0]
            info["detail"] = (f"datetime {parsed.min()} to {parsed.max()} "
                              f"({how}); format {pattern(first)}")
        else:
            avg_len = s.dropna().astype(str).str.len().mean()
            if (info["unique"] <= MAX_CAT and avg_len <= MAX_LEN
                    and not ID_HINT.search(name)):
                info["detail"] = counts_text(s)
            else:
                # show the shape of the first value, e.g. to see unparsed timestamp formats
                info["detail"] = (f"avg length {avg_len:.0f}; "
                                  f"first value shape {pattern(s.dropna().iloc[0])}")
    info["detail"] = str(info["detail"]).replace("|", "/")
    return info


def md_table(rows, cols):
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def df_text(df):
    """DataFrame -> Markdown if `tabulate` is installed, else plain text."""
    try:
        return df.to_markdown()
    except ImportError:
        return df.to_string()


def inventory_site(csv_dir, max_rows=None):
    """Profile every CSV in csv_dir. Returns a dict of DataFrames and ID sets."""
    files = sorted(Path(csv_dir).expanduser().glob("*.csv"))
    summary, profiles, col_files, id_sets = [], {}, {}, {}
    for f in files:
        df, enc = read(f, max_rows)
        print(f"{f.name}: {len(df)} rows x {df.shape[1]} cols")
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


def write_report(inv, site, out_path, base="ai_picu_demographics.csv"):
    """Write the Markdown report."""
    summ = inv["summary"]
    parts = [f"# Inventory: {site}", f"Generated {date.today()}", "",
             "# Files at a glance", "",
             md_table(summ.to_dict("records"), list(summ.columns)), ""]
    for fn, prof in inv["profiles"].items():
        parts += [f"## {fn}", "", md_table(prof.to_dict("records"), list(prof.columns)), ""]
    parts += ["## Columns shared between files", "", df_text(shared_columns(inv)), ""]
    overlap = id_overlap(inv, base)
    if len(overlap):
        parts += [f"## ID overlap with {base}", "", df_text(overlap), ""]
    Path(out_path).write_text("\n".join(parts) + "\n")