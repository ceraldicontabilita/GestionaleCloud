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
- Lo stesso conto arriva anche come CSV («Resoconto_transazioni_…csv»):
  stesso motore, stesse righe, stessa identità per codice transazione.
- Un bonifico verso Ceraldi Group è un **giroconto** verso BPM, non una
  spesa: due movimenti speculari in Prima Nota Banca (uscita 19.01.05,
  entrata 19.01.01) collegati da ``trasferimento_collegato_id`` con lo
  stesso ``operation_id``. L'entrata BPM si aggancia alla riga del suo
  estratto conto solo se è una e una sola.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.parsers.estratto_conto_sumup_parser import (
    EstrattoSumUp,
    RigaSumUp,
    leggi_estratto_sumup,
    leggi_resoconto_sumup_csv,
)
from app.services.conti_pos import CONTO_BPM, CONTO_SUMUP_MASTERCARD

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


def testi_da_riga(riga: RigaSumUp) -> Dict[str, Any]:
    """I campi descrittivi della riga, gli stessi che scrive ``record_movimento``."""
    testi: Dict[str, Any] = {
        "riferimento": riga.riferimento,
        "causale": riga.causale,
        "ora": riga.ora,
    }
    if riga.tipo_transazione.lower().startswith("bonifico"):
        testi["iban_beneficiario"] = _iban_beneficiario(riga.riferimento)
    return testi


async def _payout_per_pid(db) -> Dict[str, str]:
    """``PID…`` → ``payout_id`` dei payout già registrati dall'API."""
    mappa: Dict[str, str] = {}
    async for payout in db[COLL_PAYOUT].find({}, {"_id": 0, "payout_id": 1}):
        payout_id = str(payout.get("payout_id") or "")
        trovato = _PID.search(payout_id)
        if trovato:
            mappa[trovato.group(0)] = payout_id
    return mappa


async def importa_estratto_sumup(
    db,
    filename: str,
    contenuto: bytes,
    *,
    source: str = "documenti_upload_auto_sumup",
    drive_file_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Legge, verifica e salva l'estratto (PDF o CSV). Solleva se non torna."""
    if str(filename or "").lower().endswith(".csv"):
        estratto = leggi_resoconto_sumup_csv(contenuto)
    else:
        estratto = leggi_estratto_sumup(contenuto)
    sha256 = hashlib.sha256(contenuto).hexdigest()
    estratto_id = f"sumup_statement:{sha256}"
    ora_import = datetime.now(timezone.utc).isoformat()

    gia_noto = await db[COLL_ESTRATTI].find_one(
        {"content_sha256": sha256}, {"_id": 0, "id": 1},
    )
    codici = [riga.codice for riga in estratto.righe]
    esistenti = {
        doc.get("codice_transazione"): doc
        async for doc in db[COLL_MOVIMENTI].find(
            {"codice_transazione": {"$in": codici}},
            {"_id": 0, "id": 1, "codice_transazione": 1, "riferimento": 1,
             "causale": 1, "ora": 1, "iban_beneficiario": 1},
        )
    }
    da_csv = str(filename or "").lower().endswith(".csv")
    testi_corretti = 0
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
            # Il PDF spezza le celle lunghe («VANDEMO ORTELE», IBAN a capo):
            # il CSV ha i testi interi e li sostituisce. Importi, saldo e
            # collegamenti restano quelli gia' registrati.
            if da_csv:
                testi = testi_da_riga(riga)
                vecchio = esistenti[riga.codice]
                diversi = {k: v for k, v in testi.items() if vecchio.get(k) != v}
                if diversi:
                    await db[COLL_MOVIMENTI].update_one({"id": vecchio["id"]}, {"$set": diversi})
                    testi_corretti += 1
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

    giroconti = await registra_giroconti(db, [riga.codice for riga in estratto.righe])

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
        "testi_corretti": testi_corretti,
        "payout_collegati": payout_collegati,
        "payout_senza_api": payout_mancanti,
        "giroconti": giroconti,
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
        # Il giroconto verso BPM ha le sue due gambe (registra_giroconto).
        and not e_giroconto(m)
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

# --- Giroconti verso il conto BPM -------------------------------------------

CATEGORIA_GIROCONTO = "trasferimento_interno"
SOURCE_GIROCONTO = "giroconto_sumup"
_CONTROPARTE_PROPRIA = "CERALDI GROUP"
_GIORNI_ARRIVO_BPM = 3


def e_giroconto(movimento: Dict[str, Any]) -> bool:
    """Bonifico in uscita verso la società stessa (conto BPM)."""
    return (
        str(movimento.get("tipo_transazione") or "").lower().startswith("bonifico")
        and movimento.get("segno") == "uscita"
        and _CONTROPARTE_PROPRIA in str(movimento.get("riferimento") or "").upper()
    )


def _descrizione_ec(riga: Dict[str, Any]) -> str:
    return str(riga.get("descrizione_originale") or riga.get("descrizione") or "")


async def _entrata_bpm(db, importo: float, giorno: date,
                       operazione: str) -> Optional[Dict[str, Any]]:
    """La riga dell'estratto BPM che riceve il giroconto, se è una sola."""
    fine = (giorno + timedelta(days=_GIORNI_ARRIVO_BPM)).isoformat()
    candidati = await db["estratto_conto_movimenti"].find({
        "data": {"$gte": giorno.isoformat(), "$lte": fine},
        "tipo": "entrata",
    }, {"_id": 0, "id": 1, "importo": 1, "descrizione_originale": 1,
        "descrizione": 1, "conto_contabile": 1, "riconciliato": 1,
        "operation_id_giroconto": 1}).to_list(None)
    trovati = [
        riga for riga in candidati
        # Una riga già spiegata da un'altra prova non si riusa.
        if (not riga.get("riconciliato") or riga.get("operation_id_giroconto") == operazione)
        and abs(abs(float(riga.get("importo") or 0)) - importo) <= 0.01
        and _CONTROPARTE_PROPRIA in _descrizione_ec(riga).upper()
        and riga.get("conto_contabile") in (None, CONTO_BPM)
    ]
    # Due entrate uguali nella stessa finestra: non si sceglie a caso.
    return trovati[0] if len(trovati) == 1 else None


async def registra_giroconto(db, movimento: Dict[str, Any]) -> Dict[str, Any]:
    """Scrive (idempotente) le due gambe del giroconto SumUp -> BPM."""
    from app.services.scritture_contabili import scrivi_movimento_se_assente

    importo = abs(float(movimento.get("importo") or 0))
    operazione = f"giroconto-sumup:{movimento['codice_transazione']}"
    causale = movimento.get("causale") or "Giroconto"
    comune = {
        "data": movimento["data"], "importo": importo,
        "categoria": CATEGORIA_GIROCONTO, "operation_id": operazione,
        "source": SOURCE_GIROCONTO, "sumup_movimento_id": movimento["id"],
    }
    id_sumup, _ = await scrivi_movimento_se_assente(
        db, "banca", {"operation_id": operazione, "conto_contabile": CONTO_SUMUP_MASTERCARD},
        {**comune, "tipo": "uscita", "conto_contabile": CONTO_SUMUP_MASTERCARD,
         "descrizione": f"Giroconto da Mastercard SumUp a Banco BPM — {causale}"},
    )
    bpm = await _entrata_bpm(
        db, importo, date.fromisoformat(str(movimento["data"])[:10]), operazione,
    )
    gamba_bpm = {**comune, "tipo": "entrata", "conto_contabile": CONTO_BPM,
                 "trasferimento_collegato_id": id_sumup,
                 "descrizione": f"Giroconto da Mastercard SumUp — {causale}"}
    if bpm:
        gamba_bpm["estratto_conto_id"] = bpm["id"]
    else:
        # L'accredito BPM non si vede ancora: la gamba resta un'attesa.
        gamba_bpm["in_attesa_estratto_ufficiale"] = True
    id_bpm, gia_scritta = await scrivi_movimento_se_assente(
        db, "banca", {"operation_id": operazione, "conto_contabile": CONTO_BPM}, gamba_bpm,
    )
    await db["prima_nota_banca"].update_one(
        {"id": id_sumup}, {"$set": {"trasferimento_collegato_id": id_bpm}},
    )
    if bpm:
        if gia_scritta:
            # L'accredito BPM è arrivato dopo la gamba: ora la prova c'è.
            await db["prima_nota_banca"].update_one({"id": id_bpm}, {"$set": {
                "estratto_conto_id": bpm["id"], "in_attesa_estratto_ufficiale": False,
            }})
        await db["estratto_conto_movimenti"].update_one({"id": bpm["id"]}, {"$set": {
            "riconciliato": True,
            "tipo_riconciliazione": "giroconto",
            "operation_id_giroconto": operazione,
            "dettagli_riconciliazione": {"prima_nota_id": id_bpm},
        }})
    await db[COLL_MOVIMENTI].update_one({"id": movimento["id"]}, {"$set": {
        "giroconto_operation_id": operazione,
        "prima_nota_id": id_sumup,
        "estratto_bpm_id": (bpm or {}).get("id"),
    }})
    return {"operation_id": operazione, "id_sumup": id_sumup, "id_bpm": id_bpm,
            "estratto_bpm": (bpm or {}).get("id")}


async def registra_giroconti(db, codici: List[str]) -> List[Dict[str, Any]]:
    """Giroconti fra le righe indicate, anche quelle importate in passato:
    un'entrata BPM arrivata dopo si aggancia al giro successivo."""
    righe = await db[COLL_MOVIMENTI].find(
        {"codice_transazione": {"$in": codici}}, {"_id": 0},
    ).to_list(None)
    esiti = []
    for riga in righe:
        if not e_giroconto(riga):
            continue
        if riga.get("giroconto_operation_id") and riga.get("estratto_bpm_id"):
            continue
        esiti.append(await registra_giroconto(db, riga))
    return esiti
