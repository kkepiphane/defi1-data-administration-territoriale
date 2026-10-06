"""Orchestration : sources brutes → tables propres, indicateurs, contrôles. Exporte data/processed/."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import geopandas as gpd
import pandas as pd

from . import cleaning as cl, geo, indicators as ind
from .config import BOUNDARIES_SOURCE, EXTRA_PREF_NAMES, PROCESSED_DIR, REGIONS
from .loading import inventory, load_all


@dataclass
class Data:
    immat: pd.DataFrame
    immat_cyl: pd.DataFrame
    national: pd.DataFrame
    permis: pd.DataFrame
    safety: pd.DataFrame
    units: pd.DataFrame
    pref: pd.DataFrame
    reg: pd.DataFrame
    auto_ecoles: pd.DataFrame
    roads: pd.DataFrame
    road_lines: list
    road_hover: pd.DataFrame
    troncons: pd.DataFrame
    reseau_totaux: pd.DataFrame
    voiries: pd.DataFrame
    pref_geojson: dict
    region_geojson: dict
    views: dict
    inventory_files: pd.DataFrame
    inventory_vars: pd.DataFrame
    journal: pd.DataFrame
    controles: pd.DataFrame
    anomalies: pd.DataFrame
    recommandations: pd.DataFrame = None
    meta: dict = field(default_factory=dict)


def build(write: bool = True, verbose: bool = False) -> Data:
    t0 = time.perf_counter()
    j = cl.Journal()
    cl.FLAGS.clear()
    raw = load_all()
    inv_files, inv_vars = inventory(raw)
    j.log("Toutes sources", "Lecture en texte brut", "Fichiers ouverts en lecture seule ; empreinte SHA-256 relevée "
          "pour prouver que les sources ne sont pas modifiées", int(inv_files.lignes.sum()))

    units, prefs, pop_total = cl.clean_population(raw["population"], j)
    pref_keys = set(prefs.prefecture_key)
    immat = cl.clean_immatriculations(raw["immatriculations"], j)
    immat_cyl = cl.clean_immat_detail(raw["immat_detail"], immat, j)
    national = cl.clean_national(raw["national"], j, pop_total)
    # Recoupements immatriculations ↔ séries nationales
    four = immat[immat.famille != "Deux-roues"].groupby("annee").valeur.sum()
    ok4 = (national["immat_4r"].dropna() - four).abs().dropna() < 0.5
    j.control("Immatriculations", "4 roues et plus = série nationale « parc 4 roues et plus »",
              f"{int(ok4.sum())} / {len(ok4)} années conformes", bool(ok4.all()))
    two = immat[immat.famille == "Deux-roues"].groupby("annee").valeur.sum()
    ok2 = (national["immat_2r"].dropna() - two).abs().dropna() < 0.5
    j.control("Immatriculations", "Deux-roues = série nationale « deux roues et assimilées »",
              f"{int(ok2.sum())} / {len(ok2)} années conformes", bool(ok2.all()))
    permis = cl.clean_permis(raw["permis"], national, j)
    ae = cl.clean_auto_ecoles(raw["auto_ecoles"], pref_keys, j)
    routes = cl.clean_routes_geo(raw["routes_geo"], pref_keys, j)
    tr, totals, voiries = cl.clean_etat_routes(raw["etat_routes"], j)

    # Noms d'affichage des préfectures (orthographe des bases géolocalisées)
    names = pd.concat([ae[["prefecture_key", "prefecture"]], routes[["prefecture_key", "prefecture"]]])
    names = names.drop_duplicates("prefecture_key").set_index("prefecture_key").prefecture.to_dict()
    names.update({k: v for k, v in EXTRA_PREF_NAMES.items() if k not in names})
    prefs["prefecture"] = prefs.prefecture_key.map(names).fillna(prefs.prefecture_source.str.title())
    absent = prefs[~prefs.prefecture_key.isin(set(routes.prefecture_key) | set(ae.prefecture_key))]

    pref_poly, reg_poly = geo.load_boundaries(prefs, j)
    roads = geo.build_roads(routes, pref_poly, j)
    ae = ae.join(geo.check_points(ae, pref_poly, j))
    for p in absent.itertuples():
        n_seg = int((roads.prefecture_spatiale == p.prefecture_key).sum())
        n_ae = int((ae.prefecture_spatiale == p.prefecture_key).sum())
        j.control("Nomenclature", f"{p.prefecture} : préfecture absente des bases routes et auto-écoles",
                  f"{n_seg} segment(s) et {n_ae} auto-école(s) situés dans son polygone OCHA → "
                  + ("zéro cohérent avec la géographie" if n_seg + n_ae == 0 else "rattachement à vérifier"),
                  n_seg + n_ae == 0)
    troncons, roads = geo.attribute_troncons(tr, roads, units, j)

    roads["hover"] = [_segment_hover(r) for r in roads.itertuples()]
    pref, reg = ind.territorial_tables(prefs, pref_poly, ae, roads, troncons)
    pref = ind.priority_scores(pref)
    reg = ind.priority_scores(reg)
    reg["region"] = pd.Categorical(reg.region, REGIONS, ordered=True)
    reg = reg.sort_values("region").reset_index(drop=True)
    reg["region"] = reg.region.astype(str)
    safety = ind.safety_table(national, immat)

    # Emprises pour le zoom des cartes
    views = {"Togo": tuple(pref_poly.total_bounds)}
    for r in reg_poly.itertuples():
        views[r.region] = tuple(r.geometry.bounds)
    for p in pref_poly.itertuples():
        views[p.prefecture_key] = tuple(p.geometry.bounds)

    frames = j.frames()
    data = Data(
        immat=immat, immat_cyl=immat_cyl, national=national, permis=permis, safety=safety, units=units,
        pref=pref, reg=reg, auto_ecoles=ae, roads=pd.DataFrame(roads.drop(columns="geometry")),
        road_lines=geo.line_coords(roads), road_hover=geo.hover_points(roads), troncons=troncons, reseau_totaux=totals, voiries=voiries,
        pref_geojson=geo.to_geojson(pref_poly, "prefecture_key"), region_geojson=geo.to_geojson(reg_poly, "region"),
        views=views, inventory_files=inv_files, inventory_vars=inv_vars, journal=frames["journal"],
        controles=frames["controles"], anomalies=frames["anomalies"],
        meta={"population_2022": pop_total, "source_limites": BOUNDARIES_SOURCE, "flags": {k: dict(v) for k, v in cl.FLAGS.items()},
              "build_seconds": round(time.perf_counter() - t0, 2)},
    )
    from .recommendations import build_recommendations  # import tardif : dépend de Data
    data.recommandations = build_recommendations(data)
    if write:
        export(data, roads, pref_poly)
    if verbose:
        print(f"Pipeline exécuté en {time.perf_counter() - t0:.1f} s")
    return data


def _segment_hover(r) -> str:
    head = f"<b>{r.troncon if isinstance(r.troncon, str) else r.route_nom}</b>"
    base = f"{r.route_type} · {r.route_recouvrement.lower()}<br>{r.prefecture} ({r.region}) · segment de {cl.fr_num(r.km, 1)} km"
    if r.etat == "Non évalué":
        return f"{head}<br>{base}<br><i>État non renseigné (tronçon absent du relevé 2020)</i>"
    parts = " · ".join(f"{e} {cl.fr_num(100 * getattr(r, 'part_' + e), 0)} %" for e in ["Bon", "Moyen", "Mauvais", "Travaux"]
                       if getattr(r, "part_" + e) > 0)
    return f"{head}<br>{base}<br>État du tronçon (2020) : {parts}"


def export(data: Data, roads: gpd.GeoDataFrame, pref_poly: gpd.GeoDataFrame):
    """Tables traitées et tables de contrôle, rejouables à l'identique (python app.py --rebuild)."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "immatriculations.csv": data.immat,
        "immatriculations_cylindree.csv": data.immat_cyl,
        "series_nationales.csv": data.national.reset_index(),
        "permis.csv": data.permis,
        "securite_routiere.csv": data.safety.reset_index(),
        "population_unites.csv": data.units,
        "indicateurs_prefectures.csv": data.pref,
        "indicateurs_regions.csv": data.reg,
        "auto_ecoles.csv": data.auto_ecoles,
        "troncons_etat.csv": data.troncons,
        "segments_routes.csv": data.roads,
        "recommandations.csv": data.recommandations,
        "qualite_inventaire_fichiers.csv": data.inventory_files,
        "qualite_inventaire_variables.csv": data.inventory_vars,
        "qualite_journal.csv": data.journal,
        "qualite_controles.csv": data.controles,
        "qualite_anomalies.csv": data.anomalies,
    }
    for name, df in out.items():
        df.to_csv(PROCESSED_DIR / name, index=False, encoding="utf-8-sig", float_format="%.4f")
    (PROCESSED_DIR / "prefectures.geojson").write_text(json.dumps(data.pref_geojson), encoding="utf-8")
    (PROCESSED_DIR / "meta.json").write_text(json.dumps(data.meta, ensure_ascii=False, indent=2), encoding="utf-8")
