"""Lance le Transcripteur : démarre le serveur local et ouvre le navigateur.

Usage : python lancer.py [--sans-navigateur]
Si le Transcripteur tourne déjà, ouvre simplement un nouvel onglet. Fermer la fenêtre noire arrête l'application.
Le serveur n'écoute que sur 127.0.0.1 : il n'est pas joignable depuis un autre ordinateur.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import urllib.request
import webbrowser

PORT = 8780
ADRESSE = f"http://127.0.0.1:{PORT}/"


def deja_lance() -> bool:
    """Vrai si un Transcripteur répond déjà sur le port."""
    try:
        ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # jamais de proxy pour le PC lui-même
        with ouvreur.open(ADRESSE + "api/version", timeout=2) as reponse:
            return json.load(reponse).get("application") == "Transcripteur"
    except Exception:
        return False


def port_occupe() -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def main() -> None:
    ouvrir = "--sans-navigateur" not in sys.argv
    if deja_lance():
        print("Le Transcripteur tourne déjà : ouverture d'un nouvel onglet.")
        if ouvrir:
            webbrowser.open(ADRESSE)
        return
    if port_occupe():
        print(f"Le port {PORT} est occupé par un autre programme : le Transcripteur ne peut pas démarrer.")
        input("Appuyez sur Entrée pour fermer.")
        return
    import uvicorn
    from transcripteur.app import app

    print(f"Le Transcripteur est lancé : {ADRESSE}")
    print("Laissez cette fenêtre ouverte ; fermez-la pour arrêter le Transcripteur.")
    if ouvrir:
        threading.Timer(1.0, webbrowser.open, args=(ADRESSE,)).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
