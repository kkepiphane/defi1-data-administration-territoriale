"""Fabrique de graphiques Plotly : thème sobre noir et blanc, palette fonctionnelle à 5 couleurs."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .cleaning import fr_num
from .config import (BLUE, EMPTY, ETAT_COLORS, ETAT_LABELS, ETATS, FAMILLE_COLORS, FONT, GREEN, GREY, GREY_LIGHT,
                     GRID, INK, INK_2, LINE, MUTED, ORANGE, PERMIS_COLORS, RED, SEQ_BLUE, SEQ_RED, SURFACE)

GRAPH_CONFIG = {
    "displaylogo": False,
    "locale": "fr",
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines", "zoomIn2d", "zoomOut2d",
                               "hoverCompareCartesian", "hoverClosestCartesian"],
    "toImageButtonOptions": {"format": "png", "scale": 2, "filename": "securite-routiere-togo"},
    "responsive": True,
}
PRIORITY_COLORS = {"Élevée": RED, "Moyenne": ORANGE, "À surveiller": GREY, "Indéterminée": GREY_LIGHT}
MAP_STYLE = "white-bg"  # fond local : fonctionne hors ligne, aucune dépendance à un serveur de tuiles
BASEMAP_STYLE = "carto-positron-nolabels"  # fond de plan optionnel (internet requis), sans libellés anglais
REGION_LINE = "#4A4945"


def _region_outline(fig: go.Figure, region_geojson: dict | None):
    """Contours régionaux par-dessus les préfectures, pour se repérer sans fond de plan."""
    if not region_geojson:
        return
    ids = [f["id"] for f in region_geojson["features"]]
    fig.add_trace(go.Choroplethmap(geojson=region_geojson, locations=ids, z=[0] * len(ids), featureidkey="id",
                                   colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
                                   marker=dict(line=dict(color=REGION_LINE, width=1.6)), hoverinfo="skip",
                                   showlegend=False, name="Régions"))


def config(filename: str) -> dict:
    c = dict(GRAPH_CONFIG)
    c["toImageButtonOptions"] = {**GRAPH_CONFIG["toImageButtonOptions"], "filename": filename}
    return c


def theme(fig: go.Figure, height: int = 320, legend: bool = True, margin=None) -> go.Figure:
    fig.update_layout(
        height=height, template="none", separators=", ",
        font=dict(family=FONT, size=12, color=INK_2),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        margin=margin or dict(l=8, r=12, t=8 if not legend else 36, b=8),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=LINE, font=dict(family=FONT, size=12, color=INK), align="left"),
        showlegend=legend,
        legend=dict(orientation="h", x=0, xanchor="left", y=1.02, yanchor="bottom", font=dict(size=11.5, color=INK_2),
                    bgcolor="rgba(0,0,0,0)", itemclick="toggle", itemdoubleclick="toggleothers", title=None),
        bargap=0.38, barcornerradius=3, hovermode="closest", dragmode=False,
        legend_traceorder="normal",
    )
    fig.update_xaxes(showgrid=False, zeroline=False, showline=True, linecolor="#D6D5CF", linewidth=1, ticks="",
                     tickfont=dict(size=11, color=MUTED), title=None, automargin=True, fixedrange=True)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False, showline=False, ticks="",
                     tickfont=dict(size=11, color=MUTED), title=None, automargin=True, fixedrange=True,
                     separatethousands=True)
    return fig


def empty(message: str = EMPTY, height: int = 280, hint: str | None = None) -> go.Figure:
    fig = go.Figure()
    text = f"<b>{message}</b>" + (f"<br><span style='font-size:11.5px;color:{MUTED}'>{hint}</span>" if hint else "")
    fig.add_annotation(text=text, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
                       font=dict(size=13, color=INK_2, family=FONT), align="center")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return theme(fig, height, legend=False, margin=dict(l=0, r=0, t=0, b=0))


def _flag_trace(x, y, texts, name="Valeur atypique (à vérifier)") -> go.Scatter:
    return go.Scatter(x=x, y=y, mode="markers", name=name, text=texts,
                      marker=dict(symbol="circle-open", size=13, color=INK, line=dict(width=1.6)),
                      hovertemplate="%{text}<extra></extra>", showlegend=True, cliponaxis=False)


def _years_axis(fig, years):
    if len(years) and len(years) <= 16:
        fig.update_xaxes(tickmode="array", tickvals=list(years), ticktext=[str(y) for y in years])
    else:
        fig.update_xaxes(dtick=2 if len(years) <= 24 else 5)


# ── Vue d'ensemble ───────────────────────────────────────────────────────────────────────

def overview_index(safety: pd.DataFrame, immat_tot: pd.Series, years, flags: dict | None = None
                   ) -> tuple[go.Figure, str]:
    """Indices base 100 (une seule échelle) : motorisation vs accidents vs décès.

    L'année de base est la première de la période où les trois séries existent et qui n'est pas signalée
    atypique : une base anormalement basse gonflerait artificiellement toutes les évolutions.
    """
    y0, y1 = years
    df = pd.DataFrame({"Immatriculations": immat_tot, "Accidents": safety.accidents, "Décès": safety.deces})
    df = df.loc[(df.index >= y0) & (df.index <= y1)].dropna()
    flagged = set()
    for k in ("Accidents", "Décès", "Blessés"):
        flagged |= set((flags or {}).get(k, {}))
    skipped = []
    while len(df) > 2 and int(df.index[0]) in flagged:
        skipped.append(int(df.index[0]))
        df = df.iloc[1:]
    if len(df) < 2:
        return empty("Période trop courte pour comparer les évolutions",
                     hint="Les accidents sont disponibles de 2010 à 2022 : élargissez la période."), ""
    base = int(df.index[0])
    idx = 100 * df / df.iloc[0]
    fig = go.Figure()
    colors = {"Immatriculations": BLUE, "Accidents": ORANGE, "Décès": RED}
    for col in idx.columns:
        fig.add_trace(go.Scatter(
            x=idx.index, y=idx[col], name=col, mode="lines+markers", line=dict(color=colors[col], width=2.2),
            marker=dict(size=6, color=colors[col], line=dict(color=SURFACE, width=1.5)),
            customdata=df[col], hovertemplate=f"<b>{col}</b> %{{x}}<br>Indice %{{y:.0f}} (base {base} = 100)"
                                              "<br>Valeur : %{customdata:,.0f}<extra></extra>"))
    ends = idx.iloc[-1].sort_values()
    span = max(idx.max().max() - idx.min().min(), 1)
    shifts, prev = {}, None
    for col, v in ends.items():
        shifts[col] = 0
        if prev is not None and (v - prev[1]) < span * 0.07:
            shifts[prev[0]] = shifts.get(prev[0], 0) - 6
            shifts[col] = 6
        prev = (col, v)
    for col, v in ends.items():
        fig.add_annotation(x=idx.index[-1], y=v, text=f"{v:.0f}", showarrow=False, xanchor="left", xshift=8,
                           yshift=shifts[col], font=dict(size=11.5, color=INK))
    fig.add_hline(y=100, line=dict(color="#C9C8C1", width=1))
    theme(fig, 300)
    _years_axis(fig, list(idx.index))
    fig.update_xaxes(range=[idx.index[0] - 0.4, idx.index[-1] + 0.9])
    last = idx.iloc[-1]
    def pct(v):
        v = v - 100
        return f"{'+' if v >= 0 else '−'}{fr_num(abs(v))} %"
    msg = (f"De {base} à {int(idx.index[-1])} : immatriculations {pct(last['Immatriculations'])}, accidents "
           f"{pct(last['Accidents'])}, décès {pct(last['Décès'])}.")
    if skipped:
        msg += f" Base {base} : {', '.join(map(str, skipped))} écarté (valeur d'accidents atypique)."
    return fig, msg


def choropleth(pref: pd.DataFrame, geojson: dict, col: str, colorscale, view: dict, hover: str, selected=None,
               height: int = 470, zmin=None, zmax=None, colorbar_title="", customdata_cols=None,
               region_geojson: dict | None = None) -> go.Figure:
    df = pref.copy()
    fig = go.Figure(go.Choroplethmap(
        geojson=geojson, locations=df.prefecture_key, z=df[col], featureidkey="id", colorscale=colorscale,
        zmin=zmin, zmax=zmax, marker=dict(line=dict(color=SURFACE, width=0.8), opacity=0.95),
        customdata=df[customdata_cols].values if customdata_cols else None, hovertemplate=hover,
        colorbar=dict(title=dict(text=colorbar_title, font=dict(size=11, color=MUTED)), thickness=10, len=0.55,
                      x=0.99, xanchor="right", y=0.5, outlinewidth=0, tickfont=dict(size=10.5, color=MUTED),
                      bgcolor="rgba(255,255,255,0.75)"),
    ))
    _region_outline(fig, region_geojson)
    if selected:
        fig.add_trace(go.Choroplethmap(
            geojson=geojson, locations=selected, z=[1] * len(selected), featureidkey="id",
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
            marker=dict(line=dict(color=INK, width=2.6)), hoverinfo="skip"))
    fig.update_layout(map=dict(style=MAP_STYLE, center=view["center"], zoom=view["zoom"]),
                      margin=dict(l=0, r=0, t=0, b=0), height=height, paper_bgcolor=SURFACE,
                      font=dict(family=FONT), hoverlabel=dict(bgcolor=SURFACE, bordercolor=LINE,
                                                              font=dict(family=FONT, size=12, color=INK)),
                      showlegend=False, separators=", ")
    return fig


def priority_map(pref, geojson, view, selected=None, height=470, region_geojson=None) -> go.Figure:
    df = pref.copy()
    df["score_txt"] = df.score.map(lambda v: fr_num(v, 0))
    df["mauv_txt"] = df.part_mauvais.map(lambda v: fr_num(v, 0) + " %" if pd.notna(v) else "non évalué")
    df["ae_txt"] = df.ae_100k.map(lambda v: fr_num(v, 1))
    df["dens_txt"] = df.densite_km_1000km2.map(lambda v: fr_num(v, 0))
    hover = ("<b>%{customdata[0]}</b> · %{customdata[1]}<br>Score de priorité : <b>%{customdata[2]}</b> / 100 "
             "(%{customdata[3]})<br>Réseau en mauvais état ≈ %{customdata[4]}<br>Auto-écoles / 100 000 hab. : "
             "%{customdata[5]}<br>Routes classées / 1 000 km² : %{customdata[6]}<extra></extra>")
    cs = [[i / (len(SEQ_RED) - 1), c] for i, c in enumerate(SEQ_RED)]
    return choropleth(df, geojson, "score", cs, view, hover, selected, height, 0, 100, "Score",
                      ["prefecture", "region", "score_txt", "priorite", "mauv_txt", "ae_txt", "dens_txt"],
                      region_geojson)


def priority_bars(pref: pd.DataFrame, n: int = 12, selected=None) -> go.Figure:
    df = pref.dropna(subset=["score"]).sort_values("score", ascending=False).head(n).iloc[::-1]
    if df.empty:
        return empty()
    colors = [PRIORITY_COLORS.get(p, GREY) for p in df.priorite]
    lines = [2 if selected and k in selected else 0 for k in df.prefecture_key]
    fig = go.Figure(go.Bar(
        x=df.score, y=df.prefecture, orientation="h", marker=dict(color=colors, line=dict(color=INK, width=lines)),
        customdata=np.stack([df.region, df.priorite, df.composantes, df.prefecture_key], axis=1),
        text=df.score.map(lambda v: fr_num(v)), textposition="outside", textfont=dict(size=11, color=INK),
        hovertemplate="<b>%{y}</b> (%{customdata[0]})<br>Score %{x:.0f} / 100 · priorité %{customdata[1]}"
                      "<br>Composantes disponibles : %{customdata[2]} / 3<extra></extra>", cliponaxis=False))
    theme(fig, max(260, 26 * len(df) + 40), legend=False, margin=dict(l=8, r=30, t=6, b=6))
    fig.update_layout(bargap=0.32)
    fig.update_xaxes(range=[0, 108], showline=False, showgrid=True, gridcolor=GRID, dtick=25)
    fig.update_yaxes(showgrid=False, tickfont=dict(size=11.5, color=INK_2))
    return fig


# ── Mobilité & permis ────────────────────────────────────────────────────────────────────

def immat_stack(w: pd.DataFrame, mode: str, flags: dict) -> go.Figure:
    if w.empty or w.sum().sum() == 0:
        return empty(hint="Sélectionnez au moins un type de véhicule et une période contenant des données.")
    data = w.div(w.sum(axis=1), axis=0) * 100 if mode == "part" else w
    fig = go.Figure()
    for fam in w.columns:
        fig.add_trace(go.Bar(
            x=data.index, y=data[fam], name=fam, marker=dict(color=FAMILLE_COLORS.get(fam, GREY), line=dict(width=0)),
            customdata=np.stack([w[fam], 100 * w[fam] / w.sum(axis=1)], axis=1),
            hovertemplate=f"<b>{fam}</b> %{{x}}<br>%{{customdata[0]:,.0f}} immatriculations"
                          "<br>%{customdata[1]:.1f} % du total<extra></extra>"))
    fx, fy, ft = [], [], []
    for fam in w.columns:
        for y, kind in flags.get(fam, {}).items():
            if y in data.index:
                fx.append(y)
                fy.append(data.loc[y].sum() * (1.04 if mode != "part" else 1.03))
                ft.append(f"{fam} {y} : {kind.lower()} — valeur conservée, à confirmer")
    if fx:
        fig.add_trace(_flag_trace(fx, fy, ft, "Anomalie signalée"))
    theme(fig, 330)
    fig.update_layout(barmode="stack", bargap=0.3)
    fig.update_yaxes(ticksuffix=" %" if mode == "part" else "", range=[0, 104] if mode == "part" else None)
    _years_axis(fig, list(data.index))
    return fig


def share_line(w: pd.DataFrame, fam: str = "Deux-roues") -> tuple[go.Figure, str]:
    if w.empty or fam not in w or w[fam].sum() == 0:
        return empty("Deux-roues non sélectionnés", hint="Ajoutez « Deux-roues » dans le filtre Type de véhicule."), ""
    share = 100 * w[fam] / w.sum(axis=1)
    fig = go.Figure(go.Scatter(
        x=share.index, y=share, mode="lines", line=dict(color=BLUE, width=2.2), fill="tozeroy",
        fillcolor="rgba(29,78,158,0.08)", name="Part des deux-roues",
        hovertemplate="%{x} : <b>%{y:.1f} %</b> des immatriculations<extra></extra>"))
    fig.add_trace(go.Scatter(x=[share.index[-1]], y=[share.iloc[-1]], mode="markers+text", text=[f"{share.iloc[-1]:.0f} %"],
                             textposition="top center", marker=dict(size=8, color=BLUE, line=dict(color=SURFACE, width=2)),
                             textfont=dict(size=11.5, color=INK), hoverinfo="skip", cliponaxis=False))
    theme(fig, 250, legend=False, margin=dict(l=8, r=16, t=18, b=8))
    fig.update_yaxes(range=[0, 100], ticksuffix=" %", dtick=25)
    fig.update_xaxes(dtick=3 if len(share) > 8 else 1)
    y0, y1 = share.index[0], share.index[-1]
    return fig, (f"Les deux-roues représentent {fr_num(share.iloc[-1])} % des immatriculations en {y1}, contre "
                 f"{fr_num(share.iloc[0])} % en {y0}.")


def permis_stack(w: pd.DataFrame, mode: str, flags: dict, missing_years: list[int]) -> go.Figure:
    if w.empty or w.sum().sum() == 0:
        return empty(hint="Les permis par catégorie couvrent 2007–2022 (2013 manquant).")
    data = w.div(w.sum(axis=1), axis=0) * 100 if mode == "part" else w
    fig = go.Figure()
    for c in w.columns:
        fig.add_trace(go.Bar(
            x=data.index, y=data[c], name=c, marker=dict(color=PERMIS_COLORS.get(c, GREY), line=dict(width=0)),
            customdata=np.stack([w[c], 100 * w[c] / w.sum(axis=1)], axis=1),
            hovertemplate=f"<b>{c}</b> %{{x}}<br>%{{customdata[0]:,.0f}} permis<br>%{{customdata[1]:.1f}} % du total"
                          "<extra></extra>"))
    fx, fy, ft = [], [], []
    for c in w.columns:
        for y, kind in flags.get(c, {}).items():
            if y in data.index:
                fx.append(y)
                fy.append(data.loc[y].sum() * 1.04 if mode != "part" else 103)
                ft.append(f"{c} {y} : {kind.lower()} ({fr_num(w.loc[y, c])}) — à confirmer")
    if fx:
        fig.add_trace(_flag_trace(fx, fy, ft, "Anomalie signalée"))
    top = (data.sum(axis=1).max() if mode != "part" else 100) or 1
    for y in missing_years:
        if data.index.min() <= y <= data.index.max():
            fig.add_trace(go.Bar(x=[y], y=[top * 0.12], marker=dict(color="rgba(0,0,0,0)", line=dict(color=GREY, width=1.2)),
                                 name="Donnée manquante", hovertemplate=f"{y} : donnée manquante<extra></extra>",
                                 showlegend=True))
            fig.add_annotation(x=y, y=top * 0.12, text="n.d.", showarrow=False, yshift=10,
                               font=dict(size=10.5, color=MUTED))
    theme(fig, 330)
    fig.update_layout(barmode="stack", bargap=0.3)
    fig.update_yaxes(ticksuffix=" %" if mode == "part" else "", range=[0, 106] if mode == "part" else None)
    _years_axis(fig, list(range(int(data.index.min()), int(data.index.max()) + 1)))
    return fig


def formation_gap(imm: pd.DataFrame, per: pd.DataFrame, flags: dict) -> tuple[go.Figure, str]:
    """Permis délivrés pour 100 véhicules immatriculés de la même catégorie : petits multiples (échelles propres)."""
    pairs = [("A · Moto", ["Deux-roues"], "Permis A pour 100 deux-roues", BLUE),
             ("B · Véhicule léger", ["Voitures", "Utilitaires légers"], "Permis B pour 100 voitures + utilitaires", ORANGE)]
    series = []
    for cat, fams, label, color in pairs:
        if imm.empty or per.empty or cat not in per or not set(fams) & set(imm.columns):
            continue
        den = imm[[f for f in fams if f in imm]].sum(axis=1)
        r = (100 * per[cat] / den.reindex(per.index)).replace([np.inf, -np.inf], np.nan).dropna()
        if not r.empty:
            series.append((cat, label, color, r))
    if not series:
        return empty(hint="Sélectionnez les catégories A ou B et les véhicules correspondants."), ""
    fig = make_subplots(rows=len(series), cols=1, subplot_titles=[s[1] for s in series], vertical_spacing=0.2,
                        shared_xaxes=True)
    msgs = []
    for i, (cat, label, color, r) in enumerate(series, start=1):
        fig.add_trace(go.Scatter(x=r.index, y=r, name=label, mode="lines+markers", line=dict(color=color, width=2),
                                 marker=dict(size=6, color=color, line=dict(color=SURFACE, width=1.5)),
                                 hovertemplate=f"<b>{label}</b><br>%{{x}} : %{{y:.1f}}<extra></extra>", showlegend=False),
                      row=i, col=1)
        fl = [y for y in flags.get(cat, {}) if y in r.index]
        if fl:
            fig.add_trace(_flag_trace(fl, r.loc[fl], [f"{cat} {y} : numérateur atypique — à confirmer" for y in fl]),
                          row=i, col=1)
        med = r.median()
        fig.add_hline(y=med, line=dict(color=GREY, width=1), row=i, col=1,
                      annotation=dict(text=f"médiane {fr_num(med, 1)}", font=dict(size=10.5, color=INK_2),
                                      xanchor="right", x=1, yanchor="bottom"))
        msgs.append(f"{label} : {fr_num(med, 1)} en médiane")
    theme(fig, 150 * len(series) + 40, legend=False, margin=dict(l=8, r=12, t=26, b=8))
    for a in fig.layout.annotations:
        if a.text in [s[1] for s in series]:
            a.font = dict(size=12, color=INK, family=FONT)
            a.xanchor, a.x = "left", 0
    fig.update_yaxes(rangemode="tozero", nticks=4)
    fig.update_xaxes(dtick=3)
    return fig, " · ".join(msgs) + " (années de la période)."


def cylindree(df: pd.DataFrame, years) -> go.Figure:
    d = df[(df.annee >= years[0]) & (df.annee <= years[1])]
    if d.empty:
        return empty("Détail par cylindrée disponible de 2013 à 2019 uniquement", height=220)
    w = d.pivot(index="annee", columns="cylindree", values="valeur")
    fig = go.Figure()
    for c, col in [("50 à 125 cm³", BLUE), ("Plus de 125 cm³", "#8FB0E0")]:
        if c in w:
            fig.add_trace(go.Bar(x=w.index, y=w[c], name=c, marker=dict(color=col),
                                 customdata=100 * w[c] / w.sum(axis=1),
                                 hovertemplate=f"<b>{c}</b> %{{x}}<br>%{{y:,.0f}} (%{{customdata:.0f}} %)<extra></extra>"))
    theme(fig, 230)
    fig.update_layout(barmode="stack")
    _years_axis(fig, list(w.index))
    return fig


# ── Sécurité routière ────────────────────────────────────────────────────────────────────

def safety_multiples(s: pd.DataFrame, flags: dict) -> go.Figure:
    if s.empty:
        return empty(hint="Accidents, blessés et décès sont disponibles de 2010 à 2022.")
    cols = [("accidents", "Accidents", ORANGE), ("blesses", "Blessés", ORANGE), ("deces", "Décès", RED)]
    fig = make_subplots(rows=1, cols=3, subplot_titles=[c[1] for c in cols], horizontal_spacing=0.07)
    for i, (col, label, color) in enumerate(cols, start=1):
        v = s[col].dropna()
        fig.add_trace(go.Scatter(x=v.index, y=v, mode="lines+markers", name=label, line=dict(color=color, width=2),
                                 marker=dict(size=6, color=color, line=dict(color=SURFACE, width=1.5)),
                                 fill="tozeroy", fillcolor="rgba(179,38,30,0.06)" if col == "deces" else "rgba(239,138,0,0.06)",
                                 hovertemplate=f"<b>{label}</b> %{{x}} : %{{y:,.0f}}<extra></extra>", showlegend=False),
                      row=1, col=i)
        if len(v):
            fig.add_annotation(x=v.index[-1], y=v.iloc[-1], text=fr_num(v.iloc[-1]), showarrow=False, yshift=12,
                               font=dict(size=11, color=INK), row=1, col=i)
        fl = [y for y in flags.get(label, {}) if y in v.index]
        if fl:
            fig.add_trace(_flag_trace(fl, v.loc[fl], [f"{label} {y} : valeur atypique — à confirmer" for y in fl]),
                          row=1, col=i)
    theme(fig, 270, legend=False, margin=dict(l=8, r=12, t=28, b=8))
    fig.update_annotations(selector=dict(text="Accidents"), font=dict(size=12, color=INK))
    for a in fig.layout.annotations:
        if a.text in ("Accidents", "Blessés", "Décès"):
            a.font = dict(size=12, color=INK, family=FONT)
            a.xanchor, a.x = "left", a.x - 0.13
    fig.update_yaxes(rangemode="tozero", showgrid=True, gridcolor=GRID)
    fig.update_xaxes(dtick=3 if len(s) > 8 else 1)
    if any(fl for fl in flags.values()):
        fig.update_layout(showlegend=False)
    return fig


def rate_chart(s: pd.DataFrame, col: str, label: str, decimals: int, flags_years: list[int]) -> go.Figure:
    v = s[col].dropna()
    if v.empty:
        return empty()
    color = RED if "deces" in col else ORANGE
    fig = go.Figure(go.Bar(x=v.index, y=v, marker=dict(color=color), name=label,
                           hovertemplate=f"%{{x}} : <b>%{{y:,.{decimals}f}}</b> {label.lower()}<extra></extra>"))
    avg = v.mean()
    fig.add_hline(y=avg, line=dict(color=INK, width=1, dash="solid"), opacity=0.6,
                  annotation=dict(text=f"moyenne {fr_num(avg, decimals)}", font=dict(size=10.5, color=INK_2),
                                  xanchor="right", x=1, yanchor="bottom", bgcolor="rgba(255,255,255,0.85)"))
    fl = [y for y in flags_years if y in v.index]
    if fl:
        fig.add_trace(_flag_trace(fl, v.loc[fl] * 1.06, [f"{y} : numérateur atypique — à confirmer" for y in fl]))
    theme(fig, 280, legend=bool(fl))
    fig.update_layout(bargap=0.45)
    _years_axis(fig, list(v.index))
    return fig


def years_ranking(s: pd.DataFrame, col: str, label: str, decimals: int) -> go.Figure:
    v = s[col].dropna().sort_values(ascending=True)
    if v.empty:
        return empty()
    top = set(v.sort_values(ascending=False).head(3).index)
    colors = [RED if y in top else GREY_LIGHT for y in v.index]
    fig = go.Figure(go.Bar(x=v.values, y=[str(y) for y in v.index], orientation="h", marker=dict(color=colors),
                           text=[fr_num(x, decimals) for x in v.values], textposition="outside",
                           textfont=dict(size=10.5, color=INK_2), cliponaxis=False,
                           hovertemplate=f"<b>%{{y}}</b> : %{{x:,.{decimals}f}} {label.lower()}<extra></extra>"))
    theme(fig, max(240, 21 * len(v) + 30), legend=False, margin=dict(l=8, r=36, t=6, b=6))
    fig.update_layout(bargap=0.3)
    fig.update_xaxes(showline=False, showgrid=True, gridcolor=GRID, showticklabels=False)
    fig.update_yaxes(showgrid=False, type="category", tickfont=dict(size=11, color=INK_2))
    return fig


def motor_scatter(s: pd.DataFrame, x: str, y: str, xlabel: str, ylabel: str, r: float, n: int) -> go.Figure:
    d = s[[x, y]].dropna()
    if len(d) < 3:
        return empty("Pas assez d'années pour croiser les deux séries")
    keep = {d.index.min(), d.index.max(), d[y].idxmax(), d[y].idxmin()}
    labels = [str(i) if i in keep else "" for i in d.index]
    fig = go.Figure(go.Scatter(
        x=d[x], y=d[y], mode="markers+text", text=labels, textposition="top center",
        customdata=[str(i) for i in d.index], textfont=dict(size=10.5, color=INK_2),
        marker=dict(size=11, color=[RED if i == d.index.max() else BLUE for i in d.index], opacity=0.9,
                    line=dict(color=SURFACE, width=2)),
        hovertemplate=f"<b>%{{customdata}}</b><br>{xlabel} : %{{x:,.0f}}<br>{ylabel} : %{{y:,.0f}}<extra></extra>"))
    if len(d) >= 4:
        k, b = np.polyfit(d[x], d[y], 1)
        xs = np.linspace(d[x].min(), d[x].max(), 20)
        fig.add_trace(go.Scatter(x=xs, y=k * xs + b, mode="lines", line=dict(color=GREY, width=1.2),
                                 hoverinfo="skip", name="Tendance linéaire"))
    theme(fig, 300, legend=False, margin=dict(l=8, r=16, t=12, b=8))
    fig.update_xaxes(title=dict(text=xlabel, font=dict(size=11, color=MUTED)), showgrid=True, gridcolor=GRID)
    fig.update_yaxes(title=dict(text=ylabel, font=dict(size=11, color=MUTED)))
    return fig


def togo_unavailable(geojson: dict, view: dict, height: int = 300) -> go.Figure:
    """Silhouette grise : la donnée n'est pas territorialisée (règle : gris = indisponible)."""
    ids = [f["id"] for f in geojson["features"]]
    fig = go.Figure(go.Choroplethmap(geojson=geojson, locations=ids, z=[0] * len(ids), featureidkey="id",
                                     colorscale=[[0, "#E4E3DE"], [1, "#E4E3DE"]], showscale=False,
                                     marker=dict(line=dict(color=SURFACE, width=0.8)), hoverinfo="skip"))
    fig.update_layout(map=dict(style="white-bg", center=view["center"], zoom=view["zoom"]),
                      margin=dict(l=0, r=0, t=0, b=0), height=height, paper_bgcolor=SURFACE, dragmode=False)
    fig.add_annotation(text="<b>Donnée non territorialisée</b><br><span style='font-size:11px'>Accidents et décès "
                            "publiés<br>au niveau national seulement</span>", x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, bgcolor="rgba(255,255,255,0.92)", bordercolor=LINE, borderpad=8,
                       font=dict(size=12, color=INK_2, family=FONT))
    return fig


# ── Réseau routier & formation ───────────────────────────────────────────────────────────

def road_map(roads: pd.DataFrame, lines: list, ae: pd.DataFrame, pref: pd.DataFrame, geojson: dict, view: dict,
             states: list[str], layers: list[str], selected=None, mode: str = "reseau", height: int = 600,
             hover_pts: pd.DataFrame | None = None, region_geojson: dict | None = None) -> go.Figure:
    basemap = "fond" in layers
    fig = go.Figure()
    # Fond : préfectures (choroplèthe auto-écoles / 100 000 hab. en mode formation, sinon contour neutre)
    if mode == "formation":
        cs = [[i / (len(SEQ_BLUE) - 1), c] for i, c in enumerate(SEQ_BLUE)]
        d = pref.copy()
        d["ae_txt"] = d.ae_100k.map(lambda v: fr_num(v, 1))
        fig.add_trace(go.Choroplethmap(
            geojson=geojson, locations=d.prefecture_key, z=d.ae_100k.clip(upper=4), featureidkey="id", colorscale=cs,
            zmin=0, zmax=4, marker=dict(line=dict(color=SURFACE, width=0.8), opacity=0.8),
            customdata=np.stack([d.prefecture, d.region, d.ae_n, d.ae_txt, d.population], axis=1),
            hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]}<br>%{customdata[2]} auto-école(s)<br>"
                          "%{customdata[3]} pour 100 000 hab.<br>Population 2022 : %{customdata[4]:,.0f}<extra></extra>",
            colorbar=dict(title=dict(text="Auto-écoles<br>/ 100 000 hab.", font=dict(size=10.5, color=MUTED)),
                          thickness=10, len=0.45, x=0.99, xanchor="right", y=0.72, outlinewidth=0,
                          tickvals=[0, 1, 2, 3, 4], ticktext=["0", "1", "2", "3", "≥ 4"], tickfont=dict(size=10.5),
                          bgcolor="rgba(255,255,255,0.8)"), name="Auto-écoles / 100 000 hab."))
    else:
        fig.add_trace(go.Choroplethmap(
            geojson=geojson, locations=pref.prefecture_key, z=[0] * len(pref), featureidkey="id",
            colorscale=[[0, "rgba(255,255,255,0.01)"], [1, "rgba(255,255,255,0.01)"]] if basemap else
            [[0, "#F1F0EC"], [1, "#F1F0EC"]], showscale=False,
            marker=dict(line=dict(color="#C9C8C1" if not basemap else "#B9B8B1", width=0.7)),
            customdata=np.stack([pref.prefecture, pref.region], axis=1),
            hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]}<br>Cliquer pour filtrer<extra></extra>",
            name="Préfectures"))
    _region_outline(fig, region_geojson)
    if "routes" in layers and len(roads):
        order = ["Non évalué", "Bon", "Moyen", "Travaux", "Mauvais"]
        for etat in order:
            if etat != "Non évalué" and etat not in states:
                continue
            idx = roads.index[roads.etat == etat]
            if not len(idx):
                continue
            lon, lat = [], []
            for i in idx:
                xs, ys = lines[i]
                lon += xs
                lat += ys
            width = {"Mauvais": 3.2, "Travaux": 2.8, "Moyen": 2.4, "Bon": 2.2}.get(etat, 1.4)
            fig.add_trace(go.Scattermap(
                lon=lon, lat=lat, mode="lines", line=dict(color=ETAT_COLORS[etat], width=width),
                name=ETAT_LABELS[etat], legendgroup=etat, hoverinfo="skip",
                opacity=0.55 if etat == "Non évalué" else 0.95))
            if hover_pts is not None:
                hp = hover_pts[hover_pts.seg.isin(idx)]
                fig.add_trace(go.Scattermap(
                    lon=hp.lon, lat=hp.lat, mode="markers", legendgroup=etat, showlegend=False,
                    marker=dict(size=14, color=ETAT_COLORS[etat], opacity=0),
                    # liste JSON simple : dcc.Graph ne relit pas les tableaux binaires de Plotly dans clickData
                    customdata=hp.seg.astype(int).tolist(),
                    text=roads.loc[hp.seg, "hover"].values, hovertemplate="%{text}<extra></extra>",
                    name=ETAT_LABELS[etat]))
    if "ae" in layers and len(ae):
        fig.add_trace(go.Scattermap(
            lon=ae.lon, lat=ae.lat, mode="markers", name=f"Auto-écoles ({len(ae)})",
            marker=dict(size=8, color=INK, opacity=0.9),
            cluster=dict(enabled=True, color=INK, opacity=0.7, size=[12, 17, 23], step=[5, 25], maxzoom=11),
            customdata=np.stack([ae.nom, ae.localite, ae.prefecture, ae.agrement], axis=1),
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} · %{customdata[2]}<br>Statut : "
                          "%{customdata[3]}<extra></extra>"))
    if selected:
        fig.add_trace(go.Choroplethmap(
            geojson=geojson, locations=selected, z=[1] * len(selected), featureidkey="id",
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
            marker=dict(line=dict(color=INK, width=2.6)), hoverinfo="skip", name="Sélection"))
    fig.update_layout(
        map=dict(style=BASEMAP_STYLE if basemap else MAP_STYLE, center=view["center"], zoom=view["zoom"]),
        margin=dict(l=0, r=0, t=0, b=0),
        height=height, paper_bgcolor=SURFACE, font=dict(family=FONT, color=INK_2), separators=", ",
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=LINE, font=dict(family=FONT, size=12, color=INK)),
        legend=dict(x=0.01, y=0.01, xanchor="left", yanchor="bottom", bgcolor="rgba(255,255,255,0.9)",
                    bordercolor=LINE, borderwidth=1, font=dict(size=11, color=INK_2), itemclick="toggle"),
        showlegend=True, uirevision=f"{mode}-{selected}")
    return fig


def state_by_region(reg: pd.DataFrame, mode: str, states: list[str], selected_region=None) -> go.Figure:
    d = reg[reg.km_evalue > 0].copy()
    if d.empty or not states:
        return empty(hint="Sélectionnez au moins un état routier.")
    d = d.iloc[::-1]
    fig = go.Figure()
    for e in ETATS:
        if e not in states:
            continue
        km = d[f"km_{e.lower()}"]
        val = 100 * km / d.km_evalue if mode == "part" else km
        fig.add_trace(go.Bar(
            y=d.region, x=val, orientation="h", name=ETAT_LABELS[e], marker=dict(color=ETAT_COLORS[e]),
            customdata=np.stack([km, 100 * km / d.km_evalue], axis=1),
            hovertemplate=f"<b>%{{y}}</b> — {ETAT_LABELS[e]}<br>%{{customdata[0]:,.0f}} km "
                          "(%{customdata[1]:.0f} % du réseau évalué)<extra></extra>"))
    theme(fig, 280)
    fig.update_layout(barmode="stack", bargap=0.35)
    fig.update_xaxes(ticksuffix=" %" if mode == "part" else " km", showgrid=True, gridcolor=GRID, showline=False,
                     range=[0, 100] if mode == "part" else None)
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12, color=INK),
                     ticktext=[f"<b>{r}</b>" if r == selected_region else r for r in d.region], tickvals=list(d.region))
    return fig


def ae_ranking(pref: pd.DataFrame, nat_rate: float, selected=None, n: int = 16) -> go.Figure:
    """Préfectures les moins dotées en auto-écoles (barres horizontales, lisibles)."""
    d = pref.sort_values(["ae_100k", "population"], ascending=[True, False]).head(n)
    if d.empty:
        return empty()
    d = d.iloc[::-1]
    colors = [RED if v == 0 else (ORANGE if v < nat_rate / 2 else (GREY if v < nat_rate else GREEN)) for v in d.ae_100k]
    lines = [1.8 if selected and k in selected else 0 for k in d.prefecture_key]
    labels = [f"{fr_num(v, 2)}" if v > 0 else "aucune" for v in d.ae_100k]
    ylab = [f"{p} · {fr_num(h / 1e3)} k hab." for p, h in zip(d.prefecture, d.population)]
    fig = go.Figure(go.Bar(
        y=ylab, x=d.ae_100k.where(d.ae_100k > 0, 0.04), orientation="h",
        marker=dict(color=colors, line=dict(color=INK, width=lines)),
        text=labels, textposition="outside", textfont=dict(size=10.5, color=INK_2), cliponaxis=False,
        customdata=np.stack([d.region, d.ae_n, d.population, d.prefecture_key, d.ae_100k], axis=1),
        hovertemplate="<b>%{y}</b> (%{customdata[0]})<br>%{customdata[1]} auto-école(s) pour %{customdata[2]:,.0f} hab."
                      "<br><b>%{customdata[4]:.2f}</b> pour 100 000 hab.<extra></extra>"))
    fig.add_vline(x=nat_rate, line=dict(color=INK, width=1), opacity=0.7,
                  annotation=dict(text=f"moyenne nationale {fr_num(nat_rate, 1)}", font=dict(size=10.5, color=INK_2),
                                  yanchor="bottom", y=1, xanchor="right"))
    theme(fig, max(260, 22 * len(d) + 50), legend=False, margin=dict(l=8, r=40, t=22, b=8))
    fig.update_layout(bargap=0.3)
    fig.update_xaxes(showgrid=True, gridcolor=GRID, showline=False, range=[0, max(nat_rate * 1.15, d.ae_100k.max() * 1.2)])
    fig.update_yaxes(showgrid=False, tickfont=dict(size=11, color=INK_2))
    return fig


def cumul_matrix(pref: pd.DataFrame, selected=None) -> go.Figure:
    d = pref.dropna(subset=["part_mauvais"]).copy()
    if d.empty:
        return empty(hint="Aucune préfecture avec réseau évalué dans la sélection.")
    xm, ym = pref.ae_100k.median(), pref.part_mauvais.median()
    size = 9 + 30 * np.sqrt(d.population / pref.population.max())
    fig = go.Figure()
    fig.add_shape(type="rect", x0=-0.5, x1=xm, y0=ym, y1=108, fillcolor="rgba(179,38,30,0.06)", line=dict(width=0),
                  layer="below")
    fig.add_annotation(x=xm, y=104, xanchor="left", yanchor="top", showarrow=False, xshift=6,
                       text="← réseau dégradé et faible offre de formation", font=dict(size=10.5, color=RED))
    for prio in ["À surveiller", "Moyenne", "Élevée"]:
        g = d[d.priorite == prio]
        if g.empty:
            continue
        fig.add_trace(go.Scatter(
            x=g.ae_100k, y=g.part_mauvais, mode="markers", name=f"Priorité {prio.lower()}",
            marker=dict(size=size[g.index], color=PRIORITY_COLORS[prio], opacity=0.85,
                        line=dict(color=[INK if selected and k in selected else SURFACE for k in g.prefecture_key],
                                  width=[2.5 if selected and k in selected else 1.5 for k in g.prefecture_key])),
            customdata=np.stack([g.prefecture, g.region, g.population, g.score, g.prefecture_key], axis=1),
            hovertemplate="<b>%{customdata[0]}</b> (%{customdata[1]})<br>Auto-écoles / 100 000 hab. : %{x:.2f}"
                          "<br>Réseau en mauvais état ≈ %{y:.0f} %<br>Population : %{customdata[2]:,.0f}"
                          "<br>Score : %{customdata[3]:.0f}<extra></extra>"))
    lab = d.sort_values("score", ascending=False).head(6).sort_values("part_mauvais")
    for k, r in enumerate(lab.itertuples()):
        fig.add_annotation(x=r.ae_100k, y=r.part_mauvais, text=r.prefecture, showarrow=False,
                           xshift=-12 if k % 2 else 12, xanchor="right" if k % 2 else "left", yshift=8,
                           font=dict(size=10.5, color=INK))
    fig.add_vline(x=xm, line=dict(color="#C9C8C1", width=1))
    fig.add_hline(y=ym, line=dict(color="#C9C8C1", width=1))
    theme(fig, 360)
    fig.update_xaxes(title=dict(text="Auto-écoles pour 100 000 hab. (médiane en trait gris)", font=dict(size=11, color=MUTED)),
                     showgrid=True, gridcolor=GRID, range=[-0.5, max(4.5, d.ae_100k.max() * 1.05)])
    fig.update_yaxes(title=dict(text="Réseau évalué en mauvais état (%, estimé)", font=dict(size=11, color=MUTED)),
                     range=[-9, 108], ticksuffix=" %")
    return fig
