# Transcripteur

Un petit logiciel pour avocats qui enregistre un rendez-vous, le transcrit et en rédige une synthèse, **entièrement sur votre ordinateur**. Aucun service en ligne, aucun compte, aucune télémétrie : ni l'audio, ni le texte, ni la synthèse ne quittent le PC. Il a été écrit pour que la transcription automatique reste compatible avec le secret professionnel.

- **Au cabinet** : le micro du PC enregistre la pièce.
- **En visioconférence** (Teams, Zoom, Meet, appel depuis le PC…) : le micro enregistre votre voix et le **son de l'ordinateur** celle de vos interlocuteurs, mélangés dans un seul enregistrement. Rien à installer dans le logiciel de visio, pas de « robot » qui rejoint la réunion.
- **Après coup** : un fichier audio existant (dictaphone, téléphone) peut être transcrit de la même façon.

L'audio est écrasé puis supprimé dès qu'il est transcrit. Il reste le texte horodaté et une synthèse structurée (contexte, faits, questions juridiques, conseils donnés, pièces à obtenir, actions, échéances), à relire, corriger, copier ou télécharger en Word.

## Ce qu'il faut

- Windows 10 ou 11.
- [Python](https://www.python.org/downloads/windows/) 3.12 ou plus récent (cochez « Add python.exe to PATH » à l'installation).
- Environ 3 Go de disque pour la transcription, et 8 Go de mémoire vive ou plus.
- Pour la synthèse (facultative) : [Ollama](https://ollama.com/download), puis la commande `ollama pull mistral` dans un terminal (environ 4 Go). Sans Ollama, le Transcripteur transcrit sans rédiger de synthèse.
- Un disque chiffré (BitLocker, « Chiffrement de l'appareil » dans les paramètres de Windows) : le Transcripteur vous signale s'il ne l'est pas.

## Installation (une seule fois)

1. Téléchargez ce dépôt (bouton vert « Code », puis « Download ZIP ») et décompressez-le où vous voulez.
2. Double-cliquez sur `installer.bat`.

L'installation est le **seul moment où Internet est utilisé** : elle télécharge les bibliothèques Python et le modèle de transcription Whisper (environ 1,6 Go). Ensuite, le Transcripteur s'interdit tout téléchargement et fonctionne hors ligne.

## Utilisation

Double-cliquez sur `lancer.bat`. Une fenêtre noire s'ouvre (c'est le logiciel : elle doit rester ouverte) et votre navigateur affiche <http://127.0.0.1:8780/>. Fermer la fenêtre noire arrête le Transcripteur.

1. **Réglages** (la première fois) : indiquez votre nom ; adaptez si vous le souhaitez la formule d'information et la trame de la synthèse.
2. **Nouvel enregistrement** : donnez un titre, le client, les participants (leurs noms aident la transcription à les orthographier).
3. **Informez le client et recueillez son accord**, puis cochez la case : sans elle, l'enregistrement ne démarre pas. L'heure de l'accord est inscrite au journal de la transcription.
4. Choisissez **« Le micro seul »** ou **« Le micro et le son de l'ordinateur »**, puis « Enregistrer ». Deux barres de niveau montrent en direct que le micro et l'ordinateur sont bien captés.
5. **« Arrêter et transcrire »** : comptez de dix à trente minutes de traitement pour une heure d'entretien, selon le PC. Vous pouvez fermer la page, pas la fenêtre noire.
6. Relisez la synthèse, corrigez-la, téléchargez-la en Word. Une fois la synthèse relue, « Effacer le texte intégral » limite ce qui est conservé ; « Supprimer cette transcription » efface tout.

### Conseils pour la visioconférence

- Choisissez comme « son de l'ordinateur » la sortie par laquelle vous entendez vos interlocuteurs (haut-parleurs, écran ou casque). Si la barre « Son de l'ordinateur » reste vide quand ils parlent, ce n'est pas la bonne.
- Un casque donne le meilleur résultat. Avec des haut-parleurs, le micro entend aussi vos interlocuteurs : la transcription reste correcte, parfois avec des répétitions.
- Tout ce que l'ordinateur joue sur cette sortie est enregistré, notifications sonores comprises.

## Confidentialité : ce que fait le logiciel, précisément

- Le serveur n'écoute que sur `127.0.0.1` : il n'est pas joignable depuis un autre ordinateur, et il refuse toute requête qui ne vient pas d'une de ses propres pages.
- La transcription est faite par [faster-whisper](https://github.com/SYSTRAN/faster-whisper) sur le processeur du PC, avec `HF_HUB_OFFLINE` : aucun téléchargement possible en dehors de l'installation.
- La synthèse est rédigée par Ollama, interrogé sur `127.0.0.1:11434`, sans passer par un proxy.
- L'audio est gardé le temps de la transcription, puis écrasé (une passe de zéros) et supprimé. Sur un disque SSD, l'écrasement n'offre pas de garantie absolue : c'est le chiffrement du disque qui protège.
- Les données sont dans `C:\Users\<vous>\Transcripteur`, volontairement hors de OneDrive, Dropbox ou Google Drive. Ne déplacez pas ce dossier dans un dossier synchronisé.
- Les pages n'appellent aucune police, aucun script ni aucune image sur Internet.

Le logiciel ne peut pas garantir à votre place le reste de la chaîne : chiffrement et verrouillage du poste, sauvegardes, accès de tiers à l'ordinateur.

## Limites et précautions

- La transcription et la synthèse se trompent (noms propres, chiffres, négations, nuances). La synthèse est un **document de travail interne**, à relire avant tout usage, jamais à transmettre telle quelle.
- Les interlocuteurs ne sont pas distingués : le texte intégral est horodaté, sans nom devant chaque prise de parole.
- Un seul enregistrement à la fois. La transcription est réglée pour le français.
- L'information préalable des personnes enregistrées et leur accord relèvent de votre responsabilité, comme la conformité de votre usage à vos obligations déontologiques et au RGPD (information, durée de conservation, registre des traitements). Le logiciel vous aide (formule d'information, case d'accord, journal, effacement), il ne s'en charge pas.
- Fourni sans garantie (voir la licence). Éprouvé sur Windows 11.

## Organisation du code

Tout est en français : fichiers, fonctions, variables, messages.

| Fichier | Rôle |
| --- | --- |
| `lancer.py` | Point d'entrée : serveur local (port 8780) et navigateur |
| `transcripteur/app.py` | Pages, routes et contrôle de provenance des requêtes |
| `transcripteur/audio.py` | Micros et sorties, enregistrement du micro et du son de l'ordinateur, lecture et effacement des fichiers |
| `transcripteur/traitement.py` | Transcription (Whisper), synthèse (Ollama), file des traitements |
| `transcripteur/rendu.py` | Mise en forme de la synthèse à l'écran et en Word |
| `transcripteur/base.py` | Base SQLite : transcriptions, journal, réglages |
| `transcripteur/templates/`, `transcripteur/static/` | Pages HTML (Jinja2) et feuille de style |
| `outils/preparer.py` | Téléchargement du modèle Whisper à l'installation, vérification d'Ollama |
| `outils/serveur_test.py` | Serveur de test : données à part, faux micro qui rejoue des fichiers |

Pour changer de modèle de transcription (un PC modeste préférera `small`), modifiez `MODELE_WHISPER` dans `transcripteur/traitement.py` et `outils/preparer.py`, puis relancez `installer.bat`.

### Tester sans micro

```
.venv\Scripts\python.exe outils\serveur_test.py 8781 chemin\vers\un\dossier
```

Le dossier contient `micro.wav` et, pour essayer le mode visioconférence, `ordinateur.wav` : ils sont rejoués à la place des vrais périphériques, et les données vont dans `%TEMP%\transcripteur-test`.

## Licence

MIT : voir [LICENSE](LICENSE). Le Transcripteur s'appuie sur faster-whisper, SoundCard, FastAPI, python-docx et Ollama, chacun sous sa propre licence.
