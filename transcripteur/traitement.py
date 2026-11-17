"""Le traitement d'un enregistrement : transcription par Whisper, effacement de l'audio, synthèse par Ollama.

- faster-whisper transcrit sur le processeur du PC avec le modèle large-v3-turbo, rangé dans le cache Hugging
  Face du profil. HF_HUB_OFFLINE interdit tout téléchargement : seul `outils/preparer.py`, lancé par
  `installer.bat`, va chercher le modèle, une fois.
- l'audio est écrasé puis supprimé dès la transcription terminée ;
- le modèle de langue d'Ollama (127.0.0.1:11434, Mistral par défaut) rédige la synthèse selon la trame des
  réglages. Sans Ollama, la transcription se fait quand même, sans synthèse.

Les traitements passent un par un dans une file, dans un fil d'exécution ; au démarrage, `reprendre()` remet en
file ce qu'un arrêt de Got it! a coupé.
"""

from __future__ import annotations

import os

# Avant tout import de faster-whisper : aucun téléchargement, aucune télémétrie de Hugging Face.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import gc  # noqa: E402
import json  # noqa: E402
import queue  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import urllib.request  # noqa: E402
from pathlib import Path  # noqa: E402

from . import audio, base  # noqa: E402

import subprocess  # noqa: E402
import sys  # noqa: E402

# La variable TRANSCRIPTEUR_MODELE permet d'essayer un autre modèle (« tiny » pour les tests, « small » sur un
# PC modeste) sans toucher au code.
MODELE_WHISPER = os.environ.get("TRANSCRIPTEUR_MODELE") or "large-v3-turbo"
TAILLES_MODELES = {"large-v3-turbo": 1_621_667_008}     # octets, pour la barre de progression
TYPE_CALCUL = "int8"
LANGUE = "fr"
MODELE_OLLAMA = "mistral"
CONTEXTE_OLLAMA = 16384
ADRESSE_OLLAMA = "http://127.0.0.1:11434"
TAILLE_MORCEAU = 30000          # caractères de transcription envoyés à Ollama en une fois

EN_TRAITEMENT = ("en attente", "transcription", "synthèse")

INFORMATION_DEFAUT = (
    "« Pour la qualité du suivi de votre dossier, je vous propose d'enregistrer notre entretien. "
    "L'enregistrement est transcrit sur mon ordinateur, sans aucun envoi vers un service extérieur, "
    "puis l'audio est effacé. La transcription est couverte par le secret professionnel et conservée "
    "avec votre dossier. Vous pouvez refuser, ou me demander d'arrêter à tout moment. Êtes-vous d'accord ? »"
)

TRAME_DEFAUT = """Tu es l'assistant d'un cabinet d'avocat. On te fournit la transcription automatique d'un rendez-vous entre l'avocat et son client. Rédige un compte rendu interne, en français, destiné uniquement à l'avocat.

Règles impératives :
- Ne rien inventer. Si un point est incertain ou inaudible dans la transcription, l'indiquer entre crochets : [à vérifier].
- Conserver les noms, dates, montants et termes employés par les interlocuteurs.
- Rester factuel ; ne pas ajouter de conseil juridique qui n'a pas été exprimé pendant l'entretien.
- Aucune formule de politesse, aucune introduction.

Structure attendue (titres en gras, prose courte sous chaque titre, listes seulement pour les actions et échéances) :

**Contexte et objet du rendez-vous**
**Faits exposés par le client**
**Questions juridiques soulevées**
**Analyse et conseils donnés pendant l'entretien**
**Pièces et informations à obtenir**
**Actions à mener** (liste : qui fait quoi, pour quand)
**Échéances et délais mentionnés**
**Points restant à éclaircir**
"""

_verrou = threading.Lock()
_file: queue.Queue[int] = queue.Queue()
_ouvrier: threading.Thread | None = None


# ---------------------------------------------------------------- utilitaires

def horodatage(secondes) -> str:
    """75 → '00:01:15'."""
    s = int(secondes or 0)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def duree_lisible(secondes) -> str:
    """42 → '42 s' ; 200 → '3 min 20 s' ; 3900 → '1 h 05 min'."""
    s = int(round(secondes or 0))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min {s % 60} s" if s % 60 else f"{s // 60} min"
    return f"{s // 3600} h {(s % 3600) // 60:02d} min"


def dossier_audio() -> Path:
    dossier = base.DOSSIER / "enregistrements"
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def chemin_audio(nom: str | None) -> Path | None:
    return dossier_audio() / Path(nom).name if nom else None


def maj(conn, tid: int, **champs) -> None:
    """Met à jour une transcription et valide aussitôt (le suivi en direct lit la base pendant le traitement)."""
    champs["modifie_le"] = base.maintenant()
    colonnes = ", ".join(f"{cle} = :{cle}" for cle in champs)
    with conn:
        conn.execute(f"UPDATE transcriptions SET {colonnes} WHERE id = :id", {**champs, "id": tid})


def noter(conn, tid: int, commentaire: str) -> None:
    with conn:
        base.journaliser(conn, tid, commentaire)


# ---------------------------------------------------------------- environnement

def modele_whisper_present() -> bool:
    try:
        from faster_whisper.utils import download_model
        download_model(MODELE_WHISPER, local_files_only=True)
        return True
    except Exception:
        return False


# Le téléchargement du modèle : le seul moment où Got it! va sur Internet, à la demande de l'utilisateur.
# Il se fait dans un programme à part (`lancer.py --telecharger-modele`), parce que ce programme-ci s'est
# interdit tout téléchargement dès son démarrage (HF_HUB_OFFLINE).
_telechargement: subprocess.Popen | None = None
_fin_telechargement = ""        # message d'échec du dernier téléchargement


def _dossier_du_modele() -> Path | None:
    """Le dossier du cache Hugging Face où le modèle arrive, pour mesurer l'avancement."""
    try:
        from faster_whisper.utils import _MODELS
        from huggingface_hub.constants import HF_HUB_CACHE
        depot = _MODELS.get(MODELE_WHISPER, MODELE_WHISPER)
        return Path(HF_HUB_CACHE) / ("models--" + depot.replace("/", "--"))
    except Exception:
        return None


def demarrer_telechargement() -> None:
    global _telechargement, _fin_telechargement
    with _verrou:
        if _telechargement is not None and _telechargement.poll() is None:
            return
        _fin_telechargement = ""
        if getattr(sys, "frozen", False):       # Got it! installé : le programme se relance lui-même
            commande = [sys.executable, "--telecharger-modele"]
        else:
            commande = [sys.executable, str(Path(__file__).resolve().parent.parent / "lancer.py"),
                        "--telecharger-modele"]
        environnement_fils = {**os.environ, "HF_HUB_OFFLINE": "0", "HF_HUB_DISABLE_XET": "1",
                              "HF_HUB_DISABLE_TELEMETRY": "1", "TRANSCRIPTEUR_MODELE": MODELE_WHISPER}
        _telechargement = subprocess.Popen(commande, env=environnement_fils, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def etat_telechargement() -> dict:
    """Où en est le modèle : présent, en cours de téléchargement (avec l'avancement), ou absent."""
    global _fin_telechargement
    en_cours = _telechargement is not None and _telechargement.poll() is None
    if _telechargement is not None and not en_cours and _telechargement.returncode not in (0, None):
        _fin_telechargement = ("Le téléchargement a échoué : vérifiez la connexion à Internet, puis réessayez. "
                               "Ce qui est déjà téléchargé est gardé.")
    present = False if en_cours else modele_whisper_present()
    recu = 0
    if en_cours:
        dossier = _dossier_du_modele()
        if dossier is not None and dossier.exists():
            recu = sum(f.stat().st_size for f in dossier.rglob("*") if f.is_file() and not f.is_symlink())
    total = TAILLES_MODELES.get(MODELE_WHISPER, 0)
    return {"present": present, "en_cours": en_cours, "recu": recu, "total": total,
            "progression": round(min(recu / total, 0.99), 3) if total else 0,
            "erreur": "" if present or en_cours else _fin_telechargement}


def ouvrir_url(requete, delai: float):
    """Appel à Ollama, sur ce PC : jamais par un proxy, même si Windows en déclare un."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(requete, timeout=delai)


def ollama_modeles() -> list[str] | None:
    """Modèles installés dans Ollama, ou None si Ollama ne répond pas."""
    try:
        with ouvrir_url(ADRESSE_OLLAMA + "/api/tags", 3) as reponse:
            return [m["name"] for m in json.loads(reponse.read().decode("utf-8")).get("models", [])]
    except Exception:
        return None


def choisir_modele(modeles: list[str], prefere: str = "") -> str:
    """Le modèle choisi dans les réglages s'il est installé, sinon Mistral, sinon le premier disponible."""
    if prefere in modeles:
        return prefere
    return next((m for m in modeles if m == MODELE_OLLAMA or m.startswith(MODELE_OLLAMA + ":")), modeles[0])


def environnement(conn) -> dict:
    modeles = ollama_modeles()
    return {"whisper": modele_whisper_present(), "modele_whisper": MODELE_WHISPER, "ollama": modeles,
            "telechargement": etat_telechargement(),
            "modele_ollama": choisir_modele(modeles, base.reglage(conn, "modele_ollama")) if modeles else "",
            "chiffrement": base.etat_chiffrement()}


# ---------------------------------------------------------------- transcription et synthèse

def transcrire_audio(chemin: Path, invite: str, signaler) -> tuple[str, float]:
    """Texte horodaté ('[00:01:15] …' par segment) et durée de l'audio, par faster-whisper sur le processeur."""
    from faster_whisper import WhisperModel

    signaler(0.0, "Lecture de l'audio…")
    son = audio.lire_audio(chemin)
    signaler(0.0, "Chargement du modèle de transcription…")
    modele = WhisperModel(MODELE_WHISPER, device="cpu", compute_type=TYPE_CALCUL, local_files_only=True,
                          cpu_threads=os.cpu_count() or 4)
    try:
        segments, info = modele.transcribe(
            son, language=LANGUE, beam_size=5, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 600},
            condition_on_previous_text=False, initial_prompt=invite or None)
        total = info.duration or 1.0
        signaler(0.0, f"Transcription… 00:00:00 sur {horodatage(total)}")
        lignes = []
        for segment in segments:
            texte = segment.text.strip()
            if texte:
                lignes.append(f"[{horodatage(segment.start)}] {texte}")
            signaler(min(segment.end / total, 0.99), f"Transcription… {horodatage(segment.end)} sur {horodatage(total)}")
        return "\n".join(lignes), float(info.duration or 0)
    finally:
        del modele
        gc.collect()


def ollama_generer(modele: str, systeme: str, contenu: str) -> str:
    corps = json.dumps({
        "model": modele,
        "stream": False,
        "options": {"num_ctx": CONTEXTE_OLLAMA, "temperature": 0.2},
        "messages": [{"role": "system", "content": systeme}, {"role": "user", "content": contenu}],
    }).encode("utf-8")
    requete = urllib.request.Request(ADRESSE_OLLAMA + "/api/chat", data=corps,
                                     headers={"Content-Type": "application/json"})
    with ouvrir_url(requete, 3600) as reponse:
        return json.loads(reponse.read().decode("utf-8"))["message"]["content"].strip()


def decouper(texte: str, taille: int = TAILLE_MORCEAU) -> list[str]:
    """Découpe une longue transcription en morceaux, sur des fins de ligne."""
    morceaux, courant = [], ""
    for ligne in texte.splitlines(keepends=True):
        if len(courant) + len(ligne) > taille and courant:
            morceaux.append(courant)
            courant = ""
        courant += ligne
    if courant:
        morceaux.append(courant)
    return morceaux


def rediger_synthese(modele: str, trame: str, contexte: str, texte: str, signaler) -> str:
    """Synthèse selon la trame ; une transcription trop longue est résumée par parties, puis fusionnée."""
    morceaux = decouper(texte)
    if len(morceaux) == 1:
        signaler(0.1, f"Rédaction de la synthèse par {modele}…")
        return ollama_generer(modele, trame, f"{contexte}\n\nTranscription :\n\n{texte}")
    notes = []
    for i, morceau in enumerate(morceaux, 1):
        signaler((i - 1) / (len(morceaux) + 1), f"Synthèse : partie {i} sur {len(morceaux)}…")
        notes.append(ollama_generer(
            modele, trame, f"{contexte}\n\nPartie {i} sur {len(morceaux)} de la transcription. Rédige les notes de "
                           f"cette partie selon la structure demandée :\n\n{morceau}"))
    signaler(len(morceaux) / (len(morceaux) + 1), "Synthèse : fusion des parties…")
    return ollama_generer(
        modele, trame, f"{contexte}\n\nVoici des notes partielles rédigées sur plusieurs parties d'un même entretien. "
                       "Fusionne-les en un seul compte rendu selon la structure demandée, sans perdre d'information "
                       "ni en ajouter :\n\n" + "\n\n---\n\n".join(notes))


def invite_whisper(t, avocat: str) -> str:
    """Amorce donnée à Whisper : les noms propres attendus s'orthographient mieux."""
    morceaux = [f"Rendez-vous de {avocat}" if avocat else "Rendez-vous d'avocat"]
    if t["client"]:
        morceaux.append(f"avec {t['client']}")
    if t["participants"]:
        morceaux.append(f"({t['participants']})")
    return " ".join(morceaux) + "."


def contexte_synthese(t, avocat: str) -> str:
    jour = t["cree_le"][:10]
    lignes = [f"Rendez-vous : {t['titre']}", f"Date : {jour[8:10]}/{jour[5:7]}/{jour[:4]}"]
    if avocat:
        lignes.append(f"Avocat : {avocat} (conseille ; le client expose sa situation)")
    if t["client"]:
        lignes.append(f"Client : {t['client']}")
    if t["dossier"]:
        lignes.append(f"Dossier : {t['dossier']}")
    if t["participants"]:
        lignes.append(f"Participants : {t['participants']}")
    return "\n".join(lignes)


def signaleur(conn, tid: int):
    """Progression écrite dans la base au plus toutes les deux secondes, pour le suivi en direct."""
    dernier = [0.0]

    def signaler(progression: float, etape: str) -> None:
        if time.time() - dernier[0] >= 2 or progression >= 1:
            dernier[0] = time.time()
            maj(conn, tid, progression=round(progression, 3), etape=etape)
    return signaler


def terminer(conn, tid: int, etape: str) -> None:
    maj(conn, tid, statut="terminée", progression=1.0, etape=etape, termine_le=base.maintenant())
    noter(conn, tid, etape)


def traiter(tid: int) -> None:
    """Transcrit l'audio (s'il ne l'est pas déjà), l'efface, puis fait rédiger la synthèse par Ollama."""
    conn = base.connexion()
    try:
        t = conn.execute("SELECT * FROM transcriptions WHERE id = ?", (tid,)).fetchone()
        if t is None or t["statut"] not in EN_TRAITEMENT:
            return
        avocat = base.reglage(conn, "avocat")
        if not t["transcrit_le"]:
            chemin = chemin_audio(t["audio"])
            if chemin is None or not chemin.exists():
                raise RuntimeError("Le fichier audio n'existe plus : il n'y a rien à transcrire.")
            if not modele_whisper_present():
                raise RuntimeError("Le modèle de transcription n'est pas encore sur ce PC : téléchargez-le depuis "
                                   "la page « Nouvel enregistrement », puis cliquez sur « Relancer ». "
                                   "L'enregistrement est gardé en attendant.")
            maj(conn, tid, statut="transcription", progression=0.0, etape="Chargement du modèle de transcription…",
                erreur="")
            texte, duree = transcrire_audio(chemin, invite_whisper(t, avocat), signaleur(conn, tid))
            maj(conn, tid, texte=texte, duree=duree or t["duree"], modele_whisper=MODELE_WHISPER,
                transcrit_le=base.maintenant(), progression=1.0, etape="Transcription terminée.")
            noter(conn, tid, f"{duree_lisible(duree)} d'audio transcrites sur ce PC (Whisper {MODELE_WHISPER})")
            audio.effacer_fichier(chemin)
            maj(conn, tid, audio="", audio_efface_le=base.maintenant())
            noter(conn, tid, "audio effacé (écrasé puis supprimé)")
            t = conn.execute("SELECT * FROM transcriptions WHERE id = ?", (tid,)).fetchone()
        if not t["texte"].strip():
            terminer(conn, tid, "Aucune parole n'a été reconnue dans l'enregistrement.")
            return
        if not t["synthese"]:
            modeles = ollama_modeles()
            if not modeles:
                terminer(conn, tid, "Ollama ne répond pas : la synthèse n'a pas été rédigée. Ouvrez Ollama depuis le "
                                    "menu Démarrer, puis « Rédiger la synthèse ».")
                return
            modele = choisir_modele(modeles, base.reglage(conn, "modele_ollama"))
            maj(conn, tid, statut="synthèse", progression=0.0, etape=f"Rédaction de la synthèse par {modele}…")
            trame = base.reglage(conn, "trame") or TRAME_DEFAUT
            synthese = rediger_synthese(modele, trame, contexte_synthese(t, avocat), t["texte"], signaleur(conn, tid))
            maj(conn, tid, synthese=synthese, modele_ollama=modele)
            noter(conn, tid, f"synthèse rédigée sur ce PC par Ollama ({modele})")
        terminer(conn, tid, "Terminé. La synthèse est un document de travail, à relire avant tout usage.")
    except Exception as erreur:
        message = str(erreur) or erreur.__class__.__name__
        try:
            maj(conn, tid, statut="erreur", erreur=message[:1000], etape="Le traitement s'est arrêté sur une erreur.")
            noter(conn, tid, f"erreur : {message[:300]}")
        except Exception:
            pass
    finally:
        conn.close()


def ouvrier() -> None:
    while True:
        tid = _file.get()
        try:
            traiter(tid)
        except Exception:  # traiter consigne ses erreurs dans la base ; rien ne doit arrêter la file
            pass


def mettre_en_file(tid: int) -> None:
    global _ouvrier
    _file.put(tid)
    with _verrou:
        if _ouvrier is None or not _ouvrier.is_alive():
            _ouvrier = threading.Thread(target=ouvrier, name="transcriptions", daemon=True)
            _ouvrier.start()


def reprendre() -> None:
    """Au démarrage : un enregistrement coupé par l'arrêt devient « interrompue » (l'audio est gardé, « Transcrire
    ce qui a été enregistré » le reprend) ; un traitement en cours ou en attente repart dans la file."""
    conn = base.connexion()
    try:
        with conn:
            for t in conn.execute("SELECT id, audio FROM transcriptions WHERE statut = 'enregistrement'").fetchall():
                chemin = chemin_audio(t["audio"])
                try:
                    duree = audio.duree_wav(chemin) if chemin and chemin.exists() else 0.0
                except Exception:
                    duree = 0.0
                etape = "Enregistrement coupé par l'arrêt de Got it!"
                etape += f" : {duree_lisible(duree)} conservées." if duree else "."
                conn.execute("UPDATE transcriptions SET statut = 'interrompue', duree = ?, etape = ?, modifie_le = ?"
                             " WHERE id = ?", (duree, etape, base.maintenant(), t["id"]))
                base.journaliser(conn, t["id"], "arrêt de Got it! pendant l'enregistrement")
            a_reprendre = [r["id"] for r in conn.execute(
                "SELECT id FROM transcriptions WHERE statut IN ('en attente', 'transcription', 'synthèse')"
                " ORDER BY id")]
            conn.execute("UPDATE transcriptions SET statut = 'en attente', etape = 'En attente (reprise au démarrage).'"
                         " WHERE statut IN ('transcription', 'synthèse')")
    finally:
        conn.close()
    for tid in a_reprendre:
        mettre_en_file(tid)
