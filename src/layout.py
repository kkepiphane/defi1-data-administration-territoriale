"""Mise en page : barre latérale de filtres, en-tête, navigation et cinq vues."""
from __future__ import annotations

from dash import dash_table, dcc, html

from .config import ETAT_COLORS, ETAT_LABELS, ETATS, FONT, INK, INK_2, LINE, MUTED, PERMIS, REGIONS, VEHICULE_MAP
from .figures import config
from .indicators import DEFAULT_WEIGHTS, SAFETY_LABELS, SCORE_COMPONENTS, UNAVAILABLE_COMPONENTS

VIEWS = [("overview", "Vue d'ensemble"), ("mobilite", "Mobilité et permis"), ("securite", "Sécurité routière"),
         ("reseau", "Réseau routier et formation"), ("reco", "Recommandations et qualité")]
VEHICLE_TYPES = [v[0] for v in VEHICULE_MAP.values()]
DROPDOWN_LABELS = {"select_all": "Tout sélectionner", "deselect_all": "Tout désélectionner",
                   "selected_count": "{num_selected} sélectionné(s)", "search": "Rechercher",
                   "clear_search": "Effacer", "clear_selection": "Effacer la sélection",
                   "no_options_found": "Aucun résultat"}

TABLE_STYLE = dict(
    style_as_list_view=True,
    style_table={"overflowX": "auto"},
    style_header={"backgroundColor": "#FFFFFF", "color": MUTED, "fontWeight": "600", "fontSize": "11px",
                  "textTransform": "uppercase", "letterSpacing": ".04em", "borderBottom": "1px solid #CFCEC8",
                  "fontFamily": FONT, "padding": "8px 10px", "whiteSpace": "normal", "height": "auto"},
    style_cell={"fontFamily": FONT, "fontSize": "12.5px", "color": INK_2, "padding": "7px 10px",
                "borderBottom": f"1px solid {LINE}", "textAlign": "left", "whiteSpace": "normal", "height": "auto",
                "maxWidth": "380px", "minWidth": "70px"},
    style_data_conditional=[{"if": {"state": "active"}, "backgroundColor": "#F4F4F1", "border": f"1px solid {LINE}"},
                            {"if": {"row_index": "odd"}, "backgroundColor": "#FCFCFB"}],
    css=[{"selector": ".dash-spreadsheet-menu", "rule": "display:none"},
         {"selector": ".previous-next-container", "rule": f"font-family:{FONT};font-size:12px"}],
)


# ── Briques ─────────────────────────────────────────────────────────────────────────────

def card(title, *children, sub_id=None, sub=None, tools=None, foot=None, className="", badge=None, question=None):
    head = html.Div([
        html.Div([
            html.Div([html.H2(title), html.Span(badge, className="badge") if badge else None], className="card-title"),
            html.P(question, className="card-question") if question else None,
            html.P(sub, id=sub_id, className="card-sub") if sub_id else (html.P(sub, className="card-sub") if sub else None),
        ], className="card-head-text"),
        html.Div(tools, className="card-tools") if tools is not None else None,
    ], className="card-head")
    return html.Section([head, *children, html.P(foot, className="card-foot") if foot else None],
                        className=f"card {className}".strip())


def graph(id_, filename, height=None):
    return dcc.Loading(dcc.Graph(id=id_, config=config(filename), style={"height": f"{height}px"} if height else {}),
                       type="dot", color=INK, delay_show=250, overlay_style={"visibility": "visible", "opacity": 0.45})


def segmented(id_, options, value, className=""):
    return dcc.RadioItems(id=id_, options=[{"label": l, "value": v} for v, l in options], value=value,
                          className=f"seg {className}".strip(), inline=True, persistence=True,
                          persistence_type="memory")


def export_button(name, label="Exporter CSV"):
    return html.Button([html.Span("↓", className="btn-icon"), label], id={"type": "export", "name": name},
                       className="btn btn-ghost btn-sm", n_clicks=0, title="Télécharger les données filtrées (CSV)")


def kpis(id_, n):
    return html.Div(id=id_, className=f"kpis kpis-{n}")


def datatable(id_, page_size=10, wide_cols=()):
    style = dict(TABLE_STYLE)
    style["style_cell_conditional"] = [{"if": {"column_id": c}, "minWidth": "220px"} for c in wide_cols]
    return dash_table.DataTable(id=id_, data=[], columns=[], page_size=page_size, sort_action="native",
                                page_action="native", **style)


# ── Barre latérale ──────────────────────────────────────────────────────────────────────

def chips(id_, options, value, colors=None):
    opts = []
    for v, l in options:
        dot = html.Span(className="chip-dot", style={"background": colors[v]}) if colors else None
        opts.append({"label": html.Span([dot, l], className="chip-label"), "value": v})
    return dcc.Checklist(id=id_, options=opts, value=value, className="chips", inline=True)


def sidebar(data):
    years = (int(data.immat.annee.min()), int(data.immat.annee.max()))
    marks = {y: {"label": str(y)} for y in (years[0], 2000, 2010, years[1])}
    pref_opts = [{"label": r.prefecture, "value": r.prefecture_key} for r in data.pref.sort_values("prefecture").itertuples()]
    return html.Aside([
        html.Div([
            html.Div(html.Img(src="/assets/armoiries.png", alt="Armoiries de la République togolaise"),
                     className="brand-mark"),
            html.Div([html.Div("Mobilité & sécurité routière", className="brand-title"),
                      html.Div("Togo · tableau de bord décisionnel", className="brand-sub")]),
        ], className="brand"),
        html.Div([
            html.Div([html.Label("Période", htmlFor="f-years"), html.Span(id="f-years-label", className="filter-value")],
                     className="filter-head"),
            dcc.RangeSlider(id="f-years", min=years[0], max=years[1], step=1, value=[2010, years[1]], marks=marks,
                            allowCross=False, allow_direct_input=False,
                            tooltip={"placement": "bottom", "always_visible": False},
                            className="year-slider"),
        ], className="filter"),
        html.Div([
            html.Label("Région", htmlFor="f-region"),
            dcc.Dropdown(id="f-region", options=[{"label": r, "value": r} for r in REGIONS], value=None,
                         placeholder="Toutes les régions", clearable=True, searchable=False, labels=DROPDOWN_LABELS),
        ], className="filter"),
        html.Div([
            html.Label("Préfecture", htmlFor="f-pref"),
            dcc.Dropdown(id="f-pref", options=pref_opts, value=None, placeholder="Toutes les préfectures",
                         clearable=True, labels=DROPDOWN_LABELS),
        ], className="filter"),
        html.Div([
            html.Label("Type de véhicule", htmlFor="f-vehicles"),
            dcc.Dropdown(id="f-vehicles", options=[{"label": v, "value": v} for v in VEHICLE_TYPES], value=[],
                         multi=True, placeholder="Tous les types", searchable=False, labels=DROPDOWN_LABELS),
        ], className="filter"),
        html.Div([
            html.Label("Catégorie de permis", htmlFor="f-permis"),
            dcc.Dropdown(id="f-permis", options=[{"label": p, "value": p} for p in PERMIS], value=[],
                         multi=True, placeholder="Toutes les catégories", searchable=False, labels=DROPDOWN_LABELS),
        ], className="filter"),
        html.Div([html.Label("État routier"),
                  chips("f-etat", [(e, ETAT_LABELS[e].replace(" en cours", "")) for e in ETATS], ETATS, ETAT_COLORS)],
                 className="filter"),
        html.Button("Réinitialiser les filtres", id="btn-reset", className="btn btn-outline btn-block", n_clicks=0),
        html.Div([
            html.P([html.Span(className="scope-dot nat"), "National"]),
            html.P([html.Span(className="scope-dot ter"), "Territorial"]),
        ], className="side-legend"),
    ], className="sidebar")



# ── Vues ─────────────────────────────────────────────────────────────────────────────────

def view_overview(data):
    return html.Div([
        kpis("ov-kpis", 6),
        html.Div([
            card("Motorisation, accidents, décès : qui progresse le plus vite ?",
                 graph("ov-index", "evolution-indices"), sub_id="ov-index-msg", className="span-2", badge="National"),
            card("Alertes", html.Div(id="ov-insights", className="insights"), className="insight-card"),
        ], className="grid grid-3"),
        html.Div([
            card("Où agir en priorité ?", graph("ov-map", "carte-priorites", 470), sub_id="ov-map-msg",
                 badge="Territorial", className="span-2"),
            card("Préfectures les plus prioritaires", graph("ov-rank", "classement-priorites"), sub_id="ov-rank-msg",
                 badge="Territorial",
                 foot="Rouge ≥ 65 · orange 45–65 · gris < 45"),
        ], className="grid grid-3"),
    ], className="view")


def view_mobilite(data):
    return html.Div([
        kpis("mob-kpis", 6),
        html.Div([
            card("Quelles catégories tirent les immatriculations ?", graph("mob-stack", "immatriculations-categories"),
                 sub_id="mob-stack-msg", className="span-2", badge="National",
                 tools=segmented("mob-mode", [("volume", "Volumes"), ("part", "Parts %")], "volume")),
            card("Poids des deux-roues", graph("mob-share", "part-deux-roues"), sub_id="mob-share-msg", badge="National"),
        ], className="grid grid-3"),
        html.Div([
            card("Quels permis sont délivrés ?", graph("mob-permis", "permis-categories"), sub_id="mob-permis-msg",
                 className="span-2", badge="National",
                 tools=segmented("mob-pmode", [("volume", "Volumes"), ("part", "Parts %")], "volume")),
            card("La formation suit-elle la motorisation ?", graph("mob-gap", "ratio-permis-vehicules"),
                 sub_id="mob-gap-msg", badge="National"),
        ], className="grid grid-3"),
        html.Div([
            card("Deux-roues par cylindrée", graph("mob-cyl", "deux-roues-cylindree"), badge="National"),
            html.Section([
                html.Div("i", className="notice-icon"),
                html.Div([
                    html.H3("Comparaison régionale indisponible"),
                    html.P("Immatriculations et permis ne sont publiés qu'au niveau national."),
                ]),
            ], className="card notice span-2"),
        ], className="grid grid-3"),
    ], className="view")


SAFETY_METRICS = [("taux_deces_100k", "Décès / 100 000 hab."), ("taux_accidents_100k", "Accidents / 100 000 hab."),
                  ("deces_100_accidents", "Décès / 100 accidents"), ("accidents_10k_immat", "Accidents / 10 000 immat."),
                  ("deces_10k_immat", "Décès / 10 000 immat.")]


def view_securite(data):
    return html.Div([
        kpis("saf-kpis", 6),
        html.Div([
            card("Accidents, blessés et décès : l'évolution annuelle", graph("saf-multi", "accidents-blesses-deces"),
                 sub_id="saf-multi-msg", className="span-2", badge="National"),
            card("Carte des taux par territoire", dcc.Graph(id="saf-map", config={"displayModeBar": False}),
                 badge="Indisponible", sub="Accidents publiés au niveau national uniquement."),
        ], className="grid grid-3"),
        html.Div([
            card("Le risque routier baisse-t-il ?", graph("saf-rate", "taux-securite"), sub_id="saf-rate-msg",
                 className="span-2", badge="National",
                 tools=segmented("saf-metric", SAFETY_METRICS, "taux_deces_100k", "seg-wrap")),
            card("Années les plus critiques", graph("saf-years", "classement-annees"), sub_id="saf-years-msg",
                 badge="National"),
        ], className="grid grid-3"),
        html.Div([
            card("Plus de véhicules, plus d'accidents ?", graph("saf-scatter", "motorisation-accidentologie"),
                 sub_id="saf-scatter-msg", badge="National",
                 tools=html.Div([
                     segmented("saf-x", [("immatriculations", "Toutes immat."), ("immat_deux_roues", "Deux-roues")],
                               "immatriculations"),
                     segmented("saf-y", [("accidents", "Accidents"), ("deces", "Décès")], "accidents"),
                 ], className="tool-stack")),
            card("Tableau annuel détaillé", datatable("saf-table", 13, wide_cols=("anomalie",)), className="span-2", badge="National",
                 tools=export_button("securite")),
        ], className="grid grid-3"),
    ], className="view")


def view_reseau(data):
    return html.Div([
        kpis("net-kpis", 6),
        html.Div([
            card("Où le réseau est-il dégradé, où manque la formation ?", graph("net-map", "carte-reseau", 620),
                 sub_id="net-map-msg", className="span-2", badge="Territorial",
                 tools=html.Div([
                     segmented("net-mode", [("reseau", "État des routes"), ("formation", "Accès à la formation")],
                               "reseau"),
                     dcc.Checklist(id="net-layers", options=[{"label": "Routes", "value": "routes"},
                                                             {"label": "Auto-écoles", "value": "ae"},
                                                             {"label": "Fond de plan (internet)", "value": "fond"}],
                                   value=["routes", "ae"], inline=True, className="checks", persistence=True,
                                   persistence_type="memory"),
                 ], className="tool-stack"),
                 foot="Couleur = état majoritaire du tronçon (2020)"),
            card("Détail du territoire", html.Div(id="net-detail", className="detail"), sub_id="net-detail-msg",
                 className="detail-card"),
        ], className="grid grid-3"),
        html.Div([
            card("Quelles régions ont le réseau le plus dégradé ?", graph("net-state", "etat-reseau-regions"),
                 sub_id="net-state-msg", badge="Territorial",
                 tools=segmented("net-smode", [("part", "Parts %"), ("km", "Kilomètres")], "part")),
            card("Quelles préfectures manquent d'auto-écoles ?", graph("net-ae", "auto-ecoles-prefectures"),
                 sub_id="net-ae-msg", badge="Territorial"),
        ], className="grid grid-2"),
        html.Div([
            card("Territoires cumulant réseau dégradé et faible formation", graph("net-matrix", "matrice-cumul"),
                 sub_id="net-matrix-msg", badge="Territorial"),
            card("Comparer deux régions", html.Div([
                html.Div([
                    dcc.Dropdown(id="cmp-a", options=REGIONS, value="Savanes", clearable=False, searchable=False),
                    html.Span("vs", className="vs"),
                    dcc.Dropdown(id="cmp-b", options=REGIONS, value="Plateaux", clearable=False, searchable=False),
                ], className="cmp-pickers"),
                html.Div(id="cmp-table"),
            ]), badge="Territorial"),
        ], className="grid grid-2"),
        card("Tronçons évalués : lesquels traiter d'abord ?", datatable("net-troncons", 12, wide_cols=("troncon",)), sub_id="net-troncons-msg",
             tools=export_button("troncons"), badge="Territorial"),
    ], className="view")


def methodology(data):
    defs = [
        ("Immatriculations", "Nombre de véhicules immatriculés dans l'année (flux), par type ; total = somme des types "
                             "sélectionnés. Croissance annuelle = (Nₜ / Nₜ₋₁ − 1) × 100 ; TCAM = (N_fin / N_début)^(1/années) − 1."),
        ("Part des deux-roues", "Deux-roues ÷ immatriculations de l'année (types sélectionnés) × 100."),
        ("Permis pour 100 véhicules", "Permis A ÷ deux-roues immatriculés × 100 ; permis B ÷ (voitures + utilitaires "
                                      "légers) × 100, même année."),
        ("Taux d'accidents pour 100 000 hab.", "Valeur publiée (libellé source erroné « accidents mortels »), "
                                               "vérifiée : accidents ÷ population × 100 000."),
        ("Taux de décès pour 100 000 hab.", "Décès ÷ population implicite × 100 000, où population implicite = accidents ÷ "
                                            "taux publié × 100 000 (2022 : identique au RGPH-5)."),
        ("Décès pour 100 accidents", "Indicateur de gravité : décès ÷ accidents × 100."),
        ("Accidents (décès) pour 10 000 immatriculations", "Accidents (décès) ÷ immatriculations de l'année × 10 000. "
                                                          "Proxy de tendance : le parc en circulation n'est pas publié."),
        ("Part du réseau en mauvais état", "Km « mauvais » ÷ km évalués × 100 (relevé 2020). Région : somme exacte des "
                                           "tronçons rattachés. Préfecture : estimation (km de chaque segment × répartition "
                                           "par état de son tronçon)."),
        ("Km dégradés pour 100 000 hab.", "Km en mauvais état ÷ population 2022 × 100 000."),
        ("Desserte routière", "Km de routes classées (longueur géodésique des géométries) ÷ superficie OCHA × 1 000."),
        ("Auto-écoles pour 100 000 hab.", "Auto-écoles recensées (toutes, agréées ou non) ÷ population 2022 × 100 000."),
        ("Score de priorité", "Moyenne pondérée des rangs centiles (0–100, 100 = plus défavorable) de : part en mauvais "
                              "état, déficit d'auto-écoles par habitant, faible densité routière. Élevée ≥ 65, moyenne "
                              "45–65, à surveiller < 45. Mortalité, accidentologie et motorisation sont exclues car "
                              "publiées au niveau national seulement."),
    ]
    m = data.troncons.methode_attribution.value_counts()
    ctrl = data.controles.set_index("controle").resultat
    code_geo = ctrl.get("Région du code = région des géométries appariées", "—")
    sections = [
        ("Sources et couverture", html.Ul([
            html.Li(f"{len(data.inventory_files)} fichiers CSV du portail national (lecture seule, empreintes SHA-256 "
                    "dans l'inventaire)."),
            html.Li("Accidents, décès, blessés : 2010–2022, national. Immatriculations : 1990–2022, national. Permis : "
                    "2007–2022 (2013 manquant), national."),
            html.Li("Population : RGPH-5 2022, du pays au canton. État des routes : 2020, par tronçon."),
            html.Li(f"Routes classées ({len(data.roads)} segments géolocalisés) et auto-écoles "
                    f"({len(data.auto_ecoles)} points) : exports 2024–2025."),
            html.Li(f"Limites des préfectures : {data.meta['source_limites']}."),
        ])),
        ("Définitions des indicateurs", html.Table([
            html.Thead(html.Tr([html.Th("Indicateur"), html.Th("Calcul")])),
            html.Tbody([html.Tr([html.Td(a, className="strong"), html.Td(b)]) for a, b in defs]),
        ], className="tbl")),
        ("Rattachement territorial des tronçons", html.Ol([
            html.Li(f"Code régional dans le libellé (TGR + M/P/C/K/S) — {m.get('Code régional du libellé', 0)} tronçons."),
            html.Li("Sinon, appariement aux géométries : nom normalisé quasi identique (similarité ≥ 0,92), ou nom proche "
                    f"(≥ 0,60) et longueur concordante à ± 5 % — {m.get('Géométrie appariée', 0)} tronçons."),
            html.Li("Sinon, toponymes du libellé retrouvés dans la nomenclature RGPH-5 — "
                    f"{m.get('Toponymes (RGPH-5)', 0)} tronçons ; non attribués : {m.get('Non attribué', 0)}."),
            html.Li(f"Contrôle : région du code = région des géométries appariées pour {code_geo}."),
        ])),
        ("Principes de traitement", html.Ul([
            html.Li("Aucune valeur observée n'est modifiée : seuls des libellés (coquilles) et le codage des manquants "
                    "sont corrigés, et chaque opération est journalisée."),
            html.Li("Les valeurs atypiques sont signalées (cercles sur les graphiques), jamais supprimées ni lissées."),
            html.Li("Le Grand Lomé (Golfe, Agoè-Nyivé) est rattaché à la région Maritime, comme dans les bases routes "
                    "et auto-écoles ; il reste distinct au niveau préfectoral."),
            html.Li("Le pipeline est rejouable : python app.py --rebuild régénère data/processed/ à l'identique."),
        ])),
    ]
    return html.Div([html.Details([html.Summary(t), html.Div(c, className="details-body")])
                     for t, c in sections], className="accordion")


def view_reco(data):
    w = DEFAULT_WEIGHTS
    sliders = []
    for k, c in SCORE_COMPONENTS.items():
        sliders.append(html.Div([
            html.Div([html.Span(c["label"], className="w-label"), html.Span(id=f"w-{k}-val", className="w-val")],
                     className="w-head"),
            dcc.Slider(id=f"w-{k}", min=0, max=100, step=5, value=w[k], marks=None, className="w-slider",
                       allow_direct_input=False, persistence=True, persistence_type="memory"),
            html.P(c["definition"], className="w-def"),
        ], className="w-row"))
    unavailable = html.Ul([html.Li([html.Span(className="na-dot"), t]) for t in UNAVAILABLE_COMPONENTS.values()],
                          className="na-list")
    return html.Div([
        html.Div([
            card("Recommandations priorisées", html.Div([
                html.Div([
                    segmented("reco-cat", [("all", "Toutes"), ("Urgence", "Urgence"), ("Formation", "Formation"),
                                           ("Infrastructures", "Infrastructures"),
                                           ("Gouvernance des données", "Données")], "all", "seg-wrap"),
                    segmented("reco-prio", [("all", "Toutes priorités"), ("Élevée", "Élevée"), ("Moyenne", "Moyenne"),
                                            ("À surveiller", "À surveiller")], "all", "seg-wrap"),
                ], className="toolbar"),
                html.Div(id="reco-list", className="reco-list"),
            ]), sub_id="reco-msg", className="span-2", tools=export_button("recommandations")),
            card("Score de priorité : pondérations", html.Div([
                html.Div(sliders, className="weights"),
                html.H3("Composantes non mobilisables"),
                unavailable,
                html.H3("Préfectures en tête avec ces poids"),
                html.Div(id="reco-score-top"),
            ]), className="weights-card"),
        ], className="grid grid-3"),
        html.Div([
            card("Qualité des données", html.Div([
                html.Div(id="dq-summary", className="dq-summary"),
                html.Div(segmented("dq-view", [("inventaire", "Inventaire"), ("controles", "Contrôles"),
                                               ("anomalies", "Anomalies"), ("journal", "Journal"),
                                               ("variables", "Variables"), ("limites", "Limites")], "inventaire",
                                   "seg-wrap"), className="toolbar"),
                datatable("dq-table", 12, wide_cols=("detail", "traitement", "resultat", "role")),
            ]), className="span-2", tools=export_button("qualite"), sub_id="dq-msg"),
            card("Méthodologie", methodology(data)),
        ], className="grid grid-3"),
    ], className="view")


def build_layout(data):
    tabs = dcc.Tabs(id="tabs", value="overview", className="tabs", parent_className="tabs-wrap",
                    persistence=True, persistence_type="session", children=[
                        dcc.Tab(label=l, value=v, className="tab", selected_className="tab-on",
                                children=builder(data))
                        for (v, l), builder in zip(VIEWS, [view_overview, view_mobilite, view_securite, view_reseau,
                                                          view_reco])])
    return html.Div([
        sidebar(data),
        html.Main([
            html.Header([
                html.H1(id="view-title"),
                html.Div(id="scope-chips", className="scope-chips"),
            ], className="topbar"),
            tabs,
            html.Footer("Sources : portail national des données du Togo, RGPH-5 2022, OCHA COD-AB.", className="footer"),
        ], className="main"),
        dcc.Location(id="url", refresh=False),
        dcc.Download(id="download"),
        dcc.Store(id="weights", data=DEFAULT_WEIGHTS),
    ], className="shell")
