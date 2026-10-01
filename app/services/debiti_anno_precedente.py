"""Fatture dell'anno precedente pagate nell'anno attivo: solo il debito.

Titolare, 28/09/2026. Le fatture degli anni prima non entrano in `invoices`
(decisione del 20/09/2026: niente costo, IVA, giornale ne' Lotti fuori
dall'anno attivo). Ma quelle di dicembre si pagano a gennaio, febbraio,
marzo: FEP 71_25 e FEP 72_25 di A 2000 Costruzioni (12.200,00 ciascuna, del
29/12/2025) sono state pagate con tre bonifici del 2026, che restavano senza
documento. Qui entrano come **debito verso il fornitore** e basta: il
bonifico lo chiude, e nessun conto dell'anno attivo cambia.

Una collezione sola, ``debiti_anno_precedente``::

    {id, fornitore, piva, numero, data, totale_cents, residuo_cents, stato,
     pagamenti: [{movimento_id, data, quota_cents}], drive_file_id, sha256}

Si abbina con le stesse regole delle fatture: identita' del fornitore in
causale (``_fornitore_del_movimento``) e importo al centesimo, da un bonifico
solo o da piu' acconti (``_combinazioni_che_quadrano``); ambiguo = niente.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COLL = "debiti_anno_precedente"
CATEGORIA = "Debiti anno precedente"
CHIAVE_RECUPERO = "debiti_anno_precedente_recupero"
LOTTO_RECUPERO = 100


def _cents(valore: Any) -> int:
    try:
        return int(round(abs(float(valore or 0)) * 100))
    except (TypeError, ValueError):
        return 0


def _piva(valore: Any) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(valore or "").upper()).removeprefix("IT")


def id_debito(parsed: Dict[str, Any]) -> str:
    chiave = "|".join((
        _piva(parsed.get("supplier_vat")),
        str(parsed.get("invoice_number") or "").strip().upper(),
        str(parsed.get("invoice_date") or "")[:10],
    ))
    return "DAP-" + hashlib.sha256(chiave.encode("utf-8")).hexdigest()[:24]


def e_anno_precedente(parsed: Dict[str, Any], anno_attivo: int) -> bool:
    anno = str(parsed.get("invoice_date") or "")[:4]
    return anno.isdigit() and int(anno) == anno_attivo - 1


async def registra(db, parsed: Dict[str, Any], *, drive_file_id: Optional[str] = None,
                   sha256: Optional[str] = None) -> Dict[str, Any]:
    """Il debito della fattura; il secondo import non crea niente."""
    tipo = str(parsed.get("tipo_documento") or "").upper()
    if tipo in {"TD04", "TD08"}:
        # Una nota di credito non e' un debito da pagare.
        return {"registrato": False, "motivo": "nota_di_credito"}
    totale = _cents(parsed.get("total_amount")) - _cents(parsed.get("importo_ritenuta"))
    if totale <= 0 or not _piva(parsed.get("supplier_vat")):
        return {"registrato": False, "motivo": "importo_o_fornitore_assente"}
    debito_id = id_debito(parsed)
    if await db[COLL].find_one({"id": debito_id}, {"_id": 0, "id": 1}):
        return {"registrato": False, "id": debito_id, "gia_presente": True}
    await db[COLL].insert_one({
        "id": debito_id,
        "fornitore": parsed.get("supplier_name"),
        "piva": _piva(parsed.get("supplier_vat")),
        "numero": parsed.get("invoice_number"),
        "data": str(parsed.get("invoice_date") or "")[:10],
        "totale_cents": totale,
        "residuo_cents": totale,
        "stato": "aperto",
        "pagamenti": [],
        "drive_file_id": drive_file_id,
        "sha256": sha256,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"registrato": True, "id": debito_id}


GIORNI_PAGAMENTO = 180


def _entro(data_iso: str) -> str:
    """Ultimo giorno in cui un bonifico puo' pagare la fattura: oltre, un
    importo uguale e' un'altra fattura, non questa."""
    from datetime import date, timedelta

    try:
        return (date.fromisoformat(data_iso) + timedelta(days=GIORNI_PAGAMENTO)).isoformat()
    except ValueError:
        return data_iso


def _come_fattura(debito: Dict[str, Any]) -> Dict[str, Any]:
    """La forma che i riconoscitori del fornitore si aspettano."""
    return {"supplier_name": debito.get("fornitore"), "supplier_vat": debito.get("piva")}


async def _fattura_esiste(db, fattura_id: Any) -> bool:
    if not fattura_id:
        return False
    cercati = [str(fattura_id)] + ([int(fattura_id)] if str(fattura_id).isdigit() else [])
    return bool(await db["invoices"].find_one({"id": {"$in": cercati}}, {"_id": 0, "id": 1}))


def _soluzioni_per_debito(
    debiti: List[Dict[str, Any]], candidati: List[Dict[str, Any]], ricorrenti: Dict[str, set],
) -> List[Any]:
    """Per ogni debito i gruppi di bonifici che lo chiudono al centesimo.
    Calcolo puro, senza I/O: gira fuori dall'event loop (CLAUDE.md, regola 16)."""
    from app.services.bank_payment_allocations import (
        _combinazioni_che_quadrano, _fornitore_del_movimento,
    )
    from app.services.payment_allocation_validator import to_cents

    soluzioni = []
    for debito in debiti:
        fattura = _come_fattura(debito)
        if debito["residuo_cents"] in ricorrenti.get(debito["piva"], set()):
            # Canone o bolletta a importo fisso (Fastweb 43,86, Arval 832,25):
            # lo stesso importo del fornitore c'e' anche fra le fatture di
            # quest'anno, quindi il bonifico paga piu' probabilmente quella.
            # Solo il numero della fattura in causale lo lega al debito vecchio.
            numero = re.sub(r"[^0-9A-Z]", "", str(debito.get("numero") or "").upper())
            suoi_candidati = [
                m for m in candidati
                if len(numero) >= 4 and numero in re.sub(
                    r"[^0-9A-Z]", "", str(m.get("descrizione_originale") or m.get("descrizione") or "").upper())
            ]
        else:
            suoi_candidati = candidati
        suoi = [
            m for m in suoi_candidati
            if debito["data"] <= str(m.get("data") or "")[:10] <= _entro(debito["data"])
            and abs(to_cents(m.get("importo"))) <= debito["residuo_cents"]
            and _fornitore_del_movimento(m, fattura)
        ]
        esatti = [[m] for m in suoi if abs(to_cents(m.get("importo"))) == debito["residuo_cents"]]
        gruppi = esatti or (_combinazioni_che_quadrano(suoi, debito["residuo_cents"]) if len(suoi) <= 12 else [])
        if gruppi:
            soluzioni.append((debito, gruppi))
    return soluzioni


async def abbina_pagamenti(db, *, anno_attivo: Optional[int] = None) -> Dict[str, Any]:
    """Bonifici dell'anno attivo che pagano un debito dell'anno prima."""
    from app.services.bank_payment_allocations import (
        _fornitore_del_movimento, _is_outgoing_invoice_candidate,
    )
    from app.services.payment_allocation_validator import to_cents

    if anno_attivo is None:
        from app.services.config_import import get_anno_importazione_attivo

        anno_attivo = await get_anno_importazione_attivo(db)
    esito: Dict[str, Any] = {"collegati": [], "ambigui": 0}
    debiti = await db[COLL].find({"stato": "aperto"}, {"_id": 0}).to_list(5000)
    if not debiti:
        return esito
    movimenti = await db["estratto_conto_movimenti"].find(
        {"data": {"$regex": f"^{anno_attivo}"},
         "debito_anno_precedente_id": {"$exists": False}},
        {"_id": 0},
    ).to_list(20000)
    candidati = []
    for m in movimenti:
        if m.get("ignorata") or not _is_outgoing_invoice_candidate(m):
            continue
        # Un collegamento a una fattura che non c'e' piu' (le fatture del
        # 2025 tolte il 20/09) non e' un collegamento.
        if m.get("fattura_ids") or (m.get("fattura_id") and await _fattura_esiste(db, m.get("fattura_id"))):
            continue
        # Riconciliato vale solo se lo e' con qualcosa che esiste ancora: il
        # 12.200 di A 2000 era «riconciliato» con una fattura tolta il 20/09.
        if m.get("riconciliato") and not m.get("fattura_id"):
            continue
        candidati.append(m)

    # Importi dell'anno attivo per fornitore: un debito dello stesso importo e'
    # un canone, e l'importo da solo non dice quale mese si sta pagando.
    ricorrenti: Dict[str, set] = {}
    for inv in await db["invoices"].find(
            {"invoice_date": {"$regex": f"^{anno_attivo}"}},
            {"_id": 0, "supplier_vat": 1, "total_amount": 1}).to_list(50000):
        ricorrenti.setdefault(_piva(inv.get("supplier_vat")), set()).add(_cents(inv.get("total_amount")))

    soluzioni = await asyncio.to_thread(_soluzioni_per_debito, debiti, candidati, ricorrenti)

    contesi: Dict[str, int] = {}
    for _debito, gruppi in soluzioni:
        for gruppo in gruppi:
            for m in gruppo:
                contesi[str(m.get("id"))] = contesi.get(str(m.get("id")), 0) + 1
    ora = datetime.now(timezone.utc).isoformat()
    usati: set = set()
    ambigui: List[Dict[str, Any]] = []
    for debito, gruppi in soluzioni:
        gruppo = gruppi[0]
        if len(gruppi) != 1 or any(contesi[str(m.get("id"))] != 1 for m in gruppo):
            ambigui.append(debito)
            continue
        await _chiudi(db, debito, gruppo, ora, esito, to_cents)
        usati.update(str(m.get("id")) for m in gruppo)

    # Debiti uguali dello stesso fornitore (FEP 71_25 e 72_25, 12.200 l'uno):
    # nessun bonifico sa quale dei due paga, ma se i bonifici ancora liberi di
    # quel fornitore fanno al centesimo il totale dei suoi debiti, si
    # ripartiscono in ordine di data e ognuno deve chiudersi esatto.
    per_fornitore: Dict[str, List[Dict[str, Any]]] = {}
    for debito in ambigui:
        per_fornitore.setdefault(debito["piva"], []).append(debito)
    for suoi_debiti in per_fornitore.values():
        suoi_debiti.sort(key=lambda d: (d["data"], str(d.get("numero") or "")))
        fattura = _come_fattura(suoi_debiti[0])
        liberi = sorted(
            (m for m in candidati
             if str(m.get("id")) not in usati and _fornitore_del_movimento(m, fattura)
             and suoi_debiti[0]["data"] <= str(m.get("data") or "")[:10] <= _entro(suoi_debiti[-1]["data"])),
            key=lambda m: (str(m.get("data") or ""), str(m.get("id"))),
        )
        if sum(abs(to_cents(m.get("importo"))) for m in liberi) != sum(d["residuo_cents"] for d in suoi_debiti):
            esito["ambigui"] += len(suoi_debiti)
            continue
        ripartizione = []
        coda = list(liberi)
        for debito in suoi_debiti:
            gruppo, somma = [], 0
            while coda and somma < debito["residuo_cents"]:
                m = coda.pop(0)
                gruppo.append(m)
                somma += abs(to_cents(m.get("importo")))
            if somma != debito["residuo_cents"]:
                ripartizione = None
                break
            ripartizione.append((debito, gruppo))
        if not ripartizione:
            esito["ambigui"] += len(suoi_debiti)
            continue
        for debito, gruppo in ripartizione:
            await _chiudi(db, debito, gruppo, ora, esito, to_cents)
    return esito


async def _chiudi(db, debito, gruppo, ora, esito, to_cents) -> None:
    pagamenti = [
        {"movimento_id": m.get("id"), "data": str(m.get("data") or "")[:10],
         "quota_cents": abs(to_cents(m.get("importo")))}
        for m in gruppo
    ]
    for m in gruppo:
        aggiornamento = {
            "categoria": CATEGORIA,
            "categoria_auto": True,
            "categoria_auto_motivo": f"paga la fattura {debito.get('numero')} del {debito['data']} (anno precedente)",
            "debito_anno_precedente_id": debito["id"],
            "riconciliato": True,
            "stato_riconciliazione": "riconciliato",
            "riconciliato_at": ora,
        }
        if m.get("fattura_id"):
            aggiornamento["fattura_id_orfano"] = m.get("fattura_id")
            aggiornamento["fattura_id"] = None
        await db["estratto_conto_movimenti"].update_one({"id": m.get("id")}, {"$set": aggiornamento})
        await _proietta_prima_nota(db, m, debito, ora, to_cents)
    await db[COLL].update_one({"id": debito["id"]}, {"$set": {
        "residuo_cents": 0, "stato": "pagato", "pagamenti": pagamenti, "pagato_at": ora,
    }})
    esito["collegati"].append({"debito_id": debito["id"], "numero": debito.get("numero"),
                               "movimenti": [p["movimento_id"] for p in pagamenti]})


CONTO_FORNITORI = "33.03.01"


async def _proietta_prima_nota(db, m, debito, ora, to_cents) -> None:
    """Titolare, 28/09/2026: il pagamento entra in Prima Nota Banca, sul conto
    fornitori (33.03.01) e senza costo ne' IVA: e' il debito del 2025 che si
    chiude, e senza questa riga il saldo della banca non torna. Una riga sola
    per movimento: quella che c'e' gia' (import o fattura sparita) si
    completa, mai se ne affianca una seconda."""
    from uuid import uuid4

    from app.services.scritture_contabili import FILTRO_MOVIMENTO_ATTIVO, scrivi_movimento_se_assente

    movimento_id = str(m.get("id") or "")
    descrizione = f"Pagamento fattura {debito.get('numero')} del {debito['data']} (anno precedente)"
    campi = {
        "categoria": CATEGORIA, "category": CATEGORIA,
        "descrizione": descrizione, "description": descrizione,
        "conto_contropartita": CONTO_FORNITORI,
        "debito_anno_precedente_id": debito["id"],
        "fattura_id": None, "invoice_id": None,
        "estratto_conto_id": movimento_id, "movimento_bancario_id": movimento_id,
        "riconciliato": True, "updated_at": ora,
    }
    pn_query = {"$or": [
        {"estratto_conto_id": movimento_id},
        {"movimento_bancario_id": movimento_id},
        {"movimento_estratto_conto_id": movimento_id},
    ]}
    esistenti = await db["prima_nota_banca"].find(
        {"$and": [pn_query, dict(FILTRO_MOVIMENTO_ATTIVO)]}, {"_id": 0, "id": 1}).to_list(10)
    if esistenti:
        for riga in esistenti:
            await db["prima_nota_banca"].update_one({"id": riga["id"]}, {"$set": campi})
        return
    await scrivi_movimento_se_assente(db, "banca", pn_query, {
        "id": str(uuid4()),
        "data": str(m.get("data") or "")[:10],
        "tipo": "uscita",
        "importo": abs(to_cents(m.get("importo"))) / 100,
        "source": "debito_anno_precedente",
        "idempotency_key": f"banca:{movimento_id}:debito_anno_precedente",
        "created_at": ora,
        **campi,
    })


async def recupera_da_drive(db, *, lotto: int = LOTTO_RECUPERO) -> Dict[str, Any]:
    """Rilegge gli XML di fattura gia' smistati in ELABORATE e registra quelli
    dell'anno prima: lo smistatore li scartava senza lasciare traccia. Un
    lotto per volta, ognuno segnato come letto sul registro dello smistatore."""
    from app.parsers.fattura_elettronica_parser import parse_fattura_xml_multi
    from app.services.config_import import get_anno_importazione_attivo
    from app.services.drive_cartella_unica import REGISTRO, _service
    from app.services.drive_download import scarica_bytes

    anno_attivo = await get_anno_importazione_attivo(db)
    righe = await db[REGISTRO].find(
        {"tipo": "fattura", "cartella": "ELABORATE", "letto_debiti_anno_precedente": {"$ne": True}},
        {"_id": 0, "id": 1, "drive_file_id": 1, "nome": 1, "sha256": 1},
    ).to_list(lotto)
    esito = {"letti": 0, "registrati": 0, "errori": 0, "restano": None}
    if not righe:
        esito["restano"] = 0
        return esito
    service = await asyncio.to_thread(_service)
    for riga in righe:
        file_id = riga.get("drive_file_id") or riga.get("id")
        esito["letti"] += 1
        try:
            contenuto = await asyncio.to_thread(scarica_bytes, service, file_id)
            testo = contenuto.decode("utf-8", errors="replace")
            for parsed in parse_fattura_xml_multi(testo):
                if e_anno_precedente(parsed, anno_attivo):
                    r = await registra(db, parsed, drive_file_id=file_id, sha256=riga.get("sha256"))
                    esito["registrati"] += bool(r.get("registrato"))
            segno = {"letto_debiti_anno_precedente": True}
        except Exception as exc:  # noqa: BLE001 - un file illeggibile non ferma il lotto
            esito["errori"] += 1
            logger.warning("Debiti anno precedente: %s non letto (%s: %s)",
                           riga.get("nome"), type(exc).__name__, exc)
            # Segnato comunque, col motivo: un file rotto non si rilegge a
            # ogni giro, e il motivo resta sul registro.
            segno = {"letto_debiti_anno_precedente": True,
                     "errore_debiti_anno_precedente": f"{type(exc).__name__}: {exc}"[:300]}
        await db[REGISTRO].update_one({"id": riga.get("id")}, {"$set": segno})
    esito["restano"] = await db[REGISTRO].count_documents(
        {"tipo": "fattura", "cartella": "ELABORATE", "letto_debiti_anno_precedente": {"$ne": True}})
    return esito
