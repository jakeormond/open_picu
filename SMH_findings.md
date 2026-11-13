# Open-PICU: St Mary's (SMH) dataset, findings so far

Written 2026-11-10. Source: inventory of the 13 CSVs in the secure data environment (`inventory.py` + notebook), plus diagnostic cells. Aggregates only; no row-level data are reproduced here.

## 1. What is in the folder

13 CSV files, all prefixed `ai_picu_`. The tables are mostly long format (one row per charted value) with 3 to 9 columns.

| File | Rows | Exact duplicate rows | Rows after de-duplication | Notes |
|---|---|---|---|---|
| vent | 10,307,655 | 5,372,486 | 4,935,169 | 15 `interventionId` values |
| vitals | 9,058,409 | 3,525,005 | 5,533,404 | 13 `interventionId`, 31 `attributeId` |
| io | 5,496,565 | 12,359 | 5,484,206 | `hourTotal`, `cumTotal` (ml), `isFinal`, `isReset` |
| airway | 3,148,920 | 1,041,845 | 2,107,075 | 3 `interventionId`, 8 `attributeId` |
| bg (blood gas) | 2,659,774 | 778,627 | 1,881,147 | 16 `shortLabel` values |
| labs | 1,019,225 | 308,275 | 710,950 | 21 `shortLabel` values |
| infusion | 279,817 | 0 | 279,817 | 25 drugs (Midazolam, Fentanyl, Morphine, Noradrenaline, ...) |
| medications | 32,876 | 0 | 32,876 | 8 drugs |
| medications_furosemide | 12,666 | 0 | 12,666 | furosemide only |
| medications_v2 | 45,542 | 0 | 45,542 | = medications + medications_furosemide |
| demographics | 4,625 | 123 | 4,502 | 4,047 encounters |
| outcomes | 4,657 | 594 | 4,063 | 4,047 encounters |
| piccanet | 3,711 | 0 | 3,711 | 3,709 encounters, 17 columns |

- RBH had essentially no exact duplicate rows; here 29 to 52% of rows in vent, vitals, airway, bg and labs are exact repeats. Whether they are true repeats or distinct measurements with identical fields is not yet known. De-duplicate before counting.
- `medications_v2` has exactly the row count of the other two medication files combined (32,876 + 12,666 = 45,542) and identical drug counts (for example Chloral Hydrate 19,530, Furosemide 12,635, Dexamethasone 4,803). Use v2 only.
- Spelling variants in `infusion`: "Morphine Sulphate" and "Morphine Sulfate" are the same drug.

## 2. IDs and linking

- Key: `encounterId` (`encounterID` in the medication files). No composite key or prefix.
- Demographics: 4,047 encounters, 3,386 patients (`UniquePtID`). 2,983 patients have one encounter; 403 have two or more.
- Every file is 100% inside demographics by `encounterId`. Coverage of the 4,047 encounters: vitals 4,037; vent and airway 4,036; io 4,024; bg 3,880; labs 3,838; infusion 2,558; outcomes 4,047; PICANet 3,709.
- `UniquePtID` does not match between demographics and PICANet (0% overlap). They use different pseudonyms. Link on `encounterId`; use the demographics `UniquePtID` for patient-level splits. The average lengths also differ (34 versus 32 characters).

## 3. Time

- Chart times (`utcChartTime`) are UTC, ISO format, from 2011-12-31 (io) / 2012-01-02 to 2023-03-06.
- `inTime` (demographics) and `AdDateTime` (PICANet) are `dd/mm/yyyy hh:mm:ss` strings, day-first, in London local time. The first vitals time minus `inTime` is -1 h for most May to September encounters (1,336) and 0 h for most November to February encounters (1,300). Convert admission times to UTC before comparing with chart times. About 10% of encounters are off by an hour or more in either season (charting started earlier or later than `inTime`).
- `medications_furosemide` uses a different time format (`dd/mm/yyyy hh:mm`).
- Admission range: demographics 2012-01-02 to 2022-12-30; PICANet 2013-01-02 to 2022-12-30.

## 4. Cohort

| Admission year | Encounters | In PICANet |
|---|---|---|
| 2012 | 338 | 0 |
| 2013 | 345 | 345 |
| 2014 | 337 | 337 |
| 2015 | 325 | 325 |
| 2016 | 340 | 340 |
| 2017 | 321 | 321 |
| 2018 | 326 | 326 |
| 2019 | 400 | 400 |
| 2020 | 322 | 322 |
| 2021 | 467 | 467 |
| 2022 | 526 | 526 |
| **Total** | **4,047** | **3,709** |

- PICANet covers every encounter admitted 2013 to 2022 and none from 2012. The vitals cover 4,037 of the 4,047 encounters.
- The application's and deck's St Mary's figure is 3,594, about 3% below PICANet's 3,709. How it was derived is unknown.
- PICANet audit fields (PIM3, diagnosis group, `LOSHours`, `InTubeDays`, `TrachDays`) are missing for about 10% of rows (PIM3 missing in 378 rows). `AdTime` is also 10% missing and is stored as a time with a placeholder date.
- Admissions rise in 2021 (467) and 2022 (526) compared with about 320 to 400 a year before. Worth knowing for distribution shift.

## 5. Demographics and outcomes

- 4,625 rows = 4,502 distinct rows for 4,047 encounters. 383 encounters have differing rows: 381 differ only in `Weight` and 2 differ in `inTime` (12 and 94 hours apart). Age, gender, ethnicity, `primaryDiagnosis`, `SepsisDiagnosis` and `UniquePtID` are consistent within an encounter.
- `Weight` is stored as text. 229 entries are non-numeric, and at least one encounter has a weight of 0. For the 184 encounters whose numeric weights differ, the median max/min ratio is 1.13.
- `Age` is an integer with a maximum of 215 and 99th percentile of about 201, almost certainly months (under 18 years).
- `primaryDiagnosis` is 27% missing in demographics. `SepsisDiagnosis` is 1 for 147 rows.
- Outcomes: 4,657 rows with 594 exact duplicates, 4,047 encounters. `isDeceased` is 1 in 213 rows, which must be de-duplicated before computing mortality. `LOS` has a median of 97 and is likely in hours (PICANet `LOSHours` median is about 91).

## 6. What the IDs seem to mean (unconfirmed, from value patterns)

Vitals/vent/airway/io identify the measurement only by `interventionId` and `attributeId`. There is no dictionary in the folder. Only `bg` and `labs` (`shortLabel`) and the drug files carry names.

| File | Intervention | Looks like |
|---|---|---|
| vitals | 3406 | NIBP: cuff site ("Leg L/R", "Arm L") and numbers |
| vitals | 3818 | temperature: site ("Ax") and values such as 36.5 |
| vitals | 5027 | cardiac rhythm (SR, ST, SB, S. Arry) |
| vitals | 8528 | pupil reaction (Br, Sl, Pinpoint, Fix, UTA) |
| vitals | 8073 | SpO2 (100, 98, 99) |
| vitals | 8010 | heart rate? (values around 120 to 130) |
| vitals | 2934, 2935, 4688, 7238, 7796, 8070, 30546 | unclear |
| vent | 5984 | ventilation mode (PC-BiPAP, BIPAP-ASB, SV RA, HFOV, Spontaneous-Timed) |
| vent | 8114, 14238 | FiO2 |
| vent | 5431 | PEEP? |
| vent | 4131, 4185, 4186, 4553, 4554, 4555, 5184, 8115, 8117, 8119, 3984 | unclear |
| airway | 8039 | airway type (Oral ETT, Nasal ETT, Trach, Trache tube, Normal); with ventilation mode this could give intubation and extubation events |
| airway | 5402, 5404 | tube size, cuff, depth, route |

- All measurement values (`terseForm`, `verboseForm`) are stored as text; parse before use. `Dosage_terse` is numeric; `Dosage_verbose` includes the unit.
- The column names (`interventionId`, `attributeId`, `terseForm`, `verboseForm`, `utcChartTime`, `isFinal`, `isReset`) may be from a Philips ICCA export (unconfirmed). If so, the source system will have lookup tables for the IDs.

## 7. Other notes

- `io`: only millilitres; `hourTotal` min -4,078 and max 6,639; `cumTotal` up to 271,698; 4,111 rows with `isReset` = 1; 16 `interventionId` values, unlabelled. Cumulative totals need handling at resets.
- 10 demographics encounters have no vitals.

## 8. Open questions

For the supplier or the PhD student:

1. Is there a dictionary for `interventionId`, `attributeId` and `materialId`, and what mapping did the PhD student use?
2. Which `Weight` should be used when an encounter has several, and what are the zero and non-numeric entries? Why do two encounters have two `inTime` values?
3. Why do `UniquePtID` values differ between demographics and PICANet?
4. Demographics includes 2012 but PICANet starts in 2013. Is PICANet data for 2012 available?
5. Why do vent, vitals, airway, bg and labs contain so many exact duplicate rows (29 to 52%)? Are they safe to drop?
6. How was the application's St Mary's figure of 3,594 derived, given 3,709 encounters in PICANet and 4,047 in demographics?
7. Why do admissions rise in 2021 and 2022 (467 and 526 versus about 330 a year earlier)?
8. How were the `ai_picu_*` files built? Is a rawer layer available?

For us (technical):

9. Collapse demographics to one row per encounter (weight rule, `inTime` rule).
10. Convert admission times from London local time to UTC.
11. Handle `io` cumulative totals and resets.
12. Governance: ethics approval and data-sharing terms for each London dataset for the new uses (public de-identified release, sharing with Bayreuth); PICANet fields may have separate terms.

13. The date audit shows `AdTime` (PICANet) is a time of day stored with the placeholder date 1900-01-01, but some rows seem to carry a real date (up to 2018-04-25). Check which rows, and whether `AdDateTime` should be used instead.
14. (Resolved) Infusion `utcChartTime` failed to parse only because of a parser bug. All 279,817 values share one ISO format and the range is 2012-01-03 to 2023-02-18.
15. Check what `primaryDiagnosis` (907 distinct values) and PICANet `EthnicOther` (273 distinct values) contain before any release: they may hold identifying detail.

## 9. Dates, identifiers and anonymisation inputs

Source: the date audit and identifier audit of the SMH inventory, 2026-11-13. Ranges and counts only. Everything here is an input to the anonymisation plan, not a decision.

**Absolute dates are real calendar dates, to the second.**

| Column | Files | Range | Resolution |
|---|---|---|---|
| `utcChartTime` | airway, bg, io, labs, vent, vitals, medications (all variants) | 2012-01-02 (io 2011-12-31, medications 2012-01-05) to 2023-03-06 (medications to 2023-02-12); about 4,030 distinct days | second (io, medications: minute) |
| `utcChartTime` | infusion | 2012-01-03 to 2023-02-18 (279,817 values, 3,588 distinct days) | minute |
| `inTime` | demographics | 2012-01-02 to 2022-12-30 (4,625 rows, 2,553 distinct days) | second |
| `AdDateTime`, `AdDate` | PICANet | 2013-01-02 to 2022-12-30 (3,711 rows) | second, date only |
| `AdTime` | PICANet | time of day with placeholder date 1900-01-01 for 93% of rows; 237 rows carry a real date, 2017-01-17 to 2018-04-25 (41 distinct days; question 13) | minute |

- Admissions end 2022-12-30 but chart data run to 2023-03-06, so long stays that start in late 2022 are captured to the end.
- PICANet `AdDateTime` appears to equal the demographics `inTime` to the second (both end at 2022-12-30 21:10:38). If so, the two records can be linked on exact admission time; not yet checked row by row.
- Admission times are London local time and chart times are UTC. Converting between them needs the real calendar date (BST), so convert to UTC (or to relative time) before dates are removed.
- `medications_furosemide` uses day-first `dd/mm/yyyy hh:mm`, the same style as `inTime`; the other drug files use ISO. Check that the day/month order holds (the rerun audit reports the maximum of each field).

**Identifier audit.**
- No column is named like a name, NHS number, hospital number, date of birth, postcode, address, phone or email.
- Keys: `encounterId` in every table; `UniquePtID` (hashed text, 3,386 patients) in demographics and PICANet. The two files use different hashes, so it is a patient pseudonym that must be replaced, not an external link.
- Quasi-identifiers: `Age` (months, 215 distinct values; no day-level age as in RBH), `gender` (2 values), `Weight` (text, 470 distinct), `ethnicGroup` (94 distinct values in demographics versus 19 in PICANet; the long tail is a small-cell risk), `SepsisDiagnosis`, `isDeceased`.
- Free-text-like: demographics `primaryDiagnosis` (907 distinct values, about 20% of rows unique), PICANet `SecDescriptions` (1,343 distinct values) and `EthnicOther` (273 distinct values; RBH has 11).
- The `Dosage_terse` and `Dosage_verbose` columns were flagged as quasi-identifiers by mistake (a regex matching "age" inside "Dosage"); fixed.
- No `EventID` and no `AgeDays` in St Mary's PICANet, so it carries fewer linkable fields than RBH.

**Candidate anonymisation steps (to discuss):**
1. Replace `encounterId` and `UniquePtID` with new random keys, one mapping per site kept inside the SDE.
2. Convert times to UTC first, then replace absolute dates by time since admission; decide whether to keep a coarse calendar year.
3. Top-code and coarsen `Age`.
4. Collapse `ethnicGroup` to the PICANet categories (or fewer), map `primaryDiagnosis` to `PrimaryDiagnosisGroup`, drop `SecDescriptions` and `EthnicOther` (or map to categories).
5. Check small combinations of age, sex, ethnicity, weight, diagnosis and admission year before release.

## 10. Next steps

- Weight rule: 3,307 encounters have both a numeric demographics weight and a PICANet weight. The demographics minimum, median and maximum are within 5% of the PICANet weight in 94.6%, 93.3% and 93.9% of them, so the choice among them matters little. Proposed rule: use the PICANet weight where present; otherwise the median of the positive numeric demographics weights (this also covers 2012, which has no PICANet record). Zero and non-numeric entries are excluded.
- Get the ID dictionary and map the unclear interventions.
- Repeat the inventory for GOSH.
- Hold all quoted St Mary's numbers until questions 4 and 6 are answered.
