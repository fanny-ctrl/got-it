"""La base SQLite du Transcripteur : transcriptions, journal et réglages.

Tout est rangé dans C:\\Users\\<vous>\\Transcripteur, volontairement hors des dossiers synchronisés (OneDrive,
Dropbox…) : la base `transcripteur.db` et, le temps d'une transcription, le dossier `enregistrements`.
La variable TRANSCRIPTEUR_DONNEES désigne un autre dossier (les tests s'en servent pour travailler à part).
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

DOSSIER = Path(os.environ.get("TRANSCRIPTEUR_DONNEES") or Path.home() / "Transcripteur")
CHEMIN_BASE = DOSSIER / "transcripteur.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS transcriptions (
    id INTEGER PRIMARY KEY,
    titre TEXT NOT NULL,
    client TEXT NOT NULL DEFAULT '',
    dossier TEXT NOT NULL DEFAULT '',
    participants TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,                    -- 'micro', 'micro et ordinateur' ou 'fichier'
    fichier_origine TEXT NOT NULL DEFAULT '',
    accord_le TEXT NOT NULL DEFAULT '',
    statut TEXT NOT NULL,
    etape TEXT NOT NULL DEFAULT '',
    progression REAL NOT NULL DEFAULT 0,
    erreur TEXT NOT NULL DEFAULT '',
    audio TEXT NOT NULL DEFAULT '',          -- nom du fichier, sans son dossier
    duree REAL NOT NULL DEFAULT 0,
    texte TEXT NOT NULL DEFAULT '',
    synthese TEXT NOT NULL DEFAULT '',
    modele_whisper TEXT NOT NULL DEFAULT '',
    modele_ollama TEXT NOT NULL DEFAULT '',
    transcrit_le TEXT NOT NULL DEFAULT '',
    audio_efface_le TEXT NOT NULL DEFAULT '',
    texte_efface_le TEXT NOT NULL DEFAULT '',
    termine_le TEXT NOT NULL DEFAULT '',
    cree_le TEXT NOT NULL,
    modifie_le TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY,
    transcription_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    commentaire TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS journal_transcription ON journal (transcription_id);
CREATE TABLE IF NOT EXISTS reglages (
    cle TEXT PRIMARY KEY,
    valeur TEXT NOT NULL
);
"""


def maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connexion() -> sqlite3.Connection:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CHEMIN_BASE, timeout=30)
    conn.row_factory = sqlite3.Row
    # Un texte effacé est réellement écrasé dans le fichier, pas seulement marqué comme libre.
    conn.execute("PRAGMA secure_delete = ON")
    return conn


def preparer() -> None:
    """Crée les tables si elles manquent ; ne supprime jamais rien."""
    conn = connexion()
    with conn:
        conn.executescript(SCHEMA)
    conn.close()


def journaliser(conn, transcription_id: int, commentaire: str) -> None:
    conn.execute("INSERT INTO journal (transcription_id, date, commentaire) VALUES (?, ?, ?)",
                 (transcription_id, maintenant(), commentaire))


def reglage(conn, cle: str, defaut: str = "") -> str:
    ligne = conn.execute("SELECT valeur FROM reglages WHERE cle = ?", (cle,)).fetchone()
    return ligne["valeur"] if ligne is not None else defaut


def regler(conn, cle: str, valeur: str) -> None:
    conn.execute("INSERT INTO reglages (cle, valeur) VALUES (?, ?)"
                 " ON CONFLICT (cle) DO UPDATE SET valeur = excluded.valeur", (cle, valeur))


_chiffrement: tuple[float, str] | None = None


def etat_chiffrement() -> str:
    """'protégé', 'chiffrement en cours', 'non protégé' ou 'non vérifié' : BitLocker sur le lecteur de la base.
    Lu par l'Explorateur de Windows, sans droits d'administrateur ; gardé cinq minutes en mémoire."""
    global _chiffrement
    if _chiffrement and time.time() - _chiffrement[0] < 300:
        return _chiffrement[1]
    lecteur = DOSSIER.resolve().drive or "C:"
    try:
        sortie = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(New-Object -ComObject Shell.Application).NameSpace('{lecteur}').Self"
             ".ExtendedProperty('System.Volume.BitLockerProtection')"],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
        etat = {"1": "protégé", "3": "chiffrement en cours"}.get(sortie, "non protégé" if sortie else "non vérifié")
    except Exception:
        etat = "non vérifié"
    _chiffrement = (time.time(), etat)
    return etat
