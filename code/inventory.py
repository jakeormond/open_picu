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

Step 1 findings (what later steps must be told; counts and column names only):

    by_year = I.rows_by_year(inv)                 # rows per file per calendar year
    I.find_gaps(by_year)                          # years far below the file's usual level (era changes, outages)
    I.key_table(inv)                              # candidate key columns per file
    I.lookalike_files(inv)                        # old/new/merged copies of the same table (screening list)
    paths = I.finalise(inv, "RBH", reports_dir, base="ai_picu_demographics.csv",
                       rejected={"ai_picu_piccanet_old.csv": "reason"}, by_year=by_year)
    cf = I.load_carried_forward(paths["carried_forward"])
    I.check_columns(cf, frame.columns)            # later steps: free-text/direct-identifier names still present?

No row-level data is returned. ID-like columns get counts only.
"""
import difflib
import itertools
import json
import re
import time
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
    """Read a CSV (utf-8, else latin-1) or a parquet file. Returns (DataFrame, encoding)."""
    if str(path).lower().endswith(".parquet"):
        df = pd.read_parquet(path, columns=usecols)
        return (df.head(max_rows) if max_rows else df), "parquet"
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
    if pd.api.types.is_datetime64_any_dtype(s):      # e.g. from a parquet file
        return s, "native datetime"
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


def list_files(folder):
    """Every file under folder, any depth and any format: path (relative), type, size, depth.
    Use it first on a new site, to see what is there before profiling."""
    root = Path(folder).expanduser()
    rows = [{"path": p.relative_to(root).as_posix(), "type": p.suffix.lower() or "(none)",
             "size MB": round(p.stat().st_size / 1e6, 1), "depth": len(p.relative_to(root).parts) - 1}
            for p in sorted(root.rglob("*")) if p.is_file()]
    return pd.DataFrame(rows)


def _inventory_file(args):
    """Profile one file (worker for inventory_site; top-level so it can run in a subprocess)."""
    f, root, max_rows = args
    t0 = time.time()
    name = Path(f).relative_to(root).as_posix()
    df, enc = read(f, max_rows)
    summary = {"file": name, "size MB": round(Path(f).stat().st_size / 1e6, 1), "rows": len(df),
               "columns": df.shape[1], "duplicate rows": int(df.duplicated().sum()), "encoding": enc}
    prof = pd.DataFrame([profile_column(df[c], c) for c in df.columns])
    details = dict(zip(prof["column"], prof["detail"]))
    uniq = dict(zip(prof["column"], prof["unique"]))            # nunique once, reused below
    dates = [date_row(name, c, df[c]) for c in df.columns if _is_date_col(c, details[c])]
    col_files, ids = {}, {}
    for c in df.columns:
        key = c.strip().lower()
        col_files[key] = uniq[c]
        if ID_HINT.search(c) and uniq[c] < 5_000_000:
            ids[key] = set(df[c].dropna().unique())
    summary["seconds"] = round(time.time() - t0)
    return name, summary, prof, dates, col_files, ids


def inventory_site(csv_dir, max_rows=None, recursive=False, exclude=None, n_jobs=1):
    """Profile every CSV (and parquet) in csv_dir. Returns a dict of DataFrames and ID sets.
    recursive=True also takes files in subfolders; files are then named by their path
    relative to csv_dir (e.g. "sub/inner/file.csv"), and that name is the key everywhere
    (profiles, id_sets, `base=` arguments).
    exclude: regex on the relative path; matching files are skipped (e.g. r"lab_components").
    n_jobs: files profiled in parallel processes. Each worker holds one whole file in
    memory, so keep n_jobs small when there are multi-GB files.
    inv["summary"] has a `seconds` column, to see which files dominate the run time."""
    root = Path(csv_dir).expanduser()
    files = sorted(p for p in (root.rglob("*") if recursive else root.glob("*"))
                   if p.is_file() and p.suffix.lower() in (".csv", ".parquet")
                   and ".ipynb_checkpoints" not in p.parts
                   and not (exclude and re.search(exclude, p.relative_to(root).as_posix())))
    jobs = [(f, root, max_rows) for f in files]
    if n_jobs > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=n_jobs) as ex:
            results = []
            for r in ex.map(_inventory_file, jobs):
                print(f"{r[0]}: {r[1]['rows']} rows x {r[1]['columns']} cols ({r[1]['seconds']} s)")
                results.append(r)
    else:
        results = []
        for j in jobs:
            r = _inventory_file(j)
            print(f"{r[0]}: {r[1]['rows']} rows x {r[1]['columns']} cols ({r[1]['seconds']} s)")
            results.append(r)
    summary, profiles, col_files, id_sets, date_rows = [], {}, {}, {}, []
    for name, s, prof, dates, cf, ids in results:
        summary.append(s)
        profiles[name] = prof
        date_rows += dates
        for key, n in cf.items():
            col_files.setdefault(key, {})[name] = n
        if ids:
            id_sets[name] = ids
    return {"summary": pd.DataFrame(summary), "profiles": profiles,
            "col_files": col_files, "id_sets": id_sets,
            "dates": pd.DataFrame(date_rows), "csv_dir": str(csv_dir)}


def save_inventory(inv, path):
    """Pickle an inventory so it need not be rerun. It contains the ID values themselves
    (id_sets), so it is row-level data: save it only in the git-ignored derived/ folder."""
    import pickle
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump(inv, fh)


def load_inventory(path):
    import pickle
    with open(path, "rb") as fh:
        return pickle.load(fh)


def schema_groups(inv):
    """Group files that have exactly the same columns (one CSV per variable is common).
    One row per group: the columns, number of files, total rows, folders, and a first
    file to look at in inv["profiles"]. Far shorter to read than 100+ profiles."""
    rows_per = inv["summary"].set_index("file")["rows"]
    groups = {}
    for fn, prof in inv["profiles"].items():
        groups.setdefault(tuple(prof["column"]), []).append(fn)
    out = []
    for cols, fns in groups.items():
        out.append({"columns": ", ".join(cols), "n files": len(fns),
                    "total rows": int(rows_per[fns].sum()),
                    "folders": ", ".join(sorted({fn.rsplit("/", 1)[0] if "/" in fn else "(top)" for fn in fns})),
                    "first file": fns[0]})
    return pd.DataFrame(out).sort_values("n files", ascending=False).reset_index(drop=True)


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
# A name column must be a person's name (patient_name, FirstName), not any column containing "name"
# (drug_name, TemplateName, "Unnamed: 0"); "dob" must stand alone, so DOBUTAMINE is not flagged.
DIRECT_NAME = re.compile(r"(?<![a-z])(?:patient|first|last|sur|given|full|family|fore|mother|father|parent)_?name"
                         r"|nhs|mrn|hospital.?n|(?<![a-z])dob(?![a-z])|birth|post.?code|address|phone|email", re.I)
# "age" only at the start of a word (Age, AgeDays, Age_mth), so "Dosage" is not flagged
QUASI_NAME = re.compile(r"(?<![a-z])[Aa]ge|(?i:sex|gender|ethnic|weight|diagnos|death|deceased|died)")
TEXT_NAME = re.compile(r"other|desc|note|comment|text|reason", re.I)
# Quasi-identifiers that the final threat model (PRIVACY_THREAT_MODEL.md) uses: sex, age, weight, diagnosis
# group, outcome. Ethnicity is also flagged but is not released in Tier 2.
USED_QUASI = re.compile(r"(?<![a-z])[Aa]ge|(?i:sex|gender|weight|diagnos|death|deceased|died)")


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
                flags.append("quasi-identifier (in threat model)" if USED_QUASI.search(col)
                             else "quasi-identifier (not in threat model)")
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


def write_report(inv, site, out_path, base="ai_picu_demographics.csv", dates=None, findings=None):
    """Write the Markdown report, including the identifier flags and the date audit.
    findings: Markdown from findings_text(), placed at the top."""
    if dates is None:
        dates = inv.get("dates")
    summ = inv["summary"]
    parts = [f"# Inventory: {site}", f"Generated {date.today()}", "",
             *([findings, ""] if findings else []),
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



# ---------------------------------------------------------------------------
# Step 1 findings: what the later steps must be told
# ---------------------------------------------------------------------------

def key_table(inv):
    """Candidate key columns: every ID-like column in every file, with its unique count, missing
    share, and whether it is unique per row. One row per (file, column). Lists the keys a site
    offers, so a link that needs a special key (GOSH project_id) is visible at step 1."""
    rows_per = inv["summary"].set_index("file")["rows"]
    out = []
    for fn, prof in inv["profiles"].items():
        n = int(rows_per[fn])
        for _, r in prof.iterrows():
            if ID_HINT.search(r["column"]) and r["unique"] > 1:
                non_missing = n * (1 - (r["missing %"] or 0) / 100)
                out.append({"file": fn, "column": r["column"], "unique": r["unique"],
                            "missing %": r["missing %"],
                            "unique per row": bool(non_missing and r["unique"] >= 0.999 * non_missing)})
    return pd.DataFrame(out)


def rows_by_year(inv, csv_dir=None, min_year=1990):
    """Rows per calendar year for each file, by its main time column (the parsed date column with
    distinct timestamps, so a measurement time (hundreds of thousands of values) beats a stay-level time
    such as WARD_IN that repeats on every row of a stay; time-of-day-only and placeholder-date columns are skipped). Reads one column per
    file. Returns a table: rows = (file, column), columns = years. A file whose rows collapse after
    some date (a system changeover) shows here."""
    csv_dir = Path(csv_dir or inv["csv_dir"]).expanduser()
    d = inv["dates"]
    if "earliest" not in d:
        return pd.DataFrame()
    d = d[d["earliest"].notna()]
    if "note" in d:
        d = d[~d["note"].fillna("").str.contains("placeholder|time of day")]
    out = []
    for fn, g in d.groupby("file"):
        uniq = dict(zip(inv["profiles"][fn]["column"], inv["profiles"][fn]["unique"]))
        col = max(g["column"], key=lambda c: uniq.get(c, 0))
        df, _ = read(csv_dir / fn, usecols=[col])
        p = parse_dates(df[col])[0].dropna()
        for y, n in p[p.dt.year >= min_year].dt.year.value_counts().items():
            out.append({"file": fn, "column": col, "year": int(y), "rows": int(n)})
    if not out:
        return pd.DataFrame()
    return (pd.DataFrame(out).pivot_table(index=["file", "column"], columns="year",
                                          values="rows", fill_value=0).sort_index())


def find_gaps(by_year, frac=0.5, min_rows=1000, rise=1.5):
    """Years, strictly inside a file's first and last year, with fewer than `frac` of the file's
    median yearly rows (a drop) or more than `rise` times it (a rise: a new system charting more often).
    The first and last years are partial and are not tested. Flags are
    leads to explain (an Epic go-live, a pandemic year, an outage), not errors."""
    out = []
    for (fn, col), r in by_year.iterrows():
        nz = r[r > 0]
        if len(nz) < 3 or nz.median() < min_rows:
            continue
        typical = nz.median()
        for y, n in r.loc[nz.index.min():nz.index.max()].items():
            if y in (nz.index.min(), nz.index.max()):
                continue
            if n < frac * typical or n > rise * typical:
                out.append({"file": fn, "column": col, "year": y, "rows": int(n),
                            "typical": int(typical), "share of typical": round(n / typical, 2),
                            "change": "drop" if n < typical else "rise"})
    return pd.DataFrame(out)


NOISE = re.compile(r"(?:^|_)(?:old|new|archived?|copy|backup|final|v\d+|merged|flowsheet|rows|lab|variables?)(?=_|$)")


def _stem(fn):
    s = re.sub(NOISE, "", Path(fn).stem.lower())
    return re.sub(r"_+", "_", s).strip("_")


def _id_share(inv, a, b):
    """Largest share, over ID columns the two files have in common, of the smaller file's IDs found in the other."""
    A, B = inv["id_sets"].get(a, {}), inv["id_sets"].get(b, {})
    best = 0.0
    for c in set(A) & set(B):
        if A[c] and B[c]:
            best = max(best, len(A[c] & B[c]) / min(len(A[c]), len(B[c])))
    return best


def lookalike_files(inv, min_jaccard=0.3, min_id_overlap=0.9, min_row_ratio=0.8, family=2):
    """Screening list of pairs of files that may be copies or versions of the same table:
      (a) same name apart from old/new/merged/archive labels, with at least half the columns shared; or
      (b) similar columns, nearly the same IDs and similar row counts, where neither file belongs to
          a larger family of files with identical columns (one-file-per-variable exports are families).
    Candidates to settle at step 2 (which file is right), not a verdict."""
    cols = {fn: {c.strip().lower() for c in p["column"]} for fn, p in inv["profiles"].items()}
    rows = inv["summary"].set_index("file")["rows"]
    fam = {}
    for p_fn, p in inv["profiles"].items():
        fam.setdefault(tuple(p["column"]), []).append(p_fn)
    fam = {fn: len(v) for v in fam.values() for fn in v}
    out = []
    for a, b in itertools.combinations(sorted(cols), 2):
        jac = len(cols[a] & cols[b]) / len(cols[a] | cols[b])
        ratio = min(rows[a], rows[b]) / max(rows[a], rows[b]) if max(rows[a], rows[b]) else 0
        share = _id_share(inv, a, b)
        if _stem(a) == _stem(b) and jac >= 0.5:
            why = "same name apart from old/new/merged labels"
        elif (jac >= min_jaccard and share >= min_id_overlap and ratio >= min_row_ratio
              and fam[a] <= family and fam[b] <= family):
            why = "similar columns, IDs and size"
        else:
            continue
        out.append({"file A": a, "file B": b, "rows A": int(rows[a]), "rows B": int(rows[b]),
                    "column overlap": round(jac, 2), "ID overlap": round(share, 2), "why": why})
    return pd.DataFrame(out)


def free_text_columns(inv):
    """(file, column) pairs that identifier_audit flags as free text or as direct-identifier names."""
    a = identifier_audit(inv)
    if not len(a):
        return pd.DataFrame(columns=["file", "column", "kind"])
    a = a.assign(kind=a["flags"].map(lambda f: "direct-identifier name" if "direct-identifier" in f else
                                     "free text?" if "free text?" in f else None)).dropna(subset=["kind"])
    return a[["file", "column", "kind"]].reset_index(drop=True)


def carried_forward(inv, site, rejected=None, excluded=None, notes=None):
    """What steps 2 to 10 must honour, as plain lists (names only, no values):
      free_text / direct_identifier: columns that must not reach a release;
      lookalike_files: pairs to settle at step 2;
      rejected_files: {file: reason} files known not to be used (their columns must not be released);
      excluded_from_inventory: the exclude pattern used (those files were never profiled);
      notes: free statements, e.g. a system changeover date."""
    ft = free_text_columns(inv)
    look = lookalike_files(inv)
    return {"site": site, "date": str(date.today()),
            "free_text": ft.loc[ft["kind"] == "free text?", ["file", "column"]].values.tolist(),
            "direct_identifier": ft.loc[ft["kind"] != "free text?", ["file", "column"]].values.tolist(),
            "lookalike_files": look[["file A", "file B", "why"]].values.tolist() if len(look) else [],
            "rejected_files": dict(rejected or {}), "excluded_from_inventory": excluded,
            "notes": list(notes or [])}


def save_carried_forward(cf, path):
    Path(path).write_text(json.dumps(cf, indent=1))


def load_carried_forward(path):
    return json.loads(Path(path).read_text())


def check_columns(cf, columns):
    """For later steps: which of `columns` (names in a harmonised or released table) have the name of
    a column flagged as free text or as a direct identifier at step 1? Names only, case-insensitive."""
    flagged = {c.strip().lower(): kind for kind in ("free_text", "direct_identifier")
               for _, c in cf[kind]}
    return [(c, flagged[c.strip().lower()]) for c in columns if c.strip().lower() in flagged]


def findings_text(inv, site, base, by_year=None, rejected=None, notes=None, gaps=None):
    """Markdown 'Findings' block for the top of the report."""
    ft, look, keys = free_text_columns(inv), lookalike_files(inv), key_table(inv)
    if gaps is None and by_year is not None and len(by_year):
        gaps = find_gaps(by_year)
    parts = [f"# Findings for later steps: {site}", "",
             f"{len(inv['summary'])} files profiled; base file for ID overlap: {base}.", ""]
    if notes:
        parts += ["## Notes from the analyst", ""] + [f"- {n}" for n in notes] + [""]
    if rejected:
        parts += ["## Files known not to be used", ""] + [f"- {f}: {why}" for f, why in rejected.items()] + [""]
    parts += ["## Files that look like copies or versions of one another (to settle at step 2)", "",
              df_text(look, index=False) if len(look) else "none found", ""]
    parts += ["## Candidate keys (ID-like columns)", "",
              df_text(keys, index=False) if len(keys) else "none", ""]
    parts += ["## Free-text and direct-identifier columns (must not reach a release)", "",
              df_text(ft, index=False) if len(ft) else "none", ""]
    if gaps is not None:
        parts += ["## Years far below a file's usual level (era changes, gaps)", "",
                  df_text(gaps, index=False) if len(gaps) else "none", ""]
    if by_year is not None and len(by_year):
        parts += ["## Rows per calendar year, by each file's main time column", "", df_text(by_year), ""]
    return "\n".join(parts)


def finalise(inv, site, out_dir, base="ai_picu_demographics.csv", by_year=None, rejected=None,
             excluded=None, notes=None):
    """Write the step 1 outputs for one site into out_dir (counts, shapes and column names only):
      <SITE>_inventory_<date>.md   the full report, findings first;
      <SITE>_carried_forward.json  the lists later steps check against (load_carried_forward).
    Returns the two paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / f"{site}_inventory_{date.today()}.md"
    js = out_dir / f"{site}_carried_forward.json"
    write_report(inv, site, md, base=base,
                 findings=findings_text(inv, site, base, by_year, rejected, notes))
    save_carried_forward(carried_forward(inv, site, rejected, excluded, notes), js)
    return {"report": md, "carried_forward": js}