"""Tests : reproductibilité, valeurs de référence recalculées à la main, robustesse des filtres.

    python -m pytest -q            (ou)            python tests/test_dashboard.py
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dash._callback_context import context_value  # noqa: E402
from dash._utils import AttributeDict  # noqa: E402

from app import create_app  # noqa: E402
from src.config import ETATS, PERMIS, REGIONS  # noqa: E402
from src.layout import VEHICLE_TYPES  # noqa: E402
from src.loading import locate, read_raw, sha256  # noqa: E402
from src.pipeline import build  # noqa: E402

DATA = build(write=False)
APP = create_app()


def cb(output_prefix: str):
    """Fonction Python d'un callback, retrouvée par le début de sa clé de sortie."""
    for k, v in APP.callback_map.items():
        if k.lstrip(".").startswith(output_prefix):
            return v["callback"].__wrapped__
    raise KeyError(output_prefix)


def with_trigger(prop_id: str, value=None):
    context_value.set(AttributeDict(triggered_inputs=[{"prop_id": prop_id, "value": value}], inputs_list=[],
                                    states_list=[], outputs_list=[], args_grouping=[], using_args_grouping=False,
                                    using_outputs_grouping=False))


# ── Données ──────────────────────────────────────────────────────────────────────────────

def test_sources_unchanged():
    """Le pipeline lit les sources sans les modifier."""
    before = {k: sha256(locate(p)) for k, p in [("a", "observationdata-*.csv")]}
    build(write=False)
    after = {k: sha256(locate(p)) for k, p in [("a", "observationdata-*.csv")]}
    assert before == after


def test_reproducible():
    d2 = build(write=False)
    pd.testing.assert_frame_equal(DATA.pref.drop(columns=["etat_estime"]), d2.pref.drop(columns=["etat_estime"]))
    pd.testing.assert_frame_equal(DATA.safety, d2.safety)
    pd.testing.assert_frame_equal(DATA.recommandations, d2.recommandations)


def test_reference_values():
    s = DATA.safety
    assert s.loc[2022, "deces"] == 683 and s.loc[2022, "accidents"] == 7507
    assert round(s.loc[2022, "taux_deces_100k"], 2) == round(683 / 8_095_498 * 1e5, 2)
    assert abs(s.loc[2022, "pop_implicite"] - 8_095_498) < 1
    imm = DATA.immat.groupby("annee").valeur.sum()
    raw = read_raw("immatriculations")
    tot = raw[raw["types-de-vehicule"] == "Total"].set_index("Date").Value.astype(int)
    assert all(imm.loc[int(y)] == v for y, v in tot.items())
    assert DATA.pref.population.sum() == 8_095_498
    assert DATA.pref.ae_n.sum() == 272 and len(DATA.pref) == 39
    reg = DATA.reg.set_index("region")
    assert reg.population.sum() == 8_095_498
    km = DATA.troncons.Total.sum()
    assert abs(km - (2198.47 + 964.96)) < 1
    assert DATA.permis[DATA.permis.annee == 2013].empty  # 2013 traité comme manquant


def test_controls_and_scores():
    assert (DATA.controles.statut == "Écart").sum() <= 2
    assert DATA.pref.score.between(0, 100).all() or DATA.pref.score.isna().any()
    assert set(DATA.recommandations.priorite) <= {"Élevée", "Moyenne", "À surveiller"}
    assert DATA.recommandations.indicateur.str.len().min() > 10  # chaque recommandation cite un indicateur


# ── Interface : aucun filtre ne doit casser l'interface ──────────────────────────────────

YEAR_CASES = [[1990, 2022], [2010, 2022], [1990, 2005], [2013, 2013], [2022, 2022]]
TERR_CASES = [(None, None), ("Kara", None), ("Maritime", "GOLFE"), ("Centrale", "MO"), ("Plateaux", "DANYI")]


def test_overview_all_filters():
    f = cb("ov-kpis")
    for years, (reg, pref), veh, perm in itertools.product(YEAR_CASES, TERR_CASES, [VEHICLE_TYPES, [], ["Camions"]],
                                                           [PERMIS, []]):
        out = f(years, reg, pref, veh, perm, {"etat": 40, "formation": 35, "desserte": 25})
        assert len(out) == 8
        for o in out:
            if isinstance(o, go.Figure):
                o.to_dict()


def test_mobilite_all_filters():
    f = cb("mob-kpis")
    for years, veh, perm, mode in itertools.product(YEAR_CASES, [VEHICLE_TYPES, [], ["Deux-roues"], ["Voitures"]],
                                                    [PERMIS, [], ["A · Moto"]], ["volume", "part"]):
        out = f(years, veh, perm, mode, mode)
        assert len(out) == 10


def test_securite_all_filters():
    f = cb("saf-kpis")
    for years, metric, x, y in itertools.product(YEAR_CASES, ["taux_deces_100k", "accidents_10k_immat",
                                                              "deces_100_accidents"],
                                                 ["immatriculations", "immat_deux_roues"], ["accidents", "deces"]):
        out = f(years, metric, x, y)
        assert len(out) == 12


def test_reseau_all_filters():
    f = cb("net-kpis")
    for (reg, pref), etats, mode, layers, smode in itertools.product(
            TERR_CASES + [("Savanes", "OTI")], [ETATS, [], ["Mauvais"]], ["reseau", "formation"],
            [["routes", "ae"], []], ["part", "km"]):
        out = f(reg, pref, etats, mode, layers, smode, {"etat": 0, "formation": 0, "desserte": 100})
        assert len(out) == 12


def test_controller_and_clicks():
    ctrl = cb("f-region.value...f-pref.value...f-pref.options")
    with_trigger("f-pref.value", "KOZAH")
    region, pref, opts, *_ = ctrl(None, "KOZAH", 0)
    assert region == "Kara" and pref == "KOZAH" and len(opts) == 7
    with_trigger("f-region.value", "Savanes")
    region, pref, *_ = ctrl("Savanes", "KOZAH", 0)
    assert region == "Savanes" and pref is None  # préfecture hors région effacée
    with_trigger("btn-reset.n_clicks", 1)
    out = ctrl("Kara", "KOZAH", 1)
    assert out[0] is None and out[1] is None and out[4] == [] and out[5] == [] and out[6] == ETATS
    detail = cb("net-detail")
    for i in [0, 100, 500]:
        with_trigger("net-map.clickData", {"points": [{"customdata": i}]})
        detail(None, None, {"points": [{"customdata": i}]}, None)
    with_trigger("f-pref.value", "GOLFE")
    detail("Maritime", "GOLFE", None, None)


def test_reco_quality_compare_weights():
    reco = cb("reco-list")
    for (reg, pref), cat, prio in itertools.product(TERR_CASES, ["all", "Urgence", "Formation"], ["all", "Élevée"]):
        reco(reg, pref, cat, prio)
    q = cb("dq-table")
    for v in ["inventaire", "controles", "anomalies", "journal", "variables", "limites"]:
        data, cols, *_ = q(v)
        assert len(data) > 0 and len(cols) > 0
    cmp_ = cb("cmp-table")
    for a, b in itertools.product(REGIONS, REGIONS):
        cmp_(a, b, None)
    w = cb("weights.data")
    w(0, 0, 0)
    w(100, 0, 0)


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"{len(tests)} tests réussis")
