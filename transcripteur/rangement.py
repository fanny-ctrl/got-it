"""Le dossier de rangement : où déposer le compte rendu Word d'une transcription terminée.

C'est un choix de l'utilisateur, fait dans les réglages (rien n'est rangé tant qu'aucun dossier n'est choisi).
Le dossier peut être n'importe où, y compris dans un dossier synchronisé (OneDrive, Google Drive, Dropbox) :
dans ce cas le compte rendu quitte le PC par ce service, et c'est le seul contenu qui le fait. La base, l'audio
et le texte intégral restent dans le dossier des données ; le texte intégral n'entre dans le fichier rangé que
si la case des réglages le demande.

Réglages (table `reglages`) : `dossier_rangement`, `rangement_auto` ('1' ou ''), `rangement_texte` ('1' ou '').
Pour les tests, la variable TRANSCRIPTEUR_DOSSIER_TEST remplace la fenêtre de choix du dossier.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from . import base, rendu

# La fenêtre « Choisir un dossier » de Windows, au premier plan ; écrit le chemin choisi, ou rien si annulé.
SCRIPT_CHOIX = (
    "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Add-Type -AssemblyName System.Windows.Forms; "
    "$fenetre = New-Object System.Windows.Forms.Form -Property @{TopMost = $true; ShowInTaskbar = $false}; "
    "$choix = New-Object System.Windows.Forms.FolderBrowserDialog; "
    "$choix.Description = 'Dossier ou ranger les comptes rendus'; $choix.ShowNewFolderButton = $true; "
    "if ($env:GOT_IT_DEPART -and (Test-Path -LiteralPath $env:GOT_IT_DEPART)) { $choix.SelectedPath = $env:GOT_IT_DEPART }; "
    "if ($choix.ShowDialog($fenetre) -eq 'OK') { [Console]::Out.Write($choix.SelectedPath) }"
)
# Dossiers synchronisés avec un service en ligne, reconnus à leur nom pour l'avertissement des réglages.
SERVICES = (("onedrive", "OneDrive"), ("google drive", "Google Drive"), ("googledrive", "Google Drive"),
            ("mon drive", "Google Drive"), ("my drive", "Google Drive"), ("dropbox", "Dropbox"),
            ("icloud", "iCloud"), ("kdrive", "kDrive"), ("nextcloud", "Nextcloud"), ("sharepoint", "SharePoint"))


def date_fr(valeur: str, avec_heure: bool = False) -> str:
    """'2026-11-16T14:03:22' → '16/11/2026', ou '16/11/2026 à 14 h 03'."""
    if not valeur or len(valeur) < 10:
        return ""
    jour = f"{valeur[8:10]}/{valeur[5:7]}/{valeur[:4]}"
    if avec_heure and len(valeur) >= 16:
        jour += f" à {valeur[11:13]} h {valeur[14:16]}"
    return jour


def choisir_dossier(depart: str = "") -> str:
    """Ouvre la fenêtre de choix d'un dossier ; renvoie le chemin choisi, ou '' si l'utilisateur annule."""
    essai = os.environ.get("TRANSCRIPTEUR_DOSSIER_TEST")
    if essai is not None:
        return essai
    sortie = subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-Command", SCRIPT_CHOIX], capture_output=True, timeout=600,
        env={**os.environ, "GOT_IT_DEPART": depart}, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return sortie.stdout.decode("utf-8", "replace").strip()


def service_en_ligne(dossier: str) -> str:
    """Le nom du service de synchronisation dont dépend ce dossier ('OneDrive'…), ou '' s'il n'en dépend pas
    à première vue. C'est un indice tiré du chemin, pas une certitude."""
    chemin = dossier.lower()
    return next((nom for motif, nom in SERVICES if motif in chemin), "")


def reglages(conn) -> dict:
    dossier = base.reglage(conn, "dossier_rangement")
    return {"dossier": dossier, "auto": bool(base.reglage(conn, "rangement_auto")),
            "texte": bool(base.reglage(conn, "rangement_texte")),
            "service": service_en_ligne(dossier) if dossier else "",
            "accessible": bool(dossier) and Path(dossier).is_dir()}


def proprietes(t, avocat: str) -> list[tuple[str, str]]:
    """L'en-tête du compte rendu Word : date, avocat, client, dossier, participants, durée."""
    from .traitement import duree_lisible

    lignes = [("Date", date_fr(t["cree_le"], True))]
    lignes += [(nom, valeur) for nom, valeur in (("Avocat", avocat), ("Client", t["client"]),
                                                 ("Dossier", t["dossier"]), ("Participants", t["participants"]))
               if valeur]
    if t["duree"]:
        lignes.append(("Durée", duree_lisible(t["duree"])))
    return lignes


def nom_fichier(t) -> str:
    """'2026-11-16 - Société Essai, contrat de licence.docx' : la date, puis le titre sans caractère interdit."""
    titre = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", t["titre"])
    titre = re.sub(r"\s+", " ", titre).strip(" .")[:90] or "Rendez-vous"
    return f"{t['cree_le'][:10]} - {titre}.docx"


def ranger(conn, tid: int) -> Path:
    """Écrit le compte rendu Word de la transcription dans le dossier de rangement et l'inscrit au journal.
    Le fichier d'une même transcription est remplacé (après une correction de la synthèse, par exemple)."""
    choix = reglages(conn)
    if not choix["dossier"]:
        raise RuntimeError("Aucun dossier de rangement n'est choisi : indiquez-le dans les réglages.")
    dossier = Path(choix["dossier"])
    if not dossier.is_dir():
        raise RuntimeError(f"Le dossier de rangement est introuvable ({dossier}) : vérifiez qu'il existe, ou "
                           "choisissez-en un autre dans les réglages.")
    t = conn.execute("SELECT * FROM transcriptions WHERE id = ?", (tid,)).fetchone()
    if t is None or t["statut"] != "terminée":
        raise RuntimeError("La transcription n'est pas terminée.")
    avec_texte = choix["texte"] and bool(t["texte"])
    if not t["synthese"] and not avec_texte:
        raise RuntimeError("Il n'y a pas de synthèse à ranger (et le texte intégral n'est pas inclus : voir les "
                           "réglages).")
    contenu = rendu.en_word(t, proprietes(t, base.reglage(conn, "avocat")), avec_texte=avec_texte)
    chemin = dossier / nom_fichier(t)
    provisoire = chemin.with_suffix(".docx.partiel")
    try:
        provisoire.write_bytes(contenu)
        os.replace(provisoire, chemin)
    except PermissionError:
        provisoire.unlink(missing_ok=True)
        raise RuntimeError(f"Le fichier « {chemin.name} » est ouvert dans Word, ou le dossier refuse l'écriture : "
                           "fermez le document, puis recommencez.") from None
    with conn:
        base.journaliser(conn, tid, f"compte rendu Word rangé dans {dossier}"
                                    + (" (avec le texte intégral)" if avec_texte else " (synthèse seule)"))
    return chemin


def ranger_si_demande(conn, tid: int) -> None:
    """À la fin d'un traitement ou après une correction : range le compte rendu si les réglages le demandent.
    Un échec (dossier absent, disque débranché) s'inscrit au journal et n'arrête rien."""
    choix = reglages(conn)
    if not (choix["dossier"] and choix["auto"]):
        return
    try:
        ranger(conn, tid)
    except Exception as erreur:
        with conn:
            base.journaliser(conn, tid, f"compte rendu non rangé : {str(erreur)[:300]}")
