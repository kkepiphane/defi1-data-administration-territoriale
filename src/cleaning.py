"""Nettoyage et harmonisation. Chaque transformation, contrôle et anomalie est consigné dans le journal.

Principe : les valeurs observées ne sont jamais modifiées. Les corrections portent uniquement sur des
libellés (coquilles) ou sur le codage des valeurs manquantes, et chacune est tracée.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import (NATIONAL_MAP, PERMIS_MAP, POP_LABEL_FIXES, POP_REGION_MAP, REGIONS, VEHICULE_MAP)


# ── Journal de traçabilité ───────────────────────────────────────────────────────────────

@dataclass
class Journal:
    steps: list = field(default_factory=list)
    controls: list = field(default_factory=list)
    anomalies: list = field(default_factory=list)

    def log(self, source: str, operation: str, detail: str, lignes: int | None = None):
        self.steps.append({"n": len(self.steps) + 1, "source": source, "operation": operation,
                           "detail": detail, "lignes_concernees": lignes})

    def control(self, source: str, controle: str, resultat: str, conforme: bool | None):
        statut = "Conforme" if conforme else ("Information" if conforme is None else "Écart")
        self.controls.append({"source": source, "controle": controle, "resultat": resultat, "statut": statut})

    def anomaly(self, source: str, element: str, type_: str, detail: str, traitement: str):
        self.anomalies.append({"source": source, "element": element, "type": type_, "detail": detail,
                               "traitement": traitement})

    def frames(self) -> dict[str, pd.DataFrame]:
        return {"journal": pd.DataFrame(self.steps), "controles": pd.DataFrame(self.controls),
                "anomalies": pd.DataFrame(self.anomalies)}


# ── Outils ───────────────────────────────────────────────────────────────────────────────

def strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()


def key(name) -> str:
    """Clé géographique harmonisée : majuscules, sans accents, tirets et apostrophes → espace."""
    if name is None or (isinstance(name, float) and math.isnan(name)):
        return ""
    s = strip_accents(name).upper()
    s = re.sub(r"[-'’_/]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fr_num(value, decimals: int = 0) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "—"
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")


FLAGS: dict[str, dict[int, str]] = {}  # série → {année: type d'anomalie}, lu par les graphiques


def flag_series(j: Journal, source: str, label: str, s: pd.Series, floor: float = 200,
                factor: float = 1.8) -> list[int]:
    """Repère les valeurs atypiques d'une série annuelle sans les modifier.

    - valeur atypique (pic ou creux) : écart d'un facteur ≥ 1,8, dans le même sens, à la médiane des deux années
      précédentes ET à celle des deux années suivantes (un seul côté aux extrémités de la série). Procédure
      itérative : la valeur la plus extrême est signalée puis écartée avant de réexaminer les autres, pour
      qu'un pic n'en fasse pas apparaître un faux à côté de lui ;
    - rupture de niveau : variation d'un facteur ≥ 3 entre deux années consécutives non atypiques.
    Les valeurs de faible effectif (< `floor`) sont ignorées pour éviter les faux positifs.
    """
    s = s.dropna().sort_index()
    s = s[s > 0]
    kept = list(s.index)
    found: dict[int, tuple] = {}
    thr = math.log(factor)
    while True:
        best = None
        for i, y in enumerate(kept):
            v = s.loc[y]
            left = [s.loc[k] for k in kept[max(0, i - 2):i]]
            right = [s.loc[k] for k in kept[i + 1:i + 3]]
            sides = [float(np.median(x)) for x in (left, right) if len(x) == 2]
            if not sides or v < floor or min(sides) < floor:
                continue
            devs = [math.log(v / m) for m in sides]
            if all(d >= thr for d in devs) or all(d <= -thr for d in devs):
                strength = min(abs(d) for d in devs)
                if best is None or strength > best[0]:
                    best = (strength, y, float(np.median(left + right)))
        if best is None:
            break
        _, y, med = best
        found[y] = ("Valeur atypique", med)
        kept.remove(y)
    for a, b in zip(kept, kept[1:]):
        va, vb = s.loc[a], s.loc[b]
        if va >= floor and vb >= floor and abs(math.log(vb / va)) >= math.log(3):
            found[b] = ("Rupture de niveau", va, a)
    for y in sorted(found):
        info = found[y]
        v = s.loc[y]
        if info[0] == "Valeur atypique":
            j.anomaly(source, f"{label} — {y}", "Valeur atypique",
                      f"{fr_num(v)} contre {fr_num(info[1])} en médiane sur les années voisines "
                      f"(× {fr_num(v / info[1], 1)})",
                      "Valeur conservée et signalée sur les graphiques ; à confirmer auprès du producteur")
        else:
            j.anomaly(source, f"{label} — {y}", "Rupture de niveau",
                      f"{fr_num(info[1])} en {info[2]} → {fr_num(v)} en {y} (× {fr_num(v / info[1], 1)})",
                      "Valeur conservée ; changement probable de périmètre ou de méthode de collecte")
        FLAGS.setdefault(label, {})[int(y)] = info[0]
    return sorted(found)


def _numeric(df: pd.DataFrame, j: Journal, source: str) -> pd.DataFrame:
    df = df.copy()
    df["annee"] = pd.to_numeric(df["Date"], errors="coerce")
    df["valeur"] = pd.to_numeric(df["Value"], errors="coerce")
    bad_year = df["annee"].isna() | (df["annee"] < 1900) | (df["annee"] > 2030)
    bad_val = df["valeur"].isna()
    j.control(source, "Dates valides (années 1900–2030)", f"{(~bad_year).sum()} / {len(df)} lignes", not bad_year.any())
    j.control(source, "Valeurs numériques", f"{(~bad_val).sum()} / {len(df)} lignes", not bad_val.any())
    df = df[~bad_year & ~bad_val]
    df["annee"] = df["annee"].astype(int)
    return df


# ── Immatriculations ─────────────────────────────────────────────────────────────────────

def clean_immatriculations(raw: pd.DataFrame, j: Journal) -> pd.DataFrame:
    src = "Immatriculations"
    df = _numeric(raw.rename(columns={"types-de-vehicule": "type_source"}), j, src)
    dup = df.duplicated(["type_source", "annee"]).sum()
    j.control(src, "Doublons (type × année)", f"{dup} doublon(s)", dup == 0)
    total = df[df.type_source == "Total"].set_index("annee")["valeur"]
    det = df[df.type_source != "Total"].copy()
    unknown = sorted(set(det.type_source) - set(VEHICULE_MAP))
    if unknown:
        j.anomaly(src, ", ".join(unknown), "Libellé inconnu", "Type de véhicule non référencé", "Exclu")
        det = det[det.type_source.isin(VEHICULE_MAP)]
    det["type"] = det.type_source.map(lambda s: VEHICULE_MAP[s][0])
    det["famille"] = det.type_source.map(lambda s: VEHICULE_MAP[s][1])
    j.log(src, "Harmonisation des types de véhicules",
          "« Voitues » → « Voitures » (coquille) ; « Tracteurs » → « Tracteurs routiers » ; "
          "« 2 roues et assimilées » → « Deux-roues » ; 7 types regroupés en 5 familles "
          "(Deux-roues, Voitures, Utilitaires légers, Poids lourds, Transport collectif)", len(det))
    sums = det.groupby("annee")["valeur"].sum()
    gap = (sums - total.reindex(sums.index)).abs()
    j.control(src, "Total publié = somme des 7 types", f"{int((gap < 0.5).sum())} / {len(gap)} années conformes",
              bool((gap < 0.5).all()))
    j.log(src, "Retrait de la ligne « Total »", "Total recalculé à partir des types retenus par les filtres", len(total))
    years = sorted(det.annee.unique())
    missing_years = sorted(set(range(years[0], years[-1] + 1)) - set(years))
    j.control(src, "Continuité de la série", f"{years[0]}–{years[-1]}, années manquantes : "
              f"{', '.join(map(str, missing_years)) or 'aucune'}", not missing_years)
    j.anomaly(src, "Nature de la série", "Ambiguïté de définition",
              "Libellé source « parc automobile immatriculé » ; les valeurs annuelles fluctuent (ex. 1993 : 4 349 "
              "contre 7 250 en 1992), ce qui correspond à des flux d'immatriculations et non à un stock cumulé",
              "Série traitée comme immatriculations de l'année (flux) ; aucun parc en circulation n'est estimé")
    for t, g in det.groupby("type"):
        flag_series(j, src, t, g.set_index("annee")["valeur"])
    return det[["annee", "type", "famille", "valeur"]].sort_values(["annee", "type"]).reset_index(drop=True)


def clean_immat_detail(raw: pd.DataFrame, immat: pd.DataFrame, j: Journal) -> pd.DataFrame:
    src = "Immatriculations (détail)"
    df = _numeric(raw.rename(columns={"automobile": "type_source"}), j, src)
    w = df.pivot_table(index="annee", columns="type_source", values="valeur", aggfunc="sum")
    deux = immat[immat.famille == "Deux-roues"].set_index("annee")["valeur"]
    cyl = w[["Engins à 2 R de 50 à 125cm3", "Engins à 2 R + de 125cm3"]]
    ok = ((cyl.sum(axis=1) - deux.reindex(cyl.index)).abs() < 0.5) & \
         ((w["Total 2 Roues"] - deux.reindex(w.index)).abs() < 0.5)
    j.control(src, "Deux-roues : 50–125 cm³ + > 125 cm³ = total deux-roues du fichier principal",
              f"{int(ok.sum())} / {len(ok)} années conformes", bool(ok.all()))
    voit = immat[immat.type == "Voitures"].set_index("annee")["valeur"]
    okv = (w["Voitures"] - voit.reindex(w.index)).abs() < 0.5
    j.control(src, "Voitures identiques au fichier principal", f"{int(okv.sum())} / {len(okv)} années", bool(okv.all()))
    out = cyl.rename(columns={"Engins à 2 R de 50 à 125cm3": "50 à 125 cm³",
                              "Engins à 2 R + de 125cm3": "Plus de 125 cm³"}).reset_index()
    out = out.melt(id_vars="annee", var_name="cylindree", value_name="valeur")
    j.log(src, "Extraction de la ventilation des deux-roues par cylindrée",
          "Seule information absente du fichier principal ; les autres lignes sont des doublons contrôlés", len(out))
    return out


# ── Séries nationales ────────────────────────────────────────────────────────────────────

def clean_national(raw: pd.DataFrame, j: Journal, pop_2022: float) -> pd.DataFrame:
    src = "Séries nationales"
    df = _numeric(raw, j, src)
    unknown = sorted(set(df.indicateur) - set(NATIONAL_MAP))
    for u in unknown:
        j.anomaly(src, u, "Indicateur non référencé", "Libellé absent de la table de correspondance", "Exclu")
    df = df[df.indicateur.isin(NATIONAL_MAP)].copy()
    df["code"] = df.indicateur.map(lambda s: NATIONAL_MAP[s][0])
    dup = df.duplicated(["code", "annee"]).sum()
    j.control(src, "Doublons (indicateur × année)", f"{dup} doublon(s)", dup == 0)
    w = df.pivot_table(index="annee", columns="code", values="valeur", aggfunc="first").sort_index()
    j.log(src, "Codification des 13 indicateurs", "Libellés longs remplacés par des codes stables (accidents, deces, "
          "blesses, immat_4r…) ; table de correspondance dans src/config.py", len(df))

    # Le « taux d'accidents mortels » publié est en réalité le taux de TOUS les accidents.
    t = w[["accidents", "deces", "taux_accidents_publie"]].dropna()
    implied = t["accidents"] / t["taux_accidents_publie"] * 1e5
    if 2022 in implied.index:
        ecart = abs(implied.loc[2022] / pop_2022 - 1)
        taux_deces_2022 = t.loc[2022, "deces"] / pop_2022 * 1e5
        j.control(src, "Libellé « Accidents mortels /100.000 hab » : vérification du numérateur",
                  f"2022 : accidents / taux publié × 100 000 = {fr_num(implied.loc[2022])} hab., soit "
                  f"{fr_num(100 * ecart, 2)} % d'écart avec le RGPH-5 ({fr_num(pop_2022)}) ; avec les décès, le taux "
                  f"serait {fr_num(taux_deces_2022, 1)} et non {fr_num(t.loc[2022, 'taux_accidents_publie'], 1)}",
                  ecart < 0.01)
        j.anomaly(src, "Accidents mortels /100.000 hab", "Libellé erroné",
                  "Le taux publié rapporte l'ensemble des accidents (et non les seuls accidents mortels) à la "
                  "population", "Renommé « Accidents pour 100 000 habitants » ; valeurs inchangées")
        j.log(src, "Correction du libellé du taux publié", "« Accidents mortels /100.000 hab » → "
              "« Accidents pour 100 000 habitants » (démonstration par le calcul, voir contrôles)", len(t))
    w["pop_implicite"] = implied
    j.log(src, "Dénominateur de population annuel", "Population implicite = accidents ÷ taux publié × 100 000 "
          "(seule série annuelle de population disponible) ; recoupée avec le RGPH-5 en 2022", len(implied))
    rounded = [y for y, v in t["taux_accidents_publie"].items() if float(v).is_integer()]
    for y in rounded:
        j.anomaly(src, f"Taux publié {y}", "Valeur arrondie",
                  f"Taux publié entier ({fr_num(t.loc[y, 'taux_accidents_publie'])}) : population implicite "
                  f"{fr_num(implied.loc[y])} hab., quasi identique à l'année suivante",
                  "Taux de décès de cette année calculé avec ce dénominateur ; précision réduite signalée")
    for code, label in [("accidents", "Accidents"), ("deces", "Décès"), ("blesses", "Blessés")]:
        if code in w:
            flag_series(j, src, label, w[code])
    acc = w["accidents"].dropna()
    j.control(src, "Couverture accidents / décès / blessés", f"{acc.index.min()}–{acc.index.max()} "
              f"({len(acc)} années), échelle nationale uniquement", None)
    return w


# ── Permis de conduire ───────────────────────────────────────────────────────────────────

def clean_permis(raw: pd.DataFrame, national: pd.DataFrame, j: Journal) -> pd.DataFrame:
    src = "Permis de conduire"
    df = _numeric(raw.rename(columns={"categories-de-permis": "cat_source"}), j, src)
    total = df[df.cat_source == "Total"].set_index("annee")["valeur"]
    det = df[df.cat_source != "Total"].copy()
    det["categorie"] = det.cat_source.map(PERMIS_MAP)
    j.log(src, "Harmonisation des catégories", "« Voiture légèr (B) » → « B · Véhicule léger » (coquille) ; "
          "codes A à F placés en tête de libellé", len(det))
    sums = det.groupby("annee")["valeur"].sum()
    gap = (sums - total.reindex(sums.index)).abs()
    j.control(src, "Total publié = somme des 6 catégories", f"{int((gap < 0.5).sum())} / {len(gap)} années conformes",
              bool((gap < 0.5).all()))
    empty_years = [y for y, v in total.items() if v == 0 and y not in sums.index]
    for y in empty_years:
        j.anomaly(src, f"Total {y}", "Manquant codé en zéro",
                  f"Total = 0 sans aucune ligne par catégorie ; l'année {y} est aussi absente de la série nationale",
                  "Recodé en valeur manquante (exclu des calculs, affiché comme lacune)")
        j.log(src, f"Recodage {y}", "Zéro transformé en valeur manquante", 1)
    if "permis_total" in national:
        nat = national["permis_total"].dropna()
        okn = (nat - sums.reindex(nat.index)).abs() < 0.5
        j.control(src, "Total par catégories = série nationale « permis délivrés »",
                  f"{int(okn.sum())} / {len(okn)} années conformes", bool(okn.all()))
    zeros_f = det[(det.categorie == "F · Véhicule spécial") & (det.valeur == 0)].annee.tolist()
    if zeros_f:
        j.anomaly(src, "F · Véhicule spécial", "Zéros observés",
                  f"Aucun permis F de {min(zeros_f)} à {max(zeros_f)}", "Zéros conservés (valeurs déclarées)")
    for c, g in det.groupby("categorie"):
        flag_series(j, src, c, g.set_index("annee")["valeur"])
    return det[["annee", "categorie", "valeur"]].sort_values(["annee", "categorie"]).reset_index(drop=True)


# ── Population (RGPH-5, 2022) ────────────────────────────────────────────────────────────

def clean_population(raw: pd.DataFrame, j: Journal) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """Reconstitue la hiérarchie pays → région → préfecture → commune → canton à partir de l'ordre des lignes."""
    src = "Population"
    df = raw.rename(columns={"découpage-administratif": "libelle_source"}).copy()
    df["population"] = pd.to_numeric(df["Value"], errors="coerce")
    j.control(src, "Valeurs numériques", f"{df.population.notna().sum()} / {len(df)}", df.population.notna().all())
    j.control(src, "Millésime", f"{', '.join(sorted(df.Date.unique()))} (une seule année)", None)
    labels = [POP_LABEL_FIXES.get(s.strip(), s.strip()) for s in df.libelle_source]
    for s, fixed in POP_LABEL_FIXES.items():
        if s in set(df.libelle_source):
            j.log(src, "Correction de libellé", f"« {s} » → « {fixed} »", 1)

    rows = []
    region = pref = None
    last_commune_no = 0
    for i, name in enumerate(labels):
        nxt = labels[i + 1] if i + 1 < len(labels) else ""
        level = "canton"
        if i == 0 and name == "TOGO":
            level = "pays"
        elif name in POP_REGION_MAP:
            level, region, pref = "région", name, None
        elif re.match(rf"^{re.escape(name)}\s?\d", nxt):
            level, pref, last_commune_no = "préfecture", name, 0
        elif pref and re.match(rf"^{re.escape(pref)}\s?(\d+)", name):
            level = "commune"
            no = int(re.match(rf"^{re.escape(pref)}\s?(\d+)", name).group(1))
            if no <= last_commune_no:  # libellé de commune répété (ex. deux « EST-MONO 1 »)
                fixed = f"{pref} {last_commune_no + 1}"
                j.anomaly(src, name, "Libellé dupliqué", f"Deuxième commune « {name} » dans la préfecture {pref}",
                          f"Renommée « {fixed} » (somme des communes = population de la préfecture)")
                name, no = fixed, last_commune_no + 1
            last_commune_no = no
        rows.append({"ordre": i, "niveau": level, "libelle_source": df.libelle_source.iloc[i], "libelle": name,
                     "region_source": region if level != "pays" else None,
                     "prefecture_source": pref if level in ("commune", "canton", "préfecture") else None,
                     "population": df.population.iloc[i]})
    units = pd.DataFrame(rows)
    # commune de rattachement des cantons
    commune = None
    comm = []
    for r in units.itertuples():
        if r.niveau in ("pays", "région", "préfecture"):
            commune = None
        if r.niveau == "commune":
            commune = r.libelle
        comm.append(commune if r.niveau in ("commune", "canton") else None)
    units["commune_source"] = comm
    units["region"] = units.region_source.map(POP_REGION_MAP)
    units["prefecture_key"] = units.prefecture_source.map(key)

    counts = units.niveau.value_counts()
    j.log(src, "Reconstitution de la hiérarchie administrative",
          f"{counts.get('région', 0)} régions (dont le District autonome du Grand Lomé), "
          f"{counts.get('préfecture', 0)} préfectures, {counts.get('commune', 0)} communes, "
          f"{counts.get('canton', 0)} cantons — détectés par l'ordre des lignes et la numérotation des communes",
          len(units))

    # Contrôles de sommes à chaque niveau
    total = units.loc[units.niveau == "pays", "population"].iloc[0]
    reg = units[units.niveau == "région"]
    j.control(src, "Somme des 6 régions = Togo", f"{fr_num(reg.population.sum())} / {fr_num(total)}",
              abs(reg.population.sum() - total) < 1)
    pref_rows = units[units.niveau == "préfecture"]
    by_reg = pref_rows.groupby("region_source").population.sum()
    bad = [r for r, v in by_reg.items() if abs(v - reg.set_index("libelle").population[r]) >= 1]
    j.control(src, "Somme des préfectures = région", f"{len(by_reg) - len(bad)} / {len(by_reg)} régions conformes"
              + (f" (écarts : {', '.join(bad)})" if bad else ""), not bad)
    comm_rows = units[units.niveau == "commune"]
    by_pref = comm_rows.groupby("prefecture_source").population.sum()
    bad = [p for p, v in by_pref.items() if abs(v - pref_rows.set_index("libelle").population[p]) >= 1]
    j.control(src, "Somme des communes = préfecture", f"{len(by_pref) - len(bad)} / {len(by_pref)} préfectures "
              f"conformes" + (f" (écarts : {', '.join(bad)})" if bad else ""), not bad)
    cant = units[units.niveau == "canton"]
    by_comm = cant.groupby(["prefecture_source", "commune_source"]).population.sum()
    comm_idx = comm_rows.set_index(["prefecture_source", "libelle"]).population
    bad = [f"{c}" for (p, c), v in by_comm.items() if abs(v - comm_idx.get((p, c), np.nan)) >= 1]
    j.control(src, "Somme des cantons = commune", f"{len(by_comm) - len(bad)} / {len(by_comm)} communes conformes"
              + (f" (écarts : {', '.join(bad[:6])})" if bad else ""), not bad)
    dup_comm = cant.duplicated(["prefecture_source", "commune_source", "libelle"]).sum()
    j.control(src, "Cantons en double dans une même commune", f"{dup_comm}", dup_comm == 0)
    homo = cant[cant.duplicated("libelle", keep=False)].libelle.unique()
    j.control(src, "Cantons homonymes (communes différentes)", f"{len(homo)} libellé(s) : {', '.join(sorted(homo))} — "
              "distingués par leur commune de rattachement", None)
    j.log(src, "Rattachement du Grand Lomé (DAGL) à la région Maritime",
          "Les bases routes et auto-écoles rangent Golfe et Agoè-Nyivé en Maritime ; la population DAGL "
          f"({fr_num(reg.set_index('libelle').population.get('DAGL', 0))} hab.) est donc agrégée à Maritime au niveau "
          "régional, et reste distincte au niveau préfectoral", 2)

    prefs = pref_rows[["libelle", "prefecture_key", "region_source", "region", "population"]].rename(
        columns={"libelle": "prefecture_source"}).reset_index(drop=True)
    return units, prefs, float(total)


# ── Auto-écoles ──────────────────────────────────────────────────────────────────────────

AGREMENT_MAP = {"Agréée": "Agréée", "Antenne agréée": "Antenne agréée", "Non agréée": "Non agréée",
                "Néant": "Non renseigné"}
MISSING_TOKENS = {"nsp", "néant", "neant", "aucun", "aucune", "rien", "-", ""}


def _point(wkt: str):
    m = re.match(r"POINT\s*\(\s*([-\d.eE]+)\s+([-\d.eE]+)\s*\)", str(wkt))
    return (float(m.group(1)), float(m.group(2))) if m else (np.nan, np.nan)


def clean_auto_ecoles(raw: pd.DataFrame, pref_keys: set[str], j: Journal) -> pd.DataFrame:
    src = "Auto-écoles"
    df = raw.copy()
    j.control(src, "Valeurs manquantes (12 champs)", f"{int(df.isna().sum().sum())} cellule(s) vide(s)",
              not df.isna().any().any())
    dup_id = df.FID.duplicated().sum()
    j.control(src, "Identifiants uniques", f"{dup_id} doublon(s) d'identifiant", dup_id == 0)
    xy = df.geometry.map(_point)
    df["lon"], df["lat"] = xy.str[0], xy.str[1]
    bad_geom = df.lon.isna().sum()
    in_box = df.lon.between(-0.25, 1.95) & df.lat.between(5.9, 11.2)
    j.control(src, "Coordonnées valides et situées dans l'emprise du Togo",
              f"{int(in_box.sum())} / {len(df)} points", bool(in_box.all()) and bad_geom == 0)
    same_xy = df.duplicated(["lon", "lat"], keep=False)
    if same_xy.any():
        j.anomaly(src, f"{int(same_xy.sum())} établissements", "Coordonnées identiques",
                  "Plusieurs établissements partagent exactement le même point", "Conservés (adresses distinctes)")
    dup_name = df.duplicated(["nom_etablissement", "nom_localite"]).sum()
    j.control(src, "Doublons nom × localité", f"{dup_name} doublon(s)", dup_name == 0)

    df["agrement"] = df.agregation.map(AGREMENT_MAP).fillna("Non renseigné")
    n_neant = int((df.agregation == "Néant").sum())
    j.log(src, "Harmonisation du statut d'agrément", f"« Néant » → « Non renseigné » ({n_neant} ligne(s)) ; "
          "« Agréée » et « Antenne agréée » regroupées sous « agréée » pour les ratios", len(df))
    df["agree"] = df.agrement.isin(["Agréée", "Antenne agréée"])
    addr_missing = df.adresse_etablissement.str.strip().str.lower().isin(MISSING_TOKENS)
    df["adresse"] = df.adresse_etablissement.where(~addr_missing)
    j.log(src, "Codage des adresses manquantes", "« Nsp », « Néant », « Aucun(e) » → valeur manquante",
          int(addr_missing.sum()))
    jours = df.journee_ouverture.str.findall(r"lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche")
    df["jours_ouverture"] = jours.map(lambda x: len(set(x)) if x else np.nan)
    j.log(src, "Normalisation des jours d'ouverture", "Listes {lundi,…} de formats variables → nombre de jours ; "
          "« Nsp » → manquant", int(df.jours_ouverture.isna().sum()))

    df["region"] = df.region_nom_bdd.str.strip()
    bad_reg = ~df.region.isin(REGIONS)
    j.control(src, "Régions reconnues", f"{int((~bad_reg).sum())} / {len(df)}", not bad_reg.any())
    df["prefecture_key"] = df.prefecture_nom_bdd.map(key)
    unk = sorted(set(df.prefecture_key) - pref_keys)
    j.control(src, "Préfectures rattachées à la nomenclature population", f"{len(set(df.prefecture_key)) - len(unk)} / "
              f"{df.prefecture_key.nunique()} préfectures" + (f" (inconnues : {', '.join(unk)})" if unk else ""),
              not unk)
    df["id"] = df.FID.str.split(".fid-").str[-1]
    out = df.rename(columns={"prefecture_nom_bdd": "prefecture", "commune_nom_bdd": "commune",
                             "canton_nom_bdd": "canton", "nom_localite": "localite", "nom_etablissement": "nom"})
    return out[["id", "region", "prefecture_key", "prefecture", "commune", "canton", "localite", "nom", "agrement",
                "agree", "adresse", "jours_ouverture", "lon", "lat"]]


# ── Routes classées (géométries) ─────────────────────────────────────────────────────────

RECOUVREMENT_FIX = {"Terre amenagée": "Terre aménagée", "Beton": "Béton", "Gravier non amenagé": "Gravier non aménagé",
                    "Gravier amenagé": "Gravier aménagé"}
REVETU = {"Bitume", "Béton", "Pavé"}


def clean_routes_geo(raw: pd.DataFrame, pref_keys: set[str], j: Journal) -> pd.DataFrame:
    src = "Routes classées (géométries)"
    df = raw.copy()
    j.control(src, "Identifiants uniques", f"{int(df.FID.duplicated().sum())} doublon(s)", not df.FID.duplicated().any())
    dup_geom = df.geometry.duplicated().sum()
    j.control(src, "Géométries dupliquées", f"{dup_geom} segment(s) strictement identiques", dup_geom == 0)
    df["route_recouvrement"] = df.route_recouvrement.replace(RECOUVREMENT_FIX)
    j.log(src, "Harmonisation des revêtements", "Accents restaurés (« amenagée » → « aménagée », « Beton » → « Béton ») ; "
          "regroupement Revêtu (bitume, béton, pavé) / Non revêtu (terre, gravier)", len(df))
    df["revetement"] = np.where(df.route_recouvrement.isin(REVETU), "Revêtu", "Non revêtu")
    incoh = ((df.route_type == "Route nationale revêtue") & (df.revetement == "Non revêtu")) | \
            ((df.route_type == "Route nationale non revêtue") & (df.revetement == "Revêtu"))
    if incoh.any():
        j.anomaly(src, f"{int(incoh.sum())} segments", "Incohérence type / revêtement",
                  "Type « revêtue » avec revêtement en terre ou gravier, ou l'inverse",
                  "Conservés ; le type de route déclaré fait foi pour les agrégats par catégorie")
    j.control(src, "Cohérence type de route / revêtement", f"{int((~incoh).sum())} / {len(df)} segments cohérents",
              not incoh.any())
    df["voies_nbr"] = pd.to_numeric(df.voies_nbr, errors="coerce")
    zero = (df.voies_nbr == 0).sum()
    if zero:
        j.anomaly(src, f"{zero} segments", "Nombre de voies = 0", "Valeur impossible pour une route ouverte",
                  "Recodé en valeur manquante")
        df.loc[df.voies_nbr == 0, "voies_nbr"] = np.nan
    no_name = df.route_nom.isna().sum()
    if no_name:
        j.anomaly(src, f"{no_name} segments", "Nom de route manquant", "Champ route_nom vide",
                  "Libellé « Route sans nom » ; segment conservé, non rattachable à un tronçon évalué")
    df["route_nom"] = df.route_nom.fillna("Route sans nom")
    df["region"] = df.region_nom_bdd.str.strip()
    df["prefecture_key"] = df.prefecture_nom_bdd.map(key)
    unk = sorted(set(df.prefecture_key) - pref_keys)
    j.control(src, "Préfectures rattachées à la nomenclature population",
              f"{df.prefecture_key.nunique() - len(unk)} / {df.prefecture_key.nunique()}", not unk)
    df["id"] = df.FID.str.split(".fid-").str[-1]
    return df.rename(columns={"prefecture_nom_bdd": "prefecture", "commune_nom_bdd": "commune",
                              "canton_nom_bdd": "canton"})[
        ["id", "region", "prefecture_key", "prefecture", "commune", "canton", "route_nom", "route_type",
         "route_recouvrement", "revetement", "voies_nbr", "geometry"]]


# ── État du réseau (tronçons) ────────────────────────────────────────────────────────────

RESEAU_MAP = {"ROUTES REVETUES": "Routes revêtues", "ROUTES EN TERRES": "Routes en terre",
              "VOIRIES REVETUES": "Voiries revêtues", "VOIRIES EN TERRES": "Voiries en terre"}
ETAT_MAP = {"BON": "Bon", "MOYEN": "Moyen", "MAUVAIS": "Mauvais", "TRAVAUX": "Travaux", "TOTAL": "Total"}


def clean_etat_routes(raw: pd.DataFrame, j: Journal) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Retourne (tronçons, totaux publiés par réseau, voiries urbaines agrégées)."""
    src = "État du réseau routier"
    df = _numeric(raw.rename(columns={"tronçon": "troncon_source"}), j, src)
    df["reseau"] = df.indicateur.map(RESEAU_MAP)
    df["etat"] = df.etat.map(ETAT_MAP)
    df["troncon_source"] = df.troncon_source.str.strip()
    j.control(src, "Millésime", f"{', '.join(map(str, sorted(df.annee.unique())))} (photographie unique)", None)
    dup = df.duplicated(["reseau", "troncon_source", "etat"]).sum()
    j.control(src, "Doublons (réseau × tronçon × état)", f"{dup}", dup == 0)
    w = df.pivot_table(index=["reseau", "troncon_source"], columns="etat", values="valeur", aggfunc="sum",
                       sort=False).reset_index()
    for e in ["Bon", "Moyen", "Mauvais", "Travaux"]:
        if e not in w:
            w[e] = np.nan
    is_total = w.troncon_source.str.upper().str.match(r"^TOTAL")
    is_voirie = w.reseau.str.startswith("Voiries")
    n_missing = int(w.loc[~is_total, "Travaux"].isna().sum())
    w[["Bon", "Moyen", "Mauvais", "Travaux"]] = w[["Bon", "Moyen", "Mauvais", "Travaux"]].fillna(0.0)
    j.log(src, "État « Travaux » absent → 0 km", "La ligne TRAVAUX n'existe que pour les tronçons concernés ; "
          "la somme Bon + Moyen + Mauvais égale le total pour les autres (contrôle ci-dessous)", n_missing)
    w["somme_etats"] = w[["Bon", "Moyen", "Mauvais", "Travaux"]].sum(axis=1)
    w["ecart"] = (w.somme_etats - w["Total"]).round(2)
    ok = w.ecart.abs() <= 0.05
    j.control(src, "Bon + Moyen + Mauvais + Travaux = total du tronçon (± 0,05 km)",
              f"{int(ok[~is_total].sum())} / {int((~is_total).sum())} tronçons conformes", bool(ok[~is_total].all()))
    for r in w[~ok & ~is_total].itertuples():
        j.anomaly(src, r.troncon_source, "Somme des états ≠ total", f"Écart de {fr_num(r.ecart, 2)} km",
                  "Total publié conservé ; parts calculées sur le total")
    totals = w[is_total].copy()
    tr = w[~is_total & ~is_voirie].copy()
    for r in totals.itertuples():
        s = tr.loc[tr.reseau == r.reseau, "Total"].sum()
        j.control(src, f"Somme des tronçons = total publié ({r.reseau})",
                  f"{fr_num(s, 2)} km contre {fr_num(r.Total, 2)} km", abs(s - r.Total) <= 0.5)
    voiries = w[is_voirie].copy()
    j.log(src, "Voiries urbaines isolées", "Publiées en un seul agrégat national sans tronçon : exclues des "
          "comparaisons régionales, incluses dans le total national", len(voiries))
    tr["troncon"] = tr.troncon_source.map(display_troncon)
    j.log(src, "Libellés d'affichage des tronçons", "Code technique de gestion (ex. « TGRPRR ») retiré à l'affichage ; "
          "libellé source conservé pour la traçabilité", len(tr))
    return tr.drop(columns=["somme_etats", "ecart"]), totals, voiries


def display_troncon(name: str) -> str:
    s = re.sub(r"\s+", " ", str(name)).strip()
    s = re.sub(r"^TGR[MPCKS][RVTA]*?(?=RN\d|\s)", "", s).strip()
    return s
