"""Ponte Lotti -> Menu digitale (richiesta del titolare, 03/09/2026):
"quando aggiungo un prodotto in Lotti fai in modo che lo aggiungi anche in
Menu con le stesse immagini e scelgo io se far comparire nel menu pubblico".

La fonte e' la ricetta di Lotti (collezione ``ricette``): ogni ricetta viene
SEMPRE replicata in ``menu_products`` (tabelle del Menu, progetto Supabase
``Lotti-HACCP``, client PostgREST sincrono di ``app.menu.supabase_client``)
con ``origine = "lotti"`` e chiave idempotente ``lotti_ref = "ricetta:<id>"``.
La colonna ``visible`` replica il flag ``menu_pubblico`` della ricetta: il
titolare la vede nell'area admin del Menu e decide se mostrarla ai clienti.

Immagini: i nuovi upload di Lotti sono persistiti direttamente nel bucket
Supabase Storage ``menu-images`` sotto ``lotti/ricette`` e il prodotto Menu
usa lo stesso oggetto, senza copie concorrenti. Il lettore Drive resta solo
per le immagini storiche finche' la loro migrazione non e' completata.

Prezzo (decisione del titolare 19/09/2026): la ricetta ha due prezzi, al banco
(``prezzo_vendita``, quello del food cost) e al tavolo (``prezzo_tavolo``). Il
Menu digitale mostra il prezzo AL TAVOLO. Finche' il prezzo al tavolo non e'
stato deciso si continua a esporre quello al banco (vedi ``prezzo_per_menu``).
Una ricetta senza prezzo compare nella carta con «Prezzo da definire».
Le API del catalogo ordinabile la escludono finche' non ha un prezzo valido.

Categoria: ogni ricetta operativa va nella categoria canonica "Produzione
Ceraldi" e nella sottocategoria derivata dal reparto. Non esiste una seconda
classificazione manuale concorrente.

Il ponte non deve MAI far fallire un endpoint di Lotti: le funzioni pubbliche
restituiscono sempre un dizionario ``{"esito": ...}`` e non sollevano
eccezioni. Senza ``MENU_SUPABASE_URL`` (test di Lotti, sviluppo locale)
l'esito e' ``non_configurato`` e nessuna chiamata parte.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from app.menu.supabase_client import inserisci_con_id_del_database, supabase

logger = logging.getLogger("uvicorn.error")

ORIGINE_LOTTI = "lotti"
STORAGE_BUCKET = "menu-images"
STORAGE_PREFIX = "lotti"
TABELLA_CATEGORIE = "menu_categories"
TABELLA_SOTTOCATEGORIE = "menu_subcategories"
TABELLA_PRODOTTI = "menu_products"

CATEGORIA_NOME = "Ceraldi Production"
CATEGORIA_NOME_IT = "Produzione Ceraldi"

# Gli id di menu_* li assegna il database (identity BY DEFAULT, migrazione
# 20261007051337_menu_id_dal_database, applicata in produzione): l'insert parte
# senza id e legge quello restituito (``_inserisci``). Il ponte non legge ne'
# calcola mai un id; se il database rifiuta l'insert l'errore risale cosi' com'e'.

# reparto Lotti -> sottocategoria Menu (name, name_it)
SOTTOCATEGORIE_REPARTO = {
    "pasticceria": ("Pastry", "Pasticceria"),
    "rosticceria": ("Rotisserie", "Rosticceria"),
    "bar": ("Bar", "Bar"),
}
SOTTOCATEGORIA_ALTRO = ("Other", "Altro")

# Allergeni Lotti (app/lotti/allergeni.py, ALLERGENI_14) -> i 14 id UE del Menu
# (menu_allergens, seed_routes.py). Tutto il resto viene ignorato.
MAPPA_ALLERGENI_MENU = {
    "glutine": "gluten",
    "latte": "milk",
    "lattosio": "milk",
    "uova": "eggs",
    "frutta a guscio": "nuts",
    "pesce": "fish",
    "soia": "soy",
    "solfiti": "sulphites",
    "anidride solforosa": "sulphites",
    "crostacei": "crustaceans",
    "molluschi": "molluscs",
    "sedano": "celery",
    "senape": "mustard",
    "sesamo": "sesame",
    "lupini": "lupin",
    "arachidi": "peanuts",
}

ESTENSIONE_DA_MIME = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def menu_configurato() -> bool:
    return bool(os.environ.get("MENU_SUPABASE_URL", "").strip().strip('"').strip("'"))


def lotti_ref_ricetta(ricetta_id: str) -> str:
    return f"ricetta:{ricetta_id}"


# ================== Trasformazioni pure ==================

def mappa_allergeni(allergeni: Optional[list]) -> list[str]:
    """Da nomi Lotti ("Glutine", "Frutta a guscio", ...) agli id del Menu."""
    risultato: list[str] = []
    for voce in allergeni or []:
        chiave = str(voce or "").strip().casefold()
        mappato = MAPPA_ALLERGENI_MENU.get(chiave)
        if mappato and mappato not in risultato:
            risultato.append(mappato)
    return risultato


def allergeni_da_pubblicare(ricetta: dict) -> list:
    """Gli allergeni che il Menu deve dichiarare per la ricetta.

    ``allergeni`` e' la lista vigente: calcolata dagli ingredienti oppure
    confermata a mano dal titolare. Una lista **vuota** e' una risposta
    («nessun allergene»), non un dato mancante: ripiegare su
    ``allergeni_auto`` quando e' vuota pubblicava gli allergeni rilevati
    in automatico proprio sulle ricette che il titolare aveva dichiarato
    senza allergeni. Il ripiego vale solo per le ricette vecchie che il
    campo non l'hanno mai avuto.
    """
    vigenti = ricetta.get("allergeni")
    if isinstance(vigenti, list):
        return vigenti
    return ricetta.get("allergeni_auto") or []


def prezzo_menu(prezzo: Any) -> Optional[str]:
    """Formato del seed originale del Menu (``"3.50€"``); None se assente."""
    if prezzo in (None, ""):
        return None
    try:
        valore = float(prezzo)
    except (TypeError, ValueError):
        return None
    if valore <= 0:
        return None
    return f"{valore:.2f}€"


def prezzo_banco_da_ricetta(ricetta: dict) -> Optional[float]:
    """Prezzo al banco della ricetta (``prezzo_vendita``) come numero; None se non c'e' o non e' valido."""
    try:
        valore = float(ricetta.get("prezzo_vendita"))
    except (TypeError, ValueError):
        return None
    return round(valore, 2) if valore == valore and 0 < valore < float("inf") else None


def prezzo_per_menu(ricetta: dict) -> tuple[Optional[str], str]:
    """Prezzo da esporre nel Menu digitale e da dove viene.

    Il titolare ha deciso (19/09/2026) che la ricetta ha due prezzi come in
    ogni bar: ``prezzo_vendita`` e' il prezzo AL BANCO (resta la base del food
    cost e del margine) e ``prezzo_tavolo`` e' il prezzo AL TAVOLO, che e'
    quello che il Menu digitale deve mostrare.

    Le centinaia di ricette gia' in archivio non hanno ancora un prezzo al
    tavolo: per loro il Menu continua a esporre il prezzo al banco, che e'
    esattamente il prezzo che stanno gia' mostrando oggi. Nessuna migrazione
    copia ``prezzo_vendita`` dentro ``prezzo_tavolo``: una copia farebbe
    sembrare *deciso* un prezzo che nessuno ha mai deciso, e non si saprebbe
    piu' distinguerlo. Il ripiego resta quindi visibile riga per riga
    (``prezzo_origine`` qui, ``prezzo_tavolo_impostato`` in
    ``GET /api/ricette-prezzi``, conteggio nel backfill).

    Restituisce ``(prezzo_formattato | None, "tavolo" | "banco" | "assente")``.
    """
    tavolo = prezzo_menu(ricetta.get("prezzo_tavolo"))
    if tavolo:
        return tavolo, "tavolo"
    banco = prezzo_menu(ricetta.get("prezzo_vendita"))
    if banco:
        return banco, "banco"
    return None, "assente"


def _intero(valore: Any) -> Optional[int]:
    if valore in (None, ""):
        return None
    try:
        return int(valore)
    except (TypeError, ValueError):
        return None


def _sottocategoria_per_reparto(reparto: Any) -> tuple[str, str]:
    return SOTTOCATEGORIE_REPARTO.get(str(reparto or "").strip().casefold(), SOTTOCATEGORIA_ALTRO)


def _estensione(mime: str) -> str:
    return ESTENSIONE_DA_MIME.get((mime or "").split(";", 1)[0].strip().casefold(), "jpg")


def _foto_id_da_url(foto_url: Any) -> Optional[str]:
    """Id foto dagli URL interni di Lotti ``/api/foto/<id>[?v=...]``."""
    if not foto_url:
        return None
    path = str(foto_url).split("?", 1)[0].rstrip("/")
    marker = "/api/foto/"
    if marker not in path:
        return None
    return path.split(marker, 1)[1] or None


def percorso_storage(foto_id: str, mime: str) -> str:
    return f"{STORAGE_PREFIX}/{foto_id}.{_estensione(mime)}"


def _descrizione(ricetta: dict) -> Optional[str]:
    # Solo `descrizione`: il campo `note` della ricetta e' "Note / Procedimento"
    # (FormRicetta.jsx) e non deve finire nel menu pubblico dei clienti.
    testo = str(ricetta.get("descrizione") or "").strip()
    if testo:
        return testo
    if ricetta.get("descrizione_origine") == "manuale_vuota":
        return None
    from app.lotti.servizi.descrizione_ricetta import descrizione_da_ingredienti

    return descrizione_da_ingredienti(ricetta)


# ================== Accesso al Menu (client sincrono, eseguito in thread) ==================

def _inserisci(tabella: str, riga: dict) -> int:
    """Inserisce lasciando l'``id`` al database e restituisce quello generato.

    Unico percorso: ``inserisci_con_id_del_database`` (nessuna lettura di
    ``max(id)``, nessun id calcolato, nessun ritentativo). Un rifiuto del
    database risale al chiamante cosi' com'e'."""
    return inserisci_con_id_del_database(supabase, tabella, riga)


def _categoria_lotti_id() -> int:
    res = (
        supabase.table(TABELLA_CATEGORIE).select("id")
        .eq("origine", ORIGINE_LOTTI).eq("name_it", CATEGORIA_NOME_IT)
        .limit(1).execute()
    )
    if res.data:
        return int(res.data[0]["id"])
    return _inserisci(TABELLA_CATEGORIE, {
        "name": CATEGORIA_NOME, "name_it": CATEGORIA_NOME_IT,
        "image": None, "origine": ORIGINE_LOTTI,
    })


def _sottocategoria_lotti_id(categoria_id: int, reparto: Any) -> int:
    nome, nome_it = _sottocategoria_per_reparto(reparto)
    res = (
        supabase.table(TABELLA_SOTTOCATEGORIE).select("id")
        .eq("origine", ORIGINE_LOTTI).eq("category_id", categoria_id).eq("name_it", nome_it)
        .limit(1).execute()
    )
    if res.data:
        return int(res.data[0]["id"])
    return _inserisci(TABELLA_SOTTOCATEGORIE, {
        "category_id": categoria_id, "name": nome, "name_it": nome_it,
        "image": None, "origine": ORIGINE_LOTTI,
    })


def _categoria_menu(categoria_id: int) -> Optional[dict]:
    """La categoria Menu con quell'id, se esiste."""
    res = (
        supabase.table(TABELLA_CATEGORIE).select("id,name,name_it,origine")
        .eq("id", categoria_id).limit(1).execute()
    )
    return res.data[0] if res.data else None


def _sottocategoria_menu(sottocategoria_id: int) -> Optional[dict]:
    res = (
        supabase.table(TABELLA_SOTTOCATEGORIE).select("id,category_id,name,name_it")
        .eq("id", sottocategoria_id).limit(1).execute()
    )
    return res.data[0] if res.data else None


def _destinazione_menu(ricetta: dict) -> tuple[int, int, str]:
    """(category_id, subcategory_id, origine_della_scelta).

    Se la ricetta porta la categoria e la sottocategoria scelte dal titolare
    (``menu_categoria_id`` / ``menu_sottocategoria_id``) e la coppia esiste
    ancora nel Menu, vale quella (``scelta``). Altrimenti la destinazione
    dipende soltanto dal reparto canonico (``automatica``)."""
    categoria_scelta = _intero(ricetta.get("menu_categoria_id"))
    sottocategoria_scelta = _intero(ricetta.get("menu_sottocategoria_id"))
    if categoria_scelta is not None and sottocategoria_scelta is not None:
        sotto = _sottocategoria_menu(sottocategoria_scelta)
        if sotto and int(sotto.get("category_id") or 0) == categoria_scelta and _categoria_menu(categoria_scelta):
            return categoria_scelta, sottocategoria_scelta, "scelta"
    categoria_id = _categoria_lotti_id()
    return categoria_id, _sottocategoria_lotti_id(categoria_id, ricetta.get("reparto")), "automatica"


# Scheda vendita: canali sala/delivery, esaurito, aggiunte (prezzo in centesimi) e rimozioni di ingredienti.
# Vive sulla ricetta e il ponte la replica nel Menu (colonne della migrazione `menu_codice_prodotto`).
CAMPI_SCHEDA_VENDITA = ("vendita_sala", "vendita_delivery", "disponibile", "aggiunte", "rimozioni", "prezzo_banco")


def scheda_vendita_da_ricetta(ricetta: dict) -> dict:
    """I cinque campi di vendita che il Menu riceve. Assente = valore di partenza (venduto ovunque, disponibile)."""
    aggiunte = []
    for voce in ricetta.get("aggiunte") or []:
        nome = str((voce or {}).get("nome") or "").strip()
        centesimi = _intero((voce or {}).get("prezzo_centesimi"))
        if nome and centesimi is not None and centesimi >= 0:
            aggiunte.append({"nome": nome, "prezzo_centesimi": centesimi})
    return {
        "vendita_sala": ricetta.get("vendita_sala") is not False,
        "vendita_delivery": ricetta.get("vendita_delivery") is not False,
        "disponibile": ricetta.get("esaurito") is not True,
        "aggiunte": aggiunte,
        "rimozioni": [str(r).strip() for r in (ricetta.get("rimozioni") or []) if str(r).strip()],
    }


def _e_colonna_scheda_mancante(errore: Exception) -> bool:
    testo = str(errore)
    return any(campo in testo for campo in CAMPI_SCHEDA_VENDITA)


def _senza_scheda(riga: dict) -> dict:
    return {k: v for k, v in riga.items() if k not in CAMPI_SCHEDA_VENDITA}


def _riga_esistente(lotti_ref: str) -> Optional[dict]:
    res = supabase.table(TABELLA_PRODOTTI).select("*").eq("lotti_ref", lotti_ref).limit(1).execute()
    return res.data[0] if res.data else None


def _riga_agganciata(ricetta: dict, lotti_ref: str) -> Optional[dict]:
    """Il prodotto del Menu a cui il titolare ha unito la ricetta (``menu_prodotto_id``).

    Vale solo se la riga esiste e non e' gia' di un'altra ricetta: la ricetta ne
    prende il posto (stesso id, stesso codice PRD) invece di crearne un doppione."""
    prodotto_id = _intero(ricetta.get("menu_prodotto_id"))
    if prodotto_id is None:
        return None
    res = supabase.table(TABELLA_PRODOTTI).select("*").eq("id", prodotto_id).limit(1).execute()
    riga = res.data[0] if res.data else None
    if riga and riga.get("lotti_ref") not in (None, "", lotti_ref):
        return None
    return riga


def _carica_immagine(foto: dict) -> str:
    """Copia i byte della foto Lotti nel bucket del Menu e restituisce l'URL pubblico."""
    mime = str(foto.get("mime") or "image/jpeg")
    percorso = percorso_storage(str(foto["_id"]), mime)
    supabase.storage.from_(STORAGE_BUCKET).upload(
        percorso, bytes(foto["data"]), {"content-type": mime, "upsert": "true"}
    )
    return supabase.storage.from_(STORAGE_BUCKET).get_public_url(percorso)


def _immagine_per_prodotto(ricetta: dict, foto: Optional[dict], esistente: Optional[dict]) -> Optional[str]:
    """URL da scrivere in ``image``: lo stesso oggetto Storage di Lotti;
    per una foto storica copia i byte una sola volta, altrimenti conserva un
    eventuale URL assoluto gia' pubblico o quello gia' presente."""
    if foto and foto.get("storage_path"):
        from app.lotti.servizi import supabase_foto_ricette
        return supabase_foto_ricette.url_pubblico(str(foto["storage_path"]))
    if foto and foto.get("data"):
        foto_id = str(foto["_id"])
        attuale = (esistente or {}).get("image") or ""
        if f"/{STORAGE_PREFIX}/{foto_id}." in attuale:
            return attuale
        return _carica_immagine(foto)
    foto_url = str(ricetta.get("foto_url") or "")
    if foto_url.startswith(("http://", "https://")):
        return foto_url
    return (esistente or {}).get("image")


def _pubblica_sync(ricetta: dict, foto: Optional[dict], visibile: bool) -> dict:
    lotti_ref = lotti_ref_ricetta(str(ricetta["id"]))
    esistente = _riga_esistente(lotti_ref) or _riga_agganciata(ricetta, lotti_ref)
    categoria_id, sottocategoria_id, categoria_origine = _destinazione_menu(ricetta)
    nome = str(ricetta.get("nome") or "").strip() or f"Ricetta {ricetta['id']}"
    descrizione = _descrizione(ricetta)
    immagine = _immagine_per_prodotto(ricetta, foto, esistente)
    prezzo, prezzo_origine = prezzo_per_menu(ricetta)

    # La carta mostra anche le ricette senza prezzo come catalogo. Le API
    # dei prodotti ordinabili continuano a richiedere un prezzo valido.
    prezzo_mancante = prezzo is None
    visibile_richiesta = bool(visibile)
    visibile_effettivo = visibile_richiesta

    riga = {
        "category_id": categoria_id,
        "subcategory_id": sottocategoria_id,
        "name": nome,
        "name_it": nome,
        "price": prezzo or "",
        "description": descrizione,
        "description_it": descrizione,
        "allergens": mappa_allergeni(allergeni_da_pubblicare(ricetta)),
        "image": immagine,
        "origine": ORIGINE_LOTTI,
        "lotti_ref": lotti_ref,
        "visible": visibile_effettivo,
        "menu_bb": ricetta.get("menu_bb") is not False,
        # prodotto unico: il prezzo AL BANCO della ricetta (base del food cost) va nel prodotto, accanto a quello al tavolo
        "prezzo_banco": prezzo_banco_da_ricetta(ricetta),
        **scheda_vendita_da_ricetta(ricetta),
    }

    # Migrazione `menu_codice_prodotto` non ancora applicata: le colonne di vendita non ci sono, e la
    # ricetta deve arrivare nel Menu lo stesso (senza canali/aggiunte, che arrivano appena la colonna c'e').
    if esistente:
        prodotto_id = int(esistente["id"])
        try:
            supabase.table(TABELLA_PRODOTTI).update(riga).eq("id", prodotto_id).execute()
        except Exception as errore:  # noqa: BLE001
            if not _e_colonna_scheda_mancante(errore):
                raise
            logger.warning("Lotti->Menu: colonne di vendita assenti (%s), pubblico senza", type(errore).__name__)
            supabase.table(TABELLA_PRODOTTI).update(_senza_scheda(riga)).eq("id", prodotto_id).execute()
        esito = "aggiornato"
    else:
        try:
            prodotto_id = _inserisci(TABELLA_PRODOTTI, riga)
        except Exception as errore:  # noqa: BLE001
            if not _e_colonna_scheda_mancante(errore):
                raise
            logger.warning("Lotti->Menu: colonne di vendita assenti (%s), pubblico senza", type(errore).__name__)
            prodotto_id = _inserisci(TABELLA_PRODOTTI, _senza_scheda(riga))
        esito = "pubblicato"

    return {
        "esito": esito,
        "menu_product_id": prodotto_id,
        "lotti_ref": lotti_ref,
        "visible": visibile_effettivo,
        "visibile_richiesta": visibile_richiesta,
        "image": immagine,
        "category_id": categoria_id,
        "subcategory_id": sottocategoria_id,
        "categoria_origine": categoria_origine,
        "price": prezzo or "",
        "prezzo_origine": prezzo_origine,
        "prezzo_mancante": prezzo_mancante,
        "motivo_nascosto": None,
    }


def _rimuovi_sync(lotti_ref: str) -> dict:
    res = supabase.table(TABELLA_PRODOTTI).delete().eq("lotti_ref", lotti_ref).execute()
    rimossi = len(res.data or []) if getattr(res, "data", None) is not None else 0
    return {"esito": "rimosso", "lotti_ref": lotti_ref, "rimossi": rimossi}


def _codici_prodotti_sync() -> dict:
    righe = supabase.table(TABELLA_PRODOTTI).select("lotti_ref,codice_prodotto").limit(5000).execute().data or []
    prefisso = lotti_ref_ricetta("")
    return {r["lotti_ref"][len(prefisso):]: r["codice_prodotto"]
            for r in righe if r.get("codice_prodotto") and str(r.get("lotti_ref") or "").startswith(prefisso)}


def _codice_di_ricetta_sync(ricetta_id: str) -> Optional[str]:
    righe = (supabase.table(TABELLA_PRODOTTI).select("codice_prodotto")
             .eq("lotti_ref", lotti_ref_ricetta(ricetta_id)).limit(1).execute().data or [])
    return righe[0].get("codice_prodotto") if righe else None


def _ricetta_di_codice_sync(codice: str) -> Optional[str]:
    righe = (supabase.table(TABELLA_PRODOTTI).select("lotti_ref")
             .eq("codice_prodotto", codice).limit(1).execute().data or [])
    riferimento = str(righe[0].get("lotti_ref") or "") if righe else ""
    prefisso = lotti_ref_ricetta("")
    return riferimento[len(prefisso):] if riferimento.startswith(prefisso) else None


def _url_menu_sync() -> Optional[str]:
    righe = supabase.table("menu_qrcode_config").select("menu_url").eq("id", "qrcode_config").limit(1).execute().data or []
    return (righe[0].get("menu_url") or None) if righe else None


async def codice_di_ricetta(ricetta_id: str) -> Optional[str]:
    _esigi_configurato()
    return await asyncio.to_thread(_codice_di_ricetta_sync, ricetta_id)


async def ricetta_di_codice(codice: str) -> Optional[str]:
    _esigi_configurato()
    return await asyncio.to_thread(_ricetta_di_codice_sync, codice)


async def url_menu_pubblico() -> Optional[str]:
    _esigi_configurato()
    return await asyncio.to_thread(_url_menu_sync)


async def codici_prodotti_ricette() -> dict:
    """ID prodotto unico (PRD-000123) di ogni ricetta: {ricetta_id: codice}.

    Lo assegna il database alla riga Menu e non cambia mai: Lotti lo legge, non lo scrive."""
    _esigi_configurato()
    return await asyncio.to_thread(_codici_prodotti_sync)


# ================== API asincrona usata dal router ricette ==================

async def _foto_ricetta(ricetta: dict, db: Any) -> Optional[dict]:
    storage_path = str(ricetta.get("foto_storage_path") or "").strip()
    if storage_path:
        return {
            "_id": str(ricetta.get("foto_id") or storage_path),
            "mime": str(ricetta.get("foto_content_type") or "image/jpeg"),
            "sha256": ricetta.get("foto_sha256"),
            "storage_path": storage_path,
        }
    drive_id = str(ricetta.get("foto_drive_id") or "").strip()
    if drive_id:
        from app.lotti.servizi import drive_foto_ricette
        contenuto, mime, _ = await asyncio.to_thread(
            drive_foto_ricette.leggi,
            drive_id,
            folder_id=str(ricetta.get("foto_drive_folder_id") or ""),
        )
        return {"_id": drive_id, "mime": mime, "data": contenuto,
                "sha256": ricetta.get("foto_sha256")}
    foto_id = _foto_id_da_url(ricetta.get("foto_url"))
    if not foto_id or db is None:
        return None
    return await db.foto_files.find_one({"_id": foto_id})


async def pubblica_prodotto_nel_menu(ricetta: dict, *, visibile: bool, db: Any = None) -> dict:
    """Crea o aggiorna nel Menu il prodotto corrispondente alla ricetta.
    Non solleva mai: esito ``pubblicato`` / ``aggiornato`` / ``non_configurato`` / ``errore``."""
    if not menu_configurato():
        return {"esito": "non_configurato", "lotti_ref": lotti_ref_ricetta(str(ricetta.get("id")))}
    try:
        if db is None:
            from app.lotti.db import database as db
        foto = await _foto_ricetta(ricetta, db)
        return await asyncio.to_thread(_pubblica_sync, ricetta, foto, visibile)
    except Exception as e:  # pragma: no cover - dipende dal servizio esterno
        logger.exception("Lotti->Menu: pubblicazione ricetta %s fallita", ricetta.get("id"))
        return {"esito": "errore", "errore": str(e), "lotti_ref": lotti_ref_ricetta(str(ricetta.get("id")))}


async def rimuovi_prodotto_dal_menu(lotti_ref: str) -> dict:
    """Toglie dal Menu la riga con quel ``lotti_ref``. Non solleva mai."""
    if not menu_configurato():
        return {"esito": "non_configurato", "lotti_ref": lotti_ref}
    try:
        return await asyncio.to_thread(_rimuovi_sync, lotti_ref)
    except Exception as e:  # pragma: no cover - dipende dal servizio esterno
        logger.exception("Lotti->Menu: rimozione %s fallita", lotti_ref)
        return {"esito": "errore", "errore": str(e), "lotti_ref": lotti_ref}


# ================== Categorie del Menu lette e create da Lotti ==================
# "la categoria dove inserirla, che recuperi da Menu o si creano in Lotti"
# (titolare, 19/09/2026). Stesso client del ponte: nessuna seconda connessione
# al progetto Menu.

class MenuNonConfigurato(RuntimeError):
    """Manca ``MENU_SUPABASE_URL``: il Menu non e' raggiungibile da qui."""


class CategoriaMenuNonValida(ValueError):
    """Categoria, sottocategoria o prodotto del Menu inesistente o non valido."""


def _esigi_configurato() -> None:
    if not menu_configurato():
        raise MenuNonConfigurato("Menu non configurato (MENU_SUPABASE_URL assente)")


def _voce_categoria(riga: dict, sottocategorie: list) -> dict:
    return {
        "id": int(riga["id"]),
        "name": riga.get("name"),
        "name_it": riga.get("name_it"),
        "origine": riga.get("origine"),
        "sottocategorie": sottocategorie,
    }


def _elenco_categorie_sync() -> dict:
    categorie = supabase.table(TABELLA_CATEGORIE).select(
        "id,name,name_it,origine").order("id").execute().data or []
    sottocategorie = supabase.table(TABELLA_SOTTOCATEGORIE).select(
        "id,category_id,name,name_it,origine").order("id").execute().data or []

    per_categoria: dict[int, list] = {}
    for s in sottocategorie:
        per_categoria.setdefault(int(s.get("category_id") or 0), []).append({
            "id": int(s["id"]),
            "category_id": int(s.get("category_id") or 0),
            "name": s.get("name"),
            "name_it": s.get("name_it"),
            "origine": s.get("origine"),
        })

    voci = [_voce_categoria(c, per_categoria.get(int(c["id"]), [])) for c in categorie]
    return {"categorie": voci, "totale": len(voci)}


def _avviso_omonimia(nome_it: str) -> Optional[str]:
    """Avviso quando nel Menu esiste gia' una categoria con quel nome ma di
    un'altra origine (creata a mano nell'admin o gia' presente).

    L'idempotenza sul nome copre solo le categorie create da Lotti: creare una
    "Bar" quando ce n'e' gia' una riesce, e il cliente si trova due riquadri
    identici nella home. Non si blocca — il titolare potrebbe volerne davvero
    una sua — ma la risposta lo dice."""
    righe = (
        supabase.table(TABELLA_CATEGORIE).select("id,name,name_it,origine")
        .eq("name_it", nome_it).execute().data or []
    )
    omonime = [r for r in righe if (r.get("origine") or None) != ORIGINE_LOTTI]
    if not omonime:
        return None
    provenienze = sorted({str(r.get("origine") or "menu") for r in omonime})
    identificativi = ", ".join(str(r["id"]) for r in omonime)
    return (
        f"Nel Menu esiste gia' una categoria «{nome_it}» ({'/'.join(provenienze)}, "
        f"id {identificativi}): i clienti vedranno due riquadri con lo stesso "
        "nome. Se non e' voluto, usa un nome diverso."
    )


def _crea_categoria_sync(nome_it: str, nome: str, immagine: Optional[str]) -> dict:
    # Idempotente sul nome italiano fra le categorie di Lotti: due clic sullo
    # stesso bottone non creano due "Colazioni".
    avviso = _avviso_omonimia(nome_it)
    esistente = (
        supabase.table(TABELLA_CATEGORIE).select("id,name,name_it,origine")
        .eq("origine", ORIGINE_LOTTI).eq("name_it", nome_it).limit(1).execute()
    )
    if esistente.data:
        return {"creata": False, "categoria": _voce_categoria(esistente.data[0], []),
                "avviso": avviso}
    riga = {"name": nome, "name_it": nome_it,
            "image": immagine or None, "origine": ORIGINE_LOTTI}
    nuovo_id = _inserisci(TABELLA_CATEGORIE, riga)
    return {"creata": True, "categoria": _voce_categoria({**riga, "id": nuovo_id}, []),
            "avviso": avviso}


def _crea_sottocategoria_sync(categoria_id: int, nome_it: str, nome: str,
                              immagine: Optional[str]) -> dict:
    if not _categoria_menu(categoria_id):
        raise CategoriaMenuNonValida("Categoria inesistente nel Menu")
    esistente = (
        supabase.table(TABELLA_SOTTOCATEGORIE).select("id,category_id,name,name_it,origine")
        .eq("origine", ORIGINE_LOTTI).eq("category_id", categoria_id)
        .eq("name_it", nome_it).limit(1).execute()
    )
    if esistente.data:
        return {"creata": False, "sottocategoria": esistente.data[0]}
    riga = {"category_id": categoria_id, "name": nome,
            "name_it": nome_it, "image": immagine or None, "origine": ORIGINE_LOTTI}
    nuovo_id = _inserisci(TABELLA_SOTTOCATEGORIE, riga)
    return {"creata": True, "sottocategoria": {**riga, "id": nuovo_id}}


async def elenco_categorie_menu() -> dict:
    """Categorie e sottocategorie del Menu.

    A differenza del resto del ponte queste funzioni SOLLEVANO: servono un
    endpoint interattivo, dove un errore deve arrivare al titolare invece di
    restare un esito silenzioso."""
    _esigi_configurato()
    return await asyncio.to_thread(_elenco_categorie_sync)


async def crea_categoria_menu(nome_it: str, nome: Optional[str] = None,
                              immagine: Optional[str] = None) -> dict:
    _esigi_configurato()
    nome_it = str(nome_it or "").strip()
    if not nome_it:
        raise CategoriaMenuNonValida("Nome categoria mancante")
    return await asyncio.to_thread(
        _crea_categoria_sync, nome_it, (nome or nome_it).strip(), immagine)


async def crea_sottocategoria_menu(categoria_id: int, nome_it: str,
                                   nome: Optional[str] = None,
                                   immagine: Optional[str] = None) -> dict:
    _esigi_configurato()
    nome_it = str(nome_it or "").strip()
    if not nome_it:
        raise CategoriaMenuNonValida("Nome sottocategoria mancante")
    return await asyncio.to_thread(
        _crea_sottocategoria_sync, int(categoria_id), nome_it,
        (nome or nome_it).strip(), immagine)


def _prodotti_agganciabili_sync(ricetta_id: str, testo: str, limite: int) -> list:
    """Prodotti gia' nel Menu non ancora di nessuna ricetta (``lotti_ref`` assente),
    piu' quello gia' unito a questa ricetta, con categoria e sottocategoria."""
    righe = (
        supabase.table(TABELLA_PRODOTTI)
        .select("id,name_it,name,price,category_id,subcategory_id,lotti_ref,codice_prodotto,visible")
        .order("name_it").limit(5000).execute().data or []
    )
    mio = lotti_ref_ricetta(ricetta_id)
    cerca = str(testo or "").strip().casefold()
    liberi = [r for r in righe if not r.get("lotti_ref") or r.get("lotti_ref") == mio]
    if cerca:
        liberi = [r for r in liberi if cerca in str(r.get("name_it") or r.get("name") or "").casefold()]
    categorie = {int(c["id"]): c.get("name_it") or c.get("name")
                 for c in supabase.table(TABELLA_CATEGORIE).select("id,name,name_it").execute().data or []}
    sotto = {int(c["id"]): c.get("name_it") or c.get("name")
             for c in supabase.table(TABELLA_SOTTOCATEGORIE).select("id,name,name_it").execute().data or []}
    return [{
        "id": int(r["id"]),
        "nome": r.get("name_it") or r.get("name"),
        "prezzo": r.get("price") or "",
        "codice": r.get("codice_prodotto"),
        "categoria": categorie.get(int(r.get("category_id") or 0)),
        "sottocategoria": sotto.get(int(r.get("subcategory_id") or 0)),
        "visibile": r.get("visible") is not False,
        "gia_unito": r.get("lotti_ref") == mio,
    } for r in liberi[:limite]]


async def prodotti_agganciabili(ricetta_id: str, testo: str = "", limite: int = 60) -> list:
    _esigi_configurato()
    return await asyncio.to_thread(_prodotti_agganciabili_sync, ricetta_id, testo, limite)


def _valida_destinazione_sync(categoria_id: Optional[int], sottocategoria_id: Optional[int],
                              prodotto_id: Optional[int], ricetta_id: str) -> None:
    if (categoria_id is None) != (sottocategoria_id is None):
        raise CategoriaMenuNonValida("Categoria e sottocategoria vanno scelte insieme")
    if categoria_id is not None:
        sotto = _sottocategoria_menu(sottocategoria_id)
        if not _categoria_menu(categoria_id):
            raise CategoriaMenuNonValida("Categoria inesistente nel Menu")
        if not sotto or int(sotto.get("category_id") or 0) != categoria_id:
            raise CategoriaMenuNonValida("La sottocategoria non appartiene alla categoria scelta")
    if prodotto_id is not None:
        res = supabase.table(TABELLA_PRODOTTI).select("id,lotti_ref").eq("id", prodotto_id).limit(1).execute()
        riga = res.data[0] if res.data else None
        if not riga:
            raise CategoriaMenuNonValida("Prodotto inesistente nel Menu")
        if riga.get("lotti_ref") not in (None, "", lotti_ref_ricetta(ricetta_id)):
            raise CategoriaMenuNonValida("Il prodotto e' gia' unito a un'altra ricetta")


async def valida_destinazione(ricetta_id: str, categoria_id: Optional[int],
                              sottocategoria_id: Optional[int], prodotto_id: Optional[int]) -> None:
    """Solleva ``CategoriaMenuNonValida`` se la scelta del titolare non regge."""
    _esigi_configurato()
    await asyncio.to_thread(_valida_destinazione_sync, categoria_id, sottocategoria_id, prodotto_id, ricetta_id)
