"""Un nome non dice mai un colore che non contiene.

CLAUDE.md: «Il colore non e' mai un nome: una variabile o una costante si
chiama per quello che contiene (`SALVIA`, `--primary`), mai `NAVY` o
`--violet` con dentro il verde».

Il gestionale era a meta' di un rebrand: `primary` era gia' l'inchiostro
verde `#2a3329`, ma `primaryLight`, `primaryDark` e `primarySoft` erano
rimasti navy e azzurri, sotto un commento che diceva «Brand navy». Il
risultato si vedeva: `Button.jsx` usa `primaryLight` sull'hover, quindi il
bottone primario era verde a riposo e **blu** al passaggio del mouse.

Stessa storia per `public/archivio-fiscale-drive.html`, pagina viva aperta da
un bottone color inchiostro e disegnata in navy e blu.
"""
import pathlib
import re

import pytest

RADICE = pathlib.Path(__file__).resolve().parents[2]
UTILS = RADICE / "frontend" / "src" / "lib" / "utils.js"

# Blu, indaco e viola espliciti: non appartengono ne' alla palette salvia
# delle tre app ne' allo slate-oro del gestionale.
BLU_E_VIOLA = re.compile(
    r"#(1e3a5f|081425|e8eef7|2563eb|0f2744|dbeafe|e0f2fe|1e40af|4f46e5|7c3aed|"
    r"8b5cf6|6366f1|3b82f6|1d4ed8)\b", re.IGNORECASE)


def _variante(nome: str) -> str:
    sorgente = UTILS.read_text(encoding="utf-8")
    trovato = re.search(rf"{nome}:\s*'(#[0-9a-fA-F]{{6}})'", sorgente)
    assert trovato, f"{nome} non trovato in lib/utils.js"
    return trovato.group(1).lower()


def _luminosita(colore: str) -> float:
    r, g, b = (int(colore[i:i + 2], 16) for i in (1, 3, 5))
    return 0.299 * r + 0.587 * g + 0.114 * b


def test_le_varianti_sono_dello_stesso_colore_del_primario():
    """`primaryLight` deve essere il primario piu' chiaro, non un altro colore."""
    primario, chiaro, scuro = (_variante(n) for n in ("primary", "primaryLight", "primaryDark"))

    for nome, colore in (("primaryLight", chiaro), ("primaryDark", scuro)):
        r, g, b = (int(colore[i:i + 2], 16) for i in (1, 3, 5))
        assert g >= b, (
            f"{nome} = {colore}: il blu supera il verde, quindi non e' una "
            "variante dell'inchiostro. Era il navy rimasto dal vecchio brand."
        )


def test_light_e_piu_chiaro_e_dark_piu_scuro():
    assert _luminosita(_variante("primaryLight")) > _luminosita(_variante("primary"))
    assert _luminosita(_variante("primaryDark")) < _luminosita(_variante("primary"))


def test_l_etichetta_non_chiama_navy_un_verde():
    """L'etichetta che nomina il gruppo di colori, non il racconto di com'era.

    Qui stava `/* Brand navy */` sopra `#2a3329`, che e' verde.
    """
    sorgente = UTILS.read_text(encoding="utf-8")

    assert "/* Brand navy */" not in sorgente


PAGINE_STATICHE = sorted((RADICE / "frontend" / "public").glob("*.html"))


@pytest.mark.parametrize("pagina", PAGINE_STATICHE, ids=lambda p: p.name)
def test_le_pagine_statiche_non_usano_il_vecchio_blu(pagina):
    """Servite dal gestionale, quindi devono avere la sua palette.

    Non passano dal bundle, quindi nessuna scansione le copriva.
    """
    trovati = sorted(set(BLU_E_VIOLA.findall(pagina.read_text(encoding="utf-8"))))

    assert not trovati, f"{pagina.name}: colori del vecchio brand {trovati}"


# Lo stesso navy scritto in decimale. La scansione dei colori prescritta da
# CLAUDE.md cerca solo esadecimali, quindi `rgba(15,39,68,.18)` le passava
# davanti senza essere vista: erano 23 file, fra ombre, sfondi di modale e
# anelli di focus, e finivano nel bundle come `#0f27442e`.
NAVY_DECIMALE = re.compile(
    r"\b15\s*[, ]\s*39\s*[, ]\s*68\b|"
    r"\b30\s*[, ]\s*58\s*[, ]\s*95\b|"
    r"\b8\s*[, ]\s*20\s*[, ]\s*37\b"
)

SORGENTI_ERP = [
    p for p in sorted((RADICE / "frontend" / "src").rglob("*"))
    if p.suffix.lower() in {".js", ".jsx", ".css"}
    and "node_modules" not in str(p)
    and ".test." not in p.name
]


def test_nessun_navy_scritto_in_decimale():
    """`rgb(15 39 68)` e' lo stesso `#0f2744`, ma in incognito."""
    colpevoli = [
        f"{p.relative_to(RADICE)}:{n}"
        for p in SORGENTI_ERP
        for n, riga in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if NAVY_DECIMALE.search(riga)
    ]

    assert not colpevoli, (
        "Navy in notazione decimale (la scansione esadecimale non lo vede):\n"
        + "\n".join(colpevoli[:20])
    )


def test_la_barra_del_browser_non_e_navy():
    """`theme-color` e il manifest: il colore che si vede sul telefono."""
    for percorso in ("frontend/index.html", "frontend/public/manifest.webmanifest"):
        testo = (RADICE / percorso).read_text(encoding="utf-8")
        assert not BLU_E_VIOLA.search(testo), f"{percorso}: colore del vecchio brand"
