"""Dessine l'icône de Got it! (transcripteur/static/icone.ico) : cinq barres laiton, comme une onde sonore,
sur un carré ardoise aux coins arrondis. Sans bibliothèque d'image : le PNG est écrit à la main.

Usage : .venv\\Scripts\\python.exe outils\\creer_icone.py   (à relancer seulement pour changer l'icône)
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np

SORTIE = Path(__file__).resolve().parent.parent / "transcripteur" / "static" / "icone.ico"
BLEU = (38, 41, 45)        # ardoise
TAILLES = (256, 64, 48, 32, 16)
BARRES = (0.30, 0.58, 0.82, 0.50, 0.26)   # hauteur de chaque barre, en part de la hauteur de l'icône


def rectangle_arrondi(y, x, x0, y0, x1, y1, rayon):
    """Masque d'un rectangle aux coins arrondis, sur les grilles de coordonnées y et x."""
    dx = np.maximum(np.maximum(x0 + rayon - x, x - (x1 - rayon)), 0)
    dy = np.maximum(np.maximum(y0 + rayon - y, y - (y1 - rayon)), 0)
    return (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1) & (dx * dx + dy * dy <= rayon * rayon)


def dessiner(taille: int) -> np.ndarray:
    """L'image en RGBA, dessinée quatre fois trop grande puis réduite pour adoucir les bords."""
    n = taille * 4
    y, x = np.mgrid[0:n, 0:n] / n
    fond = rectangle_arrondi(y, x, 0.03, 0.03, 0.97, 0.97, 0.21)
    barres = np.zeros((n, n), dtype=bool)
    largeur, ecart = 0.085, 0.062
    depart = 0.5 - (len(BARRES) * largeur + (len(BARRES) - 1) * ecart) / 2
    for i, hauteur in enumerate(BARRES):
        x0 = depart + i * (largeur + ecart)
        barres |= rectangle_arrondi(y, x, x0, 0.5 - hauteur / 2, x0 + largeur, 0.5 + hauteur / 2, largeur / 2)
    image = np.zeros((n, n, 4), dtype=np.float64)
    image[fond] = (*BLEU, 255)
    image[barres & fond] = (217, 178, 106, 255)     # laiton
    # Réduction par moyenne, couleurs pondérées par l'opacité.
    blocs = image.reshape(taille, 4, taille, 4, 4)
    alpha = blocs[..., 3].mean(axis=(1, 3))
    couleur = (blocs[..., :3] * blocs[..., 3:4]).sum(axis=(1, 3)) / np.maximum(blocs[..., 3:4].sum(axis=(1, 3)), 1)
    return np.dstack([couleur, alpha]).round().astype(np.uint8)


def en_png(image: np.ndarray) -> bytes:
    def morceau(nom: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", zlib.crc32(nom + donnees))

    hauteur, largeur = image.shape[:2]
    lignes = b"".join(b"\x00" + image[i].tobytes() for i in range(hauteur))
    return (b"\x89PNG\r\n\x1a\n" + morceau(b"IHDR", struct.pack(">IIBBBBB", largeur, hauteur, 8, 6, 0, 0, 0))
            + morceau(b"IDAT", zlib.compress(lignes, 9)) + morceau(b"IEND", b""))


def main() -> None:
    images = [en_png(dessiner(t)) for t in TAILLES]
    entete = struct.pack("<HHH", 0, 1, len(images))
    position = 6 + 16 * len(images)
    table = b""
    for taille, png in zip(TAILLES, images):
        table += struct.pack("<BBBBHHII", taille % 256, taille % 256, 0, 0, 1, 32, len(png), position)
        position += len(png)
    SORTIE.write_bytes(entete + table + b"".join(images))
    print(f"Icône écrite : {SORTIE} ({SORTIE.stat().st_size} octets)")


if __name__ == "__main__":
    main()
