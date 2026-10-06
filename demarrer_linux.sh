#!/usr/bin/env bash
# Démarrage du tableau de bord sous Linux (et macOS via demarrer_macos.command) : ./demarrer_linux.sh
# Première fois : environnement Python local (.venv) + bibliothèques. Ensuite : démarrage direct.
cd "$(dirname "$0")" || exit 1

echo
echo "  Mobilité et sécurité routière au Togo - tableau de bord"
echo "  --------------------------------------------------------"
echo

if [ -x .venv/bin/python ]; then
  echo "  [1/3] Environnement Python local déjà prêt."
else
  PY=""
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
      PY="$c"; break
    fi
  done
  if [ -z "$PY" ]; then
    echo "  [Erreur] Python 3.10 ou plus est introuvable : https://www.python.org/downloads/"
    exit 1
  fi
  echo "  [1/3] Première utilisation : création de l'environnement Python local .venv - environ 20 secondes..."
  if ! "$PY" -m venv .venv; then
    rm -rf .venv
    echo "  [Erreur] Impossible de créer .venv (Debian/Ubuntu : sudo apt install python3-venv)."
    exit 1
  fi
fi

if cmp -s requirements.txt .venv/requirements.ok; then
  echo "  [2/3] Bibliothèques déjà installées."
else
  echo "  [2/3] Installation des bibliothèques : 2 à 5 minutes la première fois, connexion internet requise..."
  echo
  if ! .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt; then
    echo
    echo "  [Erreur] L'installation a échoué. Vérifiez la connexion internet puis relancez : elle reprendra."
    exit 1
  fi
  cp requirements.txt .venv/requirements.ok
  echo
fi

echo "  [3/3] Démarrage du tableau de bord..."
echo
exec .venv/bin/python app.py "$@"
