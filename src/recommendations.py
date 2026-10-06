"""Recommandations générées par règles explicites. Chaque ligne cite l'indicateur observé qui la justifie.

Aucune recommandation n'est rédigée à la main : si les données changent, les recommandations changent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .cleaning import fr_num

PRIORITY_ORDER = {"Élevée": 0, "Moyenne": 1, "À surveiller": 2}
CATEGORIES = ["Urgence", "Formation", "Infrastructures", "Gouvernance des données"]


def _rec(cat, territoire, niveau, probleme, indicateur, action, priorite, source):
    return {"categorie": cat, "territoire": territoire, "niveau": niveau, "probleme": probleme,
            "indicateur": indicateur, "action": action, "priorite": priorite, "source": source}


def build_recommendations(d) -> pd.DataFrame:
    recs = []
    s = d.safety
    pref, reg = d.pref, d.reg
    imm = d.immat.pivot_table(index="annee", columns="famille", values="valeur", aggfunc="sum")
    per = d.permis.pivot_table(index="annee", columns="categorie", values="valeur", aggfunc="sum")

    # ── Urgence (séries nationales) ──────────────────────────────────────────────────────
    last = int(s.deces.dropna().index.max())
    base = s.loc[2017:2019, "deces"].mean()
    ch = 100 * (s.loc[last, "deces"] / base - 1)
    recs.append(_rec(
        "Urgence", "Togo", "National",
        f"Mortalité routière {'en hausse' if ch > 0 else 'en baisse'} par rapport à 2017–2019 : "
        f"{fr_num(s.loc[last, 'deces'])} décès en {last}",
        f"Décès {last} : {fr_num(s.loc[last, 'deces'])} contre {fr_num(base)} en moyenne 2017–2019 "
        f"({'+' if ch >= 0 else ''}{fr_num(ch)} %) ; {fr_num(s.loc[last, 'taux_deces_100k'], 1)} décès pour 100 000 hab.",
        "Intensifier les contrôles des comportements à risque (vitesse, alcool, casque) sur les axes nationaux ; "
        "fixer un objectif chiffré de baisse des décès suivi chaque année",
        "Élevée" if ch > 10 else "Moyenne", "Séries nationales (accidents, décès)"))
    acc = s.accidents.dropna()
    ch_acc = 100 * (acc.loc[last] / acc.loc[2017:2019].mean() - 1)
    recs.append(_rec(
        "Urgence", "Togo", "National",
        f"Accidents {'au-dessus' if ch_acc > 0 else 'en dessous'} de la référence 2017–2019 : "
        f"{fr_num(acc.loc[last])} en {last}",
        f"Accidents {last} : {fr_num(acc.loc[last])} ({'+' if ch_acc >= 0 else ''}{fr_num(ch_acc)} % par rapport à la "
        f"moyenne 2017–2019) ; {fr_num(s.loc[last, 'blesses'])} blessés",
        "Renforcer la chaîne de secours (délais d'intervention, postes avancés) sur les axes à fort trafic ; "
        "évaluer l'effet des contrôles par une mesure annuelle",
        "Élevée" if ch_acc > 20 else "Moyenne", "Séries nationales (accidents, blessés)"))
    # Deux-roues vs permis A
    common = imm["Deux-roues"].dropna().index.intersection(per["A · Moto"].dropna().index)
    y = int(common.max())
    share2r = 100 * imm.loc[y, "Deux-roues"] / imm.loc[y].sum()
    ratioA = 100 * per.loc[y, "A · Moto"] / imm.loc[y, "Deux-roues"]
    med_ratio = (100 * per["A · Moto"] / imm["Deux-roues"]).loc[2007:y].median()
    atypical = y in d.meta.get("flags", {}).get("A · Moto", {})
    recs.append(_rec(
        "Formation", "Togo", "National",
        "Motorisation dominée par les deux-roues, très peu de permis A délivrés",
        f"{y} : deux-roues = {fr_num(share2r)} % des immatriculations ; {fr_num(ratioA, 1)} permis A pour 100 deux-roues "
        f"immatriculés{' (valeur ' + str(y) + ' atypique, à confirmer)' if atypical else ''} ; médiane 2007–{y} : "
        f"{fr_num(med_ratio, 1)}",
        "Lancer une campagne nationale de formation et de permis moto (A) à coût réduit ; conditionner "
        "l'immatriculation d'un deux-roues à la présentation du permis A",
        "Élevée", "Immatriculations × permis par catégorie"))

    # ── Formation (territorial) ──────────────────────────────────────────────────────────
    nat_rate = pref.ae_n.sum() / pref.population.sum() * 1e5
    zero = pref[pref.ae_n == 0].sort_values("population", ascending=False)
    for r in zero.itertuples():
        prio = "Élevée" if r.population >= 150_000 else ("Moyenne" if r.population >= 80_000 else "À surveiller")
        recs.append(_rec(
            "Formation", f"{r.prefecture} ({r.region})", "Préfecture",
            "Aucune auto-école recensée",
            f"0 auto-école pour {fr_num(r.population)} habitants (moyenne nationale : {fr_num(nat_rate, 1)} pour "
            "100 000 hab.)",
            "Soutenir l'ouverture d'une auto-école ou d'une antenne agréée ; organiser des sessions mobiles de "
            "formation et d'examen", prio, "Auto-écoles × RGPH-5"))
    low = pref[(pref.ae_n > 0) & (pref.ae_100k < 1)].sort_values("ae_100k")
    for r in low.itertuples():
        recs.append(_rec(
            "Formation", f"{r.prefecture} ({r.region})", "Préfecture",
            "Offre de formation très faible",
            f"{r.ae_n} auto-école(s) pour {fr_num(r.population)} hab. ({fr_num(r.ae_100k, 2)} pour 100 000 hab. ; "
            f"1 pour {fr_num(r.hab_par_ae)} hab.)",
            "Accompagner l'installation d'une auto-école supplémentaire (agrément, accès au foncier)",
            "Moyenne" if r.population >= 150_000 else "À surveiller", "Auto-écoles × RGPH-5"))
    for r in reg[reg.part_non_agreees >= 50].sort_values("part_non_agreees", ascending=False).itertuples():
        recs.append(_rec(
            "Formation", r.region, "Région",
            "Majorité d'auto-écoles non agréées",
            f"{fr_num(r.part_non_agreees)} % des {r.ae_n} auto-écoles recensées ne sont pas agréées",
            "Programme d'accompagnement à l'agrément et contrôle de la qualité de la formation",
            "Moyenne" if r.part_non_agreees >= 60 else "À surveiller", "Auto-écoles (statut d'agrément)"))
    lome = pref[pref.prefecture_key.isin(["GOLFE", "AGOE NYIVE"])]
    rest = pref[(pref.region == "Maritime") & ~pref.prefecture_key.isin(["GOLFE", "AGOE NYIVE"])]
    if len(lome) and len(rest):
        r_lome = lome.ae_n.sum() / lome.population.sum() * 1e5
        r_rest = rest.ae_n.sum() / rest.population.sum() * 1e5
        recs.append(_rec(
            "Formation", "Maritime hors Grand Lomé", "Région",
            "Concentration de l'offre de formation dans le Grand Lomé",
            f"Grand Lomé : {fr_num(r_lome, 1)} auto-écoles pour 100 000 hab. ; reste de la Maritime : {fr_num(r_rest, 1)} "
            f"({rest.ae_n.sum()} auto-écoles pour {fr_num(rest.population.sum())} hab.)",
            "Inciter l'ouverture d'antennes des auto-écoles de Lomé dans les préfectures de la Maritime",
            "Moyenne", "Auto-écoles × RGPH-5"))

    # ── Infrastructures ──────────────────────────────────────────────────────────────────
    tr = d.troncons.copy()
    tr["part_mauvais"] = 100 * tr.Mauvais / tr.Total
    worst = tr[tr.Mauvais >= 20].sort_values("Mauvais", ascending=False)
    for r in worst.itertuples():
        recs.append(_rec(
            "Infrastructures", f"{r.troncon} ({r.region or 'région non attribuée'})", "Tronçon",
            "Tronçon largement dégradé",
            f"{fr_num(r.Mauvais, 1)} km en mauvais état sur {fr_num(r.Total, 1)} km ({fr_num(r.part_mauvais)} %) — 2020",
            "Inscrire en entretien prioritaire ; signaliser les sections dégradées en attendant les travaux",
            "Élevée" if r.part_mauvais >= 50 else "Moyenne", "État du réseau routier 2020"))
    for r in reg.sort_values("part_mauvais", ascending=False).itertuples():
        if r.part_mauvais >= 20:
            recs.append(_rec(
                "Infrastructures", r.region, "Région",
                "Part élevée du réseau en mauvais état",
                f"{fr_num(r.part_mauvais)} % du réseau évalué en mauvais état ({fr_num(r.km_mauvais)} km) ; "
                f"{fr_num(r.km_mauvais_100k, 1)} km dégradés pour 100 000 hab.",
                "Programme régional d'entretien prioritaire, en commençant par les tronçons les plus dégradés",
                "Élevée" if r.part_mauvais >= 25 else "Moyenne", "État du réseau routier 2020 × RGPH-5"))
    works = tr[tr.Travaux > 0].sort_values("Travaux", ascending=False)
    if len(works):
        top = works.head(3)
        recs.append(_rec(
            "Infrastructures", "Togo", "National",
            "Linéaire important en travaux à suivre",
            f"{fr_num(works.Travaux.sum())} km en travaux sur {len(works)} tronçons en 2020, dont "
            + ", ".join(f"{t.troncon} ({fr_num(t.Travaux)} km)" for t in top.itertuples()),
            "Publier un suivi d'avancement des chantiers (date de fin, km livrés) et sécuriser les déviations",
            "Moyenne", "État du réseau routier 2020"))
    low_dens = pref[(pref.densite_km_1000km2 < 25)].sort_values("densite_km_1000km2")
    for r in low_dens.itertuples():
        recs.append(_rec(
            "Infrastructures", f"{r.prefecture} ({r.region})", "Préfecture",
            "Desserte en routes classées insuffisante",
            f"{fr_num(r.densite_km_1000km2, 1)} km de routes classées pour 1 000 km² (médiane des préfectures : "
            f"{fr_num(pref.densite_km_1000km2.median(), 1)})",
            "Étudier le désenclavement (classement ou aménagement de pistes vers les axes nationaux)",
            "Moyenne" if r.population >= 100_000 else "À surveiller", "Routes classées (géométries) × OCHA"))

    # ── Gouvernance des données ──────────────────────────────────────────────────────────
    nogeo = tr[~tr.geolocalise]
    an = d.anomalies
    atyp = an[an.type.isin(["Valeur atypique", "Rupture de niveau"])]
    gov = [
        ("Accidents non territorialisés",
         "Accidents, décès et blessés publiés uniquement à l'échelle nationale (2010–2022), sans lieu ni date fine",
         "Géocoder chaque accident (coordonnées, tronçon, date, heure, usagers) pour identifier les points noirs et "
         "les périodes à risque", "Élevée"),
        ("Pas de dénominateur « parc en circulation »",
         "Immatriculations publiées en flux annuel ; le parc roulant n'est pas disponible",
         "Publier le parc en circulation par catégorie et par région pour calculer des taux par véhicule", "Élevée"),
        ("État du réseau figé en 2020 et non géolocalisé",
         "Une seule photographie (2020), par tronçon sans localisation des sections dégradées ; "
         f"{len(nogeo)} tronçon(s) ({fr_num(nogeo.Total.sum())} km) sans géométrie appariable",
         "Relevé annuel de l'état par section géolocalisée (PK début / PK fin) avec le même identifiant que la base "
         "des routes classées", "Moyenne"),
        ("Champs du dictionnaire absents des exports",
         "Praticabilité, zone inondable, date de collecte (routes) ; date de création, reconnaissance (auto-écoles)",
         "Exporter l'ensemble des champs documentés dans le dictionnaire", "Moyenne"),
        ("Valeurs atypiques et lacunes non expliquées",
         f"{len(an)} anomalies tracées, dont {len(atyp)} valeurs atypiques ou ruptures de série "
         f"({', '.join(atyp.element.head(4))}…), une année codée 0 au lieu de manquante et un libellé de taux erroné",
         "Joindre une note méthodologique à chaque publication et corriger les libellés", "À surveiller"),
    ]
    for prob, ind, act, prio in gov:
        recs.append(_rec("Gouvernance des données", "Togo", "National", prob, ind, act, prio, "Contrôles qualité"))

    df = pd.DataFrame(recs)
    df["ordre"] = df.priorite.map(PRIORITY_ORDER)
    df["cat_ordre"] = df.categorie.map({c: i for i, c in enumerate(CATEGORIES)})
    df = df.sort_values(["ordre", "cat_ordre"]).drop(columns=["ordre", "cat_ordre"]).reset_index(drop=True)
    df.insert(0, "id", [f"R{i + 1:02d}" for i in range(len(df))])
    return df
