"""Chargement des fichiers sources (lecture seule) et inventaire des fichiers et variables."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from .config import RAW_DIRS, SOURCES


class SourceMissing(FileNotFoundError):
    pass


def locate(pattern: str) -> Path:
    """Premier fichier correspondant au motif dans data/raw, data/ puis la racine du projet."""
    for folder in RAW_DIRS:
        hits = sorted(folder.glob(pattern))
        if hits:
            return hits[-1]  # export le plus récent si plusieurs versions horodatées
    raise SourceMissing(f"Fichier source introuvable : {pattern} (cherché dans data/raw/, data/ et la racine)")


def read_raw(key: str) -> pd.DataFrame:
    """Lit un CSV source en texte brut : aucune conversion implicite, la source n'est jamais réécrite."""
    path = locate(SOURCES[key]["fichier"])
    return pd.read_csv(path, dtype=str, encoding="utf-8", keep_default_na=False, na_values=[""])


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_all() -> dict[str, pd.DataFrame]:
    return {key: read_raw(key) for key in SOURCES}


def _period(df: pd.DataFrame) -> str:
    for col in ("Date", "date"):
        if col in df.columns:
            years = pd.to_numeric(df[col], errors="coerce").dropna().astype(int)
            if len(years):
                return f"{years.min()}–{years.max()}" if years.min() != years.max() else str(years.min())
    return "—"


GEO_KEYS = {
    "region_nom_bdd": "région", "prefecture_nom_bdd": "préfecture", "commune_nom_bdd": "commune",
    "canton_nom_bdd": "canton", "découpage-administratif": "découpage administratif (libellé)",
    "tronçon": "tronçon (libellé)", "geometry": "géométrie WKT",
}


def inventory(raw: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Inventaire des fichiers (une ligne par fichier) et des variables (une ligne par colonne)."""
    files, variables = [], []
    for key, meta in SOURCES.items():
        path = locate(meta["fichier"])
        df = raw[key]
        cells = df.size
        missing = int(df.isna().sum().sum())
        geo = [GEO_KEYS[c] for c in df.columns if c in GEO_KEYS]
        files.append({
            "cle": key,
            "fichier": path.name,
            "role": meta["role"],
            "theme": meta["theme"],
            "format": "CSV (UTF-8, séparateur virgule)",
            "taille_ko": round(path.stat().st_size / 1024, 1),
            "lignes": len(df),
            "colonnes": df.shape[1],
            "periode": _period(df),
            "cles_geographiques": ", ".join(geo) if geo else "aucune (national)",
            "completude_pct": round(100 * (1 - missing / cells), 2) if cells else None,
            "doublons_exacts": int(df.duplicated().sum()),
            "sha256": sha256(path)[:16],
        })
        for col in df.columns:
            s = df[col]
            variables.append({
                "fichier": path.name,
                "variable": col,
                "valeurs_distinctes": int(s.nunique(dropna=True)),
                "manquantes": int(s.isna().sum()),
                "exemple": str(s.dropna().iloc[0])[:60] if s.notna().any() else "",
            })
    return pd.DataFrame(files), pd.DataFrame(variables)
