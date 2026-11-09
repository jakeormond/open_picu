# Inventory: RBH
Generated 2026-11-09

# Files at a glance

| file | size MB | rows | columns | duplicate rows | encoding |
|---|---|---|---|---|---|
| ai_picu_airway.csv | 57.0 | 615369 | 8 | 0 | utf-8 |
| ai_picu_bg.csv | 102.7 | 555193 | 29 | 0 | utf-8 |
| ai_picu_biochemistry.csv | 23.3 | 149154 | 38 | 0 | utf-8 |
| ai_picu_coagulation.csv | 13.4 | 124556 | 14 | 0 | utf-8 |
| ai_picu_demographics.csv | 1.2 | 14799 | 8 | 0 | utf-8 |
| ai_picu_full_blood_count.csv | 18.0 | 129719 | 20 | 0 | utf-8 |
| ai_picu_infusion.csv | 115.5 | 731258 | 15 | 0 | utf-8 |
| ai_picu_io.csv | 375.4 | 2588228 | 43 | 0 | utf-8 |
| ai_picu_meds.csv | 51.0 | 331165 | 16 | 0 | utf-8 |
| ai_picu_outcomes.csv | 0.4 | 14797 | 3 | 0 | utf-8 |
| ai_picu_piccanet.csv | 1.0 | 4796 | 21 | 0 | utf-8 |
| ai_picu_piccanet_old.csv | 1.7 | 7928 | 21 | 0 | utf-8 |
| ai_picu_sedation.csv | 197.0 | 1193315 | 15 | 1 | utf-8 |
| ai_picu_sedation_old.csv | 79.1 | 484111 | 15 | 1 | utf-8 |
| ai_picu_temp.csv | 97.6 | 921045 | 10 | 0 | utf-8 |
| ai_picu_vent.csv | 325.8 | 1705956 | 39 | 0 | utf-8 |
| ai_picu_vitals.csv | 281.7 | 1957204 | 19 | 0 | utf-8 |

## ai_picu_airway.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 14797 | avg length 22; first value shape aaa:ddddddd:dddddddddd |
| Day | float64 | 1.5 | 299 | min 0; p1 0; median 7; p99 158; max 1717 |
| intv_hr | float64 | 1.5 | 6976 | min 0; p1 2; median 176; p99 3775; max 41224 |
| chartTime | str | 1.5 | 116879 | avg length 22; first value shape ddaaadddd:dd:dd:dd.ddd |
| sizeETT | float64 | 1.6 | 26 | min 0; p1 3; median 3.5; p99 7.5; max 12 |
| WARD_IN_dttm | str | 0.0 | 12438 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| PATIENT_RK | int64 | 0.0 | 10019 | min 84; p1 46712; median 1.02499e+06; p99 1.29767e+06; max 1.32331e+06 |
| PAS_AD_RK | int64 | 0.0 | 13285 | min 2; p1 17320; median 645215; p99 922418; max 936282 |

## ai_picu_bg.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 14797 | avg length 21; first value shape aaa:ddddddd:dddddddddd |
| PATIENT_RK | int64 | 0.0 | 10019 | min 84; p1 35578; median 231249; p99 1.28901e+06; max 1.32331e+06 |
| Day | float64 | 1.2 | 843 | min -358; p1 -223; median 3; p99 238; max 4126 |
| intv_hr | float64 | 1.2 | 15929 | min -8610; p1 -5350.07; median 72; p99 5707.07; max 99043 |
| SampleCollectDateTime | str | 1.2 | 374776 | avg length 22; first value shape ddaaadddd:dd:dd:dd.ddd |
| SampleTypeDesc | str | 11.3 | 33 | Arterial Blood: 153868; Arterial: 136551; Venous blood: 61757; Capillary: 29619; Mixed Venous: 24930; Venous (Jugular): 23838; Other: 17697; Venous (Femoral): 15680; Venous [Jugular]: 5529; Venous [Femoral]: 3285; Venous (Mixed/PA): 3205; ECMO: Post-oxy: 2658; Venous (Peripheral): 2384; Venous (Subclavian): 2221; Venous: 1804; Venous (Umbilical): 1493; .Select Option: 1343; Unknown: 1296; Venous [Mixed / PA]: 1291; Haemofilter: 463; MixedVenous: 444; Venous [Subclavian]: 299; Venous [Peripheral]: 251; Bypass Prime: 239; Venous [Umbilical]: 207; ECMO: Pre-oxy: 161; .Select Options: 110; Cord Blood Venous: 17; ECMO [Post-oxy]: 17; Cord Blood Arterial: 11; Calibration Verification: 5; Profiency Testing: 2; Fetal Scalp: 2 |
| pH | float64 | 2.1 | 124 | min 6.33; p1 7.19; median 7.39; p99 7.55; max 7.9 |
| Lactate | float64 | 1.9 | 173 | min -0.8; p1 0.5; median 1.3; p99 7.9; max 43 |
| pCO2 | float64 | 1.4 | 971 | min 0.3; p1 3.6; median 5.98; p99 10.5; max 39.1 |
| pO2 | float64 | 1.6 | 1513 | min 0.5; p1 2.96; median 6.41; p99 42.3; max 85.5 |
| HCO3 | float64 | 2.4 | 496 | min 4; p1 16.6; median 25.4; p99 39.9; max 55.7 |
| BE | float64 | 1.7 | 561 | min -29.7; p1 -9.5; median 1.8; p99 18.2; max 29.9 |
| Hb | float64 | 37.9 | 252 | min -1; p1 75; median 118; p99 181; max 268 |
| O2_Sat | float64 | 1.9 | 949 | min 1.6; p1 32.3; median 83.2; p99 100; max 102 |
| OxyHb | float64 | 5.0 | 944 | min 1.6; p1 31.6; median 81.3; p99 98.5; max 101.6 |
| CarboxyHb | float64 | 1.9 | 93 | min -2; p1 0.2; median 1.1; p99 2.8; max 7.2 |
| MetHb | float64 | 1.9 | 85 | min -2; p1 0.2; median 1; p99 2.2; max 21.3 |
| HHB | float64 | 1.9 | 936 | min -1.9; p1 0; median 16.4; p99 66.5; max 97.6 |
| Sodium | float64 | 1.9 | 109 | min 19; p1 127; median 139; p99 154; max 283 |
| Potassium | float64 | 1.9 | 270 | min 0.4; p1 2.6; median 3.8; p99 6.1; max 98.9 |
| Calcium | float64 | 2.0 | 313 | min 0.02; p1 0.88; median 1.22; p99 1.48; max 10 |
| Corr_Calcium | float64 | 3.8 | 261 | min 0.1; p1 0.87; median 1.22; p99 1.45; max 6.75 |
| Chloride | float64 | 1.5 | 113 | min 4; p1 86; median 106; p99 122; max 350 |
| Glucose | float64 | 1.8 | 352 | min 0; p1 3.2; median 6.1; p99 18; max 149 |
| Hydrogen_Ion | float64 | 2.1 | 1077 | min 12.6; p1 28.3; median 40.8; p99 65.3; max 471.7 |
| Anion_Gap_K | float64 | 57.3 | 411 | min -11.7; p1 4.8; median 11.1; p99 20.9; max 50.5 |
| Anion_Gap | float64 | 57.3 | 417 | min -16.9; p1 0.5; median 7.2; p99 16.9; max 46.5 |
| WARD_IN_dttm | str | 0.0 | 12438 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| PAS_AD_RK | int64 | 0.0 | 13285 | min 2; p1 5579; median 567624; p99 919474; max 936282 |

## ai_picu_biochemistry.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 14797 | avg length 21; first value shape aaa:ddddddd:dddddddddd |
| PATIENT_RK | int64 | 0.0 | 10019 | min 84; p1 10247; median 229848; p99 1.29033e+06; max 1.32331e+06 |
| Day | float64 | 3.8 | 956 | min -359; p1 -209; median 5; p99 269; max 9245 |
| intv_hr | float64 | 3.8 | 12134 | min -8619; p1 -5029; median 106; p99 6453; max 221896 |
| SampleCollectDateTime | str | 3.8 | 72808 | avg length 22; first value shape ddaaadddd:dd:dd:dd.ddd |
| CRP | float64 | 19.3 | 497 | min 0; p1 1; median 29; p99 307; max 601 |
| PCT | float64 | 99.3 | 338 | min 0.04; p1 0.05; median 0.57; p99 64.09; max 99.15 |
| Creatinine | float64 | 24.0 | 451 | min 1; p1 8; median 34; p99 196; max 901 |
| GFR | float64 | 99.9 | 58 | min 6; p1 12.18; median 61; p99 90; max 90 |
| Glucose | float64 | 21.6 | 384 | min 0; p1 2.7; median 5.4; p99 15.5; max 177.6 |
| Albumin | float64 | 13.4 | 48 | min 10; p1 13; median 28; p99 46; max 57 |
| Protein_Tot | float64 | 17.9 | 87 | min 10; p1 27; median 48; p99 76; max 185 |
| ALT | float64 | 15.1 | 1294 | min 3; p1 6; median 21; p99 571; max 9309 |
| AST | float64 | 29.4 | 1319 | min 5; p1 13; median 35; p99 665.32; max 17792 |
| ALP | float64 | 14.8 | 1016 | min 5; p1 33; median 147; p99 606.18; max 5281 |
| GGT | float64 | 99.4 | 264 | min 6; p1 7.57; median 72; p99 1078; max 1850 |
| Bilirubin | float64 | 17.0 | 473 | min 1; p1 2; median 11; p99 245; max 804 |
| Amylase | float64 | 98.9 | 303 | min 0; p1 2; median 63; p99 786.76; max 5559 |
| Sodium | float64 | 10.1 | 65 | min 86; p1 128; median 138; p99 153; max 187 |
| Potassium | float64 | 16.8 | 103 | min 1.4; p1 2.8; median 4.2; p99 6.3; max 17.9 |
| Urea | float64 | 10.7 | 399 | min 0; p1 0.9; median 4.9; p99 23.6; max 82.4 |
| Calcium | float64 | 14.7 | 304 | min 0.13; p1 1.53; median 2.24; p99 2.82; max 5.98 |
| Corr_calcium | float64 | 15.5 | 299 | min 0.03; p1 1.86; median 2.5; p99 2.93; max 5.09 |
| Phosphate | float64 | 16.8 | 468 | min 0.3; p1 0.78; median 1.8; p99 3.38; max 10.37 |
| Magnesium | float64 | 18.9 | 366 | min 0.09; p1 0.6; median 0.91; p99 2.01; max 9.17 |
| CK | float64 | 98.0 | 807 | min 6; p1 11; median 96; p99 18952.4; max 246686 |
| Troponin_T | float64 | 100.0 | 0 | all missing |
| Troponin_I | float64 | 93.4 | 3809 | min 0.04; p1 0.05; median 54; p99 40147.2; max 101000 |
| BNP | float64 | 97.3 | 1211 | min 2; p1 13; median 318; p99 4693; max 5032 |
| Iron | float64 | 99.5 | 211 | min 0.6; p1 1.095; median 8.65; p99 39.44; max 47.7 |
| Ferritin | float64 | 98.6 | 860 | min 2; p1 4; median 260; p99 2410.78; max 6927 |
| TIBC | float64 | 99.4 | 41 | min 15; p1 20; median 63; p99 115; max 130 |
| Transferrin_saturation | float64 | 99.5 | 70 | min 1; p1 2; median 14; p99 74.36; max 131 |
| Transferrin | float64 | 99.4 | 41 | min 0.6; p1 0.8; median 2.4; p99 4.6; max 5.2 |
| Free_T4 | float64 | 98.1 | 289 | min 2.3; p1 4.5; median 14.1; p99 42.51; max 65.1 |
| Tot_CO2 | float64 | 99.9 | 23 | min 5; p1 10.08; median 25; p99 36; max 36 |
| WARD_IN_dttm | str | 0.0 | 12438 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| PAS_AD_RK | int64 | 0.0 | 13285 | min 2; p1 5983; median 522317; p99 920324; max 936282 |

## ai_picu_coagulation.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 14797 | avg length 21; first value shape aaa:ddddddd:dddddddddd |
| PATIENT_RK | int64 | 0.0 | 10019 | min 84; p1 9128; median 228907; p99 1.28261e+06; max 1.32331e+06 |
| Day | float64 | 4.9 | 808 | min -359; p1 -213; median 4; p99 247; max 7592 |
| intv_hr | float64 | 4.9 | 11259 | min -8619; p1 -5107.4; median 91; p99 5930.4; max 182224 |
| SampleCollectDateTime | str | 4.9 | 60990 | avg length 22; first value shape ddaaadddd:dd:dd:dd.ddd |
| INR | float64 | 15.6 | 109 | min 0.7; p1 0.9; median 1.2; p99 3.5; max 19.1 |
| APTT | float64 | 13.7 | 2254 | min 15.1; p1 22.8; median 41.9; p99 215.8; max 360.1 |
| PT | float64 | 11.1 | 656 | min 8.2; p1 10.3; median 14; p99 40.9; max 233 |
| Fibrinogen | float64 | 24.5 | 128 | min 0.2; p1 0.8; median 2.7; p99 7; max 11.9 |
| Hep_Conc | float64 | 58.0 | 379 | min 0; p1 0; median 0.32; p99 1.46; max 31.4 |
| D_Dimer | float64 | 97.3 | 2084 | min 0; p1 115.66; median 2205; p99 45609.6; max 124100 |
| LDH | float64 | 98.7 | 838 | min 130; p1 321; median 806; p99 4525.3; max 24846 |
| WARD_IN_dttm | str | 0.0 | 12438 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| PAS_AD_RK | int64 | 0.0 | 13285 | min 2; p1 6223.75; median 522317; p99 916596; max 936282 |

## ai_picu_demographics.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 14797 | avg length 21; first value shape aaa:ddddddd:dddddddddd |
| PATIENT_RK | int64 | 0.0 | 10019 | min 84; p1 7343; median 580687; p99 1.29033e+06; max 1.32331e+06 |
| Age_mth | int64 | 0.0 | 253 | min 0; p1 0; median 8; p99 191; max 934 |
| Gender | int64 | 0.0 | 3 | min 1; p1 1; median 1; p99 2; max 9 / values -> 1: 8311; 2: 6480; 9: 8 |
| Ethnicity | str | 29.8 | 17 | White British: 5388; Not stated: 1068; White Any other: 729; Black or Black British African: 558; Asian or Asian British Indian: 489; Asian or Asian British Any other: 401; Other Ethnic Any other: 352; Asian or Asian British Pakistani: 314; Black or Black British Caribbean: 227; Mixed White and Asian: 185; Mixed Any other: 146; Asian or Asian British Bangladeshi: 139; Mixed White and Black Caribbean: 118; Black or Black British Any other: 99; Mixed White and Black African: 70; White Irish: 60; Other Ethnic Chinese: 41 |
| Weight_kg | float64 | 51.2 | 591 | min 0.6; p1 1; median 7; p99 76.158; max 175 |
| PICUadm_dttm | str | 0.0 | 12438 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| PAS_AD_RK | int64 | 0.0 | 13285 | min 2; p1 8611.72; median 430974; p99 921398; max 936282 |

## ai_picu_full_blood_count.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 14797 | avg length 21; first value shape aaa:ddddddd:dddddddddd |
| PATIENT_RK | int64 | 0.0 | 10019 | min 84; p1 10247; median 224681; p99 1.28901e+06; max 1.32331e+06 |
| Day | float64 | 4.5 | 918 | min -359; p1 -212; median 4; p99 256; max 9245 |
| intv_hr | float64 | 4.5 | 11426 | min -8619; p1 -5088.55; median 93; p99 6128.1; max 221891 |
| SampleCollectDateTime | str | 4.5 | 63347 | avg length 22; first value shape ddaaadddd:dd:dd:dd.ddd |
| Hb | float64 | 4.9 | 383 | min 0.1; p1 8.2; median 92; p99 171; max 250 |
| WBC | float64 | 4.8 | 557 | min 0; p1 3.3; median 11.2; p99 33.3; max 209.4 |
| Neut | float64 | 4.9 | 1750 | min 0; p1 1.1; median 6.6; p99 26.6; max 129.8 |
| Lymph | float64 | 4.9 | 893 | min 0; p1 0.2; median 2.4; p99 9.3; max 104.3 |
| MonoC | float64 | 4.9 | 426 | min 0; p1 0.1; median 1.1; p99 4.1; max 48.2 |
| Eosinoph | float64 | 4.9 | 229 | min 0; p1 0; median 0.2; p99 1.7; max 49.7 |
| Basoph | float64 | 5.0 | 74 | min 0; p1 0; median 0; p99 0.4; max 3.6 |
| Plt | float64 | 5.0 | 1074 | min 1; p1 31; median 209; p99 735; max 1586 |
| PCV | float64 | 4.8 | 72 | min 0; p1 0.22; median 0.35; p99 0.53; max 30 |
| RBC | float64 | 4.8 | 686 | min 0; p1 2.48; median 4.01; p99 6.15; max 12.21 |
| MCV | float64 | 4.8 | 183 | min 50; p1 69; median 87; p99 109; max 131 |
| MCH | float64 | 4.8 | 284 | min 5.6; p1 22.2; median 29.6; p99 37.6; max 46.9 |
| MCHC | float64 | 4.9 | 263 | min 6.7; p1 31.7; median 323; p99 357; max 469 |
| WARD_IN_dttm | str | 0.0 | 12438 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| PAS_AD_RK | int64 | 0.0 | 13285 | min 2; p1 5652; median 509620; p99 919474; max 936282 |

## ai_picu_infusion.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 2884 | avg length 21; first value shape aaa:ddddddd:dddddddddd |
| PATIENT_RK | int64 | 0.0 | 2215 | min 433; p1 53939; median 236773; p99 1.13717e+06; max 1.29766e+06 |
| Weight_kg | float64 | 1.6 | 377 | min 0.6; p1 2.2; median 5; p99 55.5; max 175 |
| Day | int64 | 0.0 | 305 | min 0; p1 0; median 8; p99 198; max 440 |
| intv_hr | int64 | 0.0 | 7213 | min 0; p1 3; median 182; p99 4742.43; max 10556 |
| chartTime | str | 0.0 | 95031 | avg length 22; first value shape ddaaadddd:dd:dd:dd.ddd |
| Drug | str | 0.0 | 7 | MILRINONE: 344348; FUROSEMIDE: 171716; ADRENALINE: 136193; NORADRENALINE: 69246; VASOPRESSIN: 7215; DOPAMINE: 2029; DOBUTAMINE: 511 |
| Dose | float64 | 0.0 | 3596 | min 3.7244e-05; p1 0.01; median 0.3; p99 1; max 20 |
| Dose_Unit | str | 0.0 | 6 | mcg/kg/min: 552327; mg/kg/hr: 170650; Units/kg/min: 6410; mg/hr: 1065; Units/min: 805; mg: 1 |
| Rate_Unit | str | 0.0 | 1 | ml/hr: 731189 |
| WARD_IN_dttm | str | 0.0 | 2868 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| LOS | int64 | 0.0 | 721 | min 0; p1 31; median 562; p99 6730; max 60318 |
| WARD_OUT_dttm | str | 0.1 | 2551 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| PAS_AD_RK | int64 | 0.0 | 2688 | min 391; p1 17157; median 604429; p99 779943; max 920192 |
| encounterId | int64 | 0.0 | 2785 | min 92; p1 4203; median 32682; p99 76811; max 135811 |

## ai_picu_io.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 14797 | avg length 21; first value shape aaa:ddddddd:dddddddddd |
| PATIENT_RK | int64 | 0.0 | 10019 | min 84; p1 46712; median 1.02013e+06; p99 1.2976e+06; max 1.32331e+06 |
| Weight_kg | float64 | 0.9 | 591 | min 0.6; p1 2; median 5.9; p99 82; max 175 |
| RRT | str | 86.2 | 1 | RRT: 356503 |
| Day | float64 | 0.3 | 982 | min -359; p1 -220; median 9; p99 335; max 1540 |
| intv_hr | float64 | 0.3 | 22708 | min -8619; p1 -5285; median 203; p99 8045; max 36954 |
| chartTime | str | 0.3 | 144850 | avg length 22; first value shape ddaaadddd:dd:dd:dd.ddd |
| bolus_CSL | float64 | 99.4 | 263 | min 1; p1 5; median 28; p99 340; max 550 |
| bolus_NACL | float64 | 99.9 | 118 | min 0.2; p1 1; median 5; p99 200; max 500 |
| bolus_ISOPLEX | float64 | 100.0 | 54 | min 5; p1 10; median 25; p99 260; max 400 |
| bolus_PLASMALYTE | float64 | 99.7 | 204 | min 1; p1 6; median 32; p99 400; max 500 |
| bolus_ALBUMIN5 | float64 | 100.0 | 70 | min 4; p1 5.78; median 35; p99 500; max 640 |
| bolus_ALBUMIN20 | float64 | 100.0 | 48 | min 5; p1 5; median 25; p99 167.5; max 500 |
| CT_Output | float64 | 70.8 | 239 | min 0; p1 0; median 0; p99 55; max 2150 |
| Drain_Output | float64 | 97.2 | 170 | min 0; p1 0; median 0; p99 110; max 1027 |
| Urine_Output | float64 | 38.5 | 854 | min 0; p1 0; median 13; p99 240; max 2000 |
| Blood_In | float64 | 75.2 | 827 | min 0; p1 0; median 0; p99 200; max 3977 |
| IV_Infusion | float64 | 21.7 | 3408 | min 0; p1 0; median 6; p99 77.2; max 3013 |
| Total_In_ex_dialysis | float64 | 9.9 | 6724 | min -921.5; p1 0; median 22.8; p99 224.9; max 11349 |
| Total_Out_ex_dialysis | float64 | 34.7 | 1137 | min 0; p1 0; median 20; p99 254; max 2150 |
| Net_Body_Balance | float64 | 1.4 | 11717 | min -5400; p1 -178.5; median 4.5; p99 185; max 13989 |
| Dialysis_In | float64 | 98.7 | 1611 | min 0; p1 0; median 30; p99 2742; max 11306 |
| Ultrafiltrate_Out | float64 | 100.0 | 1 | min 0; p1 0; median 0; p99 0; max 0 / values -> 0.0: 6 |
| Dialysis_Out | float64 | 98.4 | 1832 | min 0; p1 0; median 25; p99 2619.64; max 11316 |
| Dialysis_Net_Balance | float64 | 98.1 | 600 | min -3728; p1 -244; median -8; p99 80; max 2777 |
| TOTAL_IN | float64 | 93.8 | 3941 | min 0; p1 0; median 0; p99 203.96; max 3677.74 |
| TOTAL_OUT | float64 | 95.8 | 419 | min -600; p1 0; median 0; p99 215; max 2148 |
| IV_Meds | float64 | 60.3 | 4317 | min 0; p1 0; median 0; p99 85; max 10048.6 |
| Colloids | float64 | 77.4 | 263 | min 0; p1 0; median 0; p99 80; max 3000 |
| Enteral_PO | float64 | 80.6 | 494 | min 0; p1 0; median 26; p99 165; max 1500 |
| PO_NG_Intake | float64 | 90.8 | 349 | min 0; p1 0; median 23; p99 175; max 1100.42 |
| PD_In | float64 | 99.9 | 8 | min 0; p1 0; median 0; p99 36; max 100 / values -> 0.0: 1911; 24.0: 205; 36.0: 169; 25.0: 136; 40.0: 2; 100.0: 2; 72.0: 1; 96.0: 1 |
| Stool_Output | float64 | 97.9 | 319 | min 0; p1 0; median 0; p99 176.57; max 850 |
| GI_Output | float64 | 98.7 | 133 | min 0; p1 0; median 0; p99 60; max 840 |
| Misc_Output | float64 | 99.7 | 121 | min 0; p1 0; median 0; p99 193; max 615 |
| TPN | float64 | 94.7 | 1503 | min 0; p1 0; median 10.9; p99 74.8; max 532 |
| Calories | float64 | 97.4 | 1099 | min 0; p1 0; median 48.8; p99 180; max 1520 |
| Calories_new | float64 | 100.0 | 25 | min 0; p1 0; median 37.37; p99 150; max 161.6 |
| Protein | float64 | 98.1 | 778 | min 0; p1 0; median 3.33; p99 8.4; max 89.4639 |
| Fats | float64 | 97.4 | 998 | min 0; p1 0; median 1.9485; p99 7.47; max 74.7 |
| Carbohydrates | float64 | 98.2 | 969 | min 0; p1 0; median 7.81; p99 24.16; max 167 |
| WARD_IN_dttm | str | 0.0 | 12438 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| PAS_AD_RK | int64 | 0.0 | 13285 | min 2; p1 20245; median 650059; p99 922650; max 936282 |

## ai_picu_meds.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 5109 | avg length 21; first value shape aaa:ddddddd:dddddddddd |
| PATIENT_RK | int64 | 0.0 | 3694 | min 433; p1 69872; median 243617; p99 1.28794e+06; max 1.32331e+06 |
| Weight_kg | float64 | 2.2 | 475 | min 0.6; p1 2.2; median 5.2; p99 59.344; max 175 |
| Day | int64 | 0.0 | 359 | min 0; p1 0; median 10; p99 214; max 1545 |
| intv_hr | int64 | 0.0 | 7020 | min 0; p1 7; median 233; p99 5135; max 37071 |
| chartTime | str | 0.0 | 101290 | avg length 22; first value shape ddaaadddd:dd:dd:dd.ddd |
| Drug | str | 0.0 | 6 | FUROSEMIDE: 252402; SPIRONOLACTONE: 50025; CHLOROTHIAZIDE: 14806; HYDROCORTISONE: 7618; DEXAMETHASONE: 5815; METHYLPREDNISOLONE: 499 |
| Route | str | 51.9 | 9 | NG: 95036; IV Bolus: 48703; PO: 7232; NJ: 5299; PEG: 1144; PEJ: 929; IV Infusion: 734; Topical: 197; IV: 170 |
| Dose | float64 | 0.0 | 1042 | min 0.00119048; p1 0.0512821; median 0.5; p99 80; max 1000 |
| Dose_Unit | str | 0.0 | 4 | mg/kg/hr: 170650; mg: 159253; mg/hr: 1065; Appl: 197 |
| Rate_Unit | str | 48.1 | 1 | ml/hr: 171713 |
| WARD_IN_dttm | str | 0.0 | 5071 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| LOS | int64 | 0.0 | 876 | min 2; p1 36; median 642; p99 8344; max 60318 |
| WARD_OUT_dttm | str | 0.2 | 4587 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| PAS_AD_RK | int64 | 0.0 | 4682 | min 391; p1 19868; median 616920; p99 920324; max 936282 |
| encounterId | int64 | 0.0 | 4916 | min 92; p1 4175; median 33953; p99 136230; max 146975 |

## ai_picu_outcomes.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 14797 | avg length 21; first value shape aaa:ddddddd:dddddddddd |
| picuLOS | int64 | 0.0 | 1004 | min -1744; p1 3; median 53; p99 1676.08; max 75541 |
| picuMortality | int64 | 0.0 | 2 | min 0; p1 0; median 0; p99 1; max 1 / values -> 0: 14293; 1: 504 |

## ai_picu_piccanet.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 4795 | avg length 22; first value shape aaa:ddddddd:dddddddddd |
| AgeDays | float64 | 7.6 | 1778 | min 0; p1 0; median 224; p99 5792.87; max 6549 |
| AgeMonths | float64 | 7.6 | 204 | min 0; p1 0; median 7; p99 189.69; max 215 |
| AgeYears | float64 | 7.6 | 18 | min 0; p1 0; median 0; p99 15; max 17 |
| Gender | float64 | 7.6 | 3 | min 1; p1 1; median 1; p99 2; max 3 / values -> 1.0: 2467; 2.0: 1964; 3.0: 1 |
| EthnicDescription | str | 7.6 | 17 | Not stated: 2716; White British: 994; Asian Indian: 169; Black African: 158; Asian Pakistani: 108; Mixed White and Asian: 65; Black Caribbean: 51; Asian Bangladeshi: 44; Unknown: 36; Mixed White and Black Caribbean: 35; Mixed White and Black African: 22; White Irish: 14; Asian other: 5; Chinese: 5; Other: 4; White other: 4; Mixed other: 2 |
| EthnicOther | str | 99.7 | 11 | Arabic: 2; Arab: 1; Mixed any other background: 1; Caucasian: 1; Albanian: 1; Polish: 1; Kurdish: 1; Palestine: 1; Mediterranean: 1; Kuwaiti: 1; Tamil: 1 |
| Weight | float64 | 8.9 | 536 | min 0.28; p1 1; median 7.1; p99 999; max 999 |
| AdDateTime | str | 7.6 | 4383 | avg length 18; first value shape ddaaadddd:dd:dd:dd |
| AdDate | str | 7.6 | 2456 | datetime 2013-01-02 00:00:00 to 2022-12-31 00:00:00 (parsed day-first); format ddaaadddd |
| AdTime | str | 7.6 | 608 | avg length 5; first value shape d:dd |
| LOSHours | float64 | 7.6 | 684 | min 1; p1 5; median 74; p99 1840.76; max 11013 |
| UnitDisDateTime | str | 7.6 | 4363 | avg length 18; first value shape ddaaadddd:dd:dd:dd |
| PrimaryDiagnosisGroup | str | 7.6 | 13 | Cardiovascular: 3784; Respiratory: 395; Gastrointestinal: 55; Oncology: 44; Other: 38; Infection: 36; Neurological: 25; Unknown: 18; Endocrine / metabolic: 14; Musculoskeletal: 12; Body wall and cavities: 8; Multisystem: 2; Trauma: 1 |
| SecDescriptions | str | 19.9 | 2386 | avg length 78; first value shape aaaaaaaaaaa aa aaaaaaaaa aaaaaa/aaaaa aaaaaa aaaaaaaaa/aaa   aaaaaa aaaaaa aaaaaa/aaaa  aaaaaaaa aaaaaaaaaaaaaaaa aaaaaa aaaaaa/aaaaa aaaaaa aaaa aaa aaaa aaaaaaaaaa aaaaa/aaaaa |
| PIM3 | float64 | 7.6 | 4056 | min 0.000865982; p1 0.00178666; median 0.0168047; p99 0.362341; max 0.945531 |
| VentilationStatus | str | 7.6 | 4 | Invasive only: 2135; Neither: 1156; Both: 893; Non-invasive only: 248 |
| InTubeDays | float64 | 7.6 | 74 | min 0; p1 0; median 2; p99 41; max 231 |
| TrachDays | float64 | 7.6 | 34 | min 0; p1 0; median 0; p99 7; max 225 |
| UnplannedExtubation | float64 | 99.5 | 2 | min 1; p1 1; median 1; p99 1.75; max 2 / values -> 1.0: 25; 2.0: 1 |
| EventID | float64 | 7.6 | 4404 | min 408218; p1 409417; median 683328; p99 884821; max 889517 |

## ai_picu_piccanet_old.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 7926 | avg length 22; first value shape aaa:ddddddd:dddddddddd |
| AgeDays | float64 | 10.2 | 1799 | min 0; p1 0; median 225; p99 5678.1; max 6549 |
| AgeMonths | float64 | 10.2 | 204 | min 0; p1 0; median 7; p99 186; max 215 |
| AgeYears | float64 | 10.2 | 18 | min 0; p1 0; median 0; p99 15; max 17 |
| Gender | float64 | 10.2 | 3 | min 1; p1 1; median 1; p99 2; max 3 / values -> 1.0: 4015; 2.0: 3100; 3.0: 1 |
| EthnicDescription | str | 10.2 | 17 | Not stated: 4208; White British: 1701; Asian Indian: 289; Black African: 257; Asian Pakistani: 185; Mixed White and Asian: 105; Black Caribbean: 90; Asian Bangladeshi: 70; Mixed White and Black Caribbean: 63; Unknown: 62; Mixed White and Black African: 32; White Irish: 24; Asian other: 9; White other: 7; Chinese: 7; Other: 5; Mixed other: 2 |
| EthnicOther | str | 99.8 | 11 | Arabic: 3; Polish: 2; Kurdish: 2; Palestine: 2; Kuwaiti: 2; Arab: 1; Mixed any other background: 1; Caucasian: 1; Albanian: 1; Mediterranean: 1; Tamil: 1 |
| Weight | float64 | 11.5 | 544 | min 0.28; p1 1; median 7.2; p99 999; max 999 |
| AdDateTime | str | 10.2 | 4673 | avg length 18; first value shape ddaaadddd:dd:dd:dd |
| AdDate | str | 10.2 | 2540 | datetime 2013-01-01 00:00:00 to 2022-12-31 00:00:00 (parsed day-first); format ddaaadddd |
| AdTime | str | 10.2 | 632 | avg length 5; first value shape dd:dd |
| LOSHours | float64 | 10.2 | 720 | min 1; p1 5; median 75; p99 1801.4; max 11013 |
| UnitDisDateTime | str | 10.2 | 4654 | avg length 18; first value shape ddaaadddd:dd:dd:dd |
| PrimaryDiagnosisGroup | str | 10.2 | 13 | Cardiovascular: 6383; Respiratory: 440; Gastrointestinal: 64; Other: 46; Infection: 45; Oncology: 44; Neurological: 29; Unknown: 22; Musculoskeletal: 16; Endocrine / metabolic: 15; Body wall and cavities: 9; Multisystem: 2; Trauma: 1 |
| SecDescriptions | str | 20.3 | 2535 | avg length 79; first value shape aaaaaaa/aaaa (aaaaaaa aaaa) |
| PIM3 | float64 | 10.2 | 4289 | min 0.000865982; p1 0.00190709; median 0.0156148; p99 0.336888; max 0.945531 |
| VentilationStatus | str | 10.2 | 4 | Invasive only: 3635; Neither: 1631; Both: 1492; Non-invasive only: 358 |
| InTubeDays | float64 | 10.2 | 77 | min 0; p1 0; median 2; p99 39; max 231 |
| TrachDays | float64 | 10.2 | 34 | min 0; p1 0; median 0; p99 3; max 225 |
| UnplannedExtubation | float64 | 99.6 | 2 | min 1; p1 1; median 1; p99 1.69; max 2 / values -> 1.0: 31; 2.0: 1 |
| EventID | float64 | 10.2 | 4700 | min 408217; p1 409417; median 677834; p99 884808; max 889535 |

## ai_picu_sedation.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 7576 | avg length 22; first value shape aaa:ddddddd:dddddddddd |
| PATIENT_RK | int64 | 0.0 | 3501 | min 433; p1 80109; median 1.03503e+06; p99 1.2818e+06; max 1.3371e+06 |
| Weight_kg | float64 | 2.0 | 519 | min 0.6; p1 2; median 5.9; p99 98; max 175 |
| Day | int64 | 0.0 | 334 | min 0; p1 0; median 8; p99 168; max 2041 |
| intv_hr | int64 | 0.0 | 6866 | min 0; p1 2; median 192; p99 4030; max 48981 |
| chartTime | str | 0.0 | 160530 | avg length 22; first value shape ddaaadddd:dd:dd:dd.ddd |
| Drug | str | 0.0 | 11 | MORPHINE SULPHATE IV: 506168; CLONIDINE: 251464; MIDAZOLAM: 157675; FENTANYL: 106192; MORPHINE SULPHATE: 63104; VECURONIUM: 60947; ATRACURIUM: 23943; PROPOFOL: 9192; KETAMINE: 8316; DEXMEDETOMIDINE: 6285; REMIFENTANIL: 29 |
| Dose | float64 | 0.0 | 3842 | min 0.01; p1 0.1; median 10; p99 600; max 2000 |
| Dose_Unit | str | 0.0 | 8 | microgram/kg/hr: 907070; mg: 159289; micrograms: 81652; mg/hr: 29471; micrograms/hr: 10649; mg/kg/hr: 2921; mcg/kg/min: 2214; ug/ml: 49 |
| Rate_Unit | str | 20.2 | 1 | ml/hr: 952324 |
| WARD_IN_dttm | str | 0.0 | 5077 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| LOS | int64 | 0.0 | 952 | min 1; p1 22; median 584; p99 8344; max 65944 |
| WARD_OUT_dttm | str | 0.1 | 4623 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| PAS_AD_RK | int64 | 0.0 | 4312 | min 2094; p1 21727; median 671719; p99 919575; max 946225 |
| encounterId | int64 | 0.0 | 4577 | min 17413; p1 17914; median 45737; p99 135592; max 153341 |

## ai_picu_sedation_old.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 2613 | avg length 21; first value shape aaa:ddddddd:dddddddddd |
| PATIENT_RK | int64 | 0.0 | 2069 | min 557; p1 53939; median 244772; p99 1.20145e+06; max 1.29913e+06 |
| Weight_kg | float64 | 2.8 | 408 | min 0.6; p1 2.2; median 6.1; p99 100; max 136 |
| Day | int64 | 0.0 | 275 | min 0; p1 0; median 11; p99 182; max 439 |
| intv_hr | int64 | 0.0 | 6434 | min 0; p1 3; median 258; p99 4371.9; max 10525 |
| chartTime | str | 0.0 | 88391 | avg length 22; first value shape ddaaadddd:dd:dd:dd.ddd |
| Drug | str | 0.0 | 10 | CLONIDINE: 204466; MIDAZOLAM: 136385; FENTANYL: 59897; VECURONIUM: 51255; ATRACURIUM: 18449; PROPOFOL: 7734; DEXMEDETOMIDINE: 3678; KETAMINE: 2188; REMIFENTANIL: 50; MORPHINE SULPHATE: 9 |
| Dose | float64 | 0.0 | 3460 | min 0.0057971; p1 0.48; median 3.5; p99 900; max 1700 |
| Dose_Unit | str | 0.0 | 7 | microgram/kg/hr: 457515; mg/hr: 12324; micrograms/hr: 9282; mg/kg/hr: 2744; mcg/kg/min: 2238; mg: 7; micrograms: 1 |
| Rate_Unit | str | 0.0 | 1 | ml/hr: 484103 |
| WARD_IN_dttm | str | 0.0 | 2598 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| LOS | int64 | 0.0 | 722 | min 2; p1 41; median 779; p99 8344; max 60318 |
| WARD_OUT_dttm | str | 0.1 | 2355 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| PAS_AD_RK | int64 | 0.0 | 2441 | min 590; p1 14754; median 618670; p99 866302; max 926657 |
| encounterId | int64 | 0.0 | 2532 | min 902; p1 4351; median 34446; p99 107599; max 140301 |

## ai_picu_temp.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 14797 | avg length 22; first value shape aaa:ddddddd:dddddddddd |
| PATIENT_RK | int64 | 0.0 | 10019 | min 84; p1 53533; median 1.03373e+06; p99 1.29834e+06; max 1.32331e+06 |
| Day | float64 | 0.9 | 376 | min 0; p1 0; median 6; p99 166; max 1545 |
| intv_hr | float64 | 0.9 | 7411 | min 0; p1 1; median 134; p99 3974; max 37081 |
| chartTime | str | 0.9 | 295280 | avg length 22; first value shape ddaaadddd:dd:dd:dd.ddd |
| clinicalUnit | str | 0.9 | 2 | RBH-PICU: 855681; RBH-Theatre: 57305 |
| centralTemp_C | float64 | 25.1 | 310 | min 0.2; p1 28.2; median 36.7; p99 38.4; max 45 |
| periphTemp_C | float64 | 24.6 | 322 | min 0.2; p1 24.3; median 32.5; p99 37.3; max 41.3 |
| WARD_IN_dttm | str | 0.0 | 12438 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| PAS_AD_RK | int64 | 0.0 | 13285 | min 2; p1 20050; median 674048; p99 923496; max 936282 |

## ai_picu_vent.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 14797 | avg length 22; first value shape aaa:ddddddd:dddddddddd |
| PATIENT_RK | int64 | 0.0 | 10019 | min 84; p1 51953; median 1.04888e+06; p99 1.30342e+06; max 1.32331e+06 |
| Weight_kg | float64 | 2.9 | 591 | min 0.6; p1 1.6; median 5.4; p99 80; max 175 |
| Day | float64 | 0.5 | 389 | min 0; p1 0; median 7; p99 185; max 1717 |
| intv_hr | float64 | 0.5 | 9168 | min 0; p1 0; median 161; p99 4438; max 41225 |
| chartTime | str | 0.5 | 481990 | avg length 22; first value shape ddaaadddd:dd:dd:dd.ddd |
| clinicalUnit | str | 0.5 | 9 | RBH-PICU: 1404238; RBH-PHDU: 191702; RBH-Theatre: 89169; RBH-Cath: 12491; RBH-Reginald-Wilson: 340; RBH-Recovery: 73; RBH-AICU: 20; RBH-Alex: 14; RBH-EICU/EHDU: 5 |
| Ventilation_Mode | str | 29.4 | 29 | BiPAP: 507660; Self Vent: 307031; CPAP: 154159; Nasal High Flow: 58407; PC-BIPAP: 53387; CPAP+Pressure Support: 31134; BILEVEL: 27261; SIMV: 18483; SIMV + PS: 9995; VC-SIMV: 8961; HFOV: 8070; High Flow: 7675; SPN-CPAP/PS: 5430; NIV: 2522; PCV: 1306; ASB: 1296; PC-SIMV: 569; IPPV: 211; BIPAP-APRV: 190; BIPAP-SIMV: 189; T Piece: 171; PC-APRV: 171; SPN-CPAP/VS: 116; CMV: 34; PC-AC: 32; SIPPV: 18; SPN-PPS: 10; VC-MMV: 10; PAV: 9 |
| Airway | str | 29.8 | 1074 | avg length 8; first value shape aaaa aaa |
| Airway_Events | str | 63.9 | 9 | Tube Insitu: 601493; Intubated: 7628; Extubated: 5374; Throat pack OUT: 629; Trachy performed: 291; Throat pack IN: 36; Trachy removed: 31; Self extubation: 21; Accidental extubation: 21 |
| SpO2 | float64 | 7.8 | 101 | min 0; p1 67; median 97; p99 100; max 100 |
| FiO2 | float64 | 34.6 | 83 | min 18; p1 21; median 30; p99 100; max 100 |
| End_Tidal_CO2 | float64 | 47.8 | 228 | min 0; p1 1.2; median 4.8; p99 8.3; max 40 |
| Inspired_O2 | float64 | 95.5 | 98 | min 0; p1 19; median 50; p99 100; max 100 |
| FiO2_L_min | float64 | 100.0 | 0 | all missing |
| Spont_Resp_Rate | float64 | 48.7 | 207 | min 0; p1 0; median 15; p99 64; max 262 |
| Vent_Rate | float64 | 50.2 | 101 | min 0; p1 0; median 24; p99 55; max 100 |
| NIV_backup_rate | float64 | 100.0 | 0 | all missing |
| Total_Resp_Rate | float64 | 26.3 | 172 | min 0; p1 10; median 30; p99 69; max 300 |
| Tidal_Volume | float64 | 51.7 | 943 | min 0; p1 3; median 36; p99 455.73; max 1996 |
| Vt_Kg | float64 | 100.0 | 0 | all missing |
| Spont_Minute_Volume | float64 | 65.5 | 46 | min 0; p1 0; median 0; p99 5; max 49 |
| Expired_Minute_Volume | float64 | 50.6 | 51 | min 0; p1 0; median 1; p99 9; max 50 |
| Peak_Insp_Press_mBar | float64 | 47.9 | 72 | min -1; p1 0; median 19; p99 32; max 91 |
| Mean_Airway_Pressure | float64 | 48.7 | 56 | min -10; p1 0; median 10; p99 19; max 90 |
| PEEP | float64 | 42.6 | 44 | min 0; p1 3; median 5; p99 13; max 50 |
| Jet_Vent_RR | float64 | 100.0 | 0 | all missing |
| HFOV_Frequency | float64 | 100.0 | 0 | all missing |
| HFOV_Amplitude | float64 | 100.0 | 0 | all missing |
| Vent_Days | float64 | 100.0 | 0 | all missing |
| Insp_Ratio | float64 | 53.4 | 50 | min 0; p1 1; median 1; p99 1; max 5 |
| Exp_Ratio | float64 | 53.3 | 101 | min 0; p1 1; median 2.3; p99 7.6; max 10 |
| IE_Ratio | str | 0.5 | 476 | avg length 4; first value shape .:. |
| Plateau_Pressure | float64 | 77.4 | 59 | min -2; p1 11; median 20; p99 31; max 86 |
| Compliance_Dynamic | float64 | 57.3 | 201 | min 0; p1 0; median 3; p99 60; max 200 |
| PAS_AD_RK | int64 | 0.0 | 13285 | min 2; p1 23947; median 693900; p99 926901; max 936282 |
| WARD_IN_dttm | str | 0.0 | 12438 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| LOS | int64 | 0.0 | 1004 | min -1744; p1 17; median 455; p99 6730; max 75541 |
| WARD_OUT_dttm | str | 0.4 | 11544 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |

## ai_picu_vitals.csv

| column | dtype | missing % | unique | detail |
|---|---|---|---|---|
| studyID | str | 0.0 | 14797 | avg length 22; first value shape aaa:ddddddd:dddddddddd |
| PATIENT_RK | int64 | 0.0 | 10019 | min 84; p1 53533; median 1.04646e+06; p99 1.30342e+06; max 1.32331e+06 |
| Weight_kg | float64 | 2.9 | 591 | min 0.6; p1 1.3; median 5.4; p99 80; max 175 |
| Day | float64 | 0.4 | 389 | min 0; p1 0; median 6; p99 182; max 1717 |
| intv_hr | float64 | 0.4 | 9163 | min 0; p1 0; median 151; p99 4363; max 41225 |
| chartTime | str | 0.4 | 703832 | avg length 22; first value shape ddaaadddd:dd:dd:dd.ddd |
| clinicalUnit | str | 0.4 | 9 | RBH-PICU: 1615795; RBH-PHDU: 195389; RBH-Theatre: 108087; RBH-Cath: 29553; RBH-Reginald-Wilson: 355; RBH-Recovery: 72; RBH-AICU: 19; RBH-Alex: 13; RBH-EICU/EHDU: 4 |
| HR | float64 | 10.4 | 300 | min 0; p1 59; median 130; p99 184; max 300 |
| Underlying_Cardiac_Rhythm | str | 97.8 | 361 | avg length 4; first value shape aaaaa |
| NIBP_s | float64 | 56.0 | 212 | min 0; p1 45; median 81; p99 129; max 256 |
| NIBP_m | float64 | 55.9 | 169 | min 0; p1 29; median 55; p99 94; max 200 |
| NIBP_d | float64 | 56.0 | 158 | min 0; p1 21; median 46; p99 85; max 176 |
| ABP_s | float64 | 65.2 | 241 | min 0; p1 39; median 77; p99 138; max 300 |
| ABP_m | float64 | 63.0 | 201 | min 0; p1 28; median 56; p99 100; max 200 |
| ABP_d | float64 | 65.2 | 155 | min 0; p1 23; median 44; p99 80; max 176 |
| PAS_AD_RK | int64 | 0.0 | 13285 | min 2; p1 23947; median 693156; p99 926901; max 936282 |
| WARD_IN_dttm | str | 0.0 | 12438 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |
| LOS | int64 | 0.0 | 1004 | min -1744; p1 16; median 449; p99 6730; max 75541 |
| WARD_OUT_dttm | str | 0.4 | 11544 | avg length 21; first value shape ddaaadddd:dd:dd:dd.dd |

## Columns shared between files

|                       |   ai_picu_airway.csv |   ai_picu_bg.csv |   ai_picu_biochemistry.csv |   ai_picu_coagulation.csv |   ai_picu_demographics.csv |   ai_picu_full_blood_count.csv |   ai_picu_infusion.csv |   ai_picu_io.csv |   ai_picu_meds.csv |   ai_picu_outcomes.csv |   ai_picu_piccanet.csv |   ai_picu_piccanet_old.csv |   ai_picu_sedation.csv |   ai_picu_sedation_old.csv |   ai_picu_temp.csv |   ai_picu_vent.csv |   ai_picu_vitals.csv |
|:----------------------|---------------------:|-----------------:|---------------------------:|--------------------------:|---------------------------:|-------------------------------:|-----------------------:|-----------------:|-------------------:|-----------------------:|-----------------------:|---------------------------:|-----------------------:|---------------------------:|-------------------:|-------------------:|---------------------:|
| addate                |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                   2456 |                       2540 |                    nan |                        nan |                nan |                nan |                  nan |
| addatetime            |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                   4383 |                       4673 |                    nan |                        nan |                nan |                nan |                  nan |
| adtime                |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                    608 |                        632 |                    nan |                        nan |                nan |                nan |                  nan |
| agedays               |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                   1778 |                       1799 |                    nan |                        nan |                nan |                nan |                  nan |
| agemonths             |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                    204 |                        204 |                    nan |                        nan |                nan |                nan |                  nan |
| ageyears              |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                     18 |                         18 |                    nan |                        nan |                nan |                nan |                  nan |
| calcium               |                  nan |              313 |                        304 |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                    nan |                        nan |                    nan |                        nan |                nan |                nan |                  nan |
| charttime             |               116879 |              nan |                        nan |                       nan |                        nan |                            nan |                  95031 |           144850 |             101290 |                    nan |                    nan |                        nan |                 160530 |                      88391 |             295280 |             481990 |               703832 |
| clinicalunit          |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                    nan |                        nan |                    nan |                        nan |                  2 |                  9 |                    9 |
| corr_calcium          |                  nan |              261 |                        299 |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                    nan |                        nan |                    nan |                        nan |                nan |                nan |                  nan |
| day                   |                  299 |              843 |                        956 |                       808 |                        nan |                            918 |                    305 |              982 |                359 |                    nan |                    nan |                        nan |                    334 |                        275 |                376 |                389 |                  389 |
| dose                  |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                   3596 |              nan |               1042 |                    nan |                    nan |                        nan |                   3842 |                       3460 |                nan |                nan |                  nan |
| dose_unit             |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                      6 |              nan |                  4 |                    nan |                    nan |                        nan |                      8 |                          7 |                nan |                nan |                  nan |
| drug                  |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                      7 |              nan |                  6 |                    nan |                    nan |                        nan |                     11 |                         10 |                nan |                nan |                  nan |
| encounterid           |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                   2785 |              nan |               4916 |                    nan |                    nan |                        nan |                   4577 |                       2532 |                nan |                nan |                  nan |
| ethnicdescription     |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                     17 |                         17 |                    nan |                        nan |                nan |                nan |                  nan |
| ethnicother           |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                     11 |                         11 |                    nan |                        nan |                nan |                nan |                  nan |
| eventid               |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                   4404 |                       4700 |                    nan |                        nan |                nan |                nan |                  nan |
| gender                |                  nan |              nan |                        nan |                       nan |                          3 |                            nan |                    nan |              nan |                nan |                    nan |                      3 |                          3 |                    nan |                        nan |                nan |                nan |                  nan |
| glucose               |                  nan |              352 |                        384 |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                    nan |                        nan |                    nan |                        nan |                nan |                nan |                  nan |
| hb                    |                  nan |              252 |                        nan |                       nan |                        nan |                            383 |                    nan |              nan |                nan |                    nan |                    nan |                        nan |                    nan |                        nan |                nan |                nan |                  nan |
| intubedays            |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                     74 |                         77 |                    nan |                        nan |                nan |                nan |                  nan |
| intv_hr               |                 6976 |            15929 |                      12134 |                     11259 |                        nan |                          11426 |                   7213 |            22708 |               7020 |                    nan |                    nan |                        nan |                   6866 |                       6434 |               7411 |               9168 |                 9163 |
| los                   |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    721 |              nan |                876 |                    nan |                    nan |                        nan |                    952 |                        722 |                nan |               1004 |                 1004 |
| loshours              |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                    684 |                        720 |                    nan |                        nan |                nan |                nan |                  nan |
| pas_ad_rk             |                13285 |            13285 |                      13285 |                     13285 |                      13285 |                          13285 |                   2688 |            13285 |               4682 |                    nan |                    nan |                        nan |                   4312 |                       2441 |              13285 |              13285 |                13285 |
| patient_rk            |                10019 |            10019 |                      10019 |                     10019 |                      10019 |                          10019 |                   2215 |            10019 |               3694 |                    nan |                    nan |                        nan |                   3501 |                       2069 |              10019 |              10019 |                10019 |
| pim3                  |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                   4056 |                       4289 |                    nan |                        nan |                nan |                nan |                  nan |
| potassium             |                  nan |              270 |                        103 |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                    nan |                        nan |                    nan |                        nan |                nan |                nan |                  nan |
| primarydiagnosisgroup |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                     13 |                         13 |                    nan |                        nan |                nan |                nan |                  nan |
| rate_unit             |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                      1 |              nan |                  1 |                    nan |                    nan |                        nan |                      1 |                          1 |                nan |                nan |                  nan |
| samplecollectdatetime |                  nan |           374776 |                      72808 |                     60990 |                        nan |                          63347 |                    nan |              nan |                nan |                    nan |                    nan |                        nan |                    nan |                        nan |                nan |                nan |                  nan |
| secdescriptions       |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                   2386 |                       2535 |                    nan |                        nan |                nan |                nan |                  nan |
| sodium                |                  nan |              109 |                         65 |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                    nan |                        nan |                    nan |                        nan |                nan |                nan |                  nan |
| studyid               |                14797 |            14797 |                      14797 |                     14797 |                      14797 |                          14797 |                   2884 |            14797 |               5109 |                  14797 |                   4795 |                       7926 |                   7576 |                       2613 |              14797 |              14797 |                14797 |
| trachdays             |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                     34 |                         34 |                    nan |                        nan |                nan |                nan |                  nan |
| unitdisdatetime       |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                   4363 |                       4654 |                    nan |                        nan |                nan |                nan |                  nan |
| unplannedextubation   |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                      2 |                          2 |                    nan |                        nan |                nan |                nan |                  nan |
| ventilationstatus     |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                      4 |                          4 |                    nan |                        nan |                nan |                nan |                  nan |
| ward_in_dttm          |                12438 |            12438 |                      12438 |                     12438 |                        nan |                          12438 |                   2868 |            12438 |               5071 |                    nan |                    nan |                        nan |                   5077 |                       2598 |              12438 |              12438 |                12438 |
| ward_out_dttm         |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                   2551 |              nan |               4587 |                    nan |                    nan |                        nan |                   4623 |                       2355 |                nan |              11544 |                11544 |
| weight                |                  nan |              nan |                        nan |                       nan |                        nan |                            nan |                    nan |              nan |                nan |                    nan |                    536 |                        544 |                    nan |                        nan |                nan |                nan |                  nan |
| weight_kg             |                  nan |              nan |                        nan |                       nan |                        591 |                            nan |                    377 |              591 |                475 |                    nan |                    nan |                        nan |                    519 |                        408 |                nan |                591 |                  591 |

## ID overlap with ai_picu_demographics.csv

|    | column     | file                         |   unique ids |   % in base |
|---:|:-----------|:-----------------------------|-------------:|------------:|
|  0 | studyid    | ai_picu_airway.csv           |        14797 |       100   |
|  1 | studyid    | ai_picu_bg.csv               |        14797 |       100   |
|  2 | studyid    | ai_picu_biochemistry.csv     |        14797 |       100   |
|  3 | studyid    | ai_picu_coagulation.csv      |        14797 |       100   |
|  4 | studyid    | ai_picu_full_blood_count.csv |        14797 |       100   |
|  5 | studyid    | ai_picu_infusion.csv         |         2884 |       100   |
|  6 | studyid    | ai_picu_io.csv               |        14797 |       100   |
|  7 | studyid    | ai_picu_meds.csv             |         5109 |       100   |
|  8 | studyid    | ai_picu_outcomes.csv         |        14797 |       100   |
|  9 | studyid    | ai_picu_piccanet.csv         |         4795 |       100   |
| 10 | studyid    | ai_picu_piccanet_old.csv     |         7926 |        61   |
| 11 | studyid    | ai_picu_sedation.csv         |         7576 |        58.4 |
| 12 | studyid    | ai_picu_sedation_old.csv     |         2613 |       100   |
| 13 | studyid    | ai_picu_temp.csv             |        14797 |       100   |
| 14 | studyid    | ai_picu_vent.csv             |        14797 |       100   |
| 15 | studyid    | ai_picu_vitals.csv           |        14797 |       100   |
| 16 | patient_rk | ai_picu_airway.csv           |        10019 |       100   |
| 17 | patient_rk | ai_picu_bg.csv               |        10019 |       100   |
| 18 | patient_rk | ai_picu_biochemistry.csv     |        10019 |       100   |
| 19 | patient_rk | ai_picu_coagulation.csv      |        10019 |       100   |
| 20 | patient_rk | ai_picu_full_blood_count.csv |        10019 |       100   |
| 21 | patient_rk | ai_picu_infusion.csv         |         2215 |       100   |
| 22 | patient_rk | ai_picu_io.csv               |        10019 |       100   |
| 23 | patient_rk | ai_picu_meds.csv             |         3694 |       100   |
| 24 | patient_rk | ai_picu_sedation.csv         |         3501 |        96.4 |
| 25 | patient_rk | ai_picu_sedation_old.csv     |         2069 |       100   |
| 26 | patient_rk | ai_picu_temp.csv             |        10019 |       100   |
| 27 | patient_rk | ai_picu_vent.csv             |        10019 |       100   |
| 28 | patient_rk | ai_picu_vitals.csv           |        10019 |       100   |
| 29 | pas_ad_rk  | ai_picu_airway.csv           |        13285 |       100   |
| 30 | pas_ad_rk  | ai_picu_bg.csv               |        13285 |       100   |
| 31 | pas_ad_rk  | ai_picu_biochemistry.csv     |        13285 |       100   |
| 32 | pas_ad_rk  | ai_picu_coagulation.csv      |        13285 |       100   |
| 33 | pas_ad_rk  | ai_picu_full_blood_count.csv |        13285 |       100   |
| 34 | pas_ad_rk  | ai_picu_infusion.csv         |         2688 |       100   |
| 35 | pas_ad_rk  | ai_picu_io.csv               |        13285 |       100   |
| 36 | pas_ad_rk  | ai_picu_meds.csv             |         4682 |       100   |
| 37 | pas_ad_rk  | ai_picu_sedation.csv         |         4312 |        96   |
| 38 | pas_ad_rk  | ai_picu_sedation_old.csv     |         2441 |       100   |
| 39 | pas_ad_rk  | ai_picu_temp.csv             |        13285 |       100   |
| 40 | pas_ad_rk  | ai_picu_vent.csv             |        13285 |       100   |
| 41 | pas_ad_rk  | ai_picu_vitals.csv           |        13285 |       100   |

