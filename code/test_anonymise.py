"""Tests for anonymise.py on synthetic data (no real data, no real IDs). Run: python test_anonymise.py   (or pytest test_anonymise.py)
Builds a small fake harmonised folder and static table in a temporary directory, runs both levels, and checks that each rule does what
the documentation says, and that each check stops the run when it should."""
import tempfile
from pathlib import Path

import numpy as np
from dataclasses import replace
import pandas as pd

import anonymise as A

SITES = ("GOSH", "RBH", "SMH")
RNG = np.random.default_rng(0)


def make_static(n=1500):
    frames = []
    for si, site in enumerate(SITES):
        d = pd.DataFrame({
            "site": site,
            "stay_key": [f"{site[0]}X{100000 + i * 7 + si}" for i in range(n)],
            "patient_id": [f"PT{site[0]}{200000 + i // 2}" for i in range(n)],
            "t0": pd.Timestamp("2016-01-01") + pd.to_timedelta(RNG.integers(0, 24 * 365 * 5, n), unit="h"),
            "year": RNG.integers(2014, 2021, n),
            "age_months": RNG.choice([0.5, 2, 6, 18, 40, 90, 150, 200], n),
            "sex": RNG.choice(["Male", "Female"], n),
            "ethnicity": RNG.choice(["White - British", "Asian - Indian", "Black - African", "Not stated"], n),
            "ethnicity_source": "picanet", "weight_kg": RNG.choice([3.0, 8.0, 15.0, 30.0, 60.0], n), "weight_source": "picanet",
            "los_hours": RNG.uniform(7, 400, n), "los_source": "picanet", "died": RNG.random(n) < 0.05,
            "diagnosis_group": RNG.choice(["Cardiac", "Respiratory", "Neuro"], n), "pim": RNG.random(n), "pim_version": "PIM3"})
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def make_harmonised(root, static, bad=None):
    """Fake harmonised files. `bad` injects a problem: 'id' (an original stay key inside value_raw), 'date' (a date in value_raw)."""
    root.mkdir(parents=True, exist_ok=True)
    for site in SITES:
        s = static[static["site"] == site]
        keys = s["stay_key"].to_numpy()[:400]
        rows = []
        for k in keys:
            for h in range(0, 6):
                rows.append({"site": site, "stay_key": k, "concept": "hr", "hour": float(h), "value": 100.0 + h, "value_text": None, "value_raw": None, "flag": "", "source": "0", "src_row": len(rows)})
            rows.append({"site": site, "stay_key": k, "concept": "vent_mode", "hour": 1.0, "value": np.nan, "value_text": "SIMV" if hash(k) % 2 else "CPAP", "value_raw": None, "flag": "", "source": "0", "src_row": len(rows)})
        v = pd.DataFrame(rows)
        # a text string seen in only 3 stays, and a note-like string
        v.loc[v.index[v["concept"] == "vent_mode"][:3], "value_text"] = "RareModeX"
        v.loc[v.index[v["concept"] == "vent_mode"][3], "value_text"] = "patient moved to side room after long family discussion"
        if site == "GOSH":
            extra = v[v["concept"] == "hr"].head(50).assign(concept="pulse_rate")
            v = pd.concat([v, extra], ignore_index=True)
            f = v[v["concept"] == "hr"].head(40).assign(concept="intake_total", source="1")
            v = pd.concat([v, v[v["concept"] == "hr"].head(40).assign(concept="intake_total", source="0"), f], ignore_index=True)
            cab = v[v["concept"] == "hr"].head(10).assign(concept="intake_total", source="gosh_caboodle")
            v = pd.concat([v, cab], ignore_index=True)
        if site == "SMH":
            v = pd.concat([v, v[v["concept"] == "hr"].head(30).assign(concept="ps_peep")], ignore_index=True)
        v["value_raw"] = v["value_raw"].astype("object")
        v.loc[v.index[:5], "value_raw"] = "9 ml"
        if bad == "id" and site == "RBH":
            v.loc[v.index[5], "value_raw"] = f"see {keys[0]}"
        if bad == "date" and site == "RBH":
            v.loc[v.index[5], "flag"] = "2017-03-12"           # the note scan only covers value_raw and value_text, so this reaches the check
        if bad is None and site == "RBH":
            v.loc[v.index[5], "value_raw"] = "12/03/2017"      # a date in value_raw is nulled by the scan, so the run still passes
        v["patient_name"] = "ZZ"                                     # an unexpected column: must be dropped and reported
        v.to_parquet(root / f"{site}_vitals.parquet", index=False)
        v.head(10).to_parquet(root / f"{site}_rejected.parquet", index=False)
        d = pd.DataFrame({"site": site, "stay_key": np.repeat(keys[:100], 3), "concept": "drug_a", "hour": 1.0, "value": 5.0,
                          "unit": np.tile(["mg", None, ""], 100)[:300], "kind": "amount", "route": None, "value_raw": None, "source": "1" if site == "GOSH" else "0", "src_row": 1})
        d.to_parquet(root / f"{site}_drugs.parquet", index=False)


T2 = A.preset("tier2", max_small_share=None)      # synthetic cells are small by construction; the threshold is tested separately


def run_level(cfg, bad=None, **kw):
    tmp = Path(tempfile.mkdtemp())
    static = make_static()
    make_harmonised(tmp / "h", static, bad)
    steps, checks = A.run(tmp / "h", static, tmp / "out", cfg, **kw)
    return tmp, static, steps, checks


def test_note_like():
    s = pd.Series(["9 ml", "120/80", "a:b 1:2", "this is a typed note about the child", "12/03/2017", "2017-03-12", "x" * 41, "call 07123456789", "a@b.org", None])
    got = A.note_like(s).tolist()
    assert got == [False, False, False, True, True, True, True, True, True, False], got


def test_free_text_warns_at_tier1_and_fails_at_tier2():
    df = pd.DataFrame({"stay_key": ["S1"] * 300, "concept": "vent_mode", "hour": 1.0, "value": 1.0,
                       "value_text": [f"mode variant {i} of ventilation" for i in range(300)]})
    r1 = {c["check"]: c for c in A.check_frame(df, "t", A.TIER1, set(), A.allowed_series(A.TIER1))}
    r2 = {c["check"]: c for c in A.check_frame(df, "t", A.TIER2, set(), A.allowed_series(A.TIER2))}
    assert r1["free text"]["status"] == "WARN" and r2["free text"]["status"] == "FAIL"


def test_text_vocabulary():
    tmp = Path(tempfile.mkdtemp())
    static = make_static()
    make_harmonised(tmp / "h", static)
    v = A.text_vocabulary(tmp / "h")
    r = v[(v["site"] == "RBH") & (v["concept"] == "vent_mode")].iloc[0]
    assert r["distinct_rare"] >= 1 and r["rows_rare"] >= 3 and 0 < r["share_rows_rare"] < 1


def test_short_ids_not_tested():
    assert A.testable_ids({"1", "1234", "12345", "ABC123"}) == {"12345", "ABC123"}
    tmp, static, steps, checks = run_level(T2)
    assert "too short" in " ".join(steps["item"].astype(str))


def test_unitless_rule_scope():
    tmp, static, steps, checks = run_level(T2)
    d = pd.read_parquet(tmp / "out" / "tier2" / "drugs.parquet")
    assert steps[steps["item"] == "drop_drug_rule"]["n"].sum() == 200
    assert len(d) <= 900 - 200 and len(d) > 600                      # the 200 GOSH rows with a number and no unit are gone; other rows stay
    df = pd.DataFrame({"stay_key": ["a", "a", "a"], "concept": "drug_a", "hour": 1.0, "value": [5.0, np.nan, 5.0], "unit": [None, None, "mg"],
                       "kind": "x", "route": None, "value_raw": None, "source": "0", "src_row": 1})
    out, lg = A.transform_series(df, "GOSH", "drugs", {"a": "S1"}, T2, set())
    assert lg["drop_drug_rule"] == 1 and len(out) == 2
    out, lg = A.transform_series(df, "RBH", "drugs", {"a": "S1"}, T2, set())
    assert lg["drop_drug_rule"] == 0 and len(out) == 3


def test_zero_match_stops():
    tmp = Path(tempfile.mkdtemp())
    static = make_static()
    make_harmonised(tmp / "h", static)
    d = pd.read_parquet(tmp / "h" / "GOSH_drugs.parquet").assign(unit="mg")
    d.to_parquet(tmp / "h" / "GOSH_drugs.parquet", index=False)
    try:
        A.run(tmp / "h", static, tmp / "out", T2)
    except A.CheckFailed as e:
        assert "drug rule" in set(e.checks.loc[e.checks["status"] == "FAIL", "check"])
        return
    raise AssertionError("a rule that matched nothing did not stop the run")


def test_short_ids_in_key_columns():
    df = pd.DataFrame({"stay_key": ["S1"], "concept": ["hr"], "hour": [1.0], "value": [1.0], "flag": ["12"], "source": ["12"]})
    ok = {c["check"]: c for c in A.check_frame(df, "t", A.TIER1, set(), A.allowed_series(A.TIER1), short_ids=frozenset({"7"}))}
    assert ok["ids"]["status"] == "pass"                       # short ID absent; 'source' is never tested for short IDs
    r = {c["check"]: c for c in A.check_frame(df, "t", A.TIER1, set(), A.allowed_series(A.TIER1), short_ids=frozenset({"12"}))}
    assert r["ids"]["status"] == "FAIL" and "flag" in r["ids"]["note"] or r["ids"]["n"] == 1
    s = df.assign(source="7", flag="")
    assert {c["check"]: c for c in A.check_frame(s, "t", A.TIER1, set(), A.allowed_series(A.TIER1), short_ids=frozenset({"7"}))}["ids"]["status"] == "pass"


def test_note_scan_exempts_vocabulary():
    words = "oral tracheal tube cuffed with side port"             # six words, but typed the same way in many stays
    df = pd.DataFrame({"stay_key": [f"S{i}" for i in range(12)] + ["S99"], "concept": "airway_device", "hour": 1.0, "value": np.nan,
                       "value_text": [words] * 12 + ["patient moved to side room after long family discussion"], "value_raw": None, "flag": "",
                       "source": "0", "src_row": 1, "site": "GOSH"})
    keymap = {k: k for k in df["stay_key"]}
    for cfg in (A.TIER1, T2):
        out, lg = A.transform_series(df, "GOSH", "series", keymap, cfg, set())
        assert (out["value_text"] == words).sum() == 12                 # vocabulary kept
        assert not out["value_text"].dropna().str.contains("family").any()   # the one-off note is gone (blanked at Tier 1, "rare" at Tier 2)
    assert A.note_like(pd.Series([words, "call 07123456789"]), common={words, "call 07123456789"}).tolist() == [False, True]   # hard rules always apply


def test_diagnose_text_runs():
    tmp = Path(tempfile.mkdtemp())
    static = make_static()
    make_harmonised(tmp / "h", static)
    cols, concepts = A.diagnose_text(tmp / "h", static, A.TIER1, "RBH", "vitals")
    assert {"column", "distinct", "note_like"} <= set(cols.columns) and "stay_key" in set(cols["column"])


def test_level_report():
    try:
        import sklearn  # noqa: F401
        import level_report as LR
    except ImportError:
        return
    tmp, static, steps, checks = run_level(T2)
    cs = LR.cell_summary(tmp / "out", "tier2")
    assert list(cs["k"]) == [5, 10, 20] and cs.attrs["stays"] == len(A.cohort_static(static))
    res = LR.site_report(tmp / "out", "tier2", static)
    tab = LR.summary(res)
    assert len(tab) == 4 and {"accuracy", "baseline", "gain_pts", "balanced_acc", "recall_GOSH"} <= set(tab.columns)
    assert (tab["accuracy"] < 0.6).all()          # the synthetic sites are identical in structure, so the site cannot be guessed well
    r1 = LR.cached_site_report(tmp / "out", "tier2", static)
    assert (tmp / "out" / "_private" / "site_report_tier2_drugs1_seed0.pkl").exists()
    r2 = LR.cached_site_report(tmp / "out", "tier2", static)     # second call loads the cache
    assert LR.summary(r1).equals(LR.summary(r2))
    d1 = LR.drugs_only_report(tmp / "out", "tier2", static)
    d2 = LR.drugs_only_report(tmp / "out", "tier2", static)
    assert LR.summary(d1).equals(LR.summary(d2)) and LR.summary(d1)["variant"].iloc[0] == "drugs only"
    t, _ = LR.compare_levels(tmp / "out", ["tier2"], static)
    assert list(t["level"].unique()) == ["tier2"]


def test_concept_investigation():
    try:
        import sklearn, scipy  # noqa: F401
        import level_report as LR
    except ImportError:
        return
    import tempfile
    rng = np.random.default_rng(0)
    root = Path(tempfile.mkdtemp())
    d = root / "lv"; d.mkdir(); (root / "_private").mkdir()
    sites = ["A"] * 60 + ["B"] * 60 + ["C"] * 60
    keys = [f"S{i:08d}" for i in range(180)]
    pd.DataFrame({"site": sites, "stay_key": [str(i) for i in range(180)], "new_stay_key": keys}).to_parquet(root / "_private" / "lv_key_map.parquet")
    rows = []
    for i, (s, k) in enumerate(zip(sites, keys)):
        rows.append((k, "hr", 0, rng.normal(100, 10) * (1.0), None))              # same everywhere
        rows.append((k, "temp", 0, rng.normal(37, 0.5) * (1.8 if s == "B" else 1.0), None))   # B scaled
        if s == "C":
            rows.append((k, "only_c", 0, 1.0, None))                              # one-site concept
        if s != "A":
            rows.append((k, "two_site", 0, 5.0, None))
    pd.DataFrame(rows, columns=["stay_key", "concept", "hour", "value", "value_text"]).to_parquet(d / "vitals.parquet")
    cov = LR.concept_coverage_released(root, "lv").set_index("concept")
    assert cov.loc["only_c", "n_sites"] == 1 and cov.loc["two_site", "n_sites"] == 2 and cov.loc["hr", "n_sites"] == 3
    one = LR.single_concept_accuracy(root, "lv").set_index("concept")
    assert one.loc["only_c", "accuracy"] > one.loc["hr", "accuracy"] and one.loc["hr", "gain_pts"] <= 0.01
    sh = LR.concept_shift(root, "lv").set_index("concept")
    assert sh.loc["temp", "shift"] > 3 and sh.loc["temp", "scale_hint"] == "x1.8 (C/F)" and sh.loc["hr", "shift"] < 1
    assert sh.index[0] == "temp"


def test_fluid_definition_check():
    import tempfile, harmonise as H
    rng = np.random.default_rng(1)
    root = Path(tempfile.mkdtemp())
    static = pd.DataFrame({"site": ["A", "B"], "stay_key": ["1", "2"], "weight_kg": [10.0, 10.0]})
    rows = []
    for site, key, running in (("A", "1", False), ("B", "2", True)):
        inn = rng.integers(0, 40, 72).astype(float)
        out = rng.integers(0, 20, 72).astype(float)
        val = np.cumsum(inn) if running else inn
        for h in range(72):
            rows.append((site, key, "intake_total", h, val[h], "src"))
            rows.append((site, key, "output_total", h, out[h], "src"))
            rows.append((site, key, "net_balance", h, inn[h] - out[h], "src"))
    df = pd.DataFrame(rows, columns=["site", "stay_key", "concept", "hour", "value", "source"])
    for s_ in ("A", "B"):
        df[df["site"] == s_].to_parquet(root / f"{s_}_fluids.parquet")
    prof, ident = H.fluid_definition_check(root, static, sites=("A", "B"))
    p = prof[prof["concept"] == "intake_total"].set_index("site")
    assert p.loc["B", "pct_nondecreasing"] > 95 and p.loc["A", "pct_nondecreasing"] < 75
    assert p.loc["B", "median_day_per_kg"] > 5 * p.loc["A", "median_day_per_kg"]
    assert (ident.set_index("site").loc["A", "net_equals_in_minus_out"] == 100.0)
    assert ident.set_index("site").loc["B", "net_equals_in_minus_out"] < 50


def test_caboodle_and_source_labels():
    tmp, static, steps, checks = run_level(T2)
    row = steps[(steps["item"] == "drop_caboodle") & steps["step"].str.contains("GOSH_vitals")]
    assert len(row) == 1 and int(row["n"].iloc[0]) == 10
    d = pd.read_parquet(tmp / "out" / "tier2" / "vitals.parquet")
    assert not d["source"].dropna().astype(str).str.contains("gosh|rbh|smh", case=False).any()
    assert (checks[checks["check"] == "source labels"]["status"] == "pass").all() and (checks["check"] == "source labels").any()
    # without the rule, the source name reaches a pooled file and the check stops the run
    try:
        run_level(A.preset("tier2", name="tier2_keep_cab", drop_gosh_caboodle=False, seed=9, max_small_share=None))
    except A.CheckFailed as e:
        assert "source labels" in str(e)
    else:
        raise AssertionError("site name in source was released")
    # explicit alternative: no source column at all
    tmp, static, steps, checks = run_level(A.preset("tier2", name="tier2_nosrc", drop_gosh_caboodle=False, source_mode="none", seed=10, max_small_share=None))
    assert (checks["status"] == "pass").all()


def test_gosh_era_comparison():
    try:
        import scipy  # noqa: F401
    except ImportError:
        return
    import tempfile, harmonise as H
    rng = np.random.default_rng(2)
    root = Path(tempfile.mkdtemp())
    n = 200
    t0 = list(pd.date_range("2018-01-01", periods=n // 2, freq="D")) + list(pd.date_range("2019-06-01", periods=n // 2, freq="D"))
    static = pd.DataFrame({"site": "GOSH", "stay_key": [str(i) for i in range(n)], "t0": t0, "los_hours": 100.0})
    rows = []
    for i in range(n):
        post = i >= n // 2
        rows.append((str(i), "stable", 0.0, rng.normal(50, 5)))
        if not post:
            rows.append((str(i), "gone", 0.0, rng.normal(10, 1)))
        else:
            rows.append((str(i), "new", 0.0, rng.normal(10, 1)))
        rows.append((str(i), "shifted", 0.0, rng.normal(20 if not post else 40, 2)))
        if i % 2 == 0 or not post:
            rows.append((str(i), "thin", 0.0, rng.normal(5, 1)))
    pd.DataFrame(rows, columns=["stay_key", "concept", "hour", "value"]).to_parquet(root / "GOSH_vitals.parquet")
    out = H.gosh_era_comparison(root, static).set_index("concept")
    assert out.loc["gone", "flag"] == "absent after" and out.loc["new", "flag"] == "new after"
    assert out.loc["thin", "flag"] == "thin after" or out.loc["thin", "flag"] == ""        # 50% of post stays: borderline, not asserted
    assert out.loc["shifted", "flag"] == "values differ" and out.loc["stable", "flag"] == ""
    assert out.loc["stable", "n_pre"] == 100 and out.loc["stable", "n_post"] == 100


def test_gosh_epic_cutoff():
    tmp, static, steps, checks = run_level(A.preset("tier2", name="t2_pre", gosh_epic_cutoff="2018-07-01", max_small_share=None, seed=12))
    assert (checks["status"] == "pass").all()
    left = steps[(steps["step"] == "cohort") & steps["item"].str.contains("GOSH stays left out")]["n"].iloc[0]
    g = static[static["site"] == "GOSH"]
    assert left == int((g["t0"] >= pd.Timestamp("2018-07-01")).sum()) and left > 0
    st = pd.read_parquet(tmp / "out" / "t2_pre" / "static.parquet")
    assert len(st) == len(A.cohort_static(static)) - left
    try:
        A.preset("tier2", gosh_epic_cutoff="not a date")
    except ValueError:
        return
    raise AssertionError("bad cutoff accepted")


def test_patient_report():
    try:
        import patient_report as PR
    except ImportError:
        return
    import tempfile
    # end to end on a synthetic Tier 2 level: the series are identical across stays, so measurements cannot single a stay out
    tmp, static, steps, checks = run_level(T2)
    div = PR.outcome_diversity(tmp / "out", "tier2")
    assert {"item", "n", "share_or_rate"} <= set(div.columns) and div["share_or_rate"].dropna().between(0, 1).all()
    att = PR.known_observation_attack(tmp / "out", "tier2", ms=(1, 3, 5), n_targets=80)
    s1 = att[(att["known"] == "series only") & (att["m"] == 1)].iloc[0]
    assert s1["unique"] == 0 and s1["median_candidates"] > 100
    s0 = att[att["m"] == 0].iloc[0]
    assert s0["known"] == "static fields only" and s0["median_candidates"] >= 1
    link = PR.repeat_stay_linkage(tmp / "out", "tier2", static)
    assert len(link) == 2 and link["chance"].between(0, 1).all() and link["hit"].between(0, 1).all()
    # distinct values: every stay is found from three measurements
    rng = np.random.default_rng(3)
    root = Path(tempfile.mkdtemp()); d = root / "lv"; d.mkdir()
    n = 200
    pd.DataFrame({"stay_key": [f"S{i:04d}" for i in range(n)], "age_band": "1y", "sex": "Male", "weight_band": "w", "died": False,
                  "diagnosis_group": "x"}).to_parquet(d / "static.parquet")
    rows = [(f"S{i:04d}", c, float(h), float(rng.normal(100, 20))) for i in range(n) for c in ("hr", "bp") for h in range(10)]
    pd.DataFrame(rows, columns=["stay_key", "concept", "hour", "value"]).to_parquet(d / "vitals.parquet")
    a = PR.known_observation_attack(root, "lv", ms=(1, 3), n_targets=100)
    r3 = a[(a["known"] == "series only") & (a["m"] == 3)].iloc[0]
    assert r3["unique"] > 0.95 and r3["below_k"] > 0.95
    a2 = PR.known_observation_attack(root, "lv", ms=(1,), n_targets=100, rel_tol=0.5)
    assert a2[(a2["known"] == "series only") & (a2["m"] == 1)].iloc[0]["median_candidates"] > a[(a["known"] == "series only") & (a["m"] == 1)].iloc[0]["median_candidates"]


def test_value_report():
    try:
        import sklearn  # noqa: F401
        import level_report as LR
        import reid
    except ImportError:
        return
    # numeric columns are used as numbers: a value shifted by site is found, as categories it would be hopeless
    rng = np.random.default_rng(4)
    site = np.repeat(["A", "B"], 300)
    X = pd.DataFrame({"v": np.r_[rng.normal(0, 1, 300), rng.normal(3, 1, 300)], "c": "x"})
    as_num = reid.site_inference(X, site, drop_one=False, numeric=["v"])["accuracy"]
    as_cat = reid.site_inference(X, site, drop_one=False)["accuracy"]
    assert as_num > 0.9 and as_cat < as_num
    tmp, static, steps, checks = run_level(T2)
    res = LR.value_report(tmp / "out", "tier2", static)
    assert set(res) == {"concepts + median values", "concepts + values + recording pattern", "everything (static, drugs, values, pattern)"}
    t = LR.summary(res)
    assert t["accuracy"].between(0, 1).all() and (t["features"] > 0).all()
    again = LR.value_report(tmp / "out", "tier2", static)
    assert LR.summary(again).equals(t)
    top = next(c for c in LR.concept_importance(tmp / "out", "tier2", static, repeats=1).index[:1])
    ab = LR.value_report(tmp / "out", "tier2", static, drop=[top])
    assert set(ab) == set(res) and all(ab[k]["features"] < res[k]["features"] for k in res)
    import matplotlib
    matplotlib.use("Agg")
    import harmonise as H
    by = H.concept_by_age(tmp / "h", static, "hr")
    figs = LR.site_figures(tmp / "out", "tier2", static, {"drop one": [top]}, by, tmp / "figs")
    assert all(p.exists() and p.stat().st_size > 5000 for p in figs.values()) and len(figs) == 4
    imp = LR.concept_importance(tmp / "out", "tier2", static, repeats=1)
    assert list(imp.columns) == ["all", "values", "pattern"] and len(imp) > 0
    assert imp["all"].is_monotonic_decreasing


def test_drop_static_fields():
    for cfg in (A.preset("tier2_no_ethnicity", max_small_share=None), A.preset("tier1", name="tier1_no_eth", seed=7, drop_static=("ethnicity", "weight"))):
        tmp, static, steps, checks = run_level(cfg)
        assert (checks["status"] == "pass").all()
        st = pd.read_parquet(tmp / "out" / cfg.name / "static.parquet")
        assert not {c for c in st.columns if c.startswith(("ethnicity", "weight"))} & A.dropped_static_columns(cfg)
        assert "ethnicity" not in st.columns and "ethnicity_source" not in st.columns
        assert "age_band" in st.columns or "age_months" in st.columns
    try:
        A.preset("tier2", drop_static=("sex",))
    except ValueError:
        return
    raise AssertionError("an unsupported field was accepted")


def test_config_validation():
    for bad in (dict(static_mode="coarse"), dict(patient_key="split_group"), dict(source_mode="x"), dict(time_resolution_hours=0)):
        try:
            A.Config(**bad).validate()
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")
    A.TIER1.validate(); A.TIER2.validate()
    assert A.preset("tier2", k=20).k == 20
    c = A.preset("tier2", name="tier2_k20", k=20, seed=5)
    assert c.name == "tier2_k20" and c.k == 20 and c.seed == 5


def test_tier1():
    tmp, static, steps, checks = run_level(A.TIER1)
    assert (checks["status"] == "pass").all(), checks[checks["status"] != "pass"]
    out = tmp / "out" / "tier1"
    assert (out / "static.parquet").exists() and (tmp / "out" / "_private" / "tier1_key_map.parquet").exists()
    assert not list(out.glob("*key_map*")) and not list(out.glob("*rejected*"))
    st = pd.read_parquet(out / "static.parquet")
    assert set(st.columns) == set(A.allowed_static(A.TIER1)) and "patient_id" not in st.columns and "t0" not in st.columns
    n = len(A.cohort_static(static))
    assert len(st) == n and st["stay_key"].is_unique
    assert set(st["site"]) == set(A.SITES)
    old = set(static["stay_key"]) | set(static["patient_id"])
    assert not (set(st["stay_key"]) | set(st["patient_key"])) & old
    # a patient with two stays keeps one patient key, and the same raw patient_id at two sites would not link (ids differ here by design)
    assert st.groupby("patient_key")["stay_key"].nunique().max() == 2
    g = pd.read_parquet(out / "GOSH_vitals.parquet")
    assert "patient_name" not in g.columns and "pulse_rate" in set(g["concept"]) and "ps_peep" not in set(g["concept"])
    s = pd.read_parquet(out / "SMH_vitals.parquet")
    assert "ps_target_pressure" in set(s["concept"]) and "ps_peep" not in set(s["concept"])
    assert "RareModeX" in set(g["value_text"].dropna())                 # Tier 1 keeps rare strings (inside the SDE)
    assert not g["value_text"].dropna().str.contains("family discussion").any()     # but not note-like text
    assert "patient_name" in " ".join(steps["item"].astype(str))        # the dropped column is reported by name
    d = pd.read_parquet(out / "GOSH_drugs.parquet")
    assert len(d) == 300                                                # Tier 1 keeps the unitless GOSH rows


def test_tier2():
    tmp, static, steps, checks = run_level(T2)
    assert (checks["status"] == "pass").all(), checks[checks["status"] != "pass"]
    out = tmp / "out" / "tier2"
    files = sorted(p.name for p in out.glob("*.parquet"))
    assert files == ["drugs.parquet", "static.parquet", "vitals.parquet"], files
    st = pd.read_parquet(out / "static.parquet")
    assert set(st.columns) == set(A.allowed_static(A.TIER2)) and "site" not in st.columns
    assert st["split_group"].between(0, 9).all() and len(st) == len(A.cohort_static(static))
    v = pd.read_parquet(out / "vitals.parquet")
    assert set(v.columns) == set(A.allowed_series(A.TIER2)) and "site" not in v.columns and "src_row" not in v.columns
    assert not set(v["concept"]) & {"pulse_rate", "ps_peep", "ps_target_pressure"}
    assert set(v.loc[v["concept"] == "vent_mode", "value_text"].dropna()) <= {"SIMV", "CPAP", "rare"} and "rare" in set(v["value_text"])
    assert v.loc[v["concept"] != "intake_total", "source"].isna().all() and v.loc[v["concept"] == "intake_total", "source"].notna().all()
    assert v["stay_key"].is_monotonic_increasing
    # the order of the keys carries no site information: walking down the sorted file, the site changes about as often as in a random order
    km = pd.read_parquet(tmp / "out" / "_private" / "tier2_key_map.parquet").set_index("new_stay_key")["site"]
    sites_in_order = km.reindex(v["stay_key"].drop_duplicates()).to_numpy()
    changes = (sites_in_order[1:] != sites_in_order[:-1]).mean()
    assert changes > 0.5, changes                                         # 2/3 for three equal sites in random order; ~0 if blocked by site
    d = pd.read_parquet(out / "drugs.parquet")
    gosh_unitless_dropped = steps[steps["item"] == "drop_drug_rule"]["n"].sum()
    assert gosh_unitless_dropped == 200, gosh_unitless_dropped        # 100 stays x 3 rows; two of each 3 have no unit (None or empty)
    assert "pim" not in st.columns and "pim_band" not in st.columns
    # nothing in the output equals an original identifier
    old = set(static["stay_key"]) | set(static["patient_id"])
    assert not set(v["stay_key"]) & old and not set(st["stay_key"]) & old


def test_levels_differ_only_by_config():
    tmp, static, steps, checks = run_level(A.preset("tier2_pim", max_small_share=None))
    st = pd.read_parquet(tmp / "out" / "tier2_pim" / "static.parquet")
    assert "pim_band" in st.columns and st["pim_band"].between(1, 10).all()
    cfg = A.preset("tier2_hourly", max_small_share=None)
    tmp, static, steps, checks = run_level(cfg)
    v = pd.read_parquet(tmp / "out" / "tier2_hourly" / "vitals.parquet")
    assert np.allclose(v["hour"], np.round(v["hour"]))
    cfg = A.preset("tier2_hourly", name="tier2_hourly_one", one_row_per_hour=True, max_small_share=None, seed=40)
    tmp, static, steps, checks = run_level(cfg)
    v1 = pd.read_parquet(tmp / "out" / "tier2_hourly_one" / "vitals.parquet")
    num = v1[v1["value"].notna()]
    assert not num.duplicated([c for c in ("stay_key", "concept", "hour", "source") if c in num.columns]).any() and len(v1) <= len(v)
    assert (checks[(checks["check"] == "rows")]["status"] == "pass").all()
    back = A.config_from_level(tmp / "out", "tier2_hourly_one", name="y")
    assert back == replace(cfg, name="y")
    _expect_value_error = False
    try:
        A.preset("tier2", one_row_per_hour=True)
    except ValueError as e:
        _expect_value_error = "time_resolution_hours" in str(e)
    assert _expect_value_error


def test_one_row_per_hour_merge():
    cfg = A.preset("tier2_hourly", name="x", one_row_per_hour=True, max_small_share=None)
    df = pd.DataFrame({"stay_key": ["a"] * 5, "concept": ["hr"] * 3 + ["spo2"] * 2, "hour": [0.1, 0.3, 0.4, 2.0, 2.2],
                       "value": [100., 110., 120., 95., 97.], "value_text": [None] * 5, "value_raw": ["100", "110", "120", "95", "97"],
                       "source": [None] * 5, "flag": [0] * 5})
    o, log = A.transform_series(df, "RBH", "vitals", {"a": "S1"}, cfg, set())
    assert log["rows_merged_hourly"] == 3 and sorted(o["value"]) == [96.0, 110.0] and o["value_raw"].isna().all()


def test_unit_consistency():
    import tempfile, harmonise as H
    tmp = Path(tempfile.mkdtemp())
    static = make_static()
    make_harmonised(tmp / "h", static)
    u = H.unit_consistency(tmp / "h", static)
    r = u[u["concept"] == "hr"].iloc[0]
    assert r["adjusted_ratio"] == 1.0 and not r["flag"] and r["bands_used"] >= 2
    f = tmp / "h" / f"{SITES[0]}_vitals.parquet"
    if not f.exists():
        f = next((tmp / "h").glob(f"{SITES[0]}_*.parquet"))
    d = pd.read_parquet(f)
    d.loc[d["concept"] == "hr", "value"] *= 88.4
    d.to_parquet(f, index=False)
    u = H.unit_consistency(tmp / "h", static)
    r = u[u["concept"] == "hr"].iloc[0]
    assert r["flag"] and "88.4" in r["unit_hint"]
    assert H._factor_hint(1.8, "bilirubin") == "" and H._factor_hint(7.5, "bg_po2") != "" and H._factor_hint(7.5, "alt") == ""
    by = H.concept_by_age(tmp / "h", static, "hr")
    assert set(by["site"]) == set(SITES) and (by["stays"] > 0).all()


def test_reproducible_keys():
    static = A.cohort_static(make_static())
    ids = A.source_ids(static)
    a = A.make_keys(static, A.TIER1, ids)
    b = A.make_keys(static, A.TIER1, ids)
    c = A.make_keys(static, A.preset("tier1", seed=99), ids)
    assert a.equals(b) and not a["new_stay_key"].equals(c["new_stay_key"])
    assert a["new_stay_key"].is_unique


def _expect_fail(bad, check):
    try:
        run_level(T2, bad=bad)
    except A.CheckFailed as e:
        assert check in set(e.checks.loc[e.checks["status"] == "FAIL", "check"]), e.checks
        return
    raise AssertionError(f"{bad} did not stop the run")


def test_failures_stop_the_run():
    _expect_fail("id", "ids")
    _expect_fail("date", "dates")
    # nothing was released
    tmp = Path(tempfile.mkdtemp())
    static = make_static()
    make_harmonised(tmp / "h", static, "id")
    try:
        A.run(tmp / "h", static, tmp / "out", T2)
    except A.CheckFailed:
        pass
    assert not (tmp / "out" / "tier2").exists() and not (tmp / "out" / "tier2.staging").exists()


def test_check_functions_directly():
    ids = {"ABC123456"}
    cfg = A.TIER2
    df = pd.DataFrame({"stay_key": ["S1"], "concept": ["hr"], "hour": [1.0], "value": [1.0], "extra": ["x"], "value_raw": ["ref ABC123456 here"]})
    r = {c["check"]: c for c in A.check_frame(df, "t", cfg, ids, A.allowed_series(cfg))}
    assert r["allow-list"]["status"] == "FAIL" and r["ids"]["status"] == "FAIL"
    h = pd.DataFrame({"stay_key": ["S1"], "concept": ["hr"], "hour": [1e9], "value": [1.0]})
    assert {c["check"]: c for c in A.check_frame(h, "t", cfg, ids, A.allowed_series(cfg))}["hour range"]["status"] == "FAIL"
    hexdf = pd.DataFrame({"stay_key": ["a" * 32]})
    assert {c["check"]: c for c in A.check_frame(hexdf, "t", cfg, ids, ["stay_key"])}["ids"]["status"] == "FAIL"
    dt = pd.DataFrame({"stay_key": ["S1"], "t": [pd.Timestamp("2017-01-01")]})
    assert {c["check"]: c for c in A.check_frame(dt, "t", cfg, ids, ["stay_key", "t"])}["dates"]["status"] == "FAIL"
    tx = pd.DataFrame({"site": ["A"] * 3, "concept": ["m"] * 3, "stay_key": ["1", "2", "3"], "value_text": ["x", "x", "rare"]})
    assert A.check_text_counts(tx, "t", 10)[0]["status"] == "FAIL" and A.check_text_counts(tx, "t", 2)[0]["status"] == "pass"
    q = pd.DataFrame({"stay_key": [str(i) for i in range(12)], "age_band": ["a"] * 11 + ["b"], "sex": "Male", "ethnicity": "x", "diagnosis_group": "d", "died": False, "weight_band": "w"})
    assert A.check_small_cells(q, A.preset("tier2", max_small_share=0.01))[0]["status"] == "FAIL"
    assert A.check_small_cells(q, A.preset("tier2", max_small_share=None))[0]["status"] == "pass"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)