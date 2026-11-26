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
    from IPython.display import display
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