# Inventory: SMH
Generated 2026-11-10

# Files at a glance

| file | size MB | rows | columns | duplicate rows | encoding |
|---|---|---|---|---|---|
| ai_picu_airway.csv | 185.3 | 3148920 | 6 | 1041845 | utf-8 |
| ai_picu_bg.csv | 164.2 | 2659774 | 6 | 778627 | utf-8 |
| ai_picu_demographics.csv | 0.5 | 4625 | 9 | 123 | utf-8 |
| ai_picu_infusion.csv | 21.4 | 279817 | 7 | 0 | utf-8 |
| ai_picu_io.csv | 433.8 | 5496565 | 8 | 12359 | utf-8 |
| ai_picu_labs.csv | 57.0 | 1019225 | 6 | 308275 | utf-8 |
| ai_picu_medications.csv | 2.5 | 32876 | 7 | 0 | utf-8 |
| ai_picu_medications_furosemide.csv | 0.7 | 12666 | 7 | 0 | utf-8 |
| ai_picu_medications_v2.csv | 3.3 | 45542 | 7 | 0 | utf-8 |
| ai_picu_outcomes.csv | 0.1 | 4657 | 3 | 594 | utf-8 |
| ai_picu_piccanet.csv | 0.7 | 3711 | 17 | 0 | utf-8 |
| ai_picu_vent.csv | 477.9 | 10307655 | 5 | 5372486 | utf-8 |
| ai_picu_vitals.csv | 476.6 | 9058409 | 6 | 3525005 | utf-8 |

## ai_picu_airway.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| encounterId | int64 | 0.0 | 4036 | min 2; p1 137; median 11586; p99 31153; max 32420 |
| interventionId | int64 | 0.0 | 3 | min 5402; p1 5404; median 5404; p99 8039; max 8039 |
| attributeId | int64 | 0.0 | 8 | min 13432; p1 13432; median 13436; p99 32939; max 36578 |
| utcChartTime | str | 0.0 | 145436 | datetime 2012-01-02 08:09:00 to 2023-03-06 12:00:00 (generic, day-first); format dddd-dd-dd dd:dd:dd.ddd |
| terseForm | str | 0.2 | 608 | avg length 6; first value shape aaaaaa |
| verboseForm | str | 0.2 | 610 | avg length 10; first value shape aaaaaa |

## ai_picu_bg.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| encounterId | int64 | 0.0 | 3880 | min 2; p1 212; median 11569; p99 31958; max 32420 |
| interventionId | int64 | 0.0 | 23 | min 1190; p1 1190; median 1198; p99 113868; max 113868 |
| shortLabel | str | 0.0 | 16 | NPT pH from [H+]: 206941; NPT pCO2: 205229; NPT Base Excess: 204982; NPT pO2: 201640; NPT Glucose: 186506; NPT HCO3 Standard: 182330; NPT Ionised Calcium: 173308; NPT Lactate: 172519; NPT Sodium: 172484; NPT Potassium: 172429; NPT Chloride: 171829; NPT tHb: 160172; NPT MetHb: 158509; NPT SO2: 156995; NPT Haematocrit: 102189; Blood gas sample: 31712 |
| utcChartTime | str | 0.0 | 156061 | datetime 2012-01-02 09:48:00 to 2023-03-05 15:39:00 (generic, day-first); format dddd-dd-dd dd:dd:dd.ddd |
| terseForm | str | 0.4 | 1937 | avg length 3; first value shape d.dd |
| verboseForm | str | 0.4 | 4782 | avg length 8; first value shape d.dd |

## ai_picu_demographics.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| encounterId | int64 | 0.0 | 4047 | min 2; p1 253.88; median 13314; p99 32125.8; max 32420 |
| UniquePtID | str | 0.0 | 3386 | avg length 34; first value shape daddaddadaaddaadddadddaadddaaaddad |
| Age | int64 | 0.0 | 215 | min 0; p1 0; median 25; p99 201; max 215 |
| gender | str | 0.5 | 2 | Male: 2570; Female: 2031 |
| ethnicGroup | str | 1.2 | 94 | avg length 14; first value shape aaaaaaaaa |
| Weight | str | 0.0 | 470 | avg length 3; first value shape d.d |
| inTime | str | 0.0 | 4049 | datetime 2012-01-02 08:09:36 to 2022-12-30 21:10:38 (generic, day-first); format dd/dd/dddd dd:dd:dd |
| primaryDiagnosis | str | 27.0 | 907 | avg length 35; first value shape aaaaaaaaaaaaa (aa:aaaaa) |
| SepsisDiagnosis | int64 | 0.0 | 2 | min 0; p1 0; median 0; p99 1; max 1 / values -> 0: 4478; 1: 147 |

## ai_picu_infusion.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| encounterId | int64 | 0.0 | 2558 | min 2; p1 474; median 17844; p99 32318; max 32420 |
| interventionId | int64 | 0.0 | 24 | min 10698; p1 10698; median 10703; p99 12386; max 22847 |
| utcChartTime | str | 0.0 | 72595 | avg length 23; first value shape dddd-dd-dd dd:dd:dd.ddd |
| Drug_terse | str | 0.1 | 25 | Midazolam: 77810; Fentanyl: 46298; Morphine Sulphate: 35711; Morphine Sulfate: 33438; Noradrenaline: 19214; Furosemide: 16760; Clonidine: 14003; Vecuronium: 8531; Adrenaline: 6788; Propofol: 4570; Milrinone: 4536; Ketamine: 2506; Rocuronium Bromide: 2420; Remifentanil: 1900; Labetalol: 1205; Vasopressin: 1163; Dexmedetomidine: 1025; Dopamine: 641; Hydralazine HCl: 460; Thiopentone Sodium®: 374; Atracurium: 217; Glyceryl Trinitrate: 30; Sodium Nitroprusside: 28; Dobutamine: 23; Thiopentone Sodium: 14 |
| Drug_verbose | str | 0.1 | 25 | Midazolam: 77810; Fentanyl: 46298; Morphine Sulphate: 35711; Morphine Sulfate: 33438; Noradrenaline: 19214; Furosemide: 16760; Clonidine: 14003; Vecuronium: 8531; Adrenaline: 6788; Propofol: 4570; Milrinone: 4536; Ketamine: 2506; Rocuronium Bromide: 2420; Remifentanil: 1900; Labetalol: 1205; Vasopressin: 1163; Dexmedetomidine: 1025; Dopamine: 641; Hydralazine HCl: 460; Thiopentone Sodium®: 374; Atracurium: 217; Glyceryl Trinitrate: 30; Sodium Nitroprusside: 28; Dobutamine: 23; Thiopentone Sodium: 14 |
| Dosage_terse | float64 | 6.1 | 915 | min 0; p1 0.01; median 2; p99 80; max 1200 |
| Dosage_verbose | str | 6.1 | 1284 | avg length 13; first value shape dd aaa/aa/aa |

## ai_picu_io.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| encounterId | int64 | 0.0 | 4024 | min 2; p1 196; median 12488; p99 32188; max 32420 |
| interventionId | int64 | 0.0 | 16 | min 1851; p1 1851; median 2052; p99 113958; max 113961 |
| utcChartTime | str | 0.0 | 96437 | datetime 2011-12-31 10:00:00 to 2023-03-06 14:00:00 (generic, day-first); format dddd-dd-dd dd:dd:dd.ddd |
| hourTotal | float64 | 0.0 | 29433 | min -4078; p1 -100; median 5; p99 220; max 6639 |
| cumTotal | float64 | 0.0 | 802681 | min -14815.5; p1 -658.974; median 111; p99 6158.15; max 271698 |
| unitOfMeasure | str | 0.0 | 1 | ml: 5496565 |
| isFinal | int64 | 0.0 | 2 | min 0; p1 0; median 0; p99 1; max 1 / values -> 0: 5291116; 1: 205449 |
| isReset | int64 | 0.0 | 2 | min 0; p1 0; median 0; p99 0; max 1 / values -> 0: 5492454; 1: 4111 |

## ai_picu_labs.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| encounterId | int64 | 0.0 | 3838 | min 2; p1 242; median 11038; p99 31862; max 32420 |
| interventionId | int64 | 0.0 | 50 | min 1203; p1 1274; median 1378; p99 117306; max 117502 |
| shortLabel | str | 0.0 | 21 | PLT: 134117; Hb: 132368; Albumin: 80219; Calcium: 77135; Bilirubin: 70219; Magnesium: 68476; Sodium: 42627; Creatinine: 42394; Urea: 41862; Potassium: 41220; WBC: 38959; Phosphate: 38657; Neutrophils: 38560; ALT: 36916; Lymphocytes: 35976; Chloride: 32154; APTT: 30598; Fibrinogen: 30033; INR: 4766; Glucose: 1963; Activated Partial thromboplastin Time: 6 |
| utcChartTime | str | 0.0 | 54617 | datetime 2012-01-02 10:26:00 to 2023-03-05 23:14:00 (generic, day-first); format dddd-dd-dd dd:dd:dd.ddd |
| terseForm | str | 0.2 | 2932 | avg length 4; first value shape aaaaa |
| verboseForm | str | 0.2 | 9230 | avg length 8; first value shape aaaaa |

## ai_picu_medications.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| encounterID | int64 | 0.0 | 2717 | min 20; p1 269; median 16895; p99 32200; max 32420 |
| materialId | int64 | 0.0 | 7 | min 370; p1 370; median 370; p99 3593; max 3593 |
| utcChartTime | str | 0.0 | 27232 | datetime 2012-01-05 11:41:00 to 2023-02-12 04:50:00 (generic, day-first); format dddd-dd-dd dd:dd:dd.ddd |
| Drug_terse | str | 0.3 | 8 | Chloral Hydrate: 19530; Dexamethasone: 4803; Spironolactone: 4350; Hydrocortisone: 2234; Prednisolone: 606; Methylprednisolone: 450; Chlorothiazide: 413; Methylprednisolone Sodium...: 393 |
| Drug_verbose | str | 0.3 | 8 | Chloral Hydrate: 19530; Dexamethasone: 4803; Spironolactone: 4350; Hydrocortisone: 2234; Prednisolone: 606; Methylprednisolone: 450; Chlorothiazide: 413; Methylprednisolone Sodium Succinate: 393 |
| Dosage_terse | float64 | 11.2 | 624 | min 0; p1 0.4; median 90; p99 1000; max 2000 |
| Dosage_verbose | str | 11.2 | 625 | avg length 6; first value shape d.d aa |

## ai_picu_medications_furosemide.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| encounterID | int64 | 0.0 | 2076 | min 2; p1 327; median 14769; p99 32287; max 32420 |
| materialId | int64 | 0.0 | 1 | min 795; p1 795; median 795; p99 795; max 795 |
| utcChartTime | str | 0.0 | 11887 | datetime 2012-01-05 10:15:00 to 2023-02-06 14:00:00 (generic, day-first); format dd/dd/dddd dd:dd |
| Drug_terse | str | 0.2 | 1 | Furosemide: 12635 |
| Drug_verbose | str | 0.2 | 1 | Furosemide: 12635 |
| Dosage_terse | float64 | 14.6 | 158 | min 0; p1 0.3; median 2.5; p99 20; max 180 |
| Dosage_verbose | str | 14.6 | 158 | avg length 5; first value shape d.d aa |

## ai_picu_medications_v2.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| encounterID | int64 | 0.0 | 2879 | min 2; p1 271.23; median 16256; p99 32212; max 32420 |
| materialId | int64 | 0.0 | 8 | min 370; p1 370; median 795; p99 3593; max 3593 |
| utcChartTime | str | 0.0 | 35691 | datetime 2012-01-05 10:15:00 to 2023-02-12 04:50:00 (generic, day-first); format dddd-dd-dd dd:dd:dd.ddd |
| Drug_terse | str | 0.3 | 9 | Chloral Hydrate: 19530; Furosemide: 12635; Dexamethasone: 4803; Spironolactone: 4350; Hydrocortisone: 2234; Prednisolone: 606; Methylprednisolone: 450; Chlorothiazide: 413; Methylprednisolone Sodium...: 393 |
| Drug_verbose | str | 0.3 | 9 | Chloral Hydrate: 19530; Furosemide: 12635; Dexamethasone: 4803; Spironolactone: 4350; Hydrocortisone: 2234; Prednisolone: 606; Methylprednisolone: 450; Chlorothiazide: 413; Methylprednisolone Sodium Succinate: 393 |
| Dosage_terse | float64 | 12.1 | 645 | min 0; p1 0.4; median 19; p99 1000; max 2000 |
| Dosage_verbose | str | 12.1 | 646 | avg length 5; first value shape d.d aa |

## ai_picu_outcomes.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| encounterId | int64 | 0.0 | 4047 | min 2; p1 257.72; median 13315; p99 32125.4; max 32420 |
| LOS | float64 | 0.0 | 3541 | min 0; p1 7.858; median 97.17; p99 4066.02; max 10004.4 |
| isDeceased | int64 | 0.0 | 2 | min 0; p1 0; median 0; p99 1; max 1 / values -> 0: 4444; 1: 213 |

## ai_picu_piccanet.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| encounterId | int64 | 0.0 | 3709 | min 2; p1 242.2; median 13336; p99 32146.4; max 32420 |
| UniquePtID | str | 0.0 | 3090 | avg length 32; first value shape aaaaddddaadadaaadddddaaadadaaada |
| Age | int64 | 0.0 | 215 | min 0; p1 0; median 26; p99 202; max 215 |
| gender | str | 0.4 | 2 | Male: 2067; Female: 1630 |
| AdDateTime | str | 0.0 | 3711 | datetime 2013-01-02 02:01:00 to 2022-12-30 21:10:38 (generic, day-first); format dd/dd/dddd dd:dd:dd |
| AdDate | str | 0.0 | 2327 | datetime 2013-01-02 00:00:00 to 2022-12-30 00:00:00 (generic, day-first); format dd/dd/dddd |
| AdTime | str | 10.2 | 1015 | datetime 1900-01-01 00:00:00 to 2018-04-25 20:54:00 (generic, day-first); format dd/dd/dddd dd:dd |
| PrimaryDiagnosisGroup | str | 10.2 | 14 | Respiratory: 1674; Neurological: 612; Infection: 241; Endocrine / metabolic: 197; Cardiovascular: 136; Gastrointestinal: 112; Blood / lymphatic: 108; Trauma: 88; Unknown: 78; Other: 43; Body wall and cavities: 24; Musculoskeletal: 13; Oncology: 4; Multisystem: 3 |
| PIM3 | float64 | 10.2 | 2824 | min 0.000811687; p1 0.00140523; median 0.0126107; p99 0.653498; max 0.99944 |
| SecDescriptions | str | 44.1 | 1343 | avg length 41; first value shape aaaaaaaaa aaaa |
| SexDescription | str | 10.2 | 2 | Male: 1853; Female: 1480 |
| EthnicDescription | str | 10.2 | 19 | White British: 986; Black African: 551; White other: 433; Asian Pakistani: 240; Asian Indian: 221; Other: 217; Asian other: 140; Black Caribbean: 125; Asian Bangladeshi: 116; Mixed White and Black African: 55; Mixed other: 52; Not stated: 49; Mixed White and Asian: 41; Mixed White and Black Caribbean: 33; Black other: 23; White Irish: 21; Chinese: 14; Unknown: 13; Arab: 3 |
| EthnicOther | str | 77.3 | 273 | avg length 9; first value shape aaaaaaa/aaaaaa |
| LOSHours | float64 | 10.2 | 2379 | min 0.75; p1 5.048; median 90.6667; p99 1190.99; max 10002.7 |
| InTubeDays | float64 | 10.2 | 57 | min 0; p1 0; median 3; p99 30; max 234 |
| TrachDays | float64 | 10.2 | 34 | min 0; p1 0; median 0; p99 11.68; max 407 |
| Weight | float64 | 10.9 | 549 | min 1.7; p1 2.1124; median 11.7; p99 80; max 128 |

## ai_picu_vent.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| encounterId | int64 | 0.0 | 4036 | min 2; p1 330; median 8725; p99 31950; max 32420 |
| interventionId | int64 | 0.0 | 15 | min 3984; p1 4131; median 5431; p99 8119; max 14238 |
| utcChartTime | str | 0.0 | 130545 | datetime 2012-01-02 08:09:00 to 2023-03-06 12:00:00 (generic, day-first); format dddd-dd-dd dd:dd:dd.ddd |
| terseForm | str | 0.2 | 2308 | avg length 3; first value shape aa aa |
| verboseForm | str | 0.2 | 2923 | avg length 6; first value shape aaaa aaaaaaaaaaa aaaa aaaa |

## ai_picu_vitals.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| encounterId | int64 | 0.0 | 4037 | min 2; p1 251; median 11555; p99 32053; max 32420 |
| interventionId | int64 | 0.0 | 13 | min 2934; p1 2934; median 5027; p99 8528; max 30546 |
| attributeId | int64 | 0.0 | 31 | min 1082; p1 1082; median 56052; p99 64034; max 64034 |
| utcChartTime | str | 0.0 | 146810 | datetime 2012-01-02 08:09:00 to 2023-03-06 12:46:00 (generic, day-first); format dddd-dd-dd dd:dd:dd.ddd |
| terseForm | str | 0.3 | 989 | avg length 2; first value shape d |
| verboseForm | str | 0.2 | 1420 | avg length 7; first value shape d a |

## Columns shared between files

|                |   ai_picu_airway.csv |   ai_picu_bg.csv |   ai_picu_demographics.csv |   ai_picu_infusion.csv |   ai_picu_io.csv |   ai_picu_labs.csv |   ai_picu_medications.csv |   ai_picu_medications_furosemide.csv |   ai_picu_medications_v2.csv |   ai_picu_outcomes.csv |   ai_picu_piccanet.csv |   ai_picu_vent.csv |   ai_picu_vitals.csv |
|:---------------|---------------------:|-----------------:|---------------------------:|-----------------------:|-----------------:|-------------------:|--------------------------:|-------------------------------------:|-----------------------------:|-----------------------:|-----------------------:|-------------------:|---------------------:|
| age            |                  nan |              nan |                        215 |                    nan |              nan |                nan |                       nan |                                  nan |                          nan |                    nan |                    215 |                nan |                  nan |
| attributeid    |                    8 |              nan |                        nan |                    nan |              nan |                nan |                       nan |                                  nan |                          nan |                    nan |                    nan |                nan |                   31 |
| dosage_terse   |                  nan |              nan |                        nan |                    915 |              nan |                nan |                       624 |                                  158 |                          645 |                    nan |                    nan |                nan |                  nan |
| dosage_verbose |                  nan |              nan |                        nan |                   1284 |              nan |                nan |                       625 |                                  158 |                          646 |                    nan |                    nan |                nan |                  nan |
| drug_terse     |                  nan |              nan |                        nan |                     25 |              nan |                nan |                         8 |                                    1 |                            9 |                    nan |                    nan |                nan |                  nan |
| drug_verbose   |                  nan |              nan |                        nan |                     25 |              nan |                nan |                         8 |                                    1 |                            9 |                    nan |                    nan |                nan |                  nan |
| encounterid    |                 4036 |             3880 |                       4047 |                   2558 |             4024 |               3838 |                      2717 |                                 2076 |                         2879 |                   4047 |                   3709 |               4036 |                 4037 |
| gender         |                  nan |              nan |                          2 |                    nan |              nan |                nan |                       nan |                                  nan |                          nan |                    nan |                      2 |                nan |                  nan |
| interventionid |                    3 |               23 |                        nan |                     24 |               16 |                 50 |                       nan |                                  nan |                          nan |                    nan |                    nan |                 15 |                   13 |
| materialid     |                  nan |              nan |                        nan |                    nan |              nan |                nan |                         7 |                                    1 |                            8 |                    nan |                    nan |                nan |                  nan |
| shortlabel     |                  nan |               16 |                        nan |                    nan |              nan |                 21 |                       nan |                                  nan |                          nan |                    nan |                    nan |                nan |                  nan |
| terseform      |                  608 |             1937 |                        nan |                    nan |              nan |               2932 |                       nan |                                  nan |                          nan |                    nan |                    nan |               2308 |                  989 |
| uniqueptid     |                  nan |              nan |                       3386 |                    nan |              nan |                nan |                       nan |                                  nan |                          nan |                    nan |                   3090 |                nan |                  nan |
| utccharttime   |               145436 |           156061 |                        nan |                  72595 |            96437 |              54617 |                     27232 |                                11887 |                        35691 |                    nan |                    nan |             130545 |               146810 |
| verboseform    |                  610 |             4782 |                        nan |                    nan |              nan |               9230 |                       nan |                                  nan |                          nan |                    nan |                    nan |               2923 |                 1420 |
| weight         |                  nan |              nan |                        470 |                    nan |              nan |                nan |                       nan |                                  nan |                          nan |                    nan |                    549 |                nan |                  nan |

## ID overlap with ai_picu_demographics.csv

|    | column      | file                               |   unique ids |   % in base |
|---:|:------------|:-----------------------------------|-------------:|------------:|
|  0 | encounterid | ai_picu_airway.csv                 |         4036 |         100 |
|  1 | encounterid | ai_picu_bg.csv                     |         3880 |         100 |
|  2 | encounterid | ai_picu_infusion.csv               |         2558 |         100 |
|  3 | encounterid | ai_picu_io.csv                     |         4024 |         100 |
|  4 | encounterid | ai_picu_labs.csv                   |         3838 |         100 |
|  5 | encounterid | ai_picu_medications.csv            |         2717 |         100 |
|  6 | encounterid | ai_picu_medications_furosemide.csv |         2076 |         100 |
|  7 | encounterid | ai_picu_medications_v2.csv         |         2879 |         100 |
|  8 | encounterid | ai_picu_outcomes.csv               |         4047 |         100 |
|  9 | encounterid | ai_picu_piccanet.csv               |         3709 |         100 |
| 10 | encounterid | ai_picu_vent.csv                   |         4036 |         100 |
| 11 | encounterid | ai_picu_vitals.csv                 |         4037 |         100 |
| 12 | uniqueptid  | ai_picu_piccanet.csv               |         3090 |           0 |

