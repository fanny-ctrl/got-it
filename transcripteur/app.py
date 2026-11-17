"""L'application : pages et routes de Got it!

Routes :
  GET  /                          toutes les transcriptions, de la plus récente à la plus ancienne
  GET  /nouvelle                  préparation : formule d'information, accord, micro, son de l'ordinateur, fichier
  POST /enregistrer               démarre l'enregistrement (case d'accord obligatoire)
  POST /importer                  transcrit un fichier audio envoyé par le navigateur
  GET  /t/{id}                    suivi en direct, puis synthèse et texte intégral
  POST /t/{id}/arreter            arrête l'enregistrement et met la transcription en file
  POST /t/{id}/abandonner         arrête ou retire de la file sans transcrire, efface l'audio
  POST /t/{id}/relancer           reprend après une erreur ou une coupure, ou rédige la synthèse
  POST /t/{id}/synthese           enregistre la synthèse corrigée à la main
  POST /t/{id}/effacer-texte      efface le texte intégral (minimisation) ; la synthèse reste
  POST /t/{id}/supprimer          supprime la transcription, sa synthèse et son journal
  GET  /t/{id}/word               la synthèse en Word (?texte=1 : avec le texte intégral)
  POST /t/{id}/ranger             dépose le compte rendu Word dans le dossier de rangement
  POST /reglages/dossier          choisit (fenêtre de Windows) ou oublie le dossier de rangement
  GET  /api/t/{id}                état en JSON pour le suivi (chrono, niveaux, progression)
  GET  /reglages, POST /reglages  nom de l'avocat, formule d'information, trame de la synthèse, modèle Ollama
  GET  /api/version               pour que lancer.py reconnaisse un Got it! déjà ouvert

Sécurité locale : le serveur n'écoute que sur 127.0.0.1 ; `verifier_provenance` refuse tout autre nom d'hôte
(protection contre le « DNS rebinding ») et toute écriture qui ne vient pas d'une page de Got it!
"""

from __future__ import annotations

import re
import threading
import time
import unicodedata
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import VERSION, audio, base, rangement, rendu, traitement

RACINE = Path(__file__).parent

# Statuts d'une transcription : libellé affiché et teinte de la pastille.
STATUTS = {
    "enregistrement": {"nom": "enregistrement en cours", "teinte": "rouge"},
    "en attente": {"nom": "en attente", "teinte": "jaune"},
    "transcription": {"nom": "transcription en cours", "teinte": "bleu"},
    "synthèse": {"nom": "synthèse en cours", "teinte": "violet"},
    "terminée": {"nom": "terminée", "teinte": "vert"},
    "erreur": {"nom": "erreur", "teinte": "rouge"},
    "interrompue": {"nom": "interrompue", "teinte": "jaune"},
    "abandonnée": {"nom": "abandonnée", "teinte": "gris"},
}
SOURCES = {"micro": "micro du PC", "micro et ordinateur": "micro et son de l'ordinateur"}

_verrou = threading.Lock()
_enregistrement: audio.Enregistreur | None = None


@asynccontextmanager
async def cycle(application: FastAPI):
    base.preparer()
    traitement.reprendre()
    yield


app = FastAPI(title="Got it!", docs_url=None, redoc_url=None, openapi_url=None, lifespan=cycle)
app.mount("/static", StaticFiles(directory=RACINE / "static"), name="static")
templates = Jinja2Templates(directory=RACINE / "templates")


@app.middleware("http")
async def verifier_provenance(request: Request, suite):
    hote = request.headers.get("host", "")
    if hote.split(":")[0] not in ("127.0.0.1", "localhost"):
        return PlainTextResponse("Got it! ne répond que sur ce PC.", status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        provenance = request.headers.get("origin") or request.headers.get("referer") or ""
        if not (provenance == f"http://{hote}" or provenance.startswith(f"http://{hote}/")):
            return PlainTextResponse("Cette demande ne vient pas d'une page de Got it!", status_code=403)
    reponse = await suite(request)
    reponse.headers["Cache-Control"] = "no-store"
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    reponse.headers["Referrer-Policy"] = "same-origin"
    return reponse


@app.exception_handler(HTTPException)
async def page_d_erreur(request: Request, erreur: HTTPException):
    """Un refus s'affiche comme une page, avec un lien de retour, plutôt qu'en JSON."""
    if request.url.path.startswith("/api/"):
        return PlainTextResponse(str(erreur.detail), status_code=erreur.status_code)
    return templates.TemplateResponse(request, "erreur.html", {"detail": erreur.detail},
                                      status_code=erreur.status_code)


# ---------------------------------------------------------------- utilitaires

date_fr = rangement.date_fr


templates.env.filters["date_fr"] = date_fr
templates.env.filters["horodatage"] = traitement.horodatage
templates.env.filters["duree"] = traitement.duree_lisible
templates.env.filters["rendu"] = rendu.en_html
templates.env.globals["statuts"] = STATUTS
templates.env.globals["sources"] = SOURCES
templates.env.globals["version"] = VERSION
templates.env.globals["mac"] = audio.MAC
templates.env.globals["nom_chiffrement"] = base.NOM_CHIFFREMENT


def rendre(request: Request, gabarit: str, **contexte) -> HTMLResponse:
    return templates.TemplateResponse(request, gabarit, contexte)


@contextmanager
def transaction():
    conn = base.connexion()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def champ(form, cle: str) -> str:
    valeur = form.get(cle)
    return valeur.replace("\r\n", "\n").strip() if isinstance(valeur, str) else ""


def slug(texte: str, defaut: str = "rendez-vous") -> str:
    texte = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    texte = re.sub(r"[^A-Za-z0-9]+", "-", texte).strip("-").lower()
    return texte[:50] or defaut


def charger(conn, tid: int):
    t = conn.execute("SELECT * FROM transcriptions WHERE id = ?", (tid,)).fetchone()
    if t is None:
        raise HTTPException(404, "Cette transcription n'existe pas.")
    return t


def page(tid: int, message: str = "") -> RedirectResponse:
    suite = f"?{urlencode({'message': message})}" if message else ""
    return RedirectResponse(f"/t/{tid}{suite}", status_code=303)


def enregistrement_en_cours() -> int | None:
    enregistrement = _enregistrement
    return enregistrement.transcription_id if enregistrement is not None else None


def lire_champs(form) -> dict:
    return {"titre": champ(form, "titre") or f"Rendez-vous du {date_fr(base.maintenant())}",
            "client": champ(form, "client"), "dossier": champ(form, "dossier"),
            "participants": champ(form, "participants")}


def creer_ligne(conn, champs: dict, source: str, statut: str, accord_le: str = "", fichier_origine: str = "") -> int:
    instant = base.maintenant()
    curseur = conn.execute(
        "INSERT INTO transcriptions (titre, client, dossier, participants, source, fichier_origine, accord_le, statut,"
        " etape, cree_le, modifie_le) VALUES (:titre, :client, :dossier, :participants, :source, :fichier_origine,"
        " :accord_le, :statut, :etape, :cree_le, :modifie_le)",
        {**champs, "source": source, "fichier_origine": fichier_origine, "accord_le": accord_le, "statut": statut,
         "etape": "En attente de transcription…" if statut == "en attente" else "", "cree_le": instant,
         "modifie_le": instant})
    return curseur.lastrowid


# ---------------------------------------------------------------- pages

# ---------------------------------------------------------------- pour le lanceur (lancer.py)

_presence = time.time()


def signaler_presence() -> None:
    global _presence
    _presence = time.time()


def derniere_presence() -> float:
    """L'instant du dernier signe d'une page de Got it! ouverte (chaque page en donne un toutes les cinq secondes)."""
    return _presence


def en_activite() -> bool:
    """Vrai tant qu'un enregistrement ou un traitement est en cours : le serveur ne doit pas s'arrêter."""
    if _enregistrement is not None:
        return True
    conn = base.connexion()
    try:
        return conn.execute("SELECT 1 FROM transcriptions WHERE statut IN ('en attente', 'transcription', 'synthèse')"
                            " LIMIT 1").fetchone() is not None
    finally:
        conn.close()


def fermer_enregistrement(raison: str) -> None:
    """Fenêtre fermée pendant un enregistrement : on ne laisse pas le micro ouvert sans rien à l'écran.
    L'enregistrement est arrêté et part en transcription, comme avec « Arrêter et transcrire »."""
    tid = enregistrement_en_cours()
    if tid is None:
        return
    arreter_enregistrement(tid)
    with transaction() as conn:
        base.journaliser(conn, tid, f"enregistrement arrêté automatiquement : {raison}")


@app.get("/api/presence")
def presence():
    signaler_presence()
    return {"present": True}


@app.get("/api/version")
def version_api():
    return {"application": "Got-it", "version": VERSION}


@app.get("/", response_class=HTMLResponse)
def liste(request: Request, message: str = ""):
    conn = base.connexion()
    lignes = conn.execute("SELECT * FROM transcriptions ORDER BY cree_le DESC, id DESC").fetchall()
    conn.close()
    return rendre(request, "liste.html", transcriptions=lignes, en_cours=enregistrement_en_cours(), message=message)


@app.get("/nouvelle", response_class=HTMLResponse)
def nouvelle(request: Request):
    conn = base.connexion()
    information = base.reglage(conn, "information") or traitement.INFORMATION_DEFAUT
    environnement = traitement.environnement(conn)
    conn.close()
    return rendre(request, "nouvelle.html", titre=f"Rendez-vous du {date_fr(base.maintenant())}",
                  peripheriques=audio.peripheriques(), information=information, environnement=environnement,
                  en_cours=enregistrement_en_cours(), extensions=",".join(audio.EXTENSIONS_AUDIO))


@app.post("/enregistrer")
async def demarrer_enregistrement(request: Request):
    global _enregistrement
    form = await request.form()
    if not form.get("accord"):
        raise HTTPException(400, "Lisez la formule d'information au client et cochez la case de son accord "
                                 "avant d'enregistrer.")
    # Un périphérique n'est accepté que s'il figure dans la liste que Windows vient de donner.
    connus = audio.peripheriques()
    micro = champ(form, "micro")
    if micro not in [identifiant for identifiant, _ in connus["micros"]]:
        raise HTTPException(400, "Ce micro n'est plus branché : rechargez la page et choisissez-en un autre.")
    sortie = ""
    if champ(form, "mode") == "visio":
        sortie = champ(form, "sortie")
        if sortie not in [identifiant for identifiant, _ in connus["sorties"]]:
            raise HTTPException(400, "Cette sortie audio n'est plus branchée : rechargez la page et choisissez-en "
                                     "une autre.")
    with _verrou:
        if _enregistrement is not None:
            return page(_enregistrement.transcription_id, "Un enregistrement est déjà en cours : un seul à la fois.")
        accord = base.maintenant()
        source = "micro et ordinateur" if sortie else "micro"
        with transaction() as conn:
            champs = lire_champs(form)
            tid = creer_ligne(conn, champs, source, "enregistrement", accord_le=accord)
            nom = f"{tid:05d}-{slug(champs['titre'])}.wav"
            conn.execute("UPDATE transcriptions SET audio = ? WHERE id = ?", (nom, tid))
            base.journaliser(conn, tid, f"information du client et accord recueillis le {date_fr(accord, True)} ; "
                                        f"enregistrement : {SOURCES[source]}")
        try:
            _enregistrement = audio.Enregistreur(tid, traitement.chemin_audio(nom), micro, sortie)
        except Exception as erreur:
            with transaction() as conn:
                traitement.maj(conn, tid, statut="erreur", audio="", etape="L'enregistrement n'a pas pu démarrer.",
                               erreur=f"L'enregistrement n'a pas pu démarrer : {erreur}.")
                base.journaliser(conn, tid, "l'enregistrement n'a pas pu démarrer")
            audio.effacer_fichier(traitement.chemin_audio(nom))
    return page(tid)


@app.post("/importer")
async def importer_fichier(request: Request):
    form = await request.form()
    fichier = form.get("fichier")
    if fichier is None or not getattr(fichier, "filename", ""):
        raise HTTPException(400, "Choisissez un fichier audio à transcrire.")
    extension = Path(fichier.filename).suffix.lower()
    if extension not in audio.EXTENSIONS_AUDIO:
        raise HTTPException(400, f"Ce type de fichier n'est pas pris en charge ({extension or 'sans extension'}) : "
                                 f"{', '.join(audio.EXTENSIONS_AUDIO)}.")
    with transaction() as conn:
        champs = lire_champs(form)
        tid = creer_ligne(conn, champs, "fichier", "en attente", fichier_origine=Path(fichier.filename).name)
    nom = f"{tid:05d}-{slug(champs['titre'])}{extension}"
    taille = 0
    with open(traitement.chemin_audio(nom), "wb") as sortie:
        while bloc := await fichier.read(1024 * 1024):
            sortie.write(bloc)
            taille += len(bloc)
    with transaction() as conn:
        conn.execute("UPDATE transcriptions SET audio = ? WHERE id = ?", (nom, tid))
        base.journaliser(conn, tid, f"copie du fichier « {Path(fichier.filename).name} » ({taille / 1048576:.1f} Mo) "
                                    "à transcrire ; l'original n'est pas touché")
    traitement.mettre_en_file(tid)
    return page(tid)


@app.get("/t/{tid}", response_class=HTMLResponse)
def fiche(request: Request, tid: int, message: str = "", corriger: int = 0):
    conn = base.connexion()
    t = charger(conn, tid)
    journal = conn.execute("SELECT * FROM journal WHERE transcription_id = ? ORDER BY date DESC, id DESC",
                           (tid,)).fetchall()
    conn.close()
    enregistrement = _enregistrement
    actif = enregistrement is not None and enregistrement.transcription_id == tid
    conn = base.connexion()
    choix = rangement.reglages(conn)
    conn.close()
    return rendre(request, "fiche.html", t=t, journal=journal, message=message, actif=actif, rangement=choix,
                  corriger=bool(corriger) and t["statut"] == "terminée",
                  ecoule=time.time() - enregistrement.debut if actif else 0)


@app.post("/t/{tid}/arreter")
def arreter_enregistrement(tid: int):
    global _enregistrement
    with _verrou:
        enregistrement = _enregistrement
        if enregistrement is None or enregistrement.transcription_id != tid:
            enregistrement = None
        else:
            _enregistrement = None
    if enregistrement is None:
        return page(tid)
    duree = enregistrement.arreter()
    with transaction() as conn:
        traitement.maj(conn, tid, statut="en attente", duree=duree, progression=0.0,
                       etape="En attente de transcription…")
        commentaire = f"enregistrement arrêté après {traitement.duree_lisible(duree)}"
        if enregistrement.alerte:
            commentaire += f" (avertissement : {enregistrement.alerte})"
        base.journaliser(conn, tid, commentaire)
    traitement.mettre_en_file(tid)
    return page(tid)


@app.post("/t/{tid}/abandonner")
def abandonner(tid: int):
    global _enregistrement
    with _verrou:
        enregistrement = _enregistrement
        if enregistrement is not None and enregistrement.transcription_id == tid:
            _enregistrement = None
        else:
            enregistrement = None
    if enregistrement is not None:
        enregistrement.arreter()
    with transaction() as conn:
        t = charger(conn, tid)
        if t["statut"] in ("transcription", "synthèse"):
            raise HTTPException(400, "Le traitement est en cours : il ne peut plus être abandonné.")
        if t["statut"] in ("terminée", "abandonnée"):
            return page(tid)
    chemin = traitement.chemin_audio(t["audio"])
    if chemin is not None and chemin.exists():
        audio.effacer_fichier(chemin)
    with transaction() as conn:
        traitement.maj(conn, tid, statut="abandonnée", audio="",
                       audio_efface_le=base.maintenant() if t["audio"] else "",
                       etape="Abandonnée sans transcription ; l'audio a été effacé." if t["audio"]
                       else "Abandonnée sans transcription.")
        base.journaliser(conn, tid, "abandon sans transcription, audio effacé" if t["audio"]
                         else "abandon sans transcription")
    return page(tid)


@app.post("/t/{tid}/relancer")
def relancer(tid: int):
    with transaction() as conn:
        t = charger(conn, tid)
        synthese_seule = t["statut"] == "terminée" and t["texte"] and not t["synthese"]
        if t["statut"] not in ("erreur", "interrompue") and not synthese_seule:
            raise HTTPException(400, "Cette transcription ne peut pas être relancée.")
        if not t["transcrit_le"]:
            chemin = traitement.chemin_audio(t["audio"])
            if chemin is None or not chemin.exists():
                raise HTTPException(400, "Le fichier audio n'existe plus : la transcription ne peut pas reprendre.")
        traitement.maj(conn, tid, statut="en attente", erreur="", progression=0.0, termine_le="",
                       etape="En attente de la synthèse…" if t["transcrit_le"] else "En attente de transcription…")
        base.journaliser(conn, tid, "synthèse demandée" if synthese_seule else "relance")
    traitement.mettre_en_file(tid)
    return page(tid)


@app.post("/t/{tid}/synthese")
async def corriger_synthese(request: Request, tid: int):
    form = await request.form()
    with transaction() as conn:
        t = charger(conn, tid)
        if t["statut"] != "terminée":
            raise HTTPException(400, "La transcription n'est pas terminée.")
        traitement.maj(conn, tid, synthese=champ(form, "synthese"))
        base.journaliser(conn, tid, "synthèse corrigée à la main")
    conn = base.connexion()
    try:
        rangement.ranger_si_demande(conn, tid)      # le fichier rangé suit la correction
    finally:
        conn.close()
    return page(tid, "La synthèse corrigée est enregistrée.")


@app.post("/t/{tid}/ranger")
def ranger_compte_rendu(tid: int):
    """Dépose le compte rendu Word dans le dossier de rangement choisi dans les réglages."""
    conn = base.connexion()
    try:
        charger(conn, tid)
        chemin = rangement.ranger(conn, tid)
    except RuntimeError as erreur:
        raise HTTPException(400, str(erreur)) from None
    finally:
        conn.close()
    return page(tid, f"Le compte rendu est rangé : {chemin}")


@app.post("/t/{tid}/effacer-texte")
def effacer_texte(tid: int):
    with transaction() as conn:
        t = charger(conn, tid)
        if t["texte"]:
            traitement.maj(conn, tid, texte="", texte_efface_le=base.maintenant())
            base.journaliser(conn, tid, "texte intégral effacé (la synthèse reste)")
    return page(tid, "Le texte intégral est effacé ; la synthèse reste.")


@app.post("/t/{tid}/supprimer")
def supprimer(tid: int):
    if enregistrement_en_cours() == tid:
        raise HTTPException(400, "L'enregistrement est en cours : arrêtez-le ou abandonnez-le d'abord.")
    with transaction() as conn:
        t = charger(conn, tid)
        if t["statut"] in ("transcription", "synthèse"):
            raise HTTPException(400, "Le traitement est en cours : attendez qu'il se termine.")
        conn.execute("DELETE FROM journal WHERE transcription_id = ?", (tid,))
        conn.execute("DELETE FROM transcriptions WHERE id = ?", (tid,))
    chemin = traitement.chemin_audio(t["audio"])
    if chemin is not None and chemin.exists():
        audio.effacer_fichier(chemin)
    return RedirectResponse(f"/?{urlencode({'message': 'La transcription « ' + t['titre'] + ' » est supprimée.'})}",
                            status_code=303)


@app.get("/t/{tid}/word")
def telecharger_word(tid: int, texte: int = 0):
    conn = base.connexion()
    t = charger(conn, tid)
    avocat = base.reglage(conn, "avocat")
    conn.close()
    if t["statut"] != "terminée":
        raise HTTPException(400, "La transcription n'est pas terminée.")
    contenu = rendu.en_word(t, rangement.proprietes(t, avocat), avec_texte=bool(texte))
    nom = rangement.nom_fichier(t)
    return Response(contenu, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nom)}"})


@app.get("/api/t/{tid}")
def etat(tid: int):
    conn = base.connexion()
    t = conn.execute("SELECT statut, progression, etape, erreur, duree FROM transcriptions WHERE id = ?",
                     (tid,)).fetchone()
    conn.close()
    if t is None:
        raise HTTPException(404, "Cette transcription n'existe pas.")
    reponse = dict(t)
    enregistrement = _enregistrement
    if enregistrement is not None and enregistrement.transcription_id == tid:
        reponse.update(ecoule=round(time.time() - enregistrement.debut, 1),
                       niveau_micro=round(enregistrement.niveau_micro, 4),
                       niveau_ordinateur=round(enregistrement.niveau_ordinateur, 4), alerte=enregistrement.alerte)
    return reponse


@app.post("/modele/telecharger")
def telecharger_modele(request: Request):
    """Lance le téléchargement du modèle de transcription (le seul accès à Internet, à la demande)."""
    traitement.demarrer_telechargement()
    retour = request.headers.get("referer") or "/nouvelle"
    return RedirectResponse(retour if retour.startswith(f"http://{request.headers.get('host')}/") else "/nouvelle",
                            status_code=303)


@app.get("/api/modele")
def etat_modele():
    return traitement.etat_telechargement()


@app.get("/reglages", response_class=HTMLResponse)
def reglages(request: Request, message: str = ""):
    conn = base.connexion()
    valeurs = {"avocat": base.reglage(conn, "avocat"),
               "information": base.reglage(conn, "information") or traitement.INFORMATION_DEFAUT,
               "trame": base.reglage(conn, "trame") or traitement.TRAME_DEFAUT,
               "modele_ollama": base.reglage(conn, "modele_ollama")}
    environnement = traitement.environnement(conn)
    choix = rangement.reglages(conn)
    conn.close()
    return rendre(request, "reglages.html", valeurs=valeurs, environnement=environnement, message=message,
                  dossier=str(base.DOSSIER), rangement=choix)


@app.post("/reglages/dossier")
async def choisir_dossier_de_rangement(request: Request):
    """Ouvre la fenêtre « Choisir un dossier » de Windows, ou oublie le dossier (bouton « Ne plus ranger »)."""
    form = await request.form()
    if form.get("oublier"):
        with transaction() as conn:
            base.regler(conn, "dossier_rangement", "")
        message = "Les comptes rendus ne sont plus rangés dans un dossier."
    else:
        conn = base.connexion()
        actuel = base.reglage(conn, "dossier_rangement")
        conn.close()
        choisi = rangement.choisir_dossier(actuel)
        if not choisi:
            message = "Aucun dossier choisi : rien n'a changé."
        elif not Path(choisi).is_dir():
            message = f"Ce dossier est introuvable : {choisi}"
        else:
            with transaction() as conn:
                base.regler(conn, "dossier_rangement", choisi)
                if not actuel:      # premier choix : rangement automatique, synthèse seule
                    base.regler(conn, "rangement_auto", "1")
                    base.regler(conn, "rangement_texte", "")
            message = f"Les comptes rendus seront rangés dans : {choisi}"
    return RedirectResponse(f"/reglages?{urlencode({'message': message})}#rangement", status_code=303)


@app.post("/reglages")
async def enregistrer_reglages(request: Request):
    form = await request.form()
    with transaction() as conn:
        if form.get("retablir"):
            # Une valeur vide redonne la formule et la trame d'origine.
            base.regler(conn, "information", "")
            base.regler(conn, "trame", "")
            message = "La formule d'information et la trame d'origine sont rétablies."
        else:
            for cle in ("avocat", "information", "trame", "modele_ollama"):
                base.regler(conn, cle, champ(form, cle))
            for cle in ("rangement_auto", "rangement_texte"):
                base.regler(conn, cle, "1" if form.get(cle) else "")
            message = "Les réglages sont enregistrés."
    return RedirectResponse(f"/reglages?{urlencode({'message': message})}", status_code=303)
