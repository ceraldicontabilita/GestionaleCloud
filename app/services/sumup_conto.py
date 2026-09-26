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

import asyncio
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

PREFISSO_ID = "sumup_conto:"
COLL_ESTRATTO_CONTO_BANCA = "estratto_conto_movimenti"

_PID = re.compile(r"\bPID\d+\b")
_IBAN_IT = re.compile(r"IT\d{2}[A-Z]\d{10}[0-9A-Z]{12}")
_INIZIO_IBAN = re.compile(r"\bIT\d{2}[A-Z]\d")


def _id_riga(codice: str) -> str:
    return f"{PREFISSO_ID}{codice}"


def collezione_del_movimento(movimento: Dict[str, Any]) -> str:
    """In quale archivio sta un movimento bancario: carta SumUp o conto BPM.

    I motori di abbinamento (fatture, stipendi) lavorano sulle due fonti con
    la stessa logica; cambia solo dove si scrive l'esito.
    """
    identificativo = str(movimento.get("id") or "")
    return COLL_MOVIMENTI if identificativo.startswith(PREFISSO_ID) else COLL_ESTRATTO_CONTO_BANCA


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
    record.update(campi_bancari(record))
    return record


def campi_bancari(movimento: Dict[str, Any]) -> Dict[str, Any]:
    """I campi che i motori di abbinamento leggono su ogni movimento bancario.

    ``tipo`` (entrata/uscita), ``beneficiario`` e ``descrizione``: nel PDF
    l'IBAN va a capo dentro la cella e resterebbe spezzato in due parole, che
    nessun confronto con l'anagrafica riconosce. Qui si ricompone.
    """
    riferimento = str(movimento.get("riferimento") or "").strip()
    causale = str(movimento.get("causale") or "").strip()
    iban = movimento.get("iban_beneficiario")
    beneficiario = riferimento
    if iban:
        inizio = _INIZIO_IBAN.search(riferimento)
        beneficiario = riferimento[:inizio.start()].strip() if inizio else riferimento
    parti = [p for p in (beneficiario, iban, causale) if p]
    importo = str(movimento.get("importo") or "0")
    return {
        "tipo": "uscita" if importo.startswith("-") else "entrata",
        "beneficiario": beneficiario,
        "descrizione": " — ".join(parti) if parti else riferimento,
    }


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


async def abbina_movimenti_sumup(db, *, anno: Optional[int] = None) -> Dict[str, Any]:
    """Abbina i bonifici partiti dalla carta SumUp a cedolini e fatture.

    Nessun motore nuovo: gli stessi del conto BPM, puntati sulla collezione
    della carta, con le stesse prove (identità del dipendente o del
    fornitore, importo al centesimo, un solo candidato). L'esito ambiguo
    resta non abbinato.

    1. stipendi: ``associa_bonifici_stipendi`` (dipendente per IBAN, CF o
       nome univoco, importo entro il residuo della busta);
    2. fatture: abbinamento per identità (numero, IBAN/P.IVA o nome del
       fornitore più importo al centesimo), che scrive fattura, partita,
       scadenze e Prima Nota Banca su 19.01.05;
    3. Prima Nota Banca dei pagamenti con causale certa (stipendi,
       finanziamento soci) sul conto della carta.
    """
    from app.services.bank_payment_allocations import _reconcile_unique_identity_matches
    from app.services.proiezione_bancaria import proietta_movimenti_bancari_semantici
    from app.services.stipendi_bonifici import associa_bonifici_stipendi

    movimenti = await db[COLL_MOVIMENTI].find({}, {"_id": 0}).to_list(20000)
    if anno:
        movimenti = [m for m in movimenti if str(m.get("data") or "").startswith(f"{anno}-")]
    # Le righe importate prima di questa versione non hanno i campi bancari.
    arricchiti = 0
    for movimento in movimenti:
        mancanti = {
            chiave: valore for chiave, valore in campi_bancari(movimento).items()
            if movimento.get(chiave) != valore
        }
        if mancanti:
            await db[COLL_MOVIMENTI].update_one({"id": movimento["id"]}, {"$set": mancanti})
            movimento.update(mancanti)
            arricchiti += 1

    stipendi = await associa_bonifici_stipendi(
        db, anno=anno, collezione_movimenti=COLL_MOVIMENTI, ripassa_collegati=False,
    )

    ids_stipendio = {
        doc.get("id") async for doc in db[COLL_MOVIMENTI].find(
            {"riconciliato": True}, {"_id": 0, "id": 1},
        )
    }
    da_abbinare = [
        m for m in movimenti
        if m.get("tipo") == "uscita" and not m.get("riconciliato")
        and m.get("id") not in ids_stipendio
    ]
    fatture = await _reconcile_unique_identity_matches(db, da_abbinare, proponi=False)

    prima_nota = await proietta_movimenti_bancari_semantici(
        db, anno=anno, collezione=COLL_MOVIMENTI,
        conto_contabile=CONTO_SUMUP_MASTERCARD,
    )
    esito = {
        "movimenti": len(movimenti),
        "arricchiti": arricchiti,
        "stipendi_abbinati": stipendi.get("bonifici_associati", 0),
        "stipendi_dettaglio": stipendi.get("dettaglio", []),
        "stipendi_ambigui": stipendi.get("match_ambigui_ignorati", 0),
        "fatture_abbinate": fatture["collegati_count"],
        "fatture_dettaglio": fatture["collegati"],
        "fatture_ambigue": fatture["ambigui_movimento"] + fatture["ambigui_fattura"],
        "fatture_da_scegliere": fatture["proposte"],
        "prima_nota_banca": {
            "scritte": prima_nota.get("proiettati", 0),
            "gia_presenti": prima_nota.get("gia_presenti", 0),
            "stipendi": prima_nota.get("stipendi", 0),
            "finanziamenti_soci": prima_nota.get("finanziamenti_soci", 0),
        },
    }
    logger.info("Abbinamento carta SumUp: %s", {k: v for k, v in esito.items() if k != "fatture_dettaglio"})
    return esito


_ABBINAMENTI_IN_CORSO: set = set()


def accoda_abbinamento(db) -> None:
    """Dopo un import l'abbinamento gira in sottofondo: l'import non lo aspetta.

    Se ne sta gia' girando uno, basta quello (rilegge tutta la collezione).
    """
    if _ABBINAMENTI_IN_CORSO:
        return

    async def _gira() -> None:
        try:
            await abbina_movimenti_sumup(db)
        except Exception as exc:  # noqa: BLE001 - lo ripassa il giro dei 30 minuti
            logger.exception("Abbinamento carta SumUp dopo l'import non completato (%s)",
                             type(exc).__name__)

    task = asyncio.get_running_loop().create_task(_gira(), name="abbinamento_carta_sumup")
    _ABBINAMENTI_IN_CORSO.add(task)
    task.add_done_callback(_ABBINAMENTI_IN_CORSO.discard)
