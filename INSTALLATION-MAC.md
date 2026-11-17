# Got it! sur Mac : avant de commencer

> **Version Mac en cours de mise au point.** Elle a été écrite à partir de la version Windows et n'a pas encore été éprouvée sur un Mac. Si une étape échoue, signalez-le sur la page [Issues](https://github.com/fanny-ctrl/got-it/issues) en copiant le message affiché.

Comptez une vingtaine de minutes, dont l'essentiel en téléchargements. Il faut un Mac récent (puce Apple M1 ou plus récente de préférence, macOS 13 ou plus récent), 8 Go de mémoire et environ 8 Go de disque libres.

## Ce qu'il faut installer

| | Quoi | Pourquoi | Obligatoire ? |
| --- | --- | --- | --- |
| 1 | **Python 3.12** | Le langage dans lequel Got it! est écrit | Oui |
| 2 | **Ollama** et le modèle **Mistral** | Rédiger la synthèse, sur le Mac | Non : sans lui, Got it! transcrit sans résumer |
| 3 | **BlackHole 2ch** | Capter la voix de vos interlocuteurs en visioconférence | Non : inutile pour les rendez-vous au cabinet |
| 4 | **Google Chrome** | Ouvrir Got it! dans sa propre fenêtre | Non : sans lui, Got it! s'ouvre dans un onglet de Safari |

### 1. Python

Téléchargez « macOS 64-bit universal2 installer » de Python 3.12 sur <https://www.python.org/downloads/macos/> et installez-le comme n'importe quelle application.

### 2. Ollama (pour la synthèse)

1. Installez Ollama depuis <https://ollama.com/download> et ouvrez-le une fois.
2. Ouvrez l'application **Terminal** (dossier Applications, Utilitaires), collez la ligne suivante puis validez par Entrée. Le téléchargement fait environ 4 Go.

```bash
ollama pull mistral
```

### 3. BlackHole (pour la visioconférence)

macOS ne permet pas à une application d'enregistrer ce qui sort des haut-parleurs. BlackHole est un pilote audio gratuit et libre qui contourne cette limite, sans rien envoyer sur Internet.

1. Installez **BlackHole 2ch** depuis <https://existential.audio/blackhole/> (le site demande une adresse e-mail pour envoyer le lien de téléchargement), puis redémarrez le Mac.
2. Ouvrez **Configuration audio et MIDI** (dossier Applications, Utilitaires).
3. En bas à gauche, cliquez sur **+**, puis **Créer un périphérique à sorties multiples**.
4. Cochez vos haut-parleurs ou votre casque **et** « BlackHole 2ch ». Vos haut-parleurs doivent être en tête de liste.
5. Avant une visioconférence, choisissez ce « Périphérique à sorties multiples » comme sortie son du Mac (Réglages Système, Son, Sortie). Vous entendez normalement, et Got it! reçoit le son par BlackHole.

Tant que cette sortie est active, les touches de volume du clavier sont sans effet : réglez le volume avant, ou revenez à vos haut-parleurs après le rendez-vous.

## Installer Got it!

1. Sur <https://github.com/fanny-ctrl/got-it>, cliquez sur le bouton vert **Code**, puis **Download ZIP**. Décompressez le dossier et rangez-le où vous voulez, par exemple dans Documents (pas dans iCloud Drive).
2. Faites un **clic droit** sur `installer.command`, puis **Ouvrir**, puis **Ouvrir** dans la fenêtre d'avertissement. Le simple double-clic est refusé la première fois, parce que le fichier vient d'Internet.
3. Laissez l'installation se terminer : elle télécharge les bibliothèques et le modèle de transcription (1,6 Go). C'est le seul moment où Got it! utilise Internet.

Si macOS répond que le fichier « ne peut pas être ouvert » ou n'est pas exécutable, ouvrez Terminal, tapez `chmod +x ` (avec l'espace), glissez-y `installer.command`, validez par Entrée, puis recommencez l'étape 2.

## Ouvrir Got it!

Clic droit sur `lancer.command`, puis **Ouvrir** la première fois ; un double-clic suffit ensuite. Une fenêtre de Terminal s'ouvre et doit rester ouverte pendant l'utilisation ; Got it! apparaît dans sa propre fenêtre.

Au premier enregistrement, macOS demande d'autoriser **Terminal** à utiliser le micro : acceptez. En cas de refus par erreur : Réglages Système, Confidentialité et sécurité, Microphone, cochez Terminal.

Pour enregistrer une visioconférence, choisissez « Le micro et le son de l'ordinateur » : « BlackHole 2ch » doit apparaître sous « Son de l'ordinateur ».

## Où sont les données

Dans le dossier `Got-it` de votre dossier personnel, hors d'iCloud. Activez **FileVault** (Réglages Système, Confidentialité et sécurité) : Got it! signale s'il ne l'est pas.

## Ce qui diffère de Windows

- Pas d'installateur en un clic : l'installation passe par `installer.command`.
- Le son de l'ordinateur demande BlackHole et le réglage ci-dessus.
- Une fenêtre de Terminal reste ouverte pendant l'utilisation.
