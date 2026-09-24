"""Categorie del Menu digitale viste e create da Lotti.

Richiesta del titolare (19/09/2026): sulla ricetta si sceglie «la categoria
dove inserirla, che recuperi da Menu o si creano in Lotti». Il Menu smette di
pescare dalle ricette: e' Lotti a spingere nel Menu, e la ricetta porta con se'
la destinazione.

GET  /api/menu-categorie                          — categorie e sottocategorie del Menu
POST /api/menu-categorie                          — crea una categoria di Lotti
POST /api/menu-categorie/{id}/sottocategorie      — crea una sua sottocategoria

Tutto passa dal client del ponte (``app/lotti/servizi/menu_bridge.py``):
nessuna seconda connessione al progetto Supabase del Menu.

**Selezionabili solo le categorie di Lotti** (``origine`` valorizzata). Le
categorie che arrivano da Qromo sono elencate ma non agganciabili: la
sincronizzazione Qromo cancella e reinserisce tutto cio' che ha
``origine IS NULL`` (``app/menu/qromo_sync.py::_sostituisci_tabelle``), e un
prodotto o una sottocategoria di Lotti appesi a una di quelle categorie
farebbero fallire quella cancellazione per vincolo di chiave esterna. Per
questo ogni riga creata da qui nasce con ``origine = "lotti"``: e' cio' che la
fa sopravvivere alla sincronizzazione.
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


@router.get("/menu-categorie")
async def elenco_categorie_menu():
    """Categorie e sottocategorie del Menu digitale.

    Ogni voce porta ``selezionabile``: vale ``False`` per le categorie di Qromo,
    con il ``motivo`` da mostrare a schermo."""
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
    origine** (tipicamente Qromo) la creazione riesce lo stesso — il titolare
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
    """Crea una sottocategoria dentro una categoria di Lotti. Idempotente sul nome."""
    try:
        return await menu_bridge.crea_sottocategoria_menu(
            categoria_id, body.nome, nome=body.nome_en, immagine=body.immagine)
    except Exception as exc:  # noqa: BLE001
        raise _errore_menu(exc) from exc
