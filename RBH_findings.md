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
- The new `sedation.csv` has 7,576 studyIDs; 3,155 (all `NND`, admitted 2012 to 2023) are not in demographics. None has a missing `PATIENT_RK`; 3,023 belong to a cohort patient and 2,975 to a cohort admission.
- For 2,473 of those 3,155, demographics holds a `NIC` studyID with the identical patient and admission time. So the same stay carries a `NIC` or `NND` prefix depending on the table. The other 682 are: 502 with the admission in the cohort but a different time (up to 6,555 h apart), and 180 whose admission is not in the cohort.
- Duplication in `sedation.csv`: 2,478 stays appear under both a `NIC` and an `NND` prefix. 94.8% have the same row count in both copies; of the distinct (stay, time, drug, dose) records, 324,126 are in both copies (92.7% of the NIC copy's 349,744, 97.3% of the NND copy's 333,268). The two copies together hold about 683k of the file's 1.19M rows, so per-patient sums would roughly double for these stays unless de-duplicated. Within demographics, only 5 of 6,876 stays carry both prefixes.
- The NIC/NND duplication is confined to two files. `sedation.csv`: 7,576 studyIDs = 5,098 stays, 2,478 under both prefixes. `piccanet_old.csv`: 7,926 studyIDs = 5,502 stays, 2,424 under both prefixes. In every other file, at most 5 stays carry both prefixes (the same 5 as in demographics: 14,797 studyIDs = 14,792 stays). The new PICANet file is clean: 4,795 studyIDs = 4,789 stays. So much of the "old versus new PICANet" difference is probably a labelling artefact, not different patients; compare at stay level.
- Consequence: do not join tables on the studyID string. Join on patient plus admission time (or `PAS_AD_RK` plus admission time), and de-duplicate stays before counting.

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
| In old PICANet file | 7,926 studyIDs = 5,502 distinct stays (2,424 stays appear under both prefixes). Versus the new file at stay level: 4,737 in both, 52 new only, 765 old only (96 in this cohort, 669 not) |

- **Empty studyIDs are historical.** Almost all are admissions from 1990 to 2009; from 2010 on, fewer than 15 a year are empty. Time-series data start around late 2009 / 2010. Likely cause: paper charting before electronic records (to be confirmed).
- **Usable cohort:** about 6.9k PICU admissions, 2009/10 to early 2023, about 530 to 610 a year for 2010 to 2019, 340 in 2020, about 440 afterwards, 108 in 2023 (partial).
- **Prefix split (provisional: the same stay can carry either prefix, see section 2):** `NIC`: 2,962, all with PICU data, 95% in PICANet. `NND`: 11,837, of which 7,917 are empty; of the 3,920 with data, 3,702 have a PICU row but only about half are in PICANet.
- **Admission level** (collapsing studyIDs to `PAS_AD_RK`, approximate): 6,097 admissions have a PICU row (4,484 in PICANet, 1,613 not); 102 PICANet admissions have no PICU row.
- Vitals rows by unit: PICU 83%, PHDU 10%, Theatre 5.5%, Cath 1.5%, others under 0.1%.
- Age: median 8 months in both the empty and non-empty groups. Weight is available for 6,723 of 6,882 studyIDs with data.

**PICANet versus vitals, by year:** of the 6,881 studyIDs with vitals, 4,770 are in new PICANet and 2,111 are not (1,981 of those have a PICU row; 1,965 are `NND`, 146 `NIC`). By admission year the 2,111 are 1,803 from 2009 to 2012 (95, 532, 614, 562), 200 from 2013 to 2022 (9 to 33 a year) and 108 from 2023. So new PICANet covers about 2013 to 2022 and is missing the earlier and later years; within 2013 to 2022, about 96% of stays with vitals (4,770 of about 4,970) are in it. 25 PICANet-new studyIDs have no vitals (spread over 2013 to 2022). The old PICANet file reaches into 2023 (82 old-only in-cohort stays), which would cover most of the 108 vitals stays from that year.

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

1. What do the `NIC` and `NND` prefixes mean? The same stay (same patient, same admission time) appears as `NIC` in demographics and `NND` in sedation for at least 2,473 stays. Which is canonical?
2. New PICANet covers about 2013 to 2022; the vitals run 2009 to early 2023. Is PICANet data available for 2009 to 2012 and 2023? Within 2013 to 2022, about 200 stays with vitals (mostly `NND`) are not in new PICANet; are those unreported or unlinked admissions?
3. Was charting on paper before 2010, so that the roughly 7.9k pre-2010 studyIDs genuinely have no time-series data?
4. Why does the extract end in early 2023? Is later data available?
5. What are the old and new PICANet files? The old file has 7,926 studyIDs but only 5,502 distinct stays (2,424 appear under both prefixes); the new has 4,795 studyIDs and 4,789 stays. About 3,090 old studyIDs are outside this cohort, probably mostly the NND copies of NIC stays. At stay level the files overlap on 4,737 stays; 52 are new only and 765 are old only (96 in this cohort, 669 not). By admission year: 82 of the 96 old-only stays in the cohort and 181 of the 669 outside it are from 2023 (the old file reaches further into 2023); the other 488 outside the cohort are spread over 2013 to 2022 (about 30 to 85 a year). The 52 new-only stays are spread over 2014 to 2022. Are the roughly 490 old-only stays from 2013 to 2022 PICANet admissions that could not be linked to hospital records, and were they removed from the new file on purpose? Why does the old file carry both copies?
6. Why does the new `sedation.csv` label 3,155 stays `NND` that are not in demographics? 2,473 of them exist as `NIC` in demographics. For the other 682 (502 with a cohort admission but a different time, 180 with an admission outside the cohort), are they separate PICU admissions that demographics misses? For the 502, the nearest cohort studyID in the same hospital admission is a median 133 h away (25th to 75th percentile 17 to 423 h; maximum 6,555 h; 161 within 24 h), which looks more like separate PICU admissions than timestamp shifts. They have no vitals in this extract. How does this differ from `sedation_old`, whose 2,613 studyIDs are all in demographics? Also, why do 2,478 stays appear in sedation under both `NIC` and `NND` with near-identical rows (about 5% differ), and which copy is authoritative?
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
