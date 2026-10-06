"""Paramètres partagés : chemins, palette fonctionnelle, nomenclatures et libellés."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIRS = [ROOT / "data" / "raw", ROOT / "data", ROOT]  # ordre de recherche des fichiers sources
REFERENCE_DIR = ROOT / "data" / "reference"
PROCESSED_DIR = ROOT / "data" / "processed"

# ── Fichiers sources (motif de nom → rôle) ───────────────────────────────────────────────
SOURCES = {
    "immatriculations": {
        "fichier": "observationdata-akkouh.csv",
        "role": "Immatriculations annuelles par type de véhicule",
        "theme": "Mobilité",
    },
    "immat_detail": {
        "fichier": "observationdata-wklhvw.csv",
        "role": "Immatriculations détaillées (deux-roues par cylindrée)",
        "theme": "Mobilité",
    },
    "national": {
        "fichier": "observationdata-hxdpzbg.csv",
        "role": "Séries nationales : accidents, décès, blessés, trafic, fret, permis",
        "theme": "Sécurité routière",
    },
    "permis": {
        "fichier": "observationdata-wvtolmb.csv",
        "role": "Permis de conduire délivrés par catégorie",
        "theme": "Mobilité",
    },
    "population": {
        "fichier": "observationdata-kwwolwb.csv",
        "role": "Population résidente 2022 par découpage administratif (RGPH-5)",
        "theme": "Dénominateurs",
    },
    "etat_routes": {
        "fichier": "observationdata-tmdtnad.csv",
        "role": "État du réseau routier par tronçon (km, 2020)",
        "theme": "Infrastructure",
    },
    "routes_geo": {
        "fichier": "file-routes-routes-classees-*.csv",
        "role": "Géométries des routes classées (segments géolocalisés)",
        "theme": "Infrastructure",
    },
    "auto_ecoles": {
        "fichier": "file-entreprises-auto-ecoles-*.csv",
        "role": "Auto-écoles géolocalisées et statut d'agrément",
        "theme": "Formation",
    },
    "dict_routes": {
        "fichier": "routes-routes-classees.csv",
        "role": "Dictionnaire des champs « routes classées »",
        "theme": "Métadonnées",
    },
    "dict_auto_ecoles": {
        "fichier": "entreprises-auto-ecoles.csv",
        "role": "Dictionnaire des champs « auto-écoles »",
        "theme": "Métadonnées",
    },
}
BOUNDARIES_FILE = REFERENCE_DIR / "tgo_admin2.geojson"
BOUNDARIES_SOURCE = (
    "OCHA COD-AB Togo v02 (limites des préfectures, valides au 07/01/2021), plateforme HDX "
    "https://data.humdata.org/dataset/cod-ab-tgo — licence CC BY-IGO"
)

# ── Palette fonctionnelle (5 couleurs, validée CVD — voir rapport) ─────────────────────────
BLUE = "#1D4E9E"     # information, mobilité, travaux en cours
ORANGE = "#EF8A00"   # alerte, état moyen
RED = "#B3261E"      # danger, mortalité, mauvais état
GREEN = "#5CB85C"    # bon état, amélioration
GREY = "#A3A29C"     # donnée indisponible, neutre
GREY_LIGHT = "#D9D8D3"

INK = "#0B0B0B"
INK_2 = "#3D3C39"
MUTED = "#7A7974"
LINE = "#E6E5E0"
GRID = "#ECEBE6"
SURFACE = "#FFFFFF"
BACKGROUND = "#F4F4F1"

FONT = "Inter, 'Segoe UI', system-ui, -apple-system, Roboto, 'Helvetica Neue', Arial, sans-serif"

# Rampes séquentielles (une teinte, clair → foncé)
SEQ_BLUE = ["#EEF3FB", "#C9D8F0", "#8FB0E0", "#4F7FC4", "#1D4E9E", "#0F2F66"]
SEQ_RED = ["#FBEDEB", "#F2C4BF", "#E08F86", "#C9554A", "#B3261E", "#7A1712"]

# ── Nomenclatures ────────────────────────────────────────────────────────────────────────
REGIONS = ["Savanes", "Kara", "Centrale", "Plateaux", "Maritime"]  # nord → sud

ETATS = ["Bon", "Moyen", "Mauvais", "Travaux"]
ETAT_COLORS = {"Bon": GREEN, "Moyen": ORANGE, "Mauvais": RED, "Travaux": BLUE, "Non évalué": GREY}
ETAT_LABELS = {"Bon": "Bon état", "Moyen": "État moyen", "Mauvais": "Mauvais état",
               "Travaux": "Travaux en cours", "Non évalué": "État non renseigné"}

# Immatriculations : libellé source → (type harmonisé, famille)
VEHICULE_MAP = {
    "Voitues": ("Voitures", "Voitures"),
    "Camionnettes": ("Camionnettes", "Utilitaires légers"),
    "Autocars/Autobus": ("Autocars et autobus", "Transport collectif"),
    "Camions": ("Camions", "Poids lourds"),
    "Semi-remorques": ("Semi-remorques", "Poids lourds"),
    "Tracteurs": ("Tracteurs routiers", "Poids lourds"),
    "2 roues et assimilées": ("Deux-roues", "Deux-roues"),
}
FAMILLES = ["Deux-roues", "Voitures", "Utilitaires légers", "Poids lourds", "Transport collectif"]
FAMILLE_COLORS = {
    "Deux-roues": BLUE, "Voitures": "#6C8FC9", "Utilitaires légers": "#A9BEE0",
    "Poids lourds": "#3D3C39", "Transport collectif": GREY,
}

PERMIS_MAP = {
    "Moto (A)": "A · Moto",
    "Voiture légèr (B)": "B · Véhicule léger",
    "Poids lourd (C)": "C · Poids lourd",
    "Transport en commun (D)": "D · Transport en commun",
    "Semi-remorque (E)": "E · Semi-remorque",
    "Voiture spéciale (F)": "F · Véhicule spécial",
}
PERMIS = list(PERMIS_MAP.values())
PERMIS_COLORS = {
    "A · Moto": BLUE, "B · Véhicule léger": "#8FB0E0", "C · Poids lourd": "#3D3C39",
    "D · Transport en commun": GREY, "E · Semi-remorque": ORANGE, "F · Véhicule spécial": GREY_LIGHT,
}

# Séries nationales : libellé source → (code, libellé harmonisé, unité)
NATIONAL_MAP = {
    "Nombre de cas d'accidents de la circulation": ("accidents", "Accidents de la circulation", "nombre"),
    "Nombre de morts": ("deces", "Décès", "nombre"),
    "Nombre de blessés": ("blesses", "Blessés", "nombre"),
    "Accidents mortels /100.000 hab": ("taux_accidents_publie", "Accidents pour 100 000 habitants (taux publié)",
                                       "pour 100 000 hab."),
    "Evolution du parc automobile 4 roues et plus immatriculé": ("immat_4r", "Immatriculations 4 roues et plus", "nombre"),
    "Evolution des deux roues et assimilées immatriculées": ("immat_2r", "Immatriculations deux-roues", "nombre"),
    "Evolution des premières mise en circulation du parc automobile 4 roues et plus immatriculés":
        ("premieres_mec_4r", "Premières mises en circulation (4 roues et plus)", "nombre"),
    "Nombre de permis de conduire délivrés aux examens de permis de conduire":
        ("permis_total", "Permis de conduire délivrés", "nombre"),
    "Trafic de véhicules de transports de passagers sur le réseau routier":
        ("trafic_passagers", "Trafic de véhicules de transport de passagers", "véhicules"),
    "Trafic de véhicules de transports de marchandises sur le réseau routier":
        ("trafic_marchandises", "Trafic de véhicules de transport de marchandises", "véhicules"),
    "Evolution du volume de fret routier": ("fret_routier", "Fret routier", "tonnes"),
    "Evolution du volume de tonne de marchandises transportées par rails": ("fret_rail", "Fret ferroviaire", "tonnes"),
    "Réseau total (chemins de fer-km)": ("rail_km", "Réseau ferré", "km"),
}

# Codes régionaux portés par les noms de tronçons (TGR + lettre)
REGION_CODES = {"M": "Maritime", "P": "Plateaux", "C": "Centrale", "K": "Kara", "S": "Savanes"}

# Régions du fichier population → région d'analyse (nomenclature des bases routes / auto-écoles)
POP_REGION_MAP = {"SAVANES": "Savanes", "KARA": "Kara", "CENTRALE": "Centrale", "PLATEAUX": "Plateaux",
                  "MARITIME": "Maritime", "DAGL": "Maritime"}

# Corrections de libellés du fichier population (coquilles constatées, contrôlées par les sommes)
POP_LABEL_FIXES = {"TOTOAL AVE": "AVE", "BINAH2": "BINAH 2"}

# Noms OCHA → clé de préfecture harmonisée
OCHA_ALIASES = {"NAKI OUEST": "KPENDJAL OUEST", "PLAINE DU MO": "MO", "LOME COMMUNE": "GOLFE"}

# Noms d'affichage pour les préfectures absentes des bases routes / auto-écoles
EXTRA_PREF_NAMES = {"MO": "Mô"}

UNAVAILABLE = "Donnée indisponible"
EMPTY = "Aucune donnée pour cette sélection"
