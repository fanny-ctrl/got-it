"""L'audio : micros et sorties du PC, enregistrement, lecture d'un fichier, effacement.

Deux façons d'enregistrer :
- le micro seul, pour un rendez-vous au cabinet ;
- le micro et le son de l'ordinateur, mélangés, pour une visioconférence ou un appel passé depuis le PC : la voix
  de l'interlocuteur sort des haut-parleurs ou du casque, Windows permet de la capter « en boucle » (WASAPI
  loopback) sans rien installer.

La bibliothèque soundcard parle à Windows ; chaque source est lue dans son propre fil d'exécution et un dernier
fil mélange les sources et écrit un WAV 16 kHz mono. Le module wave réécrit l'en-tête à chaque bloc : le fichier
reste lisible même si Got-it s'arrête pendant l'enregistrement.

Pour les tests, la variable TRANSCRIPTEUR_AUDIO_TEST désigne un dossier : `micro.wav` (et `ordinateur.wav` s'il
existe) y sont rejoués à la place des vrais périphériques. Aucun micro réel n'est alors ouvert.
"""

from __future__ import annotations

import gc
import os
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

FREQUENCE = 16000
BLOC = FREQUENCE // 10            # un dixième de seconde par lecture
MARGE = FREQUENCE // 2            # une demi-seconde d'écart tolérée entre les deux sources
EXTENSIONS_AUDIO = (".wav", ".mp3", ".m4a", ".mp4", ".aac", ".ogg", ".oga", ".opus", ".webm", ".flac", ".wma",
                    ".mov")

VIDE = np.zeros(0, dtype=np.float32)


def dossier_test() -> Path | None:
    chemin = os.environ.get("TRANSCRIPTEUR_AUDIO_TEST")
    return Path(chemin) if chemin else None


def _preparer_fil() -> None:
    """Windows exige que chaque fil d'exécution qui touche au son initialise COM."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0)


# ---------------------------------------------------------------- périphériques

def peripheriques() -> dict:
    """Micros et sorties (haut-parleurs, casques) du PC, avec ceux que Windows utilise par défaut.
    Rien n'est enregistré ici. `erreur` explique pourquoi la liste est vide, le cas échéant."""
    essai = dossier_test()
    if essai is not None:
        sorties = [("essai-ordinateur", "Sortie d'essai (rejoue ordinateur.wav)")] \
            if (essai / "ordinateur.wav").exists() else []
        return {"micros": [("essai-micro", "Micro d'essai (rejoue micro.wav)")], "micro_defaut": "essai-micro",
                "sorties": sorties, "sortie_defaut": "essai-ordinateur" if sorties else "", "erreur": ""}
    resultat = {"micros": [], "micro_defaut": "", "sorties": [], "sortie_defaut": "", "erreur": ""}
    try:
        _preparer_fil()
        import soundcard as sc
        resultat["micros"] = [(m.id, m.name) for m in sc.all_microphones(include_loopback=False)]
        resultat["sorties"] = [(s.id, s.name) for s in sc.all_speakers()]
    except Exception as erreur:
        resultat["erreur"] = str(erreur) or erreur.__class__.__name__
        return resultat
    try:
        resultat["micro_defaut"] = sc.default_microphone().id
    except Exception:
        pass
    try:
        resultat["sortie_defaut"] = sc.default_speaker().id
    except Exception:
        pass
    return resultat


# ---------------------------------------------------------------- sources

class Source(threading.Thread):
    """Une source de son, lue dans son fil : elle dépose des blocs de nombres flottants, 16 kHz mono."""

    def __init__(self, nom: str):
        super().__init__(daemon=True, name=f"source-{nom}")
        self.nom = nom
        self.erreur = ""
        self.prete = threading.Event()
        self.fin = threading.Event()
        self._verrou = threading.Lock()
        self._blocs: list[np.ndarray] = []

    def deposer(self, bloc: np.ndarray) -> None:
        with self._verrou:
            self._blocs.append(np.asarray(bloc, dtype=np.float32))

    def prendre(self) -> np.ndarray:
        with self._verrou:
            blocs, self._blocs = self._blocs, []
        return np.concatenate(blocs) if blocs else VIDE


class SourceCarte(Source):
    """Un micro, ou le son d'une sortie capté en boucle (`boucle=True`)."""

    def __init__(self, nom: str, identifiant: str, boucle: bool):
        super().__init__(nom)
        self.identifiant = identifiant
        self.boucle = boucle

    def run(self) -> None:
        try:
            _preparer_fil()
            import soundcard as sc
            peripherique = sc.get_microphone(self.identifiant, include_loopback=self.boucle)
            # Deux canaux pour une sortie (stéréo), ramenés à un seul par la moyenne.
            with peripherique.recorder(samplerate=FREQUENCE, channels=2 if self.boucle else 1,
                                       blocksize=BLOC) as capture:
                self.prete.set()
                while not self.fin.is_set():
                    self.deposer(capture.record(numframes=BLOC).mean(axis=1))
        except Exception as erreur:
            self.erreur = str(erreur) or erreur.__class__.__name__
            self.prete.set()


class SourceFichier(Source):
    """Pour les tests : rejoue un fichier au rythme du temps réel, puis du silence."""

    def __init__(self, nom: str, chemin: Path):
        super().__init__(nom)
        self.chemin = chemin

    def run(self) -> None:
        try:
            audio = lire_audio(self.chemin)
        except Exception as erreur:
            self.erreur = str(erreur)
            self.prete.set()
            return
        self.prete.set()
        position, debut, livres = 0, time.time(), 0
        while not self.fin.is_set():
            bloc = audio[position:position + BLOC]
            position += BLOC
            if len(bloc) < BLOC:
                bloc = np.concatenate([bloc, np.zeros(BLOC - len(bloc), dtype=np.float32)])
            self.deposer(bloc)
            livres += BLOC
            time.sleep(max(0.0, debut + livres / FREQUENCE - time.time()))


def _ouvrir_source(nom: str, identifiant: str, boucle: bool) -> Source:
    essai = dossier_test()
    if essai is not None:
        return SourceFichier(nom, essai / ("ordinateur.wav" if boucle else "micro.wav"))
    return SourceCarte(nom, identifiant, boucle)


def _niveau(bloc: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(bloc)))) if len(bloc) else 0.0


def _completer(bloc: np.ndarray, longueur: int) -> np.ndarray:
    if len(bloc) >= longueur:
        return bloc[:longueur]
    return np.concatenate([bloc, np.zeros(longueur - len(bloc), dtype=np.float32)])


# ---------------------------------------------------------------- enregistrement

class Enregistreur:
    """Enregistre le micro, et le son de l'ordinateur si `sortie` est donnée, dans un WAV 16 kHz mono."""

    def __init__(self, transcription_id: int, chemin: Path, micro: str, sortie: str = ""):
        self.transcription_id = transcription_id
        self.niveau_micro = 0.0
        self.niveau_ordinateur = 0.0
        self.avec_ordinateur = bool(sortie)
        self.alerte = ""
        self._fin = threading.Event()
        self._reste_micro = VIDE
        self._reste_ordinateur = VIDE

        self.micro = _ouvrir_source("micro", micro, boucle=False)
        self.ordinateur = _ouvrir_source("ordinateur", sortie, boucle=True) if sortie else None
        sources = [s for s in (self.micro, self.ordinateur) if s is not None]
        for source in sources:
            source.start()
        for source in sources:
            source.prete.wait(10)
        echec = ""
        if self.micro.erreur or not self.micro.prete.is_set():
            echec = f"le micro ne démarre pas ({self.micro.erreur or 'pas de réponse'})"
        elif self.ordinateur is not None and (self.ordinateur.erreur or not self.ordinateur.prete.is_set()):
            echec = f"le son de l'ordinateur ne peut pas être capté ({self.ordinateur.erreur or 'pas de réponse'})"
        if echec:
            for source in sources:
                source.fin.set()
            raise RuntimeError(echec)

        self.fichier = wave.open(str(chemin), "wb")
        self.fichier.setnchannels(1)
        self.fichier.setsampwidth(2)
        self.fichier.setframerate(FREQUENCE)
        self.debut = time.time()
        self._fil = threading.Thread(target=self._melanger_en_continu, daemon=True, name="melange")
        self._fil.start()

    def _melanger_en_continu(self) -> None:
        while not self._fin.wait(0.2):
            self._melanger()
        self._melanger(final=True)

    def _melanger(self, final: bool = False) -> None:
        """Écrit ce que les sources ont livré. Avec deux sources, on avance au rythme de la plus lente, sans
        jamais attendre plus d'une demi-seconde : une source muette ou débranchée est remplacée par du silence."""
        self._reste_micro = np.concatenate([self._reste_micro, self.micro.prendre()])
        if self.micro.erreur and not self.alerte:
            self.alerte = f"le micro s'est arrêté ({self.micro.erreur})"
        if self.ordinateur is None:
            micro, self._reste_micro = self._reste_micro, VIDE
            ordinateur = VIDE
            longueur = len(micro)
        else:
            self._reste_ordinateur = np.concatenate([self._reste_ordinateur, self.ordinateur.prendre()])
            if self.ordinateur.erreur and not self.alerte:
                self.alerte = f"le son de l'ordinateur n'est plus capté ({self.ordinateur.erreur})"
            longueur = min(len(self._reste_micro), len(self._reste_ordinateur))
            if final or len(self._reste_micro) - longueur > MARGE:
                longueur = len(self._reste_micro)
            elif self.micro.erreur and len(self._reste_ordinateur) - longueur > MARGE:
                longueur = len(self._reste_ordinateur)
            micro = _completer(self._reste_micro, longueur)
            ordinateur = _completer(self._reste_ordinateur, longueur)
            self._reste_micro = self._reste_micro[longueur:]
            self._reste_ordinateur = self._reste_ordinateur[longueur:][-MARGE:]
        if not longueur:
            return
        self.niveau_micro = _niveau(micro)
        melange = micro
        if self.ordinateur is not None:
            self.niveau_ordinateur = _niveau(ordinateur)
            melange = micro + ordinateur
        self.fichier.writeframes((np.clip(melange, -1.0, 1.0) * 32767).astype(np.int16).tobytes())

    def arreter(self) -> float:
        """Arrête les sources, écrit la fin et ferme le fichier ; renvoie la durée enregistrée."""
        duree = time.time() - self.debut
        for source in (self.micro, self.ordinateur):
            if source is not None:
                source.fin.set()
        for source in (self.micro, self.ordinateur):
            if source is not None:
                source.join(3)
        self._fin.set()
        self._fil.join(5)
        self.fichier.close()
        return duree


# ---------------------------------------------------------------- fichiers

def duree_wav(chemin: Path) -> float:
    with wave.open(str(chemin), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def lire_audio(chemin: Path) -> np.ndarray:
    """L'audio en 16 kHz mono, nombres flottants, comme Whisper l'attend.

    Un WAV 16 kHz mono 16 bits (les enregistrements de Got-it) est lu tel quel ; tout autre fichier est
    décodé par PyAV. On ne passe pas par `faster_whisper.decode_audio` : il appelle `av.open(...,
    metadata_errors=...)`, option que PyAV a retirée (version 19), ce qui fait échouer la transcription."""
    if chemin.suffix.lower() == ".wav":
        try:
            with wave.open(str(chemin), "rb") as w:
                if (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (FREQUENCE, 1, 2):
                    return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        except wave.Error:
            pass  # WAV d'un autre format (flottant, compressé…) : PyAV s'en charge
    import av
    from av.audio.resampler import AudioResampler

    convertisseur = AudioResampler(format="s16", layout="mono", rate=FREQUENCE)
    morceaux = []
    try:
        with av.open(str(chemin), mode="r") as conteneur:
            for trame in conteneur.decode(audio=0):
                try:
                    morceaux.extend(t.to_ndarray().reshape(-1) for t in convertisseur.resample(trame))
                except av.error.InvalidDataError:
                    continue  # trame abîmée : on la saute
            morceaux.extend(t.to_ndarray().reshape(-1) for t in convertisseur.resample(None))
    except (av.error.FFmpegError, IndexError) as erreur:  # IndexError : aucune piste audio
        raise RuntimeError("Ce fichier n'est pas un enregistrement audio lisible : vérifiez qu'il s'ouvre dans un "
                           f"lecteur audio. (Détail technique : {erreur.__class__.__name__}.)") from None
    del convertisseur
    gc.collect()
    if not morceaux:
        raise RuntimeError("Ce fichier ne contient pas de piste audio lisible.")
    return np.concatenate(morceaux).astype(np.float32) / 32768.0


def effacer_fichier(chemin: Path) -> None:
    """Écrase le fichier (une passe de zéros), puis le supprime."""
    try:
        taille = os.path.getsize(chemin)
        with open(chemin, "r+b") as f:
            bloc = b"\x00" * (1024 * 1024)
            restant = taille
            while restant > 0:
                n = min(restant, len(bloc))
                f.write(bloc[:n])
                restant -= n
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass
    try:
        os.remove(chemin)
    except OSError:
        pass
