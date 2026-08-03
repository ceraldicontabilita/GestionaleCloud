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
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

COLL_MOVIMENTI = "movimenti_contabili"
COLL_PIANO_CONTI = "piano_conti"

# Conti fissi corrispettivi (schema CEE)
_C_CASSA = ("01.01.01", "Cassa")
_C_BANCA = ("01.01.02", "Banca c/c")
_C_RICAVI = ("04.01.02", "Ricavi vendite bar")
_C_IVA_DEBITO = ("02.03.01", "IVA a debito")
_ALIQUOTA_CORRISPETTIVI = 0.10  # ristorazione (parametro storico, invariato)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    `{"anno": anno}` in Mongo intercetta sia i documenti con `anno` uguale
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
    """Inserisce il movimento e aggiorna i saldi dei conti (una sola volta)."""
    from app.routers.accounting.piano_conti import aggiorna_saldo_conto
    await db[COLL_MOVIMENTI].insert_one(movimento.copy())
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
    iva_detraibile = iva if iva_detraibile_raw is None else float(iva_detraibile_raw or 0)
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

    iva = round(totale * _ALIQUOTA_CORRISPETTIVI / (1 + _ALIQUOTA_CORRISPETTIVI), 2)
    imponibile = round(totale - iva, 2)
    cassa = float(corr.get("pagato_contante", corr.get("pagato_cassa", 0)) or 0)
    pos = float(corr.get("pagato_elettronico", 0) or 0)
    if cassa + pos == 0:
        cassa = totale

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
    }
    mov = await _scrivi_movimento(db, movimento, saldi)
    await db["corrispettivi"].update_one(
        {"id": corr_id},
        {"$set": {"registrato_contabilita": True, "movimento_contabile_id": mov["id"]}})
    return {"stato": "registrato", "movimento": mov}


async def registra_tutte_fatture(db) -> Dict[str, Any]:
    fatture = await db["invoices"].find(
        {"$or": [{"registrata_contabilita": {"$ne": True}},
                 {"registrata_contabilita": {"$exists": False}}]}, {"_id": 0}).to_list(5000)
    registrate, errori = 0, []
    for f in fatture:
        try:
            r = await registra_fattura(db, f)
            if r.get("stato") == "registrato":
                registrate += 1
        except Exception as e:  # noqa: BLE001 - raccolgo e riporto, non silenzio
            errori.append(f"Fattura {f.get('invoice_number', 'N/A')}: {e}")
    return {"success": True, "fatture_processate": len(fatture),
            "registrate": registrate, "errori": errori[:20]}


async def registra_tutti_corrispettivi(db) -> Dict[str, Any]:
    corrispettivi = await db["corrispettivi"].find(
        {"$or": [{"registrato_contabilita": {"$ne": True}},
                 {"registrato_contabilita": {"$exists": False}}]}, {"_id": 0}).to_list(5000)
    registrati, errori = 0, []
    for c in corrispettivi:
        try:
            r = await registra_corrispettivo(db, c)
            if r.get("stato") == "registrato":
                registrati += 1
        except Exception as e:  # noqa: BLE001
            errori.append(f"Corrispettivo {c.get('id', 'N/A')}: {e}")
    return {"success": True, "corrispettivi_processati": len(corrispettivi),
            "registrati": registrati, "errori": errori[:20]}


async def ricostruisci_fatture(db) -> Dict[str, Any]:
    """Ricostruzione completa (ex `ricategorizza-fatture`): azzera i movimenti di
    tipo fattura_acquisto + i saldi (tranne cassa/banca) e ri-registra tutto da zero.
    NON tocca i movimenti di corrispettivi/ammortamenti/TFR."""
    conti_da_non_resettare = [_C_CASSA[0], _C_BANCA[0]]
    await db[COLL_PIANO_CONTI].update_many(
        {"codice": {"$nin": conti_da_non_resettare}}, {"$set": {"saldo": 0}})
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
