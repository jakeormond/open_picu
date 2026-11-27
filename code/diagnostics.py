"""Step 2 diagnostics: helpers shared by the three site modules (rbh_diagnostics, smh_diagnostics, gosh_links).

Nothing here knows a site's ID format. A site module builds sets of stay keys and hands them in; these
functions count, compare and write. Counts only: nothing returned is an ID, a date or a row value.

    import diagnostics as D
    D.compare_keys(new_keys, old_keys, ("new", "old"), others={"in demographics": coh})
    D.coverage_by_year(manifest, {"infusion": keys1, "meds": keys2})
    D.show(tables)                      # in a notebook: a table, or a dict of named tables
    D.write_report(tables, path)        # the same tables, as one dated Markdown file
"""
from datetime import date
from pathlib import Path

import pandas as pd

import inventory as I


def compare_keys(a, b, names=("A", "B"), others=None, year_of=None):
    """Two sets of stay keys (two versions of a file, or two tables). Counts: in each, in both, in only one.
    others: {label: set} reference sets; for each, how many of the A-only and B-only keys lie inside it.
    year_of: function(sorted keys) -> Series of years; adds the admission years of the one-sided keys."""
    a, b = set(a), set(b)
    na, nb = names
    rows = {na: len(a), nb: len(b), "in both": len(a & b), f"{na} only": len(a - b), f"{nb} only": len(b - a)}
    for label, ref in (others or {}).items():
        ref = set(ref)
        rows[f"{na} only, {label}"] = len((a - b) & ref)
        rows[f"{nb} only, {label}"] = len((b - a) & ref)
    out = {"stay counts": pd.DataFrame({"stays": rows})}
    if year_of is not None:
        out["admission year"] = pd.DataFrame({
            f"{na} only": year_of(sorted(a - b)).value_counts().sort_index(),
            f"{nb} only": year_of(sorted(b - a)).value_counts().sort_index()}).fillna(0).astype(int)
    return out


def coverage_by_year(manifest, key_sets, key_col="stay_key", year_col="year"):
    """For the eligible stays in `manifest`: the share, by admission year, that have at least one row in each
    table. key_sets = {table name: set of stay keys with a row}. A falling share is missing data; a flat share
    with fewer rows is a change in charting. The first column is the number of eligible stays that year."""
    has = pd.DataFrame({name: manifest[key_col].isin(set(keys)) for name, keys in key_sets.items()})
    has[year_col] = manifest[year_col].values
    share = has.groupby(year_col).mean().round(3)
    share.insert(0, "eligible stays", has.groupby(year_col).size())
    return share


def show(tables):
    """Display a table, or a dict of named tables, in a notebook."""
    try:
        from IPython.display import display
    except ImportError:      # outside a notebook
        display = print
    for name, t in (tables.items() if isinstance(tables, dict) else [(None, tables)]):
        if name:
            print(name)
        display(t)


def write_report(tables, path, title="Diagnostics"):
    """Write named tables (name -> DataFrame, or name -> dict of such) to one Markdown file, dated."""
    parts = [f"# {title}", f"Generated {date.today()}", ""]
    for name, t in tables.items():
        parts += [f"## {name}", ""]
        for sub, df in (t.items() if isinstance(t, dict) else [(None, t)]):
            if sub:
                parts += [f"### {sub}", ""]
            parts += [I.df_text(df), ""]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(parts) + "\n")


def rows_by_month(path, time_col, start=None, end=None):
    """Rows per calendar month of `time_col` in one file (CSV or parquet), optionally between start and end
    ("2014-01", "2015-06"). Months with no rows are shown as 0, so a gap is visible. Finds the month a table
    changes or stops."""
    t = I.parse_dates(I.read(path, usecols=[time_col])[0][time_col])[0].dropna()
    s = t.dt.to_period("M").value_counts().sort_index()
    s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"), fill_value=0)
    return s.loc[start:end].to_frame("rows")


class Log:
    """Collects what a notebook prints (and any table added) into one Markdown report, while still showing it.
    For modules that print their counts (gosh_links.py) rather than return tables. Counts only: use it only
    around functions that print counts.

        log = D.Log()
        with log("1. How the IDs link"):
            links = GL.check_links(...)          # prints as usual, and is kept
        log.add("2. Rows by month", D.rows_by_month(...))
        log.write(reports_dir / "GOSH_diagnostics_<date>.md", title="GOSH diagnostics")
    """

    class _Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, s):
            for st in self.streams:
                st.write(s)
            return len(s)

        def flush(self):
            for st in self.streams:
                st.flush()

    def __init__(self):
        self.sections = []

    def __call__(self, name):
        import contextlib
        import io
        import sys
        log, buf = self, io.StringIO()

        @contextlib.contextmanager
        def _ctx():
            with contextlib.redirect_stdout(log._Tee(sys.stdout, buf)):
                try:
                    yield
                finally:
                    log.sections.append((name, "```\n" + buf.getvalue().rstrip() + "\n```"))
        return _ctx()

    def add(self, name, table):
        """Add a table (or dict of tables) under a heading, and display it."""
        show(table)
        self.sections.append((name, "\n\n".join(
            (f"### {k}\n\n" if k else "") + I.df_text(v)
            for k, v in (table.items() if isinstance(table, dict) else [(None, table)]))))

    def write(self, path, title="Diagnostics"):
        parts = [f"# {title}", f"Generated {date.today()}", ""]
        for name, text in self.sections:
            parts += [f"## {name}", "", text, ""]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("\n".join(parts) + "\n")