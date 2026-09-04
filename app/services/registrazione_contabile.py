"""Motore UNICO di registrazione contabile in partita doppia (PROMPT_DEFINITIVO §6.1).

Sostituisce le tre logiche parallele e divergenti:
- `contabilita_avanzata /ricategorizza-fatture`
- `piano_conti /registra-tutte-fatture`
- `piano_conti /registra-corrispettivi`
- `piano_conti /registra-fattura` (singola)

Schema CEE (piano dei conti puntato, es. 05.01.01). NON tocca il piano numerico di
`contabilita_italiana` (rinviato, scelta utente §6).

Requisiti §6.1 garantiti:
- idempotenza: una fattura/corrispettivo non viene registrato due volte (chiave naturale
  tipo+documento);
- fonte documento: `fonte_documento` {tipo, id, numero};
- numero di protocollo PROGRESSIVO PER ANNO (`numero_registrazione`, scelta utente
  2026-07-14): riparte da 1 a ogni nuovo anno solare, come nella prassi dei registri
  contabili (Zucchetti/TeamSystem/GB); univoco all'interno dello stesso anno;
- data competenza: `data_competenza` oltre a data documento/registrazione;
- DARE/AVERE espliciti su ogni riga (colonne `dare`/`avere`), con conto e centro di costo;
- audit log su ogni scrittura;
- possibilità di ricostruzione: `ricostruisci_fatture()`.

Riusa gli helper canonici di `piano_conti` (determina_conti_fattura, aggiorna_saldo_conto)
via import pigro per evitare import circolari.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

COLL_MOVIMENTI = "movimenti_contabili"
COLL_PIANO_CONTI = "piano_conti"

# Audit del commercialista 03/09/2026 §2 (PR 8): oltre alla guardia
# ``find_one`` (valida in un solo processo), ogni scrittura porta una
# ``idempotency_key`` naturale che Postgres rende UNICA tra le righe attive
# (indice ``documents_idempotency_key_uidx``, migrazione
# supabase/migrations/20260903_idempotency_key.sql): due processi che
# registrano lo stesso documento nello stesso istante producono UNA sola
# scrittura, l'altra viene rifiutata e riallineata al documento esistente.
_PREFISSO_CHIAVE = "reg"


def chiave_idempotenza(tipo_documento: str, documento_id: str) -> str:
    """Chiave naturale della scrittura: ``reg:<tipo>:<id documento>``."""
    return f"{_PREFISSO_CHIAVE}:{tipo_documento}:{documento_id}"


def _documento_esistente_da_rifiuto(exc: BaseException, chiave: Optional[str]) -> Optional[Dict[str, Any]]:
    """Se ``exc`` e' il rifiuto di Postgres per ``idempotency_key`` gia'
    usata (``DocumentoDuplicatoRemoto`` del runtime Supabase), restituisce
    la scrittura gia' esistente per quella chiave; altrimenti ``None``.
    Confronto per nome per non importare il runtime nel motore contabile."""
    if not chiave or type(exc).__name__ != "DocumentoDuplicatoRemoto":
        return None
    esistenti = getattr(exc, "documento_esistente_per_chiave", None) or {}
    ids = getattr(exc, "id_esistente_per_chiave", None) or {}
    if chiave not in ids and chiave not in esistenti:
        return None
    doc = dict(esistenti.get(chiave) or {})
    doc.setdefault("id", ids.get(chiave))
    doc.pop("_id", None)
    return doc

# Conti fissi corrispettivi (schema CEE)
_C_CASSA = ("01.01.01", "Cassa")
_C_BANCA = ("01.01.02", "Banca c/c")
_C_RICAVI = ("04.01.02", "Ricavi vendite bar")
_C_IVA_DEBITO = ("02.03.01", "IVA a debito")
_ALIQUOTA_CORRISPETTIVI = 0.10  # ristorazione (parametro storico, invariato)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _primo_importo(doc: Dict[str, Any], *chiavi: str) -> float:
    """Primo importo presente (non None) tra le chiavi indicate, come float."""
    for chiave in chiavi:
        valore = doc.get(chiave)
        if valore is None or valore == "":
            continue
        try:
            return float(valore)
        except (TypeError, ValueError):
            continue
    return 0.0


def _anno_da_data(data: Optional[str]) -> Optional[int]:
    if not data:
        return None
    try:
        return int(str(data)[:4])
    except (ValueError, TypeError):
        return None


async def _prossimo_numero(db, anno: Optional[int]) -> int:
    """Numero di protocollo PROGRESSIVO PER ANNO (scelta utente 2026-07-14,
    prassi dei registri contabili): riparte da 1 a ogni nuovo anno solare.
    `{"anno": anno}` nel repository intercetta sia i documenti con `anno` uguale
    sia quelli senza il campo, quando `anno` è None (fallback per scritture
    senza data individuabile)."""
    ultimo = await db[COLL_MOVIMENTI].find_one(
        {"numero_registrazione": {"$exists": True}, "anno": anno},
        {"_id": 0, "numero_registrazione": 1},
        sort=[("numero_registrazione", -1)],
    )
    if ultimo and isinstance(ultimo.get("numero_registrazione"), int):
        return ultimo["numero_registrazione"] + 1
    return 1


async def _audit(db, azione: str, entita_id: str, dettaglio: str) -> None:
    try:
        from app.services.audit_logger import log_evento
        await log_evento(
            modulo="contabilita", azione=azione, entita_id=str(entita_id),
            entita_collection=COLL_MOVIMENTI, db=db, fonte="registrazione_contabile",
            dettaglio=dettaglio,
        )
    except Exception:
        # l'audit non deve mai bloccare la registrazione
        pass


async def _scrivi_movimento(db, movimento: Dict[str, Any], saldi: list) -> Dict[str, Any]:
    """Inserisce il movimento e aggiorna i saldi dei conti (una sola volta).

    Se Postgres rifiuta la riga perche' la ``idempotency_key`` e' gia' usata
    (scrittura fatta nel frattempo da un altro processo), NON aggiorna i
    saldi e restituisce la scrittura esistente con ``gia_registrato=True``.
    """
    from app.routers.accounting.piano_conti import aggiorna_saldo_conto
    try:
        await db[COLL_MOVIMENTI].insert_one(movimento.copy())
    except Exception as exc:  # noqa: BLE001 - solo il rifiuto per chiave e' gestito
        esistente = _documento_esistente_da_rifiuto(exc, movimento.get("idempotency_key"))
        if esistente is None:
            raise
        logger.warning(
            "Scrittura %s gia' presente (chiave %s, id %s): nessuna seconda registrazione",
            movimento.get("tipo"), movimento.get("idempotency_key"), esistente.get("id"),
        )
        esistente["gia_registrato"] = True
        return esistente
    for codice, importo, verso in saldi:
        if importo:
            await aggiorna_saldo_conto(db, codice, importo, verso)
    await _audit(db, "registrato", movimento["id"],
                 f"{movimento['tipo']} {movimento.get('descrizione', '')} "
                 f"n.{movimento['numero_registrazione']} DARE={movimento['totale_dare']} "
                 f"AVERE={movimento['totale_avere']}")
    movimento.pop("_id", None)
    return movimento


async def registra_fattura(db, fattura: Dict[str, Any], *, force: bool = False,
                           conti: Optional[Dict[str, Any]] = None,
                           extra_movimento: Optional[Dict[str, Any]] = None,
                           extra_fattura: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Registra una fattura acquisto in partita doppia (idempotente).

    DARE costo merce (imponibile) + IVA a credito · AVERE debito v/fornitore (totale).

    `conti` opzionale permette a chi ha una categorizzazione più ricca (es.
    contabilita_avanzata con deducibilità IRES/IRAP) di passare i conti già scelti,
    mantenendo un unico motore/schema/scrittura. `extra_movimento`/`extra_fattura`
    aggiungono campi al movimento e alla fattura senza duplicare la logica.
    """
    from app.routers.accounting.piano_conti import determina_conti_fattura

    fattura_id = fattura.get("id")
    if not fattura_id:
        return {"stato": "saltato", "motivo": "fattura senza id"}

    if not force:
        esistente = await db[COLL_MOVIMENTI].find_one(
            {"tipo": "fattura_acquisto", "fattura_id": fattura_id}, {"_id": 0, "id": 1})
        if esistente:
            return {"stato": "gia_registrato", "movimento_id": esistente.get("id")}

    # importi robusti a schemi diversi
    importo_totale = float(fattura.get("total_amount") or fattura.get("importo_totale") or 0)
    iva = float(fattura.get("total_tax") or fattura.get("iva") or fattura.get("totale_iva") or 0)
    iva_detraibile_raw = fattura.get("iva_detraibile")
    if iva > 0 and iva_detraibile_raw is None:
        return {
            "stato": "da_verificare",
            "motivo": "IVA detraibile non classificata",
        }
    iva_detraibile = float(iva_detraibile_raw or 0)
    iva_detraibile = round(max(0.0, min(iva, iva_detraibile)), 2)
    iva_indetraibile = round(max(0.0, iva - iva_detraibile), 2)
    imponibile = float(fattura.get("imponibile") or (importo_totale - iva) or 0)
    if importo_totale <= 0:
        importo_totale = imponibile + iva
    if importo_totale <= 0:
        return {"stato": "saltato", "motivo": "importo nullo"}

    if conti is None:
        conti = await determina_conti_fattura(db, fattura)
    centro_costo = fattura.get("centro_costo") or fattura.get("centro_di_costo")
    data_doc = fattura.get("invoice_date") or fattura.get("data_fattura")
    numero = fattura.get("invoice_number") or fattura.get("numero_fattura")
    anno = _anno_da_data(fattura.get("data_competenza") or data_doc)

    costo_contabile = round(imponibile + iva_indetraibile, 2)
    righe = [
        {"conto_codice": conti["costo"]["codice"], "conto_nome": conti["costo"]["nome"],
         "dare": costo_contabile, "avere": 0, "centro_costo": centro_costo,
         "descrizione": (
             "Costo acquisto" if iva_indetraibile == 0
             else f"Costo acquisto (incl. IVA indetraibile {iva_indetraibile:.2f})"
         )},
        {"conto_codice": conti["iva_credito"]["codice"], "conto_nome": conti["iva_credito"]["nome"],
         "dare": iva_detraibile, "avere": 0, "centro_costo": None, "descrizione": "IVA a credito detraibile"},
        {"conto_codice": conti["debito_fornitore"]["codice"], "conto_nome": conti["debito_fornitore"]["nome"],
         "dare": 0, "avere": importo_totale, "centro_costo": None, "descrizione": "Debito v/fornitore"},
    ]
    now = _now()
    movimento = {
        "id": str(uuid.uuid4()),
        "numero_registrazione": await _prossimo_numero(db, anno),
        "tipo": "fattura_acquisto",
        "fonte_documento": {"tipo": "fattura", "id": fattura_id, "numero": numero},
        "fattura_id": fattura_id,
        "descrizione": f"Fattura {numero or ''} - {fattura.get('supplier_name') or fattura.get('cedente_denominazione') or ''}".strip(),
        "data": data_doc, "data_documento": data_doc,
        "data_competenza": fattura.get("data_competenza") or data_doc,
        "data_registrazione": now,
        "anno": anno,
        "importo_totale": importo_totale, "imponibile": imponibile, "iva": iva,
        "iva_detraibile": iva_detraibile, "iva_indetraibile": iva_indetraibile,
        "righe": righe,
        "totale_dare": round(costo_contabile + iva_detraibile, 2),
        "totale_avere": round(importo_totale, 2),
        "stato": "registrato", "created_at": now,
        "idempotency_key": chiave_idempotenza("fattura", fattura_id),
    }
    if extra_movimento:
        movimento.update(extra_movimento)
    saldi = [
        (conti["costo"]["codice"], costo_contabile, "dare"),
        (conti["iva_credito"]["codice"], iva_detraibile, "dare"),
        (conti["debito_fornitore"]["codice"], importo_totale, "avere"),
    ]
    mov = await _scrivi_movimento(db, movimento, saldi)
    patch = {"registrata_contabilita": True, "movimento_contabile_id": mov["id"]}
    if extra_fattura:
        patch.update(extra_fattura)
    await db["invoices"].update_one({"id": fattura_id}, {"$set": patch})
    if mov.get("gia_registrato"):
        return {"stato": "gia_registrato", "movimento_id": mov.get("id")}
    return {"stato": "registrato", "movimento": mov}


async def registra_corrispettivo(db, corr: Dict[str, Any], *, force: bool = False) -> Dict[str, Any]:
    """Registra un corrispettivo (idempotente).
    DARE cassa/banca · AVERE ricavi + IVA a debito (scorporo aliquota storica)."""
    corr_id = corr.get("id")
    if not corr_id:
        return {"stato": "saltato", "motivo": "corrispettivo senza id"}

    if not force:
        esistente = await db[COLL_MOVIMENTI].find_one(
            {"tipo": "corrispettivo", "corrispettivo_id": corr_id}, {"_id": 0, "id": 1})
        if esistente:
            return {"stato": "gia_registrato", "movimento_id": esistente.get("id")}

    totale = float(corr.get("totale", 0) or 0)
    if totale <= 0:
        return {"stato": "saltato", "motivo": "importo nullo"}

    iva_raw = corr.get("totale_iva")
    if iva_raw is None:
        iva_raw = corr.get("iva")
    imponibile_raw = corr.get("totale_imponibile")
    if imponibile_raw is None:
        imponibile_raw = corr.get("imponibile")

    # L'XML del corrispettivo e' la fonte dell'aliquota effettiva. Il 10%
    # resta solo un fallback per record storici privi del dettaglio fiscale.
    try:
        iva = round(float(iva_raw), 2) if iva_raw is not None else None
        imponibile = round(float(imponibile_raw), 2) if imponibile_raw is not None else None
    except (TypeError, ValueError):
        return {"stato": "da_verificare", "motivo": "IVA o imponibile non numerico"}
    if iva is None and imponibile is None:
        iva = round(totale * _ALIQUOTA_CORRISPETTIVI / (1 + _ALIQUOTA_CORRISPETTIVI), 2)
        imponibile = round(totale - iva, 2)
    elif iva is None:
        iva = round(totale - imponibile, 2)
    elif imponibile is None:
        imponibile = round(totale - iva, 2)
    if iva < 0 or imponibile < 0 or abs(round(imponibile + iva - totale, 2)) > 0.01:
        return {
            "stato": "da_verificare",
            "motivo": "totale, imponibile e IVA del corrispettivo non quadrano",
        }
    # Nomi reali dei campi (verificati sui 1218 corrispettivi in archivio il
    # 03/09/2026): `pagato_contanti` (plurale, scritto dal parser XML e dai
    # servizi) e `pagato_elettronico`; `pagato_contante`/`pagato_cassa`/
    # `pagato_pos` restano come ripiego per record storici. Prima si leggeva
    # SOLO il singolare `pagato_contante`, assente ovunque: ogni giornata con
    # contanti + POS finiva "da_verificare" (ripartizione non quadrata).
    cassa = _primo_importo(corr, "pagato_contanti", "pagato_contante", "pagato_cassa")
    pos = _primo_importo(corr, "pagato_elettronico", "pagato_pos")
    if cassa + pos == 0:
        cassa = totale
    elif abs(round(cassa + pos - totale, 2)) > 0.01:
        return {
            "stato": "da_verificare",
            "motivo": "ripartizione contanti/POS non quadrata con il totale",
        }

    righe = []
    saldi = []
    if cassa > 0:
        righe.append({"conto_codice": _C_CASSA[0], "conto_nome": _C_CASSA[1], "dare": cassa, "avere": 0, "centro_costo": None})
        saldi.append((_C_CASSA[0], cassa, "dare"))
    if pos > 0:
        righe.append({"conto_codice": _C_BANCA[0], "conto_nome": _C_BANCA[1], "dare": pos, "avere": 0, "centro_costo": None})
        saldi.append((_C_BANCA[0], pos, "dare"))
    righe.append({"conto_codice": _C_RICAVI[0], "conto_nome": _C_RICAVI[1], "dare": 0, "avere": imponibile, "centro_costo": None})
    righe.append({"conto_codice": _C_IVA_DEBITO[0], "conto_nome": _C_IVA_DEBITO[1], "dare": 0, "avere": iva, "centro_costo": None})
    saldi.append((_C_RICAVI[0], imponibile, "avere"))
    saldi.append((_C_IVA_DEBITO[0], iva, "avere"))

    data_corr = corr.get("data") or _now()[:10]
    anno = _anno_da_data(data_corr)
    now = _now()
    movimento = {
        "id": str(uuid.uuid4()),
        "numero_registrazione": await _prossimo_numero(db, anno),
        "tipo": "corrispettivo",
        "fonte_documento": {"tipo": "corrispettivo", "id": corr_id, "numero": None},
        "corrispettivo_id": corr_id,
        "descrizione": f"Corrispettivo del {data_corr}",
        "data": data_corr, "data_documento": data_corr,
        "data_competenza": data_corr, "data_registrazione": now,
        "anno": anno,
        "importo_totale": totale, "imponibile": imponibile, "iva": iva,
        "righe": righe,
        "totale_dare": round(cassa + pos, 2), "totale_avere": round(totale, 2),
        "stato": "registrato", "created_at": now,
        "idempotency_key": chiave_idempotenza("corrispettivo", corr_id),
    }
    mov = await _scrivi_movimento(db, movimento, saldi)
    await db["corrispettivi"].update_one(
        {"id": corr_id},
        {"$set": {"registrato_contabilita": True, "movimento_contabile_id": mov["id"]}})
    if mov.get("gia_registrato"):
        return {"stato": "gia_registrato", "movimento_id": mov.get("id")}
    return {"stato": "registrato", "movimento": mov}


# Stesso predicato "documento attivo" del bilancio di verifica
# (contabilita_gestionale._bilancio_verifica_da_registro): un documento
# cancellato o archiviato non va mai registrato nel libro giornale.
_FILTRO_FATTURE_DA_REGISTRARE: Dict[str, Any] = {
    "status": {"$nin": ["deleted", "archived"]},
    "entity_status": {"$ne": "deleted"},
    "registrata_contabilita": {"$ne": True},
}
_FILTRO_CORRISPETTIVI_DA_REGISTRARE: Dict[str, Any] = {
    "status": {"$nin": ["deleted", "archived"]},
    "entity_status": {"$ne": "deleted"},
    "registrato_contabilita": {"$ne": True},
}
# Un corrispettivo provvisorio (chiusura manuale serale in attesa dell'XML
# del registratore telematico) non e' ancora un documento fiscale: entra nel
# libro giornale solo quando arriva l'XML (stato definitivo) — altrimenti la
# scrittura nascerebbe su un totale che l'XML potrebbe correggere.
_STATI_CORRISPETTIVO_PROVVISORIO = {"provvisorio", "manca_xml"}


def _corrispettivo_registrabile(corr: Dict[str, Any]) -> bool:
    if str(corr.get("stato") or "") in _STATI_CORRISPETTIVO_PROVVISORIO:
        return False
    if corr.get("stato_import") == "archivio_storico":
        return False
    if corr.get("status") in {"archiviata", "archived", "deleted"}:
        return False
    return corr.get("entity_status") != "deleted"


def _riepilogo_esiti(esiti: list) -> Dict[str, int]:
    conteggio: Dict[str, int] = {}
    for stato in esiti:
        conteggio[stato] = conteggio.get(stato, 0) + 1
    return conteggio


async def registra_tutte_fatture(db, *, dry_run: bool = False) -> Dict[str, Any]:
    """Registra (idempotente) tutte le fatture attive non ancora nel libro
    giornale. ``dry_run=True`` conta soltanto, senza scrivere nulla."""
    fatture = await db["invoices"].find(
        dict(_FILTRO_FATTURE_DA_REGISTRARE), {"_id": 0}).to_list(5000)
    if dry_run:
        return {"success": True, "dry_run": True, "fatture_processate": len(fatture),
                "da_registrare": len(fatture), "registrate": 0, "errori": []}
    registrate, errori, esiti = 0, [], []
    for f in fatture:
        try:
            r = await registra_fattura(db, f)
            esiti.append(r.get("stato") or "sconosciuto")
            if r.get("stato") == "registrato":
                registrate += 1
        except Exception as e:  # noqa: BLE001 - raccolgo e riporto, non silenzio
            esiti.append("errore")
            errori.append(f"Fattura {f.get('invoice_number', 'N/A')}: {e}")
    return {"success": True, "dry_run": False, "fatture_processate": len(fatture),
            "registrate": registrate, "esiti": _riepilogo_esiti(esiti),
            "errori": errori[:20]}


async def registra_tutti_corrispettivi(db, *, dry_run: bool = False) -> Dict[str, Any]:
    """Registra (idempotente) tutti i corrispettivi definitivi non ancora nel
    libro giornale. ``dry_run=True`` conta soltanto, senza scrivere nulla."""
    trovati = await db["corrispettivi"].find(
        dict(_FILTRO_CORRISPETTIVI_DA_REGISTRARE), {"_id": 0}).to_list(5000)
    corrispettivi = [c for c in trovati if _corrispettivo_registrabile(c)]
    provvisori = len(trovati) - len(corrispettivi)
    if dry_run:
        return {"success": True, "dry_run": True,
                "corrispettivi_processati": len(corrispettivi),
                "da_registrare": len(corrispettivi), "provvisori_esclusi": provvisori,
                "registrati": 0, "errori": []}
    registrati, errori, esiti = 0, [], []
    for c in corrispettivi:
        try:
            r = await registra_corrispettivo(db, c)
            esiti.append(r.get("stato") or "sconosciuto")
            if r.get("stato") == "registrato":
                registrati += 1
        except Exception as e:  # noqa: BLE001
            esiti.append("errore")
            errori.append(f"Corrispettivo {c.get('id', 'N/A')}: {e}")
    return {"success": True, "dry_run": False,
            "corrispettivi_processati": len(corrispettivi),
            "provvisori_esclusi": provvisori,
            "registrati": registrati, "esiti": _riepilogo_esiti(esiti),
            "errori": errori[:20]}


async def registra_pregresso(db, *, dry_run: bool = False) -> Dict[str, Any]:
    """Recupero del pregresso non registrato: UN solo giro che riusa le due
    funzioni massive (fatture + corrispettivi). Idempotente: rilanciarlo non
    crea seconde scritture. ``dry_run`` restituisce solo i conteggi."""
    fatture = await registra_tutte_fatture(db, dry_run=dry_run)
    corrispettivi = await registra_tutti_corrispettivi(db, dry_run=dry_run)
    return {
        "success": True,
        "dry_run": dry_run,
        "fatture": fatture,
        "corrispettivi": corrispettivi,
        "da_registrare": (
            fatture.get("da_registrare", fatture.get("fatture_processate", 0))
            + corrispettivi.get("da_registrare", corrispettivi.get("corrispettivi_processati", 0))
        ),
        "registrate": fatture.get("registrate", 0) + corrispettivi.get("registrati", 0),
        "errori": (fatture.get("errori") or []) + (corrispettivi.get("errori") or []),
    }


_COLLEZIONE_PER_TIPO = {"fattura": "invoices", "corrispettivo": "corrispettivi"}


async def registra_documento_import(db, tipo_documento: str, documento: Dict[str, Any]) -> Dict[str, Any]:
    """Aggancio UNICO per le pipeline di import (fatture XML, corrispettivi RT).

    Audit 03/09/2026 §2 (PR 8): il libro giornale si alimenta da solo
    all'arrivo del documento (art. 2216 c.c., 60 giorni) invece di aspettare
    il comando manuale "Registra fatture". Regole:
    - non solleva MAI: un errore contabile non deve bloccare l'import
      (viene loggato e annotato sul documento sorgente);
    - idempotente: stesso documento due volte → una sola scrittura;
    - un corrispettivo provvisorio viene rimandato all'arrivo dell'XML;
    - se la scrittura esiste gia' ma l'importo del documento e' cambiato
      (es. XML che sostituisce un totale manuale), NON riscrive: segnala
      ``da_verificare`` sul documento, perche' una correzione del libro
      giornale e' una scelta del contabile, non dell'import.
    """
    collezione = _COLLEZIONE_PER_TIPO.get(tipo_documento)
    doc_id = (documento or {}).get("id")
    if not collezione or not doc_id:
        return {"stato": "saltato", "motivo": "documento senza id o tipo sconosciuto"}
    if tipo_documento == "corrispettivo" and not _corrispettivo_registrabile(documento):
        return {"stato": "rimandato", "motivo": "corrispettivo provvisorio o archiviato"}
    try:
        if tipo_documento == "fattura":
            esito = await registra_fattura(db, documento)
        else:
            esito = await registra_corrispettivo(db, documento)
        if esito.get("stato") == "gia_registrato" and esito.get("movimento_id"):
            esito = await _verifica_importo_scrittura(db, documento, esito)
    except Exception as exc:  # noqa: BLE001 - mai bloccare l'import
        logger.exception("Registrazione contabile automatica fallita per %s %s",
                         tipo_documento, doc_id)
        esito = {"stato": "errore", "motivo": str(exc)}

    stato = esito.get("stato")
    if stato in {"da_verificare", "saltato", "errore"}:
        logger.warning("Registrazione contabile %s %s: %s (%s)",
                       tipo_documento, doc_id, stato, esito.get("motivo"))
        try:
            await db[collezione].update_one(
                {"id": doc_id},
                {"$set": {"registrazione_contabile_esito": {
                    "stato": stato, "motivo": esito.get("motivo"), "at": _now(),
                }}},
            )
        except Exception:  # noqa: BLE001
            logger.warning("Impossibile annotare l'esito contabile su %s %s", collezione, doc_id)
    elif stato in {"registrato", "gia_registrato"}:
        try:
            await db[collezione].update_one(
                {"id": doc_id}, {"$unset": {"registrazione_contabile_esito": ""}})
        except Exception:  # noqa: BLE001
            pass
    return esito


async def _verifica_importo_scrittura(db, documento: Dict[str, Any], esito: Dict[str, Any]) -> Dict[str, Any]:
    """Scrittura gia' presente: confronta l'importo registrato con quello
    del documento (un XML puo' sostituire un totale manuale)."""
    mov = await db[COLL_MOVIMENTI].find_one(
        {"id": esito["movimento_id"]}, {"_id": 0, "importo_totale": 1, "id": 1})
    if not mov:
        return esito
    importo_doc = float(
        documento.get("totale") or documento.get("total_amount")
        or documento.get("importo_totale") or 0)
    importo_reg = float(mov.get("importo_totale") or 0)
    if importo_doc > 0 and abs(round(importo_doc - importo_reg, 2)) > 0.01:
        return {
            "stato": "da_verificare",
            "movimento_id": esito["movimento_id"],
            "motivo": (
                f"scrittura gia' registrata per {importo_reg:.2f} ma il documento "
                f"vale ora {importo_doc:.2f}: correggere a mano nel libro giornale"
            ),
        }
    return esito


async def ricostruisci_fatture(db) -> Dict[str, Any]:
    """Ricostruzione completa (ex `ricategorizza-fatture`): azzera i movimenti di
    tipo fattura_acquisto + i saldi (tranne cassa/banca) e ri-registra tutto da zero.
    NON tocca i movimenti di corrispettivi/ammortamenti/TFR.

    I saldi per conto non vivono piu' nella collezione ``piano_conti``
    (dismessa, audit 03/09/2026 PR 7): si ricavano dalle scritture, quindi
    non c'e' nulla da azzerare oltre ai movimenti stessi."""
    await db[COLL_MOVIMENTI].delete_many({"tipo": "fattura_acquisto"})
    await db["invoices"].update_many(
        {"registrata_contabilita": True},
        {"$set": {"registrata_contabilita": False}, "$unset": {"movimento_contabile_id": ""}})
    res = await registra_tutte_fatture(db)
    res["ricostruzione"] = True
    return res


# ============================================================
# SCRITTURE SEMPLICI (A7): eventi non-documentali in partita doppia
# ============================================================

# Conti operativi ESISTENTI usati dalle scritture semplici (niente conti
# inventati: regola vincolante utente sul piano dei conti).
_C_TFR_COSTO = ("05.03.03", "TFR")
_C_TFR_DEBITO = ("02.04.01", "TFR")
_C_DEBITI_TRIBUTARI = ("02.02.01", "Debiti tributari")
_C_AMMORTAMENTO = ("05.04.01", "Ammortamento immobilizzazioni")
_C_FONDO_AMMORTAMENTO = ("01.05.01", "Fondo ammortamento")


def riga(conto: tuple, dare: float = 0, avere: float = 0,
         descrizione: str = "") -> Dict[str, Any]:
    """Riga di partita doppia nello stesso schema delle scritture del motore."""
    return {"conto_codice": conto[0], "conto_nome": conto[1],
            "dare": round(float(dare), 2), "avere": round(float(avere), 2),
            "centro_costo": None, "descrizione": descrizione}


async def registra_scrittura_semplice(db, movimento: Dict[str, Any],
                                      righe: list,
                                      chiave_naturale: Dict[str, Any]) -> Dict[str, Any]:
    """Registra in `movimenti_contabili` una scrittura in partita doppia per
    eventi NON documentali (TFR, ammortamenti, risultato d'esercizio...).

    Differenze rispetto a registra_fattura/corrispettivo (deliberate, A7):
    - NON aggiorna i saldi dei conti: il bilancio CEE aggrega dai documenti
      sorgente (cedolini, cespiti, fatture) — aggiornare i saldi qui
      produrrebbe DOPPIO CONTEGGIO.
    - Mantiene nel documento tutti i campi passati in `movimento` (tipo,
      importo, dettaglio, dipendente_id...): i lettori esistenti non cambiano.
    - Idempotente sulla `chiave_naturale` (es. {"tipo":..., "anno":...}).
    """
    esistente = await db[COLL_MOVIMENTI].find_one(chiave_naturale, {"_id": 0, "id": 1})
    if esistente:
        return {"id": esistente["id"], "gia_presente": True}

    tot_dare = round(sum(float(r.get("dare", 0) or 0) for r in righe), 2)
    tot_avere = round(sum(float(r.get("avere", 0) or 0) for r in righe), 2)
    if abs(tot_dare - tot_avere) > 0.01:
        raise ValueError(
            f"Scrittura non bilanciata: DARE {tot_dare} != AVERE {tot_avere}")

    doc = dict(movimento)
    doc.setdefault("id", str(uuid.uuid4()))
    if doc.get("data"):
        doc.setdefault("data_documento", doc["data"])
    anno = doc.get("anno")
    if anno is None:
        anno = _anno_da_data(doc.get("data_documento") or doc.get("data"))
        doc["anno"] = anno
    doc["righe"] = righe
    doc["totale_dare"] = tot_dare
    doc["totale_avere"] = tot_avere
    doc["numero_registrazione"] = await _prossimo_numero(db, anno)
    doc.setdefault("created_at", _now())
    await db[COLL_MOVIMENTI].insert_one(dict(doc))
    await _audit(db, "scrittura_semplice", doc["id"],
                 f"{doc.get('tipo', '?')} DARE={tot_dare} AVERE={tot_avere}")
    doc.pop("_id", None)
    doc["gia_presente"] = False
    return doc
