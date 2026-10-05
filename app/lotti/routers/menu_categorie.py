"""Categorie del Menu digitale viste e create da Lotti.

Sulla ricetta si sceglie la categoria e la sottocategoria dove metterla nel
Menu e, se il prodotto c'e' gia', a quale prodotto del Menu unirla (stesso id,
stesso codice PRD, nessun doppione). Il Menu e' nostro: e' Lotti a spingere nel
Menu, e la ricetta porta con se' la destinazione.

GET  /api/menu-categorie                          — categorie e sottocategorie del Menu
POST /api/menu-categorie                          — crea una categoria
POST /api/menu-categorie/{id}/sottocategorie      — crea una sua sottocategoria
GET  /api/ricette/{id}/menu-prodotti              — prodotti del Menu a cui si puo' unire la ricetta

Tutto passa dal client del ponte (``app/lotti/servizi/menu_bridge.py``):
nessuna seconda connessione al progetto Supabase del Menu. Ogni riga creata da
qui nasce con ``origine = "lotti"``.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.lotti.auth import require_admin
from app.lotti.servizi import menu_bridge

router = APIRouter(tags=["Menu categorie"])


class CategoriaMenuCreate(BaseModel):
    nome: str = Field(..., description="Nome italiano mostrato nel Menu")
    nome_en: Optional[str] = Field(None, description="Nome inglese; se assente si usa quello italiano")
    immagine: Optional[str] = Field(None, description="URL immagine di copertina (facoltativo)")


def _errore_menu(exc: Exception) -> HTTPException:
    if isinstance(exc, menu_bridge.MenuNonConfigurato):
        return HTTPException(503, "Menu digitale non configurato su questo ambiente")
    if isinstance(exc, menu_bridge.CategoriaMenuNonValida):
        return HTTPException(400, str(exc))
    return HTTPException(502, f"Menu digitale non raggiungibile: {exc}")


@router.get("/prodotti-codici")
async def codici_prodotti():
    """{ricetta_id: «PRD-000123»}: l'ID prodotto unico, lo stesso in Menu, B&B e Lotti."""
    try:
        return await menu_bridge.codici_prodotti_ricette()
    except Exception as exc:  # noqa: BLE001 - tradotto in errore HTTP parlante
        raise _errore_menu(exc) from exc


@router.get("/menu-categorie")
async def elenco_categorie_menu():
    """Categorie e sottocategorie del Menu digitale."""
    try:
        return await menu_bridge.elenco_categorie_menu()
    except Exception as exc:  # noqa: BLE001 - tradotto in errore HTTP parlante
        raise _errore_menu(exc) from exc


@router.post("/menu-categorie")
async def crea_categoria_menu(body: CategoriaMenuCreate, _admin=Depends(require_admin)):
    """Crea nel Menu una categoria di Lotti (``origine = "lotti"``).

    Idempotente sul nome: ripetere la chiamata restituisce la categoria gia'
    creata con ``creata: false``, non un doppione.

    Se nel Menu esiste gia' una categoria con quel nome ma di **altra
    origine** la creazione riesce lo stesso — il titolare
    potrebbe volerne davvero una sua — ma la risposta porta ``avviso``: senza,
    i clienti si troverebbero due riquadri «Bar» identici nella home."""
    try:
        return await menu_bridge.crea_categoria_menu(
            body.nome, nome=body.nome_en, immagine=body.immagine)
    except Exception as exc:  # noqa: BLE001
        raise _errore_menu(exc) from exc


@router.post("/menu-categorie/{categoria_id}/sottocategorie")
async def crea_sottocategoria_menu(
    categoria_id: int, body: CategoriaMenuCreate, _admin=Depends(require_admin),
):
    """Crea una sottocategoria dentro una categoria del Menu. Idempotente sul nome."""
    try:
        return await menu_bridge.crea_sottocategoria_menu(
            categoria_id, body.nome, nome=body.nome_en, immagine=body.immagine)
    except Exception as exc:  # noqa: BLE001
        raise _errore_menu(exc) from exc


@router.get("/ricette/{ricetta_id}/menu-prodotti")
async def prodotti_menu_agganciabili(ricetta_id: str, q: str = "", _admin=Depends(require_admin)):
    """Prodotti gia' nel Menu non ancora di nessuna ricetta, per unirli a questa."""
    try:
        return {"prodotti": await menu_bridge.prodotti_agganciabili(ricetta_id, q)}
    except Exception as exc:  # noqa: BLE001
        raise _errore_menu(exc) from exc
