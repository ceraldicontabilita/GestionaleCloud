"""Import sicuro dei PDF bonifico e associazione ai cedolini.

Regola canonica: un PDF bonifico viene collegato a una riga stipendio solo
quando l'identita' del dipendente e l'importo al centesimo coincidono. In
caso di zero o piu' candidati il documento resta da verificare: nessuna
scelta per vicinanza, ordine del database o semplice mese.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.routers.bonifici_module.common import build_dedup_key
from app.routers.bonifici_module.pdf_parser import (
    extract_filename_metadata,
    extract_transfers_from_text,
    read_pdf_bytes,
)

logger = logging.getLogger(__name__)


def nome_tokens(nome: str) -> frozenset[str]:
    """Token identita' accent-insensitive, senza parole bancarie."""
    text = (nome or "").casefold()
    tokens = re.findall(r"[a-zà-ÿ']+", text)
    stop = {
        "beneficiario", "ordinante", "bonifico", "stipendio", "emolumenti",
        "mensilita", "pagamento", "favore", "copia",
    }
    return frozenset(t for t in tokens if len(t) > 1 and t not in stop)


def identita_coincide(nome_a: str, nome_b: str) -> bool:
    """Richiede lo stesso nome completo (almeno nome+cognome)."""
    a, b = nome_tokens(nome_a), nome_tokens(nome_b)
    return len(a) >= 2 and a == b


def nome_presente_nel_testo(nome: str, testo: str) -> bool:
    """Vero se tutti i token del nome completo compaiono nella causale."""
    identita = nome_tokens(nome)
    testo_tokens = nome_tokens(testo)
    return len(identita) >= 2 and identita.issubset(testo_tokens)


def importo_residuo_salario(riga: Dict[str, Any]) -> float:
    busta = float(riga.get("importo_busta") or riga.get("importo") or 0)
    # Il PDF documenta la disposizione, mentre `importo_bonifico` deriva
    # dall'estratto conto. Sono due prove dello stesso pagamento: non vanno
    # sommate. Per accettare acconti successivi si sottrae la prova piu'
    # completa gia' disponibile.
    documentato = float(riga.get("importo_bonifico_documentato") or 0)
    riconciliato = float(riga.get("importo_bonifico") or 0)
    return round(max(0.0, busta - max(documentato, riconciliato)), 2)


def _nome_salario(riga: Dict[str, Any]) -> str:
    return (
        riga.get("dipendente_nome")
        or riga.get("dipendente")
        or riga.get("nome_dipendente")
        or ""
    ).strip()


def data_pagamento_compatibile(data_pagamento: Any, riga: Dict[str, Any]) -> bool:
    """Verifica la normale finestra paga: dal 20 al 15 del mese seguente."""
    try:
        data = datetime.fromisoformat(str(data_pagamento)[:10])
        mese = int(riga.get("mese") or 0)
        anno = int(riga.get("anno") or 0)
        if not 1 <= mese <= 12:
            return False
        inizio = datetime(anno, mese, 20)
        fine = datetime(anno + 1, 1, 15) if mese == 12 else datetime(anno, mese + 1, 15)
        return inizio <= data <= fine
    except (TypeError, ValueError):
        return False


def causale_contraddice_beneficiario(
    bonifico: Dict[str, Any], righe: Iterable[Dict[str, Any]]
) -> bool:
    """Blocca il match se la causale nomina chiaramente un altro dipendente.

    Nei documenti reali puo' capitare che il beneficiario bancario sia una
    persona ma la causale riporti il nome completo di un'altra. In quel caso
    il documento resta da verificare: non si sceglie ne' il beneficiario ne'
    la causale in modo arbitrario.
    """
    beneficiario = bonifico.get("beneficiario") or {}
    identita_beneficiario = nome_tokens(
        beneficiario.get("nome") or bonifico.get("dipendente_nome") or ""
    )
    causale = bonifico.get("causale") or ""
    if len(identita_beneficiario) < 2 or not causale:
        return False

    identita_viste = set()
    for riga in righe:
        identita = nome_tokens(_nome_salario(riga))
        if len(identita) < 2 or identita in identita_viste:
            continue
        identita_viste.add(identita)
        if identita != identita_beneficiario and nome_presente_nel_testo(
            _nome_salario(riga), causale
        ):
            return True
    return False


def seleziona_salario_univoco(
    bonifico: Dict[str, Any], righe: Iterable[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Seleziona un solo candidato per identita', periodo e importo nel residuo."""
    righe = list(righe)
    importo = round(abs(float(bonifico.get("importo") or 0)), 2)
    if importo <= 0:
        return None
    if causale_contraddice_beneficiario(bonifico, righe):
        return None

    beneficiario = bonifico.get("beneficiario") or {}
    nome = (beneficiario.get("nome") or bonifico.get("dipendente_nome") or "").strip()
    iban = re.sub(r"\s+", "", beneficiario.get("iban") or "").upper()
    # Il periodo e' considerato solo quando proviene dalla causale del PDF.
    # "bonifico marzo" nel nome file descrive invece il mese di pagamento.
    periodo_mese = bonifico.get("periodo_mese")
    periodo_anno = bonifico.get("periodo_anno")
    data_pagamento = bonifico.get("data")

    candidati: List[Dict[str, Any]] = []
    for riga in righe:
        if riga.get("riconciliato") is True:
            continue
        residuo = importo_residuo_salario(riga)
        # Un dipendente puo' ricevere piu' acconti e poi il saldo. L'importo
        # deve essere positivo e non puo' superare il residuo documentabile;
        # la riga sara' chiusa solo quando la somma raggiunge la busta.
        if residuo <= 0 or importo - residuo > 0.009:
            continue

        nome_ok = identita_coincide(nome, _nome_salario(riga))
        riga_iban = re.sub(
            r"\s+", "",
            riga.get("iban") or riga.get("dipendente_iban") or "",
        ).upper()
        iban_ok = bool(iban and riga_iban and iban == riga_iban)
        if not (nome_ok or iban_ok):
            continue
        if periodo_mese and int(riga.get("mese") or 0) != int(periodo_mese):
            continue
        if periodo_anno and int(riga.get("anno") or 0) != int(periodo_anno):
            continue
        if not periodo_mese and not periodo_anno and data_pagamento:
            if not data_pagamento_compatibile(data_pagamento, riga):
                continue
        candidati.append(riga)

    return candidati[0] if len(candidati) == 1 else None


async def arricchisci_nomi_salari_da_cedolini(db) -> int:
    """Completa le vecchie righe senza nome usando CF/cedolino, mai l'importo."""
    vuote = await db["prima_nota_salari"].find(
        {"$or": [
            {"dipendente": {"$exists": False}}, {"dipendente": None},
            {"dipendente": ""},
            {"dipendente_nome": {"$exists": False}}, {"dipendente_nome": None},
            {"dipendente_nome": ""},
        ]},
        {"_id": 0},
    ).to_list(5000)
    aggiornate = 0
    for riga in vuote:
        cedolino = None
        if riga.get("cedolino_id"):
            cedolino = await db["cedolini"].find_one(
                {"id": riga["cedolino_id"]}, {"_id": 0}
            )
        if not cedolino and riga.get("codice_fiscale"):
            cedolino = await db["cedolini"].find_one({
                "codice_fiscale": riga["codice_fiscale"],
                "mese": riga.get("mese"), "anno": riga.get("anno"),
            }, {"_id": 0})
        nome = (cedolino or {}).get("nome_dipendente")
        if not nome:
            # Alcune righe storiche hanno conservato il nome soltanto nella
            # descrizione canonica "Stipendio NOME - MM/AAAA".
            match = re.search(
                r"Stipendio\s+(.+?)\s*[-–]\s*\d{1,2}/\d{4}",
                riga.get("descrizione") or "",
                re.I,
            )
            nome = match.group(1).strip() if match else None
        if not nome:
            continue
        result = await db["prima_nota_salari"].update_one(
            {"id": riga.get("id")},
            {"$set": {
                "dipendente": nome.upper(),
                "dipendente_nome": nome,
                "dipendente_id": (cedolino or {}).get("dipendente_id"),
                "codice_fiscale": (cedolino or {}).get("codice_fiscale"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        aggiornate += int(bool(result.modified_count))
    return aggiornate


async def associa_transfer_a_salario(db, transfer: Dict[str, Any]) -> Dict[str, Any]:
    """Collega il PDF, ma non certifica ancora il riscontro bancario."""
    if transfer.get("salario_associato") is True and transfer.get(
        "operazione_salario_id"
    ):
        return {
            "associato": True,
            "salario_id": transfer.get("operazione_salario_id"),
            "dipendente": transfer.get("dipendente_nome"),
            "gia_associato": True,
        }
    await arricchisci_nomi_salari_da_cedolini(db)
    righe = await db["prima_nota_salari"].find(
        {"riconciliato": {"$ne": True}}, {"_id": 0}
    ).to_list(5000)

    candidato = seleziona_salario_univoco(transfer, righe)
    if not candidato:
        return {"associato": False, "motivo": "identita_importo_non_univoci"}

    transfer_id = transfer.get("id")
    importo = round(abs(float(transfer.get("importo") or 0)), 2)
    ids = list(candidato.get("bonifico_documenti_ids") or [])
    gia_collegato = transfer_id in ids
    if not gia_collegato:
        ids.append(transfer_id)
    totale_documentato = float(candidato.get("importo_bonifico_documentato") or 0)
    if not gia_collegato:
        totale_documentato = round(totale_documentato + importo, 2)

    nome = _nome_salario(candidato)
    now = datetime.now(timezone.utc).isoformat()
    residuo_prima = importo_residuo_salario(candidato)
    evidenze = ["identita_esatta", "importo_entro_residuo"]
    if abs(residuo_prima - importo) <= 0.009:
        evidenze.append("saldo_documentale_completo")
    else:
        evidenze.append("acconto_documentale")
    await db["bonifici_transfers"].update_one(
        {"id": transfer_id},
        {"$set": {
            "salario_associato": True,
            "operazione_salario_id": candidato.get("id"),
            "dipendente_id": candidato.get("dipendente_id"),
            "dipendente_nome": nome,
            "associazione_evidenze": evidenze,
            "stato_riconciliazione": "documento_associato_attesa_banca",
            "updated_at": now,
        }},
    )
    await db["prima_nota_salari"].update_one(
        {"id": candidato.get("id")},
        {"$set": {
            "importo_bonifico_documentato": totale_documentato,
            "bonifico_documenti_ids": ids,
            "bonifico_documento_associato": True,
            "stato_bonifico": "documentato_attesa_estratto_conto",
            "updated_at": now,
        }},
    )
    return {"associato": True, "salario_id": candidato.get("id"), "dipendente": nome}


async def associa_transfer_a_fatture(db, transfer: Dict[str, Any]) -> Dict[str, Any]:
    """Collega fatture solo con numero esplicito, fornitore e centesimi certi."""
    from app.services.payment_document_links import (
        collega_bonifico_fatture,
        seleziona_fatture_bonifico,
    )

    invoices = await db["invoices"].find(
        {"bonifico_associato": {"$ne": True}},
        {"_id": 0, "id": 1, "invoice_number": 1, "numero_fattura": 1,
         "supplier_name": 1, "fornitore_denominazione": 1, "fornitore": 1,
         "cedente_denominazione": 1, "total_amount": 1, "totale": 1,
         "importo_totale": 1, "invoice_date": 1},
    ).to_list(5000)
    matched = seleziona_fatture_bonifico(transfer, invoices)
    if not matched:
        return {"associato": False, "motivo": "fattura_non_certa_o_ambigua"}
    await collega_bonifico_fatture(db, transfer, matched, auto=True)
    return {"associato": True, "fattura_ids": [item["id"] for item in matched]}


async def associa_transfer_documento(db, transfer: Dict[str, Any]) -> Dict[str, Any]:
    """Prima salari/cedolini, poi fatture fornitori; mai entrambe."""
    salary = await associa_transfer_a_salario(db, transfer)
    if salary.get("associato"):
        return salary
    return await associa_transfer_a_fatture(db, transfer)


async def importa_pdf_bonifico(
    db,
    content: bytes,
    filename: str,
    source: str = "upload_manuale",
    auto_associa: bool = True,
) -> Dict[str, Any]:
    """Parsa e archivia il PDF; il match automatico puo' essere disattivato."""
    if not content.startswith(b"%PDF"):
        return {"status": "error", "message": "Il file non e' un PDF valido"}
    digest = hashlib.sha256(content).hexdigest()
    esistente = await db["bonifici_transfers"].find_one(
        {"document_hash": digest}, {"_id": 0}
    )
    if esistente:
        # I documenti caricati prima della correzione possono contenere il
        # mese del nome file nel vecchio campo "periodo". Rileggiamo sempre il
        # PDF originale e correggiamo i soli metadati estratti.
        text = read_pdf_bytes(content)
        reparsed = extract_transfers_from_text(text, filename=filename)[0]
        beneficiario = reparsed.get("beneficiario") or {}
        metadata_file = extract_filename_metadata(filename)
        if not beneficiario.get("nome"):
            beneficiario["nome"] = metadata_file.get("beneficiario_nome")
        reparsed["beneficiario"] = beneficiario
        aggiornamento = {
            key: reparsed.get(key)
            for key in (
                "data", "importo", "beneficiario", "ordinante", "causale",
                "cro_trn", "periodo_mese", "periodo_anno",
                "mese_pagamento_file", "anno_pagamento_file",
            )
        }
        if isinstance(aggiornamento.get("data"), datetime):
            aggiornamento["data"] = aggiornamento["data"].isoformat()
        aggiornamento["source_file"] = filename
        aggiornamento["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db["bonifici_transfers"].update_one(
            {"id": esistente.get("id")}, {"$set": aggiornamento}
        )
        esistente.update(aggiornamento)
        associazione = (
            await associa_transfer_documento(db, esistente)
            if auto_associa
            else {"associato": False, "motivo": "associazione_manuale_richiesta"}
        )
        return {"status": "duplicate", "transfer_id": esistente.get("id"), **associazione}

    text = read_pdf_bytes(content)
    parsed = extract_transfers_from_text(text, filename=filename)[0]
    metadata_file = extract_filename_metadata(filename)
    beneficiario = parsed.get("beneficiario") or {}
    if not beneficiario.get("nome"):
        beneficiario["nome"] = metadata_file.get("beneficiario_nome")
    parsed["beneficiario"] = beneficiario

    now = datetime.now(timezone.utc).isoformat()
    transfer = {
        **parsed,
        "id": str(uuid.uuid4()),
        "source_file": filename,
        "source": source,
        "document_hash": digest,
        "pdf_data": base64.b64encode(content).decode("ascii"),
        "created_at": now,
        "riconciliato": False,
    }
    if isinstance(transfer.get("data"), datetime):
        transfer["data"] = transfer["data"].isoformat()
    transfer["dedup_key"] = build_dedup_key(transfer)
    transfer["parser_completo"] = bool(
        transfer.get("importo")
        and (transfer.get("beneficiario") or {}).get("nome")
        and transfer.get("data")
    )
    await db["bonifici_transfers"].insert_one(dict(transfer))
    associazione = (
        await associa_transfer_documento(db, transfer)
        if auto_associa
        else {"associato": False, "motivo": "associazione_manuale_richiesta"}
    )
    return {
        "status": "saved",
        "transfer_id": transfer["id"],
        "parser_completo": transfer["parser_completo"],
        **associazione,
    }


async def processa_inbox_bonifici(db, limit: int = 100) -> Dict[str, int]:
    """Recupera anche i PDF gia' caricati prima dell'attivazione del flusso."""
    docs = await db["documents_inbox"].find(
        {
            "category": "bonifico",
            "$or": [
                {"processed": {"$ne": True}},
                {"status": {"$in": ["da_processare", "errore_processing"]}},
            ],
        },
    ).sort("created_at", 1).to_list(limit)
    stats = {"letti": 0, "salvati": 0, "duplicati": 0, "associati": 0, "errori": 0}
    for doc in docs:
        stats["letti"] += 1
        document_filter = {"_id": doc["_id"]} if doc.get("_id") is not None else {"id": doc.get("id")}
        try:
            content = base64.b64decode(doc.get("pdf_data") or "", validate=True)
            result = await importa_pdf_bonifico(
                db, content, doc.get("filename") or "bonifico.pdf",
                source=doc.get("source") or "documents_inbox",
            )
            status = result.get("status")
            if status == "saved":
                stats["salvati"] += 1
            elif status == "duplicate":
                stats["duplicati"] += 1
            if result.get("associato"):
                stats["associati"] += 1
            await db["documents_inbox"].update_one(
                document_filter,
                {"$set": {
                    "processed": True,
                    "status": "elaborato",
                    "bonifico_transfer_id": result.get("transfer_id"),
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
        except Exception as exc:
            stats["errori"] += 1
            logger.warning("Bonifico inbox non processabile (%s): %s", doc.get("id"), exc)
            await db["documents_inbox"].update_one(
                document_filter,
                {"$set": {"status": "errore_processing", "processing_error": type(exc).__name__}},
            )
    return stats


async def riprocessa_bonifici_pendenti(db, limit: int = 200) -> Dict[str, int]:
    """Rilegge i PDF non associati e ritenta esclusivamente il match certo."""
    transfers = await db["bonifici_transfers"].find(
        {
            "salario_associato": {"$ne": True},
            "pdf_data": {"$exists": True, "$nin": [None, ""]},
        },
        {"_id": 0},
    ).sort("created_at", 1).to_list(limit)
    stats = {"letti": 0, "associati": 0, "non_associati": 0, "errori": 0}
    for transfer in transfers:
        stats["letti"] += 1
        try:
            content = base64.b64decode(transfer.get("pdf_data") or "", validate=True)
            result = await importa_pdf_bonifico(
                db,
                content,
                transfer.get("source_file") or "bonifico.pdf",
                source=transfer.get("source") or "riprocessamento_sicuro",
            )
            if result.get("associato"):
                stats["associati"] += 1
            else:
                stats["non_associati"] += 1
        except Exception as exc:
            stats["errori"] += 1
            logger.warning("Bonifico pendente non riprocessabile (%s): %s", transfer.get("id"), exc)
    return stats
