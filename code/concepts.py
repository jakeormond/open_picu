"""Cross-site concept map: which measurements exist at RBH, SMH and GOSH, in what range, and for how many stays.

The map (`CONCEPTS`) was written from the assembled column and file names (RBH: wide tables, one column per
measurement; GOSH: one file per variable; SMH: numeric IDs, see smh_mappings.py). `build` measures every
source in the assembled tables: stays with a value, rows, share numeric, and the 5th, 50th and 95th percentile
(so unit differences between sites show up). Output is aggregate counts and ranges only.

Matching is by name, so entries marked "check" in a note are not confirmed. GOSH blood gases, fluid balance
components and all drugs live in long tables filtered by a label column: list those labels with `list_values`
first, then add them to the map.

Notebook use:
    import concepts as C
    C.list_values(assembled_dir, "GOSH", "merged_gas_data__merged_blood_gasses", "standard_variable")
    detail, summary = C.build(assembled_dir, static=pooled_static)
    C.survivors(summary, min_pct=50)
"""
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

import smh_mappings as SM

SITES = ("RBH", "SMH", "GOSH")
STAY = {"RBH": "stay_key", "GOSH": "stay_id"}      # SMH: encounterId
MISSING = {"", "null", "nan", "none", "na", "n/a", ".:."}      # ".:." is the RBH placeholder for an empty I:E ratio
GV = "res_value"                                    # GOSH value column in the per-variable files
_L = "merged_lab_values__"
_V = "merged_values__"
_VENT = "merged_vent_data__"
_BG = "merged_gas_data__merged_blood_gasses"
_BGL = "standard_variable"
_BAL = "merged_balance__"


def _c(group, RBH=(), SMH=(), GOSH=(), note=""):
    return {"group": group, "RBH": list(RBH), "SMH": list(SMH), "GOSH": list(GOSH), "note": note}


# RBH source = (table without 'ai_picu_', column); SMH source = (table, concept in smh_mappings);
# GOSH source = (file stem, value column) or (file stem, value column, label column, [labels])
CONCEPTS = {
    # ---- vital signs ----
    "hr": _c("vitals", [("vitals", "HR")], [("vitals", "HR")], [(_V + "HR_merged", GV)]),
    "pulse_rate": _c("vitals", GOSH=[(_V + "PulseRate_merged", GV)], note="GOSH only (probably pulse from the SpO2 probe: check)"),
    "spo2": _c("vitals", [("vent", "SpO2")], [("vitals", "SpO2")], [(_V + "SpO2_merged", GV)], note="RBH keeps SpO2 in the vent table"),
    "nibp_sys": _c("vitals", [("vitals", "NIBP_s")], [("vitals", "systolicNIBP")], [(_V + "Non-Invasive_systolic_BP_merged", GV)]),
    "nibp_mean": _c("vitals", [("vitals", "NIBP_m")], [("vitals", "meanNIBP")], [(_V + "Non-Invasive_mean_BP_merged", GV)]),
    "nibp_dia": _c("vitals", [("vitals", "NIBP_d")], [("vitals", "diastolicNIBP")], [(_V + "Non-Invasive_diastolic_BP_merged", GV)]),
    "abp_sys": _c("vitals", [("vitals", "ABP_s")], [("vitals", "systolicABP")], [(_V + "Invasive_systolic_BP_merged", GV)]),
    "abp_mean": _c("vitals", [("vitals", "ABP_m")], [("vitals", "meanABP")], [(_V + "Invasive_mean_BP_merged", GV)]),
    "abp_dia": _c("vitals", [("vitals", "ABP_d")], [("vitals", "diastolicABP")], [(_V + "Invasive_diastolic_BP_merged", GV)]),
    "temp_central": _c("vitals", [("temp", "centralTemp_C")], [("vitals", "temp")], [(_V + "Temperature_merged", GV)],
                       note="SMH = Temp1 central; GOSH Temperature site not stated: check"),
    "temp_peripheral": _c("vitals", [("temp", "periphTemp_C")], note="RBH only"),
    "resp_rate_total": _c("vitals", [("vent", "Total_Resp_Rate")], [("vent", "RR(measured)")], [(_VENT + "vent_Respiratory_measured_merged", GV)],
                          note="measured total rate from the ventilator; GOSH match by name: check"),
    "resp_rate_monitor": _c("vitals", GOSH=[(_V + "RespiratoryRate_merged", GV)], note="GOSH only (vital-sign respiratory rate)"),
    "etco2": _c("vitals", [("vent", "End_Tidal_CO2")], [("vitals", "etCO2")], [(_V + "ETCO2_merged", GV)], note="units: check (kPa or mmHg)"),
    "cvp": _c("vitals", SMH=[("vitals", "CVP")], GOSH=[(_V + "CVP_merged", GV)]),
    "crt": _c("vitals", SMH=[("vitals", "CRT(central)")], GOSH=[(_V + "Capillary_merged", GV)], note="GOSH Capillary assumed to be capillary refill: check"),
    "cardiac_rhythm": _c("vitals", [("vitals", "Underlying_Cardiac_Rhythm")], [("vitals", "cardiacRhythm")], [(_V + "HeartRhythm_merged", GV)], note="text"),
    "pupil_size": _c("vitals", SMH=[("vitals", "pupilSize")], GOSH=[(_V + "Pupil_size_merged", GV)]),
    "pupil_reaction": _c("vitals", SMH=[("vitals", "pupilReaction")], GOSH=[(_V + "Pupil_reaction_merged", GV)]),
    "gcs": _c("vitals", GOSH=[(_V + "GCS_merged", GV)], note="GOSH only"),
    "avpu": _c("vitals", GOSH=[(_V + "AVPU_score_merged", GV)], note="GOSH only"),
    # ---- ventilation and airway ----
    "vent_mode": _c("vent", [("vent", "Ventilation_Mode")], [("vent", "ventMode")], [(_VENT + "vent_Ventilation_mode_flowsheet_rows", GV, "var_type", ["Ventilator Mode.Ventilator Mode.Ventilator Mode"])],
                    note="text; GOSH flowsheet table, mode names are in res_value for this var_type; the other var_type ('Ventilation', 64k rows) is free text (31k distinct values) and is excluded: drop it at anonymisation; vocabularies differ by site"),
    "fio2": _c("vent", [("vent", "FiO2")], [("vent", "FiO2")], [(_VENT + "vent_FiO2_merged", GV)], note="fraction or percent: check"),
    "peep": _c("vent", [("vent", "PEEP")], [("vent", "PEEP(set)")], [(_VENT + "vent_PEEP_merged", GV)]),
    "pip": _c("vent", [("vent", "Peak_Insp_Press_mBar")], [("vent", "PIP")], [(_VENT + "vent_PIP_merged", GV)], note="mbar or cmH2O: check"),
    "mean_airway_pressure": _c("vent", [("vent", "Mean_Airway_Pressure")], [("vent", "MAP")], [(_VENT + "vent_mean_airway_merged", GV)]),
    "tidal_volume": _c("vent", [("vent", "Tidal_Volume")], [("vent", "TV(measured)")], [(_VENT + "merged_tidal_volumes", GV)], note="ml; GOSH expired or inspired: check"),
    "insp_time": _c("vent", SMH=[("vent", "inspTime")], GOSH=[(_VENT + "merged_inspiratory times", GV)], note="RBH has ratios instead"),
    "ie_ratio": _c("vent", [("vent", "IE_Ratio")], [("vent", "IE_ratio")], [(_VENT + "merged_IE_ratios", GV)], note="text or number: check"),
    "rr_set": _c("vent", [("vent", "Vent_Rate")], [("vent", "RR(set)")], [(_VENT + "vent_Respiratory_Rate_merged", GV)], note="GOSH 'Respiratory_Rate' assumed to be the set rate: check"),
    "ps_peep": _c("vent", SMH=[("vent", "PS+PEEP")], note="SMH only"),
    "inhaled_no": _c("vent", SMH=[("vent", "iNO")], note="SMH only"),
    "plateau_pressure": _c("vent", [("vent", "Plateau_Pressure")], note="RBH only"),
    "compliance_dynamic": _c("vent", [("vent", "Compliance_Dynamic")], note="RBH only"),
    "hfov_frequency": _c("vent", [("vent", "HFOV_Frequency")], note="RBH only"),
    "airway_device": _c("vent", [("vent", "Airway")], [("airway", "airwayType")], [(_VENT + "vent_airway_device_merged", GV)], note="text"),
    "ett_size": _c("vent", [("airway", "sizeETT")], [("airway", "ETT_paed")], [(_VENT + "Endotracheal_size_merged", GV), (_VENT + "ETT_size_merged", GV)],
                   note="SMH ETT_paed holds site and size attributes, so rows are not all sizes"),
    # ---- blood gas (GOSH: one long table, filtered by the label in standard_variable; units are in the label) ----
    "bg_ph": _c("blood gas", [("bg", "pH")], [("bg", "pH")], [(_BG, GV, _BGL, ["pH"])]),
    "bg_pco2": _c("blood gas", [("bg", "pCO2")], [("bg", "PCO2")], [(_BG, GV, _BGL, ["pCO2 kPa"])], note="GOSH and SMH kPa; RBH unit: check"),
    "bg_po2": _c("blood gas", [("bg", "pO2")], [("bg", "PO2")], [(_BG, GV, _BGL, ["pO2 kPa"])], note="GOSH and SMH kPa; RBH unit: check"),
    "bg_hco3": _c("blood gas", [("bg", "HCO3")], [("bg", "HCO3")], [(_BG, GV, _BGL, ["HCO3 mmol/L"])]),
    "bg_base_excess": _c("blood gas", [("bg", "BE")], [("bg", "baseExcess")], [(_BG, GV, _BGL, ["Base Excess mmol/L"])]),
    "bg_lactate": _c("blood gas", [("bg", "Lactate")], [("bg", "lactate")], [(_BG, GV, _BGL, ["Lactate mmol/L"])], note="GOSH also has a unit-less 'Lactate' label (118 stays), not included"),
    "bg_glucose": _c("blood gas", [("bg", "Glucose")], [("bg", "glucose_bg")], [(_BG, GV, _BGL, ["Glucose mmol/L"])]),
    "bg_sodium": _c("blood gas", [("bg", "Sodium")], [("bg", "sodium_bg")], [(_BG, GV, _BGL, ["Na+ mmol/L"])]),
    "bg_potassium": _c("blood gas", [("bg", "Potassium")], [("bg", "potassium_bg")], [(_BG, GV, _BGL, ["K+ mmol/L"])]),
    "bg_chloride": _c("blood gas", [("bg", "Chloride")], [("bg", "chloride_bg")], [(_BG, GV, _BGL, ["Cl- mmol/L"])]),
    "bg_calcium": _c("blood gas", [("bg", "Calcium")], [("bg", "calcium_bg")], [(_BG, GV, _BGL, ["Ca++ mmol/L"])], note="ionised at SMH and GOSH; RBH calcium type: check"),
    "bg_hb": _c("blood gas", [("bg", "Hb")], [("bg", "totalHb_bg(g/dL)"), ("bg", "totalHb_bg(g/L)")], [(_BG, GV, _BGL, ["Hb g/L"])],
                note="SMH in two units; RBH unit: check; GOSH also has an 'Hb' label (13 stays), not included"),
    "bg_hct": _c("blood gas", SMH=[("bg", "Hct")], GOSH=[(_BG, GV, _BGL, ["Hct %"]), (_BG, GV, _BGL, ["Hct fract"]), (_BG, GV, _BGL, ["Hct"])],
                 note="GOSH has three labels with different units (percent, fraction, unstated): convert before pooling; RBH has none in the blood gas"),
    "bg_methb": _c("blood gas", [("bg", "MetHb")], [("bg", "MetHb_bg")], [(_BG, GV, _BGL, ["MetHb %"])]),
    "bg_o2_sat": _c("blood gas", [("bg", "O2_Sat")], [("bg", "SaO2")], [(_BG, GV, _BGL, ["SaO2 %"])], note="GOSH SaO2 covers more stays than the other gas values: check what it contains"),
    "bg_venous_sat": _c("blood gas", GOSH=[(_BG, GV, _BGL, ["SvO2 %"]), (_BG, GV, _BGL, ["CvO2"])], note="GOSH only"),
    "bg_sample_type": _c("blood gas", [("bg", "SampleTypeDesc")], [("bg", "bg_source")], [(_BG, GV, _BGL, ["Blood Gas Type"])], note="text; GOSH very sparse"),
    # ---- laboratory ----
    "wbc": _c("lab", [("full_blood_count", "WBC")], [("labs", "WBC")], [(_L + "WBC_merged", GV), (_L + "merged_wbc", GV)], note="GOSH two files overlap"),
    "neutrophils": _c("lab", [("full_blood_count", "Neut")], [("labs", "Neutrophil")], [(_L + "Neutrophils_merged", GV), (_L + "merged_neutrophils", GV)], note="GOSH two files overlap; SMH units: check"),
    "lymphocytes": _c("lab", [("full_blood_count", "Lymph")], [("labs", "Lymphocytes")], [(_L + "Lymphocyte_merged", GV)]),
    "platelets": _c("lab", [("full_blood_count", "Plt")], [("labs", "PLT")], [(_L + "Platelets_merged", GV)]),
    "haemoglobin": _c("lab", [("full_blood_count", "Hb")], [("labs", "Hb(g/dL)"), ("labs", "Hb(g/L)")], [(_L + "Haemoglobin_merged", GV), (_L + "merged_Hb", GV)], note="units differ: check; GOSH two files overlap"),
    "sodium": _c("lab", [("biochemistry", "Sodium")], [("labs", "sodium_lab")], [(_L + "Sodium_merged", GV)]),
    "potassium": _c("lab", [("biochemistry", "Potassium")], [("labs", "potassium_lab")], [(_L + "Potassium_merged", GV)]),
    "urea": _c("lab", [("biochemistry", "Urea")], [("labs", "urea")], [(_L + "Urea_merged", GV)]),
    "creatinine": _c("lab", [("biochemistry", "Creatinine")], [("labs", "creatinine")], [(_L + "Creatinine_merged", GV)]),
    "bilirubin": _c("lab", [("biochemistry", "Bilirubin")], [("labs", "totalBilirubin")], [(_L + "TotalBilirubin_merged", GV)], note="RBH total or direct: check"),
    "albumin": _c("lab", [("biochemistry", "Albumin")], [("labs", "albumin")], [(_L + "Albumin_merged", GV)]),
    "alt": _c("lab", [("biochemistry", "ALT")], [("labs", "ALT")], [(_L + "ALT_merged", GV)]),
    "calcium": _c("lab", [("biochemistry", "Calcium")], [("labs", "calcium_lab")], [(_L + "Calcium_merged", GV)]),
    "phosphate": _c("lab", [("biochemistry", "Phosphate")], [("labs", "phosphate")], [(_L + "Phosphate_merged", GV)]),
    "magnesium": _c("lab", [("biochemistry", "Magnesium")], [("labs", "magnesium")], [(_L + "Magnesium_merged", GV)]),
    "chloride": _c("lab", SMH=[("labs", "chloride_lab")], GOSH=[(_L + "Chloride_merged", GV)], note="RBH has chloride only in blood gas"),
    "glucose": _c("lab", [("biochemistry", "Glucose")], [("labs", "glucose_lab")], [(_L + "Glucose_merged", GV)], note="GOSH file is very small"),
    "inr": _c("lab", [("coagulation", "INR")], [("labs", "INR")], [(_L + "INR_merged", GV)]),
    "aptt": _c("lab", [("coagulation", "APTT")], [("labs", "APTT")], [(_L + "APTT_merged", GV)]),
    "fibrinogen": _c("lab", [("coagulation", "Fibrinogen")], [("labs", "fibrinogen")], [(_L + "Fibrinogen_merged", GV)]),
    # RBH-only laboratory columns (biochemistry): CRP, PCT, AST, ALP, GGT, Amylase, CK, Troponin_T, Troponin_I, BNP, Iron, Ferritin,
    # TIBC, Transferrin, Free_T4, Tot_CO2; (FBC) MonoC, Eosinoph, Basoph, RBC, MCV, MCH, MCHC, PCV; (coagulation) PT, Hep_Conc, D_Dimer, LDH.
    # ---- fluids (semantics differ: hourly, 24 h totals and cumulative; handle when harmonising) ----
    "urine_output": _c("fluids", [("io", "Urine_Output")], [("io", "urineOutput")], note="SMH io has 24 h totals; GOSH has no separate urine output (only totals)"),
    "intake_total": _c("fluids", [("io", "TOTAL_IN")], [("io", "fluidIn")],
                       [(_BAL + "Total_fluids", "cumTotal", "shortLabel", ["Total Fluids In (24hrs)"]),
                        ("July2026extraction_by_alex__pAIC__merged_balance__caboodle_fluid_balance", "hourly_intake_ml")],
                       note="RBH and GOSH caboodle hourly; SMH and GOSH Total_fluids are 24 h totals"),
    "output_total": _c("fluids", [("io", "TOTAL_OUT")], [("io", "fluidOut")],
                       [(_BAL + "Total_fluids", "cumTotal", "shortLabel", ["Total Fluids Out (24hrs)"]),
                        ("July2026extraction_by_alex__pAIC__merged_balance__caboodle_fluid_balance", "hourly_output_ml")]),
    "net_balance": _c("fluids", [("io", "Net_Body_Balance")], [("io", "fluidBalance")],
                      [(_BAL + "Net_Bal", "cumTotal", "shortLabel", ["LOS Net Body Balance"]),
                       ("July2026extraction_by_alex__pAIC__merged_balance__caboodle_fluid_balance", "hourly_intake_ml")],
                      note="GOSH Net_Bal (cumulative over the stay) ends at the Epic switch; the second GOSH source is the Epic-era hourly intake, "
                           "from which balance is derived as intake minus output. SMH fluidBalance is the 24 h balance; RBH hourly: not the same quantity"),
}

# ---- drugs: one presence concept per drug, "any record of the drug in the stay" (checked by name, 2026-11-18) ----
# Label specs: a plain label matches exactly; a label starting with "~" is a case-insensitive regular expression
# (so "^morphine" merges "Morphine Sulphate", "MORPHINE SULFATE" and "MORPHINE SULPHATE IV"; GOSH medsG names carry the
# strength and form, so they are matched on the drug stem).
# What a record means differs by source: RBH sedation/infusion and SMH infusions and GOSH CI/intrv_details are infusion
# rates; RBH meds, SMH medications and GOSH filtered_ALL_drugs are intermittent or oral doses; GOSH medsG (Epic era
# only, 2019-04 to 2023-04) holds administrations with no rate. The value column is the dose (RBH Dose, GOSH valueNumber)
# or, for medsG, the drug name itself (presence only); SMH is presence only.
_GD = "merged_drugs__"
_CI, _ALL, _INTRV, _MEDS = (_GD + "filtered_CI_drugs_merged", _GD + "filtered_ALL_drugs_merged",
                            _GD + "intrv_details", _GD + "medsG_medication_admins")


def _drug(stem, rbh=(), smh=(), ci=False, all_drugs=None, intrv=False, meds=True, note=""):
    """Drug concept. stem: regular expression for the drug name. rbh/smh: tables to search. ci, intrv, meds: GOSH tables
    (meds = Epic-era medsG). all_drugs: True to match the stem in GOSH filtered_ALL_drugs, or a list of exact labels."""
    lab = ["~" + stem]
    g = []
    if ci:
        g.append((_CI, "valueNumber", "shortLabel", lab))
    if intrv:
        g.append((_INTRV, "valueNumber", "shortLabel", lab))
    if all_drugs:
        g.append((_ALL, "valueNumber", "shortLabel", lab if all_drugs is True else list(all_drugs)))
    if meds:
        g.append((_MEDS, "drug_name", "drug_name", lab))
    return _c("drugs", [(t, "Dose", "Drug", lab) for t in rbh], [(t, "Drug_terse", lab) for t in smh], g, note)


_RS = ("sedation", "sedation_old")        # RBH: the two sedation files overlap in time; presence is the union
_NOTE_EPIC = "GOSH: infusion rate before 2019-04 (CI), administration record only after (medsG, no rate): check coverage by year"
CONCEPTS.update({
    # sedation, analgesia, neuromuscular blockade
    "drug_midazolam": _drug("^midazolam", _RS, ("infusions",), ci=True, note=_NOTE_EPIC),
    "drug_morphine": _drug("^morphine", _RS, ("infusions",), ci=True, note="spellings merged (sulphate, sulfate, IV). " + _NOTE_EPIC),
    "drug_fentanyl": _drug("^fentanyl", _RS, ("infusions",), ci=True, note=_NOTE_EPIC),
    "drug_clonidine": _drug("^clonidine", _RS, ("infusions",), ci=True, note=_NOTE_EPIC),
    "drug_vecuronium": _drug("^vecuronium", _RS, ("infusions",), ci=True, note=_NOTE_EPIC),
    "drug_ketamine": _drug("^ketamine", _RS, ("infusions",), ci=True, note=_NOTE_EPIC),
    "drug_propofol": _drug("^propofol", _RS, ("infusions",), ci=True, note=_NOTE_EPIC),
    "drug_dexmedetomidine": _drug("^dexmedetomidine", _RS, ("infusions",), ci=True, note="practice changed from 2015. " + _NOTE_EPIC),
    "drug_atracurium": _drug("^atracurium", _RS, ("infusions",), note="not in GOSH CI; SMH very few stays"),
    "drug_rocuronium": _drug("^rocuronium", (), ("infusions",), ci=True, note="not at RBH. " + _NOTE_EPIC),
    "drug_remifentanil": _drug("^remifentanil", (), ("infusions",), note="not at RBH; GOSH only in Epic-era medsG"),
    # vasoactive
    "drug_noradrenaline": _drug("^noradrenaline", ("infusion",), ("infusions",), ci=True, intrv=True, note=_NOTE_EPIC),
    "drug_adrenaline": _drug("^adrenaline", ("infusion",), ("infusions",), ci=True, intrv=True, note=_NOTE_EPIC),
    "drug_dopamine": _drug("^dopamine", ("infusion",), ("infusions",), ci=True, intrv=True, note=_NOTE_EPIC),
    "drug_milrinone": _drug("^milrinone", ("infusion",), ("infusions",), ci=True, intrv=True, note=_NOTE_EPIC),
    "drug_vasopressin": _drug("^vasopressin", ("infusion",), ("infusions",), ci=True, intrv=True, note=_NOTE_EPIC),
    # diuretics, steroids, chloral hydrate (intermittent or oral at all three sites; furosemide also as an infusion)
    "drug_furosemide": _drug("^furosemide", ("meds", "infusion"), ("medications", "infusions"), ci=True, all_drugs=True,
                             note="bolus, oral and infusion records together"),
    "drug_spironolactone": _drug("^spironolactone", ("meds",), ("medications",), all_drugs=True),
    "drug_dexamethasone": _drug("^dexamethasone", ("meds",), ("medications",), all_drugs=True),
    "drug_hydrocortisone": _drug("^hydrocortisone", ("meds",), ("medications",), all_drugs=["HYDROCORTISONE"],
                                 note="GOSH filtered_ALL_drugs: systemic only (topical and Daktacort excluded)"),
    "drug_methylprednisolone": _drug("^methylprednisolone", ("meds",), ("medications",), all_drugs=True, note="two SMH names merged"),
    "drug_prednisolone": _drug("^prednisolone", (), ("medications",), all_drugs=True, note="not at RBH"),
    "drug_chlorothiazide": _drug("^chlorothiazide", ("meds",), ("medications",), note="GOSH only in Epic-era medsG; SMH very few stays"),
    "drug_chloral_hydrate": _drug("chloral hydrate", (), ("medications",), all_drugs=True, note="not at RBH"),
})
# Not in the map yet: antibiotics (GOSH only: 16 names in its antibiotics table; none supplied at RBH or SMH).


# (net_balance is not listed: the Net_Bal file ends at the switch, but Epic-era balance can be derived from caboodle intake and output.)
# GOSH concepts whose sources end at the CareVue to Epic switch (about 2019-04-19). Coverage is about 65 to 99% before
# 2019 and near 0 after (from `by_year`, 2026-11-17). Usable for GOSH only if restricted to pre-Epic stays; the Epic-era
# data for these is not in the supplied folder.
GOSH_PRE_EPIC_ONLY = [
    "bg_ph", "bg_pco2", "bg_po2", "bg_hco3", "bg_base_excess", "bg_lactate", "bg_glucose", "bg_sodium", "bg_potassium",
    "bg_chloride", "bg_calcium", "bg_hb", "bg_hct", "bg_methb", "bg_o2_sat", "ett_size", "ie_ratio",
    "tidal_volume", "vent_mode",
]

# GOSH drug concepts by what happens at the CareVue to Epic switch (percent of GOSH stays by year, 2026-11-18). Before it the
# drug tables are infusion rates (CI, intrv_details) and intermittent doses (filtered_ALL_drugs); after it only medsG
# (administrations, no rate), which also records boluses. So "any record of the drug" means something different in the two eras
# for the sedatives and analgesics.
GOSH_DRUG_ERA = {
    "consistent": ["drug_furosemide", "drug_spironolactone", "drug_dexamethasone", "drug_hydrocortisone", "drug_methylprednisolone",
                   "drug_prednisolone", "drug_chloral_hydrate", "drug_noradrenaline", "drug_adrenaline", "drug_milrinone"],
    "step_up_at_switch": ["drug_fentanyl", "drug_ketamine", "drug_propofol", "drug_rocuronium", "drug_atracurium",
                          "drug_remifentanil", "drug_clonidine", "drug_chlorothiazide"],
    "falls_at_switch": ["drug_midazolam", "drug_vecuronium", "drug_morphine", "drug_vasopressin"],
    "practice_trend": ["drug_dexmedetomidine", "drug_dopamine"],
}


# --------------------------------------------------------------------------------------------------
def list_sources(assembled_dir, site, show_columns=True, max_columns=60):
    """One line per assembled table: rows and column names (names only, no values; parquet metadata only)."""
    base = Path(assembled_dir) / site
    files = sorted(base.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no parquet files in {base.resolve()}. Pass the full path of the assembled folder "
                                f"(a relative path is read from the notebook's working directory).")
    rows = []
    for p in files:
        pf = pq.ParquetFile(p)
        rows.append({"table": p.stem, "rows": pf.metadata.num_rows, "columns": len(pf.schema.names), "names": pf.schema.names})
    out = pd.DataFrame(rows)
    print(f"{site}: {len(out)} tables, {int(out['rows'].sum()):,} rows")
    for r in out.itertuples():
        print(f"\n{r.table}  ({r.rows:,} rows, {r.columns} columns)")
        if show_columns:
            more = f" ... +{len(r.names) - max_columns} more" if len(r.names) > max_columns else ""
            print("  " + ", ".join(r.names[:max_columns]) + more)
    return out.drop(columns="names")


def _present(s):
    s = s.astype("string").str.strip()
    return s.notna() & ~s.str.lower().isin(MISSING)


def list_values(assembled_dir, site, table, column, min_stays=10, top=60, where=None):
    """Distinct values of one label column (for example GOSH standard_variable or shortLabel) with row and stay counts.
    Values seen in fewer than `min_stays` stays are not shown. Labels only, no patient data.
    where=(column, value) keeps only rows where that column equals the value."""
    base = Path(assembled_dir) / site
    p = base / f"{table}.parquet" if site != "SMH" else SM._path(base, table)
    stay = STAY.get(site, "encounterId")
    want = (stay, column) + ((where[0],) if where else ())
    df = pd.read_parquet(p, columns=SM._cols(p, want))
    df.columns = ["stay", "label"] + (["w"] if where else [])
    if where:
        df = df[df["w"] == where[1]]
    g = df[_present(df["label"])].groupby("label")
    res = pd.DataFrame({"rows": g.size(), "stays": g["stay"].nunique()}).sort_values("stays", ascending=False)
    shown = res[res["stays"] >= min_stays].head(top)
    print(f"{site} {table}.{column}{' where ' + where[0] + '=' + repr(where[1]) if where else ''}: "
          f"{len(res)} distinct values; {len(shown)} shown (>= {min_stays} stays)")
    print(shown.to_string())
    return shown


def _label_mask(s, labels):
    """Rows whose label matches: a plain label exactly, a label starting with "~" as a case-insensitive regular expression."""
    s = s.astype("string").str.strip()
    m = pd.Series(False, index=s.index)
    for lab in labels:
        m |= s.str.contains(lab[1:], case=False, regex=True, na=False) if lab.startswith("~") else (s == lab).fillna(False)
    return m


def _src_label(site, src):
    """Short text naming a source in the detail table."""
    if site == "SMH":
        return f"{src[0]}.{src[1]}" + (f"[{','.join(src[2])}]" if len(src) == 3 else "")
    return ".".join(str(x) for x in src[:2]) + (f"[{','.join(src[3])}]" if len(src) > 2 else "")


def _read(assembled_dir, site, src):
    """Rows (stay, value) for one source. For SMH value is None for the io table and for name-matched drug sources (presence only).
    Sources with a label column keep only the rows whose label matches (see _label_mask)."""
    base = Path(assembled_dir) / site
    if site == "RBH":
        table, col = src[0], src[1]
        p = base / f"ai_picu_{table}.parquet"
        want = (STAY["RBH"], col) + ((src[2],) if len(src) > 2 else ())
        df = pd.read_parquet(p, columns=SM._cols(p, want))
        df.columns = ["stay", "value"] + (["label"] if len(src) > 2 else [])
        if len(src) > 2:
            df = df[_label_mask(df["label"], src[3])][["stay", "value"]]
        return df
    if site == "GOSH":
        file, col = src[0], src[1]
        p = base / f"{file}.parquet"
        want = (STAY["GOSH"], col) + ((src[2],) if len(src) > 2 else ())
        df = pd.read_parquet(p, columns=SM._cols(p, want))
        df.columns = ["stay", "value"] + (["label"] if len(src) > 2 else [])
        if len(src) > 2:
            df = df[_label_mask(df["label"], src[3])][["stay", "value"]]
        return df
    if len(src) == 3:                                      # SMH, by drug name: (table, name column, [labels])
        p = SM._path(base, src[0])
        df = pd.read_parquet(p, columns=SM._cols(p, ("encounterId", src[1])))
        df.columns = ["stay", "label"]
        return df[_label_mask(df["label"], src[2])][["stay"]].assign(value=PRESENT)
    table, concept = src                                   # SMH, by interventionId / attributeId
    p = SM._path(base, table)
    keys = SM.KEY.get(table, ("interventionId",))
    vcol = None if table == "io" else "terseForm"
    want = ("encounterId",) + keys + ((vcol,) if vcol else ())
    df = pd.read_parquet(p, columns=SM._cols(p, want))
    df.columns = ["stay"] + list(keys) + (["value"] if vcol else [])
    ids = df[keys[0]].astype("string").str.strip()
    for k in keys[1:]:
        ids = ids + "_" + df[k].astype("string").str.strip()
    out = df[ids.isin(SM.MAPPINGS[table][concept])]
    out = out[["stay"] + (["value"] if vcol else [])]
    if not vcol:
        out = out.assign(value=PRESENT)
    return out


PRESENT = "__present__"      # value of sources that only record that something exists (SMH io, drug names)


def _stats(df):
    """Rows with a real value only: a column that is entirely empty counts no stays (earlier versions counted every stay)."""
    d = df[_present(df["value"])]
    num = pd.to_numeric(d["value"], errors="coerce") if not (d["value"] == PRESENT).all() else pd.Series(dtype=float)
    q = num.quantile([.05, .5, .95]) if num.notna().any() else pd.Series([float("nan")] * 3)
    return {"rows": len(d), "stays": set(d["stay"].astype(str)),
            "numeric_pct": round(100 * num.notna().mean(), 1) if len(num) else float("nan"),
            "p5": q.iloc[0], "median": q.iloc[1], "p95": q.iloc[2]}


def build(assembled_dir, static=None, n_stays=None, concepts=None, sites=SITES, save_to=None):
    """Measure every source in the map. Returns (detail, summary).
    static: the pooled static table (columns site, stay_key). Only its stays are counted, and the denominators come from it
            (the assembled tables also hold the few stays the static table drops for conflicting PICANet rows).
    n_stays: denominators as a dict, used only when static is not given.
    detail: one row per concept, site and source (stays, rows, % numeric, p5, median, p95).
    summary: one row per concept: stays and % of the site's stays at each site (union over that site's sources)."""
    keep = None
    if static is not None:
        keep = {s: set(static.loc[static["site"] == s, "stay_key"].astype(str)) for s in sites}
        n_stays = {s: len(keep[s]) for s in sites}
    det, summ = [], []
    seen = {s: [0, 0] for s in sites}                       # stays matched to the static table, stays read
    for name, c in CONCEPTS.items():
        if concepts and name not in concepts:
            continue
        srow = {"concept": name, "group": c["group"], "note": c["note"]}
        for site in sites:
            allstays = set()
            for src in c[site]:
                label = _src_label(site, src)
                try:
                    st = _stats(_read(assembled_dir, site, src))
                except (FileNotFoundError, KeyError) as e:
                    det.append({"concept": name, "site": site, "source": label, "status": f"unavailable: {str(e)[:60]}"})
                    continue
                got = st.pop("stays")
                if keep is not None:
                    seen[site][1] += len(got)
                    got = got & keep[site]
                    seen[site][0] += len(got)
                allstays |= got
                det.append({"concept": name, "site": site, "source": label, "status": "ok", "stays": len(got), **st})
            srow[f"{site}_stays"] = len(allstays) if c[site] else None
            if n_stays and c[site]:
                srow[f"{site}_pct"] = round(100 * len(allstays) / n_stays[site], 1)
        summ.append(srow)
    for site, (hit, tot) in seen.items():
        if tot and hit / tot < 0.9:
            print(f"WARNING {site}: only {100 * hit / tot:.0f}% of the stays read match static stay_key; check the key format")
    detail, summary = pd.DataFrame(det), pd.DataFrame(summ)
    summary["gosh_pre_epic_only"] = summary["concept"].isin(GOSH_PRE_EPIC_ONLY)
    era = {n: k for k, v in GOSH_DRUG_ERA.items() for n in v}
    summary["gosh_drug_era"] = summary["concept"].map(era)
    for col in [c for c in summary.columns if c.endswith("_stays")]:
        summary[col] = summary[col].astype("Int64")
    if save_to:
        Path(save_to).parent.mkdir(parents=True, exist_ok=True)
        summary.to_csv(Path(save_to).with_name("concept_summary.csv"), index=False)
        detail.to_csv(Path(save_to).with_name("concept_detail.csv"), index=False)
    return detail, summary


def survivors(summary, min_pct=50, sites=SITES, exclude_era=False, exclude_groups=("drugs",)):
    """Concepts present at all the given sites with at least min_pct of that site's stays.
    exclude_era=True also drops the concepts whose GOSH source ends at the Epic switch (GOSH_PRE_EPIC_ONLY).
    Drugs are excluded by default: their coverage is the share of stays that received the drug, not how well it is recorded,
    so a coverage threshold does not apply to them."""
    ok = ~summary["group"].isin(exclude_groups)
    for s in sites:
        ok &= summary[f"{s}_pct"].fillna(0) >= min_pct
    if exclude_era:
        ok &= ~summary["concept"].isin(GOSH_PRE_EPIC_ONLY)
    return summary[ok].reset_index(drop=True)


def by_year(assembled_dir, static, concepts, sites=SITES, years=None):
    """Percent of each site's stays with the concept, by admission year (static table columns: site, stay_key, year).
    Shows whether low coverage is an era effect (a source that only exists in some years). Counts only."""
    rows = []
    stat = static[["site", "stay_key", "year"]].assign(stay_key=lambda d: d["stay_key"].astype(str))
    for name in concepts:
        c = CONCEPTS[name]
        for site in sites:
            have = set()
            for src in c[site]:
                try:
                    have |= _stats(_read(assembled_dir, site, src)).pop("stays")
                except (FileNotFoundError, KeyError):
                    continue
            s = stat[stat["site"] == site].assign(has=lambda d: d["stay_key"].isin(have))
            g = s.groupby("year")["has"].agg(["sum", "size"])
            for y, r in g.iterrows():
                rows.append({"concept": name, "site": site, "year": y, "stays": int(r["sum"]), "n": int(r["size"]),
                             "pct": round(100 * r["sum"] / r["size"], 1) if c[site] else float("nan")})
    out = pd.DataFrame(rows)
    if years is not None:
        out = out[out["year"].isin(years)]
    piv = out.pivot_table(index=["concept", "site"], columns="year", values="pct", sort=False)
    return out, piv


def era_columns(path, time_col="hour_timestamp", split="2019-04-20"):
    """For an hourly parquet (one row per hour, one column per variable): rows per year, and for every column the percent of
    rows with a value before and after `split` (the GOSH CareVue to Epic switch). Counts only.
    Use it to check whether a derived dataset holds post-switch data that the assembled tables lack."""
    df = pd.read_parquet(path)
    t = pd.to_datetime(df[time_col], errors="coerce")
    print(f"{len(df):,} rows; time {t.min()} to {t.max()}; unparseable times: {int(t.isna().sum()):,}")
    print("rows by year:", t.dt.year.value_counts().sort_index().to_dict())
    pre, post = (t < split), (t >= split)
    cols = [c for c in df.columns if c != time_col]
    res = pd.DataFrame({"pre_pct": 100 * df.loc[pre, cols].notna().mean(),
                        "post_pct": 100 * df.loc[post, cols].notna().mean()}).round(1)
    res["rows_pre"], res["rows_post"] = int(pre.sum()), int(post.sum())
    return res


def availability(assembled_dir, static, concepts=None, sites=SITES, save_to=None):
    """Stay x concept table of booleans: does the stay have at least one value of the concept?
    <NA> means the site has no source for the concept at all (not collected), False means collected but absent for this stay.
    Row-level (one row per stay): keep it in derived/ only. It lets users choose a feature set and the stays that have it."""
    names = [n for n in CONCEPTS if (n in concepts if concepts else CONCEPTS[n]["group"] != "drugs")]   # default: not the drugs
    parts = []
    for site in sites:
        keys = static.loc[static["site"] == site, "stay_key"].astype(str).tolist()
        df = pd.DataFrame(index=pd.MultiIndex.from_product([[site], keys], names=["site", "stay_key"]))
        for n in names:
            c = CONCEPTS[n]
            if not c[site]:
                df[n] = pd.array([pd.NA] * len(keys), dtype="boolean")
                continue
            have = set()
            for src in c[site]:
                try:
                    have |= _stats(_read(assembled_dir, site, src)).pop("stays")
                except (FileNotFoundError, KeyError):
                    pass
            df[n] = pd.array([k in have for k in keys], dtype="boolean")
        parts.append(df)
    out = pd.concat(parts)
    if save_to:
        Path(save_to).parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(save_to)
    return out


def pattern_uniqueness(avail, by_group=False, min_count=10):
    """How identifying is the availability pattern itself? Counts distinct patterns (site included) and the stays whose
    pattern is shared by fewer than `min_count` stays. by_group=True collapses the concepts to their groups first
    (vitals, vent, blood gas, lab, fluids). Counts only."""
    a = avail.copy()
    if by_group:
        groups = {}
        for n in a.columns:
            groups.setdefault(CONCEPTS[n]["group"], []).append(n)
        a = pd.DataFrame({g: a[cols].fillna(False).astype(bool).any(axis=1) for g, cols in groups.items()}, index=a.index)
    code = a.astype("string").fillna("-").replace({"True": "1", "False": "0"})
    pat = code.apply(lambda r: "".join(r), axis=1)
    site = pd.Series(a.index.get_level_values("site"), index=a.index)
    key = site.astype(str) + ":" + pat
    size = key.map(key.value_counts())
    res = {"stays": len(a), "distinct_patterns": int(key.nunique()), f"patterns_with_fewer_than_{min_count}_stays": int((key.value_counts() < min_count).sum()),
           f"stays_in_those_patterns": int((size < min_count).sum()), "share_of_stays_pct": round(100 * float((size < min_count).mean()), 1)}
    return res


def rare_share(avail, static, by=("site",), min_count=10):
    """Share of stays whose availability pattern (site included) is shared by fewer than `min_count` stays,
    broken down by columns of the static table (for example site, year, diagnosis_group). Counts only."""
    a = avail.copy()
    code = a.astype("string").fillna("-").replace({"True": "1", "False": "0"})
    pat = code.apply(lambda r: "".join(r), axis=1)
    key = pd.Series(a.index.get_level_values("site"), index=a.index).astype(str) + ":" + pat
    rare = (key.map(key.value_counts()) < min_count).rename("rare").reset_index()
    rare["stay_key"] = rare["stay_key"].astype(str)
    st = static.assign(stay_key=static["stay_key"].astype(str))
    m = st.merge(rare, on=["site", "stay_key"], how="inner")
    by = list(by)
    g = m.groupby(by)["rare"].agg(stays="size", rare_stays="sum")
    g["rare_pct"] = (100 * g["rare_stays"] / g["stays"]).round(1)
    return g


def names_by_year(assembled_dir, site, table, column, time_col, names=None, min_stays=10, top=20):
    """Number of stays per year in which each label of `column` appears, from the row times in `time_col`.
    Use it to see where a drug source starts or stops (for example GOSH before and after the Epic switch).
    names=None uses the `top` labels with most stays. Counts only; years with fewer than `min_stays` stays are blanked."""
    base = Path(assembled_dir) / site
    p = base / f"{table}.parquet" if site != "SMH" else SM._path(base, table)
    stay = STAY.get(site, "encounterId")
    df = pd.read_parquet(p, columns=SM._cols(p, (stay, column, time_col)))
    df.columns = ["stay", "label", "t"]
    df = df[_present(df["label"])]
    if names is None:
        names = df.groupby("label")["stay"].nunique().sort_values(ascending=False).head(top).index
    df = df[df["label"].isin(list(names))]
    df["year"] = pd.to_datetime(df["t"], errors="coerce", format="mixed").dt.year
    out = df.groupby(["year", "label"])["stay"].nunique().unstack("label").fillna(0).astype(int)
    out = out.where(out >= min_stays)
    out["unparsed_time_rows"] = int(df["year"].isna().sum())
    return out