"""St Mary's (SMH): record of the extraction SQL and the ID mappings (interventionId, attributeId, materialId).

Provenance (recorded 2026-11-17): the extraction SQL files (ai_picu_*.sql, labels are the SQL comments) and
the mapping dictionaries from Jake's and a student's earlier notebooks. The SMH extract has no data
dictionary. Labels come from SQL comments and were not checked against a source dictionary, except bg and
labs, which can be checked against `shortLabel` and units in the tables themselves.

These are IDs and labels only: no patient data, safe to commit.

Notebook use:
    import smh_mappings as SM
    SM.to_table()                          # one row per ID in MAPPINGS
    SM.check_coverage(out_dir)             # rows and stays per concept; IDs left unmapped (counts only)
    SM.EXTRACTION                          # how the SMH cohort was selected (applies to every table)
"""
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

import inventory as I

# =====================================================================================================
# 1. How the SMH extract was made (from the SQL; same criteria in every file unless noted)
# =====================================================================================================
EXTRACTION = {
    "database": "CISReportingDB (St Mary's clinical information system)",
    "unit": "clinicalUnitId = 32",
    "admission_window": "PtCensus.inDayId > 50039 and < 54057 (day numbers; calendar dates not recorded here)",
    "min_length_of_stay": "PtCensus.lengthOfStay > 360 (minutes, i.e. stays of 6 hours or less are NOT in the extract)",
    "age": "DATEDIFF(MONTH, dateOfBirth, inTime) <= 12*18, i.e. 18 years or younger at admission",
    "placeholder_hospital_numbers_removed": "lifeTimeNumber like 'false%', '111111', '1234567'",
    "weight_record_required": "joined to PtDemographic with interventionId = 10640 (weight): stays without a weight "
                              "record are not in the extract (the io query has this join commented out)",
    "times": "utcChartTime is UTC; inTime (demographics) is London local",
}
# Consequences to handle when pooling: (a) the 6 h minimum is SMH-specific; check RBH and GOSH length of stay
# and apply one common rule. (b) Age in months is a calendar-month count (DATEDIFF MONTH counts month
# boundaries), so it can be up to a month above the completed months.

# Source table and columns per SQL file
SQL_SOURCE = {
    "bg": "PtLabResult (+ D_Intervention.shortLabel); terseForm, verboseForm",
    "labs": "PtLabResult (+ D_Intervention.shortLabel); terseForm, verboseForm",
    "io": "PtTotalBalance; hourTotal, cumTotal, unitOfMeasure, isFinal, isReset",
    "vitals": "PtAssessment; interventionId + attributeId; terseForm, verboseForm",
    "vent": "PtAssessment; interventionId; terseForm, verboseForm",
    "airway": "PtAssessment; interventionId + attributeId; terseForm, verboseForm "
              "(no clinicalUnitId filter in the inner query; the join to PtCensus applies unit 32)",
    "medications": "PtMedication; output has materialId (no interventionId); Drug_*/Dosage_* by attributeId",
    "infusions": "PtMedication; output has interventionId (no materialId); Drug_*/Dosage_* by attributeId",
    "antibio": "PtMedication; output has interventionId (no materialId); same attributes as infusions",
    "outcomes": "PtCensus: LOS = lengthOfStay / 60 rounded to 2 decimals (HOURS), isDeceased",
    "demographics": "PtCensus + D_Encounter + PtDemographic(10640): UniquePtID = MD5 of lifeTimeNumber, Age (months), "
                    "gender, ethnicGroup, Weight (terseForm), inTime, primaryDiagnosis, SepsisDiagnosis "
                    "(primaryDiagnosis like 'sep%'). Duplicates with different weights are possible.",
}
# UniquePtID is an unsalted MD5 of the hospital number: pseudonymous, but guessable for anyone holding hospital
# numbers. Treat it as an identifier: it must not appear in any Tier 1 or Tier 2 output.

# =====================================================================================================
# 2. Mappings used for coverage checks (concept -> IDs). Keys are strings.
# =====================================================================================================
# --- blood gas (key: interventionId) -------------------------------------------------------------
BG = {
    "bg_source": ["113868"],                 # sample type text (arterial, venous, capillary...), not a measurement
    "pH": ["1190"],
    "PCO2": ["1191"],                        # kPa
    "PO2": ["1192"],                         # kPa
    "glucose_bg": ["1194"],                  # POC glucose, mmol/L
    "baseExcess": ["1196"],                  # mmol/L
    "HCO3": ["1199"],                        # HCO3 standard, mmol/L
    "lactate": ["1294"],                     # mmol/L
    "sodium_bg": ["1206"],
    "potassium_bg": ["1212"],
    "chloride_bg": ["1198"],
    "calcium_bg": ["1290"],                  # ionised
    "totalHb_bg(g/dL)": ["1324"],
    "totalHb_bg(g/L)": ["1348", "1398", "1400"],   # 1400 is labelled g/dL in the table; kept as in the notebook
    "Hct": ["1359", "1399", "1397"],         # percent; 1397 is labelled L/L but is percent (per the notebook)
    "MetHb_bg": ["1197"],                    # percent
    "SaO2": ["1343"],                        # percent
}
# In the SQL but absent from the data: 1287 (Total Hb), 1289 (lactate).

# --- labs (key: interventionId) -------------------------------------------------------------------
LABS = {
    "WBC": ["1396", "1377", "117303"],                             # 10^9/L
    "Neutrophil": ["1316", "12381", "117305"],                     # 12381 has no units: check it is not a percentage
    "Lymphocytes": ["1318", "1321", "12382", "117302", "117502"],  # 12382 has no units: check
    "PLT": ["1382", "1394", "117306"],
    "Hb(g/dL)": ["1314"],
    "Hb(g/L)": ["1378"],
    "potassium_lab": ["1388", "1392"],
    "sodium_lab": ["1385", "1386"],
    "chloride_lab": ["10687"],               # the label looks like merged comment text: check
    "glucose_lab": ["1203"],
    "calcium_lab": ["1298"],
    "phosphate": ["1302"],
    "magnesium": ["1379"],
    "urea": ["1383", "1389"],
    "creatinine": ["1381", "1384"],          # umol/L
    "totalBilirubin": ["1297"],              # umol/L
    "albumin": ["1303"],                     # g/L
    "ALT": ["1353", "1358"],                 # IU/L and U/L (same)
    "INR": ["1370"],
    "fibrinogen": ["1376", "1391"],          # g/L
    "APTT": ["1352", "1373", "1374"],        # seconds
}
# In the SQL but absent from the data (so not mapped): APTT 1239, 1276, 42803; INR 1243; WBC 1282, 1234;
# lymphocytes 1246; neutrophils 1278, 1233; platelets 1274, 1236.

# --- fluids (key: interventionId; value columns hourTotal and cumTotal) -----------------------------------
IO = {
    # used in the earlier notebook (24 h totals)
    "fluidIn": ["2045", "113860"],
    "fluidOut": ["2073", "113859", "113961"],
    "fluidBalance": ["2067", "113958"],
    # components and cumulative balance: labels from the SQL comments, not used in the notebook
    "ivInfusionTotal": ["1851"],
    "enteralIntakeTotal": ["1912"],          # PO/NG intake, 24 h
    "bloodProducts": ["2052"],
    "colloids": ["2047"],
    "urineOutput": ["1945"],                 # 24 h
    "chestDrainOutput": ["1949"],            # 24 h
    "drugVolumeTotal": ["2101"],             # 24 h
    "lengthOfStayBalance": ["2078", "113831"],   # cumulative over the stay
}
# Every ID in the io SQL with its comment label (most are not in the extract).
IO_SQL_GROUPS = {
    "Total In 24hr": ["1995", "2008", "2039", "2045", "2097", "113860"],
    "Total Out 24hr": ["1890", "1960", "2014", "2037", "2064", "2073", "2091", "113859", "113961"],
    "IV Infusion Total": ["1851"],
    "PO/NG Intake Total 24hr": ["1912"],
    "Blood Products 24hr": ["2052"],
    "Colloids Total 24hr": ["2047"],
    "Urine Output 24hr": ["1945"],
    "Chest Drain Output 24hr": ["1949"],
    "Overall Balance 24hr": ["1886", "1961", "2015", "2031", "2035", "2042", "2067", "2074", "2111", "2114", "113958"],
    "Renal Replacement Mode": ["555"],
    "Drug Volume Total 24hr": ["2101", "2019"],
    "Daily Fluid Requirement": ["5194"],
    "Total Length of Stay Balance": ["1887", "1962", "2011", "2019", "2029", "2078", "2083", "2093", "2095", "2103", "113831"],
}
# 2019 is listed under two labels in the SQL; not mapped. Which value column (hourTotal or cumTotal) the
# earlier notebook used is not recorded.

# --- vitals (key: interventionId + "_" + attributeId) ------------------------------------------------
VITALS = {
    # Provenance per line: SQL = the attribute is named in the extraction SQL comments;
    #                      NB  = only in the earlier notebook map (the SQL names the interventionId, not the attribute)
    "tempSource": ["3818_13866"],                    # SQL: 13866 source
    "temp": ["3818_13865"],                          # SQL: 13865 value (Temp1 central)
    "HR": ["8010_59129", "8010_59130"],              # SQL names 8010 = HR; attributes NB
    "cardiacRhythm": ["5027_56052"],                 # SQL names 5027; attribute NB (found in the data)
    "SpO2": ["8073_64034"],                          # SQL names 8073; attribute NB
    "etCO2": ["30546_32366", "8070_26358"],          # SQL names 8070, 30546; attributes NB
    "systolicNIBP": ["3406_57901", "3406_57902"],    # SQL: 57901; 57902 NB
    "meanNIBP": ["3406_57899", "3406_57903"],        # SQL: both
    "diastolicNIBP": ["3406_57900", "3406_57904"],   # SQL: both
    "systolicABP": ["4688_5413", "4688_5415"],       # SQL: both
    "meanABP": ["4688_5410", "4688_5411"],           # SQL: both
    "diastolicABP": ["4688_5412", "4688_5414"],      # SQL: both
    "CRT(central)": ["2934_55834", "2934_55837", "2935_53929", "2935_53930"],   # SQL: named as central
    "CRT(unconfirmed)": ["2934_55833"],              # NB only: counted as central in the old map, but the SQL does not name it
                                                     # as central (could be peripheral). 136k rows, 3,296 stays, median 2, max 22 s
    # labelled in the SQL, excluded by the student's notebook (8528, 7796, 7238, 5027); attributes seen in the data
    "CVP": ["7796_18712"],                           # SQL names 7796; attribute from the data
    "pupilSize": ["7238_10851", "7238_10852"],       # SQL names 7238; which attribute is which eye is not known
    "pupilReaction": ["8528_1082", "8528_1084"],     # SQL names 8528
    "NIBPcuffSite": ["3406_57907"],                  # text: Leg L, Leg R, Arm L, Arm R (identified from the data)
}
# SQL comments for the vitals file: 3818 Temp1 Central; 8010 HR; 5027 cardiac rhythm; 8073 SpO2;
# 3406 NIBP (57901 SBP, 57903 and 57899 mean, 57900 and 57904 DBP); 4688 and 4689 arterial BP (5413, 5415, 10366,
# 10367 SBP; 5412, 5414, 10362, 10363 DBP; 5410, 5411, 10364, 10365 mean); 8070 and 30546 etCO2; 7796 CVP;
# 2934 and 2935 CRT (55834, 55837, 53929, 53930 central); 7238 pupil size; 8528 pupil reaction.
# Differences between the old map and the SQL comments, to check: 3406_57902 (old SBP) and 2934_55833 (old CRT)
# are not in the SQL comments; 4689 and its attributes are in the SQL but not in the data.
# 3406_57907 is the NIBP cuff site (text values: leg or arm, left or right).

# --- ventilation (key: interventionId) ---------------------------------------------------------------
VENT = {
    "ventMode": ["5984"],
    "FiO2": ["8119"],
    "PIP": ["8115"],                         # 3984 (5 rows) also labelled PIP in the SQL; commented out in the notebook
    "PEEP(set)": ["5431"],
    "MAP": ["4554"],                         # mean airway pressure
    "inspTime": ["8114", "14238"],
    "IE_ratio": ["4185", "4186"],            # labelled I:E ratio in the SQL; two IDs, probably components: check values
    "TV(measured)": ["4555"],                # tidal volume, expired
    "RR(measured)": ["8117"],                # total respiratory rate
    "RR(set)": ["4553"],                     # ventilator rate
    "iNO": ["5184"],                         # inhaled nitric oxide (commented out in the notebook)
    "PS+PEEP": ["4131"],                     # pressure support + PEEP
}

# --- airway (key: interventionId; attributes in the SQL: ETT site 36578, size 36575) -------------------
AIRWAY = {
    "airwayType": ["8039"],                  # the only one the student's notebook used
    "airwayTube": ["4528"],
    "ETT_paed": ["5402", "5404"],            # paediatric ETT (site and size by attributeId); 5404 has 1.28M rows
}

# --- drugs (kept apart from measurements) -----------------------------------------------------------
# medications table: key materialId (the output has no interventionId)
MEDICATIONS = {
    "chlorothiazide": ["831"],
    "furosemide": ["3726", "795"],
    "spironolactone": ["3151"],
    "dexamethasone": ["932"],
    "hydrocortisone": ["1957"],
    "prednisolone": ["3593"],
    "methylprednisolone": ["2137"],
    "chloralHydrate": ["370"],
}
MED_ATTRIBUTES = {"drug": ["17144", "52694", "83689", "57524", "12273", "15409"],
                  "dosage": ["17141", "57521", "83685", "52688", "12268", "15406"]}
MED_INTERVENTIONS_IN_SQL = {   # interventionId filter in the medications SQL, by label
    "drug in general": ["10653"],
    "furosemide": ["10652", "37711", "60326"],
    "chlorothiazide": ["22717", "43337"],
    "spironolactone": ["11283", "21952", "66744"],
    "metolazone": ["21952", "66744"],          # same IDs as spironolactone in the SQL
    "dexamethasone": ["11177"],
    "hydrocortisone": ["10846", "11997", "10653", "24851"],
    "prednisolone": ["11165", "26918"],
    "methylprednisolone": ["12239", "13239"],
    "chloralHydrate": ["11362", "29715", "85233"],
}

# infusions table: the SQL filters by materialId (below) and outputs interventionId.
INFUSION_MATERIALS = {
    "morphine": ["1565"], "midazolam": ["995"], "fentanyl": ["3630"], "propofol": ["3246"],
    "remifentanil": ["3189"], "dexmedetomidine": ["3783"], "clonidine": ["1248"], "ketamine": ["3409"],
    "thiopentone": ["4056"], "vecuronium": ["149"], "atracurium": ["2466"], "rocuronium": ["395"],
    "adrenaline": ["898"], "noradrenaline": ["207"], "milrinone": ["3036"], "vasopressin": ["2831"],
    "dopamine": ["2380"], "dobutamine": ["2125"], "labetalol": ["1787"], "hydralazine": ["1997"],
    "sodiumNitroprusside": ["1327"], "glyceryltrinitrate": ["3787"], "furosemide": ["795", "3726"],
}
INF_ATTRIBUTES = {"drug": ["11840", "32520", "50625", "61101", "81264"],
                  "dosage": ["11830", "32525", "32526", "50626", "61098", "81266"]}
# Candidate interventionId -> drug map from the commented-out block of the infusions SQL (and Ram's comment: 10698
# noradrenaline, 15477 esmolol, 10652 bolus furosemide). NOT confirmed: the SQL author asked whether one ID
# per drug is enough. Check the data's interventionIds against Drug_terse before relying on it.
INFUSIONS = {
    "morphine": ["11208"], "midazolam": ["10700"], "fentanyl": ["10703"], "propofol": ["10699"],
    "dexmedetomidine": ["10999"], "clonidine": ["11345"], "ketamine": ["12386"], "adrenaline": ["11109"],
    "noradrenaline": ["10698"], "milrinone": ["11831"], "vasopressin": ["11248"], "dopamine": ["15387"],
    "dobutamine": ["10945"], "labetalol": ["10822"], "furosemide_infusion": ["10997"], "furosemide_bolus": ["10652"],
    "dexamethasone": ["11177"], "hydrocortisone": ["10846"], "prednisolone": ["26918", "11165"],
    "methylprednisolone": ["13239"], "glyceryltrinitrate": ["10825"], "sodiumNitroprusside": ["22847"],
    "hydralazine": ["11877"], "rocuronium": ["11502"], "esmolol": ["15477"], "generalInfusion": ["10939"],
    # identified from Drug_terse in the data (not in the SQL comments): 2026-11-17
    "vecuronium": ["11858"], "remifentanil": ["13245"], "thiopentone": ["11999"], "atracurium": ["10706"],
}

# antibiotics table: the SQL filters by materialId and outputs interventionId, so the drug is read from Drug_terse.
ANTIBIOTIC_MATERIALS = {
    "piperacillinTazobactam": ["3551"], "ceftriaxone": ["1177"], "cefotaxime": ["1730"],
    "ciprofloxacin": ["2249"], "ciprofloxacin_enteral": ["792"], "amoxicillin": ["1267"], "aciclovir": ["2703"],
    "coAmoxiclav": ["1811"], "gentamicin": ["2676"], "amikacin": ["1899"], "ambisome": ["2612"],
    "fluconazole": ["176"], "vancomycin": ["858"], "metronidazole": ["2188", "424"],
    "azithromycin": ["39", "2297", "3759"], "erythromycin": ["33", "2857", "3684"],
    "clarithromycin": ["3613", "1582", "2886"],
}
# The antibiotic SQL as supplied has no commas between the first materialIds (3551 ... 1177 ... 1730 ... 2249 ... 792 ...),
# which would not run as written. The extract may have used a different list: compare with the materials in the data.

# =====================================================================================================
# 3. Coverage check
# =====================================================================================================
MAPPINGS = {"bg": BG, "labs": LABS, "io": IO, "vitals": VITALS, "vent": VENT, "airway": AIRWAY,
            "medications": MEDICATIONS, "infusions": INFUSIONS}
TABLE_FILE = {"bg": "ai_picu_bg", "labs": "ai_picu_labs", "io": "ai_picu_io", "vitals": "ai_picu_vitals"}
# other tables: found by name (an assembled file whose name contains the table name)
KEY = {"vitals": ("interventionId", "attributeId"), "medications": ("materialId",)}   # default: interventionId
DEFAULT_TABLES = ("bg", "labs", "io", "vitals", "vent", "airway", "medications", "infusions")


def to_table():
    """One row per ID: table, concept, id."""
    rows = [{"table": t, "concept": c, "id": i} for t, m in MAPPINGS.items() for c, ids in m.items() for i in ids]
    return pd.DataFrame(rows)


def _path(base, t):
    """Assembled parquet for table t: the configured name, else the one file whose name contains t (or t without a
    trailing 's', so 'infusions' also finds 'infusion')."""
    if TABLE_FILE.get(t):
        return base / f"{TABLE_FILE[t]}.parquet"
    allf = sorted(base.glob("*.parquet"))
    for key in (t, t.rstrip("s")):
        hits = [p for p in allf if key in p.stem.lower()]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise FileNotFoundError(f"{t}: several files match: {[h.name for h in hits]}; set TABLE_FILE['{t}'] "
                                    f"to the right one (without .parquet)")
    raise FileNotFoundError(f"{t}: no assembled file matches. Files in {base}: {[p.name for p in allf]}; "
                            f"set TABLE_FILE['{t}'] to the right one (without .parquet)")


def _cols(path, wanted):
    """Actual column names in the file for the wanted names (case-insensitive)."""
    names = {n.lower(): n for n in pq.ParquetFile(path).schema.names}
    missing = [w for w in wanted if w.lower() not in names]
    if missing:
        raise KeyError(f"{path.name}: missing columns {missing}; has {list(names.values())[:20]}")
    return [names[w.lower()] for w in wanted]


def check_coverage(assembled_dir, tables=DEFAULT_TABLES, top=12):
    """For each table: rows and stays per concept, and the IDs that are not in the map.
    Counts only (IDs are measurement codes, not patient data)."""
    base = Path(assembled_dir) / "SMH"
    out = {}
    for t in tables:
        path = _path(base, t)
        keys = KEY.get(t, ("interventionId",))
        cols = _cols(path, ("encounterId",) + keys)
        df = pd.read_parquet(path, columns=cols)
        df.columns = ["stay"] + list(keys)
        ids = df[keys[0]].astype("string").str.strip()
        for k in keys[1:]:
            ids = ids + "_" + df[k].astype("string").str.strip()
        df["_id"] = ids
        rev = {i: c for c, v in MAPPINGS[t].items() for i in v}
        df["concept"] = df["_id"].map(rev)
        g = df.dropna(subset=["concept"]).groupby("concept")
        res = pd.DataFrame({"rows": g.size(), "stays": g["stay"].nunique()})
        res = res.reindex([c for c in MAPPINGS[t] if c in res.index])
        print(f"\n{t}: {len(df):,} rows; mapped {int(df['concept'].notna().sum()):,} "
              f"({100*df['concept'].notna().mean():.1f}%); stays in table {df['stay'].nunique():,}")
        print(I.df_text(res, index=True))
        un = df[df["concept"].isna()]["_id"].value_counts()
        print(f"  unmapped IDs: {len(un)}; rows {int(un.sum()):,}. Largest:")
        print("  " + "; ".join(f"{k}: {v:,}" for k, v in un.head(top).items()))
        out[t] = res
    return out


def describe_ids(assembled_dir, table, ids, value_col, top=8, min_count=10):
    """For IDs that are not mapped yet: how many rows and stays, whether the values are numeric (quantiles),
    and the most common text values. Values that occur fewer than `min_count` times are not shown.
    `ids` use the same form as the mapping (for vitals: 'interventionId_attributeId').
    Use value_col='terseForm' for measurements and 'Drug_terse' for infusions (drug names)."""
    path = _path(Path(assembled_dir) / "SMH", table)
    keys = KEY.get(table, ("interventionId",))
    cols = _cols(path, ("encounterId",) + keys + (value_col,))
    df = pd.read_parquet(path, columns=cols)
    df.columns = ["stay"] + list(keys) + ["value"]
    key = df[keys[0]].astype("string").str.strip()
    for k in keys[1:]:
        key = key + "_" + df[k].astype("string").str.strip()
    for i in ids:
        sub = df[key == str(i)]
        num = pd.to_numeric(sub["value"], errors="coerce")
        print(f"\n{table} {i}: {len(sub):,} rows, {sub['stay'].nunique():,} stays; "
              f"numeric {100 * num.notna().mean() if len(sub) else 0:.0f}%")
        if num.notna().any():
            q = num.quantile([0, .05, .5, .95, 1])
            print("  min / p5 / median / p95 / max: " + " / ".join(f"{v:.4g}" for v in q))
        txt = sub.loc[num.isna(), "value"].astype("string").str.strip().value_counts()
        txt = txt[txt >= min_count].head(top)
        if len(txt):
            print("  most common text values: " + "; ".join(f"{k!r}: {v:,}" for k, v in txt.items()))


def coverage_tables(assembled_dir, tables=DEFAULT_TABLES, baseline=None, top=15):
    """Same check as check_coverage, but returned as tables (for the report) instead of printed.
    Returns {"Summary": one row per table, "Unmapped IDs": one row per unmapped ID with rows and stays,
    "Concepts, <table>": rows and stays per concept}. Counts and measurement codes only.
    `baseline` (the assembled counts baseline, columns site, table, rows) adds a check that the table has the
    number of rows recorded at assembly."""
    base = Path(assembled_dir) / "SMH"
    summary, unmapped, out = [], [], {}
    for t in tables:
        path = _path(base, t)
        keys = KEY.get(t, ("interventionId",))
        df = pd.read_parquet(path, columns=_cols(path, ("encounterId",) + keys))
        df.columns = ["stay"] + list(keys)
        ids = df[keys[0]].astype("string").str.strip()
        for k in keys[1:]:
            ids = ids + "_" + df[k].astype("string").str.strip()
        rev = {i: c for c, v in MAPPINGS[t].items() for i in v}
        concept = ids.map(rev)
        row = {"table": t, "file": path.name, "rows": len(df), "mapped rows": int(concept.notna().sum()),
               "mapped %": round(100 * concept.notna().mean(), 1), "stays": int(df["stay"].nunique()),
               "unmapped IDs": int(ids[concept.isna()].nunique()), "unmapped rows": int(concept.isna().sum())}
        if baseline is not None:
            exp = baseline[(baseline["site"] == "SMH") & (baseline["table"] == path.stem)]["rows"]
            row["rows as assembled"] = int(exp.iloc[0]) if len(exp) else None
            row["same as assembly"] = bool(len(exp) and int(exp.iloc[0]) == len(df))
        summary.append(row)
        g = pd.DataFrame({"stay": df["stay"], "id": ids})[concept.isna().to_numpy()].groupby("id")
        u = pd.DataFrame({"rows": g.size(), "stays": g["stay"].nunique()}).sort_values("rows", ascending=False).head(top)
        u.insert(0, "table", t)
        unmapped.append(u.reset_index())
        gc = pd.DataFrame({"stay": df["stay"], "concept": concept}).dropna(subset=["concept"]).groupby("concept")
        res = pd.DataFrame({"rows": gc.size(), "stays": gc["stay"].nunique()})
        out[f"Concepts, {t}"] = res.reindex([c for c in MAPPINGS[t] if c in res.index])
    return {"Summary": pd.DataFrame(summary), "Unmapped IDs": pd.concat(unmapped, ignore_index=True), **out}