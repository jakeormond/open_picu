# Open-PICU: London PICU data (secure data environment)

Working folder for the London PICU datasets (RBH, SMH, GOSH) of the SPRIND "Recoding Medicine" project, "Data saves children: Open-PICU". The data cannot be released from the secure data environment (SDE). Only aggregate counts and ranges leave it, after output checking. The order of the steps is in `PIPELINE.md`.

## Layout

```
open_picu/
  README.md, PIPELINE.md, ASSEMBLY.md, anonymisation_design.md
  RBH_findings.md, SMH_findings.md, GOSH_findings.md     (counts and ranges only)
  code/                  shared modules; functions live here, not in notebooks
    inventory.py         profile every CSV in a site folder; date and identifier audits; report writer
    manifest.py          stay manifests (eligible stays) and waterfalls, all three sites
    gosh_links.py        GOSH diagnostics: ID links, PICANet file comparison, vitals coverage (diagnostic only)
    picanet_times.py     RBH and SMH diagnostics: admission and discharge times, LOS (diagnostic only)
    assemble.py          cut every table to the manifest stays; exact-duplicate removal; assembly log
    static.py            one row per stay, one schema across sites; pooled static table
    smh_mappings.py      SMH interventionId / attributeId / materialId mappings and the extraction SQL record
    concepts.py          cross-site concept map (102 concepts incl. 24 drugs): which measurements exist at all three sites, ranges, coverage by year, availability patterns
  notebooks/             one notebook per analysis step
    rbh_inventory, smh_inventory, gosh_inventory, manifest, assemble, concepts
  reports/               aggregate counts only; git-ignored, regenerated
  derived/               row-level (and some aggregate) outputs; never leaves the SDE; git-ignored
    assembled/<SITE>/    assembled tables (text-typed parquet)
    static/              <SITE>_static.parquet and pooled_static.parquet
    concepts/            concept_summary.csv, concept_detail.csv (counts and ranges)
    manifests, inventory pickle
```

Raw supplier files stay where they are. Nothing here writes to them.

## Sites and stay definitions

| Site | Key | Stay | Eligible stays |
|---|---|---|---|
| Royal Brompton (RBH) | `studyID` = `prefix:PATIENT_RK:SAS seconds of admission` | patient + admission time (the NIC/NND prefix is not part of the stay) | 4,765 |
| St Mary's (SMH) | `encounterId` (`encounterID` in the medication files) | one `encounterId` | 3,699 |
| GOSH | `project_id` | one `_eprweights` PICANet row with a `project_id`; `stay_id` = project + admission time | 9,671 |

There is no key shared between sites. Do not link patients across sites.

## Eligibility rules (agreed 2026-11-15)

A stay is used if it:
1. was admitted in or after 2013;
2. is in the new PICANet data (RBH: new file only; GOSH: `_eprweights` with a `project_id`);
3. has real vitals (at least one vitals row with a chart time; at SMH also a value).

`manifest.py` prints a waterfall of how many stays each rule removes. The static table drops the few stays with two conflicting PICANet rows (1 RBH, 2 SMH): 4,764, 3,697 and 9,671 stays. A common cohort rule (stays over 6 hours, because the SMH extract has that cut) is applied at pooling, not at assembly.

## Run order

See `PIPELINE.md`. In short: inventory, diagnostics, manifest, assembly, static table, mapping records, concept map, then harmonise and pool, re-identification review, and anonymisation.

## Conventions

- One notebook per analysis step. Functions live in `code/`.
- Cell 1 holds imports, autoreload, `sys.path` and nothing else. Directories are set in cell 2.
- Code and notebooks refer to data by file and column, never by value: no pasted IDs, dates or example rows in code, comments or commit messages.
- Row-level files live only in `derived/`. Assembly drops nothing except rows outside the manifest and exact duplicates; free text is handled at anonymisation.
- Findings files hold counts and ranges only.

## Git

- Remotes (both outside the SDE, both private): Imperial GitLab and GitHub (`jakeormond/open_picu`, deploy key).
- Notebook outputs are stripped on commit with `nbstripout`. Each clone needs `nbstripout --install` run inside the repo.
- Git-ignored: `derived/`, `reports/`, all CSV, parquet and pickle files. Only code, stripped notebooks and the markdown documents are committed.
- Before the first push to a remote, audit the history: `git log --all --name-only`, notebook outputs, and `NND:[0-9]|NIC:[0-9]`-shaped strings. Record the result here when it has been done. Check the markdown findings files and `gosh_for_claude.md` by eye first, because logs are free text.

## Open items

Details are in the three findings files and in `ASSEMBLY.md` (section 6). The main ones: the GOSH Epic-era data (blood gas, vent mode, tidal volume, I:E ratio, ETT size) is not in the supplied files; PIM version and calibration differ by site and year; unit harmonisation across sites; drugs are not yet mapped; governance for a pooled release (all three trusts, PICANet terms, Bayreuth); the first git push and history audit.
