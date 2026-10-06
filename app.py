"""Mobilité et sécurité routière au Togo — tableau de bord décisionnel.

    python app.py                 lance le tableau de bord et l'ouvre dans le navigateur
    python app.py --rebuild       régénère aussi les tables traitées et de contrôle (data/processed/)
    python app.py --port 8060     autre port (par défaut 8050, ou le suivant s'il est occupé)
    python app.py --no-browser    n'ouvre pas le navigateur ; --host 0.0.0.0 pour un accès depuis le réseau local
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import threading
import time
import urllib.request
import webbrowser

from dash import Dash

from src.callbacks import register
from src.config import PROCESSED_DIR
from src.layout import build_layout
from src.pipeline import build

TITLE = "Mobilité et sécurité routière — Togo"
FONTS = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"


def create_app(rebuild: bool = False) -> Dash:
    # Les données sont toujours recalculées depuis les sources (quelques secondes) : ce qui est affiché est reproductible.
    data = build(write=rebuild or not (PROCESSED_DIR / "meta.json").exists())
    app = Dash(__name__, title=TITLE, update_title=None,
               suppress_callback_exceptions=True, external_stylesheets=[FONTS],
               meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"},
                          {"name": "description", "content": "Tableau de bord décisionnel : mobilité, sécurité "
                                                             "routière, réseau routier et formation des conducteurs."}])
    app.layout = build_layout(data)
    register(app, data)
    return app


def is_dashboard(url: str) -> bool:
    """Vrai si le tableau de bord répond déjà à cette adresse (double lancement)."""
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return TITLE in r.read().decode("utf-8", "ignore")
    except OSError:
        return False


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def open_when_ready(url: str, host: str, port: int, timeout: float = 60) -> None:
    """Ouvre le navigateur dès que le serveur accepte les connexions."""
    def wait():
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if port_in_use(host, port):
                webbrowser.open(url)
                return
            time.sleep(0.25)
    threading.Thread(target=wait, daemon=True).start()


def quiet_server(app: Dash) -> None:
    """Masque les messages techniques du serveur (bannière, requêtes) ; les erreurs restent affichées."""
    import flask.cli
    flask.cli.show_server_banner = lambda *a, **k: None
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.logger.setLevel(logging.WARNING)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rebuild", action="store_true", help="régénérer data/processed/")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8050)))
    parser.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    local = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    browser = not (args.no_browser or args.debug)

    url = f"http://{local}:{args.port}"
    if is_dashboard(url):
        print(f"Le tableau de bord est déjà lancé : {url}")
        if browser:
            webbrowser.open(url)
        raise SystemExit(0)
    port = args.port
    while port_in_use(local, port) and port < args.port + 20:
        port += 1
    if port != args.port:
        print(f"Port {args.port} occupé : utilisation du port {port}.")
    url = f"http://{local}:{port}"

    print("Préparation des données (lecture, nettoyage, indicateurs)...", flush=True)
    t0 = time.perf_counter()
    app = create_app(rebuild=args.rebuild)
    print(f"Données prêtes en {time.perf_counter() - t0:.1f} s.".replace(".", ",", 1))
    print()
    print(f"  Tableau de bord : {url}")
    print("  " + ("Le navigateur va s'ouvrir automatiquement." if browser else "Ouvrez cette adresse dans un navigateur."))
    print("  Laissez cette fenêtre ouverte pendant l'utilisation ; fermez-la ou faites Ctrl+C pour arrêter.")
    print(flush=True)
    if not args.debug:
        quiet_server(app)
    if browser:
        open_when_ready(url, local, port)
    app.run(host=args.host, port=port, debug=args.debug)
