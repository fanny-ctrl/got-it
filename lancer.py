"""Lance Got-it dans sa propre fenêtre, comme une application.

Usage : pythonw lancer.py                 la fenêtre de Got-it, sans fenêtre noire (raccourci du Bureau, lancer.bat)
        python lancer.py --navigateur     dans le navigateur habituel, avec les messages dans le terminal

La fenêtre est celle de Microsoft Edge (présent sur tout Windows 10 ou 11) ou, à défaut, de Chrome, en mode
« application » : ni onglets ni barre d'adresse, et un profil à part, sans extensions ni synchronisation, rangé
avec les données de Got-it. Le serveur n'écoute que sur 127.0.0.1 : il n'est pas joignable depuis un autre
ordinateur.

Fermer la fenêtre arrête Got-it. Un enregistrement en cours est alors arrêté et transcrit ; une transcription
en cours se termine d'abord, sans fenêtre, puis Got-it s'arrête. Relancer Got-it pendant ce temps rouvre
simplement la fenêtre.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

PORT = 8780
ADRESSE = f"http://127.0.0.1:{PORT}/"
ATTENTE_SANS_FENETRE = 90       # secondes sans signe d'une page ouverte avant d'arrêter le serveur


def message(texte: str) -> None:
    """Un message à l'utilisateur : une boîte de dialogue s'il n'y a pas de terminal, sinon une ligne."""
    if sys.platform == "win32" and (sys.stdout is None or not sys.stdout.isatty()):
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, texte, "Got-it", 0x40)
    else:
        print(texte)


def deja_lance() -> bool:
    """Vrai si un Got-it répond déjà sur le port."""
    try:
        ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # jamais de proxy pour le PC lui-même
        with ouvreur.open(ADRESSE + "api/version", timeout=2) as reponse:
            return json.load(reponse).get("application") == "Got-it"
    except Exception:
        return False


def port_occupe() -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def navigateur_application() -> Path | None:
    """Edge, sinon Chrome : les navigateurs qui savent ouvrir une page comme une application."""
    racines = [os.environ.get(v) for v in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData")]
    for relatif in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
        for racine in racines:
            if racine and (Path(racine) / relatif).exists():
                return Path(racine) / relatif
    return None


def ouvrir_fenetre(dossier_donnees: Path) -> subprocess.Popen | None:
    """Ouvre la fenêtre de Got-it ; None si ni Edge ni Chrome n'est installé."""
    navigateur = navigateur_application()
    if navigateur is None:
        return None
    profil = dossier_donnees / "fenetre"
    profil.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([
        str(navigateur), f"--app={ADRESSE}", f"--user-data-dir={profil}", "--window-size=1240,880",
        "--no-first-run", "--no-default-browser-check", "--disable-sync", "--disable-extensions",
        "--disable-background-mode", "--disable-features=msEdgeStartupBoost,Translate"])


def dans_le_navigateur() -> None:
    """L'ancien mode : le navigateur habituel, et ce terminal qui reste ouvert."""
    import uvicorn
    from transcripteur.app import app

    print(f"Got-it est lancé : {ADRESSE}")
    print("Laissez cette fenêtre ouverte ; fermez-la pour arrêter Got-it.")
    threading.Timer(1.0, webbrowser.open, args=(ADRESSE,)).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


def main() -> None:
    from transcripteur import base

    if deja_lance():
        if ouvrir_fenetre(base.DOSSIER) is None:
            webbrowser.open(ADRESSE)
        return
    if port_occupe():
        message(f"Le port {PORT} est occupé par un autre programme : Got-it ne peut pas démarrer.")
        return
    if "--navigateur" in sys.argv:
        dans_le_navigateur()
        return

    # Sans terminal (pythonw), les messages techniques vont dans un fichier à côté des données.
    if sys.stdout is None or sys.stderr is None:
        base.DOSSIER.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(base.DOSSIER / "journal-technique.txt", "a", encoding="utf-8", buffering=1)

    import uvicorn
    from transcripteur import app as application

    serveur = uvicorn.Server(uvicorn.Config(application.app, host="127.0.0.1", port=PORT, log_level="warning"))
    fil = threading.Thread(target=serveur.run, name="serveur", daemon=True)
    fil.start()
    debut = time.time()
    while not serveur.started and fil.is_alive() and time.time() - debut < 30:
        time.sleep(0.1)
    if not serveur.started:
        message("Got-it n'a pas pu démarrer. Le détail est dans le fichier journal-technique.txt du dossier "
                f"{base.DOSSIER}.")
        return

    fenetre = ouvrir_fenetre(base.DOSSIER)
    if fenetre is None:
        webbrowser.open(ADRESSE)        # ni Edge ni Chrome : le navigateur habituel
    else:
        fenetre.wait()
        application.fermer_enregistrement("fenêtre fermée")
    application.signaler_presence()
    # Le serveur reste le temps de finir les transcriptions, et tant qu'une page de Got-it est ouverte.
    while application.en_activite() or time.time() - application.derniere_presence() < ATTENTE_SANS_FENETRE:
        time.sleep(2)
        if time.time() - application.derniere_presence() >= ATTENTE_SANS_FENETRE:
            application.fermer_enregistrement("plus aucune fenêtre ouverte")
    serveur.should_exit = True
    fil.join(10)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        detail = traceback.format_exc()
        try:
            print(detail)
        except Exception:
            pass
        message("Got-it s'est arrêté sur une erreur :\n\n" + detail[-700:])
