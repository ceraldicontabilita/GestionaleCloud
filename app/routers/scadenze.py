"""
Scadenze e Notifiche Router - Sistema alert per scadenze fiscali e pagamenti

Gestisce:
- Scadenze IVA mensili e confronto con F24 ricevuti
- Scadenze F24 (16 di ogni mese)
- Fatture in scadenza (pagamento entro X giorni)
- Notifiche personalizzate
"""

from fastapi import APIRouter, Query, HTTPException, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta, timezone
from app.database import Database, Collections
import logging
import uuid
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

# Collezione canonica F24 (upload manuale ed email confluiscono qui, vedi
# memoria/AUDIT_RICOGNIZIONE §3 e PROMPT_DEFINITIVO P0.1).
COLL_F24_CANONICA = "f24_unificato"


async def _iva_acquisti_ufficiale(db, periodo: str) -> Dict[str, Any]:
    """IVA acquisti detraibile del periodo 'YYYY-MM' secondo il motore
    ufficiale di liquidazione (memoria/SPECIFICA_IVA.md §10-11), la stessa
    logica usata da POST /api/iva/liquidazioni/calcola — non una terza
    formula parallela.

    Bug corretto 15/07/2026: prima questa pagina sommava semplicemente
    `iva` di TUTTE le fatture ricevute/emesse nel mese, senza escludere
    quelle già utilizzate in una liquidazione precedente (doppio conteggio
    quando una fattura di fine mese viene attribuita al mese prima per la
    regola del giorno 15), le note di credito, o i documenti annullati —
    poteva mostrare un "IVA da versare" diverso da quello confermato nella
    pagina Gestione IVA.

    Se per il periodo esiste già una liquidazione CONFERMATA/TRASMESSA,
    ritorna il suo valore definitivo (fonte="liquidazione_confermata");
    altrimenti calcola una STIMA live con le stesse regole di selezione,
    mai persistita (fonte="stima" — il numero definitivo nasce solo
    confermando la liquidazione dalla pagina Gestione IVA).
    """
    from app.routers.iva import _fatture_del_periodo, COLL_LIQ
    from app.engines import liquidazione_iva_engine as liq

    confermata = await db[COLL_LIQ].find_one(
        {"periodo": periodo, "stato": {"$in": [liq.CONFERMATA, liq.TRASMESSA]}},
        sort=[("versione", -1)],
    )
    if confermata:
        return {
            "iva_acquisti": round(float(confermata.get("iva_acquisti") or 0), 2),
            "fonte": "liquidazione_confermata",
        }

    fatture = await _fatture_del_periodo(db, periodo)
    incluse, _escluse = liq.seleziona_fatture_per_liquidazione(fatture, periodo)
    iva_acquisti = round(sum(
        round(float(f.get("iva_detraibile") or 0), 2)
        for f in incluse
    ), 2)
    return {"iva_acquisti": iva_acquisti, "fonte": "stima"}


async def conta_f24_da_pagare(db, limite_30: str) -> int:
    """Conta i F24 non pagati con scadenza entro `limite_30`, leggendo SOLO la
    collezione canonica `f24_unificato` e contando i documenti DISTINTI una volta
    sola. Copre sia lo schema canonico (`scadenza`+`status`) sia quello legacy
    (`data_scadenza`+`pagato`), senza sommare due count sulla stessa collezione
    (che raddoppiava i documenti con entrambi gli schemi). Vedi P0.1."""
    return await db[COLL_F24_CANONICA].count_documents({
        "status": {"$nin": ["pagato", "eliminato"]},
        "pagato": {"$ne": True},
        "$or": [
            {"scadenza": {"$gt": "", "$lte": limite_30}},
            {"data_scadenza": {"$gt": "", "$lte": limite_30}},
        ],
    })

# Scadenze fiscali fisse italiane
SCADENZE_FISCALI = {
    "iva_q1": {"mese": 5, "giorno": 16, "descrizione": "Versamento IVA 1° Trimestre", "tipo": "IVA"},
    "iva_q2": {"mese": 8, "giorno": 20, "descrizione": "Versamento IVA 2° Trimestre", "tipo": "IVA"},  # 20 agosto
    "iva_q3": {"mese": 11, "giorno": 16, "descrizione": "Versamento IVA 3° Trimestre", "tipo": "IVA"},
    "iva_q4": {"mese": 3, "giorno": 16, "descrizione": "Versamento IVA 4° Trimestre (anno prec.)", "tipo": "IVA"},
    "f24_mensile": {"giorno": 16, "descrizione": "Versamento F24 mensile", "tipo": "F24"},
    "inps": {"giorno": 16, "descrizione": "Versamento contributi INPS", "tipo": "INPS"},
    "irpef": {"giorno": 16, "descrizione": "Versamento ritenute IRPEF", "tipo": "IRPEF"},
}


@router.get("", include_in_schema=False)
@handle_errors
async def get_scadenze_noslash(
    anno: int = Query(None),
    mese: int = Query(None),
    tipo: str = Query(None, description="Filtra per tipo: IVA, F24, FATTURA, INPS"),
    include_passate: bool = Query(False),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """Alias /api/scadenze (senza slash)"""
    return await get_tutte_scadenze(anno=anno, mese=mese, tipo=tipo, include_passate=include_passate, limit=limit, offset=offset)


@router.get("/", include_in_schema=False)
@handle_errors
async def get_scadenze_slash(
    anno: int = Query(None),
    mese: int = Query(None),
    tipo: str = Query(None, description="Filtra per tipo: IVA, F24, FATTURA, INPS"),
    include_passate: bool = Query(False),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """Alias /api/scadenze/ (con slash)"""
    return await get_tutte_scadenze(anno=anno, mese=mese, tipo=tipo, include_passate=include_passate, limit=limit, offset=offset)


@router.get("/tutte")
@handle_errors
async def get_tutte_scadenze(
    anno: int = Query(None),
    mese: int = Query(None),
    tipo: str = Query(None, description="Filtra per tipo: IVA, F24, FATTURA, INPS"),
    include_passate: bool = Query(False),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """
    Ottiene tutte le scadenze (fiscali + fatture da pagare + notifiche custom).
    """
    db = Database.get_db()
    oggi = date.today()
    
    if not anno:
        anno = oggi.year
    mese_richiesto = mese
    
    scadenze = []
    
    # 1. Scadenze fiscali fisse
    mesi_fiscali = [mese_richiesto] if mese_richiesto else range(1, 13)
    scadenze_fiscali = []
    for mese_fiscale in mesi_fiscali:
        scadenze_fiscali.extend(
            _genera_scadenze_fiscali(anno, mese_fiscale, include_passate)
        )
    if tipo:
        scadenze_fiscali = [s for s in scadenze_fiscali if s["tipo"] == tipo]
    scadenze.extend(scadenze_fiscali)
    
    # 2. Fatture da pagare (scadenza pagamento)
    if not tipo or tipo == "FATTURA":
        fatture_scadenza = await _get_fatture_in_scadenza(db, anno, include_passate)
        scadenze.extend(fatture_scadenza)
    
    # 3. Notifiche custom salvate
    prefisso_periodo = (
        f"^{anno:04d}-{mese_richiesto:02d}-"
        if mese_richiesto
        else f"^{anno:04d}-"
    )
    query_custom = {"data_scadenza": {"$regex": prefisso_periodo}}
    if not include_passate:
        query_custom["completata"] = False
    notifiche_custom = await db["notifiche_scadenze"].find(
        query_custom,
        {"_id": 0}
    ).to_list(None)
    
    for n in notifiche_custom:
        data_scadenza = str(n.get("data_scadenza") or "")
        if not data_scadenza.startswith(f"{anno:04d}-"):
            continue
        if mese_richiesto and not data_scadenza.startswith(
            f"{anno:04d}-{mese_richiesto:02d}-"
        ):
            continue
        if tipo and n.get("tipo", "CUSTOM") != tipo:
            continue
        scadenze.append({
            "id": n.get("id"),
            "data": data_scadenza,
            "tipo": n.get("tipo", "CUSTOM"),
            "descrizione": n.get("descrizione"),
            "importo": n.get("importo"),
            "priorita": n.get("priorita", "media"),
            "completata": n.get("completata", False),
            "source": "custom"
        })
    
    # Ordina per data
    scadenze.sort(key=lambda x: x.get("data", "9999-99-99"))
    
    # Filtra passate se richiesto
    if not include_passate:
        scadenze = [s for s in scadenze if s.get("data", "9999-99-99") >= oggi.isoformat()]
    
    # Giorni mancanti/urgenza (la pagina Scadenze legge s.giorni_mancanti:
    # senza, la colonna "Giorni" restava vuota e nessuna riga era marcata scaduta)
    for s in scadenze:
        s["giorni_mancanti"] = _giorni_mancanti(s.get("data"))
        s["urgente"] = s["giorni_mancanti"] <= 3 if s["giorni_mancanti"] is not None else False

    # Calcola statistiche
    urgenti = [s for s in scadenze if _is_urgente(s.get("data"))]
    prossime_7gg = [s for s in scadenze if _is_prossimi_giorni(s.get("data"), 7)]

    return {
        "scadenze": scadenze[offset:offset + limit],
        "totale": len(scadenze),
        "pagination": {"offset": offset, "limit": limit},
        "statistiche": {
            "urgenti": len(urgenti),
            "prossimi_7_giorni": len(prossime_7gg),
            "totale_importo": sum(s.get("importo", 0) or 0 for s in scadenze if s.get("importo"))
        }
    }


@router.get("/prossime")
@handle_errors
async def get_prossime_scadenze(
    giorni: int = Query(30, description="Giorni futuri da considerare"),
    limit: int = Query(10)
) -> Dict[str, Any]:
    """
    Ottiene le prossime scadenze entro N giorni.
    Endpoint ottimizzato per widget dashboard.
    """
    db = Database.get_db()
    oggi = date.today()
    data_limite = (oggi + timedelta(days=giorni)).isoformat()
    
    scadenze = []
    
    # Scadenze fiscali
    for i in range(giorni // 30 + 2):  # Prossimi mesi
        mese = (oggi.month + i - 1) % 12 + 1
        anno = oggi.year + (oggi.month + i - 1) // 12
        scadenze_mese = _genera_scadenze_fiscali(anno, mese, False)
        scadenze.extend(scadenze_mese)
    
    # Fatture in scadenza
    fatture = await _get_fatture_in_scadenza(db, oggi.year, False, giorni)
    scadenze.extend(fatture)
    
    # Notifiche custom non completate
    notifiche = await db["notifiche_scadenze"].find(
        {
            "completata": False,
            "data_scadenza": {"$lte": data_limite}
        },
        {"_id": 0}
    ).to_list(50)
    
    for n in notifiche:
        scadenze.append({
            "id": n.get("id"),
            "data": n.get("data_scadenza"),
            "tipo": n.get("tipo", "CUSTOM"),
            "descrizione": n.get("descrizione"),
            "importo": n.get("importo"),
            "priorita": _calcola_priorita(n.get("data_scadenza")),
            "source": "custom"
        })
    
    # Filtra e ordina
    scadenze = [s for s in scadenze if oggi.isoformat() <= s.get("data", "9999") <= data_limite]
    scadenze.sort(key=lambda x: x.get("data", "9999"))
    
    # Aggiungi info urgenza
    for s in scadenze:
        s["giorni_mancanti"] = _giorni_mancanti(s.get("data"))
        s["urgente"] = s["giorni_mancanti"] <= 3 if s["giorni_mancanti"] is not None else False
    
    return {
        "scadenze": scadenze[:limit],
        "totale": len(scadenze),
        "prossima_scadenza": scadenze[0] if scadenze else None
    }


@router.get("/iva-mensile/{anno}")
@handle_errors
async def get_scadenze_iva_mensile(anno: int) -> Dict[str, Any]:
    """
    Ottiene le scadenze IVA mensili per un anno.
    Per regime IVA mensile: versamento entro il 16 del mese successivo.
    """
    db = Database.get_db()
    from app.services.iva_liquidation_query import euros, get_iva_period_snapshot

    scadenze_mensili = []
    
    for mese in range(1, 13):
        snapshot = await get_iva_period_snapshot(db, anno=anno, mese=mese)
        
        # IVA Credito (fatture) — motore ufficiale di liquidazione, vedi
        # _iva_acquisti_ufficiale.
        mesi_nomi = ['', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
                    'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']
        
        scadenze_mensili.append({
            "mese": mese,
            "mese_nome": mesi_nomi[mese],
            "periodo": f"{mesi_nomi[mese]} {anno}",
            "data_scadenza": snapshot["scadenza_legale"],
            "scadenza_nominale": snapshot["scadenza_nominale"],
            "scadenza_legale": snapshot["scadenza_legale"],
            "iva_debito": snapshot.get("iva_vendite"),
            "iva_debito_cents": snapshot.get("iva_vendite_cents"),
            "iva_credito": snapshot.get("iva_acquisti"),
            "iva_credito_cents": snapshot.get("iva_acquisti_cents"),
            "saldo": snapshot.get("saldo"),
            "saldo_cents": snapshot.get("saldo_cents"),
            "da_versare": bool(
                snapshot.get("saldo_cents") is not None and snapshot["saldo_cents"] > 0
            ),
            "importo_versamento": snapshot.get("debito_periodo"),
            "importo_versamento_cents": snapshot.get("debito_periodo_cents"),
            "a_credito": snapshot.get("credito_periodo"),
            "a_credito_cents": snapshot.get("credito_periodo_cents"),
            "stato": snapshot["stato_calcolo"] if snapshot["stato_calcolo"] in ("NON_CALCOLATO", "DATI_MANCANTI") else (
                "da_versare" if (snapshot.get("saldo_cents") or 0) > 0 else "a_credito"
            ),
            "attendibile": snapshot.get("attendibile"),
            "motivi": snapshot.get("motivi") or [],
            "giorni_senza_corrispettivo": snapshot.get("giorni_senza_corrispettivo") or [],
            "giorni_con_corrispettivo": snapshot.get("giorni_con_corrispettivo"),
            "giorni_mese": snapshot.get("giorni_mese"),
            "giorni_mancanti": _giorni_mancanti(snapshot["scadenza_legale"]),
            "fonte": "stima" if snapshot["fonte"] == "calcolo_canonico" else snapshot["fonte"],
            "fonte_calcolo": snapshot["fonte_calcolo"],
            "conteggi": snapshot["conteggi"],
        })

    calcolate = [s for s in scadenze_mensili if s["saldo_cents"] is not None]
    totale_da_versare_cents = sum(s["importo_versamento_cents"] or 0 for s in calcolate)
    totale_a_credito_cents = sum(s["a_credito_cents"] or 0 for s in calcolate)
    
    # Calcola saldo progressivo con riporto credito dal mese precedente
    saldo_progressivo_cents = 0
    for s in scadenze_mensili:
        if s["saldo_cents"] is None:
            s["saldo_progressivo"] = None
            s["saldo_progressivo_cents"] = None
            s["da_versare_effettivo"] = False
            s["importo_versamento_effettivo"] = None
            s["importo_versamento_effettivo_cents"] = None
            continue
        saldo_progressivo_cents += s["saldo_cents"]
        s["saldo_progressivo_cents"] = saldo_progressivo_cents
        s["saldo_progressivo"] = euros(saldo_progressivo_cents)
        # Il versamento F24 è dovuto solo se il progressivo è positivo
        if saldo_progressivo_cents > 0:
            s["da_versare_effettivo"] = True
            s["importo_versamento_effettivo_cents"] = saldo_progressivo_cents
            s["importo_versamento_effettivo"] = euros(saldo_progressivo_cents)
        else:
            s["da_versare_effettivo"] = False
            s["importo_versamento_effettivo_cents"] = 0
            s["importo_versamento_effettivo"] = 0.0
    
    return {
        "anno": anno,
        "regime": "mensile",
        "scadenze": scadenze_mensili,
        "totale_da_versare": euros(totale_da_versare_cents),
        "totale_da_versare_cents": totale_da_versare_cents,
        "totale_a_credito": euros(totale_a_credito_cents),
        "totale_a_credito_cents": totale_a_credito_cents,
        "saldo_annuale": euros(totale_da_versare_cents - totale_a_credito_cents),
        "saldo_annuale_cents": totale_da_versare_cents - totale_a_credito_cents,
        "saldo_progressivo": euros(saldo_progressivo_cents),
        "saldo_progressivo_cents": saldo_progressivo_cents,
        "fonte_calcolo": "iva_liquidation_query_v1",
    }



@router.post("/crea")
@handle_errors
async def crea_notifica_scadenza(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Crea una notifica/scadenza personalizzata.
    """
    db = Database.get_db()
    
    required = ["data_scadenza", "descrizione"]
    for field in required:
        if not data.get(field):
            raise HTTPException(status_code=400, detail=f"Campo {field} obbligatorio")
    
    notifica = {
        "id": str(uuid.uuid4()),
        "data_scadenza": data["data_scadenza"],
        "descrizione": data["descrizione"],
        "tipo": data.get("tipo", "CUSTOM"),
        "importo": float(data.get("importo", 0) or 0),
        "priorita": data.get("priorita", "media"),
        "note": data.get("note", ""),
        "completata": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["notifiche_scadenze"].insert_one(notifica.copy())
    notifica.pop("_id", None)
    
    return {"success": True, "notifica": notifica}


@router.put("/completa/{notifica_id}")
@handle_errors
async def completa_notifica(notifica_id: str) -> Dict[str, Any]:
    """Segna una notifica come completata."""
    db = Database.get_db()
    
    result = await db["notifiche_scadenze"].update_one(
        {"id": notifica_id},
        {"$set": {"completata": True, "completata_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Notifica non trovata")
    
    return {"success": True, "message": "Notifica completata"}


@router.delete("/{notifica_id}")
@handle_errors
async def elimina_notifica(notifica_id: str) -> Dict[str, Any]:
    """Elimina una notifica personalizzata."""
    db = Database.get_db()
    
    result = await db["notifiche_scadenze"].delete_one({"id": notifica_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notifica non trovata")
    
    return {"success": True, "message": "Notifica eliminata"}


# Helper functions

def _genera_scadenze_fiscali(anno: int, mese: int, include_passate: bool) -> List[Dict]:
    """Genera scadenze fiscali per un mese specifico."""
    oggi = date.today()
    scadenze = []
    
    # F24/INPS/IRPEF mensile (16 del mese)
    data_16 = f"{anno}-{mese:02d}-16"
    if include_passate or data_16 >= oggi.isoformat():
        scadenze.append({
            "data": data_16,
            "tipo": "F24",
            "descrizione": f"Versamento F24 - {_nome_mese(mese)} {anno}",
            "priorita": _calcola_priorita(data_16),
            "source": "fiscale"
        })
    
    return scadenze


async def _get_fatture_in_scadenza(db, anno: int, include_passate: bool, giorni_limite: int = 60) -> List[Dict]:
    """Ottiene fatture con scadenza pagamento imminente."""
    oggi = date.today()
    data_limite = (oggi + timedelta(days=giorni_limite)).isoformat()
    
    query = {
        "pagato": {"$ne": True},
        "status": {"$ne": "paid"},
        "stato_pagamento": {"$nin": ["pagata", "pagato"]},
        "$or": [
            {"data_ricezione": {"$regex": f"^{anno}"}},
            {"invoice_date": {"$regex": f"^{anno}"}}
        ]
    }
    
    fatture = await db[Collections.INVOICES].find(query, {"_id": 0}).limit(100).to_list(100)
    
    scadenze = []
    for f in fatture:
        # Calcola data scadenza (default 30 giorni da data fattura)
        data_fatt = f.get("data_ricezione") or f.get("invoice_date") or ""
        if not data_fatt:
            continue
        
        try:
            dt = datetime.strptime(data_fatt[:10], "%Y-%m-%d")
            data_scadenza = (dt + timedelta(days=30)).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        
        if not include_passate and data_scadenza < oggi.isoformat():
            continue
        if data_scadenza > data_limite:
            continue
        
        # Estrai nome fornitore da tutti i campi possibili
        fornitore = (
            f.get("supplier_name") or 
            f.get("cedente_denominazione") or
            (f.get("cedente_prestatore", {}) or {}).get("denominazione", "") or
            (f.get("fornitore", {}) or {}).get("denominazione", "") or
            (f.get("fornitore", {}) or {}).get("ragione_sociale", "") or
            ""
        )
        importo_raw = f.get("total_amount") or f.get("importo_totale") or f.get("importo") or f.get("totale_documento") or 0
        try:
            importo = abs(float(importo_raw)) if importo_raw else 0
        except (ValueError, TypeError):
            importo = 0
        numero_fatt = f.get("invoice_number") or f.get("numero_documento") or f.get("numero_fattura", "")
        fattura_id = f.get("id")
        
        scadenze.append({
            "id": f.get("id"),
            "data": data_scadenza,
            "tipo": "FATTURA",
            "descrizione": f"Pagamento fattura {numero_fatt}",
            "importo": importo,
            "priorita": _calcola_priorita(data_scadenza),
            "fornitore": fornitore,
            "numero_fattura": numero_fatt,
            "fattura_id": fattura_id,  # Per il link "Vedi"
            "source": "fattura"
        })
    
    return scadenze


def _calcola_priorita(data_str: str) -> str:
    """Calcola priorità in base ai giorni mancanti."""
    giorni = _giorni_mancanti(data_str)
    if giorni is None:
        return "bassa"
    if giorni <= 3:
        return "critica"
    if giorni <= 7:
        return "alta"
    if giorni <= 14:
        return "media"
    return "bassa"


def _giorni_mancanti(data_str: str) -> Optional[int]:
    """Calcola giorni mancanti alla scadenza."""
    if not data_str:
        return None
    try:
        data = datetime.strptime(data_str[:10], "%Y-%m-%d").date()
        return (data - date.today()).days
    except (ValueError, TypeError):
        return None


def _is_urgente(data_str: str) -> bool:
    """Verifica se la scadenza è urgente (entro 3 giorni)."""
    giorni = _giorni_mancanti(data_str)
    return giorni is not None and giorni <= 3


def _is_prossimi_giorni(data_str: str, giorni: int) -> bool:
    """Verifica se la scadenza è entro N giorni."""
    g = _giorni_mancanti(data_str)
    return g is not None and 0 <= g <= giorni


def _nome_mese(mese: int) -> str:
    """Restituisce nome mese in italiano."""
    nomi = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
            "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    return nomi[mese] if 1 <= mese <= 12 else ""


@router.get("/dashboard-widget")
@handle_errors
async def get_dashboard_scadenze() -> Dict[str, Any]:
    """
    Widget scadenze per dashboard - riepilogo compatto.
    Ritorna le scadenze più urgenti di ogni tipo.
    """
    db = Database.get_db()
    oggi = datetime.now()
    oggi_str = oggi.strftime('%Y-%m-%d')
    limite_30 = (oggi + timedelta(days=30)).strftime('%Y-%m-%d')

    # Fatture da pagare
    fatture_urgenti = await db[Collections.INVOICES].count_documents({
        "data_scadenza": {"$lte": limite_30},
        "stato_pagamento": {"$in": ["non_pagata", "da_pagare", None]}
    })
    
    # F24 da pagare — collezione canonica unica f24_unificato, conteggio distinto
    # (copre schema canonico `scadenza`/`status` e legacy `data_scadenza`/`pagato`).
    # Vedi P0.1: prima due count sommate sulla stessa collezione raddoppiavano i
    # documenti con entrambi gli schemi e la query legacy pescava a vuoto.
    f24_da_pagare = await conta_f24_da_pagare(db, limite_30)
    
    # Scadenze fiscali prossime
    scadenze_fiscali = _genera_scadenze_fiscali(oggi.year, oggi.month, False)
    scadenze_urgenti = [s for s in scadenze_fiscali if _is_prossimi_giorni(s.get("data", s.get("data_scadenza", "")), 15)]
    
    totale_alert = (
        (1 if fatture_urgenti > 0 else 0) +
        (1 if f24_da_pagare > 0 else 0) +
        len(scadenze_urgenti)
    )

    return {
        "totale_alert": totale_alert,
        "fatture": {
            "da_pagare_30gg": fatture_urgenti,
            "urgenza": "alta" if fatture_urgenti > 5 else "media" if fatture_urgenti > 0 else "bassa"
        },
        "f24": {
            "da_pagare_30gg": f24_da_pagare,
            "urgenza": "alta" if f24_da_pagare > 0 else "bassa"
        },
        "fiscali": {
            "prossime": len(scadenze_urgenti),
            "dettaglio": scadenze_urgenti[:3]
        }
    }


