# Open-PICU: London PICU data (secure data environment)

Working folder for the London PICU datasets of the SPRIND "Recoding Medicine" project, "Data saves children: Open-PICU". The data cannot be released from the secure data environment (SDE). Only aggregate counts and ranges leave it, after output checking.

## Layout

```
open_picu/
  README.md
  code/                  shared, site-agnostic modules
    inventory.py         profile every CSV in a site folder; date and identifier audits; report writer
    manifest.py          stay manifests (eligible stays) and waterfalls
  notebooks/             one notebook per analysis, numbered in run order
    01_inventory_rbh.ipynb
    01_inventory_smh.ipynb
    02_manifests.ipynb
  reports/               aggregate counts and ranges only (candidates for output checking)
    RBH_inventory.md, SMH_inventory.md
    RBH_findings.md, SMH_findings.md
  derived/               row-level, never leaves the SDE, git-ignored
    RBH_manifest.csv, SMH_manifest.csv, RBH_cohort_flags.csv
```

Raw supplier files stay where they are. Nothing here writes to them.

## Sites

| Site | Folder variable | Key | Status |
|---|---|---|---|
| Royal Brompton (RBH) | `rbh_dir` | `studyID` = `prefix:PATIENT_RK:SAS seconds of admission`; a stay is patient + admission time (the NIC/NND prefix is not part of the stay) | inventoried, manifest next |
| St Mary's (SMH) | `smh_dir` | `encounterId` (`encounterID` in the medication files) | inventoried, manifest next |
| GOSH | | | not started |

There is no key shared between sites. Do not try to link patients across sites.

## Eligibility rules (agreed 2026-11-15)

A stay is used if it:
1. was admitted in or after 2013;
2. is in the new PICANet file (the old PICANet file is not used);
3. has real vitals (at least one vitals row with a chart time; at SMH also a value).

The manifest holds only stays that pass all three. `manifest.py` prints a waterfall of how many stays each rule removes.

These rules rest on the belief that the earlier studies used only new-PICANet stays. The student has been asked to confirm.

## Run order

1. `01_inventory_*`: profile each site, write the inventory report, run the date and identifier audits.
2. `02_manifests`: build one manifest per site, print the waterfalls, save to `derived/`.
3. Later: filter every table to the manifest with `manifest.eligible_rows`, de-duplicate (sedation, vent, vitals and others have exact duplicate rows), then anonymise.

## Conventions

- One notebook per analysis. Functions live in `code/`, not in notebooks.
- Cell 1 holds imports, autoreload, `sys.path` and nothing else. Directories are set in cell 2.
- Code and notebooks refer to data by file and column, never by value: no pasted IDs, dates or example rows in code, comments or commit messages.
- Findings files hold counts and ranges only.

## Git

- Remote: Imperial GitLab.
- Notebook outputs are stripped on commit with `nbstripout`. Each clone needs `nbstripout --install` run inside the repo.
- `derived/` and all CSVs are git-ignored.

## Open items

See the open questions in `reports/RBH_findings.md` and `reports/SMH_findings.md`. The main ones: whether the studies used only new-PICANet stays, the St Mary's `interventionId`/`attributeId` dictionary, the meaning of NIC and NND, and governance terms for the planned public de-identified release.
