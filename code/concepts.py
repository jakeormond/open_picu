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

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

import inventory as I
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
    "ie_ratio": _c("vent", [("vent", "IE_Ratio")], [("vent", "IE_ratio")], [(_VENT + "merged_IE_ratios", GV, "source", ["I:E Ratio.Expiratory"])],
                   note="the ratio 1:x. RBH: text 'x:y' (placeholder '.:.'); SMH: IDs 4185 and 4186 hold two rows per time (1 and x, x not 1); "
                        "GOSH: the expiratory part x only (inspiratory rows are 1; the setting rows have no value). SMH values pool both parts, so the SMH range is not x alone"),
    "rr_set": _c("vent", [("vent", "Vent_Rate")], [("vent", "RR(set)")], [(_VENT + "vent_Respiratory_Rate_merged", GV)], note="GOSH 'Respiratory_Rate' assumed to be the set rate: check"),
    "ps_peep": _c("vent", SMH=[("vent", "PS+PEEP")], note="SMH only"),
    "inhaled_no": _c("vent", SMH=[("vent", "iNO")], note="SMH only"),
    "plateau_pressure": _c("vent", [("vent", "Plateau_Pressure")], note="RBH only"),
    "compliance_dynamic": _c("vent", [("vent", "Compliance_Dynamic")], note="RBH only"),
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
    "intake_total": _c("fluids", [("io", "TOTAL_IN"), ("io", "Total_In_ex_dialysis")], [("io", "fluidIn")],
                       [(_BAL + "Total_fluids", "cumTotal", "shortLabel", ["Total Fluids In (24hrs)"]),
                        ("July2026extraction_by_alex__pAIC__merged_balance__caboodle_fluid_balance", "hourly_intake_ml")],
                       note="RBH TOTAL_IN and TOTAL_OUT are empty columns (checked 2026-11-18): the ex-dialysis totals are the source, so dialysis fluid is not counted; "
                            "RBH and GOSH caboodle hourly; SMH and GOSH Total_fluids are 24 h totals"),
    "output_total": _c("fluids", [("io", "TOTAL_OUT"), ("io", "Total_Out_ex_dialysis")], [("io", "fluidOut")],
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


TIME_CANDIDATES = ["observation_datetime", "utcChartTime", "SampleCollectDateTime", "start_datetime", "hour_start", "chartTime", "chart_time"]


def _to_dt(s):
    """Row times as datetimes, whatever the site's format (SAS-style at RBH, ISO or day-first elsewhere): the study's own parser."""
    s = s.astype("string").str.strip()
    return I.parse_dates(s.mask(s.str.lower().isin(MISSING)))[0]


def time_column(path):
    """The row-time column of an assembled table: the first of TIME_CANDIDATES present (case-insensitive)."""
    names = {n.lower(): n for n in pq.ParquetFile(path).schema.names}
    for c in TIME_CANDIDATES:
        if c.lower() in names:
            return names[c.lower()]
    raise KeyError(f"{Path(path).name}: no time column among {TIME_CANDIDATES}")


def _read(assembled_dir, site, src, time=False):
    """Rows (stay, value) for one source; with time=True also t (the raw row time, text). For SMH value is None for the io table
    and for name-matched drug sources (presence only). Sources with a label column keep only the rows whose label matches
    (see _label_mask)."""
    base = Path(assembled_dir) / site
    if site in ("RBH", "GOSH"):
        if site == "RBH":
            p = base / f"ai_picu_{src[0]}.parquet"
        else:
            p = base / f"{src[0]}.parquet"
        col = src[1]
        tcol = time_column(p) if time else None
        want = (STAY[site], col) + ((src[2],) if len(src) > 2 else ()) + ((tcol,) if tcol else ())
        df = pd.read_parquet(p, columns=SM._cols(p, want))
        df.columns = ["stay", "value"] + (["label"] if len(src) > 2 else []) + (["t"] if tcol else [])
        if len(src) > 2:
            df = df[_label_mask(df["label"], src[3])].drop(columns="label")
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
    tcol = time_column(p) if time else None
    want = ("encounterId",) + keys + ((vcol,) if vcol else ()) + ((tcol,) if tcol else ())
    df = pd.read_parquet(p, columns=SM._cols(p, want))
    df.columns = ["stay"] + list(keys) + (["value"] if vcol else []) + (["t"] if tcol else [])
    ids = df[keys[0]].astype("string").str.strip()
    for k in keys[1:]:
        ids = ids + "_" + df[k].astype("string").str.strip()
    out = df[ids.isin(SM.MAPPINGS[table][concept])]
    out = out[["stay"] + (["value"] if vcol else []) + (["t"] if tcol else [])]
    if not vcol:
        out = out.assign(value=PRESENT)
    return out


PRESENT = "__present__"      # value of sources that only record that something exists (SMH io, drug names)


def _stats(df):
    """Rows with a real value only: a column that is entirely empty counts no stays (earlier versions counted every stay).
    For a numeric source (20% or more of its values are numbers) a stay counts only if it has a numeric value, so rows that hold a
    word instead of a value (SMH labs: "Blood") do not inflate coverage; for text sources every stay with a value counts."""
    d = df[_present(df["value"])]
    num = pd.to_numeric(d["value"], errors="coerce") if not (d["value"] == PRESENT).all() else pd.Series(dtype=float)
    q = num.quantile([.05, .5, .95]) if num.notna().any() else pd.Series([float("nan")] * 3)
    numeric_stays = set(d.loc[num.notna(), "stay"].astype(str)) if len(num) else set()
    numeric_source = len(num) > 0 and num.notna().mean() >= 0.2
    return {"rows": len(d), "stays": numeric_stays if numeric_source else set(d["stay"].astype(str)), "numeric_stays": numeric_stays,
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
                numeric = st.pop("numeric_stays")
                if keep is not None:
                    seen[site][1] += len(got)
                    got = got & keep[site]
                    numeric = numeric & keep[site]
                    seen[site][0] += len(got)
                allstays |= got
                det.append({"concept": name, "site": site, "source": label, "status": "ok", "stays": len(got), "stays_numeric": len(numeric), **st})
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
    df["year"] = _to_dt(df["t"]).dt.year
    out = df.groupby(["year", "label"])["stay"].nunique().unstack("label").fillna(0).astype(int)
    out = out.where(out >= min_stays)
    out["unparsed_time_rows"] = int(df["year"].isna().sum())
    return out


def compare_ranges(detail, sites=SITES, ratio_flag=3.0):
    """Side-by-side p5 / median / p95 for each concept and site (the source with most stays when a site has several),
    to spot unit differences. `unit_flag` is set when the largest median is more than `ratio_flag` times the smallest
    (both positive) or when the sign differs. Ranges only; numeric concepts only."""
    d = detail[(detail.get("status") == "ok") & detail["median"].notna()].copy()
    d = d.sort_values("stays", ascending=False).drop_duplicates(["concept", "site"])
    rows = []
    for name, g in d.groupby("concept", sort=False):
        row = {"concept": name}
        meds = []
        for s in sites:
            r = g[g["site"] == s]
            if len(r):
                r = r.iloc[0]
                row[s] = f"{r['p5']:.4g} / {r['median']:.4g} / {r['p95']:.4g}"
                meds.append(r["median"])
            else:
                row[s] = ""
        pos = [m for m in meds if m > 0]
        row["unit_flag"] = bool(len(meds) > 1 and ((len(pos) == len(meds) and max(pos) / min(pos) > ratio_flag)
                                                   or (len(pos) != len(meds))))
        rows.append(row)
    return pd.DataFrame(rows)


def value_checks(assembled_dir, concepts, sites=SITES):
    """Per concept, site and source: number of values, percent non-numeric, percent exactly zero, percent negative.
    Use it to find placeholder zeros, lost negative values (for example base excess) and text where a number is expected.
    Counts only. Presence-only sources (SMH io and drug names) are skipped."""
    rows = []
    for name in concepts:
        c = CONCEPTS[name]
        for site in sites:
            for src in c[site]:
                try:
                    df = _read(assembled_dir, site, src)
                except (FileNotFoundError, KeyError):
                    continue
                v = df["value"]
                v = v[_present(v)]
                if len(v) == 0 or (v == PRESENT).all():
                    continue
                num = pd.to_numeric(v, errors="coerce")
                rows.append({"concept": name, "site": site, "source": _src_label(site, src), "values": len(v),
                             "nonnumeric_pct": round(100 * num.isna().mean(), 1),
                             "zero_pct": round(100 * (num == 0).mean(), 2),
                             "negative_pct": round(100 * (num < 0).mean(), 2)})
    return pd.DataFrame(rows)


def interval_check(assembled_dir, site, table, label_col, start_col, end_col, min_stays=10, top=12):
    """For tables whose rows cover a time interval (GOSH balance files: start_datetime, end_datetime): per label, the number of
    rows and stays and how long the intervals are (median hours, share of 1 hour or less, share of about 24 hours, longest).
    Tells hourly values from 24-hour totals and from cumulative values. Counts only."""
    base = Path(assembled_dir) / site
    p = base / f"{table}.parquet" if site != "SMH" else SM._path(base, table)
    stay = STAY.get(site, "encounterId")
    df = pd.read_parquet(p, columns=SM._cols(p, (stay, label_col, start_col, end_col)))
    df.columns = ["stay", "label", "s", "e"]
    df = df[_present(df["label"])]
    hrs = (_to_dt(df["e"]) - _to_dt(df["s"])).dt.total_seconds() / 3600
    df = df.assign(h=hrs)
    out = df.groupby("label").agg(rows=("h", "size"), stays=("stay", "nunique"), median_h=("h", "median"), max_h=("h", "max"))
    out["pct_le_1h"] = df.groupby("label")["h"].apply(lambda x: round(100 * (x <= 1.01).mean(), 1))
    out["pct_23_25h"] = df.groupby("label")["h"].apply(lambda x: round(100 * ((x >= 23) & (x <= 25)).mean(), 1))
    out["pct_unparsed"] = df.groupby("label")["h"].apply(lambda x: round(100 * x.isna().mean(), 1))
    out = out[out["stays"] >= min_stays].sort_values("stays", ascending=False).head(top)
    print(f"{site} {table}: {len(out)} labels shown (>= {min_stays} stays)")
    print(out.round(2).to_string())
    return out


def _io_read(assembled_dir, ids):
    """SMH io rows for the given interventionIds: stay, id, time, hourTotal, cumTotal, isReset (numeric)."""
    p = SM._path(Path(assembled_dir) / "SMH", "io")
    cols = SM._cols(p, ("encounterId", "interventionId", "utcChartTime", "hourTotal", "cumTotal", "isReset"))
    df = pd.read_parquet(p, columns=cols)
    df.columns = ["stay", "id", "t", "hour", "cum", "reset"]
    df["id"] = df["id"].astype("string").str.strip()
    df = df[df["id"].isin([str(i) for i in ids])].copy()
    df["t"] = _to_dt(df["t"])
    for c in ("hour", "cum", "reset"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.drop_duplicates()


def io_diff_check(assembled_dir, ids=("2045", "113860", "2073", "113859", "1851", "1912", "1945"), tol=1.0):
    """Is `hourTotal` the change in `cumTotal` between consecutive rows? Per interventionId: median gap between rows (hours),
    share of consecutive pairs where cumTotal falls (a reset), and among the others the share where diff(cumTotal) equals hourTotal
    within `tol` ml. If it holds, hourly amounts can also be derived from cumulative-only sources (GOSH). Counts only."""
    df = _io_read(assembled_dir, ids).sort_values(["id", "stay", "t"])
    rows = []
    for i, g in df.groupby("id"):
        same = g["stay"].eq(g["stay"].shift())
        d = g["cum"].diff().where(same)
        gap = (g["t"].diff().dt.total_seconds() / 3600).where(same)
        fall = d < 0
        ok = ((d - g["hour"]).abs() <= tol)[~fall & d.notna()]
        at_reset = ((g["cum"] - g["hour"]).abs() <= tol)[fall & d.notna()]
        rows.append({"id": i, "rows": len(g), "median_gap_h": round(float(gap.median()), 2), "pct_cum_falls": round(100 * float(fall[d.notna()].mean()), 1),
                     "pct_reset_flag": round(100 * float((g["reset"] == 1).mean()), 1),
                     "pct_diff_equals_hour": round(100 * float(ok.mean()), 1) if len(ok) else float("nan"),
                     "pct_cum_equals_hour_at_reset": round(100 * float(at_reset.mean()), 1) if len(at_reset) else float("nan")})
    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    return out


def io_reconcile(assembled_dir, total_ids, component_ids, tol=1.0, top=6):
    """Which components add up to a total? For rows where the total (any of `total_ids`; the two ID sets cover different periods)
    and every component are present at the same stay and time, the share of rows where the total equals the sum of each subset of
    the components (hourTotal values, within `tol` ml). Shows the best `top` subsets. Counts only."""
    from itertools import combinations
    df = _io_read(assembled_dir, list(total_ids) + list(component_ids))
    w = df.pivot_table(index=["stay", "t"], columns="id", values="hour", aggfunc="first")
    tot = w[[c for c in map(str, total_ids) if c in w]].bfill(axis=1).iloc[:, 0]
    comps = [c for c in map(str, component_ids) if c in w]
    w = w[comps].fillna(0)
    ok = tot.notna()
    print(f"{int(ok.sum()):,} stay-hours with a total; components found: {comps}")
    res = []
    for r in range(1, len(comps) + 1):
        for sub in combinations(comps, r):
            res.append({"components": "+".join(sub), "pct_equal_total": round(100 * float(((w.loc[ok, list(sub)].sum(axis=1) - tot[ok]).abs() <= tol).mean()), 1),
                        "pct_sum_above_total": round(100 * float(((w.loc[ok, list(sub)].sum(axis=1) - tot[ok]) > tol).mean()), 1)})
    out = pd.DataFrame(res).sort_values("pct_equal_total", ascending=False).head(top)
    print(out.to_string(index=False))
    return out


def cum_check(assembled_dir, site, table, label_col, labels, time_col, value_col, stay_col=None):
    """For a cumulative-only source (GOSH Total_fluids and Net_Bal): per label, the median gap between consecutive rows of a stay (hours),
    the share of gaps over 1.5 hours, the share of pairs where the cumulative value falls (a reset), and the typical hour of day of a
    reset. Shows whether hourly amounts can be derived by differencing. Counts only."""
    base = Path(assembled_dir) / site
    p = base / f"{table}.parquet" if site != "SMH" else SM._path(base, table)
    stay = stay_col or STAY.get(site, "encounterId")
    df = pd.read_parquet(p, columns=SM._cols(p, (stay, label_col, time_col, value_col)))
    df.columns = ["stay", "label", "t", "v"]
    df = df[df["label"].isin(labels)].copy()
    df["t"] = _to_dt(df["t"])
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    rows = []
    for lab, g in df.sort_values(["stay", "t"]).groupby("label"):
        same = g["stay"].eq(g["stay"].shift())
        gap = (g["t"].diff().dt.total_seconds() / 3600).where(same)
        d = g["v"].diff().where(same)
        fall = d < 0
        hrs = g.loc[fall.fillna(False), "t"].dt.hour
        rows.append({"label": lab, "rows": len(g), "median_gap_h": round(float(gap.median()), 2), "pct_gap_over_1_5h": round(100 * float((gap > 1.5).mean()), 1),
                     "pct_falls": round(100 * float(fall[d.notna()].mean()), 1),
                     "most_common_reset_hour": int(hrs.mode().iloc[0]) if len(hrs) else None})
    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    return out


def caboodle_check(assembled_dir, table="July2026extraction_by_alex__pAIC__merged_balance__caboodle_fluid_balance"):
    """GOSH caboodle fluid balance (hourly, Epic era): hours per stay-day, share of hours that are exactly zero (zero-filled gaps?),
    the hour of day at which the daily columns change (the day boundary), and whether the hourly values add up to the daily columns,
    both by calendar day and by that boundary. Counts only."""
    p = Path(assembled_dir) / "GOSH" / f"{table}.parquet"
    cols = SM._cols(p, ("stay_id", "hour_start", "hourly_intake_ml", "hourly_output_ml", "daily_intake_ml", "daily_output_ml"))
    df = pd.read_parquet(p, columns=cols)
    df.columns = ["stay", "t", "hi", "ho", "di", "do"]
    for c in ("hi", "ho", "di", "do"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["t"] = _to_dt(df["t"])
    df = df.sort_values(["stay", "t"])
    same = df["stay"].eq(df["stay"].shift())
    changed = same & (df["di"].ne(df["di"].shift()) | df["do"].ne(df["do"].shift()))
    boundary = int(df.loc[changed, "t"].dt.hour.mode().iloc[0]) if changed.any() else 0
    res = {"rows": len(df), "pct_hours_zero_intake": round(100 * float((df["hi"] == 0).mean()), 1),
           "pct_hours_zero_output": round(100 * float((df["ho"] == 0).mean()), 1),
           "pct_hours_intake_missing": round(100 * float(df["hi"].isna().mean()), 1),
           "daily_columns_change_at_hour": boundary,
           "pct_hours_where_daily_changes": round(100 * float(changed.mean()), 1)}
    for name, day in (("calendar_day", df["t"].dt.date), ("boundary_day", (df["t"] - pd.Timedelta(hours=boundary)).dt.date)):
        g = df.assign(day=day).groupby(["stay", "day"]).agg(hours=("hi", "size"), sum_in=("hi", "sum"), sum_out=("ho", "sum"),
                                                              di=("di", "max"), do=("do", "max"), di_n=("di", "nunique"))
        res[f"{name}: stay_days"] = len(g)
        res[f"{name}: pct_days_daily_intake_constant"] = round(100 * float((g["di_n"] <= 1).mean()), 1)
        res[f"{name}: pct_days_hourly_sum_equals_daily_intake"] = round(100 * float(((g["sum_in"] - g["di"]).abs() <= 1).mean()), 1)
        res[f"{name}: pct_days_hourly_sum_equals_daily_output"] = round(100 * float(((g["sum_out"] - g["do"]).abs() <= 1).mean()), 1)
        res[f"{name}: pct_days_daily_intake_zero"] = round(100 * float((g["di"] == 0).mean()), 1)
    for k, v in res.items():
        print(f"{k}: {v}")
    return res


def value_shapes(assembled_dir, concept, site, top=8):
    """For the non-numeric values of a concept's sources: the most common SHAPES (each run of digits replaced by 9, so
    '97 L' becomes '9 L'), with counts. Shows what text sits where a number is expected (flags, units, ranges) without values."""
    import re
    for src in CONCEPTS[concept][site]:
        try:
            v = _read(assembled_dir, site, src)["value"]
        except (FileNotFoundError, KeyError):
            continue
        v = v[_present(v)].astype("string").str.strip()
        bad = v[pd.to_numeric(v, errors="coerce").isna()]
        print(f"\n{concept} {site} {_src_label(site, src)}: {len(v):,} values, {len(bad):,} non-numeric ({100 * len(bad) / max(len(v), 1):.1f}%)")
        if len(bad):
            sh = bad.map(lambda x: re.sub(r"\d+(\.\d+)?", "9", x)).value_counts().head(top)
            print("  shapes: " + "; ".join(f"{k!r}: {n:,}" for k, n in sh.items()))


def percentiles_by(assembled_dir, site, table, value_col, group_col, min_rows=500):
    """Rows, percent non-numeric and p5 / median / p95 of one value column, split by another column (for example a unit or label
    column). Shows which unit or label a range belongs to. Counts and ranges only."""
    base = Path(assembled_dir) / site
    p = base / f"{table}.parquet" if site != "SMH" else SM._path(base, table)
    df = pd.read_parquet(p, columns=SM._cols(p, (group_col, value_col)))
    df.columns = ["g", "v"]
    df = df[_present(df["v"])]
    df["n"] = pd.to_numeric(df["v"], errors="coerce")
    out = df.groupby("g", dropna=False).agg(rows=("n", "size"), nonnumeric_pct=("n", lambda x: round(100 * x.isna().mean(), 1)),
                                            p5=("n", lambda x: x.quantile(.05)), median=("n", "median"), p95=("n", lambda x: x.quantile(.95)))
    out = out[out["rows"] >= min_rows].sort_values("rows", ascending=False)
    print(f"{site} {table}.{value_col} by {group_col}")
    print(out.round(3).to_string())
    return out


def be_ph_check(assembled_dir, site):
    """Base excess against pH from the same sample (RBH, GOSH): median base excess in acidotic (pH below 7.25), normal and alkalotic
    samples, and the share of acidotic samples that have a base excess. A base excess with its sign lost shows large positive values in
    acidosis; one with negatives dropped shows acidotic samples without a value. Counts and medians only."""
    base = Path(assembled_dir) / site
    if site == "RBH":
        p = base / "ai_picu_bg.parquet"
        df = pd.read_parquet(p, columns=SM._cols(p, ("stay_key", "SampleCollectDateTime", "pH", "BE")))
        df.columns = ["stay", "t", "ph", "be"]
    elif site == "GOSH":
        p = base / f"{_BG}.parquet"
        raw = pd.read_parquet(p, columns=SM._cols(p, (STAY["GOSH"], "observation_datetime", GV, _BGL)))
        raw.columns = ["stay", "t", "v", "lab"]
        raw = raw[raw["lab"].isin(["pH", "Base Excess mmol/L"])]
        df = raw.pivot_table(index=["stay", "t"], columns="lab", values="v", aggfunc="first").reset_index()
        df = df.rename(columns={"pH": "ph", "Base Excess mmol/L": "be"})
    else:
        raise ValueError("RBH or GOSH only")
    df["ph"] = pd.to_numeric(df["ph"], errors="coerce")
    df["be"] = pd.to_numeric(df["be"], errors="coerce")
    df = df[df["ph"].between(6.5, 7.8)]
    for name, m in (("pH < 7.25", df["ph"] < 7.25), ("pH 7.25 to 7.45", df["ph"].between(7.25, 7.45)), ("pH > 7.45", df["ph"] > 7.45)):
        s = df[m]
        print(f"{site} {name}: {len(s):,} samples; with base excess {100 * s['be'].notna().mean():.1f}%; median base excess {s['be'].median():.2f}; "
              f"negative {100 * (s['be'] < 0).sum() / max(s['be'].notna().sum(), 1):.1f}%")


def bp_order_check(assembled_dir, site, kind="NIBP"):
    """Systolic, mean and diastolic pressure from the same time (RBH, GOSH): share of readings where diastolic is not below mean, mean is
    not below systolic, or diastolic is not below systolic (all physiologically impossible). Counts only."""
    base = Path(assembled_dir) / site
    if site == "RBH":
        p = base / "ai_picu_vitals.parquet"
        s, m, d = [f"{kind}_{x}" for x in "smd"]
        df = pd.read_parquet(p, columns=SM._cols(p, (s, m, d)))
        df.columns = ["s", "m", "d"]
    elif site == "GOSH":
        pre = "Non-Invasive" if kind == "NIBP" else "Invasive"
        parts = []
        for k, nm in (("s", "systolic"), ("m", "mean"), ("d", "diastolic")):
            p = base / f"{_V}{pre}_{nm}_BP_merged.parquet"
            x = pd.read_parquet(p, columns=SM._cols(p, (STAY["GOSH"], "observation_datetime", GV)))
            x.columns = ["stay", "t", k]
            parts.append(x.drop_duplicates(["stay", "t"]).set_index(["stay", "t"]))
        df = pd.concat(parts, axis=1, join="inner").reset_index(drop=True)
    else:
        raise ValueError("RBH or GOSH only")
    for c in ("s", "m", "d"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna()
    print(f"{site} {kind}: {len(df):,} readings with all three; diastolic >= mean {100 * (df['d'] >= df['m']).mean():.1f}%; "
          f"mean >= systolic {100 * (df['m'] >= df['s']).mean():.1f}%; diastolic >= systolic {100 * (df['d'] >= df['s']).mean():.1f}%; "
          f"diastolic == systolic {100 * (df['d'] == df['s']).mean():.1f}%; diastolic == mean {100 * (df['d'] == df['m']).mean():.1f}%")


def ie_pair_check(assembled_dir, ids=("4185", "4186")):
    """SMH I:E ratio: about half the rows are '1' and the rest vary, which looks like the inspiratory and expiratory parts charted as
    separate rows. Per interventionId, over (stay, time): the share of timestamps with one, two or more rows, and for timestamps with
    exactly two numeric rows the share where the smaller value is 1 and where both are equal. Counts only."""
    p = SM._path(Path(assembled_dir) / "SMH", "vent")
    df = pd.read_parquet(p, columns=SM._cols(p, ("encounterId", "interventionId", "utcChartTime", "terseForm")))
    df.columns = ["stay", "id", "t", "v"]
    df["id"] = df["id"].astype("string").str.strip()
    df = df[df["id"].isin(list(ids))].copy()
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    df = df.dropna(subset=["v"])
    for i in ids:
        g = df[df["id"] == i].groupby(["stay", "t"])["v"].agg(n="size", lo="min", hi="max")
        two = g[g["n"] == 2]
        print(f"{i}: {len(g):,} timestamps; one row {100 * (g['n'] == 1).mean():.1f}%; two rows {100 * (g['n'] == 2).mean():.1f}%; "
              f"three or more {100 * (g['n'] > 2).mean():.1f}%; among two-row timestamps: smaller value is 1 in {100 * (two['lo'] == 1).mean():.1f}%, "
              f"both equal in {100 * (two['lo'] == two['hi']).mean():.1f}%")


def _bg_wide(assembled_dir, site):
    """One row per blood gas sample (stay, time) with pH, bicarbonate, haemoglobin (g/dL) and recorded base excess.
    Haemoglobin in g/L (median above 30) is divided by 10. Used by be_derive_check."""
    base = Path(assembled_dir) / site
    if site == "RBH":
        p = base / "ai_picu_bg.parquet"
        df = pd.read_parquet(p, columns=SM._cols(p, ("stay_key", "SampleCollectDateTime", "pH", "HCO3", "Hb", "BE")))
        df.columns = ["stay", "t", "ph", "hco3", "hb", "be"]
    elif site == "GOSH":
        p = base / f"{_BG}.parquet"
        raw = pd.read_parquet(p, columns=SM._cols(p, (STAY["GOSH"], "observation_datetime", GV, _BGL)))
        raw.columns = ["stay", "t", "v", "lab"]
        names = {"pH": "ph", "HCO3 mmol/L": "hco3", "Hb g/L": "hb", "Base Excess mmol/L": "be"}
        raw = raw[raw["lab"].isin(names)]
        df = raw.pivot_table(index=["stay", "t"], columns="lab", values="v", aggfunc="first").reset_index().rename(columns=names)
    elif site == "SMH":
        p = SM._path(base, "bg")
        raw = pd.read_parquet(p, columns=SM._cols(p, ("encounterId", "interventionId", "utcChartTime", "terseForm")))
        raw.columns = ["stay", "id", "t", "v"]
        raw["id"] = raw["id"].astype("string").str.strip()
        want = {"ph": SM.BG["pH"], "hco3": SM.BG["HCO3"], "be": SM.BG["baseExcess"],
                "hb": SM.BG["totalHb_bg(g/dL)"] + SM.BG["totalHb_bg(g/L)"]}
        inv = {i: k for k, ids in want.items() for i in ids}
        raw["var"] = raw["id"].map(inv)
        raw["v"] = pd.to_numeric(raw["v"], errors="coerce")
        raw = raw.dropna(subset=["var", "v"])
        df = raw.pivot_table(index=["stay", "t"], columns="var", values="v", aggfunc="first").reset_index()
    else:
        raise ValueError("RBH, SMH or GOSH")
    for c in ("ph", "hco3", "hb", "be"):
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df else float("nan")
    if df["hb"].median() > 30:
        df["hb"] = df["hb"] / 10
    return df


def derive_base_excess(ph, hco3, hb=None):
    """Base excess (mmol/L) from pH, bicarbonate (mmol/L) and haemoglobin (g/dL), Siggaard-Andersen:
    (1 - 0.014 Hb) * ((HCO3 - 24.8) + (1.43 Hb + 7.7) * (pH - 7.4)).
    Without haemoglobin (hb is None or missing) the Van Slyke form 0.93 * (HCO3 - 24.4 + 14.8 * (pH - 7.4)) is used."""
    with_hb = (1 - 0.014 * hb) * ((hco3 - 24.8) + (1.43 * hb + 7.7) * (ph - 7.4)) if hb is not None else None
    van_slyke = 0.93 * (hco3 - 24.4 + 14.8 * (ph - 7.4))
    return van_slyke if with_hb is None else with_hb.fillna(van_slyke)


def be_derive_check(assembled_dir, site):
    """Can base excess be derived from pH, bicarbonate and haemoglobin? Per site, over blood gas samples with pH, bicarbonate and a
    recorded base excess (plausible ranges only: pH 6.5 to 7.8, bicarbonate 1 to 60, haemoglobin 2 to 25 g/dL):
      RBH, SMH (recorded base excess keeps its sign): derived minus recorded (median, 5th and 95th percentile) and the share within
        1 and 2 mmol/L, for the formula with haemoglobin (where recorded) and for the Van Slyke form without it.
      GOSH (sign lost): recorded minus |derived| (is the recorded value the magnitude of the derived one?), the share within 2 mmol/L,
        and how often derived is negative.
    Counts, medians and shares only."""
    df = _bg_wide(assembled_dir, site)
    df = df[df["ph"].between(6.5, 7.8) & df["hco3"].between(1, 60) & df["be"].notna()].copy()
    df["hb"] = df["hb"].where(df["hb"].between(2, 25))
    df["d_hb"] = derive_base_excess(df["ph"], df["hco3"], df["hb"])
    df["d_vs"] = derive_base_excess(df["ph"], df["hco3"])
    print(f"{site}: {len(df):,} samples with pH, bicarbonate and a recorded base excess; {100 * df['hb'].notna().mean():.1f}% also with haemoglobin")
    for name, col in (("with haemoglobin (Van Slyke where it is missing)", "d_hb"), ("Van Slyke only", "d_vs")):
        if site == "GOSH":
            diff = df["be"] - df[col].abs()
            print(f"  {name}: recorded minus |derived|: median {diff.median():.2f}, p5 {diff.quantile(.05):.2f}, p95 {diff.quantile(.95):.2f}; "
                  f"within 1: {100 * (diff.abs() <= 1).mean():.1f}%, within 2: {100 * (diff.abs() <= 2).mean():.1f}%; "
                  f"derived negative in {100 * (df[col] < 0).mean():.1f}% of samples")
        else:
            diff = df[col] - df["be"]
            big = df["be"].abs() >= 2
            same_sign = (np.sign(df[col]) == np.sign(df["be"]))[big].mean()
            print(f"  {name}: derived minus recorded: median {diff.median():.2f}, p5 {diff.quantile(.05):.2f}, p95 {diff.quantile(.95):.2f}; "
                  f"within 1: {100 * (diff.abs() <= 1).mean():.1f}%, within 2: {100 * (diff.abs() <= 2).mean():.1f}%; "
                  f"same sign when |recorded| >= 2: {100 * same_sign:.1f}%")


RBH_INTAKE_PARTS = ["IV_Infusion", "IV_Meds", "Colloids", "Blood_In", "Enteral_PO", "PO_NG_Intake", "TPN"]
RBH_BOLUS = ["bolus_CSL", "bolus_NACL", "bolus_ISOPLEX", "bolus_PLASMALYTE", "bolus_ALBUMIN5", "bolus_ALBUMIN20"]


def rbh_io_reconcile(assembled_dir, total="Total_In_ex_dialysis", parts=RBH_INTAKE_PARTS, bolus=RBH_BOLUS, tol=1.0, top=8, sample=300_000):
    """Which RBH io columns add up to the total intake? Treats the bolus columns as one component ('bolus_all'). For stay-hours with a
    positive total, the share of hours where the total equals the sum of each subset of components (missing = 0, tolerance `tol` ml),
    best subsets first, plus how often each component is non-zero and the share of hours where the total exceeds the full sum.
    Counts and shares only."""
    from itertools import combinations
    p = Path(assembled_dir) / "RBH" / "ai_picu_io.parquet"
    cols = [total] + list(parts) + list(bolus)
    df = pd.read_parquet(p, columns=SM._cols(p, cols))
    df.columns = cols
    df = df.apply(pd.to_numeric, errors="coerce")
    df = df[df[total] > 0]
    if len(df) > sample:
        df = df.sample(sample, random_state=0)
    comp = df[list(parts)].fillna(0).copy()
    comp["bolus_all"] = df[list(bolus)].fillna(0).sum(axis=1)
    names = list(comp.columns)
    t = df[total].to_numpy()
    print(f"{len(df):,} stay-hours with a positive {total} (sample of at most {sample:,})")
    print("share of hours with a non-zero value, by component:",
          {n: round(100 * float((comp[n] != 0).mean()), 1) for n in names})
    print(f"total above the sum of all components in {100 * float((t > comp.sum(axis=1).to_numpy() + tol).mean()):.1f}% of hours; "
          f"below it in {100 * float((t < comp.sum(axis=1).to_numpy() - tol).mean()):.1f}%")
    res = []
    for r in range(1, len(names) + 1):
        for sub in combinations(names, r):
            s = comp[list(sub)].sum(axis=1).to_numpy()
            res.append((float((np.abs(t - s) <= tol).mean()), sub))
    res.sort(key=lambda x: (-x[0], len(x[1])))
    for share, sub in res[:top]:
        print(f"  {100 * share:5.1f}%  {' + '.join(sub)}")


def rbh_io_by_year(assembled_dir, subset=("IV_Infusion", "IV_Meds", "Colloids", "Blood_In", "Enteral_PO"), total="Total_In_ex_dialysis",
                   others=("PO_NG_Intake", "TPN"), tol=1.0, sample=400_000):
    """Does the RBH intake total change meaning over time? For stay-hours with a positive total, by year of the row time: the number of
    hours, the share where the total equals the sum of `subset` (1 ml tolerance, missing = 0), the share where the total is above and
    below that sum, and the share of hours with a non-zero value in each column of `subset` and `others`. Counts and shares only."""
    p = Path(assembled_dir) / "RBH" / "ai_picu_io.parquet"
    cols = ["chartTime", total] + list(subset) + list(others)
    df = pd.read_parquet(p, columns=SM._cols(p, cols))
    df.columns = cols
    for c in cols[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[df[total] > 0]
    if len(df) > sample:
        df = df.sample(sample, random_state=0)
    df["year"] = _to_dt(df["chartTime"]).dt.year
    s = df[list(subset)].fillna(0).sum(axis=1)
    df["equal"] = (df[total] - s).abs() <= tol
    df["above"] = df[total] > s + tol
    df["below"] = df[total] < s - tol
    g = df.groupby("year")
    out = pd.DataFrame({"hours": g.size(), "pct_equal": 100 * g["equal"].mean(), "pct_total_above": 100 * g["above"].mean(),
                        "pct_total_below": 100 * g["below"].mean()})
    for c in list(subset) + list(others):
        out[f"nz_{c}"] = 100 * g[c].apply(lambda x: (x.fillna(0) != 0).mean())
    return out.round(1)