"""Inventory the CSV files of one site: structure, counts, ranges, missingness.

Functions for use from a notebook (see inventory.ipynb):

    import inventory as I
    inv = I.inventory_site(csv_dir)          # profile every CSV in a folder
    inv["summary"]                           # one row per file
    inv["profiles"]["some_file.csv"]         # one row per column
    I.shared_columns(inv)                    # columns appearing in several files
    I.id_overlap(inv)                        # ID overlap against the demographics file
    I.write_report(inv, "RBH", out_path)     # Markdown report

Privacy / anonymisation planning:

    inv["dates"]                             # every date/time column: format, range, resolution
    I.identifier_audit(inv)                  # ID-like, name-like, free-text-like, quasi-identifier columns
    I.cross_site_columns({"RBH": rbh, "SMH": smh})   # column names shared by several sites
    (write_report includes both of the first two automatically.)

No row-level data is returned. ID-like columns get counts only.
"""
import re
import warnings
from datetime import date
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

# "ID"/"Id" must stand as a word part (studyID, encounterId, drug_id), so "Tidal" or "Fluid" don't match.
ID_HINT = re.compile(r"(?:^|[a-z_])(?:ID|Id)(?:$|[^a-z])|(?:^|_)id(?:$|_)|(?i:mrn|nhs|number|episode|admission|patient|spell|key|_rk)")
MAX_CAT = 40      # list values when a column has at most this many unique values
MAX_LEN = 40      # ...and the average string length is at most this


def read(path, max_rows=None, usecols=None):
    for enc in ("utf-8", "latin-1"):
        try:
            df = pd.read_csv(path, low_memory=False, encoding=enc, nrows=max_rows,
                             usecols=usecols)
            return df, enc
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"cannot decode {path}")


def pattern(v):
    """Shape of a value (letters -> a, digits -> d), so formats show without values."""
    return re.sub(r"\d", "d", re.sub(r"[A-Za-z]", "a", str(v)))


SAS_FMTS = (("%d%b%Y:%H:%M:%S.%f", "SAS datetime DDMONYYYY:HH:MM:SS.ff"),   # 01JAN2020:12:34:56.78
            ("%d%b%Y:%H:%M:%S", "SAS datetime DDMONYYYY:HH:MM:SS"))          # 01JAN2020:12:34:56


def shapes_of(s):
    """Vectorised `pattern` for a whole string Series."""
    return (s.dropna().astype(str).str.replace(r"[A-Za-z]", "a", regex=True)
             .str.replace(r"\d", "d", regex=True))


def _by_shape(s, max_shapes=10):
    """Parse a column that mixes formats: group the values by shape and parse each group
    on its own (ISO year-first groups as ISO, everything else day-first)."""
    txt = s.dropna().astype(str)
    shp = shapes_of(s)
    if shp.nunique() > max_shapes:
        return pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    parts = []
    for one in shp.unique():
        sub = txt[shp == one]
        if one.startswith("dddd-dd-dd"):
            parts.append(pd.to_datetime(sub, format="ISO8601", errors="coerce"))
        else:
            parts.append(pd.to_datetime(sub, dayfirst=True, errors="coerce"))
    return pd.concat(parts).reindex(s.index)


def parse_dates(s):
    """Parse a string column to datetimes. Returns (parsed Series, name of format used).
    Order: SAS datetime formats, ISO 8601 (YYYY-MM-DD ...), generic day-first (dd/mm/yyyy),
    then a per-shape fallback for columns that mix formats.
    ISO is tried before day-first on purpose: pandas with dayfirst=True can guess
    YYYY-DD-MM from an ambiguous first value and then fail on most of the column."""
    n = s.notna().sum()
    for fmt, name in SAS_FMTS:
        parsed = pd.to_datetime(s, format=fmt, errors="coerce")
        if parsed.notna().sum() >= 0.9 * n:
            return parsed, name
    parsed = pd.to_datetime(s, format="ISO8601", errors="coerce")
    if parsed.notna().sum() >= 0.9 * n:
        return parsed, "ISO 8601 (year first)"
    parsed = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if parsed.notna().sum() >= 0.9 * n:
        return parsed, "generic, day-first"
    mixed = _by_shape(s)
    if mixed.notna().sum() >= 0.9 * n:
        return mixed, "mixed formats, parsed per shape (ISO or day-first)"
    return parsed, "generic, day-first"


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


def df_text(df, index=True):
    """DataFrame -> Markdown if `tabulate` is installed, else plain text."""
    try:
        return df.to_markdown(index=index)
    except ImportError:
        return df.to_string(index=index)


def inventory_site(csv_dir, max_rows=None):
    """Profile every CSV in csv_dir. Returns a dict of DataFrames and ID sets."""
    files = sorted(Path(csv_dir).expanduser().glob("*.csv"))
    summary, profiles, col_files, id_sets, date_rows = [], {}, {}, {}, []
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
        details = dict(zip(profiles[f.name]["column"], profiles[f.name]["detail"]))
        date_rows += [date_row(f.name, c, df[c]) for c in df.columns if _is_date_col(c, details[c])]
        for c in df.columns:
            key = c.strip().lower()
            col_files.setdefault(key, {})[f.name] = int(df[c].nunique())
            if ID_HINT.search(c) and df[c].nunique() < 5_000_000:
                id_sets.setdefault(f.name, {})[key] = set(df[c].dropna().unique())
    return {"summary": pd.DataFrame(summary), "profiles": profiles,
            "col_files": col_files, "id_sets": id_sets,
            "dates": pd.DataFrame(date_rows), "csv_dir": str(csv_dir)}


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


DATE_NAME = re.compile(r"date|time|dttm|dob|birth", re.I)
DIRECT_NAME = re.compile(r"name|nhs|mrn|hospital.?n|dob|birth|post.?code|address|phone|email|surname", re.I)
# "age" only at the start of a word (Age, AgeDays, Age_mth), so "Dosage" is not flagged
QUASI_NAME = re.compile(r"(?<![a-z])[Aa]ge|(?i:sex|gender|ethnic|weight|diagnos|death|deceased|died)")
TEXT_NAME = re.compile(r"other|desc|note|comment|text|reason", re.I)


def _is_date_col(name, detail):
    """A column counts as a date if the profile parsed it as one, or its name suggests it."""
    return str(detail).startswith("datetime") or bool(DATE_NAME.search(name))


def date_row(fn, col, s):
    """Format, parsed range, resolution and calendar span of one date/time column (aggregates only)."""
    nn = s.dropna()
    row = {"file": fn, "column": col, "dtype": str(s.dtype), "non-missing": len(nn)}
    if len(nn) == 0 or pd.api.types.is_numeric_dtype(s):
        row["note"] = "all missing" if len(nn) == 0 else "numeric, not parsed as a date"
        return row
    shape = pattern(nn.iloc[0])
    if re.fullmatch(r"d{1,2}:dd(:dd)?", shape):
        row.update({"format": shape, "note": "time of day only (no date)"})
        return row
    parsed, how = parse_dates(s)
    p = parsed.dropna()
    if len(p) < 0.9 * len(nn):
        seen = shapes_of(s).value_counts().head(4)
        row.update({"format": shape, "unparsed %": round(100 * (1 - len(p) / len(nn)), 1),
                    "note": "could not be parsed as dates; shapes seen: "
                            + "; ".join(f"{k} x{v}" for k, v in seen.items())})
        return row
    notes = []
    if re.match(r"dd/dd/dddd", shape):
        f = nn.str.extract(r"^(\d+)/(\d+)/")
        a, b = pd.to_numeric(f[0], errors="coerce").max(), pd.to_numeric(f[1], errors="coerce").max()
        notes.append(f"1st field max {a:g}, 2nd max {b:g}" + (" -> MONTH-FIRST?" if b > 12 else " (day-first OK)"))
    if len(p) < len(nn):
        row["unparsed %"] = round(100 * (1 - len(p) / len(nn)), 1)
    has_time = (p.dt.normalize() != p).mean()
    has_sec = (p.dt.second != 0).mean()
    span = p
    dummy = p.dt.year <= 1900
    if dummy.mean() >= 0.5:      # time of day exported as a date-time with a placeholder date
        span = p[~dummy]
        notes.append(f"time of day with placeholder date 1900-01-01 ({dummy.mean():.0%} of rows); "
                     f"{len(span)} rows carry a real date, summarised below")
    row.update({
        "format": pattern(nn.iloc[0]), "parsed as": how,
        "earliest": span.min(), "latest": span.max(),
        "calendar years": span.dt.year.nunique(),
        "distinct days": span.dt.normalize().nunique(),
        "resolution": "second" if has_sec > 0 else "minute" if has_time > 0 else "date only",
    })
    if notes:
        row["note"] = "; ".join(notes)
    return row


def date_audit(inv, csv_dir=None):
    """One row per date/time column. Collected by inventory_site, so this just returns
    inv["dates"]. For an inventory made before that existed, it re-reads only the date
    columns from csv_dir (pass the folder; newer inventories remember it)."""
    if "dates" in inv:
        return inv["dates"]
    csv_dir = csv_dir or inv.get("csv_dir")
    rows = []
    for fn, prof in inv["profiles"].items():
        cols = [r["column"] for _, r in prof.iterrows() if _is_date_col(r["column"], r["detail"])]
        if not cols:
            continue
        df, _ = read(Path(csv_dir).expanduser() / fn, usecols=cols)
        rows += [date_row(fn, c, df[c]) for c in cols]
    return pd.DataFrame(rows)


def identifier_audit(inv):
    """Columns that could identify a child or be used to link records: ID-like keys,
    name/NHS/DOB-style column names, free-text-like strings, quasi-identifiers
    (age, sex, ethnicity, weight, diagnosis) and date/time columns."""
    rows_per_file = inv["summary"].set_index("file")["rows"]
    out = []
    for fn, prof in inv["profiles"].items():
        n = int(rows_per_file[fn])
        for _, r in prof.iterrows():
            col, flags = r["column"], []
            non_missing = n * (1 - (r["missing %"] or 0) / 100)
            m = re.search(r"avg length (\d+)", str(r["detail"]))
            avg_len = int(m.group(1)) if m else None
            if DIRECT_NAME.search(col):
                flags.append("direct-identifier name")
            if ID_HINT.search(col) and r["unique"] > 1 and r["unique"] >= 0.001 * max(non_missing, 1):
                flags.append("ID-like")
            if ("ID-like" not in flags and r["dtype"] in ("str", "object")
                    and avg_len is not None and r["unique"] > 50
                    and (avg_len >= 20 or TEXT_NAME.search(col))):
                flags.append("free text?")
            if QUASI_NAME.search(col):
                flags.append("quasi-identifier")
            if str(r["detail"]).startswith("datetime") or DATE_NAME.search(col):
                flags.append("date/time")
            if flags:
                out.append({"file": fn, "column": col, "dtype": r["dtype"], "unique": r["unique"],
                            "unique % of rows": round(100 * r["unique"] / n, 3) if n else None,
                            "flags": ", ".join(flags)})
    return pd.DataFrame(out)


def cross_site_columns(invs):
    """Column names (case-insensitive) that appear at more than one site.
    invs = {"RBH": rbh_inventory, "SMH": smh_inventory, ...}; cells = number of files with the column."""
    names = {}
    for site, inv in invs.items():
        for fn, prof in inv["profiles"].items():
            for c in prof["column"]:
                names.setdefault(c.strip().lower(), {}).setdefault(site, []).append(fn)
    rows = [{"column": c, **{s: len(v.get(s, [])) for s in invs}} for c, v in names.items()]
    df = pd.DataFrame(rows).set_index("column").sort_index()
    return df[(df > 0).sum(axis=1) > 1]


def write_report(inv, site, out_path, base="ai_picu_demographics.csv", dates=None):
    """Write the Markdown report, including the identifier flags and the date audit."""
    if dates is None:
        dates = inv.get("dates")
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
    flags = identifier_audit(inv)
    if len(flags):
        parts += ["## Identifier and privacy flags", "", df_text(flags, index=False), ""]
    if dates is not None and len(dates):
        parts += ["## Date and time columns", "", df_text(dates, index=False), ""]
    Path(out_path).write_text("\n".join(parts) + "\n")