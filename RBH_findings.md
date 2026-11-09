# Open-PICU: RBH (Royal Brompton) dataset, findings so far

Written 2026-11-09. Source: inventory of the 17 CSVs in the secure data environment (`inventory.py` + notebook), plus diagnostic cells. Aggregates only; no row-level data are reproduced here.

## 1. What is in the folder

17 CSV files, all prefixed `ai_picu_`.

| Group | Files | Notes |
|---|---|---|
| Cohort / outcomes | demographics (14,799 rows), outcomes (14,797) | demographics has 2 studyIDs duplicated (see 4) |
| Time series | vitals (1.96M rows), vent (1.71M), io (2.59M), temp (0.92M), airway (0.62M) | hourly, several rows per hour |
| Labs | bg (0.56M), biochemistry (0.15M), full_blood_count (0.13M), coagulation (0.12M) | |
| Drugs | infusion (0.73M), meds (0.33M), sedation (1.19M), sedation_old (0.48M) | keyed on studyID, with `encounterId`; cover subsets of the cohort |
| PICANet audit | piccanet (4,796), piccanet_old (7,928) | admission-level audit fields (age, diagnosis group, PIM3, LOS, intubation days, unplanned extubation) |

Not needed: the `.7z` archive. `ventMode_dict` is the PhD student's key for vent modes; refer to it when processing vent modes.

## 2. IDs and structure

- **studyID** = `prefix : PATIENT_RK : PICU admission time`. The middle part equals `PATIENT_RK` for 100% of rows; the last part equals `PICUadm_dttm` in SAS seconds, with zero difference on every row. So a studyID is one PICU admission by one patient.
- Counts: 10,019 patients (`PATIENT_RK`), 13,285 hospital admissions (`PAS_AD_RK`), 14,797 studyIDs.
- 12,146 hospital admissions have one studyID; the rest have 2 to 13. One patient has 25 studyIDs.
- Prefixes: `NND` (11,837) and `NIC` (2,962). Meaning unknown.
- Each studyID has its own `WARD_IN_dttm`. 63 studyIDs start before the previous one in the same admission ended (up to about 240 days), so concatenating studyIDs risks double-counting.
- `studyID` is not a stable key across extracts. The new `sedation.csv` has 7,576 studyIDs but only 58% are in the demographics cohort, although 96% of its patients are.

## 3. Time

- All timestamps are SAS datetime strings, e.g. `01JAN2020:12:34:56.78`. Parse with `I.parse_dates`.
- `intv_hr` = whole hours since `WARD_IN_dttm` (truncated). `Day` is the day equivalent.
- `LOS` is in hours (median ratio 1.00 to `WARD_OUT_dttm` minus `WARD_IN_dttm`). 21 stays have the out time before the in time.
- Charting is hourly: the within-stay `intv_hr` step has median 1 and 99th percentile 1; at least 10% of steps are 0 (several rows per hour). The maximum gap is 29,013 hours.
- Vitals rows by year: 2009 (3.8k) and 2023 (32k) are partial years; 2020 dips (88k versus 155k in 2019).

## 4. Cohort

| | Count |
|---|---|
| studyIDs in demographics | 14,797 |
| ...with no time-series data (single placeholder row) | 7,916 |
| ...with time-series data | 6,882 |
| ...of those, with any PICU unit row | 6,663 |
| In new PICANet file | 4,795 (4,682 with PICU data) |
| In old PICANet file | 7,926 (4,837 in this cohort; about 3,090 outside it) |

- **Empty studyIDs are historical.** Almost all are admissions from 1990 to 2009; from 2010 on, fewer than 15 a year are empty. Time-series data start around late 2009 / 2010. Likely cause: paper charting before electronic records (to be confirmed).
- **Usable cohort:** about 6.9k PICU admissions, 2009/10 to early 2023, about 530 to 610 a year for 2010 to 2019, 340 in 2020, about 440 afterwards, 108 in 2023 (partial).
- **Prefix split:** `NIC`: 2,962, all with PICU data, 95% in PICANet. `NND`: 11,837, of which 7,917 are empty; of the 3,920 with data, 3,702 have a PICU row but only about half are in PICANet.
- **Admission level** (collapsing studyIDs to `PAS_AD_RK`, approximate): 6,097 admissions have a PICU row (4,484 in PICANet, 1,613 not); 102 PICANet admissions have no PICU row.
- Vitals rows by unit: PICU 83%, PHDU 10%, Theatre 5.5%, Cath 1.5%, others under 0.1%.
- Age: median 8 months in both the empty and non-empty groups. Weight is available for 6,723 of 6,882 studyIDs with data.

**Reconciling the application:** the application's RBH figure of 4,771 matches the PICANet-linked count (4,795). The extract holds up to about 6.7k PICU admissions with data, so the application and deck may understate RBH. Do not change any figure until the open questions below are answered.

## 5. Data quality notes

- `HR`, `NIBP_*` and `ABP_*` contain 0 values (artefacts); `HR` max 300; `ABP_s` max 300.
- `Weight_kg`: 2.9% missing; min 0.6, max 175.
- `Day` up to 1717 and `intv_hr` up to 41,225 for a few studyIDs.
- Demographics has 2 studyIDs with two rows each; the rows differ in `PAS_AD_RK` and `Weight_kg`, while patient, age, gender and `PICUadm_dttm` agree.
- `Ventilation_Mode`: 29 distinct labels, 29% missing. The file covers all respiratory support (BiPAP, CPAP, self-ventilating, nasal high flow, etc.), not only invasive ventilation. Do not read "BiPAP" as non-invasive; on some ventilators it is an invasive mode. Use the PhD student's `ventMode_dict` as the starting point.
- 1 duplicate row each in `sedation` and `sedation_old`.

## 6. Open questions

For Ram or the data supplier:

1. What do the `NIC` and `NND` prefixes mean?
2. Are the roughly 1,700 `NND` PICU admissions that are not in PICANet legitimate PICU stays (not reported, or not linked)?
3. Was charting on paper before 2010, so that the roughly 7.9k pre-2010 studyIDs genuinely have no time-series data?
4. Why does the extract end in early 2023? Is later data available?
5. What are the old and new PICANet files? About 3,090 of the 7,926 old PICANet IDs are outside this cohort.
6. Why does the new `sedation.csv` contain studyIDs (about 3,150) not in the demographics cohort, for mostly the same patients?
7. Which denominator should we quote for RBH: PICANet-linked admissions (about 4.8k), PICU admissions with data (about 6.1k to 6.7k), or all studyIDs (14.8k)?
8. How were the `ai_picu_*` files built? `Day`, `intv_hr` and `Weight_kg` appear in every table, so a common timeline was applied. Is a rawer layer available, and what did the PhD student change?

For us (technical):

9. Meaning and units of `LOS`-negative stays (21) and the very long gaps (up to 29,013 h); decide how to handle overlapping studyIDs within an admission.
10. Vent-mode mapping: decide how to classify invasive, non-invasive and spontaneous modes, using `ventMode_dict`.
11. Governance: which ethics approval and data-sharing terms cover each London dataset for the new uses (public de-identified release, sharing with Bayreuth)? PICANet data are an audit dataset with their own terms.

## 7. Next steps

- Save cohort flags (`RBH_cohort_flags.csv`) in the project folder; rerun the full inventory with date ranges.
- Take the questions in section 6 to Ram or the supplier.
- Repeat the inventory and ID decoding for GOSH and St Mary's; expect different ID schemes.
- Hold all quoted RBH numbers (deck, application, partner documents) until questions 1, 2 and 7 are answered.
