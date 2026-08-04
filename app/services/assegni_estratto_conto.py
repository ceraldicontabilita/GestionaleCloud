"""Sincronizzazione canonica assegni da movimenti di estratto conto.

Un addebito ``PRELIEVO ASSEGNO ... NUM:`` e' evidenza bancaria reale:
deve creare/aggiornare il registro assegni, lasciare una sola scrittura in
Prima Nota Banca e conservare il collegamento al movimento dell'estratto.
L'associazione a fattura e' automatica solo quando la candidata e' univoca.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.routers.bank.assegni_auto_match import TOLL, _f, _load_open_invoices_by_piva
from app.services.scritture_contabili import scrivi_movimento


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


async def _fatture_aperte_stesso_importo(db, importo: float, data_movimento: str) -> List[Dict[str, Any]]:
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
            "nota": "Importo assegno compatibile con piu fatture: conferma manuale necessaria",
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
    db, assegno: Dict[str, Any], fattura: Dict[str, Any], data_movimento: str, now: str,
) -> bool:
    fid = fattura.get("id")
    if not fid:
        return False
    importo = round(_f(assegno.get("importo")), 2)
    totale = round(_f(fattura.get("total_amount") or fattura.get("importo_totale")), 2)
    pagato = round(_f(fattura.get("importo_pagato")), 2)
    residuo = round(max(0.0, totale - pagato), 2)
    gia_collegato = any(
        isinstance(link, dict) and str(link.get("assegno_id")) == str(assegno["id"])
        for link in fattura.get("assegni_collegati") or []
    )
    pagamento_gia_confermato = bool(assegno.get("incassato_confermato_banca"))
    if not gia_collegato and importo - residuo > TOLL and not fattura.get("pagato"):
        return False

    link = {
        "assegno_id": assegno["id"], "numero": assegno.get("numero"),
        "quota": importo, "data_collegamento": now, "match_auto": True,
        "match_livello": "EC_UNIVOCO",
    }
    update_fattura: Dict[str, Any] = {
        "metodo_pagamento_effettivo": "assegno",
        "data_ultimo_incasso_assegno": data_movimento,
        "updated_at": now,
    }
    if not pagamento_gia_confermato:
        nuovo_pagato = round(min(totale, pagato + importo), 2)
        update_fattura.update({
            "importo_pagato": nuovo_pagato,
            "importo_residuo": round(max(0.0, totale - nuovo_pagato), 2),
            "payment_status": "paid" if abs(nuovo_pagato - totale) <= TOLL else "partial",
            "pagato": abs(nuovo_pagato - totale) <= TOLL,
        })
        update_doc: Dict[str, Any] = {"$set": update_fattura}
        if not gia_collegato:
            update_doc["$addToSet"] = {"assegni_collegati": link}
        await db["invoices"].update_one({"id": fid}, update_doc)
        from app.services.scadenze_rate_service import applica_quota_scadenze
        await applica_quota_scadenze(
            db, fattura_id=fid, quota=importo,
            evidenza_id=f"assegno:{assegno['id']}:{fid}", metodo="assegno",
            data_pagamento=data_movimento,
        )
    else:
        await db["invoices"].update_one({"id": fid}, {"$set": update_fattura})

    await db["assegni"].update_one(
        {"id": assegno["id"]},
        {"$set": {
            "fattura_collegata": fid, "fattura_id": fid,
            "fatture_collegate": [{
                "fattura_id": fid, "quota": importo, "data_collegamento": now,
                "match_auto": True, "match_livello": "EC_UNIVOCO",
            }],
            "numero_fattura": fattura.get("invoice_number") or fattura.get("numero_fattura"),
            "fornitore_piva": fattura.get("supplier_vat") or fattura.get("partita_iva"),
            "fornitore_ragione_sociale": fattura.get("supplier_name") or fattura.get("cedente_denominazione"),
            "beneficiario": assegno.get("beneficiario") or fattura.get("supplier_name") or fattura.get("cedente_denominazione"),
            "importo_assegnato": importo, "match_auto": True,
            "match_livello": "EC_UNIVOCO", "updated_at": now,
        }},
    )
    return not pagamento_gia_confermato


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


async def sincronizza_assegni_da_estratto_conto(db) -> Dict[str, Any]:
    risultati: Dict[str, Any] = {
        "movimenti_analizzati": 0, "assegni_trovati": 0, "assegni_creati": 0,
        "assegni_esistenti": 0, "assegni_riconciliati": 0,
        "fatture_associate": 0, "proposte_ambigue": 0, "errori": [], "dettagli": [],
    }
    movimenti = await db["estratto_conto_movimenti"].find({
        "$and": [
            {"$or": [
                {"descrizione": {"$regex": "PRELIEVO.*ASSEGNO", "$options": "i"}},
                {"descrizione_originale": {"$regex": "PRELIEVO.*ASSEGNO", "$options": "i"}},
                {"descrizione": {"$regex": "VOSTRO.*ASSEGNO", "$options": "i"}},
                {"descrizione_originale": {"$regex": "VOSTRO.*ASSEGNO", "$options": "i"}},
            ]},
            {"$or": [{"tipo": "uscita"}, {"type": "uscita"}, {"importo": {"$lt": 0}}]},
        ]
    }, {"_id": 0}).to_list(10000)
    movimenti = [
        movimento for movimento in movimenti
        if "RILASCIO CARNET" not in (
            movimento.get("descrizione") or movimento.get("descrizione_originale") or ""
        ).upper()
    ]
    risultati["movimenti_analizzati"] = len(movimenti)

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
                candidate = await _fatture_aperte_stesso_importo(db, importo, data_movimento)
                if len(candidate) == 1:
                    fattura = candidate[0]
                elif len(candidate) > 1:
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
