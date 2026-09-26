"""Import dell'estratto della carta Mastercard SumUp (conto 19.01.05).

L'API pubblica di SumUp espone vendite e payout, non i movimenti del conto
business: bonifici in uscita (stipendi, fornitori, giroconti) e pagamenti POS
fatti con la carta si leggono solo dal PDF «Estratto conto SumUp».

Le righe vanno in una collezione propria, ``sumup_conto_movimenti``, e **non**
in ``estratto_conto_movimenti``: quella la leggono come conto BPM decine di
motori (proiezione in Prima Nota, saldi, riconciliazione) che non guardano il
conto, e una riga SumUp finirebbe su 19.01.01.

- Identità della riga = codice transazione SumUp: un secondo estratto con
  periodo sovrapposto non duplica niente.
- Identità del file = SHA-256.
- Un «Pagamento da SumUp» è l'accredito di un payout già registrato dall'API
  (``sumup_payouts``): la riga lo cita (``payout_id``), non ne crea un secondo.
- Un estratto la cui catena dei saldi non torna non si importa
  (``EstrattoSumUpNonValido``).
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.parsers.estratto_conto_sumup_parser import (
    EstrattoSumUp,
    RigaSumUp,
    leggi_estratto_sumup,
)
from app.services.conti_pos import CONTO_SUMUP_MASTERCARD

logger = logging.getLogger(__name__)

COLL_ESTRATTI = "sumup_conto_estratti"
COLL_MOVIMENTI = "sumup_conto_movimenti"
COLL_PAYOUT = "sumup_payouts"

_PID = re.compile(r"\bPID\d+\b")
_IBAN_IT = re.compile(r"IT\d{2}[A-Z]\d{10}[0-9A-Z]{12}")


def _id_riga(codice: str) -> str:
    return f"sumup_conto:{codice}"


def _iban_beneficiario(riferimento: str) -> Optional[str]:
    """L'IBAN del beneficiario va a capo dentro la cella: si ricompone."""
    trovato = _IBAN_IT.search(re.sub(r"\s+", "", riferimento or "").upper())
    return trovato.group(0) if trovato else None


def record_movimento(riga: RigaSumUp, estratto: EstrattoSumUp, *, estratto_id: str,
                     payout_id: Optional[str], filename: str,
                     drive_file_id: Optional[str], ora_import: str) -> Dict[str, Any]:
    netto = riga.importo_netto
    record: Dict[str, Any] = {
        "id": _id_riga(riga.codice),
        "operation_id": _id_riga(riga.codice),
        "codice_transazione": riga.codice,
        "estratto_id": estratto_id,
        "data": riga.data,
        "ora": riga.ora,
        "tipo_transazione": riga.tipo_transazione,
        "riferimento": riga.riferimento,
        "causale": riga.causale,
        "stato": riga.stato,
        "uscita": str(riga.uscita),
        "entrata": str(riga.entrata),
        "commissione": str(riga.commissione),
        "saldo": str(riga.saldo),
        "importo": str(netto),
        "segno": "entrata" if netto > 0 else "uscita",
        "conto_contabile": CONTO_SUMUP_MASTERCARD,
        "iban_conto": estratto.iban,
        "pid": riga.pid,
        "payout_id": payout_id,
        "source_filename": filename,
        "drive_file_id": drive_file_id,
        "created_at": ora_import,
    }
    if riga.tipo_transazione.lower().startswith("bonifico"):
        record["iban_beneficiario"] = _iban_beneficiario(riga.riferimento)
    return record


async def _payout_per_pid(db) -> Dict[str, str]:
    """``PID…`` → ``payout_id`` dei payout già registrati dall'API."""
    mappa: Dict[str, str] = {}
    async for payout in db[COLL_PAYOUT].find({}, {"_id": 0, "payout_id": 1}):
        payout_id = str(payout.get("payout_id") or "")
        trovato = _PID.search(payout_id)
        if trovato:
            mappa[trovato.group(0)] = payout_id
    return mappa


async def importa_estratto_sumup_pdf(
    db,
    filename: str,
    pdf_content: bytes,
    *,
    source: str = "documenti_upload_auto_sumup",
    drive_file_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Legge, verifica e salva l'estratto. Solleva se il PDF non torna."""
    estratto = leggi_estratto_sumup(pdf_content)
    sha256 = hashlib.sha256(pdf_content).hexdigest()
    estratto_id = f"sumup_statement:{sha256}"
    ora_import = datetime.now(timezone.utc).isoformat()

    gia_noto = await db[COLL_ESTRATTI].find_one(
        {"content_sha256": sha256}, {"_id": 0, "id": 1},
    )
    codici = [riga.codice for riga in estratto.righe]
    esistenti = {
        doc.get("codice_transazione")
        async for doc in db[COLL_MOVIMENTI].find(
            {"codice_transazione": {"$in": codici}},
            {"_id": 0, "codice_transazione": 1},
        )
    }
    payout = await _payout_per_pid(db)

    nuovi = []
    payout_collegati = 0
    payout_mancanti = []
    for riga in estratto.righe:
        payout_id = payout.get(riga.pid) if riga.pid else None
        if riga.pid:
            if payout_id:
                payout_collegati += 1
            else:
                payout_mancanti.append(riga.pid)
        if riga.codice in esistenti:
            continue
        nuovi.append(record_movimento(
            riga, estratto, estratto_id=estratto_id, payout_id=payout_id,
            filename=filename, drive_file_id=drive_file_id, ora_import=ora_import,
        ))

    if not gia_noto:
        await db[COLL_ESTRATTI].insert_one({
            "id": estratto_id,
            "filename": filename,
            "content_sha256": sha256,
            "drive_file_id": drive_file_id,
            "source": source,
            "iban": estratto.iban,
            "id_utente": estratto.id_utente,
            "numero_carta": estratto.numero_carta,
            "periodo_dal": estratto.periodo_dal,
            "periodo_al": estratto.periodo_al,
            "saldo_iniziale": str(estratto.saldo_iniziale),
            "saldo_finale": str(estratto.saldo_finale),
            "totale_entrate": str(estratto.totale_entrate),
            "totale_uscite": str(estratto.totale_uscite),
            "righe": len(estratto.righe),
            "conto_contabile": CONTO_SUMUP_MASTERCARD,
            "import_date": ora_import,
        })
    for record in nuovi:
        await db[COLL_MOVIMENTI].insert_one(record)

    if payout_mancanti:
        logger.warning(
            "Estratto SumUp %s: %d accrediti senza payout registrato dall'API: %s",
            filename, len(payout_mancanti), ", ".join(payout_mancanti),
        )
    return {
        "success": True,
        "duplicate": not nuovi,
        "estratto_id": estratto_id,
        "periodo_dal": estratto.periodo_dal,
        "periodo_al": estratto.periodo_al,
        "righe": len(estratto.righe),
        "nuovi": len(nuovi),
        "gia_presenti": len(estratto.righe) - len(nuovi),
        "payout_collegati": payout_collegati,
        "payout_senza_api": payout_mancanti,
        "saldo_finale": str(estratto.saldo_finale),
    }
