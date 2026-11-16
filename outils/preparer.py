"""Prépare Got-it, une fois, avec Internet (appelé par installer.bat).

1. Télécharge le modèle Whisper large-v3-turbo (environ 1,6 Go) dans le cache Hugging Face du profil, s'il n'y est
   pas déjà. Ensuite Got-it transcrit hors ligne : transcripteur/traitement.py interdit tout
   téléchargement.
2. Vérifie qu'Ollama répond et qu'il a un modèle de langue ; sinon, explique quoi faire (la synthèse est
   facultative : sans Ollama, Got-it fait la transcription seule).

Usage : .venv\\Scripts\\python.exe outils\\preparer.py
Rien n'est envoyé : le script ne fait que télécharger le modèle depuis Hugging Face et interroger Ollama sur ce PC.
"""

from __future__ import annotations

import json
import shutil
import sys
import urllib.request

MODELE_WHISPER = "large-v3-turbo"
MODELE_OLLAMA = "mistral"


def preparer_whisper() -> bool:
    from faster_whisper.utils import download_model
    try:
        download_model(MODELE_WHISPER, local_files_only=True)
        print(f"Transcription : le modèle Whisper « {MODELE_WHISPER} » est déjà sur ce PC.")
        return True
    except Exception:
        pass
    print(f"Transcription : téléchargement du modèle Whisper « {MODELE_WHISPER} » (environ 1,6 Go, une seule fois)…")
    try:
        download_model(MODELE_WHISPER)
    except Exception as erreur:
        print(f"Échec du téléchargement : {erreur}")
        print("Vérifiez la connexion à Internet, puis relancez installer.bat.")
        return False
    print("Modèle Whisper prêt.")
    return True


def verifier_ollama() -> None:
    try:
        ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with ouvreur.open("http://127.0.0.1:11434/api/tags", timeout=3) as reponse:
            modeles = [m["name"] for m in json.loads(reponse.read().decode("utf-8")).get("models", [])]
    except Exception:
        if shutil.which("ollama"):
            print("Synthèse : Ollama est installé mais ne répond pas. Ouvrez-le depuis le menu Démarrer.")
        else:
            print("Synthèse : Ollama n'est pas installé. Sans lui, Got-it transcrit sans rédiger de synthèse.")
            print("Pour la synthèse : installez Ollama depuis https://ollama.com/download, puis tapez « ollama pull mistral ».")
        return
    if any(m == MODELE_OLLAMA or m.startswith(MODELE_OLLAMA + ":") for m in modeles):
        print(f"Synthèse : Ollama est prêt avec le modèle « {MODELE_OLLAMA} ».")
    elif modeles:
        print(f"Synthèse : Ollama utilisera « {modeles[0]} » (« {MODELE_OLLAMA} » n'est pas installé).")
    else:
        print("Synthèse : Ollama n'a aucun modèle. Tapez « ollama pull mistral » dans un terminal (environ 4 Go).")


if __name__ == "__main__":
    ok = preparer_whisper()
    verifier_ollama()
    sys.exit(0 if ok else 1)
