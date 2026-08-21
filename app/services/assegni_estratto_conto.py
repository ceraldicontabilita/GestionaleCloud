"""Sincronizzazione canonica assegni da movimenti di estratto conto.

Un addebito ``PRELIEVO ASSEGNO ... NUM:`` e' evidenza bancaria reale:
deve creare/aggiornare il registro assegni, lasciare una sola scrittura in
Prima Nota Banca e conservare il collegamento al movimento dell'estratto.
L'associazione a fattura e' automatica solo quando la candidata e' univoca.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.routers.bank.assegni_auto_match import TOLL, _f, _load_open_invoices_by_piva
from app.services.scritture_contabili import scrivi_movimento
from app.services.assegni_fattura_intent import capienza_assegno_fattura
from app.services.payment_allocation_validator import (
    is_credit_note,
    to_cents,
    validate_invoice_allocation,
)
from app.services.accounting_relation_writers import record_check_reconciliation


logger = logging.getLogger(__name__)


_PATTERN_NUMERO = (
    r"\bNUM\s*[:.]?\s*(\d{6,})\b",
    r"\bASSEGNO\s*N[.]?\s*(\d{6,})\b",
    r"\bVOSTRO\s+ASSEGNO\s+(\d{6,})\b",
)


def estrai_numero_assegno(descrizione: str) -> Optional[str]:
    """Restituisce il numero bancario senza convertirlo in intero.

    Gli zeri iniziali sono parte del numero (es. ``0208770981``) e non
    devono essere persi.
    """
    for pattern in _PATTERN_NUMERO:
        match = re.search(pattern, descrizione or "", re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _numero_equivalente(valore: Any, numero: str) -> bool:
    corrente = re.sub(r"\D", "", str(valore or ""))
    atteso = re.sub(r"\D", "", str(numero or ""))
    return bool(corrente and atteso and (corrente == atteso or corrente.endswith(atteso) or atteso.endswith(corrente)))


def _data_iso(valore: Any) -> str:
    testo = str(valore or "")[:10]
    if len(testo) == 10 and testo[4] == "-":
        return testo
    if len(testo) == 10 and testo[2] == "/":
        return f"{testo[6:10]}-{testo[3:5]}-{testo[0:2]}"
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _invoice_ids_assegno(assegno: Dict[str, Any]) -> List[str]:
    ids = []
    for chiave in ("fattura_collegata", "fattura_id"):
        if assegno.get(chiave):
            ids.append(str(assegno[chiave]))
    for link in assegno.get("fatture_collegate") or []:
        if isinstance(link, dict) and link.get("fattura_id"):
            ids.append(str(link["fattura_id"]))
    return list(dict.fromkeys(ids))


def _invoice_date_compatibile(fattura: Dict[str, Any], data_movimento: str) -> bool:
    data_fattura = str(fattura.get("invoice_date") or fattura.get("data_fattura") or "")[:10]
    try:
        d_mov = datetime.fromisoformat(data_movimento[:10])
        d_fatt = datetime.fromisoformat(data_fattura)
    except (TypeError, ValueError):
        return True
    return d_mov - timedelta(days=550) <= d_fatt <= d_mov + timedelta(days=7)


async def _fattura_da_prima_nota(db, numero: str, importo: float) -> Optional[Dict[str, Any]]:
    cursor = db["prima_nota_banca"].find({
        "importo": {"$gte": importo - TOLL, "$lte": importo + TOLL},
        "status": {"$nin": ["deleted", "archived"]},
    }, {"_id": 0})
    righe = await cursor.to_list(500)
    con_fattura = [r for r in righe if r.get("invoice_id") or r.get("fattura_id")]
    per_numero = [r for r in con_fattura if any(
        _numero_equivalente(r.get(k), numero)
        for k in ("assegno_numero", "numero_assegno", "description", "descrizione")
    )]
    candidati = per_numero or con_fattura
    ids = list(dict.fromkeys(str(r.get("invoice_id") or r.get("fattura_id")) for r in candidati))
    if len(ids) != 1:
        return None
    return await db["invoices"].find_one({"id": ids[0]}, {"_id": 0})


async def _fattura_da_numero_assegno_xml(
    db, numero: str, importo: float, data_movimento: str,
    per_piva: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Optional[Dict[str, Any]]:
    """Trova la fattura che dichiara lo stesso assegno e la stessa quota.

    E' una prova forte anche quando il registro carnet non esiste ancora:
    numero assegno nell'XML + importo al centesimo + data compatibile.
    """
    if per_piva is None:
        per_piva = await _load_open_invoices_by_piva(db)
    candidate: List[Dict[str, Any]] = []
    for fatture in per_piva.values():
        for fattura in fatture:
            if not _invoice_date_compatibile(fattura, data_movimento):
                continue
            metodo = " ".join(str(fattura.get(campo) or "") for campo in (
                "metodo_pagamento", "payment_method", "modalita_pagamento",
                "metodo_pagamento_previsto",
            ))
            numero_xml = estrai_numero_assegno(metodo)
            if not numero_xml or not _numero_equivalente(numero_xml, numero):
                continue
            residuo_ok = abs(_f(fattura.get("_residuo")) - importo) <= TOLL
            rata_ok = any(
                abs(_f(rata.get("importo")) - importo) <= TOLL
                for rata in (fattura.get("pagamento_rate") or [])
                if isinstance(rata, dict)
            )
            if residuo_ok or rata_ok:
                candidate.append(fattura)
    uniche = {str(f.get("id")): f for f in candidate if f.get("id")}
    return next(iter(uniche.values())) if len(uniche) == 1 else None


async def _fatture_aperte_stesso_importo(
    db, importo: float, data_movimento: str,
    per_piva: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    if per_piva is None:
        per_piva = await _load_open_invoices_by_piva(db)
    candidate = []
    for fatture in per_piva.values():
        for fattura in fatture:
            if not _invoice_date_compatibile(fattura, data_movimento):
                continue
            residuo_esatto = abs(_f(fattura.get("_residuo")) - importo) <= TOLL
            # Una fattura rateizzata resta candidata anche se il suo residuo e'
            # maggiore del singolo assegno: la prova e' il DettaglioPagamento
            # XML, non il totale documento. Ogni quota gia collegata consuma
            # una rata dello stesso importo.
            rate = [
                round(_f(r.get("importo")), 2)
                for r in fattura.get("pagamento_rate") or []
                if isinstance(r, dict)
            ]
            rate_compatibili = sum(1 for rata in rate if abs(rata - importo) <= TOLL)
            quote_collegate = sum(
                1 for link in fattura.get("assegni_collegati") or []
                if isinstance(link, dict) and abs(_f(link.get("quota")) - importo) <= TOLL
            )
            rata_disponibile = rate_compatibili > quote_collegate
            if residuo_esatto or rata_disponibile:
                candidate.append(fattura)
    # Una stessa fattura non deve diventare ambigua per dati duplicati in memoria.
    return list({str(f["id"]): f for f in candidate if f.get("id")}.values())


async def _registra_proposte_ambigue(
    db, assegno: Dict[str, Any], candidate: Iterable[Dict[str, Any]], now: str,
) -> int:
    count = 0
    for fattura in candidate:
        fid = fattura.get("id")
        if not fid:
            continue
        doc = {
            "id": f"EC-{assegno['id']}-{fid}",
            "assegno_id": assegno["id"],
            "assegno_numero": assegno.get("numero"),
            "fattura_id": fid,
            "fattura_numero": fattura.get("invoice_number") or fattura.get("numero_fattura"),
            "fornitore": fattura.get("supplier_name") or fattura.get("cedente_denominazione"),
            "importo": round(_f(assegno.get("importo")), 2),
            "tipo_match": "estratto_conto_importo_ambiguo",
            "confidenza": 0.5,
            "nota": (
                "Importo compatibile ma manca un riferimento esplicito alla fattura: "
                "conferma manuale necessaria"
            ),
            "stato": "da_confermare",
            "source": "estratto_conto",
            "created_at": now,
        }
        await db["proposte_associazione_assegni"].update_one(
            {"assegno_id": assegno["id"], "fattura_id": fid}, {"$set": doc}, upsert=True,
        )
        count += 1
    return count


async def _collega_fattura_univoca(
    db,
    assegno: Dict[str, Any],
    fattura: Dict[str, Any],
    data_movimento: str,
    now: str,
    quota_override: Optional[float] = None,
    aggiorna_assegno: bool = True,
) -> bool:
    fid = fattura.get("id")
    if not fid:
        return False
    importo = round(_f(quota_override if quota_override is not None else assegno.get("importo")), 2)
    if is_credit_note(fattura):
        return False
    esito_allocazione = validate_invoice_allocation(
        fattura, to_cents(importo),
        allocation_id=str(assegno.get("id") or ""),
    )
    totale = round(_f(fattura.get("total_amount") or fattura.get("importo_totale")), 2)
    pagato = round(_f(fattura.get("importo_pagato")), 2)
    link_esistente = next((
        link for link in (fattura.get("assegni_collegati") or [])
        if isinstance(link, dict) and str(link.get("assegno_id")) == str(assegno["id"])
    ), None)
    pagamento_gia_applicato = bool(link_esistente and link_esistente.get("banca_confermata"))
    if not pagamento_gia_applicato and not esito_allocazione["allowed"]:
        return False
    if not pagamento_gia_applicato:
        disponibile, _, _ = capienza_assegno_fattura(
            fattura, assegno.get("id"), importo,
        )
        if not disponibile:
            return False

    link = {
        "assegno_id": assegno["id"], "numero": assegno.get("numero"),
        "quota": importo, "data_collegamento": now, "match_auto": True,
        "match_livello": "EC_UNIVOCO", "banca_confermata": True,
    }
    update_fattura: Dict[str, Any] = {
        "metodo_pagamento_effettivo": "assegno",
        "data_ultimo_incasso_assegno": data_movimento,
        "updated_at": now,
    }
    # Se l'associazione viene scelta dopo che l'addebito e' gia' arrivato in
    # banca, la quota va applicata adesso. L'idempotenza dipende dal numero/id
    # dell'assegno gia' presente nei link della fattura, non dal solo stato
    # "incassato": due assegni distinti dello stesso importo sono due quote.
    if not pagamento_gia_applicato:
        nuovo_pagato = round(min(totale, pagato + importo), 2)
        update_fattura.update({
            "importo_pagato": nuovo_pagato,
            "importo_residuo": round(max(0.0, totale - nuovo_pagato), 2),
            "payment_status": "paid" if abs(nuovo_pagato - totale) <= TOLL else "partial",
            "pagato": abs(nuovo_pagato - totale) <= TOLL,
        })
        update_doc: Dict[str, Any] = {
            "$set": update_fattura,
            "$pull": {"assegni_collegati": {"assegno_id": assegno["id"]}},
        }
        await db["invoices"].update_one({"id": fid}, update_doc)
        await db["invoices"].update_one(
            {"id": fid}, {"$addToSet": {"assegni_collegati": link}},
        )
        from app.services.scadenze_rate_service import applica_quota_scadenze
        await applica_quota_scadenze(
            db, fattura_id=fid, quota=importo,
            evidenza_id=f"assegno:{assegno['id']}:{fid}", metodo="assegno",
            data_pagamento=data_movimento,
        )
    else:
        await db["invoices"].update_one({"id": fid}, {"$set": update_fattura})

    if aggiorna_assegno:
        await db["assegni"].update_one(
            {"id": assegno["id"]},
            {"$set": {
                "fattura_collegata": fid, "fattura_id": fid,
                "fatture_collegate": [{
                    "fattura_id": fid, "quota": importo, "data_collegamento": now,
                    "match_auto": True, "match_livello": "EC_UNIVOCO",
                    "banca_confermata": True,
                }],
                "numero_fattura": fattura.get("invoice_number") or fattura.get("numero_fattura"),
                "fornitore_piva": fattura.get("supplier_vat") or fattura.get("partita_iva"),
                "fornitore_ragione_sociale": fattura.get("supplier_name") or fattura.get("cedente_denominazione"),
                "beneficiario": assegno.get("beneficiario") or fattura.get("supplier_name") or fattura.get("cedente_denominazione"),
                "importo_assegnato": importo, "match_auto": True,
                "match_livello": "EC_UNIVOCO", "updated_at": now,
            }},
        )
    return not pagamento_gia_applicato


async def collega_assegno_riconciliato_a_fattura(
    db,
    assegno: Dict[str, Any],
    fattura: Dict[str, Any],
    *,
    match_auto: bool = False,
    match_livello: str = "MANUAL_EC",
) -> Dict[str, Any]:
    """Completa un collegamento manuale quando l'assegno e' gia' in banca.

    Mantiene distinto ogni assegno tramite ``assegno.id``/``numero`` e
    aggiorna fattura, Prima Nota e movimento di estratto conto senza creare
    una seconda riga bancaria.
    """
    return await collega_assegno_riconciliato_a_fatture(
        db,
        assegno,
        [{"fattura": fattura, "quota": round(_f(assegno.get("importo")), 2)}],
        match_auto=match_auto,
        match_livello=match_livello,
    )


async def collega_assegno_riconciliato_a_fatture(
    db,
    assegno: Dict[str, Any],
    collegamenti: List[Dict[str, Any]],
    *,
    match_auto: bool = False,
    match_livello: str = "MANUAL_EC",
) -> Dict[str, Any]:
    """Applica uno o piu' collegamenti espliciti a un assegno gia' addebitato.

    La somma delle quote deve coincidere al centesimo con l'assegno; ogni
    fattura conserva numero e quota, mentre il movimento banca rimane uno.
    """
    movimento_id = assegno.get("movimento_estratto_conto_id") or assegno.get("movimento_id")
    if not movimento_id:
        raise ValueError("L'assegno non ha un movimento di estratto conto collegato")
    movimento = await db["estratto_conto_movimenti"].find_one(
        {"id": movimento_id}, {"_id": 0}
    )
    if not movimento:
        raise ValueError("Movimento di estratto conto dell'assegno non trovato")

    if not collegamenti:
        raise ValueError("Indicare almeno una fattura")
    importo_assegno = round(_f(assegno.get("importo")), 2)
    totale_quote = round(sum(_f(item.get("quota")) for item in collegamenti), 2)
    if abs(totale_quote - importo_assegno) > TOLL:
        raise ValueError("La somma delle fatture deve coincidere al centesimo con l'assegno")

    # Gate canonico prima di qualsiasi scrittura: una fattura non può essere
    # sovra-attribuita e una nota di credito non è una destinazione di denaro.
    richieste_per_fattura: Dict[str, int] = {}
    fatture_per_id: Dict[str, Dict[str, Any]] = {}
    for item in collegamenti:
        fattura = item.get("fattura") or {}
        fid = str(fattura.get("id") or "")
        quota_cents = to_cents(item.get("quota"))
        if not fid or quota_cents == 0:
            raise ValueError("Fattura o quota non valida")
        fatture_per_id[fid] = fattura
        if quota_cents > 0:
            richieste_per_fattura[fid] = richieste_per_fattura.get(fid, 0) + quota_cents
            if is_credit_note(fattura):
                raise ValueError("Una nota di credito non può essere pagata con un assegno")
    for fid, quota_cents in richieste_per_fattura.items():
        esito = validate_invoice_allocation(
            fatture_per_id[fid], quota_cents,
            allocation_id=str(assegno.get("id") or ""),
        )
        if not esito["allowed"]:
            raise ValueError(
                f"Allocazione rifiutata per {fid}: {esito['reason']} "
                f"(residuo EUR {esito['residual_cents'] / 100:.2f})"
            )

    now = datetime.now(timezone.utc).isoformat()
    data_movimento = _data_iso(movimento.get("data") or assegno.get("data_incasso"))
    links = []
    applicate = 0
    for item in collegamenti:
        fattura = item.get("fattura") or {}
        fattura_id = str(fattura.get("id") or "")
        quota = round(_f(item.get("quota")), 2)
        if not fattura_id or abs(quota) <= TOLL:
            raise ValueError("Fattura o quota non valida")
        if quota > 0:
            applicata = await _collega_fattura_univoca(
                db, assegno, fattura, data_movimento, now,
                quota_override=quota, aggiorna_assegno=False,
            )
        else:
            # La nota di credito netta il debito ma non e' un'ulteriore
            # uscita bancaria. La si marca applicata allo stesso assegno
            # senza sommare il valore negativo ai pagamenti monetari.
            vecchio = next((
                link for link in (fattura.get("assegni_collegati") or [])
                if isinstance(link, dict)
                and str(link.get("assegno_id")) == str(assegno["id"])
                and link.get("banca_confermata")
            ), None)
            applicata = not bool(vecchio)
            await db["invoices"].update_one(
                {"id": fattura_id},
                {"$pull": {"assegni_collegati": {"assegno_id": assegno["id"]}}},
            )
            await db["invoices"].update_one(
                {"id": fattura_id},
                {"$addToSet": {"assegni_collegati": {
                    "assegno_id": assegno["id"], "numero": assegno.get("numero"),
                    "quota": quota, "data_collegamento": now, "match_auto": match_auto,
                    "match_livello": match_livello, "banca_confermata": True,
                }}},
            )
        applicate += int(applicata)
        links.append({
            "fattura_id": fattura_id,
            "quota": quota,
            "data_collegamento": now,
            "match_auto": match_auto,
            "match_livello": match_livello,
            "banca_confermata": True,
            "numero_fattura": fattura.get("invoice_number") or fattura.get("numero_fattura"),
        })

    fattura_ids = [link["fattura_id"] for link in links]
    singola_id = fattura_ids[0] if len(fattura_ids) == 1 else None
    await db["assegni"].update_one({"id": assegno["id"]}, {"$set": {
        "fatture_collegate": links,
        "fattura_collegata": singola_id,
        "fattura_id": singola_id,
        "numero_fattura": ", ".join(filter(None, (l.get("numero_fattura") for l in links))),
        "importo_assegnato": totale_quote,
        "stato": "incassato",
        "stato_finanziario": "riconciliato",
        "match_auto": match_auto,
        "match_livello": match_livello,
        "updated_at": now,
    }})
    assegno_aggiornato = await db["assegni"].find_one({"id": assegno["id"]}, {"_id": 0}) or assegno
    pn_id = await _garantisci_prima_nota(
        db, assegno_aggiornato, movimento, singola_id, now,
    )
    for fattura_id in fattura_ids:
        await db["invoices"].update_one({"id": fattura_id}, {"$set": {
            "riconciliato": True,
            "riconciliato_con_ec": True,
            "stato_finanziario": "riconciliato",
            "movimento_bancario_id": movimento_id,
            "prima_nota_id": pn_id,
            "prima_nota_banca_id": pn_id,
            "prima_nota_tipo": "banca",
            "data_riconciliazione": data_movimento,
            "updated_at": now,
        }})
    if len(fattura_ids) > 1:
        await db["prima_nota_banca"].update_one({"id": pn_id}, {"$set": {
            "fattura_ids": fattura_ids,
            "fatture_collegate": links,
            "invoice_id": None,
            "fattura_id": None,
        }})
    await db["estratto_conto_movimenti"].update_one({"id": movimento_id}, {"$set": {
        "riconciliato": True,
        "riconciliato_con": "assegno",
        "assegno_id": assegno["id"],
        "assegno_numero": assegno.get("numero"),
        "prima_nota_banca_id": pn_id,
        "fattura_id": singola_id,
        "fattura_ids": fattura_ids,
        "riconciliato_at": now,
    }})
    await db["proposte_associazione_assegni"].update_many(
        {"assegno_id": assegno["id"]},
        {"$set": {
            "stato": "confermata",
            "fattura_confermata_id": singola_id,
            "fatture_confermate_ids": fattura_ids,
            "confirmed_at": now,
        }},
    )
    try:
        await record_check_reconciliation(
            db,
            cheque=assegno_aggiornato,
            movement=movimento,
            invoice_links=links,
        )
    except Exception:
        logger.exception(
            "Errore registrazione relazioni per assegno %s",
            assegno.get("id"),
        )
    return {
        "collegato": bool(applicate),
        "quote_applicate": applicate,
        "assegno_id": assegno["id"],
        "assegno_numero": assegno.get("numero"),
        "fattura_id": singola_id,
        "fattura_ids": fattura_ids,
        "prima_nota_banca_id": pn_id,
    }


async def _garantisci_prima_nota(
    db, assegno: Dict[str, Any], movimento: Dict[str, Any], fattura_id: Optional[str], now: str,
) -> str:
    ec_id = movimento.get("id")
    esistente = await db["prima_nota_banca"].find_one({
        "$or": [
            {"movimento_estratto_conto_id": ec_id}, {"estratto_conto_id": ec_id},
            {"assegno_id": assegno["id"]},
        ],
        "status": {"$nin": ["deleted", "archived"]},
    }, {"_id": 0})
    fields = {
        "tipo": "uscita", "type": "uscita", "importo": round(_f(assegno.get("importo")), 2),
        "amount": round(_f(assegno.get("importo")), 2), "categoria": "Assegni",
        "category": "Assegni", "assegno_id": assegno["id"],
        "assegno_numero": assegno.get("numero"), "numero_assegno": assegno.get("numero"),
        "estratto_conto_id": ec_id, "movimento_estratto_conto_id": ec_id,
        "riconciliato": True, "data_riconciliazione": _data_iso(movimento.get("data")),
        "updated_at": now,
    }
    if fattura_id:
        fields.update({"invoice_id": fattura_id, "fattura_id": fattura_id})
    if esistente:
        await db["prima_nota_banca"].update_one({"id": esistente["id"]}, {"$set": fields})
        return esistente["id"]
    return await scrivi_movimento(db, "banca", {
        **fields,
        "id": str(uuid.uuid4()), "data": _data_iso(movimento.get("data")),
        "descrizione": f"Assegno n. {assegno.get('numero', '')} - riscontro estratto conto",
        "source": "assegno_estratto_conto", "created_at": now,
    })


async def sincronizza_assegni_da_estratto_conto(
    db,
    movimento_ids: Optional[List[str]] = None,
    data_dal: Optional[str] = None,
    include_provvisori: bool = False,
) -> Dict[str, Any]:
    from app.services.bank_evidence import filtro_solo_evidenza_ufficiale
    risultati: Dict[str, Any] = {
        "movimenti_analizzati": 0, "assegni_trovati": 0, "assegni_creati": 0,
        "assegni_esistenti": 0, "assegni_riconciliati": 0,
        "fatture_associate": 0, "proposte_ambigue": 0, "errori": [], "dettagli": [],
    }
    filtri_movimenti: List[Dict[str, Any]] = [
            {"$or": [
                {"descrizione": {"$regex": "PRELIEVO.*ASSEGNO", "$options": "i"}},
                {"descrizione_originale": {"$regex": "PRELIEVO.*ASSEGNO", "$options": "i"}},
                {"descrizione": {"$regex": "VOSTRO.*ASSEGNO", "$options": "i"}},
                {"descrizione_originale": {"$regex": "VOSTRO.*ASSEGNO", "$options": "i"}},
            ]},
            {"$or": [{"tipo": "uscita"}, {"type": "uscita"}, {"importo": {"$lt": 0}}]},
    ]
    if not include_provvisori:
        filtri_movimenti.insert(0, filtro_solo_evidenza_ufficiale())
    else:
        risultati["include_provvisori"] = True
    ids_richiesti = list(dict.fromkeys(
        str(movimento_id).strip()
        for movimento_id in (movimento_ids or [])
        if str(movimento_id).strip()
    ))
    if movimento_ids is not None:
        risultati["ambito"] = "nuovi_movimenti"
        if not ids_richiesti:
            return risultati
        filtri_movimenti.append({"id": {"$in": ids_richiesti}})
    else:
        risultati["ambito"] = "completo"
    if data_dal:
        filtri_movimenti.append({"data": {"$gte": str(data_dal)}})
        risultati["data_dal"] = str(data_dal)

    movimenti = await db["estratto_conto_movimenti"].find(
        {"$and": filtri_movimenti}, {"_id": 0},
    ).to_list(10000)
    movimenti = [
        movimento for movimento in movimenti
        if "RILASCIO CARNET" not in (
            movimento.get("descrizione") or movimento.get("descrizione_originale") or ""
        ).upper()
    ]
    risultati["movimenti_analizzati"] = len(movimenti)

    # Snapshot unica per tutta la run. Prima le fatture aperte venivano
    # rilette dal registro fino a due volte per ogni assegno, lasciando il
    # riprocessamento live bloccato per minuti sullo storico reale.
    fatture_aperte_per_piva = await _load_open_invoices_by_piva(db) if movimenti else {}

    for movimento in movimenti:
        try:
            descrizione = movimento.get("descrizione") or movimento.get("descrizione_originale") or ""
            numero = estrai_numero_assegno(descrizione)
            if not numero:
                risultati["errori"].append(f"Numero assegno non riconosciuto nel movimento {movimento.get('id')}")
                continue
            risultati["assegni_trovati"] += 1
            now = datetime.now(timezone.utc).isoformat()
            data_movimento = _data_iso(movimento.get("data") or movimento.get("data_pagamento"))
            importo = round(abs(_f(movimento.get("importo"))), 2)
            assegno = await db["assegni"].find_one({
                "$or": [
                    {"numero": numero}, {"assegno_numero": numero},
                    {"movimento_id": movimento.get("id")},
                    {"movimento_estratto_conto_id": movimento.get("id")},
                ]
            }, {"_id": 0})
            if assegno:
                risultati["assegni_esistenti"] += 1
            else:
                assegno = {
                    "id": str(uuid.uuid4()), "numero": numero, "importo": importo,
                    "data": data_movimento, "data_emissione": data_movimento,
                    "descrizione": descrizione, "movimento_id": movimento.get("id"),
                    "fonte": "estratto_conto", "banca": movimento.get("banca"),
                    "created_at": now, "updated_at": now,
                    "livello_evidenza_bancaria": movimento.get("livello_evidenza") or "legacy",
                    "evidenza_bancaria_ufficiale": bool(
                        movimento.get("evidenza_bancaria_ufficiale")
                        or movimento.get("livello_evidenza") in (None, "ufficiale")
                    ),
                }
                await db["assegni"].insert_one(dict(assegno))
                risultati["assegni_creati"] += 1

            fattura_ids = _invoice_ids_assegno(assegno)
            fattura = None
            if fattura_ids:
                fattura = await db["invoices"].find_one({"id": fattura_ids[0]}, {"_id": 0})
            if not fattura:
                fattura = await _fattura_da_prima_nota(db, numero, importo)
            if not fattura:
                fattura = await _fattura_da_numero_assegno_xml(
                    db, numero, importo, data_movimento, fatture_aperte_per_piva,
                )
            if not fattura:
                candidate = await _fatture_aperte_stesso_importo(
                    db, importo, data_movimento, fatture_aperte_per_piva,
                )
                # L'importo, anche se individua una sola fattura aperta, non e'
                # prova sufficiente. Il collegamento automatico richiede un
                # intento assegno->fattura gia' esplicito oppure una Prima Nota
                # gia' collegata; qui si salvano soltanto proposte da confermare.
                if candidate:
                    risultati["proposte_ambigue"] += await _registra_proposte_ambigue(db, assegno, candidate, now)

            nuova_associazione = False
            if fattura:
                nuova_associazione = await _collega_fattura_univoca(db, assegno, fattura, data_movimento, now)
                if nuova_associazione:
                    risultati["fatture_associate"] += 1
                assegno = await db["assegni"].find_one({"id": assegno["id"]}, {"_id": 0}) or assegno

            fattura_id = (_invoice_ids_assegno(assegno) or [None])[0]
            pn_id = await _garantisci_prima_nota(db, assegno, movimento, fattura_id, now)
            if fattura_id:
                await db["invoices"].update_one({"id": fattura_id}, {"$set": {
                    "riconciliato": True,
                    "riconciliato_con_ec": True,
                    "stato_finanziario": "riconciliato",
                    "movimento_bancario_id": movimento.get("id"),
                    "prima_nota_id": pn_id,
                    "prima_nota_banca_id": pn_id,
                    "prima_nota_tipo": "banca",
                    "data_riconciliazione": data_movimento,
                    "updated_at": now,
                }})
            await db["assegni"].update_one({"id": assegno["id"]}, {"$set": {
                "stato": "incassato", "data_incasso": data_movimento,
                "incassato_confermato_banca": True,
                "stato_finanziario": "riconciliato",
                "movimento_estratto_conto_id": movimento.get("id"),
                "prima_nota_banca_id": pn_id, "confermato": True, "updated_at": now,
            }})
            await db["estratto_conto_movimenti"].update_one({"id": movimento.get("id")}, {"$set": {
                "riconciliato": True, "riconciliato_con": "assegno",
                "assegno_id": assegno["id"], "assegno_numero": numero,
                "prima_nota_banca_id": pn_id, "fattura_id": fattura_id,
                "riconciliato_at": now,
            }})
            risultati["assegni_riconciliati"] += 1
            risultati["dettagli"].append({
                "numero": numero, "importo": importo, "data": data_movimento,
                "fattura_id": fattura_id, "movimento_estratto_conto_id": movimento.get("id"),
            })
        except Exception as exc:  # un movimento difettoso non blocca tutto il file
            risultati["errori"].append(f"Movimento {movimento.get('id')}: {exc}")
    return risultati
