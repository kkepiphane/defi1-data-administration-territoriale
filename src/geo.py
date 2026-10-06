"""Géographie : limites administratives, longueurs routières, contrôles spatiaux, rattachement des tronçons.

Méthode de rattachement d'un tronçon évalué (fichier « état du réseau ») à une région, dans cet ordre :
  1. code régional présent dans le libellé (TGR + M/P/C/K/S) ;
  2. correspondance avec les géométries des routes classées : nom normalisé identique ou quasi identique
     (similarité ≥ 0,92), ou nom proche (≥ 0,60) ET longueur concordante à ± 5 % ;
  3. toponymes du libellé retrouvés dans la nomenclature RGPH-5 (cantons, communes, préfectures) ;
  4. à défaut : « Non attribué ».
"""
from __future__ import annotations

import difflib
import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Geod
from shapely import wkt
from shapely.geometry import Point

from .cleaning import Journal, fr_num, key, strip_accents
from .config import BOUNDARIES_FILE, OCHA_ALIASES, REGION_CODES

GEOD = Geod(ellps="WGS84")


# ── Limites administratives ──────────────────────────────────────────────────────────────

def load_boundaries(prefs: pd.DataFrame, j: Journal) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    src = "Limites administratives (OCHA)"
    g = gpd.read_file(BOUNDARIES_FILE)[["adm2_name", "adm2_pcode", "adm1_name", "area_sqkm", "geometry"]]
    g["prefecture_key"] = g.adm2_name.map(key).replace(OCHA_ALIASES)
    j.log(src, "Harmonisation des noms OCHA", "« Naki-Ouest » → Kpendjal-Ouest ; « Plaine du Mo » → Mô ; "
          "« Lome Commune » fusionnée avec Golfe (le RGPH-5 compte Lomé dans la préfecture du Golfe)", 3)
    pref = g.dissolve(by="prefecture_key", aggfunc={"area_sqkm": "sum", "adm2_pcode": "first"}).reset_index()
    pref = pref.merge(prefs[["prefecture_key", "region"]], on="prefecture_key", how="left")
    miss_pop = sorted(set(prefs.prefecture_key) - set(pref.prefecture_key))
    miss_geo = sorted(set(pref.prefecture_key) - set(prefs.prefecture_key))
    j.control(src, "Correspondance préfectures OCHA ↔ RGPH-5",
              f"{len(pref) - len(miss_geo)} / {len(prefs)} préfectures appariées"
              + (f" ; sans polygone : {', '.join(miss_pop)}" if miss_pop else "")
              + (f" ; sans population : {', '.join(miss_geo)}" if miss_geo else ""), not miss_pop and not miss_geo)
    reg = pref.dissolve(by="region", aggfunc={"area_sqkm": "sum"}).reset_index()
    j.log(src, "Polygones régionaux", "Fusion des préfectures selon la région d'analyse (5 régions)", len(reg))
    return pref, reg


def to_geojson(gdf: gpd.GeoDataFrame, id_col: str, tolerance: float = 0.003) -> dict:
    """GeoJSON allégé pour l'affichage (simplification topologique ~200 m)."""
    g = gdf[[id_col, "geometry"]].copy()
    g["geometry"] = g.geometry.simplify(tolerance, preserve_topology=True)
    gj = json.loads(g.to_json())
    for f in gj["features"]:
        f["id"] = f["properties"][id_col]
    return gj


def bbox_view(minx, miny, maxx, maxy, width_px=700, height_px=470, pad=1.2) -> dict:
    """Centre et niveau de zoom (MapLibre, monde = 512 × 2^zoom px) pour cadrer une emprise."""
    lon_span = max(maxx - minx, 0.04) * pad
    lat_span = max(maxy - miny, 0.04) * pad * 1.02  # étirement de Mercator vers 9° N
    zx = np.log2(width_px * 360 / (512 * lon_span))
    zy = np.log2(height_px * 360 / (512 * lat_span))
    return {"center": {"lon": (minx + maxx) / 2, "lat": (miny + maxy) / 2}, "zoom": float(min(zx, zy, 11.5))}


# ── Géométries des routes ────────────────────────────────────────────────────────────────

def build_roads(routes: pd.DataFrame, pref_poly: gpd.GeoDataFrame, j: Journal) -> gpd.GeoDataFrame:
    src = "Routes classées (géométries)"
    geoms = routes.geometry.map(wkt.loads)
    invalid = (~geoms.map(lambda g: g.is_valid)).sum()
    empty = geoms.map(lambda g: g.is_empty).sum()
    j.control(src, "Géométries lisibles et non vides", f"{len(geoms) - empty} / {len(geoms)} (invalides : {invalid})",
              empty == 0)
    gdf = gpd.GeoDataFrame(routes.drop(columns="geometry"), geometry=list(geoms), crs=4326)
    gdf["km"] = [GEOD.geometry_length(g) / 1000 for g in gdf.geometry]
    j.log(src, "Calcul des longueurs", "Longueur géodésique sur l'ellipsoïde WGS84 (pyproj.Geod) ; le champ "
          "troncon_longueur_km du dictionnaire est absent de l'export", len(gdf))
    tiny = (gdf.km < 0.01).sum()
    if tiny:
        j.anomaly(src, f"{tiny} segments", "Segment de longueur quasi nulle", "Moins de 10 m", "Conservés")
    # Contrôle spatial : point représentatif du segment dans la préfecture déclarée
    rep = gdf.geometry.representative_point()
    joined = gpd.sjoin(gpd.GeoDataFrame(geometry=rep, crs=4326), pref_poly[["prefecture_key", "geometry"]],
                       how="left", predicate="within")
    joined = joined[~joined.index.duplicated()]
    gdf["prefecture_spatiale"] = joined.prefecture_key.values
    inside = (joined.prefecture_key.values == gdf.prefecture_key.values)
    gdf["dans_prefecture_declaree"] = inside
    j.control(src, "Segment situé dans la préfecture déclarée (point représentatif)",
              f"{int(inside.sum())} / {len(gdf)} ({fr_num(100 * inside.mean(), 1)} %) ; écarts près des limites",
              None)
    return gdf


def line_coords(gdf: gpd.GeoDataFrame, tolerance: float = 0.00025) -> list[tuple[list, list]]:
    """Coordonnées simplifiées (~25 m) de chaque segment, pour le tracé."""
    out = []
    for geom in gdf.geometry.simplify(tolerance, preserve_topology=False):
        lons, lats = [], []
        parts = getattr(geom, "geoms", [geom])
        for part in parts:
            xs, ys = part.xy
            lons += [round(v, 5) for v in xs] + [None]
            lats += [round(v, 5) for v in ys] + [None]
        out.append((lons, lats))
    return out


def hover_points(gdf: gpd.GeoDataFrame, step_km: float = 3.0) -> pd.DataFrame:
    """Points de survol répartis le long de chaque segment (≈ tous les 3 km, au moins un par segment).

    Les tracés eux-mêmes ne portent pas d'infobulle : la figure reste légère.
    """
    rows = []
    for i, geom, km in zip(gdf.index, gdf.geometry, gdf.km):
        n = max(1, int(round(km / step_km)))
        for k in range(n):
            p = geom.interpolate((k + 0.5) / n, normalized=True)
            rows.append((round(p.x, 5), round(p.y, 5), i))
    return pd.DataFrame(rows, columns=["lon", "lat", "seg"])


def check_points(ae: pd.DataFrame, pref_poly: gpd.GeoDataFrame, j: Journal) -> pd.DataFrame:
    pts = gpd.GeoDataFrame(geometry=[Point(x, y) for x, y in zip(ae.lon, ae.lat)], crs=4326)
    joined = gpd.sjoin(pts, pref_poly[["prefecture_key", "geometry"]], how="left", predicate="within")
    joined = joined[~joined.index.duplicated()]
    inside = joined.prefecture_key.values == ae.prefecture_key.values
    j.control("Auto-écoles", "Point situé dans la préfecture déclarée",
              f"{int(inside.sum())} / {len(ae)} ({fr_num(100 * inside.mean(), 1)} %) ; la préfecture déclarée fait foi",
              None)
    return pd.DataFrame({"dans_prefecture_declaree": inside, "prefecture_spatiale": joined.prefecture_key.values},
                        index=ae.index)


# ── Rattachement des tronçons évalués ────────────────────────────────────────────────────

STOP = {"ROUTE", "BRETELLE", "FRT", "FRE", "RETOUR", "PASSAGE", "SUPERIEUR", "CARREFOUR", "GHANA", "BENIN", "BURKINA",
        "VOIE", "CHAUSSEE", "NORD", "SUD", "HOPITAL", "EGLISE", "CATHOLIQUE", "SAINT", "JEAN", "PAUL", "MONT", "GHABA",
        "CAMPEMENT", "CHATEAU", "VIAL", "PRESIDENT", "COPE", "KOPE", "CENTRE", "MARCHE", "DEPOT", "GARE", "RUES"}


def route_key(name: str) -> tuple[str | None, str]:
    s = strip_accents(name).upper().strip()
    s = re.sub(r"_\d+$", "", s)
    m = re.match(r"^TGR([MPCKS])", s)
    code = m.group(1) if m else None
    if m:
        s = re.sub(r"^TGR[MPCKS][RVTA]*?(?=RN\d|\s|$)", "", s)
    return code, re.sub(r"[^A-Z0-9]+", " ", s).strip()


def gazetteer(units: pd.DataFrame, roads: pd.DataFrame) -> dict[str, dict[str, set]]:
    """Mot (≥ 4 lettres) → {région: {libellés}} à partir de la nomenclature RGPH-5 et des bases géolocalisées."""
    gaz: dict[str, dict[str, set]] = {}

    def add(label, region):
        if not isinstance(region, str):
            return
        for w in key(label).split():
            if len(w) >= 4 and not w.isdigit() and w not in STOP:
                gaz.setdefault(w, {}).setdefault(region, set()).add(label)

    for r in units[units.niveau.isin(["préfecture", "commune", "canton"])].itertuples():
        add(r.libelle, r.region)
    for r in roads[["canton", "commune", "region"]].drop_duplicates().itertuples():
        add(r.canton, r.region)
    return gaz


def attribute_troncons(tr: pd.DataFrame, roads: gpd.GeoDataFrame, units: pd.DataFrame, j: Journal):
    """Rattache chaque tronçon évalué à une région et aux segments géolocalisés correspondants."""
    src = "État du réseau routier"
    roads = roads.copy()
    roads[["code", "rkey"]] = roads.route_nom.apply(lambda s: pd.Series(route_key(s)))
    groups = roads.groupby("rkey").agg(km=("km", "sum"), region=("region", lambda s: s.mode().iloc[0]),
                                       n=("km", "size")).reset_index()
    tr = tr.copy()
    tr[["code", "tkey"]] = tr.troncon_source.apply(lambda s: pd.Series(route_key(s)))

    # Appariement par nom (et longueur) — chaque groupe géométrique va au tronçon le plus semblable.
    cand = []
    for i, t in tr.iterrows():
        for g in groups.itertuples():
            ratio = difflib.SequenceMatcher(None, t.tkey, g.rkey).ratio()
            len_gap = abs(g.km - t.Total) / t.Total if t.Total else np.inf
            if ratio >= 0.92:
                rule = "nom identique ou quasi identique"
            elif ratio >= 0.60 and len_gap <= 0.05:
                rule = "nom proche et longueur concordante (± 5 %)"
            else:
                continue
            if t.code and REGION_CODES[t.code] != g.region:
                continue
            cand.append((i, g.rkey, ratio, len_gap, rule, g.km, g.region))
    cand = pd.DataFrame(cand, columns=["i", "rkey", "ratio", "len_gap", "rule", "km_geo", "region_geo"])
    cand = cand.sort_values("ratio", ascending=False).drop_duplicates("rkey")
    match = cand.groupby("i").agg(rkeys=("rkey", list), regle=("rule", "first"), km_geo=("km_geo", "sum"),
                                  region_geo=("region_geo", lambda s: s.mode().iloc[0]),
                                  similarite=("ratio", "max")).reset_index()
    tr = tr.join(match.set_index("i"))

    gaz = gazetteer(units, roads)
    regions, methods, details = [], [], []
    for r in tr.itertuples():
        if r.code:
            regions.append(REGION_CODES[r.code])
            methods.append("Code régional du libellé")
            details.append(f"préfixe TGR{r.code}")
        elif isinstance(r.rkeys, list):
            regions.append(r.region_geo)
            methods.append("Géométrie appariée")
            details.append(f"{r.regle} : {fr_num(r.km_geo, 1)} km géolocalisés pour {fr_num(r.Total, 1)} km évalués")
        else:
            votes: dict[str, set] = {}
            for w in key(r.troncon_source).split():
                for reg, labels in gaz.get(w, {}).items():
                    votes.setdefault(reg, set()).add(w)
            if len(votes) == 1:
                reg = next(iter(votes))
                regions.append(reg)
                methods.append("Toponymes (RGPH-5)")
                details.append("toponymes reconnus : " + ", ".join(sorted(votes[reg])))
            else:
                regions.append(None)
                methods.append("Non attribué")
                details.append("aucun indice univoque" if not votes else
                               "toponymes de plusieurs régions : " + ", ".join(sorted(votes)))
    tr["region"] = regions
    tr["methode_attribution"] = methods
    tr["detail_attribution"] = details
    tr["geolocalise"] = tr.rkeys.map(lambda v: isinstance(v, list))

    # Contrôles et traçabilité
    both = tr[tr.code.notna() & tr.geolocalise]
    agree = (both.code.map(REGION_CODES) == both.region_geo).sum()
    j.control(src, "Région du code = région des géométries appariées", f"{agree} / {len(both)} tronçons", agree == len(both))
    counts = tr.methode_attribution.value_counts()
    j.log(src, "Rattachement régional des tronçons",
          " ; ".join(f"{m} : {n}" for m, n in counts.items()) + " (méthode détaillée dans le rapport)", len(tr))
    km_geo = tr.Total[tr.geolocalise].sum()
    j.control(src, "Tronçons évalués retrouvés dans les géométries",
              f"{int(tr.geolocalise.sum())} / {len(tr)} tronçons ; {fr_num(km_geo)} / {fr_num(tr.Total.sum())} km "
              f"({fr_num(100 * km_geo / tr.Total.sum(), 1)} %)", None)
    na = tr[tr.region.isna()]
    for r in na.itertuples():
        j.anomaly(src, r.troncon_source, "Tronçon non attribué", r.detail_attribution,
                  "Inclus dans le total national, exclu des comparaisons régionales")

    # Segments : état du tronçon apparié
    owner = {rk: i for i, rks in tr.rkeys.items() if isinstance(rks, list) for rk in rks}
    roads["troncon_idx"] = roads.rkey.map(owner)
    shares = tr[["Bon", "Moyen", "Mauvais", "Travaux"]].div(tr.Total.replace(0, np.nan), axis=0)
    tr["etat_dominant"] = tr[["Bon", "Moyen", "Mauvais", "Travaux"]].idxmax(axis=1)
    for e in ["Bon", "Moyen", "Mauvais", "Travaux"]:
        roads[f"part_{e}"] = roads.troncon_idx.map(shares[e])
    roads["etat"] = roads.troncon_idx.map(tr.etat_dominant).fillna("Non évalué")
    roads["troncon"] = roads.troncon_idx.map(tr.troncon)
    seg_eval = roads.troncon_idx.notna()
    j.log("Routes classées (géométries)", "Report de l'état sur les segments",
          f"{int(seg_eval.sum())} segments ({fr_num(roads.km[seg_eval].sum())} km) reçoivent la répartition par état de "
          "leur tronçon ; couleur = état majoritaire du tronçon ; les autres sont « non renseignés »", int(seg_eval.sum()))
    return tr.drop(columns=["rkeys", "code", "tkey"]), roads.drop(columns=["code", "rkey"])
