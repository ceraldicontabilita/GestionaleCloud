"""Cruscotto «Agenti» per settore: cosa ha letto e associato l'ultimo giro e cosa e' fermo.

Decisione del titolare (02/10/2026). Non e' un motore: legge gli esiti che i
giri scrivono gia' in ``sistema_stato`` e conta le code con le stesse query
delle pagine che le mostrano. Dove un conteggio non esiste (verbali senza
driver, cedolini senza netto, F24 non quadrati fra gli ERRORI) lo fa qui, con
proiezione senza payload. Un conteggio che non si puo' calcolare e' ``None``
(«Dato non disponibile»), mai zero.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.constants.metodi_pagamento import FILTRO_METODO_NON_CONFIGURATO
from app.constants.stati_netto import NETTO_VERIFICATO_DA_CEDOLINO
from app.constants.stati_verbale import STATI_APERTI, varianti
from app.document_repository import metadata_projection
from app.services import agenti_proposte
from app.services.drive_cartella_unica import ARRETRATO, ERRORI, REGISTRO

logger = logging.getLogger(__name__)

SETTORI: List[Dict[str, str]] = [
    {"id": "verbali", "nome": "Verbali e auto"},
    {"id": "cedolini", "nome": "Cedolini"},
    {"id": "bonifici", "nome": "Bonifici e banca"},
    {"id": "fatture", "nome": "Fatture"},
    {"id": "corrispettivi", "nome": "Corrispettivi"},
    {"id": "f24", "nome": "F24 e tributi"},
]

#: Chiavi di ``sistema_stato`` scritte dai giri, per settore: (chiave, etichetta, campo dell'istante,
#: {nome mostrato: percorso nel documento}).
GIRI: Dict[str, List[Dict[str, Any]]] = {
    "verbali": [
        {"chiave": "notifiche_pec_verbali_ultimo_giro", "etichetta": "PEC dei verbali", "istante": "eseguito_at",
         "conteggi": {"letti": "totali", "associati": "agganciate", "da_agganciare": "da_agganciare"}},
        {"chiave": "verbali_ricostruzione", "etichetta": "Ricostruzione dal PDF", "istante": "aggiornato_il",
         "conteggi": {}},
    ],
    "cedolini": [
        {"chiave": "cedolini_hr_riverifica", "etichetta": "Rilettura netti HR", "istante": "updated_at",
         "conteggi": {}},
        {"chiave": "cedolini_versioni", "etichetta": "Versioni della stessa busta", "istante": "aggiornato_il",
         "conteggi": {"gruppi": "gruppi", "rimasti": "rimasti"}},
    ],
    "bonifici": [
        {"chiave": "riconciliazione_ultimo_giro", "etichetta": "Riconciliazione (30 min)", "istante": "terminato_at",
         "conteggi": {"associati": "conteggi.bonifici", "stipendi": "conteggi.stipendi", "assegni": "conteggi.assegni"}},
        {"chiave": "bonifiche_automatiche", "etichetta": "Bonifiche automatiche", "istante": "eseguita_at",
         "conteggi": {}},
    ],
    "fatture": [
        {"chiave": "drive_cartella_unica_last_sync", "etichetta": "Cartella unica Drive", "istante": "valore",
         "conteggi": {"letti": "last_result.letti", "associati": "last_result.elaborati",
                      "errori": "last_result.errori"}},
        {"chiave": "pagamenti_dichiarati_titolare", "etichetta": "Report del titolare", "istante": "updated_at",
         "conteggi": {}},
    ],
    "corrispettivi": [
        {"chiave": "drive_cartella_unica_last_sync", "etichetta": "Cartella unica Drive", "istante": "valore",
         "conteggi": {"letti": "last_result.letti", "associati": "last_result.elaborati",
                      "errori": "last_result.errori"}},
    ],
    "f24": [
        {"chiave": "riconciliazione_ultimo_giro", "etichetta": "Riconciliazione (30 min)", "istante": "terminato_at",
         "conteggi": {"associati": "conteggi.f24"}},
        {"chiave": "drive_cartella_unica_last_sync", "etichetta": "Cartella unica Drive", "istante": "valore",
         "conteggi": {"letti": "last_result.letti", "associati": "last_result.elaborati",
                      "errori": "last_result.errori"}},
    ],
}

#: Tipo dello smistatore -> settore, per i file in ERRORI/ARRETRATO.
TIPI_PER_SETTORE: Dict[str, tuple] = {
    "verbali": ("verbale_codice_strada", "avviso_pagopa", "ricevuta_pagopa"),
    "cedolini": ("cedolino",),
    "bonifici": ("bonifici", "distinte_bpm", "estratto_conto", "estratto_conto_sumup", "spese_sumup"),
    "fatture": ("fattura", "report_fatture_ricevute"),
    "corrispettivi": ("corrispettivo", "corrispettivi_csv_ade", "pos_terminal"),
    "f24": ("f24", "quietanza_f24", "dichiarazione_fiscale", "cartella_pagamento"),
}
ROTTA_ERRORI = "/documenti/import"
ROTTA_INBOX = "/documenti/archivio"
PREFISSO_F24_NON_QUADRATO = "F24 non quadrato"


def _percorso(doc: Dict[str, Any], percorso: str) -> Any:
    valore: Any = doc
    for parte in percorso.split("."):
        if not isinstance(valore, dict):
            return None
        valore = valore.get(parte)
    return valore


def _intero(valore: Any) -> Optional[int]:
    if isinstance(valore, bool) or valore is None:
        return None
    try:
        return int(valore)
    except (TypeError, ValueError):
        return None


async def _ultimi_giri(db, settore: str, stati: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    giri = []
    for g in GIRI.get(settore, []):
        doc = stati.get(g["chiave"])
        if not doc:
            giri.append({"chiave": g["chiave"], "etichetta": g["etichetta"], "at": None, "conteggi": {},
                         "errore": None, "mai_eseguito": True})
            continue
        at = doc.get(g["istante"]) or doc.get("updated_at") or doc.get("aggiornato_il")
        conteggi = {nome: _intero(_percorso(doc, p)) for nome, p in g["conteggi"].items()}
        errore = doc.get("errore") or doc.get("last_error")
        giri.append({"chiave": g["chiave"], "etichetta": g["etichetta"], "at": at,
                     "conteggi": {k: v for k, v in conteggi.items() if v is not None},
                     "errore": str(errore)[:300] if errore else None, "mai_eseguito": False})
    return giri


async def _stati(db) -> Dict[str, Dict[str, Any]]:
    chiavi = sorted({g["chiave"] for lista in GIRI.values() for g in lista})
    righe = await db["sistema_stato"].find({"chiave": {"$in": chiavi}}, {"_id": 0}).to_list(None)
    return {r["chiave"]: r for r in righe if r.get("chiave")}


def _coda(nome: str, conteggio: Optional[int], rotta: Optional[str], motivo: str) -> Dict[str, Any]:
    return {"nome": nome, "conteggio": conteggio, "rotta_pagina": rotta, "motivo": motivo}


async def _conta(fn: Callable[[], Awaitable[int]], nome: str) -> Optional[int]:
    """Un conteggio che fallisce e' «Dato non disponibile», mai zero."""
    try:
        return int(await fn())
    except Exception as exc:  # noqa: BLE001 - il cruscotto deve aprirsi lo stesso
        logger.warning("[agenti-settori] conteggio «%s» non calcolato: %s: %s", nome, type(exc).__name__, exc)
        return None


async def _errori_per_tipo(db) -> Dict[str, Dict[str, int]]:
    """Righe del registro in ERRORI/ARRETRATO per tipo, con i non quadrati degli F24."""
    righe = await db[REGISTRO].find(
        {"cartella": {"$in": [ERRORI, ARRETRATO]}},
        {"_id": 0, "tipo": 1, "cartella": 1, "motivo": 1},
    ).to_list(None)
    esito: Dict[str, Dict[str, int]] = {"ERRORI": {}, "ARRETRATO": {}, "f24_non_quadrati": {"n": 0},
                                        "non_riconosciuti": {"n": 0}}
    for r in righe:
        tipo = str(r.get("tipo") or "non_riconosciuto")
        cartella = r.get("cartella")
        if cartella in esito:
            esito[cartella][tipo] = esito[cartella].get(tipo, 0) + 1
        if cartella == ERRORI and tipo in ("non_riconosciuto", "auto"):
            esito["non_riconosciuti"]["n"] += 1
        if cartella == ERRORI and tipo == "f24" and str(r.get("motivo") or "").startswith(PREFISSO_F24_NON_QUADRATO):
            esito["f24_non_quadrati"]["n"] += 1
    return esito


def _somma_tipi(per_tipo: Dict[str, int], tipi: tuple) -> int:
    return sum(per_tipo.get(t, 0) for t in tipi)


async def _verbali_senza_driver(db) -> int:
    righe = await db["verbali_noleggio"].find(
        {"stato": {"$in": varianti(STATI_APERTI)}},
        metadata_projection("verbali_noleggio", {"_id": 0, "driver_id": 1, "driver": 1}),
    ).to_list(None)
    return sum(1 for v in righe if not v.get("driver_id") and not v.get("driver"))


async def _cedolini_senza_netto(db) -> int:
    from app.services.cedolini_versioni import attiva

    righe = await db["cedolini"].find(
        {}, metadata_projection("cedolini", {"_id": 0, "status": 1, "entity_status": 1, "netto": 1,
                                             "netto_mese": 1, "stato_netto": 1}),
    ).to_list(None)
    return sum(1 for c in righe if attiva(c)
               and (c.get("stato_netto") != NETTO_VERIFICATO_DA_CEDOLINO or not c.get("netto_mese", c.get("netto"))))


async def _cedolini_varianti(db) -> int:
    return await db["cedolini"].count_documents({"varianti_da_decidere": True})


async def _bonifici_hr_da_associare() -> int:
    from app.hr.database import Database, DatabaseNonConfigurato

    db_hr = Database.get_db()
    if db_hr is None or isinstance(db_hr, DatabaseNonConfigurato):
        raise RuntimeError("database HR non configurato")
    return await db_hr["bonifici_da_associare"].count_documents({"stato": "da_associare"})


async def _banca_senza_categoria(db) -> int:
    from app.services.fonti_ferme import copertura_categoria_banca

    r = await copertura_categoria_banca(db)
    if r.get("senza_categoria") is None:
        raise RuntimeError("copertura banca non calcolabile")
    return int(r["senza_categoria"])


async def _fatture_senza_metodo(db) -> int:
    from app.services.fattura_attiva import FILTRO_FATTURA_ATTIVA
    from app.services.stato_pagamento_fattura import FILTRO_NON_PAGATE

    return await db["invoices"].count_documents({"$and": [FILTRO_FATTURA_ATTIVA, FILTRO_NON_PAGATE,
                                                          FILTRO_METODO_NON_CONFIGURATO]})


async def _inbox_non_classificata(db) -> int:
    return await db["documents_inbox"].count_documents({"$or": [
        {"categoria": None}, {"categoria": ""}, {"categoria": {"$exists": False}}]})


async def _ai_da_rivedere(db) -> int:
    return await db["documents_inbox"].count_documents({"$or": [
        {"needs_review": True}, {"classificazione_automatica": False, "ai_parsed": True},
        {"ai_confidence": "low"}, {"ai_parsing_error": {"$exists": True}}]})


async def stato_settori(db) -> Dict[str, Any]:
    """Per ogni settore: ultimi giri, code ferme e proposte AI in attesa."""
    stati = await _stati(db)
    try:
        errori: Optional[Dict[str, Dict[str, int]]] = await _errori_per_tipo(db)
    except Exception as exc:  # noqa: BLE001 - il registro non letto e' «dato non disponibile»
        logger.warning("[agenti-settori] registro cartella unica non letto: %s: %s", type(exc).__name__, exc)
        errori = None
    proposte = await agenti_proposte.conteggio_in_attesa(db)
    settori = []
    for s in SETTORI:
        sid = s["id"]
        tipi = TIPI_PER_SETTORE[sid]
        code: List[Dict[str, Any]] = []
        if errori is None:
            code.append(_coda("File in ERRORI su Drive", None, ROTTA_ERRORI, "registro della cartella unica non letto"))
        else:
            code.append(_coda("File in ERRORI su Drive", _somma_tipi(errori["ERRORI"], tipi), ROTTA_ERRORI,
                              "riconosciuti ma non registrati: il motivo e' sul file"))
            if sid == "f24":
                code.append(_coda("F24 non quadrati", errori["f24_non_quadrati"]["n"], ROTTA_ERRORI,
                                  "saldo stampato diverso dalle righe lette"))
            if sid == "corrispettivi":
                code.append(_coda("Chiusure RT scartate", errori["ERRORI"].get("corrispettivo", 0), ROTTA_ERRORI,
                                  "XML di chiusura non registrato"))
        if sid == "verbali":
            code.append(_coda("Verbali senza driver", await _conta(lambda: _verbali_senza_driver(db), "verbali"),
                              "/noleggio", "nessuna assegnazione alla data del fatto"))
        elif sid == "cedolini":
            code.append(_coda("Buste senza netto verificato", await _conta(lambda: _cedolini_senza_netto(db), "netto"),
                              "/hr/", "cella del netto vuota o non letta"))
            code.append(_coda("Varianti da decidere", await _conta(lambda: _cedolini_varianti(db), "varianti"),
                              "/hr/", "stessa busta con netti diversi"))
        elif sid == "bonifici":
            code.append(_coda("Bonifici HR da associare", await _conta(_bonifici_hr_da_associare, "hr"),
                              "/distinta-bonifici", "dipendente o periodo non univoco"))
            code.append(_coda("Movimenti banca senza categoria", await _conta(lambda: _banca_senza_categoria(db), "banca"),
                              "/riconciliazione/movimenti-banca", "causale non riconosciuta dal motore"))
        elif sid == "fatture":
            code.append(_coda("Fatture aperte senza metodo", await _conta(lambda: _fatture_senza_metodo(db), "metodo"),
                              "/fatture", "fornitore senza metodo di pagamento"))
            code.append(_coda("Letture AI da rivedere", await _conta(lambda: _ai_da_rivedere(db), "ai"),
                              ROTTA_INBOX, "parser AI incerto o in errore"))
        settori.append({
            "id": sid, "nome": s["nome"],
            "giri": await _ultimi_giri(db, sid, stati),
            "code_ferme": code,
            "proposte_in_attesa": proposte.get(sid, 0),
        })
    agenti = await agenti_proposte.stato(db)
    agenti["non_riconosciuti_errori"] = None if errori is None else errori["non_riconosciuti"]["n"]
    agenti["arretrato"] = None if errori is None else sum(errori["ARRETRATO"].values())
    agenti["inbox_non_classificata"] = await _conta(lambda: _inbox_non_classificata(db), "inbox")
    agenti["proposte_altro"] = proposte.get(agenti_proposte.SETTORE_ALTRO, 0)
    return {"settori": settori, "agenti_ai": agenti}
