"""Sincronizzazione del catalogo dal menu digitale Qromo (https://ceraldicaffe.qromo.it/)
nelle tabelle ORIGINALI del Menu (``menu_categories`` / ``menu_subcategories`` /
``menu_products``, colonne snake_case come in ``routes/seed_routes.py``).

Aggiunta al backend originale: parser e mappatura allergeni sono ripresi pari
pari da ``app/menu/migrazione_qromo.py``. Qromo non ha un'API pubblica: la home
del menu incorpora l'intero catalogo come costanti JavaScript nel primo
``<script>`` della pagina (``menus`` = categorie, ``menusCategories`` =
sottocategorie, ``menusItems`` = prodotti, ``menusItemsAllergens`` +
``allergens`` = allergeni). Regole:

* esclusi i menu ``BANCO - *`` (listino interno di cassa) e quelli non
  pubblicati (``available != 1``), le sottocategorie non attive, i prodotti non
  disponibili; potate sottocategorie/categorie rimaste senza prodotti;
* i 39 tag Qromo sono ridotti ai 14 allergeni UE (``MAPPA_ALLERGENI_QROMO``),
  le diciture non alimentari (vegano, piccante, bio...) sono scartate;
* le immagini restano URL esterni Qromo nella colonna ``image`` (come i dati
  originali del seed): nessun download;
* prezzo nel formato del seed originale (``"3.50€"``).

Idempotente: sostituzione integrale delle tre tabelle (cancellazione in ordine
FK-safe: prodotti, sottocategorie, categorie; poi inserimento a lotti).
``menu_allergens`` non viene toccata; nemmeno le righe con ``origine`` valorizzata
(prodotti/categorie creati da Lotti, ``origine = "lotti"``).

Endpoint (protetti da ``verify_token`` dell'app):
    POST /api/admin/sync-qromo          body {"dry_run": bool}
    GET  /api/admin/sync-qromo/preview  (equivale a dry_run=true)
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.menu.routes.qrcode_routes import verify_token
from app.menu.supabase_client import supabase

logger = logging.getLogger(__name__)

SOTTODOMINIO_DEFAULT = "ceraldicaffe"
PREFISSO_MENU_BANCO = "BANCO - "
_COSTANTE_RE = re.compile(r"const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=")
DIMENSIONE_LOTTO = 200

TABELLA_CATEGORIE = "menu_categories"
TABELLA_SOTTOCATEGORIE = "menu_subcategories"
TABELLA_PRODOTTI = "menu_products"

# Riduzione dei 39 tag Qromo ai 14 allergeni UE (id gia' presenti in menu_allergens).
MAPPA_ALLERGENI_QROMO = {
    "allergens_celery": "celery",
    "allergens_clams": "molluscs",
    "allergens_dioxide": "sulphites",
    "allergens_egg": "eggs",
    "allergens_fish": "fish",
    "allergens_gluten": "gluten",
    "allergens_lupins": "lupin",
    "allergens_milk": "milk",
    "allergens_mustard": "mustard",
    "allergens_peanuts": "peanuts",
    "allergens_sesame": "sesame",
    "allergens_shellfish": "crustaceans",
    "allergens_soia": "soy",
    "allergens_wot": "nuts",
    "allergens_almond": "nuts",
    "allergens_barley": "gluten",
    "allergens_brazil_nuts": "nuts",
    "allergens_cashew": "nuts",
    "allergens_hazelnuts": "nuts",
    "allergens_macadamia": "nuts",
    "allergens_oats": "gluten",
    "allergens_pecan": "nuts",
    "allergens_pistachios": "nuts",
    "allergens_rye": "gluten",
    "allergens_spelt": "gluten",
    "allergens_walnuts": "nuts",
    "allergens_wheat": "gluten",
    "allergens_kamut": "gluten",
}


# ================== Parser della pagina Qromo (identico a app/menu/migrazione_qromo.py) ==================

def _estrai_costanti_javascript(html: str) -> Dict[str, str]:
    """Isola il primo blocco ``<script>...</script>`` e restituisce, per ogni
    ``const NOME = valore;`` di primo livello, il testo grezzo del valore
    (JSON o un letterale JS semplice come ``null``/``true``)."""
    match = re.search(r"<script>(.*?)</script>", html, re.S)
    if not match:
        raise ValueError("Pagina Qromo senza il blocco di configurazione atteso: sottodominio errato?")
    script = match.group(1)
    nomi = _COSTANTE_RE.findall(script)
    posizioni: List[Tuple[str, int]] = [(nome, script.index(f"const {nome} =")) for nome in nomi]
    valori: Dict[str, str] = {}
    for indice, (nome, inizio) in enumerate(posizioni):
        inizio_valore = inizio + len(f"const {nome} =")
        fine = posizioni[indice + 1][1] if indice + 1 < len(posizioni) else len(script)
        grezzo = script[inizio_valore:fine].strip()
        if grezzo.endswith(";"):
            grezzo = grezzo[:-1]
        valori[nome] = grezzo
    return valori


def _costante_json(costanti: Dict[str, str], nome: str, default: Any) -> Any:
    grezzo = costanti.get(nome)
    if not grezzo or grezzo in ("null", "undefined"):
        return default
    try:
        return json.loads(grezzo)
    except json.JSONDecodeError:
        logger.warning("Costante Qromo %s non decodificabile come JSON", nome)
        return default


def catalogo_da_html(html: str) -> Dict[str, Any]:
    costanti = _estrai_costanti_javascript(html)
    return {
        "menus": _costante_json(costanti, "menus", []),
        "menusCategories": _costante_json(costanti, "menusCategories", []),
        "menusItems": _costante_json(costanti, "menusItems", []),
        "menusItemsAllergens": _costante_json(costanti, "menusItemsAllergens", []),
        "allergens": _costante_json(costanti, "allergens", []),
    }


class SorgenteQromo:
    def __init__(self, sottodominio: str):
        self.url = f"https://{sottodominio}.qromo.it/"
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers={"User-Agent": "GestionaleCloud-sync/1.0"})

    async def chiudi(self) -> None:
        await self.client.aclose()

    async def catalogo(self) -> Dict[str, Any]:
        risposta = await self.client.get(self.url)
        risposta.raise_for_status()
        return catalogo_da_html(risposta.text)


# ================== Trasformazione pura: costanti Qromo -> righe delle tabelle menu_* ==================

def _prezzo(centesimi: Optional[int]) -> str:
    """Stesso formato del seed originale (``"3.50€"``)."""
    return f"{(centesimi or 0) / 100:.2f}€"


def _pulisci(testo: Optional[str]) -> Optional[str]:
    if not isinstance(testo, str):
        return None
    testo = testo.strip()
    return testo or None


def trasforma_catalogo(dati: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Da ``{"menus", "menusCategories", "menusItems", "menusItemsAllergens", "allergens"}``
    alle righe (colonne snake_case) di ``menu_categories`` / ``menu_subcategories``
    / ``menu_products``. Nessun accesso a rete o database."""
    menu_da_includere = {
        m["menu_id"] for m in dati["menus"]
        if m.get("available") == 1 and not str(m.get("name") or "").startswith(PREFISSO_MENU_BANCO)
    }
    categorie_qromo = [m for m in dati["menus"] if m["menu_id"] in menu_da_includere]

    sottocategorie_qromo = [
        c for c in dati["menusCategories"]
        if c.get("menu_id") in menu_da_includere and c.get("active") == 1
    ]
    id_sottocategorie = {c["menu_category_id"] for c in sottocategorie_qromo}

    prodotti_qromo = [
        p for p in dati["menusItems"]
        if p.get("category_id") in id_sottocategorie and p.get("available") == 1
    ]
    id_prodotti = {p["menu_item_id"] for p in prodotti_qromo}

    # Sottocategorie/categorie senza nemmeno un prodotto pubblicato (es. "Comunicazioni")
    # non vanno replicate: il cliente non le vedrebbe nemmeno sul menu vero.
    sottocategorie_con_prodotti = {p["category_id"] for p in prodotti_qromo}
    sottocategorie_qromo = [c for c in sottocategorie_qromo if c["menu_category_id"] in sottocategorie_con_prodotti]
    sottocat_by_id = {c["menu_category_id"]: c for c in sottocategorie_qromo}
    categorie_con_sottocategorie = {c["menu_id"] for c in sottocategorie_qromo}
    categorie_qromo = [c for c in categorie_qromo if c["menu_id"] in categorie_con_sottocategorie]

    nome_allergene = {a["allergen_id"]: a.get("name_key") for a in dati["allergens"]}
    allergeni_per_prodotto: Dict[int, List[str]] = {}
    for legame in dati["menusItemsAllergens"]:
        if legame.get("menu_item_id") not in id_prodotti:
            continue
        mappato = MAPPA_ALLERGENI_QROMO.get(nome_allergene.get(legame.get("allergen_id")))
        if not mappato:
            continue
        lista = allergeni_per_prodotto.setdefault(legame["menu_item_id"], [])
        if mappato not in lista:
            lista.append(mappato)

    righe_categorie = []
    for c in categorie_qromo:
        nome = _pulisci(c.get("name")) or f"Menu {c['menu_id']}"
        righe_categorie.append({"id": c["menu_id"], "name": nome, "name_it": nome, "image": c.get("picture") or None})

    righe_sottocategorie = []
    for c in sottocategorie_qromo:
        nome = _pulisci(c.get("name")) or f"Sezione {c['menu_category_id']}"
        righe_sottocategorie.append({
            "id": c["menu_category_id"], "category_id": c["menu_id"],
            "name": nome, "name_it": nome, "image": c.get("picture") or None,
        })

    righe_prodotti = []
    for p in prodotti_qromo:
        sottocat = sottocat_by_id[p["category_id"]]
        nome = _pulisci(p.get("name")) or f"Prodotto {p['menu_item_id']}"
        descrizione = _pulisci(p.get("ingredients"))
        righe_prodotti.append({
            "id": p["menu_item_id"], "category_id": sottocat["menu_id"], "subcategory_id": p["category_id"],
            "name": nome, "name_it": nome, "price": _prezzo(p.get("price")),
            "description": descrizione, "description_it": descrizione,
            "allergens": allergeni_per_prodotto.get(p["menu_item_id"], []),
            "image": p.get("picture") or None,
        })

    return {
        "categories": righe_categorie,
        "subcategories": righe_sottocategorie,
        "products": righe_prodotti,
    }


# ================== Scrittura sulle tabelle originali ==================

def _sostituisci_tabelle(righe: Dict[str, List[Dict[str, Any]]]) -> None:
    """Cancella e reinserisce nell'ordine che rispetta le foreign key
    (stesso meccanismo di ``/api/admin/seed-once``).

    Cancella SOLO le righe senza ``origine`` (quelle di Qromo/seed): la
    categoria "Produzione Ceraldi", le sue sottocategorie e i prodotti creati
    da Lotti (``origine = "lotti"``, vedi app/lotti/servizi/menu_bridge.py)
    sopravvivono alla sincronizzazione."""
    supabase.table(TABELLA_PRODOTTI).delete().is_("origine", "null").execute()
    supabase.table(TABELLA_SOTTOCATEGORIE).delete().is_("origine", "null").execute()
    supabase.table(TABELLA_CATEGORIE).delete().is_("origine", "null").execute()

    for tabella, chiave in (
        (TABELLA_CATEGORIE, "categories"),
        (TABELLA_SOTTOCATEGORIE, "subcategories"),
        (TABELLA_PRODOTTI, "products"),
    ):
        lista = righe[chiave]
        for inizio in range(0, len(lista), DIMENSIONE_LOTTO):
            supabase.table(tabella).insert(lista[inizio:inizio + DIMENSIONE_LOTTO]).execute()


async def sincronizza(*, sottodominio: str = SOTTODOMINIO_DEFAULT, dry_run: bool = False) -> Dict[str, Any]:
    sorgente = SorgenteQromo(sottodominio)
    try:
        dati = await sorgente.catalogo()
    finally:
        await sorgente.chiudi()

    righe = trasforma_catalogo(dati)
    if not dry_run:
        _sostituisci_tabelle(righe)

    return {
        "ok": True,
        "dry_run": dry_run,
        "sottodominio": sottodominio,
        "categories": len(righe["categories"]),
        "subcategories": len(righe["subcategories"]),
        "products": len(righe["products"]),
    }


# ================== Endpoint ==================

router = APIRouter(prefix="/api/admin", tags=["Sync Qromo"])


class SyncQromoRequest(BaseModel):
    dry_run: bool = False


@router.post("/sync-qromo")
async def sync_qromo(body: SyncQromoRequest, username: str = Depends(verify_token)):
    """Replica il menu pubblicato su Qromo nelle tabelle menu_* (sostituzione integrale)."""
    try:
        return await sincronizza(dry_run=body.dry_run)
    except Exception as e:
        logger.exception("Sincronizzazione Qromo fallita")
        raise HTTPException(status_code=502, detail=f"Sincronizzazione Qromo fallita: {e}")


@router.get("/sync-qromo/preview")
async def sync_qromo_preview(username: str = Depends(verify_token)):
    """Conta cosa verrebbe importato da Qromo senza scrivere nulla."""
    try:
        return await sincronizza(dry_run=True)
    except Exception as e:
        logger.exception("Anteprima Qromo fallita")
        raise HTTPException(status_code=502, detail=f"Anteprima Qromo fallita: {e}")
