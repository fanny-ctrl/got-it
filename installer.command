#!/bin/bash
# Installation de Got it! sur Mac : à lancer une fois, par un double-clic (voir INSTALLATION-MAC.md).
cd "$(dirname "$0")" || exit 1
echo "=== Installation de Got it! ==="

# Un Python 3.11 ou plus récent : celui de python.org ou de Homebrew.
PYTHON=""
for candidat in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidat" >/dev/null 2>&1 && "$candidat" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PYTHON="$candidat"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.11 ou plus récent est introuvable."
  echo "Installez Python 3.12 depuis https://www.python.org/downloads/macos/ puis relancez ce fichier."
  read -r -p "Appuyez sur Entrée pour fermer."
  exit 1
fi
echo "Python utilisé : $("$PYTHON" --version)"

"$PYTHON" -m venv .venv || { echo "Impossible de créer l'environnement Python."; read -r -p "Entrée pour fermer."; exit 1; }
.venv/bin/python -m pip install --upgrade pip --quiet
if ! .venv/bin/python -m pip install -r requirements.txt --quiet; then
  echo "L'installation des bibliothèques a échoué. Vérifiez la connexion à Internet et relancez ce fichier."
  read -r -p "Appuyez sur Entrée pour fermer."
  exit 1
fi

echo
echo "Préparation de la transcription (modèle Whisper, environ 1,6 Go, une seule fois)..."
.venv/bin/python outils/preparer.py
chmod +x lancer.command

echo
echo "Installation terminée. Ouvrez Got it! par un double-clic sur lancer.command"
read -r -p "Appuyez sur Entrée pour fermer."
