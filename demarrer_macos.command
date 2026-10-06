#!/usr/bin/env bash
# Démarrage du tableau de bord sous macOS : double-cliquer sur ce fichier dans le Finder
# (première fois : clic droit > Ouvrir). Le Terminal s'ouvre et exécute demarrer_linux.sh.
cd "$(dirname "$0")" || exit 1
exec bash ./demarrer_linux.sh "$@"
