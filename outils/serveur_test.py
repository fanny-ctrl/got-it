"""Serveur de test : un Got-it à part, qui ne touche ni aux vraies données ni au vrai micro.

Usage : .venv\\Scripts\\python.exe outils\\serveur_test.py [port] [dossier_audio]

- Les données vont dans %TEMP%\\transcripteur-test (à supprimer après les tests), jamais dans
  C:\\Users\\<vous>\\Got-it.
- Si `dossier_audio` est donné, aucun périphérique réel n'est ouvert : `micro.wav` (et `ordinateur.wav` s'il
  existe) de ce dossier sont rejoués à la place du micro et du son de l'ordinateur.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8781
os.environ["TRANSCRIPTEUR_DONNEES"] = str(Path(tempfile.gettempdir()) / "transcripteur-test")
if len(sys.argv) > 2:
    os.environ["TRANSCRIPTEUR_AUDIO_TEST"] = str(Path(sys.argv[2]).resolve())

import uvicorn  # noqa: E402

from transcripteur.app import app  # noqa: E402

print(f"Got-it de test : http://127.0.0.1:{port}/ (données dans {os.environ['TRANSCRIPTEUR_DONNEES']})")
uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
