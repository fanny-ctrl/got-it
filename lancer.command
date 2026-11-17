#!/bin/bash
# Ouvre Got it! sur Mac. La fenêtre du Terminal doit rester ouverte pendant l'utilisation.
cd "$(dirname "$0")" || exit 1
if [ ! -x ".venv/bin/python" ]; then
  echo "Got it! n'est pas installé : lancez d'abord installer.command"
  read -r -p "Appuyez sur Entrée pour fermer."
  exit 1
fi
echo "Got it! est ouvert. Laissez cette fenêtre ouverte ; elle se libère quand Got it! s'arrête."
.venv/bin/python lancer.py
