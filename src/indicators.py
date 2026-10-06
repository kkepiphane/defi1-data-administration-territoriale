"""Calcul des indicateurs. Toutes les fonctions sont pures : mêmes entrées → mêmes sorties."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .cleaning import fr_num
from .config import ETATS, FAMILLES, PERMIS

# ── Séries nationales ────────────────────────────────────────────────────────────────────


def immat_wide(immat: pd.DataFrame, types: list[str] | None = None, by: str = "famille") -> pd.DataFrame:
    """Immatriculations annuelles, une colonne par famille (ou type), restreintes aux types retenus."""
    df = immat if not types else immat[immat["type"].isin(types)]
    if df.empty:
        return pd.DataFrame()
    w = df.pivot_table(index="annee", columns=by, values="valeur", aggfunc="sum").sort_index()
    order = [c for c in (FAMILLES if by == "famille" else w.columns) if c in w.columns]
    return w[order]


def permis_wide(permis: pd.DataFrame, cats: list[str] | None = None) -> pd.DataFrame:
    df = permis if not cats else permis[permis.categorie.isin(cats)]
    if df.empty:
        return pd.DataFrame()
    w = df.pivot_table(index="annee", columns="categorie", values="valeur", aggfunc="sum").sort_index()
    return w[[c for c in PERMIS if c in w.columns]]


def safety_table(national: pd.DataFrame, immat: pd.DataFrame) -> pd.DataFrame:
    """Tableau annuel de sécurité routière (échelle nationale) avec les taux dérivés."""
    n = national.copy()
    tot = immat.groupby("annee")["valeur"].sum()
    deux = immat[immat.famille == "Deux-roues"].groupby("annee")["valeur"].sum()
    out = pd.DataFrame(index=n.index)
    out["accidents"] = n["accidents"]
    out["blesses"] = n["blesses"]
    out["deces"] = n["deces"]
    out["pop_implicite"] = n["pop_implicite"]
    out["taux_accidents_100k"] = n["taux_accidents_publie"]
    out["taux_deces_100k"] = n["deces"] / n["pop_implicite"] * 1e5
    out["taux_blesses_100k"] = n["blesses"] / n["pop_implicite"] * 1e5
    out["deces_100_accidents"] = n["deces"] / n["accidents"] * 100
    out["blesses_par_accident"] = n["blesses"] / n["accidents"]
    out["immatriculations"] = tot.reindex(out.index)
    out["immat_deux_roues"] = deux.reindex(out.index)
    out["accidents_10k_immat"] = out["accidents"] / out["immatriculations"] * 1e4
    out["deces_10k_immat"] = out["deces"] / out["immatriculations"] * 1e4
    out = out[out[["accidents", "deces", "blesses"]].notna().any(axis=1)]
    out.index.name = "annee"
    return out


SAFETY_LABELS = {
    "accidents": "Accidents",
    "blesses": "Blessés",
    "deces": "Décès",
    "taux_accidents_100k": "Accidents pour 100 000 hab.",
    "taux_deces_100k": "Décès pour 100 000 hab.",
    "taux_blesses_100k": "Blessés pour 100 000 hab.",
    "deces_100_accidents": "Décès pour 100 accidents",
    "blesses_par_accident": "Blessés par accident",
    "accidents_10k_immat": "Accidents pour 10 000 immatriculations",
    "deces_10k_immat": "Décès pour 10 000 immatriculations",
    "pop_implicite": "Population implicite (dénominateur)",
    "immatriculations": "Immatriculations de l'année",
    "immat_deux_roues": "dont deux-roues",
}
SAFETY_DECIMALS = {"taux_accidents_100k": 1, "taux_deces_100k": 2, "taux_blesses_100k": 1,
                   "deces_100_accidents": 1, "blesses_par_accident": 2, "accidents_10k_immat": 0,
                   "deces_10k_immat": 1}


def last_valid(s: pd.Series):
    s = s.dropna()
    return (s.index[-1], s.iloc[-1]) if len(s) else (None, np.nan)


def yoy(s: pd.Series) -> tuple[float, int | None]:
    """Variation (%) entre la dernière valeur disponible et l'année précédente disponible."""
    s = s.dropna()
    if len(s) < 2 or s.iloc[-2] == 0:
        return np.nan, None
    return 100 * (s.iloc[-1] / s.iloc[-2] - 1), int(s.index[-2])


def cagr(s: pd.Series) -> tuple[float, int | None, int | None]:
    s = s.dropna()
    s = s[s > 0]
    if len(s) < 2:
        return np.nan, None, None
    y0, y1 = int(s.index[0]), int(s.index[-1])
    return 100 * ((s.iloc[-1] / s.iloc[0]) ** (1 / (y1 - y0)) - 1), y0, y1


def pearson(x: pd.Series, y: pd.Series) -> tuple[float, int]:
    d = pd.concat([x, y], axis=1).dropna()
    if len(d) < 4:
        return np.nan, len(d)
    return float(np.corrcoef(d.iloc[:, 0], d.iloc[:, 1])[0, 1]), len(d)


# ── Tables territoriales ─────────────────────────────────────────────────────────────────

def territorial_tables(prefs, pref_poly, ae, roads, troncons):
    """Indicateurs par préfecture (39) et par région (5)."""
    p = prefs.merge(pref_poly[["prefecture_key", "area_sqkm"]], on="prefecture_key", how="left")
    # Auto-écoles
    g = ae.groupby("prefecture_key")
    p["ae_n"] = p.prefecture_key.map(g.size()).fillna(0).astype(int)
    p["ae_agreees"] = p.prefecture_key.map(g.agree.sum()).fillna(0).astype(int)
    p["ae_non_agreees"] = p.prefecture_key.map(ae[ae.agrement == "Non agréée"].groupby("prefecture_key").size()
                                               ).fillna(0).astype(int)
    p["ae_100k"] = p.ae_n / p.population * 1e5
    p["part_non_agreees"] = np.where(p.ae_n > 0, 100 * p.ae_non_agreees / p.ae_n.replace(0, np.nan), np.nan)
    p["hab_par_ae"] = np.where(p.ae_n > 0, p.population / p.ae_n.replace(0, np.nan), np.nan)
    # Réseau classé (géométries)
    r = roads.groupby("prefecture_key")
    p["km_classe"] = p.prefecture_key.map(r.km.sum()).fillna(0)
    p["km_revetu"] = p.prefecture_key.map(roads[roads.revetement == "Revêtu"].groupby("prefecture_key").km.sum()).fillna(0)
    p["part_revetu"] = np.where(p.km_classe > 0, 100 * p.km_revetu / p.km_classe.replace(0, np.nan), np.nan)
    p["densite_km_1000km2"] = p.km_classe / p.area_sqkm * 1000
    p["km_100k_hab"] = p.km_classe / p.population * 1e5
    # État (≈ estimation : km du segment × répartition par état de son tronçon)
    ev = roads[roads.troncon_idx.notna()]
    p["km_evalue_est"] = p.prefecture_key.map(ev.groupby("prefecture_key").km.sum()).fillna(0)
    for e in ETATS:
        est = (ev.km * ev[f"part_{e}"]).groupby(ev.prefecture_key).sum()
        p[f"km_{e.lower()}_est"] = p.prefecture_key.map(est).fillna(0)
    p["part_mauvais"] = np.where(p.km_evalue_est > 0, 100 * p.km_mauvais_est / p.km_evalue_est.replace(0, np.nan), np.nan)
    p["part_travaux"] = np.where(p.km_evalue_est > 0, 100 * p.km_travaux_est / p.km_evalue_est.replace(0, np.nan), np.nan)
    p["km_mauvais_100k"] = p.km_mauvais_est / p.population * 1e5
    p["etat_estime"] = True

    # Régions : état exact (somme des tronçons attribués)
    reg = p.groupby("region").agg(population=("population", "sum"), area_sqkm=("area_sqkm", "sum"),
                                  ae_n=("ae_n", "sum"), ae_agreees=("ae_agreees", "sum"),
                                  ae_non_agreees=("ae_non_agreees", "sum"), km_classe=("km_classe", "sum"),
                                  km_revetu=("km_revetu", "sum"), n_prefectures=("prefecture_key", "size"),
                                  prefectures_sans_ae=("ae_n", lambda s: int((s == 0).sum()))).reset_index()
    reg["ae_100k"] = reg.ae_n / reg.population * 1e5
    reg["part_non_agreees"] = 100 * reg.ae_non_agreees / reg.ae_n.replace(0, np.nan)
    reg["hab_par_ae"] = reg.population / reg.ae_n.replace(0, np.nan)
    reg["part_revetu"] = 100 * reg.km_revetu / reg.km_classe
    reg["densite_km_1000km2"] = reg.km_classe / reg.area_sqkm * 1000
    reg["km_100k_hab"] = reg.km_classe / reg.population * 1e5
    t = troncons[troncons.region.notna()].groupby("region")[["Total"] + ETATS].sum()
    reg["km_evalue"] = reg.region.map(t["Total"]).fillna(0)
    for e in ETATS:
        reg[f"km_{e.lower()}"] = reg.region.map(t[e]).fillna(0)
    reg["part_mauvais"] = 100 * reg.km_mauvais / reg.km_evalue.replace(0, np.nan)
    reg["part_travaux"] = 100 * reg.km_travaux / reg.km_evalue.replace(0, np.nan)
    reg["part_bon"] = 100 * reg.km_bon / reg.km_evalue.replace(0, np.nan)
    reg["km_mauvais_100k"] = reg.km_mauvais / reg.population * 1e5
    reg["etat_estime"] = False
    return p, reg


# ── Score de priorité territoriale ───────────────────────────────────────────────────────

SCORE_COMPONENTS = {
    "etat": {"label": "Réseau en mauvais état", "col": "part_mauvais", "sens": +1,
             "definition": "Part du linéaire évalué en mauvais état (%)"},
    "formation": {"label": "Déficit de formation", "col": "ae_100k", "sens": -1,
                  "definition": "Auto-écoles pour 100 000 habitants (moins il y en a, plus le score monte)"},
    "desserte": {"label": "Faible desserte routière", "col": "densite_km_1000km2", "sens": -1,
                 "definition": "Km de routes classées pour 1 000 km² (moins il y en a, plus le score monte)"},
}
UNAVAILABLE_COMPONENTS = {
    "mortalite": "Mortalité routière — publiée à l'échelle nationale uniquement",
    "accidentologie": "Accidentologie — publiée à l'échelle nationale uniquement",
    "motorisation": "Motorisation — immatriculations publiées à l'échelle nationale uniquement",
}
DEFAULT_WEIGHTS = {"etat": 40, "formation": 35, "desserte": 25}


def priority_scores(table: pd.DataFrame, weights: dict | None = None) -> pd.DataFrame:
    """Score 0–100 : moyenne pondérée des rangs centiles (100 = situation la plus défavorable).

    Le rang centile neutralise les valeurs extrêmes (ex. Grand Lomé) ; une composante manquante est exclue
    et les poids restants sont renormalisés (signalé par `composantes`).
    """
    w = {k: float(v) for k, v in (weights or DEFAULT_WEIGHTS).items() if k in SCORE_COMPONENTS}
    t = table.copy()
    for k, c in SCORE_COMPONENTS.items():
        v = t[c["col"]] * c["sens"]
        t[f"s_{k}"] = 100 * v.rank(pct=True, method="average")
        if v.notna().sum() <= 1:
            t[f"s_{k}"] = np.nan
    num = sum(t[f"s_{k}"].fillna(0) * wt for k, wt in w.items())
    den = sum(t[f"s_{k}"].notna() * wt for k, wt in w.items())
    t["score"] = np.where(den > 0, num / den.replace(0, np.nan), np.nan)
    t["composantes"] = [sum(1 for k in w if not math.isnan(r[f"s_{k}"]) and w[k] > 0) for _, r in t.iterrows()]
    t["priorite"] = pd.cut(t.score, [-1, 45, 65, 101], labels=["À surveiller", "Moyenne", "Élevée"]).astype(str)
    t.loc[t.score.isna(), "priorite"] = "Indéterminée"
    t["rang"] = t.score.rank(ascending=False, method="min")
    return t


# ── Alertes automatiques (3 maximum) ─────────────────────────────────────────────────────

def insights(safety: pd.DataFrame, immat_w: pd.DataFrame, permis_w: pd.DataFrame, reg: pd.DataFrame,
             pref: pd.DataFrame, years: tuple[int, int], region: str | None = None) -> list[dict]:
    y0, y1 = years
    out = []
    s = safety.loc[(safety.index >= y0) & (safety.index <= y1)]
    if len(s.deces.dropna()) >= 3:
        d = s.deces.dropna()
        ref = d.iloc[:-1].mean()
        ch = 100 * (d.iloc[-1] / ref - 1)
        peak_y = int(d.idxmax())
        out.append({"niveau": "danger" if ch > 0 else "ok",
                    "texte": f"{fr_num(d.iloc[-1])} décès routiers en {d.index[-1]}, soit {'+' if ch >= 0 else '−'}"
                             f"{fr_num(abs(ch))} % par rapport à la moyenne {d.index[0]}–{d.index[-2]} ({fr_num(ref)}) ; "
                             f"pic en {peak_y} ({fr_num(d.max())}).",
                    "source": "Séries nationales — décès"})
    iw = immat_w.loc[(immat_w.index >= y0) & (immat_w.index <= y1)]
    pw = permis_w.loc[(permis_w.index >= y0) & (permis_w.index <= y1)]
    if "Deux-roues" in iw and "A · Moto" in pw and len(pw.dropna(how="all")):
        common = iw["Deux-roues"].dropna().index.intersection(pw["A · Moto"].dropna().index)
        if len(common):
            y = int(common.max())
            share = 100 * iw.loc[y, "Deux-roues"] / iw.loc[y].sum()
            ratio = (100 * pw.loc[common, "A · Moto"] / iw.loc[common, "Deux-roues"]).median()
            span = f"{int(common.min())}–{y}" if len(common) > 1 else str(y)
            out.append({"niveau": "alerte",
                        "texte": f"Les deux-roues font {fr_num(share)} % des immatriculations en {y}, mais on délivre "
                                 f"en médiane {fr_num(ratio, 1)} permis A pour 100 deux-roues immatriculés ({span}).",
                        "source": "Immatriculations × permis par catégorie"})
    scope = reg if region is None else reg[reg.region == region]
    if len(scope) and scope.km_evalue.sum() > 0:
        km_m = scope.km_mauvais.sum()
        part = 100 * km_m / scope.km_evalue.sum()
        zero = pref if region is None else pref[pref.region == region]
        zero = zero[zero.ae_n == 0]
        where = "du réseau évalué" if region is None else f"du réseau évalué en {region}"
        txt = f"{fr_num(part)} % {where} est en mauvais état (2020)"
        if len(zero):
            pop = zero.population.sum()
            pop_txt = f"{fr_num(pop / 1e6, 1)} million(s)" if pop >= 1e6 else f"{fr_num(pop / 1e3)} milliers"
            txt += f" et {len(zero)} préfecture(s) ({pop_txt} d'hab.) n'ont aucune auto-école."
        else:
            txt += "."
        out.append({"niveau": "danger" if part >= 25 else "alerte", "texte": txt,
                    "source": "État du réseau 2020 × auto-écoles × RGPH-5"})
    return out[:3]
