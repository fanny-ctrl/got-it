"""Mise en forme de la synthèse : le modèle de langue écrit des titres en **gras** et des listes à tirets.

`blocs()` lit ce texte une fois ; la page (`en_html`) et le document Word (`en_word`) s'en servent tous deux.
"""

from __future__ import annotations

import io
import re

from markupsafe import Markup, escape

GRAS = re.compile(r"\*\*(.+?)\*\*")
PUCE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
TITRE = re.compile(r"^\s*(?:#{1,6}\s*)?\*\*([^*]+)\*\*\s*:?\s*$|^\s*#{1,6}\s+(.+?)\s*$")


def blocs(texte: str) -> list[tuple[str, str]]:
    """Le texte en blocs : ('titre', …), ('puce', …) ou ('paragraphe', …)."""
    resultat = []
    for ligne in (texte or "").splitlines():
        if not ligne.strip():
            continue
        titre = TITRE.match(ligne)
        if titre:
            resultat.append(("titre", (titre.group(1) or titre.group(2)).strip()))
        elif PUCE.match(ligne):
            resultat.append(("puce", PUCE.sub("", ligne).strip()))
        else:
            resultat.append(("paragraphe", ligne.strip()))
    return resultat


def _gras_html(texte: str) -> str:
    return GRAS.sub(r"<strong>\1</strong>", str(escape(texte)))


def en_html(texte: str) -> Markup:
    morceaux, liste = [], False
    for nature, contenu in blocs(texte):
        if liste and nature != "puce":
            morceaux.append("</ul>")
            liste = False
        if nature == "titre":
            morceaux.append(f"<h3>{escape(contenu)}</h3>")
        elif nature == "puce":
            if not liste:
                morceaux.append("<ul>")
                liste = True
            morceaux.append(f"<li>{_gras_html(contenu)}</li>")
        else:
            morceaux.append(f"<p>{_gras_html(contenu)}</p>")
    if liste:
        morceaux.append("</ul>")
    return Markup("".join(morceaux))


def _ecrire_gras(paragraphe, texte: str) -> None:
    """Écrit le texte dans un paragraphe Word, les passages **entre étoiles** en gras."""
    position = 0
    for passage in GRAS.finditer(texte):
        if passage.start() > position:
            paragraphe.add_run(texte[position:passage.start()])
        paragraphe.add_run(passage.group(1)).bold = True
        position = passage.end()
    if position < len(texte):
        paragraphe.add_run(texte[position:])


def en_word(t, proprietes: list[tuple[str, str]], avec_texte: bool) -> bytes:
    """Le document Word d'une transcription : en-tête, synthèse, et le texte intégral si demandé."""
    from docx import Document
    from docx.shared import Pt

    document = Document()
    document.styles["Normal"].font.name = "Calibri"
    document.styles["Normal"].font.size = Pt(11)
    document.add_heading(t["titre"], level=1)
    for nom, valeur in proprietes:
        ligne = document.add_paragraph()
        ligne.add_run(f"{nom} : ").bold = True
        ligne.add_run(valeur)
        ligne.paragraph_format.space_after = Pt(0)
    avertissement = document.add_paragraph()
    avertissement.add_run(
        "Document de travail établi par transcription et synthèse automatiques, sur l'ordinateur du cabinet. "
        "À relire et corriger avant tout usage. Couvert par le secret professionnel.").italic = True
    if t["synthese"]:
        document.add_heading("Synthèse", level=2)
        for nature, contenu in blocs(t["synthese"]):
            if nature == "titre":
                document.add_heading(contenu, level=3)
            elif nature == "puce":
                _ecrire_gras(document.add_paragraph(style="List Bullet"), contenu)
            else:
                _ecrire_gras(document.add_paragraph(), contenu)
    if avec_texte and t["texte"]:
        document.add_heading("Texte intégral", level=2)
        for ligne in t["texte"].splitlines():
            if ligne.strip():
                paragraphe = document.add_paragraph(ligne)
                paragraphe.paragraph_format.space_after = Pt(2)
    sortie = io.BytesIO()
    document.save(sortie)
    return sortie.getvalue()
