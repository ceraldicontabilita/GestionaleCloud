"""Ponte Lotti -> Menu digitale (richiesta del titolare, 03/09/2026):
"quando aggiungo un prodotto in Lotti fai in modo che lo aggiungi anche in
Menu con le stesse immagini e scelgo io se far comparire nel menu pubblico".

La fonte e' la ricetta di Lotti (collezione ``ricette``): ogni ricetta viene
SEMPRE replicata in ``menu_products`` (tabelle del Menu, progetto Supabase
``Lotti-HACCP``, client PostgREST sincrono di ``app.menu.supabase_client``)
con ``origine = "lotti"`` e chiave idempotente ``lotti_ref = "ricetta:<id>"``.
La colonna ``visible`` replica il flag ``menu_pubblico`` della ricetta: il
titolare la vede nell'area admin del Menu e decide se mostrarla ai clienti.

Immagini: i byte della foto (collezione ``foto_files`` di Lotti) vengono
copiati nel bucket Storage ``menu-images`` al percorso ``lotti/<foto_id>.<ext>``
e il prodotto Menu usa l'URL pubblico. L'id foto e' immutabile per contenuto
(un nuovo upload in Lotti crea un nuovo id), quindi se la riga Menu punta gia'
allo stesso ``foto_id`` non si ricarica nulla.

Prezzo (decisione del titolare 19/09/2026): la ricetta ha due prezzi, al banco
(``prezzo_vendita``, quello del food cost) e al tavolo (``prezzo_tavolo``). Il
Menu digitale mostra il prezzo AL TAVOLO. Finche' il prezzo al tavolo non e'
stato deciso si continua a esporre quello al banco (vedi ``prezzo_per_menu``).
Una ricetta **senza nessuno dei due prezzi** viene pubblicata ma resta
nascosta (``visible = false``): senza prezzo il carrello del Menu la
conterebbe 0 euro. Il caso e' segnalato nell'esito (``prezzo_mancante``,
``motivo_nascosto``) e contato dal backfill.

Categoria: se la ricetta ha ``menu_category_id`` (scelto dal titolare fra le
categorie del Menu create da Lotti, vedi ``app/lotti/routers/menu_categorie.py``)
il prodotto va li'; senza scelta resta il comportamento storico, categoria unica
"Produzione Ceraldi" con una sottocategoria per reparto.

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

from app.menu.supabase_client import supabase

logger = logging.getLogger("uvicorn.error")

ORIGINE_LOTTI = "lotti"
STORAGE_BUCKET = "menu-images"
STORAGE_PREFIX = "lotti"
TABELLA_CATEGORIE = "menu_categories"
TABELLA_SOTTOCATEGORIE = "menu_subcategories"
TABELLA_PRODOTTI = "menu_products"

CATEGORIA_NOME = "Ceraldi Production"
CATEGORIA_NOME_IT = "Produzione Ceraldi"

# Gli id di menu_* sono assegnati dall'app (max(id)+1, come in
# menu_routes.py). Le righe importate da Qromo usano gli id di Qromo: per non
# collidere con un futuro prodotto Qromo, le righe create da Lotti partono da
# una base alta.
ID_MINIMO_LOTTI = 1_000_000

# Quante volte rileggere max(id) e riprovare l'insert quando un altro thread
# ha preso lo stesso id nel frattempo (vedi ``_inserisci_con_id``).
TENTATIVI_ID = 5

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
    return testo or None


# ================== Accesso al Menu (client sincrono, eseguito in thread) ==================

def _prossimo_id(tabella: str) -> int:
    ultimo = supabase.table(tabella).select("id").order("id", desc=True).limit(1).execute()
    massimo = int(ultimo.data[0]["id"]) if ultimo.data else 0
    return max(massimo + 1, ID_MINIMO_LOTTI)


def _e_collisione_di_id(errore: Exception) -> bool:
    """Vero solo per la violazione della PRIMARY KEY (``<tabella>_pkey``).

    L'altro unico indice unico di ``menu_products`` e' quello su ``lotti_ref``:
    se a collidere e' quello il problema non e' l'id, ritentare non serve e
    l'errore deve uscire subito."""
    testo = str(errore).lower()
    if "23505" not in testo and "duplicate key" not in testo:
        return False
    return "_pkey" in testo or "primary key" in testo


def _inserisci_con_id(tabella: str, riga: dict) -> int:
    """Inserisce assegnando ``max(id)+1`` e **ritenta sulla collisione**.

    Gli id di ``menu_*`` sono assegnati dall'app, non da una sequenza: fra la
    ``select max(id)`` e la ``insert`` un altro thread puo' infilarsi
    (``_pubblica_sync`` gira in ``asyncio.to_thread`` e il backfill cicla per
    minuti mentre il form continua a salvare). Senza ritentativo la seconda
    insert violava la primary key, il ponte restituiva ``errore`` e la ricetta
    appena salvata non arrivava nel Menu.

    Il ciclo e' limitato a ``TENTATIVI_ID`` giri e ogni giro rilegge il massimo:
    esaurititi i tentativi l'eccezione risale, quindi un fallimento definitivo
    resta visibile nell'esito del ponte e nei conteggi del backfill."""
    ultimo_errore: Optional[Exception] = None
    for tentativo in range(TENTATIVI_ID):
        nuovo_id = _prossimo_id(tabella)
        try:
            supabase.table(tabella).insert({**riga, "id": nuovo_id}).execute()
            return nuovo_id
        except Exception as errore:  # noqa: BLE001 - rilanciata se non e' l'id
            if not _e_collisione_di_id(errore):
                raise
            ultimo_errore = errore
            logger.warning(
                "Lotti->Menu: id %s gia' preso su %s, ritento (%s/%s)",
                nuovo_id, tabella, tentativo + 1, TENTATIVI_ID,
            )
    raise RuntimeError(
        f"Impossibile assegnare un id libero su {tabella} dopo {TENTATIVI_ID} "
        f"tentativi: {ultimo_errore}"
    )


def _categoria_lotti_id() -> int:
    res = (
        supabase.table(TABELLA_CATEGORIE).select("id")
        .eq("origine", ORIGINE_LOTTI).eq("name_it", CATEGORIA_NOME_IT)
        .limit(1).execute()
    )
    if res.data:
        return int(res.data[0]["id"])
    return _inserisci_con_id(TABELLA_CATEGORIE, {
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
    return _inserisci_con_id(TABELLA_SOTTOCATEGORIE, {
        "category_id": categoria_id, "name": nome, "name_it": nome_it,
        "image": None, "origine": ORIGINE_LOTTI,
    })


def _categoria_di_lotti(categoria_id: int) -> Optional[dict]:
    """La categoria Menu con quell'id, solo se e' una categoria che Lotti
    possiede (``origine`` valorizzata).

    Una categoria di Qromo (``origine IS NULL``) non e' agganciabile: la sync
    Qromo la cancella e la reinserisce a ogni giro
    (``app/menu/qromo_sync.py::_sostituisci_tabelle``), e una sottocategoria o
    un prodotto di Lotti che la referenzia farebbe fallire quella
    cancellazione per vincolo di chiave esterna."""
    res = (
        supabase.table(TABELLA_CATEGORIE).select("id,name,name_it,origine")
        .eq("id", categoria_id).limit(1).execute()
    )
    riga = res.data[0] if res.data else None
    return riga if riga and riga.get("origine") else None


def _sottocategoria_di_lotti(sottocategoria_id: int, categoria_id: int) -> Optional[dict]:
    res = (
        supabase.table(TABELLA_SOTTOCATEGORIE).select("id,category_id,name,name_it,origine")
        .eq("id", sottocategoria_id).limit(1).execute()
    )
    riga = res.data[0] if res.data else None
    if not riga or not riga.get("origine"):
        return None
    return riga if int(riga.get("category_id") or 0) == int(categoria_id) else None


def _destinazione_menu(ricetta: dict) -> tuple[int, int, str]:
    """(category_id, subcategory_id, origine_della_scelta).

    Con ``menu_category_id`` valorizzato e valido si usa quello; senza scelta
    (o con una scelta non piu' valida, es. categoria cancellata) si ricade
    esattamente sul comportamento storico: categoria unica "Produzione
    Ceraldi" e sottocategoria per reparto. Cosi' nessuna ricetta gia' in
    archivio si sposta da sola."""
    scelta = _intero(ricetta.get("menu_category_id"))
    origine_scelta = "predefinita"
    if scelta is not None:
        if _categoria_di_lotti(scelta):
            sotto_scelta = _intero(ricetta.get("menu_subcategory_id"))
            if sotto_scelta is not None and _sottocategoria_di_lotti(sotto_scelta, scelta):
                return scelta, sotto_scelta, "scelta"
            # Categoria scelta ma sottocategoria assente o non sua: dentro la
            # categoria scelta si ricrea la sezione del reparto.
            return scelta, _sottocategoria_lotti_id(scelta, ricetta.get("reparto")), "scelta_senza_sottocategoria"
        origine_scelta = "scelta_non_valida"
    categoria_id = _categoria_lotti_id()
    return categoria_id, _sottocategoria_lotti_id(categoria_id, ricetta.get("reparto")), origine_scelta


def _riga_esistente(lotti_ref: str) -> Optional[dict]:
    res = supabase.table(TABELLA_PRODOTTI).select("*").eq("lotti_ref", lotti_ref).limit(1).execute()
    return res.data[0] if res.data else None


def _carica_immagine(foto: dict) -> str:
    """Copia i byte della foto Lotti nel bucket del Menu e restituisce l'URL pubblico."""
    mime = str(foto.get("mime") or "image/jpeg")
    percorso = percorso_storage(str(foto["_id"]), mime)
    supabase.storage.from_(STORAGE_BUCKET).upload(
        percorso, bytes(foto["data"]), {"content-type": mime, "upsert": "true"}
    )
    return supabase.storage.from_(STORAGE_BUCKET).get_public_url(percorso)


def _immagine_per_prodotto(ricetta: dict, foto: Optional[dict], esistente: Optional[dict]) -> Optional[str]:
    """URL da scrivere in ``image``: la foto Lotti copiata su Storage (senza
    ricaricarla se la riga punta gia' allo stesso foto_id), altrimenti un
    eventuale URL assoluto gia' pubblico, altrimenti quello gia' presente."""
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
    esistente = _riga_esistente(lotti_ref)
    categoria_id, sottocategoria_id, categoria_origine = _destinazione_menu(ricetta)
    nome = str(ricetta.get("nome") or "").strip() or f"Ricetta {ricetta['id']}"
    descrizione = _descrizione(ricetta)
    immagine = _immagine_per_prodotto(ricetta, foto, esistente)
    prezzo, prezzo_origine = prezzo_per_menu(ricetta)

    # Senza NESSUN prezzo (ne' tavolo ne' banco) la riga non puo' diventare
    # visibile: `price` resterebbe "" e il carrello del Menu la conteggerebbe
    # 0 euro (`order_models.compute_total` scarta il valore non numerico e
    # continua), cioe' un prodotto ordinabile gratis. La riga si pubblica
    # comunque, ma nascosta: resta idempotente per `lotti_ref` e torna
    # visibile da sola appena il titolare mette un prezzo. Non si inventa un
    # prezzo di ripiego.
    prezzo_mancante = prezzo is None
    visibile_richiesta = bool(visibile)
    visibile_effettivo = visibile_richiesta and not prezzo_mancante

    riga = {
        "category_id": categoria_id,
        "subcategory_id": sottocategoria_id,
        "name": nome,
        "name_it": nome,
        "price": prezzo or "",
        "description": descrizione,
        "description_it": descrizione,
        "allergens": mappa_allergeni(ricetta.get("allergeni") or ricetta.get("allergeni_auto")),
        "image": immagine,
        "origine": ORIGINE_LOTTI,
        "lotti_ref": lotti_ref,
        "visible": visibile_effettivo,
    }

    if esistente:
        prodotto_id = int(esistente["id"])
        supabase.table(TABELLA_PRODOTTI).update(riga).eq("id", prodotto_id).execute()
        esito = "aggiornato"
    else:
        prodotto_id = _inserisci_con_id(TABELLA_PRODOTTI, riga)
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
        "motivo_nascosto": (
            "prezzo_assente" if prezzo_mancante and visibile_richiesta else None
        ),
    }


def _rimuovi_sync(lotti_ref: str) -> dict:
    res = supabase.table(TABELLA_PRODOTTI).delete().eq("lotti_ref", lotti_ref).execute()
    rimossi = len(res.data or []) if getattr(res, "data", None) is not None else 0
    return {"esito": "rimosso", "lotti_ref": lotti_ref, "rimossi": rimossi}


# ================== API asincrona usata dal router ricette ==================

async def _foto_ricetta(ricetta: dict, db: Any) -> Optional[dict]:
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
    """Categoria inesistente, oppure di Qromo e quindi non agganciabile."""


MOTIVO_QROMO = (
    "Categoria importata da Qromo: la sincronizzazione Qromo la cancella e la "
    "reinserisce a ogni giro, quindi Lotti non puo' appenderci i suoi prodotti. "
    "Crea qui una categoria di Lotti."
)


def _esigi_configurato() -> None:
    if not menu_configurato():
        raise MenuNonConfigurato("Menu non configurato (MENU_SUPABASE_URL assente)")


def _voce_categoria(riga: dict, sottocategorie: list) -> dict:
    selezionabile = bool(riga.get("origine"))
    return {
        "id": int(riga["id"]),
        "name": riga.get("name"),
        "name_it": riga.get("name_it"),
        "origine": riga.get("origine"),
        "selezionabile": selezionabile,
        "motivo": None if selezionabile else MOTIVO_QROMO,
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
            "selezionabile": bool(s.get("origine")),
        })

    voci = [_voce_categoria(c, per_categoria.get(int(c["id"]), [])) for c in categorie]
    return {"categorie": voci, "totale": len(voci),
            "selezionabili": sum(1 for v in voci if v["selezionabile"])}


def _avviso_omonimia(nome_it: str) -> Optional[str]:
    """Avviso quando nel Menu esiste gia' una categoria con quel nome ma di
    un'altra origine (tipicamente Qromo).

    L'idempotenza sul nome copre solo le categorie di Lotti: creare una "Bar"
    di Lotti quando Qromo ha gia' una "Bar" riesce, e il cliente si trova due
    riquadri identici nella home. Non si blocca — il titolare potrebbe volerne
    davvero una sua, separata da quella di Qromo — ma la risposta lo dice."""
    righe = (
        supabase.table(TABELLA_CATEGORIE).select("id,name,name_it,origine")
        .eq("name_it", nome_it).execute().data or []
    )
    omonime = [r for r in righe if (r.get("origine") or None) != ORIGINE_LOTTI]
    if not omonime:
        return None
    provenienze = sorted({str(r.get("origine") or "Qromo") for r in omonime})
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
    nuovo_id = _inserisci_con_id(TABELLA_CATEGORIE, riga)
    return {"creata": True, "categoria": _voce_categoria({**riga, "id": nuovo_id}, []),
            "avviso": avviso}


def _crea_sottocategoria_sync(categoria_id: int, nome_it: str, nome: str,
                              immagine: Optional[str]) -> dict:
    if not _categoria_di_lotti(categoria_id):
        raise CategoriaMenuNonValida(MOTIVO_QROMO)
    esistente = (
        supabase.table(TABELLA_SOTTOCATEGORIE).select("id,category_id,name,name_it,origine")
        .eq("origine", ORIGINE_LOTTI).eq("category_id", categoria_id)
        .eq("name_it", nome_it).limit(1).execute()
    )
    if esistente.data:
        return {"creata": False, "sottocategoria": esistente.data[0]}
    riga = {"category_id": categoria_id, "name": nome,
            "name_it": nome_it, "image": immagine or None, "origine": ORIGINE_LOTTI}
    nuovo_id = _inserisci_con_id(TABELLA_SOTTOCATEGORIE, riga)
    return {"creata": True, "sottocategoria": {**riga, "id": nuovo_id}}


async def elenco_categorie_menu() -> dict:
    """Categorie e sottocategorie del Menu, con il flag ``selezionabile``.

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
