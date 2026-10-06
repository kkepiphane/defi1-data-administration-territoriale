"""Interactions : filtres synchronisés, sélection par clic, drill-down, exports. Aucun filtre ne casse l'interface."""
from __future__ import annotations

import math
from urllib.parse import parse_qs

import numpy as np
import pandas as pd
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.dash_table.Format import Format, Group, Scheme

from . import figures as fg, indicators as ind
from .cleaning import fr_num
from .geo import bbox_view
from .config import ETAT_COLORS, ETAT_LABELS, ETATS, PERMIS, REGIONS, UNAVAILABLE
from .layout import SAFETY_METRICS, VEHICLE_TYPES, VIEWS

NUM_TYPES = (int, float, np.integer, np.floating)
PRIO_SLUG = {"Élevée": "high", "Moyenne": "mid", "À surveiller": "low", "Indéterminée": "na"}


# ── Petites briques d'affichage ─────────────────────────────────────────────────────────

def is_na(v) -> bool:
    return v is None or (isinstance(v, NUM_TYPES) and (math.isnan(v) or math.isinf(v)))


def kpi(label, value, unit="", delta=None, good=None, foot=None, scope="nat", decimals=0, delta_unit="%",
        delta_ref=None, approx=False):
    """Tuile KPI. `good` : 'down' si une baisse est favorable, 'up' si une hausse l'est, None si neutre."""
    if is_na(value):
        val = html.Div(UNAVAILABLE, className="kpi-value na")
    else:
        val = html.Div([("≈ " if approx else "") + fr_num(value, decimals),
                        html.Span(unit, className="kpi-unit") if unit else None], className="kpi-value")
    d = None
    if delta is not None and not is_na(delta):
        arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "■")
        tone = "neutral"
        if good == "down":
            tone = "bad" if delta > 0 else "good"
        elif good == "up":
            tone = "good" if delta > 0 else "bad"
        sign = "+" if delta > 0 else ("−" if delta < 0 else "")
        d = html.Div([html.Span(arrow, className="arrow"),
                      f"{sign}{fr_num(abs(delta), 1 if abs(delta) < 10 else 0)} {delta_unit}",
                      html.Span(f" vs {delta_ref}" if delta_ref else "", className="delta-ref")],
                     className=f"kpi-delta {tone}")
    return html.Div([
        html.Div([html.Span(label, className="kpi-label"),
                  html.Span(className=f"scope-dot {scope}", title="Indicateur national" if scope == "nat"
                            else "Indicateur territorial (suit les filtres)")], className="kpi-top"),
        val, d, html.Div(foot, className="kpi-foot") if foot else None,
    ], className="kpi")


def state_bar(values: dict, total: float, show_labels=True):
    segs, legend = [], []
    for e in ETATS:
        v = values.get(e, 0) or 0
        if total and v > 0:
            pct = 100 * v / total
            segs.append(html.Div(style={"width": f"{pct}%", "background": ETAT_COLORS[e]}, className="sb-seg",
                                 title=f"{ETAT_LABELS[e]} : {fr_num(v, 1)} km ({fr_num(pct)} %)"))
            legend.append(html.Span([html.Span(className="sb-dot", style={"background": ETAT_COLORS[e]}),
                                     f"{e} {fr_num(pct)} %"],
                                    className="sb-item"))
    return html.Div([html.Div(segs, className="sb"), html.Div(legend, className="sb-legend") if show_labels else None])


def insight_items(items):
    if not items:
        return html.P("Aucune alerte calculable pour cette sélection.", className="empty-msg")
    out = []
    for it in items:
        label = {"danger": "Danger", "alerte": "Alerte", "ok": "Amélioration"}.get(it["niveau"], "Information")
        out.append(html.Div([
            html.Div([html.Span(className=f"insight-dot {it['niveau']}"), html.Span(label, className="insight-level")],
                     className="insight-top"),
            html.P(it["texte"], className="insight-text"),
        ], className="insight"))
    return out


def columns_for(df: pd.DataFrame, decimals: dict | None = None, labels: dict | None = None):
    cols = []
    for c in df.columns:
        spec = {"name": (labels or {}).get(c, c), "id": c}
        if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c]):
            dec = (decimals or {}).get(c, 0)
            spec.update(type="numeric", format=Format(precision=dec, scheme=Scheme.fixed, group=Group.yes, groups=3,
                                                      group_delimiter=" ", decimal_delimiter=","))
        cols.append(spec)
    return cols


def scope_pref(pref: pd.DataFrame, region, pref_key) -> pd.DataFrame:
    if pref_key:
        return pref[pref.prefecture_key == pref_key]
    if region:
        return pref[pref.region == region]
    return pref


def selected_keys(data, region, pref_key):
    if pref_key:
        return [pref_key]
    if region:
        return list(data.pref.loc[data.pref.region == region, "prefecture_key"])
    return None


def view_for(data, region, pref_key, width=700, height=470):
    bounds = data.views.get(pref_key) or data.views.get(region) or data.views["Togo"]
    pad = 2.6 if pref_key else (1.35 if region else 1.15)  # garder du contexte autour d'une préfecture
    return bbox_view(*bounds, width_px=width, height_px=height, pad=pad)


def period(df_index, years):
    return (df_index >= years[0]) & (df_index <= years[1])


# ── Enregistrement ──────────────────────────────────────────────────────────────────────

def register(app, data):
    pref_all = data.pref
    nat_ae_rate = pref_all.ae_n.sum() / pref_all.population.sum() * 1e5
    pref_region = dict(zip(pref_all.prefecture_key, pref_all.region))
    pref_name = dict(zip(pref_all.prefecture_key, pref_all.prefecture))
    flags = data.meta.get("flags", {})
    years_full = [int(data.immat.annee.min()), int(data.immat.annee.max())]
    tr = data.troncons.copy()
    tr["part_mauvais"] = 100 * tr.Mauvais / tr.Total
    seg_pref = data.roads.dropna(subset=["troncon_idx"]).groupby("troncon_idx").prefecture_key.agg(lambda s: sorted(set(s)))
    tr["prefectures"] = tr.index.map(seg_pref)

    # Liens profonds : ?vue=reseau&region=Kara&prefecture=KOZAH (partage d'une vue filtrée)
    @app.callback(Output("tabs", "value"), Output("f-region", "value", allow_duplicate=True),
                  Output("f-pref", "value", allow_duplicate=True), Input("url", "search"),
                  prevent_initial_call="initial_duplicate")
    def from_url(search):
        q = parse_qs((search or "").lstrip("?"))
        vue = q.get("vue", [None])[0]
        region = q.get("region", [None])[0]
        pref_key = (q.get("prefecture", [None])[0] or "").upper().replace("-", " ") or None
        if pref_key not in pref_region:
            pref_key = None
        if region not in REGIONS:
            region = pref_region.get(pref_key) if pref_key else None
        return (vue if vue in dict(VIEWS) else no_update,
                region if region else no_update, pref_key if pref_key else no_update)

    # En-tête
    @app.callback(Output("view-title", "children"), Input("tabs", "value"))
    def header(tab):
        return dict(VIEWS).get(tab, "")

    # Contrôleur de filtres : cohérence région ↔ préfecture, réinitialisation
    @app.callback(
        Output("f-region", "value"), Output("f-pref", "value"), Output("f-pref", "options"),
        Output("f-years", "value"), Output("f-vehicles", "value"), Output("f-permis", "value"),
        Output("f-etat", "value"),
        Input("f-region", "value"), Input("f-pref", "value"), Input("btn-reset", "n_clicks"),
    )
    def controller(region, pref_key, _reset):
        trig = ctx.triggered_id
        if trig == "btn-reset":
            opts = [{"label": r.prefecture, "value": r.prefecture_key}
                    for r in pref_all.sort_values("prefecture").itertuples()]
            return None, None, opts, [2010, years_full[1]], [], [], ETATS
        if trig == "f-pref" and pref_key:
            region = pref_region.get(pref_key, region)
        if pref_key and region and pref_region.get(pref_key) != region:
            pref_key = None
        sub = pref_all if not region else pref_all[pref_all.region == region]
        opts = [{"label": r.prefecture, "value": r.prefecture_key} for r in sub.sort_values("prefecture").itertuples()]
        return region, pref_key, opts, no_update, no_update, no_update, no_update

    # Sélection par clic (vue d'ensemble)
    @app.callback(Output("f-region", "value", allow_duplicate=True), Output("f-pref", "value", allow_duplicate=True),
                  Input("ov-map", "clickData"), Input("ov-rank", "clickData"), prevent_initial_call=True)
    def overview_click(map_click, rank_click):
        key = None
        if ctx.triggered_id == "ov-map" and map_click:
            key = map_click["points"][0].get("location")
        elif ctx.triggered_id == "ov-rank" and rank_click:
            key = rank_click["points"][0]["customdata"][3]
        if key not in pref_region:
            return no_update, no_update
        return pref_region[key], key

    # Sélection par clic (réseau & formation)
    @app.callback(Output("f-region", "value", allow_duplicate=True), Output("f-pref", "value", allow_duplicate=True),
                  Input("net-map", "clickData"), Input("net-state", "clickData"), Input("net-ae", "clickData"),
                  Input("net-matrix", "clickData"), prevent_initial_call=True)
    def network_click(map_click, state_click, ae_click, matrix_click):
        trig = ctx.triggered_id
        try:
            if trig == "net-map" and map_click:
                key = map_click["points"][0].get("location")
                if key in pref_region:
                    return pref_region[key], key
            elif trig == "net-state" and state_click:
                reg = state_click["points"][0]["y"]
                if reg in REGIONS:
                    return reg, None
            elif trig == "net-ae" and ae_click:
                key = ae_click["points"][0]["customdata"][3]
                return pref_region[key], key
            elif trig == "net-matrix" and matrix_click:
                key = matrix_click["points"][0]["customdata"][4]
                return pref_region[key], key
        except (KeyError, IndexError, TypeError):
            pass
        return no_update, no_update

    # Pastilles de périmètre
    @app.callback(Output("scope-chips", "children"), Output("f-years-label", "children"),
                  Input("f-years", "value"), Input("f-region", "value"), Input("f-pref", "value"),
                  Input("f-vehicles", "value"), Input("f-permis", "value"), Input("f-etat", "value"),
                  Input("tabs", "value"))
    def chips(years, region, pref_key, veh, perm, etat, tab):
        y = f"{years[0]}–{years[1]}"
        items = [html.Span(["Période ", html.B(y)], className="chip")]
        terr = pref_name.get(pref_key) and f"{pref_name[pref_key]} ({pref_region[pref_key]})" or region or "Togo entier"
        items.append(html.Span(["Territoire ", html.B(terr)], className="chip" + (" on" if region or pref_key else "")))
        if veh and len(veh) < len(VEHICLE_TYPES):
            items.append(html.Span(["Véhicules ", html.B(f"{len(veh)} / {len(VEHICLE_TYPES)}")], className="chip on"))
        if perm and len(perm) < len(PERMIS):
            items.append(html.Span(["Permis ", html.B(f"{len(perm)} / {len(PERMIS)}")], className="chip on"))
        if len(etat or []) < len(ETATS):
            items.append(html.Span(["États ", html.B(", ".join(etat) if etat else "aucun")], className="chip on"))
        if (region or pref_key) and tab in ("mobilite", "securite"):
            items.append(html.Span("Séries nationales : le filtre territorial ne s'applique pas à cette vue",
                                   className="chip warn"))
        return items, y

    # Poids du score
    @app.callback(Output("weights", "data"), Output("w-etat-val", "children"), Output("w-formation-val", "children"),
                  Output("w-desserte-val", "children"), Output("reco-score-top", "children"),
                  Input("w-etat", "value"), Input("w-formation", "value"), Input("w-desserte", "value"))
    def weights(we, wf, wd):
        w = {"etat": we or 0, "formation": wf or 0, "desserte": wd or 0}
        tot = sum(w.values())
        labels = [f"{fr_num(100 * v / tot) if tot else 0} %" for v in w.values()]
        if not tot:
            return w, *labels, html.P("Tous les poids sont à zéro : le score ne peut pas être calculé.", className="empty-msg")
        sc = ind.priority_scores(pref_all, w).sort_values("score", ascending=False).head(5)
        rows = [html.Tr([html.Td(f"{int(r.rang)}."), html.Td(r.prefecture, className="strong"), html.Td(r.region),
                         html.Td(fr_num(r.score), className="num"),
                         html.Td(html.Span(r.priorite, className=f"pill p-{PRIO_SLUG.get(r.priorite, 'na')}"))])
                for r in sc.itertuples()]
        return w, *labels, html.Table(html.Tbody(rows), className="tbl tbl-compact")

    def scored(w):
        return ind.priority_scores(pref_all, w or ind.DEFAULT_WEIGHTS)

    # ── Vue d'ensemble ────────────────────────────────────────────────────────────────
    @app.callback(
        Output("ov-kpis", "children"), Output("ov-index", "figure"), Output("ov-index-msg", "children"),
        Output("ov-insights", "children"), Output("ov-map", "figure"), Output("ov-map-msg", "children"),
        Output("ov-rank", "figure"), Output("ov-rank-msg", "children"),
        Input("f-years", "value"), Input("f-region", "value"), Input("f-pref", "value"), Input("f-vehicles", "value"),
        Input("f-permis", "value"), Input("weights", "data"),
    )
    def overview(years, region, pref_key, veh, perm, w):
        years = years or years_full
        s = data.safety.loc[period(data.safety.index, years)]
        iw = ind.immat_wide(data.immat, veh or None)
        iw = iw.loc[period(iw.index, years)]
        tot = iw.sum(axis=1) if not iw.empty else pd.Series(dtype=float)
        pw = ind.permis_wide(data.permis, perm or None)
        k = []
        y_im, v_im = ind.last_valid(tot)
        d_im, ref = ind.yoy(tot)
        k.append(kpi("Immatriculations", v_im, delta=d_im, delta_ref=ref, foot=f"{y_im or '—'} · types sélectionnés"))
        y_a, v_a = ind.last_valid(s.accidents)
        d_a, ref_a = ind.yoy(s.accidents)
        k.append(kpi("Accidents", v_a, delta=d_a, good="down", delta_ref=ref_a,
                     foot=f"{y_a} · national" if y_a else "hors période 2010–2022"))
        y_d, v_d = ind.last_valid(s.deces)
        d_d, ref_d = ind.yoy(s.deces)
        k.append(kpi("Décès", v_d, delta=d_d, good="down", delta_ref=ref_d,
                     foot=f"{y_d} · national" if y_d else "hors période 2010–2022"))
        y_t, v_t = ind.last_valid(s.taux_deces_100k)
        d_t, ref_t = ind.yoy(s.taux_deces_100k)
        k.append(kpi("Décès / 100 000 hab.", v_t, decimals=1, delta=d_t, good="down", delta_ref=ref_t,
                     foot=f"{y_t} · national" if y_t else "hors période 2010–2022"))
        # Territorial
        if pref_key:
            p = pref_all[pref_all.prefecture_key == pref_key].iloc[0]
            k.append(kpi("Réseau en mauvais état", p.part_mauvais, "%", scope="ter", approx=True,
                         foot=f"{p.prefecture} · ≈ {fr_num(p.km_evalue_est)} km évalués (2020)"))
            k.append(kpi("Auto-écoles / 100 000 hab.", p.ae_100k, decimals=1, scope="ter",
                         foot=f"{p.ae_n} auto-école(s) · moyenne nationale {fr_num(nat_ae_rate, 1)}"))
        else:
            sub_tr = tr[tr.region == region] if region else tr
            km_eval = sub_tr.Total.sum()
            part = 100 * sub_tr.Mauvais.sum() / km_eval if km_eval else np.nan
            k.append(kpi("Réseau en mauvais état", part, "%", scope="ter",
                         foot=f"{region or 'Togo'} · {fr_num(km_eval)} km évalués (2020)"))
            sp = scope_pref(pref_all, region, None)
            rate = sp.ae_n.sum() / sp.population.sum() * 1e5
            k.append(kpi("Auto-écoles / 100 000 hab.", rate, decimals=1, scope="ter",
                         foot=f"{sp.ae_n.sum()} auto-écoles · {region or 'Togo'}"))
        fig_idx, msg_idx = fg.overview_index(data.safety, tot, years, flags)
        ins = ind.insights(data.safety, iw, pw, data.reg, pref_all, tuple(years), region)
        if pref_key:
            p = pref_all[pref_all.prefecture_key == pref_key].iloc[0]
            ins = ins[:2] + [{"niveau": "danger" if p.ae_n == 0 else "alerte",
                              "texte": f"{p.prefecture} : {p.ae_n} auto-école(s) pour {fr_num(p.population)} hab. et "
                                       f"≈ {fr_num(p.part_mauvais)} % de son réseau évalué en mauvais état.",
                              "source": "Auto-écoles × RGPH-5 × état du réseau (estimation préfectorale)"}]
        sc = scored(w)
        sel = selected_keys(data, region, pref_key)
        fig_map = fg.priority_map(sc, data.pref_geojson, view_for(data, region, pref_key), sel, 470,
                                  data.region_geojson)
        high = sc[sc.priorite == "Élevée"].sort_values("score", ascending=False)
        msg_map = (f"{len(high)} préfecture(s) en priorité élevée, dont {', '.join(high.prefecture.head(3))}."
                   if len(high) else "Aucune préfecture en priorité élevée avec ces pondérations.")
        rank_scope = scope_pref(sc, region, None)
        fig_rank = fg.priority_bars(rank_scope, 12, sel)
        top = rank_scope.dropna(subset=["score"]).sort_values("score", ascending=False)
        msg_rank = (f"{top.iloc[0].prefecture} arrive en tête ({fr_num(top.iloc[0].score)} / 100)"
                    + (f" en {region}." if region else ".")) if len(top) else ""
        return k, fig_idx, msg_idx, insight_items(ins), fig_map, msg_map, fig_rank, msg_rank

    # ── Mobilité & permis ─────────────────────────────────────────────────────────────
    @app.callback(
        Output("mob-kpis", "children"), Output("mob-stack", "figure"), Output("mob-stack-msg", "children"),
        Output("mob-share", "figure"), Output("mob-share-msg", "children"), Output("mob-permis", "figure"),
        Output("mob-permis-msg", "children"), Output("mob-gap", "figure"), Output("mob-gap-msg", "children"),
        Output("mob-cyl", "figure"),
        Input("f-years", "value"), Input("f-vehicles", "value"), Input("f-permis", "value"),
        Input("mob-mode", "value"), Input("mob-pmode", "value"),
    )
    def mobilite(years, veh, perm, mode, pmode):
        years = years or years_full
        iw = ind.immat_wide(data.immat, veh or None)
        iw = iw.loc[period(iw.index, years)] if not iw.empty else iw
        tot = iw.sum(axis=1) if not iw.empty else pd.Series(dtype=float)
        pw = ind.permis_wide(data.permis, perm or None)
        pw = pw.loc[period(pw.index, years)] if not pw.empty else pw
        ptot = pw.sum(axis=1) if not pw.empty else pd.Series(dtype=float)
        k = []
        y1, v1 = ind.last_valid(tot)
        g, ref = ind.yoy(tot)
        k.append(kpi("Immatriculations", v1, delta=g, delta_ref=ref, foot=f"{y1 or '—'} · types sélectionnés"))
        c, c0, c1 = ind.cagr(tot)
        k.append(kpi("Croissance annuelle moyenne", c, "%", decimals=1, foot=f"TCAM {c0}–{c1}" if c0 else "période trop courte"))
        tot_var = 100 * (tot.iloc[-1] / tot.iloc[0] - 1) if len(tot) >= 2 and tot.iloc[0] else np.nan
        k.append(kpi("Évolution sur la période", tot_var, "%", foot=f"{int(tot.index[0])} → {int(tot.index[-1])}"
                     if len(tot) >= 2 else "période trop courte"))
        share = 100 * iw.loc[y1, "Deux-roues"] / tot.loc[y1] if y1 and "Deux-roues" in iw and tot.loc[y1] else np.nan
        k.append(kpi("Part des deux-roues", share, "%", foot=f"{y1} · immatriculations" if y1 else ""))
        yp, vp = ind.last_valid(ptot[ptot > 0] if len(ptot) else ptot)
        gp, refp = ind.yoy(ptot[ptot > 0] if len(ptot) else ptot)
        k.append(kpi("Permis délivrés", vp, delta=gp, delta_ref=refp, foot=f"{yp or '—'} · catégories sélectionnées"))
        ratio = 100 * vp / tot.loc[yp] if yp and yp in tot.index and tot.loc[yp] else np.nan
        k.append(kpi("Permis / 100 immatriculations", ratio, decimals=1, foot=f"{yp} · même année" if yp else ""))

        fig_stack = fg.immat_stack(iw, mode, flags)
        msg_stack = ""
        if not iw.empty and len(iw) >= 2 and tot.iloc[0]:
            contrib = (iw.iloc[-1] - iw.iloc[0]).sort_values(ascending=False)
            total_gain = tot.iloc[-1] - tot.iloc[0]
            lead = contrib.index[0]
            msg_stack = (f"De {int(iw.index[0])} à {int(iw.index[-1])}, les immatriculations passent de {fr_num(tot.iloc[0])} "
                         f"à {fr_num(tot.iloc[-1])} ; « {lead} » pèse le plus dans la variation "
                         f"({'+' if contrib.iloc[0] >= 0 else ''}{fr_num(contrib.iloc[0])}).")
            if total_gain == 0:
                msg_stack = msg_stack.replace("pèse le plus dans la variation", "varie le plus")
        fig_share, msg_share = fg.share_line(iw)
        missing = [y for y in range(years[0], years[1] + 1) if 2007 <= y <= 2022 and (pw.empty or y not in pw.index)]
        fig_permis = fg.permis_stack(pw, pmode, flags, missing)
        msg_permis = ""
        if not pw.empty:
            last = pw.dropna(how="all").iloc[-1]
            if last.sum():
                top = last.sort_values(ascending=False)
                msg_permis = (f"En {int(pw.index[-1])}, « {top.index[0]} » représente {fr_num(100 * top.iloc[0] / last.sum())} % "
                              f"des {fr_num(last.sum())} permis délivrés.")
        imm_full = ind.immat_wide(data.immat, veh or None)
        fig_gap, msg_gap = fg.formation_gap(imm_full.loc[period(imm_full.index, years)] if not imm_full.empty else imm_full,
                                            pw, flags)
        fig_cyl = fg.cylindree(data.immat_cyl, years)
        return k, fig_stack, msg_stack, fig_share, msg_share, fig_permis, msg_permis, fig_gap, msg_gap, fig_cyl

    # ── Sécurité routière ─────────────────────────────────────────────────────────────
    metric_labels = dict(SAFETY_METRICS)

    @app.callback(
        Output("saf-kpis", "children"), Output("saf-multi", "figure"), Output("saf-multi-msg", "children"),
        Output("saf-map", "figure"), Output("saf-rate", "figure"), Output("saf-rate-msg", "children"),
        Output("saf-years", "figure"), Output("saf-years-msg", "children"), Output("saf-scatter", "figure"),
        Output("saf-scatter-msg", "children"), Output("saf-table", "data"), Output("saf-table", "columns"),
        Input("f-years", "value"), Input("saf-metric", "value"), Input("saf-x", "value"), Input("saf-y", "value"),
    )
    def securite(years, metric, xcol, ycol):
        years = years or years_full
        s = data.safety.loc[period(data.safety.index, years)]
        k = []
        for col, label, good, dec, unit in [("accidents", "Accidents", "down", 0, ""), ("blesses", "Blessés", "down", 0, ""),
                                            ("deces", "Décès", "down", 0, ""),
                                            ("taux_deces_100k", "Décès / 100 000 hab.", "down", 1, ""),
                                            ("deces_100_accidents", "Décès / 100 accidents", "down", 1, ""),
                                            ("accidents_10k_immat", "Accidents / 10 000 immat.", "down", 0, "")]:
            y, v = ind.last_valid(s[col]) if len(s) else (None, np.nan)
            dlt, ref = ind.yoy(s[col])
            k.append(kpi(label, v, unit, delta=dlt, good=good, delta_ref=ref, decimals=dec,
                         foot=f"{y} · national" if y else "hors période 2010–2022"))
        if s.empty:
            e = fg.empty(hint="Les accidents sont publiés de 2010 à 2022 : élargissez la période.")
            return (k, e, "", fg.togo_unavailable(data.pref_geojson, view_for(data, None, None, 380, 300)), e, "", e, "", e, "", [], [])
        multi = fg.safety_multiples(s, flags)
        d = s.deces.dropna()
        msg_multi = (f"{fr_num(s.accidents.sum())} accidents, {fr_num(s.blesses.sum())} blessés et {fr_num(d.sum())} décès "
                     f"cumulés de {int(s.index[0])} à {int(s.index[-1])} ; décès au plus haut en {int(d.idxmax())} "
                     f"({fr_num(d.max())}).")
        label = metric_labels.get(metric, metric)
        dec = ind.SAFETY_DECIMALS.get(metric, 1)
        flag_years = list(flags.get("Accidents", {}).keys()) if "accidents" in metric else []
        rate = fg.rate_chart(s, metric, label, dec, flag_years)
        r = s[metric].dropna()
        msg_rate = ""
        if len(r) >= 2:
            ch = r.iloc[-1] - r.iloc[0]
            msg_rate = (f"{label} : {fr_num(r.iloc[0], dec)} en {int(r.index[0])}, {fr_num(r.iloc[-1], dec)} en "
                        f"{int(r.index[-1])} ({'+' if ch >= 0 else '−'}{fr_num(abs(ch), dec)}).")

        yrs = fg.years_ranking(s, metric, label, dec)
        worst = r.sort_values(ascending=False).head(3) if len(r) else r
        msg_years = ("Années les plus critiques : " + ", ".join(f"{int(i)} ({fr_num(v, dec)})" for i, v in worst.items())
                     + ".") if len(worst) else ""
        xl = "Immatriculations de l'année" if xcol == "immatriculations" else "Deux-roues immatriculés"
        yl = "Accidents" if ycol == "accidents" else "Décès"
        rr, n = ind.pearson(s[xcol], s[ycol])
        scat = fg.motor_scatter(s, xcol, ycol, xl, yl, rr, n)
        if is_na(rr):
            msg_sc = "Pas assez d'années pour calculer une corrélation."
        else:
            force = "forte" if abs(rr) >= 0.7 else ("modérée" if abs(rr) >= 0.4 else "faible")
            msg_sc = f"Corrélation {force} : r = {fr_num(rr, 2)} sur {n} années."
        tab = s.reset_index()
        tab["anomalie"] = tab.annee.map(lambda y: "; ".join(f"{k2} {y} : {v[y].lower()}" for k2, v in flags.items()
                                                            if y in v and k2 in ("Accidents", "Décès", "Blessés")))
        tab = tab[["annee", "accidents", "blesses", "deces", "taux_accidents_100k", "taux_deces_100k",
                   "deces_100_accidents", "blesses_par_accident", "immatriculations", "accidents_10k_immat",
                   "deces_10k_immat", "pop_implicite", "anomalie"]]
        labels = {**ind.SAFETY_LABELS, "annee": "Année", "anomalie": "Anomalie signalée"}
        cols = columns_for(tab, {**ind.SAFETY_DECIMALS}, labels)
        for c in cols:
            if c["id"] == "annee":
                c.pop("format", None)
                c["type"] = "text"
        tab["annee"] = tab.annee.astype(str)
        return (k, multi, msg_multi, fg.togo_unavailable(data.pref_geojson, view_for(data, None, None, 380, 300)), rate, msg_rate, yrs,
                msg_years, scat, msg_sc, tab.to_dict("records"), cols)

    # ── Réseau routier & formation ────────────────────────────────────────────────────
    @app.callback(
        Output("net-kpis", "children"), Output("net-map", "figure"), Output("net-map-msg", "children"),
        Output("net-state", "figure"), Output("net-state-msg", "children"), Output("net-ae", "figure"),
        Output("net-ae-msg", "children"), Output("net-matrix", "figure"), Output("net-matrix-msg", "children"),
        Output("net-troncons", "data"), Output("net-troncons", "columns"), Output("net-troncons-msg", "children"),
        Input("f-region", "value"), Input("f-pref", "value"), Input("f-etat", "value"), Input("net-mode", "value"),
        Input("net-layers", "value"), Input("net-smode", "value"), Input("weights", "data"),
    )
    def reseau(region, pref_key, etats, mode, layers, smode, w):
        etats = etats or []
        sc = scored(w)
        sp = scope_pref(sc, region, pref_key)
        sel = selected_keys(data, region, pref_key)
        # KPI
        k = []
        roads_sc = data.roads if not (region or pref_key) else data.roads[data.roads.prefecture_key.isin(sp.prefecture_key)]
        k.append(kpi("Routes classées", roads_sc.km.sum(), " km", scope="ter",
                     foot=f"{len(roads_sc)} segments géolocalisés"))
        if pref_key:
            p = sp.iloc[0]
            evalv = {e: p[f"km_{e.lower()}_est"] for e in ETATS}
            km_eval, approx = p.km_evalue_est, True
        else:
            sub = tr[tr.region == region] if region else tr
            evalv = {e: sub[e].sum() for e in ETATS}
            km_eval, approx = sub.Total.sum(), False
        pct = (lambda e: 100 * evalv[e] / km_eval if km_eval else np.nan)
        k.append(kpi("Réseau en bon état", pct("Bon"), "%", scope="ter", approx=approx,
                     foot=f"{fr_num(evalv['Bon'])} km sur {fr_num(km_eval)} km évalués"))
        k.append(kpi("Réseau en mauvais état", pct("Mauvais"), "%", scope="ter", approx=approx,
                     foot=f"{fr_num(evalv['Mauvais'])} km · 2020"))
        k.append(kpi("Réseau en travaux", pct("Travaux"), "%", scope="ter", approx=approx,
                     foot=f"{fr_num(evalv['Travaux'])} km · 2020"))
        pop = sp.population.sum()
        k.append(kpi("Auto-écoles / 100 000 hab.", sp.ae_n.sum() / pop * 1e5 if pop else np.nan, decimals=1, scope="ter",
                     foot=f"{sp.ae_n.sum()} auto-écoles · nat. {fr_num(nat_ae_rate, 1)}"))
        n_ae = sp.ae_n.sum()
        k.append(kpi("Auto-écoles non agréées", 100 * sp.ae_non_agreees.sum() / n_ae if n_ae else np.nan, "%",
                     scope="ter", foot=f"{sp.ae_non_agreees.sum()} sur {n_ae}" if n_ae else "aucune auto-école"))
        # Carte
        ae = data.auto_ecoles if not (region or pref_key) else data.auto_ecoles[
            data.auto_ecoles.prefecture_key.isin(sp.prefecture_key)]
        roads_map = data.roads[data.roads.etat.isin(etats + ["Non évalué"])]
        fig_map = fg.road_map(roads_map, data.road_lines, ae, sc, data.pref_geojson, view_for(data, region, pref_key, 760, 620),
                              etats, layers or [], sel, mode, 620, data.road_hover, data.region_geojson)
        if mode == "formation":
            zero = sp[sp.ae_n == 0]
            msg_map = (f"{len(zero)} préfecture(s) sans auto-école ({fr_num(zero.population.sum())} hab.) dans la sélection."
                       if len(zero) else "Toutes les préfectures de la sélection ont au moins une auto-école.")
        else:
            msg_map = (f"{fr_num(pct('Mauvais'))} % du réseau évalué est en mauvais état et {fr_num(pct('Travaux'))} % en "
                       f"travaux ({'estimation préfectorale' if approx else 'relevé 2020'}).") if km_eval else \
                "Aucun tronçon évalué dans cette sélection."
        # État par région
        fig_state = fg.state_by_region(data.reg, smode, etats, region)
        rg = data.reg.dropna(subset=["part_mauvais"]).sort_values("part_mauvais", ascending=False)
        msg_state = (f"{rg.iloc[0].region} a la plus forte part en mauvais état ({fr_num(rg.iloc[0].part_mauvais)} %), "
                     f"{rg.iloc[-1].region} la plus faible ({fr_num(rg.iloc[-1].part_mauvais)} %).") if len(rg) else ""
        # Auto-écoles
        ae_scope = scope_pref(sc, region, None)
        fig_ae = fg.ae_ranking(ae_scope, nat_ae_rate, sel, n=16)
        z = ae_scope[ae_scope.ae_n == 0]
        msg_ae = (f"{len(z)} préfecture(s) sur {len(ae_scope)} n'ont aucune auto-école ; "
                  f"{fr_num(100 * ae_scope.ae_n.max() / max(ae_scope.ae_n.sum(), 1))} % de l'offre est dans "
                  f"{ae_scope.sort_values('ae_n').iloc[-1].prefecture}.") if len(ae_scope) else ""
        # Matrice
        fig_mx = fg.cumul_matrix(ae_scope, sel)
        xm, ym = pref_all.ae_100k.median(), pref_all.part_mauvais.median()
        cum = ae_scope[(ae_scope.ae_100k <= xm) & (ae_scope.part_mauvais >= ym)].sort_values("score", ascending=False)
        msg_mx = (f"{len(cum)} préfecture(s) cumulent réseau plus dégradé que la médiane et offre de formation sous la "
                  f"médiane : {', '.join(cum.prefecture.head(5))}{'…' if len(cum) > 5 else ''}.") if len(cum) else \
            "Aucune préfecture de la sélection ne cumule les deux déficits."
        # Tronçons
        t = tr.copy()
        if pref_key:
            t = t[t.prefectures.map(lambda v: isinstance(v, list) and pref_key in v)]
        elif region:
            t = t[t.region == region]
        if etats:
            t = t[(t[etats] > 0).any(axis=1)]
        else:
            t = t.iloc[0:0]
        out = t.assign(geolocalise=t.geolocalise.map({True: "Oui", False: "Non"}),
                       etat_dominant=t.etat_dominant.map(ETAT_LABELS))[
            ["troncon", "region", "reseau", "Total", "Bon", "Moyen", "Mauvais", "Travaux", "part_mauvais",
             "etat_dominant", "geolocalise", "methode_attribution"]].sort_values("Mauvais", ascending=False)
        labels = {"troncon": "Tronçon", "region": "Région", "reseau": "Réseau", "Total": "Km évalués", "Bon": "Bon (km)",
                  "Moyen": "Moyen (km)", "Mauvais": "Mauvais (km)", "Travaux": "Travaux (km)",
                  "part_mauvais": "% mauvais", "etat_dominant": "État majoritaire", "geolocalise": "Géolocalisé",
                  "methode_attribution": "Rattachement"}
        cols = columns_for(out, {"Total": 1, "Bon": 1, "Moyen": 1, "Mauvais": 1, "Travaux": 1, "part_mauvais": 0}, labels)
        out = out.fillna({"region": "Non attribuée"})
        msg_t = (f"{len(out)} tronçon(s) · {fr_num(out.Mauvais.sum())} km en mauvais état sur {fr_num(out.Total.sum())} km"
                 + (" (longueur totale des tronçons qui traversent la préfecture)." if pref_key else ".")
                 if len(out) else "Aucun tronçon ne correspond à la sélection (vérifiez le filtre État routier).")
        return (k, fig_map, msg_map, fig_state, msg_state, fig_ae, msg_ae, fig_mx, msg_mx, out.to_dict("records"), cols,
                msg_t)

    # Drill-down : région → préfecture → tronçon / auto-écoles
    @app.callback(Output("net-detail", "children"), Output("net-detail-msg", "children"),
                  Input("f-region", "value"), Input("f-pref", "value"), Input("net-map", "clickData"),
                  Input("weights", "data"))
    def detail(region, pref_key, click, w):
        if ctx.triggered_id == "net-map" and click:
            pt = click["points"][0]
            cd = pt.get("customdata")
            if isinstance(cd, (int, float)) and not isinstance(cd, bool) and int(cd) in data.roads.index:
                return troncon_detail(int(cd)), None
        sc = scored(w)
        if pref_key:
            return pref_detail(sc[sc.prefecture_key == pref_key].iloc[0]), None
        if region:
            return region_detail(region, sc), None
        return national_detail(sc), None

    def troncon_detail(seg_idx):
        seg = data.roads.loc[seg_idx]
        if pd.isna(seg.troncon_idx):
            return html.Div([
                html.H3(seg.route_nom), html.P(f"{seg.route_type} · {seg.route_recouvrement}", className="muted"),
                html.P(f"{seg.prefecture} ({seg.region}) · segment de {fr_num(seg.km, 1)} km"),
                html.P("Ce segment n'appartient à aucun tronçon du relevé d'état 2020 : état non renseigné.",
                       className="empty-msg"),
            ])
        t = tr.loc[int(seg.troncon_idx)]
        prefs = ", ".join(pref_name.get(p, p) for p in (t.prefectures if isinstance(t.prefectures, list) else []))
        return html.Div([
            html.H3(t.troncon), html.P(f"{t.reseau} · {t.region or 'région non attribuée'}", className="muted"),
            html.Div([html.Div([html.Span(fr_num(t.Total, 1), className="dv"), html.Span("km évalués", className="dl")]),
                      html.Div([html.Span(f"{fr_num(t.part_mauvais)} %", className="dv"),
                                html.Span("en mauvais état", className="dl")])], className="detail-stats"),
            state_bar({e: t[e] for e in ETATS}, t.Total),
            html.Dl([html.Dt("Préfectures traversées"), html.Dd(prefs or "—"),
                     html.Dt("Rattachement régional"), html.Dd(f"{t.methode_attribution} — {t.detail_attribution}"),
                     html.Dt("Libellé source"), html.Dd(t.troncon_source)], className="dl-grid"),
        ])

    def pref_detail(p):
        segs = data.roads[(data.roads.prefecture_key == p.prefecture_key) & data.roads.troncon_idx.notna()]
        tl = (segs.groupby("troncon_idx").km.sum().sort_values(ascending=False))
        trs = [html.Li([html.Span(className="sb-dot", style={"background": ETAT_COLORS[tr.loc[int(i), "etat_dominant"]]}),
                        html.Span(tr.loc[int(i), "troncon"], className="li-main"),
                        html.Span(f"{fr_num(km, 1)} km ici · {fr_num(tr.loc[int(i), 'part_mauvais'])} % mauvais",
                                  className="li-sub")]) for i, km in tl.items()]
        aes = data.auto_ecoles[data.auto_ecoles.prefecture_key == p.prefecture_key].sort_values(["agrement", "nom"])
        ael = [html.Li([html.Span(a.nom, className="li-main"),
                        html.Span(f"{a.localite} · {a.agrement}", className="li-sub")]) for a in aes.itertuples()]
        return html.Div([
            html.H3(p.prefecture), html.P(f"Région {p.region} · {fr_num(p.population)} hab. (2022)", className="muted"),
            html.Div([
                html.Div([html.Span(f"{fr_num(p.score)}", className="dv"),
                          html.Span(f"score · priorité {p.priorite.lower()}", className="dl")]),
                html.Div([html.Span(fr_num(p.ae_100k, 1), className="dv"), html.Span("auto-écoles / 100 000 hab.", className="dl")]),
                html.Div([html.Span(fr_num(p.densite_km_1000km2), className="dv"), html.Span("km / 1 000 km²", className="dl")]),
            ], className="detail-stats"),
            html.P(f"État estimé du réseau évalué (≈ {fr_num(p.km_evalue_est)} km)", className="detail-label"),
            state_bar({e: p[f"km_{e.lower()}_est"] for e in ETATS}, p.km_evalue_est) if p.km_evalue_est else
            html.P("Aucun tronçon évalué dans cette préfecture.", className="empty-msg"),
            html.P(f"Tronçons évalués ({len(trs)})", className="detail-label"),
            html.Ul(trs, className="detail-list") if trs else html.P("—", className="muted"),
            html.P(f"Auto-écoles ({len(ael)})", className="detail-label"),
            html.Ul(ael, className="detail-list") if ael else html.P("Aucune auto-école recensée.", className="empty-msg"),
        ])

    def region_detail(region, sc):
        r = data.reg[data.reg.region == region].iloc[0]
        rows = sc[sc.region == region].sort_values("score", ascending=False)
        body = [html.Tr([html.Td(x.prefecture, className="strong"), html.Td(fr_num(x.population), className="num"),
                         html.Td(fr_num(x.ae_100k, 1), className="num"),
                         html.Td(fr_num(x.part_mauvais) + " %" if not is_na(x.part_mauvais) else "—", className="num"),
                         html.Td(html.Span(fr_num(x.score), className=f"pill p-{PRIO_SLUG.get(x.priorite, 'na')}"), className="num")])
                for x in rows.itertuples()]
        return html.Div([
            html.H3(region), html.P(f"{fr_num(r.population)} hab. · {int(r.n_prefectures)} préfectures", className="muted"),
            html.P(f"État du réseau évalué ({fr_num(r.km_evalue)} km, relevé 2020)", className="detail-label"),
            state_bar({e: r[f"km_{e.lower()}"] for e in ETATS}, r.km_evalue),
            html.Table([html.Thead(html.Tr([html.Th("Préfecture"), html.Th("Pop.", className="num"),
                                            html.Th("AE/100k", className="num"), html.Th("≈ Mauvais", className="num"),
                                            html.Th("Score", className="num")])), html.Tbody(body)],
                       className="tbl tbl-compact"),
        ])

    def national_detail(sc):
        tot = tr.Total.sum()
        return html.Div([
            html.H3("Togo"), html.P(f"{fr_num(pref_all.population.sum())} hab. · 5 régions · 39 préfectures",
                                    className="muted"),
            html.P(f"Réseau évalué en 2020 : {fr_num(tot)} km (hors voiries urbaines)", className="detail-label"),
            state_bar({e: tr[e].sum() for e in ETATS}, tot),
            html.P("Cliquez une préfecture ou une route sur la carte.", className="muted howto-line"),
        ])

    # Comparaison de deux régions
    @app.callback(Output("cmp-table", "children"), Input("cmp-a", "value"), Input("cmp-b", "value"),
                  Input("weights", "data"))
    def compare(a, b, w):
        if not a or not b:
            return html.P("Choisissez deux régions.", className="empty-msg")
        reg = ind.priority_scores(data.reg, w or ind.DEFAULT_WEIGHTS).set_index("region")
        rows = [("Population 2022", "population", 0, None, ""), ("Auto-écoles", "ae_n", 0, None, ""),
                ("Auto-écoles / 100 000 hab.", "ae_100k", 2, -1, ""), ("Auto-écoles non agréées", "part_non_agreees", 0, 1, " %"),
                ("Routes classées", "km_classe", 0, None, " km"), ("Desserte (km / 1 000 km²)", "densite_km_1000km2", 1, -1, ""),
                ("Réseau évalué", "km_evalue", 0, None, " km"), ("En bon état", "part_bon", 0, -1, " %"),
                ("En mauvais état", "part_mauvais", 0, 1, " %"), ("En travaux", "part_travaux", 0, None, " %"),
                ("Km dégradés / 100 000 hab.", "km_mauvais_100k", 1, 1, ""), ("Score de priorité", "score", 0, 1, " / 100")]
        body = []
        for label, col, dec, worse, unit in rows:
            va, vb = reg.loc[a, col], reg.loc[b, col]
            ca = cb = "num"
            if worse and not (is_na(va) or is_na(vb)) and va != vb:
                if (va > vb) == (worse > 0):
                    ca += " worse"
                else:
                    cb += " worse"
            body.append(html.Tr([html.Td(label), html.Td(fr_num(va, dec) + unit, className=ca),
                                 html.Td(fr_num(vb, dec) + unit, className=cb)]))
        return html.Table([html.Thead(html.Tr([html.Th("Indicateur"), html.Th(a, className="num"), html.Th(b, className="num")])),
                           html.Tbody(body)], className="tbl tbl-compact cmp")

    # ── Recommandations ───────────────────────────────────────────────────────────────
    @app.callback(Output("reco-list", "children"), Output("reco-msg", "children"),
                  Input("f-region", "value"), Input("f-pref", "value"), Input("reco-cat", "value"),
                  Input("reco-prio", "value"))
    def reco(region, pref_key, cat, prio):
        r = filter_reco(region, pref_key, cat, prio)
        if r.empty:
            return html.P("Aucune recommandation pour cette sélection.", className="empty-msg"), "0 recommandation"
        cards = []
        for x in r.itertuples():
            cards.append(html.Article([
                html.Div([html.Span(x.priorite, className=f"pill p-{PRIO_SLUG.get(x.priorite, 'na')}"),
                          html.Span(x.categorie, className="reco-cat"), html.Span(x.id, className="reco-id")],
                         className="reco-top"),
                html.H4(x.territoire),
                html.P([html.Span("Problème mesuré ", className="reco-k"), x.probleme]),
                html.P([html.Span("Indicateur ", className="reco-k"), x.indicateur], className="reco-ind"),
                html.P([html.Span("Action ", className="reco-k"), x.action], className="reco-act"),
            ], className=f"reco reco-{PRIO_SLUG.get(x.priorite, 'na')}"))
        counts = r.priorite.value_counts()
        msg = (f"{len(r)} recommandation(s) : {counts.get('Élevée', 0)} élevée(s), {counts.get('Moyenne', 0)} moyenne(s), "
               f"{counts.get('À surveiller', 0)} à surveiller" + (f" — {pref_name.get(pref_key, region)}" if region or pref_key else ""))
        return cards, msg

    def filter_reco(region, pref_key, cat="all", prio="all"):
        r = data.recommandations
        if pref_key:
            name, reg_name = pref_name[pref_key], pref_region[pref_key]
            crossing = {tr.loc[i, "troncon"] for i in tr.index
                        if isinstance(tr.loc[i, "prefectures"], list) and pref_key in tr.loc[i, "prefectures"]}
            lome = pref_key in ("GOLFE", "AGOE NYIVE")
            keep = ((r.niveau == "National") | (r.territoire == reg_name)
                    | r.territoire.str.startswith(name + " (")
                    | ((r.niveau == "Tronçon") & r.territoire.map(lambda t: any(t.startswith(c + " (") for c in crossing)))
                    | ((reg_name == "Maritime") & ~lome & r.territoire.str.startswith("Maritime hors")))
            r = r[keep]
        elif region:
            r = r[(r.niveau == "National") | (r.territoire == region)
                  | r.territoire.str.endswith(f"({region})")
                  | ((region == "Maritime") & r.territoire.str.startswith("Maritime"))]
        if cat and cat != "all":
            r = r[r.categorie == cat]
        if prio and prio != "all":
            r = r[r.priorite == prio]
        return r

    # ── Qualité des données ───────────────────────────────────────────────────────────
    limits = limitations(data)

    @app.callback(Output("dq-table", "data"), Output("dq-table", "columns"), Output("dq-summary", "children"),
                  Output("dq-msg", "children"), Input("dq-view", "value"))
    def quality(view):
        df, labels = quality_frame(view)
        ctrl = data.controles.statut.value_counts()
        inv = data.inventory_files
        tiles = [(fr_num(len(inv)), "fichiers sources"), (fr_num(inv.lignes.sum()), "lignes lues"),
                 (f"{fr_num(np.average(inv.completude_pct, weights=inv.lignes * inv.colonnes), 2)} %", "complétude des cellules"),
                 (f"{ctrl.get('Conforme', 0)} / {len(data.controles)}", "contrôles conformes"),
                 (fr_num(len(data.anomalies)), "anomalies tracées"),
                 (fr_num(len(data.journal)), "transformations journalisées")]
        summary = [html.Div([html.Span(v, className="dq-v"), html.Span(l, className="dq-l")], className="dq-tile")
                   for v, l in tiles]
        msgs = {"inventaire": "Un fichier par ligne : rôle, période, clés géographiques, complétude, empreinte SHA-256.",
                "controles": f"{ctrl.get('Conforme', 0)} conformes, {ctrl.get('Écart', 0)} écart(s), "
                             f"{ctrl.get('Information', 0)} pour information.",
                "anomalies": "Valeurs atypiques, libellés erronés, manquants : aucune n'est supprimée.",
                "journal": "Chaque transformation, dans l'ordre d'exécution du pipeline.",
                "variables": "Toutes les colonnes de tous les fichiers, avec valeurs distinctes et manquantes.",
                "limites": "Ce que les données ne permettent pas de conclure."}
        return df.to_dict("records"), columns_for(df, {"completude_pct": 2, "taille_ko": 1}, labels), summary, msgs.get(view, "")

    def quality_frame(view):
        if view == "controles":
            return data.controles, {"source": "Source", "controle": "Contrôle", "resultat": "Résultat", "statut": "Statut"}
        if view == "anomalies":
            return data.anomalies, {"source": "Source", "element": "Élément", "type": "Type", "detail": "Détail",
                                    "traitement": "Traitement"}
        if view == "journal":
            return data.journal, {"n": "N°", "source": "Source", "operation": "Opération", "detail": "Détail",
                                  "lignes_concernees": "Lignes"}
        if view == "variables":
            return data.inventory_vars, {"fichier": "Fichier", "variable": "Variable", "valeurs_distinctes": "Distinctes",
                                         "manquantes": "Manquantes", "exemple": "Exemple"}
        if view == "limites":
            return limits, {"limite": "Limite", "consequence": "Conséquence", "traitement": "Traitement dans le tableau de bord"}
        inv = data.inventory_files.drop(columns=["cle", "format"])
        return inv, {"fichier": "Fichier", "role": "Rôle", "theme": "Thème", "format": "Format", "taille_ko": "Ko",
                     "lignes": "Lignes", "colonnes": "Colonnes", "periode": "Période",
                     "cles_geographiques": "Clés géographiques", "completude_pct": "Complétude %",
                     "doublons_exacts": "Doublons", "sha256": "SHA-256 (16 car.)"}

    # ── Exports CSV (un callback par vue : chaque bouton n'existe que dans son onglet) ──────────
    def send(df, fname):
        return dcc.send_data_frame(df.to_csv, fname, index=False, sep=";", decimal=",", encoding="utf-8-sig")

    @app.callback(Output("download", "data", allow_duplicate=True), Input({"type": "export", "name": "securite"}, "n_clicks"),
                  State("f-years", "value"), prevent_initial_call=True)
    def export_securite(n, years):
        if not n:
            return no_update
        years = years or years_full
        df = data.safety.loc[period(data.safety.index, years)].reset_index().rename(
            columns={**ind.SAFETY_LABELS, "annee": "Année"})
        return send(df, f"securite_routiere_{years[0]}-{years[1]}.csv")

    @app.callback(Output("download", "data", allow_duplicate=True), Input({"type": "export", "name": "troncons"}, "n_clicks"),
                  State("f-region", "value"), State("f-pref", "value"), State("f-etat", "value"),
                  prevent_initial_call=True)
    def export_troncons(n, region, pref_key, etats):
        if not n:
            return no_update
        t = tr.copy()
        if pref_key:
            t = t[t.prefectures.map(lambda v: isinstance(v, list) and pref_key in v)]
        elif region:
            t = t[t.region == region]
        t = t[(t[etats] > 0).any(axis=1)] if etats else t.iloc[0:0]
        t = t.assign(prefectures=t.prefectures.map(lambda v: ", ".join(pref_name.get(x, x) for x in v)
                                                   if isinstance(v, list) else ""))
        return send(t, f"troncons_etat_2020_{(pref_key or region or 'togo').lower().replace(' ', '-')}.csv")

    @app.callback(Output("download", "data", allow_duplicate=True),
                  Input({"type": "export", "name": "recommandations"}, "n_clicks"),
                  State("f-region", "value"), State("f-pref", "value"), State("reco-cat", "value"),
                  State("reco-prio", "value"), prevent_initial_call=True)
    def export_reco(n, region, pref_key, cat, prio):
        if not n:
            return no_update
        return send(filter_reco(region, pref_key, cat, prio), "recommandations.csv")

    @app.callback(Output("download", "data", allow_duplicate=True), Input({"type": "export", "name": "qualite"}, "n_clicks"),
                  State("dq-view", "value"), prevent_initial_call=True)
    def export_qualite(n, view):
        if not n:
            return no_update
        df, labels = quality_frame(view or "inventaire")
        return send(df.rename(columns=labels), f"qualite_{view or 'inventaire'}.csv")


def limitations(data) -> pd.DataFrame:
    tr = data.troncons
    nogeo = tr[~tr.geolocalise]
    flags = data.meta.get("flags", {})
    permis_flags = ", ".join(f"{k.split(' · ')[0]} {y}" for k, v in flags.items() if " · " in k for y in v)
    in_seg = 100 * data.roads.dans_prefecture_declaree.mean()
    in_ae = 100 * data.auto_ecoles.dans_prefecture_declaree.mean()
    rows = [
        ("Accidents, blessés, décès publiés au niveau national uniquement (2010–2022), sans lieu ni date fine",
         "Impossible d'identifier les régions, préfectures, tronçons ou mois les plus accidentogènes",
         "Analyses de sécurité nationales et annuelles ; carte des taux affichée en gris « indisponible » ; "
         "mortalité exclue du score territorial"),
        ("Immatriculations publiées en flux annuel, sans parc en circulation ni ventilation régionale",
         "Les taux « pour 10 000 véhicules » ne mesurent pas un risque par véhicule en circulation",
         "Ratio calculé sur les immatriculations de l'année et libellé comme tel ; pas de comparaison régionale"),
        (f"Permis : 2013 manquant (publié 0) ; valeurs atypiques ou ruptures ({permis_flags})",
         "Tendances de long terme fragiles pour certaines catégories",
         "2013 traité comme manquant ; valeurs atypiques conservées et cerclées sur les graphiques"),
        ("État du réseau : photographie unique de 2020, par tronçon, sans localisation des sections",
         "Pas d'évolution de l'état ; l'état d'un segment est celui de l'ensemble de son tronçon",
         f"Région : sommes exactes ; préfecture : estimation au prorata (« ≈ ») ; {len(nogeo)} tronçon(s) "
         f"({fr_num(nogeo.Total.sum())} km) non cartographiés"),
        ("Exports routes et auto-écoles incomplets par rapport à leur dictionnaire",
         "Praticabilité, zones inondables, dates de collecte, dates de création des auto-écoles indisponibles",
         "Indicateur « routes praticables » remplacé par l'état du réseau ; pas d'évolution de l'offre de formation"),
        ("Population : un seul millésime (RGPH-5 2022)",
         "Les taux territoriaux utilisent la population 2022 ; les séries annuelles utilisent la population "
         "implicite du taux publié",
         "Dénominateurs documentés pour chaque indicateur (onglet Méthodologie)"),
        ("Auto-écoles : recensement à date (export janvier 2025), statut d'agrément déclaré",
         "Aucune information sur la capacité, le nombre d'élèves ou les taux de réussite",
         "Indicateur d'accès (nombre pour 100 000 hab.) et part non agréée uniquement"),
        ("Limites administratives OCHA 2021 (source externe), Lomé Commune distincte de Golfe",
         "Superficies et contours approximatifs pour les préfectures récentes",
         f"Lomé Commune fusionnée avec Golfe (comme le RGPH-5) ; {fr_num(in_seg, 1)} % des segments et "
         f"{fr_num(in_ae, 1)} % des auto-écoles tombent dans leur préfecture déclarée"),
    ]
    return pd.DataFrame(rows, columns=["limite", "consequence", "traitement"])
