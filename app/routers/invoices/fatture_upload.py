"""
Fatture XML Upload Router - Gestione upload fatture elettroniche.
Supporta upload singolo XML, multiplo XML e file ZIP.
Include riconciliazione automatica con estratto conto per numeri assegni.

Router canonico di /api/fatture: assorbe la logica di fatture_overlay.py
(rimosso). Upload singolo e bulk condividono ora la stessa pipeline
process_xml_bytes (P7M, prima nota, event bus) già usata da Drive/Email/
Documenti inbox. GET/PUT /{id} delegano a fatture_module.crud, la stessa
logica usata da /api/fatture-ricevute/fattura/{id}. cleanup-duplicates è
stato rimosso: la pulizia duplicati canonica gira già in automatico ogni
30 min via fatture_module.crud.pulisci_duplicati_invoices (app/scheduler.py).
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Body, Depends
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import uuid
import logging
import zipfile
import io
import re

from pymongo.errors import DuplicateKeyError

from app.database import Database, Collections
from app.parsers.fattura_elettronica_parser import parse_fattura_xml, TIPO_DOC_MAP
from app.services.xml_invoice_processor import extract_xml_from_p7m, is_p7m_content
from app.utils.error_handler import handle_errors
from app.utils.ruoli import richiedi_admin

logger = logging.getLogger(__name__)


def _piva_italiana_valida(piva: str) -> bool:
    """P.IVA italiana: esattamente 11 cifre numeriche. Usata solo per
    fornitori con nazione IT/vuota — le P.IVA estere hanno formati diversi
    e non vanno validate con questa regola."""
    return bool(re.fullmatch(r"\d{11}", (piva or "").strip()))


async def _controlla_dati_fornitore_incoerenti(
    db, supplier_id: str, supplier_vat: str, supplier_name: str, nazione: str, session=None
) -> None:
    """Genera FORN_DATI_INCOERENTI se la P.IVA di un fornitore italiano non
    ha il formato standard (11 cifre) — era definito in alert_engine.py ma
    mai generato (vedi memoria/moduli/FORNITORI.md). Additivo: non blocca
    la creazione/aggiornamento del fornitore, solo lo segnala."""
    nazione_norm = (nazione or "IT").strip().upper()
    if nazione_norm not in ("IT", "ITALIA", ""):
        return
    if _piva_italiana_valida(supplier_vat):
        return
    try:
        from app.services.alert_engine import genera_alert
        await genera_alert(
            "FORN_DATI_INCOERENTI", supplier_id, Collections.SUPPLIERS,
            f"Fornitore {supplier_name}: P.IVA '{supplier_vat}' non ha il formato standard "
            f"italiano (11 cifre)",
            db,
        )
    except Exception:
        logger.exception(f"Errore generazione alert FORN_DATI_INCOERENTI per {supplier_id}")
router = APIRouter()

# Tipi documento FatturaPA che rappresentano una nota di credito (TD04) o di
# debito (TD08 è nota di debito, non di credito, ma segue la stessa logica
# "collegata a un documento precedente" — vedi memoria/moduli/FATTURE_RICEVUTE.md).
NOTE_CREDITO_TIPI_DOCUMENTO = {"TD04", "TD08"}


async def _collega_nota_credito(db, invoice: Dict[str, Any], session=None) -> Optional[Dict[str, Any]]:
    """
    Se la fattura appena importata è una nota di credito (TD04/TD08) con
    riferimenti DatiFattureCollegate, cerca la fattura originale (stesso
    fornitore, invoice_number == IdDocumento del riferimento) e collega le
    due entità nei due sensi:
      - sulla nota di credito: fattura_collegata_id
      - sulla fattura originale: note_credito_collegate (lista id) e
        importo_netto (total_amount - somma delle note di credito collegate)

    Netting best-effort: se l'originale non si trova (fattura mai importata,
    riferimento incompleto), la nota di credito resta comunque salvata ma
    senza collegamento — non blocca l'import. Vedi memoria/moduli/
    FATTURE_RICEVUTE.md gap #1: prima di questa funzione non esisteva alcun
    collegamento automatico, rischio di doppio conteggio nello scadenzario.
    """
    if (invoice.get("tipo_documento") or "").upper() not in NOTE_CREDITO_TIPI_DOCUMENTO:
        return None

    riferimenti = invoice.get("dati_fatture_collegate") or []
    if not riferimenti:
        return None

    supplier_vat = invoice.get("supplier_vat", "")
    originale = None
    for rif in riferimenti:
        id_doc = (rif or {}).get("id_documento")
        if not id_doc:
            continue
        originale = await db[Collections.INVOICES].find_one(
            {
                "invoice_number": id_doc,
                "supplier_vat": supplier_vat,
                "tipo_documento": {"$nin": list(NOTE_CREDITO_TIPI_DOCUMENTO)},
            },
            session=session,
        )
        if originale:
            break

    if not originale:
        return None

    importo_nc = float(invoice.get("total_amount") or 0)
    importo_originale = float(originale.get("total_amount") or 0)
    note_credito_collegate = list(originale.get("note_credito_collegate") or [])
    if invoice["id"] not in note_credito_collegate:
        note_credito_collegate.append(invoice["id"])

    # Somma tutte le NC collegate a questo originale (non solo quella corrente)
    # per calcolare il netto corretto anche con più note di credito parziali.
    totale_nc = 0.0
    for nc_id in note_credito_collegate:
        if nc_id == invoice["id"]:
            totale_nc += importo_nc
            continue
        nc_doc = await db[Collections.INVOICES].find_one(
            {"id": nc_id}, {"total_amount": 1}, session=session
        )
        if nc_doc:
            totale_nc += float(nc_doc.get("total_amount") or 0)

    importo_netto = round(importo_originale - totale_nc, 2)

    await db[Collections.INVOICES].update_one(
        {"id": originale["id"]},
        {"$set": {
            "note_credito_collegate": note_credito_collegate,
            "importo_netto": importo_netto,
        }},
        session=session,
    )
    await db[Collections.INVOICES].update_one(
        {"id": invoice["id"]},
        {"$set": {"fattura_collegata_id": originale["id"]}},
        session=session,
    )
    logger.info(
        f"Nota di credito {invoice.get('invoice_number')} collegata a "
        f"fattura {originale.get('invoice_number')} (netto: €{importo_netto})"
    )
    return {"fattura_collegata_id": originale["id"], "importo_netto_originale": importo_netto}


def _norm_nome_azienda(nome: str) -> str:
    """Nome azienda normalizzato per confronti: maiuscole, solo alfanumerici.
    'Ceraldi Group s.r.l.' == 'CERALDI GROUP SRL'."""
    import re as _re
    return _re.sub(r"[^A-Z0-9]", "", (nome or "").upper())


def _piva_plausibile(vat: str) -> bool:
    """True solo per una vera P.IVA (11 cifre, con o senza prefisso paese UE).
    Un codice fiscale personale (16 alfanumerici) NON è una P.IVA: non deve
    mai finire nel campo partita_iva di un fornitore."""
    import re as _re
    v = (vat or "").strip().upper().replace(" ", "")
    if _re.fullmatch(r"[A-Z]{2}\d{11}", v):
        return True
    return bool(_re.fullmatch(r"\d{11}", v))


def _piva_estera_plausibile(vat: str) -> bool:
    """Come `_piva_plausibile` ma accetta anche i formati P.IVA/VAT-ID degli
    altri paesi UE (lunghezza e alfabeto variano per stato: es. DE 9 cifre,
    FR 2 lettere/cifre di controllo + 9 cifre, IE alfanumerico, ecc.) — 2
    lettere paese + 2-13 alfanumerici. USATA SOLO per le fatture ESTERE PDF
    (mai per l'XML italiano: lì l'11 cifre resta un vincolo di qualità dati,
    vedi `_piva_plausibile`), per agganciare/creare il fornitore anche
    quando il formato non è quello italiano — così più fatture dello stesso
    fornitore estero convergono sullo stesso record invece di restare
    orfane, aumentando la certezza che l'estrazione abbia letto bene."""
    import re as _re
    v = (vat or "").strip().upper().replace(" ", "")
    if _piva_plausibile(v):
        return True
    return bool(_re.fullmatch(r"[A-Z]{2}[A-Z0-9]{2,13}", v))


async def ensure_supplier_exists(db, parsed_invoice: Dict[str, Any], session=None,
                                  piva_validator=_piva_plausibile) -> Dict[str, Any]:
    """
    Verifica se il fornitore esiste. Se sì, aggiorna i campi anagrafici mancanti.
    Se non esiste, lo crea automaticamente con i dati dalla fattura XML.

    session: sessione Mongo opzionale, per partecipare a una transazione del
    chiamante (es. process_fattura_to_db). None per gli altri chiamanti.
    piva_validator: funzione di plausibilità P.IVA da usare per la guardia
    sotto — default `_piva_plausibile` (solo formato italiano/UE 11 cifre).
    Le fatture estere PDF passano `_piva_estera_plausibile` per accettare
    anche i formati P.IVA degli altri paesi UE.
    """
    supplier_vat = parsed_invoice.get("supplier_vat") or ""
    supplier_name = parsed_invoice.get("supplier_name") or "Fornitore Sconosciuto"

    result = {
        "supplier_exists": False,
        "supplier_created": False,
        "supplier_updated": False,
        "alert_created": False,
        "supplier_id": None,
        "metodo_pagamento": None,
    }

    if not supplier_vat:
        return result

    # ── GUARDIA AUTOFATTURE / cedente=cessionario ─────────────────────────
    # Se il cedente coincide col cessionario della stessa fattura (autofatture
    # TD16-TD27, integrazioni reverse charge, o XML con anagrafiche scambiate)
    # NON è un fornitore: senza questa guardia l'azienda stessa finiva in
    # anagrafica fornitori come "Ceraldi Group srl" con P.IVA/CF di terzi
    # (fornitori fantasma segnalati dall'utente il 10/07).
    cliente_data = parsed_invoice.get("cliente") or {}
    cliente_piva = (cliente_data.get("partita_iva") or "").strip().upper().replace(" ", "")
    cedente_piva_norm = supplier_vat.strip().upper().replace(" ", "")
    stesso_soggetto = False
    if cliente_piva and cliente_piva.lstrip("IT") == cedente_piva_norm.lstrip("IT"):
        stesso_soggetto = True
    nome_cedente_norm = _norm_nome_azienda(supplier_name)
    nome_cliente_norm = _norm_nome_azienda(cliente_data.get("denominazione"))
    if nome_cedente_norm and nome_cliente_norm and nome_cedente_norm == nome_cliente_norm:
        stesso_soggetto = True
    if stesso_soggetto:
        logger.warning(
            f"Fattura con cedente = cessionario ({supplier_name} / {supplier_vat}): "
            f"probabile autofattura, NESSUN fornitore creato o aggiornato"
        )
        return result

    # ── GUARDIA P.IVA VALIDA ──────────────────────────────────────────────
    # Mai creare/agganciare un fornitore con un codice fiscale personale o
    # una stringa qualsiasi nel campo partita_iva.
    if not piva_validator(supplier_vat):
        logger.warning(
            f"Identificativo cedente '{supplier_vat}' non è una P.IVA valida "
            f"({supplier_name}): fornitore non creato automaticamente"
        )
        return result

    # Cerca fornitore per P.IVA (supporta sia 'piva' che 'partita_iva' come field name)
    # NB: niente proiezione {"_id": 0} — l'_id serve come filtro di update
    # perché i fornitori storici possono non avere il campo "id".
    existing = await db[Collections.SUPPLIERS].find_one(
        {"$or": [
            {"partita_iva": supplier_vat},
            {"piva": supplier_vat}
        ]},
        session=session
    )

    # Se non trovato per P.IVA, cerca per denominazione/nome.
    # SOLO uguaglianza esatta (normalizzata): il vecchio match a prefisso
    # ("^CERALDI GROUP SRL" prendeva anche "CERALDI GROUP S.R.L.") poteva
    # agganciare la fattura a un'azienda DIVERSA con nome simile e incollarle
    # la P.IVA del cedente. E se il record trovato ha già una P.IVA diversa,
    # è un'altra azienda: si crea un fornitore nuovo invece di sporcarlo.
    if not existing and supplier_name:
        import re as _re
        safe_name = _re.escape(supplier_name[:60])
        candidato = await db[Collections.SUPPLIERS].find_one(
            {"$or": [
                {"nome": {"$regex": f"^{safe_name}$", "$options": "i"}},
                {"ragione_sociale": {"$regex": f"^{safe_name}$", "$options": "i"}},
                {"denominazione": {"$regex": f"^{safe_name}$", "$options": "i"}}
            ]},
            session=session
        )
        if candidato:
            piva_candidato = (
                candidato.get("partita_iva") or candidato.get("piva")
                or candidato.get("vat_number") or ""
            ).strip().upper().replace(" ", "")
            if piva_candidato and piva_candidato.lstrip("IT") != cedente_piva_norm.lstrip("IT"):
                logger.warning(
                    f"Fornitore omonimo '{supplier_name}' ha P.IVA diversa "
                    f"({piva_candidato} ≠ {supplier_vat}): niente aggancio per nome"
                )
            else:
                existing = candidato

    fornitore_data = parsed_invoice.get("fornitore") or {}

    if existing:
        result["supplier_exists"] = True
        # I fornitori storici (creati da altre app o import vecchi) possono non
        # avere il campo "id": in quel caso lo generiamo e lo scriviamo sotto.
        supplier_id = existing.get("id") or str(uuid.uuid4())
        result["supplier_id"] = supplier_id
        result["metodo_pagamento"] = existing.get("metodo_pagamento")

        # FORN_INATTIVO_USATO era definito in alert_engine.py ma mai generato:
        # un fornitore marcato "attivo": False (disattivato manualmente) può
        # comunque ricevere nuove fatture senza che nessuno se ne accorga.
        # Additivo: non blocca l'import, solo lo segnala.
        if existing.get("attivo") is False:
            try:
                from app.services.alert_engine import genera_alert
                await genera_alert(
                    "FORN_INATTIVO_USATO", supplier_id, Collections.SUPPLIERS,
                    f"Nuova fattura per {supplier_name} (P.IVA {supplier_vat}), "
                    f"fornitore marcato come non attivo",
                    db,
                )
            except Exception:
                logger.exception(f"Errore generazione alert FORN_INATTIVO_USATO per {supplier_id}")

        await _controlla_dati_fornitore_incoerenti(
            db, supplier_id, supplier_vat, supplier_name,
            existing.get("nazione") or fornitore_data.get("nazione") or "IT", session=session,
        )

        # Aggiorna SEMPRE i campi anagrafici mancanti (non sovrascrive quelli già compilati)
        update_data = {}
        field_map = {
            "partita_iva": supplier_vat,
            "piva": supplier_vat,
            "nome": supplier_name,
            "ragione_sociale": existing.get("ragione_sociale") or supplier_name,
            "codice_fiscale": fornitore_data.get("codice_fiscale") or existing.get("codice_fiscale") or supplier_vat,
            "indirizzo": fornitore_data.get("indirizzo") or existing.get("indirizzo") or "",
            "cap": fornitore_data.get("cap") or existing.get("cap") or "",
            "comune": fornitore_data.get("comune") or existing.get("comune") or "",
            "provincia": fornitore_data.get("provincia") or existing.get("provincia") or "",
            "nazione": fornitore_data.get("nazione") or existing.get("nazione") or "IT",
        }
        for field, value in field_map.items():
            if value and not existing.get(field):
                update_data[field] = value

        if not existing.get("id"):
            update_data["id"] = supplier_id

        if update_data:
            update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            update_data["dati_incompleti"] = False
            await db[Collections.SUPPLIERS].update_one(
                {"_id": existing["_id"]},
                {"$set": update_data},
                session=session
            )
            result["supplier_updated"] = True
            logger.info(f"Fornitore {supplier_name} aggiornato con dati XML: {list(update_data.keys())}")

        return result

    # Fornitore non esiste — CREA
    new_supplier = {
        "id": str(uuid.uuid4()),
        "nome": supplier_name,
        "ragione_sociale": supplier_name,
        "partita_iva": supplier_vat,
        "piva": supplier_vat,
        "codice_fiscale": fornitore_data.get("codice_fiscale") or supplier_vat,
        "indirizzo": fornitore_data.get("indirizzo") or "",
        "cap": fornitore_data.get("cap") or "",
        "comune": fornitore_data.get("comune") or "",
        "provincia": fornitore_data.get("provincia") or "",
        "nazione": fornitore_data.get("nazione") or "IT",
        "metodo_pagamento": None,
        "giorni_pagamento": 30,
        "iban": "",
        "fatture_count": 1,
        "source": "auto_from_invoice",
        "dati_incompleti": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Creato automaticamente da fattura — configurare metodo pagamento"
    }

    await db[Collections.SUPPLIERS].insert_one(new_supplier.copy(), session=session)
    result["supplier_created"] = True
    result["supplier_id"] = new_supplier["id"]
    logger.info(f"Nuovo fornitore creato: {supplier_name} (P.IVA: {supplier_vat})")
    # Invalida la cache della lista fornitori: il nuovo fornitore deve
    # comparire SUBITO nella pagina Fornitori, non dopo il TTL.
    try:
        from app.middleware.performance import cache as _cache
        from app.routers.suppliers_module.common import SUPPLIERS_CACHE_KEY as _SCK
        await _cache.clear_pattern(_SCK)
    except Exception:
        pass

    # Alert per configurare il metodo di pagamento
    alert = {
        "id": str(uuid.uuid4()),
        "tipo": "fornitore_senza_metodo_pagamento",
        "titolo": f"Configura metodo pagamento per {supplier_name}",
        "messaggio": f"{supplier_name} (P.IVA: {supplier_vat}) creato da fattura. Configura il metodo di pagamento.",
        "fornitore_id": new_supplier["id"],
        "fornitore_piva": supplier_vat,
        "fornitore_nome": supplier_name,
        "priorita": "alta",
        "letto": False,
        "risolto": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "link": f"/fornitori?piva={supplier_vat}"
    }
    await db["alerts"].insert_one(alert.copy(), session=session)
    result["alert_created"] = True

    await _controlla_dati_fornitore_incoerenti(
        db, new_supplier["id"], supplier_vat, supplier_name,
        new_supplier.get("nazione") or "IT", session=session,
    )

    return result


def _finestra_pagamento(invoice_date: str) -> Optional[tuple]:
    """Finestra plausibile del pagamento: da 5 giorni prima della data fattura
    a 8 mesi dopo. Le date EC sono stringhe YYYY-MM-DD, confrontabili."""
    try:
        d = datetime.strptime((invoice_date or "")[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    return (
        (d - timedelta(days=5)).strftime("%Y-%m-%d"),
        (d + timedelta(days=240)).strftime("%Y-%m-%d"),
    )


async def find_ec_match_for_invoice(db, importo: float, supplier_name: str = "",
                                    invoice_date: str = "", session=None) -> Optional[Dict[str, Any]]:
    """Cerca nell'estratto conto un'uscita compatibile con la fattura.

    Regole:
    - tollera i DUE formati storici della collection (importo assoluto oppure
      con segno negativo per le uscite);
    - esclude i movimenti già riconciliati (un movimento paga UNA fattura);
    - applica una finestra temporale plausibile rispetto alla data fattura;
    - preferisce il match con il nome fornitore in descrizione; senza nome
      accetta il solo importo SOLO dentro la finestra temporale.
    """
    if not importo or importo <= 0:
        return None
    conds: Dict[str, Any] = {
        "tipo": "uscita",
        "riconciliato": {"$ne": True},
        "$or": [
            {"importo": {"$gte": importo - 1, "$lte": importo + 1}},
            {"importo": {"$gte": -importo - 1, "$lte": -importo + 1}},
        ],
    }
    finestra = _finestra_pagamento(invoice_date)
    if finestra:
        conds["data"] = {"$gte": finestra[0], "$lte": finestra[1]}
    nome = (supplier_name or "").upper().strip()
    if nome and len(nome) > 3:
        con_nome = {**conds, "descrizione": {"$regex": re.escape(nome[:8]), "$options": "i"}}
        match = await db["estratto_conto_movimenti"].find_one(con_nome, session=session)
        if match:
            return match
    # Solo importo: accettato solo se la finestra date limita i falsi positivi
    if finestra:
        return await db["estratto_conto_movimenti"].find_one(conds, session=session)
    return None


async def auto_registra_prima_nota(db, invoice: Dict[str, Any], metodo_pagamento: str,
                                   session=None) -> Optional[Dict[str, Any]]:
    """Applica la REGOLA prima nota all'import.

    REGOLA (utente, 18/07/2026 — aggiorna quella del 17/07): quando la
    fattura XML entra nel gestionale,
      - fornitore con metodo pagamento UNIVOCO "cassa" (contanti) → uscita
        registrata SUBITO in Prima Nota Cassa (il contante non lascia
        traccia da riconciliare);
      - fornitore con metodo "banca" → NON viene più marcata pagata in
        automatico: "non devi portare pagata una fattura solo perché ha
        metodo banca — devi sempre riconciliare con estratto conto,
        PayPal o carta". Resta PROVVISORIA finché la riconciliazione
        (estratto conto / PayPal) non trova l'addebito reale;
      - fornitore "misto", senza metodo o ambiguo → PROVVISORIA.

    La scrittura usa il writer canonico registra_pagamento_fattura
    (idempotente per fattura: riferimento FATT-{id}, mai due movimenti per
    la stessa fattura). Ritorna il dict di update applicato alla fattura
    (già persistito), oppure None se resta provvisoria.
    """
    piva = (invoice.get("supplier_vat") or invoice.get("cedente_piva") or "").strip()
    if not piva:
        return None

    forn = await db["fornitori"].find_one(
        {"$or": [{"partita_iva": piva}, {"piva": piva}, {"vat_number": piva}]},
        {"_id": 0, "metodo_pagamento": 1},
        session=session,
    )
    metodo = ((forn or {}).get("metodo_pagamento") or "").strip().lower()
    if not metodo:
        return None

    is_cassa = "contant" in metodo or metodo == "cassa" or "cash" in metodo
    if not is_cassa:
        # BANCA, misto, ambiguo o sconosciuto → PROVVISORIA. Le fatture
        # "banca" diventano pagate SOLO quando la riconciliazione
        # (estratto conto / PayPal / carta) trova l'addebito reale.
        return None

    destinazione = "cassa"
    # NB: registra_pagamento_fattura scrive fuori dalla transazione
    # dell'import (non accetta session); è idempotente per fattura, quindi
    # un eventuale abort dell'import lascia al più un movimento riferito a
    # una fattura che verrà reimportata subito dopo con lo stesso id.
    from app.routers.prima_nota_module.sync import registra_pagamento_fattura
    esito = await registra_pagamento_fattura(invoice, destinazione)
    mov_id = esito.get(destinazione)
    if not mov_id:
        return None

    update: Dict[str, Any] = {
        "pagato": True,
        "paid": True,
        "stato_pagamento": "pagata",
        "metodo_pagamento": "contanti" if is_cassa else "bonifico",
        "data_pagamento": invoice.get("invoice_date") or invoice.get("data_fattura"),
        "prima_nota_id": mov_id,
        "prima_nota_tipo": destinazione,
        "registrata_auto_da_metodo_fornitore": True,
    }
    update["prima_nota_cassa_id" if is_cassa else "prima_nota_banca_id"] = mov_id

    fattura_id = invoice.get("id") or invoice.get("invoice_key")
    if fattura_id:
        await db[Collections.INVOICES].update_one(
            {"id": fattura_id}, {"$set": update}, session=session
        )
    return update


def _normalizza_numero_fattura(numero: str) -> str:
    """Normalizza il numero fattura per il confronto con le vecchie 'fatture
    attese' (maiuscolo, senza spazi, zeri iniziali di ogni blocco rimossi:
    "0000123/A" e "123/A" devono coincidere)."""
    n = (numero or "").upper().strip()
    n = re.sub(r"\s+", "", n)
    n = re.sub(r"\b0+(\d)", r"\1", n)
    return n


async def _riscontra_anticipo_pendente(db, invoice: Dict[str, Any]) -> None:
    """Compatibilità (audit 19/07/2026, review Codex su PR #65): lo scanner
    notifiche Aruba è stato rimosso (nessuna nuova 'fattura attesa' viene più
    creata), ma la collection fatture_attese può contenere record aperti
    creati PRIMA di questa modifica, alcuni già confermati manualmente
    dall'utente con un vero movimento in prima nota (stato
    'confermata_anticipo' + prima_nota_id). Senza questo aggancio, quando
    arriva la fattura XML vera per uno di quei record, l'anticipo resta
    orfano E il fornitore (se a metodo cassa) riceverebbe un SECONDO
    movimento da auto_registra_prima_nota — un doppio pagamento reale.
    Va in idle silenzioso (nessuna query trova nulla) man mano che i
    record aperti si esauriscono: non serve più aggiungerne di nuovi.
    """
    numero_norm = _normalizza_numero_fattura(
        invoice.get("invoice_number") or invoice.get("numero_fattura") or ""
    )
    if not numero_norm:
        return
    importo = float(invoice.get("total_amount") or invoice.get("importo_totale") or 0)

    try:
        candidati = await db["fatture_attese"].find(
            {"stato": {"$in": ["in_attesa_xml", "da_verificare", "confermata_anticipo"]},
             "numero_norm": numero_norm},
            {"_id": 0},
        ).to_list(20)
    except Exception:
        logger.exception("Verifica anticipi pendenti (fatture_attese) non riuscita")
        return

    attesa = None
    for c in candidati:
        imp_attesa = c.get("importo")
        if imp_attesa is None or abs(float(imp_attesa) - importo) <= 0.01:
            attesa = c
            break
    if not attesa:
        return

    now = datetime.now(timezone.utc).isoformat()
    await db["fatture_attese"].update_one(
        {"id": attesa["id"]},
        {"$set": {"stato": "riscontrata", "invoice_id": invoice.get("id"),
                  "riscontrata_at": now}},
    )

    if not (attesa.get("prima_nota_id") and attesa.get("prima_nota_collection")):
        return

    coll = attesa["prima_nota_collection"]
    fattura_id = invoice.get("id")
    await db[coll].update_one(
        {"id": attesa["prima_nota_id"]},
        {"$set": {
            "fattura_id": fattura_id,
            "riferimento": f"FATT-{fattura_id}",
            "numero_fattura": invoice.get("invoice_number") or attesa.get("numero_fattura"),
            "fornitore_piva": invoice.get("supplier_vat") or attesa.get("fornitore_piva"),
            "descrizione": (
                f"Pagamento fattura {invoice.get('invoice_number', '?')} - "
                f"{(invoice.get('supplier_name') or attesa.get('fornitore_nome') or '')[:40]}"
            ),
            "anticipo_da_email": True,
            "updated_at": now,
        }},
    )
    metodo = "cassa" if coll == "prima_nota_cassa" else "banca"
    await db["invoices"].update_one(
        {"id": fattura_id},
        {"$set": {
            "prima_nota_id": attesa["prima_nota_id"],
            "pagato": True,
            "stato_pagamento": "pagata",
            "metodo_pagamento_effettivo": metodo,
            "data_pagamento": now[:10],
            "registrata_da": "anticipo_email_aruba",
        }},
    )
    invoice["prima_nota_id"] = attesa["prima_nota_id"]
    invoice["pagato"] = True
    invoice["stato_pagamento"] = "pagata"
    logger.info(
        f"Fattura {invoice.get('invoice_number')} agganciata al movimento "
        f"anticipato pre-esistente {attesa['prima_nota_id']} ({metodo}) — nessun doppione"
    )


async def process_fattura_to_db(db, parsed: Dict[str, Any], filename: str = "upload.xml") -> Dict[str, Any]:
    """
    Processa e salva una fattura parsata nel database.
    Usata da documenti.py per l'import automatico.

    Fornitore, fattura e (se generata) prima nota vengono scritti in
    un'unica transazione Mongo: se un passaggio fallisce a metà, tutto viene
    annullato invece di lasciare stato incoerente (es. fornitore creato ma
    fattura mai salvata, o prima nota orfana senza il link sulla fattura).
    Il client di test in sandbox (mongomock) non supporta le sessioni: in
    quel caso si procede senza transazione, come prima.

    Args:
        db: Database connection
        parsed: Dati fattura parsati da parse_fattura_xml
        filename: Nome file originale

    Returns:
        Dict con dati fattura salvata
    """
    if parsed.get("error"):
        raise HTTPException(status_code=400, detail=parsed["error"])

    invoice_key = generate_invoice_key(
        parsed.get("invoice_number", ""),
        parsed.get("supplier_vat", ""),
        parsed.get("invoice_date", "")
    )

    duplicate_detail = (
        f"Fattura duplicata: {parsed.get('invoice_number')} del fornitore "
        f"{parsed.get('supplier_name', 'N/A')} esiste già"
    )

    async def _do_import(session) -> Dict[str, Any]:
        # Controlla duplicati (l'indice unico su invoice_key resta la
        # garanzia ultima contro una race fra due transazioni concorrenti)
        existing = await db[Collections.INVOICES].find_one(
            {"invoice_key": invoice_key}, session=session
        )
        if existing:
            raise HTTPException(status_code=409, detail=duplicate_detail)

        # Assicura che il fornitore esista
        supplier_result = await ensure_supplier_exists(db, parsed, session=session)
        supplier_id = supplier_result.get("supplier_id")
        # REGOLA: metodo pagamento SOLO dal fornitore. Se non definito → sospesa (provvisorio)
        metodo_pagamento = supplier_result.get("metodo_pagamento") or "sospesa"

        # FAT_FORN_NON_TROVATO era definito ma mai generato: ensure_supplier_exists
        # ritorna subito supplier_id=None quando manca supplier_vat nell'XML (fattura
        # senza P.IVA fornitore leggibile) — la fattura viene comunque salvata ma
        # resta orfana di fornitore senza nessuna segnalazione. Additivo, non
        # blocca il salvataggio.
        if not supplier_id:
            try:
                from app.services.alert_engine import genera_alert
                await genera_alert(
                    "FAT_FORN_NON_TROVATO", invoice_key, Collections.INVOICES,
                    f"Fattura {parsed.get('invoice_number', '?')} salvata senza fornitore "
                    f"collegato (P.IVA mancante o non estratta dall'XML)",
                    db,
                )
            except Exception:
                logger.exception(f"Errore generazione alert FAT_FORN_NON_TROVATO per {invoice_key}")

        # FAT_TIPO_AMBIGUO era definito ma mai generato: nessuna validazione
        # esisteva sul campo TipoDocumento estratto dall'XML — un codice TDxx
        # non nella tabella standard FatturaPA (TIPO_DOC_MAP in
        # fattura_elettronica_parser.py) passava silenziosamente, con
        # tipo_documento_desc uguale al codice grezzo invece di una
        # descrizione leggibile. Additivo, non blocca il salvataggio.
        tipo_doc = parsed.get("tipo_documento") or ""
        if tipo_doc and tipo_doc not in TIPO_DOC_MAP:
            try:
                from app.services.alert_engine import genera_alert
                await genera_alert(
                    "FAT_TIPO_AMBIGUO", invoice_key, Collections.INVOICES,
                    f"Fattura {parsed.get('invoice_number', '?')}: TipoDocumento '{tipo_doc}' "
                    f"non riconosciuto tra i codici standard FatturaPA",
                    db,
                )
            except Exception:
                logger.exception(f"Errore generazione alert FAT_TIPO_AMBIGUO per {invoice_key}")

        # Calcola data scadenza
        data_fattura_str = parsed.get("invoice_date", "")
        data_scadenza = None
        if data_fattura_str:
            try:
                data_fattura = datetime.strptime(data_fattura_str, "%Y-%m-%d")
                data_scadenza = (data_fattura + timedelta(days=30)).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        # Crea documento fattura
        invoice = {
            "id": str(uuid.uuid4()),
            "invoice_key": invoice_key,
            "supplier_id": supplier_id,
            "invoice_number": parsed.get("invoice_number", ""),
            "invoice_date": parsed.get("invoice_date", ""),
            "data_scadenza": data_scadenza,
            "tipo_documento": parsed.get("tipo_documento", ""),
            "supplier_name": parsed.get("supplier_name", ""),
            "supplier_vat": parsed.get("supplier_vat", ""),
            "total_amount": parsed.get("total_amount", 0),
            "imponibile": parsed.get("imponibile", 0),
            "iva": parsed.get("iva", 0),
            "divisa": parsed.get("divisa", "EUR"),
            "fornitore": parsed.get("fornitore", {}),
            "cliente": parsed.get("cliente", {}),
            "linee": parsed.get("linee", []),
            "riepilogo_iva": parsed.get("riepilogo_iva", []),
            "metodo_pagamento": metodo_pagamento,
            "status": "imported",
            "source": "xml_upload",
            "filename": filename,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "cedente_piva": parsed.get("supplier_vat", ""),
            "cedente_denominazione": parsed.get("supplier_name", ""),
            "numero_fattura": parsed.get("invoice_number", ""),
            "data_fattura": parsed.get("invoice_date", ""),
            "importo_totale": parsed.get("total_amount", 0),
            "anno": int(parsed.get("invoice_date", "2024")[:4]) if parsed.get("invoice_date") else 2024,
            "causali": parsed.get("causali", []),
            "dati_fatture_collegate": parsed.get("dati_fatture_collegate", []),
            "dati_ordine_acquisto": parsed.get("dati_ordine_acquisto", []),
            "tipo_documento_desc": parsed.get("tipo_documento_desc", ""),
        }

        await db[Collections.INVOICES].insert_one(invoice.copy(), session=session)
        invoice.pop("_id", None)

        logger.info(f"Fattura importata: {invoice.get('invoice_number')} - {invoice.get('supplier_name')}")

        # AUTO-REGISTRA in Prima Nota: sempre provvisoria, conferma manuale
        # dell'utente da Prima Nota → Provvisori (vedi auto_registra_prima_nota).
        prima_nota_update = await auto_registra_prima_nota(
            db, invoice, metodo_pagamento, session=session,
        )
        if prima_nota_update:
            # Rispecchia l'update anche sul dict in memoria: altrimenti il
            # valore restituito dalla funzione resta disallineato dal DB
            # (l'invoice salvata risulterebbe "provvisoria" nella risposta
            # anche quando è stata correttamente auto-registrata).
            invoice.update(prima_nota_update)

        # Nota di credito: collega alla fattura originale e ricalcola il netto
        # (best-effort, non blocca l'import se l'originale non si trova).
        nc_update = await _collega_nota_credito(db, invoice, session=session)
        if nc_update:
            invoice.update(nc_update)

        return {"invoice": invoice, "supplier_id": supplier_id, "supplier_result": supplier_result}

    try:
        session = await db.client.start_session()
    except NotImplementedError:
        # Client di test senza supporto sessioni (es. mongomock) → nessuna transazione
        session = None

    try:
        if session is not None:
            async with session:
                outcome = await session.with_transaction(_do_import)
        else:
            outcome = await _do_import(None)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=duplicate_detail)

    invoice = outcome["invoice"]
    supplier_id = outcome["supplier_id"]
    supplier_result = outcome["supplier_result"]
    metodo_pagamento = invoice.get("metodo_pagamento")
    data_scadenza = invoice.get("data_scadenza")

    # --- STORIA FATTURA: riconosci la fattura per invoice_key e, se ha già una
    # storia (es. era stata azzerata), riapplica lo stato derivato salvato
    # (pagamento, IVA, centro di costo, riconciliazioni). Best-effort. ---
    try:
        from app.services import storia_fatture as _storia
        ripristino = await _storia.ripristina_stato(db, invoice)
        if ripristino:
            metodo_pagamento = invoice.get("metodo_pagamento", metodo_pagamento)
            logger.info(f"Storia fattura {invoice_key}: ripristinati {len(ripristino)} "
                        f"campi derivati dal reimport")
    except Exception:
        logger.exception(f"Storia fattura: hook import fallito per {invoice_key}")

    # LIBRO GIORNALE — hook DISATTIVATO (A7, scelta utente 2026-07-13): il
    # registro parallelo scritture_contabili non riceve più scritture; il
    # libro giornale/mastro legge il registro UNICO movimenti_contabili, che
    # la fattura raggiunge alla registrazione contabile (motore §6.1,
    # "Registra fatture" dal Piano dei Conti). scritture_contabili resta come
    # archivio storico. Vedi LOGICA_LIBRO_MASTRO.md.

    # --- EVENT BUS: propaga evento fattura creata (upload manuale) ---
    # Fuori dalla transazione per design: è già gestita come fail-safe/
    # best-effort (try/except sotto) e non deve bloccare né essere
    # annullata se l'import principale (già commesso) è andato a buon fine.
    # Attiva i 4 handler su FATTURA_CREATED: crea_partita, alert_fornitore,
    # audit, righe_magazzino. Fail-safe per non bloccare l'import.
    try:
        from app.services.event_bus import propagate_event, EventTypes
        fornitore_data = invoice.get("fornitore") or {}
        await propagate_event(EventTypes.FATTURA_CREATED, {
            "fattura_id": invoice["id"],
            "numero_documento": invoice.get("invoice_number", ""),
            "tipo_documento": invoice.get("tipo_documento", "TD01"),
            "importo_totale": invoice.get("total_amount", 0),
            "fornitore_id": supplier_id,
            "fornitore_ragione_sociale": invoice.get("supplier_name", ""),
            "fornitore_nuovo": supplier_result.get("nuovo", False),
            "fornitore_iban": fornitore_data.get("iban") if isinstance(fornitore_data, dict) else None,
            "metodo_pagamento": metodo_pagamento,
            "data_documento": invoice.get("invoice_date", ""),
            "data_scadenza": data_scadenza,
            "stato": invoice.get("status", "imported"),
            "pagato": invoice.get("stato_pagamento") == "pagata",
            "righe_linee": invoice.get("linee", []),
            "imponibile": invoice.get("imponibile", 0),
            "iva": invoice.get("iva", 0),
        }, db, source_module="fatture_upload_manuale")
    except Exception:
        logger.exception("Errore propagazione evento fattura.created (upload manuale)")

    try:
        await _riscontra_anticipo_pendente(db, invoice)
    except Exception:
        logger.exception(f"Riscontro anticipo pendente fallito per {invoice.get('invoice_number')}")

    return invoice


async def find_check_numbers_for_invoice(db, importo: float, data_fattura: str, fornitore: str) -> Optional[Dict[str, Any]]:
    """
    Cerca nell'estratto conto i numeri degli assegni che corrispondono all'importo della fattura.
    
    Returns:
        Dict con numeri assegni trovati o None
    """
    try:
        if not importo or importo <= 0:
            return None
        
        # Tolleranza importo
        importo_min = importo - 1.0
        importo_max = importo + 1.0
        
        # Range date (90 giorni prima e dopo la data fattura)
        data_min = None
        data_max = None
        if data_fattura:
            try:
                data_doc = datetime.strptime(data_fattura, "%Y-%m-%d")
                data_min = (data_doc - timedelta(days=90)).strftime("%Y-%m-%d")
                data_max = (data_doc + timedelta(days=90)).strftime("%Y-%m-%d")
            except Exception:
                pass
        
        # Cerca match singolo per importo
        query = {
            "tipo": "uscita",
            "descrizione": {"$regex": "assegno", "$options": "i"},
            "$or": [
                {"importo": {"$gte": importo_min, "$lte": importo_max}},
                {"importo": {"$gte": -importo_max, "$lte": -importo_min}}
            ]
        }
        if data_min and data_max:
            query["data"] = {"$gte": data_min, "$lte": data_max}
        
        match = await db["estratto_conto_movimenti"].find_one(query, {"_id": 0})
        
        if match:
            # Estrai numero assegno dalla descrizione
            descrizione = match.get("descrizione", "")
            numero_assegno = None
            
            patterns = [
                r'NUM:\s*(\d+)',
                r'ASSEGNO\s*N\.?\s*(\d+)',
                r'ASS\.?\s*N?\.?\s*(\d+)',
            ]
            for pattern in patterns:
                m = re.search(pattern, descrizione, re.IGNORECASE)
                if m:
                    numero_assegno = m.group(1)
                    break
            
            if numero_assegno:
                return {
                    "tipo": "singolo",
                    "numero_assegno": numero_assegno,
                    "descrizione": descrizione,
                    "data": match.get("data"),
                    "importo": abs(match.get("importo", 0))
                }
        
        # Se non trovato singolo, cerca combinazione assegni multipli
        from itertools import combinations
        
        query_multi = {
            "descrizione": {"$regex": "assegno", "$options": "i"}
        }
        if data_min and data_max:
            query_multi["data"] = {"$gte": data_min, "$lte": data_max}
        
        assegni = await db["estratto_conto_movimenti"].find(query_multi, {"_id": 0}).limit(50).to_list(50)
        
        if len(assegni) >= 2:
            for num in [2, 3, 4]:
                for combo in combinations(assegni, num):
                    somma = sum(abs(a.get("importo", 0)) for a in combo)
                    if importo_min <= somma <= importo_max:
                        numeri = []
                        for a in combo:
                            for pattern in patterns:
                                m = re.search(pattern, a.get("descrizione", ""), re.IGNORECASE)
                                if m:
                                    numeri.append(m.group(1))
                                    break
                        
                        if numeri:
                            return {
                                "tipo": "multiplo",
                                "numeri_assegni": numeri,
                                "numero_assegno": ", ".join(numeri),
                                "num_assegni": len(combo),
                                "somma": somma
                            }
        
        return None
        
    except Exception as e:
        logger.error(f"Errore ricerca assegni per fattura: {e}")
        return None


async def riconcilia_con_estratto_conto(db, importo: float, data_fattura: str, fornitore: str, numero_fattura: str = None) -> Dict[str, Any]:
    """
    Cerca riconciliazione nell'estratto conto (bonifici, assegni, qualsiasi movimento).
    
    REGOLE DI MATCH (in ordine di priorità):
    1. Importo + Nome fornitore/beneficiario (MATCH FORTE)
    2. Importo + Numero fattura in causale (MATCH FORTE)  
    3. Solo importo esatto con tolleranza minima (MATCH DEBOLE)
    
    NOTE: La DATA NON È un criterio obbligatorio perché un bonifico può essere:
    - Contestuale alla fattura
    - Differito rispetto alla fattura
    - In anticipo rispetto alla data fattura
    
    Returns:
        Dict con info riconciliazione o {"trovato": False}
    """
    result = {
        "trovato": False,
        "metodo_suggerito": None,
        "movimento_banca_id": None,
        "data_pagamento": None,
        "descrizione_banca": None,
        "match_tipo": None,
        "match_score": 0
    }
    
    try:
        if not importo or importo <= 0:
            return result
        
        # Tolleranza importo: ±1€ o ±1% (usa il maggiore)
        tolleranza = max(1.0, importo * 0.01)
        importo_min = importo - tolleranza
        importo_max = importo + tolleranza
        
        # Normalizza nome fornitore per ricerca (estrai parole significative)
        fornitore_words = []
        if fornitore:
            # Rimuovi forme societarie e parole comuni
            fornitore_clean = re.sub(
                r'(S\.?R\.?L\.?|S\.?P\.?A\.?|S\.?N\.?C\.?|S\.?A\.?S\.?|DI|DEL|DELLA|IL|LA|LO|GLI|LE|UN|UNA|E|ED|\d+)', 
                '', 
                fornitore, 
                flags=re.IGNORECASE
            )
            fornitore_words = [w.strip() for w in fornitore_clean.split() if len(w.strip()) > 2]
        
        # Query base: cerca movimenti in uscita con importo compatibile
        # NON filtrare per data - lascia che il match avvenga su altri criteri
        query = {
            "tipo": "uscita",
            "$or": [
                {"importo": {"$gte": importo_min, "$lte": importo_max}},
                {"importo": {"$gte": -importo_max, "$lte": -importo_min}}  # Importi negativi
            ],
            # Escludi movimenti già riconciliati
            "riconciliato": {"$ne": True}
        }
        
        # Cerca nell'estratto conto (senza limite di data)
        movimenti = await db["estratto_conto_movimenti"].find(query, {"_id": 0}).limit(50).to_list(50)
        
        best_match = None
        best_score = 0
        
        for mov in movimenti:
            descrizione = (mov.get("descrizione", "") or "").upper()
            causale = (mov.get("causale", "") or "").upper()
            beneficiario = (mov.get("beneficiario", "") or "").upper()
            testo_ricerca = f"{descrizione} {causale} {beneficiario}"
            
            score = 0
            match_reasons = []
            
            # 1. Match per nome fornitore (PESO: 50 punti)
            if fornitore_words:
                matches_found = 0
                for word in fornitore_words[:4]:  # Max 4 parole significative
                    if word.upper() in testo_ricerca:
                        matches_found += 1
                if matches_found > 0:
                    # Più parole matchano, più alto il punteggio
                    score += 25 + (matches_found * 10)
                    match_reasons.append(f"fornitore({matches_found} parole)")
            
            # 2. Match per numero fattura in causale (PESO: 40 punti)
            if numero_fattura:
                # Normalizza numero fattura (rimuovi spazi, slash)
                num_clean = numero_fattura.replace(" ", "").replace("/", "").upper()
                if num_clean in testo_ricerca.replace(" ", "").replace("/", ""):
                    score += 40
                    match_reasons.append("numero_fattura")
            
            # 3. Match per importo esatto (PESO: 30 punti)
            importo_mov = abs(mov.get("importo", 0))
            differenza = abs(importo_mov - importo)
            if differenza < 0.10:  # Quasi esatto
                score += 30
                match_reasons.append("importo_esatto")
            elif differenza < 0.50:
                score += 20
                match_reasons.append("importo_quasi")
            elif differenza < tolleranza:
                score += 10
                match_reasons.append("importo_tolleranza")
            
            # Se abbiamo un match significativo (score >= 50)
            if score >= 50 and score > best_score:
                # Determina metodo pagamento dalla descrizione
                metodo = "bonifico"  # Default
                if any(x in descrizione for x in ["BONIFICO", "BON.", "SEPA"]):
                    metodo = "bonifico"
                elif any(x in descrizione for x in ["ASSEGNO", "ASS.", "CHK"]):
                    metodo = "assegno"
                elif any(x in descrizione for x in ["PRELIEVO", "BANCOMAT", "CASH"]):
                    metodo = "cassa"
                elif any(x in descrizione for x in ["RID", "SDD", "ADDEBITO"]):
                    metodo = "rid"
                
                best_match = {
                    "trovato": True,
                    "metodo_suggerito": metodo,
                    "movimento_banca_id": mov.get("id"),
                    "data_pagamento": mov.get("data"),
                    "descrizione_banca": descrizione[:100],
                    "importo_banca": importo_mov,
                    "match_tipo": " + ".join(match_reasons),
                    "match_score": score
                }
                best_score = score
        
        if best_match:
            return best_match
        
        return result
        
    except Exception as e:
        logger.error(f"Errore riconciliazione estratto conto: {e}")
        return result


def generate_invoice_key(invoice_number: str, supplier_vat: str, invoice_date: str) -> str:
    """Genera chiave univoca per fattura: numero_piva_data"""
    key = f"{invoice_number}_{supplier_vat}_{invoice_date}"
    return key.replace(" ", "").replace("/", "-").upper()


def extract_xml_from_zip(zip_content: bytes, zip_filename: str = "archive.zip") -> List[Dict[str, Any]]:
    """
    Estrae tutti i file XML da un archivio ZIP.
    Supporta ZIP annidati (ZIP dentro ZIP).
    
    Returns:
        Lista di dict con {"filename": str, "content": bytes}
    """
    xml_files = []

    try:
        with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zf:
            # Anti zip-bomb: controlla la dimensione DECOMPRESSA dichiarata e il
            # numero di elementi PRIMA di leggere qualsiasi contenuto.
            from app.utils.upload_guard import controlla_zip
            infos = zf.infolist()
            controlla_zip(len(infos), sum(getattr(i, "file_size", 0) for i in infos))
            for name in zf.namelist():
                # Salta directory
                if name.endswith('/'):
                    continue
                
                try:
                    file_content = zf.read(name)
                    
                    if name.lower().endswith('.xml') or is_p7m_content(name):
                        # File XML (o P7M firmato) trovato
                        xml_files.append({
                            "filename": f"{zip_filename}/{name}",
                            "content": file_content
                        })
                    elif name.lower().endswith('.zip'):
                        # ZIP annidato - estrai ricorsivamente
                        nested_xmls = extract_xml_from_zip(file_content, f"{zip_filename}/{name}")
                        xml_files.extend(nested_xmls)
                except Exception as e:
                    logger.warning(f"Errore estrazione {name}: {str(e)}")
                    continue
    except zipfile.BadZipFile:
        raise ValueError(f"File ZIP corrotto o non valido: {zip_filename}")
    
    return xml_files


@router.post("/upload-xml")
@handle_errors
async def upload_fattura_xml(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Upload e parse di una singola fattura elettronica XML (o P7M firmato).

    Usa la stessa pipeline condivisa (process_xml_bytes) di Drive/Email/
    Documenti inbox, per non avere logiche di import diverse a seconda del
    canale (metodo fornitore, prima nota, event bus, dedup: tutti uguali).
    """
    filename = file.filename or "upload.xml"
    if not (filename.lower().endswith(".xml") or is_p7m_content(filename)):
        raise HTTPException(status_code=400, detail="Il file deve essere in formato XML o P7M")

    from app.utils.upload_guard import leggi_upload
    content = await leggi_upload(file)
    db = Database.get_db()
    result = await process_xml_bytes(db, content, filename, source="xml_upload_manuale")

    if result.get("status") == "duplicate":
        raise HTTPException(
            status_code=409,
            detail=f"Fattura già presente: {result.get('invoice_number')}"
        )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error", "Errore import fattura"))

    invoice = await db[Collections.INVOICES].find_one({"id": result["id"]}, {"_id": 0})
    return {
        "success": True,
        "message": f"Fattura {result.get('invoice_number')} importata",
        "invoice": invoice,
        "supplier": {"nome": result.get("supplier")},
    }


async def process_xml_bytes(db, content: bytes, filename: str, source: str = "xml_upload",
                             applica_filtro_anno: bool = False) -> Dict[str, Any]:
    """Pipeline CONDIVISA per importare una singola fattura XML dai suoi bytes.

    Usata sia dall'upload bulk (`/upload-xml-bulk`) sia dall'ingest Google Drive,
    per non duplicare la logica di decodifica/parse/dedup/import.

    `applica_filtro_anno` (richiesta utente 14/07/2026, SOLO per l'ingest
    automatico dalla cartella Drive condivisa: "carica solo quelle con data
    fattura 2026, gli anni precedenti metti in un archivio fatture
    consultabile per visione personale"): se True e la data fattura non è
    nell'anno corrente, la fattura NON entra nel flusso contabile attivo
    (niente Prima Nota, scadenzario, alert, magazzino) — viene solo
    archiviata per consultazione (vedi archivia_fattura_storica). Default
    False: l'upload manuale via UI e le altre fonti (PEC/SDI, fatture
    estere) restano invariate, un utente che carica volontariamente una
    fattura di un anno passato si aspetta che venga registrata normalmente.

    Ritorna un dict con `status` in {"imported", "duplicate", "error",
    "archiviata"}.
    """
    # 0. Busta firmata .p7m (CAdES): estrai l'XML interno prima di decodificare.
    if is_p7m_content(filename):
        extracted = extract_xml_from_p7m(content)
        if extracted is None:
            # Alcuni P7M circolano ri-codificati in base64: decodifica e riprova.
            try:
                import base64 as _b64
                extracted = extract_xml_from_p7m(_b64.b64decode(content))
            except Exception:
                extracted = None
        if extracted is None:
            return {"status": "error", "filename": filename,
                    "error": "Impossibile estrarre l'XML dalla busta firmata .p7m"}
        content = extracted

    # 1. Decodifica (prova più encoding)
    xml_content = None
    for enc in ('utf-8', 'utf-8-sig', 'latin-1', 'iso-8859-1'):
        try:
            xml_content = content.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if not xml_content:
        return {"status": "error", "filename": filename, "error": "Decodifica fallita"}

    # 2. Parse fattura elettronica
    parsed = parse_fattura_xml(xml_content)
    if parsed.get("error"):
        return {"status": "error", "filename": filename, "error": parsed["error"]}

    # Un file FatturaPA può contenere PIÙ fatture raggruppate (più
    # <FatturaElettronicaBody> sotto lo stesso header/CedentePrestatore —
    # caso reale per fatture differite spedite insieme). Prima venivano
    # lette solo dal parser e la fattura in più andava persa silenziosamente
    # (importo/righe mai registrati). "altri_body" contiene le fatture
    # aggiuntive trovate nello stesso file: vanno importate anche loro, una
    # per una, con la stessa logica della prima (bug reale 19/07/2026).
    altri_body = parsed.pop("_altri_body", None) or []

    async def _importa_una(p: Dict[str, Any]) -> Dict[str, Any]:
        if applica_filtro_anno:
            from app.services.config_import import get_anno_importazione_attivo
            invoice_date = p.get("invoice_date") or ""
            anno_fattura = int(invoice_date[:4]) if invoice_date[:4].isdigit() else None
            anno_attivo = await get_anno_importazione_attivo(db)
            # Data mancante/illeggibile: NON archiviare silenziosamente una
            # fattura che potrebbe essere dell'anno attivo solo per un XML
            # malformato — resta nel flusso attivo, dove è comunque visibile e
            # correggibile (a differenza dell'archivio storico, pensato per
            # sola consultazione).
            if anno_fattura and anno_fattura != anno_attivo:
                return await archivia_fattura_storica(db, p, filename, source, xml_raw=xml_content)

        return await import_parsed_invoice(db, p, filename, source, xml_raw=xml_content)

    risultato = await _importa_una(parsed)

    if altri_body:
        altri_risultati = [await _importa_una(p) for p in altri_body]
        tutti = [risultato] + altri_risultati
        # Tutti i chiamanti (upload manuale, bulk, Drive, email) leggono SOLO
        # lo status di primo livello: se il primo body non è quello con
        # l'esito "migliore", promuovi il migliore a risultato principale —
        # altrimenti il chiamante segnala duplicato/errore (upload manuale
        # arriva a rispondere 409 all'utente) o conta il file come solo
        # archiviato mentre una fattura ATTIVA è stata comunque scritta in
        # contabilità come effetto collaterale invisibile. "imported" (fattura
        # nel flusso contabile attivo) vale più di "archiviata" (solo
        # consultazione storica, richiesta utente 14/07/2026): con filtro
        # anno attivo e un file che raggruppa una fattura di un anno passato
        # con una dell'anno corrente, il file va sempre segnalato come
        # "imported", mai come "archiviata" (bug reale, review Codex PR #71).
        _PRIORITA = {"imported": 2, "archiviata": 1}
        migliore = max(tutti, key=lambda r: _PRIORITA.get(r.get("status"), 0))
        if _PRIORITA.get(migliore.get("status"), 0) > _PRIORITA.get(risultato.get("status"), 0):
            tutti.remove(migliore)
            risultato = migliore
            altri_risultati = tutti
        risultato = dict(risultato)
        risultato["multi_body_xml"] = True
        risultato["altre_fatture_stesso_file"] = altri_risultati

    return risultato


async def archivia_fattura_storica(db, parsed: Dict[str, Any], filename: str, source: str,
                                    xml_raw: Optional[str] = None) -> Dict[str, Any]:
    """Archivia una fattura di un anno precedente SENZA farla entrare nel
    flusso contabile attivo (richiesta utente 14/07/2026: import Drive solo
    per l'anno corrente, il resto "in un archivio fatture consultabile per
    visione personale"). A differenza di import_parsed_invoice, qui NON si
    chiama ensure_supplier_exists (nessun nuovo fornitore/statistica creata
    nell'anagrafica attiva solo per una fattura storica), NON si registra
    Prima Nota, NON si propaga l'evento fattura.created (niente scadenzario/
    alert/magazzino). Il documento resta comunque nella stessa collection
    `invoices` — la pagina Archivio Fatture Ricevute lo mostra già
    selezionando quell'anno — ma marcato `stato_import: "archivio_storico"`
    così i job schedulati che scansionano `invoices` per Prima Nota/alert/
    scadenzario possono riconoscerlo ed escluderlo esplicitamente.
    """
    invoice_key = generate_invoice_key(
        parsed.get("invoice_number", ""),
        parsed.get("supplier_vat", ""),
        parsed.get("invoice_date", ""),
    )
    if await db[Collections.INVOICES].find_one({"invoice_key": invoice_key}):
        return {"status": "duplicate", "filename": filename,
                "invoice_number": parsed.get("invoice_number")}

    invoice_date = parsed.get("invoice_date", "")
    invoice = {
        "id": str(uuid.uuid4()),
        "invoice_key": invoice_key,
        "supplier_id": None,
        "invoice_number": parsed.get("invoice_number", ""),
        "invoice_date": invoice_date,
        "tipo_documento": parsed.get("tipo_documento", ""),
        "tipo_documento_desc": parsed.get("tipo_documento_desc", ""),
        "supplier_name": parsed.get("supplier_name", ""),
        "supplier_vat": parsed.get("supplier_vat", ""),
        "total_amount": float(parsed.get("total_amount", 0) or 0),
        "imponibile": float(parsed.get("imponibile", 0) or 0),
        "iva": float(parsed.get("iva", 0) or 0),
        "divisa": parsed.get("divisa", "EUR"),
        "fornitore": parsed.get("fornitore", {}),
        "cliente": parsed.get("cliente", {}),
        "linee": parsed.get("linee", []),
        "riepilogo_iva": parsed.get("riepilogo_iva", []),
        "causali": parsed.get("causali", []),
        "status": "archiviata",
        "stato_import": "archivio_storico",
        "source": source,
        "filename": filename,
        "xml_raw": xml_raw,
        "xml_body_index": parsed.get("body_index", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cedente_piva": parsed.get("supplier_vat", ""),
        "cedente_denominazione": parsed.get("supplier_name", ""),
        "numero_fattura": parsed.get("invoice_number", ""),
        "data_fattura": invoice_date,
        "importo_totale": float(parsed.get("total_amount", 0) or 0),
        "anno": int(invoice_date[:4]) if invoice_date[:4].isdigit() else None,
    }
    await db[Collections.INVOICES].insert_one(invoice.copy())
    invoice.pop("_id", None)

    return {"status": "archiviata", "filename": filename,
            "invoice_number": parsed.get("invoice_number"),
            "supplier": parsed.get("supplier_name"), "id": invoice["id"]}


async def import_parsed_invoice(db, parsed: Dict[str, Any], filename: str, source: str,
                                 xml_raw: Optional[str] = None,
                                 piva_validator=_piva_plausibile) -> Dict[str, Any]:
    """Pipeline CONDIVISA per importare una fattura già "parsata" in un dict
    con lo schema di `parse_fattura_xml` (invoice_number/supplier_vat/...).

    Estratta da `process_xml_bytes` (passi 3-7) per essere riusata anche
    dalle fatture ESTERE arrivate come PDF via email, estratte via AI
    (vedi `process_fattura_estera_pdf`): stessa dedup, stesso fornitore,
    stessa prima nota provvisoria, stesso event bus — qualunque sia la
    fonte del `parsed`. `piva_validator` passa a `ensure_supplier_exists`.
    """
    # 3. Dedup tramite invoice_key
    invoice_key = generate_invoice_key(
        parsed.get("invoice_number", ""),
        parsed.get("supplier_vat", ""),
        parsed.get("invoice_date", ""),
    )
    if await db[Collections.INVOICES].find_one({"invoice_key": invoice_key}):
        return {"status": "duplicate", "filename": filename,
                "invoice_number": parsed.get("invoice_number")}

    # 4. Fornitore (crea se nuovo) + metodo pagamento
    supplier_result = await ensure_supplier_exists(db, parsed, piva_validator=piva_validator)
    # REGOLA: metodo pagamento SOLO dal fornitore (mai dal documento).
    # Se il fornitore non ha un metodo → "sospesa" → resta nei provvisori.
    metodo_pagamento = supplier_result.get("metodo_pagamento") or "sospesa"

    # Data scadenza: data fattura + 30 giorni (come l'upload manuale)
    invoice_date = parsed.get("invoice_date", "")
    data_scadenza = None
    if invoice_date:
        try:
            data_scadenza = (datetime.strptime(invoice_date, "%Y-%m-%d")
                             + timedelta(days=30)).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass

    # 5. Documento fattura + insert (stessi campi dell'upload manuale, inclusi
    #    i campi speculari in italiano usati da filtri e pagine contabili)
    invoice = {
        "id": str(uuid.uuid4()),
        "invoice_key": invoice_key,
        "supplier_id": supplier_result.get("supplier_id"),
        "invoice_number": parsed.get("invoice_number", ""),
        "invoice_date": invoice_date,
        "data_scadenza": data_scadenza,
        "tipo_documento": parsed.get("tipo_documento", ""),
        "tipo_documento_desc": parsed.get("tipo_documento_desc", ""),
        "supplier_name": parsed.get("supplier_name", ""),
        "supplier_vat": parsed.get("supplier_vat", ""),
        "total_amount": float(parsed.get("total_amount", 0) or 0),
        "imponibile": float(parsed.get("imponibile", 0) or 0),
        "iva": float(parsed.get("iva", 0) or 0),
        "divisa": parsed.get("divisa", "EUR"),
        "fornitore": parsed.get("fornitore", {}),
        "cliente": parsed.get("cliente", {}),
        "linee": parsed.get("linee", []),
        "riepilogo_iva": parsed.get("riepilogo_iva", []),
        "causali": parsed.get("causali", []),
        "dati_fatture_collegate": parsed.get("dati_fatture_collegate", []),
        "dati_ordine_acquisto": parsed.get("dati_ordine_acquisto", []),
        "metodo_pagamento": metodo_pagamento,
        "status": "imported",
        "source": source,
        "filename": filename,
        "xml_raw": xml_raw,
        "xml_body_index": parsed.get("body_index", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cedente_piva": parsed.get("supplier_vat", ""),
        "cedente_denominazione": parsed.get("supplier_name", ""),
        "numero_fattura": parsed.get("invoice_number", ""),
        "data_fattura": invoice_date,
        "importo_totale": float(parsed.get("total_amount", 0) or 0),
        "anno": int(invoice_date[:4]) if invoice_date[:4].isdigit() else None,
    }
    await db[Collections.INVOICES].insert_one(invoice.copy())
    invoice.pop("_id", None)

    # Giacenze magazzino: aggiornate qui sotto tramite l'event bus (punto 7,
    # EventTypes.FATTURA_CREATED -> on_fattura_righe_magazzino), NON in modo
    # sincrono in questa funzione. Vedi memoria/moduli/MAGAZZINO.md — questo
    # commento diceva erroneamente che l'import fatture non tocca mai
    # warehouse_inventory; in realtà l'handler dell'event bus lo aggiorna.

    # 6. Prima Nota: sempre provvisoria, conferma manuale dell'utente da
    #    Prima Nota → Provvisori (vedi auto_registra_prima_nota).
    try:
        await auto_registra_prima_nota(db, invoice, metodo_pagamento)
    except Exception:
        logger.exception(f"Errore auto-registrazione prima nota per {filename}")

    # Nota di credito: collega alla fattura originale e ricalcola il netto.
    try:
        nc_update = await _collega_nota_credito(db, invoice)
        if nc_update:
            invoice.update(nc_update)
    except Exception:
        logger.exception(f"Errore collegamento nota di credito per {filename}")

    # 7. Event bus: crea partita scadenziario, alert fornitore, audit.
    #    Best-effort: un errore qui non deve far fallire l'import.
    try:
        from app.services.event_bus import propagate_event, EventTypes
        fornitore_data = invoice.get("fornitore") or {}
        await propagate_event(EventTypes.FATTURA_CREATED, {
            "fattura_id": invoice["id"],
            "numero_documento": invoice.get("invoice_number", ""),
            "tipo_documento": invoice.get("tipo_documento") or "TD01",
            "importo_totale": invoice.get("total_amount", 0),
            "fornitore_id": supplier_result.get("supplier_id"),
            "fornitore_ragione_sociale": invoice.get("supplier_name", ""),
            "fornitore_nuovo": supplier_result.get("supplier_created", False),
            "fornitore_iban": fornitore_data.get("iban") if isinstance(fornitore_data, dict) else None,
            "metodo_pagamento": metodo_pagamento,
            "data_documento": invoice_date,
            "data_scadenza": data_scadenza,
            "stato": invoice.get("status", "imported"),
            "pagato": invoice.get("stato_pagamento") == "pagata",
            "righe_linee": invoice.get("linee", []),
            "imponibile": invoice.get("imponibile", 0),
            "iva": invoice.get("iva", 0),
        }, db, source_module=f"fatture_upload_{source}")
    except Exception:
        logger.exception(f"Errore propagazione evento fattura.created ({source})")

    return {"status": "imported", "filename": filename,
            "invoice_number": parsed.get("invoice_number"),
            "supplier": parsed.get("supplier_name"), "id": invoice["id"]}


async def process_fattura_estera_pdf(db, pdf_base64: str, filename: str,
                                      source: str = "email_gmail_estera",
                                      documento_inbox_id: Optional[str] = None) -> Dict[str, Any]:
    """Fattura ESTERA arrivata come PDF via email (mai XML: lo SDI è solo
    italiano). Estrae i dati con l'AI già usata per gli altri documenti
    (`document_ai_extractor`, stessa ANTHROPIC_API_KEY già configurata) e la
    importa con la pipeline condivisa `import_parsed_invoice` — stessa
    dedup, stesso fornitore, stessa prima nota provvisoria — così il
    matching PayPal (`auto_associa_transazioni`) e bonifico
    (`riconcilia_movimenti_banca`), e l'alert di scadenza
    `FAT_DA_PAGARE_SCADUTA` già esistenti la prendono in carico da soli,
    senza nessun codice nuovo lato riconciliazione.

    Se l'estrazione fallisce o non legge né numero né importo, non crea
    nulla: meglio lasciare il PDF solo archiviato (comportamento di prima)
    che registrare una fattura con dati inventati.

    A differenza delle fatture XML italiane (lettura deterministica), la
    fattura creata qui viene marcata `verifica_ai: "in_attesa"` e resta
    nella coda `/api/fatture-estere/da-verificare` finché l'utente non
    conferma o corregge i dati letti (scelta utente 14/07/2026, per avere
    un rating di affidabilità della lettura AI per fornitore).
    """
    try:
        from app.services.document_ai_extractor import process_document_from_base64
        result = await process_document_from_base64(pdf_base64, filename, document_type="fattura")
    except Exception as e:
        logger.warning(f"Estrazione AI fallita per fattura estera {filename}: {e}")
        return {"status": "extraction_error", "filename": filename, "error": str(e)}

    structured = (result or {}).get("structured_data") or {}
    if not structured.get("success"):
        return {"status": "extraction_error", "filename": filename,
                "error": structured.get("error") or (result or {}).get("error") or "estrazione non riuscita"}

    parsed = _ai_fattura_a_parsed(structured.get("data") or {})

    if not parsed.get("invoice_number") and not parsed.get("total_amount"):
        return {"status": "dati_insufficienti", "filename": filename}

    esito = await import_parsed_invoice(db, parsed, filename, source, xml_raw=None,
                                         piva_validator=_piva_estera_plausibile)

    if esito.get("status") == "imported":
        try:
            update = {"verifica_ai": "in_attesa"}
            if documento_inbox_id:
                update["documento_inbox_id"] = documento_inbox_id
            await db[Collections.INVOICES].update_one({"id": esito["id"]}, {"$set": update})

            from app.services.alert_engine import genera_alert
            alert = await genera_alert(
                "FAT_ESTERA_DA_VERIFICARE", esito["id"], Collections.INVOICES,
                f"Fattura estera '{esito.get('invoice_number', '?')}' di "
                f"{esito.get('supplier', '?')} letta dall'AI: verifica i dati prima "
                f"che vengano usati per la riconciliazione",
                db, extra={"filename": filename},
            )
            if alert:
                await db["alerts"].update_one(
                    {"id": alert["id"]}, {"$set": {"link": "/fatture-estere-verifica"}}
                )
        except Exception:
            logger.exception(f"Errore marcatura verifica_ai/alert per fattura estera {esito.get('id')}")

    return esito


def _ai_fattura_a_parsed(data: Dict[str, Any]) -> Dict[str, Any]:
    """Converte il JSON estratto dall'AI (schema `document_ai_extractor`,
    prompt "fattura": numero_fattura/data_fattura/fornitore/totale/...) nello
    schema `parsed` atteso da `import_parsed_invoice` — lo stesso prodotto da
    `parse_fattura_xml` per le fatture italiane."""
    from app.services.document_data_saver import parse_date, parse_amount

    fornitore = data.get("fornitore") or {}
    cliente = data.get("cliente") or {}
    invoice_date = parse_date(data.get("data_fattura")) or ""
    supplier_vat = (fornitore.get("partita_iva") or "").strip().upper()
    # Prefisso paese della P.IVA UE (es. "DE123456789" -> "DE"): evita che
    # ensure_supplier_exists dia per scontato "IT" su un fornitore estero e
    # generi un falso alert "P.IVA non standard italiana".
    nazione = supplier_vat[:2] if len(supplier_vat) > 2 and supplier_vat[:2].isalpha() else ""

    return {
        "invoice_number": (data.get("numero_fattura") or "").strip(),
        "invoice_date": invoice_date,
        "supplier_vat": supplier_vat,
        "supplier_name": (fornitore.get("denominazione") or "").strip(),
        "total_amount": parse_amount(data.get("totale")),
        "imponibile": parse_amount(data.get("imponibile")),
        "iva": parse_amount(data.get("iva")),
        "divisa": "EUR",
        "tipo_documento": "",
        "tipo_documento_desc": "",
        "fornitore": {
            "codice_fiscale": fornitore.get("codice_fiscale") or "",
            "indirizzo": fornitore.get("indirizzo") or "",
            "nazione": nazione,
        },
        "cliente": {
            "denominazione": cliente.get("denominazione") or "",
            "partita_iva": cliente.get("partita_iva") or "",
            "codice_fiscale": cliente.get("codice_fiscale") or "",
        },
        "linee": [],
        "riepilogo_iva": [],
        "causali": [],
        "dati_fatture_collegate": [],
        "dati_ordine_acquisto": [],
    }


@router.post("/upload-xml-bulk")
@handle_errors
async def upload_fatture_xml_bulk(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    """
    Upload massivo di fatture elettroniche XML.
    Supporta:
    - File XML multipli
    - File ZIP contenenti XML (anche annidati)
    """
    if not files:
        raise HTTPException(status_code=400, detail="Nessun file caricato")
    
    results = {
        "success": [], "errors": [], "duplicates": [],
        "total": 0, "imported": 0, "failed": 0, "skipped_duplicates": 0
    }
    
    db = Database.get_db()
    
    # Raccoglie tutti i file XML (inclusi quelli estratti da ZIP)
    xml_files = []
    
    from app.utils.upload_guard import leggi_upload
    for file in files:
        filename = file.filename or "unknown"
        content = await leggi_upload(file)

        if filename.lower().endswith('.zip'):
            # Estrai XML da ZIP
            try:
                extracted = extract_xml_from_zip(content, filename)
                xml_files.extend(extracted)
                logger.info(f"Estratti {len(extracted)} XML da {filename}")
            except Exception as e:
                results["errors"].append({"filename": filename, "error": f"Errore ZIP: {str(e)}"})
                results["failed"] += 1
        elif filename.lower().endswith('.xml') or is_p7m_content(filename):
            xml_files.append({"filename": filename, "content": content})
        else:
            results["errors"].append({"filename": filename, "error": "Formato non supportato (solo XML, P7M o ZIP)"})
            results["failed"] += 1
    
    results["total"] = len(xml_files)
    
    # Processa tutti gli XML con la pipeline condivisa (vedi process_xml_bytes)
    for xml_file in xml_files:
        filename = xml_file["filename"]
        res = await process_xml_bytes(db, xml_file["content"], filename, source="xml_bulk_upload")
        status = res.get("status")
        if status == "imported":
            results["success"].append({
                "filename": filename,
                "invoice_number": res.get("invoice_number"),
                "supplier": res.get("supplier"),
            })
            results["imported"] += 1
        elif status == "duplicate":
            results["duplicates"].append({
                "filename": filename,
                "invoice_number": res.get("invoice_number"),
            })
            results["skipped_duplicates"] += 1
        else:
            results["errors"].append({"filename": filename, "error": res.get("error", "errore")})
            results["failed"] += 1

    return results


@router.delete("/all")
@handle_errors
async def delete_all_invoices(
    confirm: str = Query(..., description="Scrivere 'CONFERMA_ELIMINAZIONE' per procedere"),
    _admin: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    """Elimina tutte le fatture. Richiede ruolo admin + conferma esplicita."""
    if confirm != "CONFERMA_ELIMINAZIONE":
        raise HTTPException(
            status_code=400,
            detail="Conferma richiesta: passare ?confirm=CONFERMA_ELIMINAZIONE"
        )
    db = Database.get_db()
    result = await db[Collections.INVOICES].delete_many({})
    try:
        from app.services.audit_logger import log_sicurezza
        await log_sicurezza(
            db, azione="delete_massivo",
            dettaglio=f"Eliminate TUTTE le fatture ({result.deleted_count})",
            utente=_admin.get("email") or _admin.get("user_id") or "admin",
            extra={"collection": "invoices", "deleted_count": result.deleted_count},
        )
    except Exception:
        pass
    return {"deleted_count": result.deleted_count}


@router.post("/sync-suppliers")
@handle_errors
async def sync_suppliers_from_invoices() -> Dict[str, Any]:
    """
    Sincronizza i fornitori dalle fatture esistenti.
    Crea nuovi fornitori per le P.IVA non presenti nel database.
    """
    db = Database.get_db()
    
    # Trova tutte le P.IVA uniche nelle fatture
    pipeline = [
        {"$match": {"supplier_vat": {"$exists": True, "$ne": ""}}},
        {"$group": {
            "_id": "$supplier_vat",
            "supplier_name": {"$first": "$supplier_name"},
            "fornitore": {"$first": "$fornitore"},
            "count": {"$sum": 1}
        }}
    ]
    
    supplier_groups = await db[Collections.INVOICES].aggregate(pipeline).to_list(5000)
    
    created = 0
    updated = 0
    skipped = 0
    
    for group in supplier_groups:
        supplier_vat = group["_id"]
        if not supplier_vat:
            continue
        
        # Cerca fornitore esistente
        existing = await db[Collections.SUPPLIERS].find_one({"partita_iva": supplier_vat})
        
        if existing:
            # Prepara aggiornamenti
            updates = {"fatture_count": group["count"], "updated_at": datetime.now(timezone.utc).isoformat()}
            
            # Aggiorna ragione_sociale se mancante
            if not existing.get("ragione_sociale") and group.get("supplier_name"):
                updates["ragione_sociale"] = group["supplier_name"]
            
            # Aggiorna dati fornitore se mancanti
            fornitore_data = group.get("fornitore") or {}
            if not existing.get("indirizzo") and fornitore_data.get("indirizzo"):
                updates["indirizzo"] = fornitore_data["indirizzo"]
            if not existing.get("cap") and fornitore_data.get("cap"):
                updates["cap"] = fornitore_data["cap"]
            if not existing.get("comune") and fornitore_data.get("comune"):
                updates["comune"] = fornitore_data["comune"]
            if not existing.get("provincia") and fornitore_data.get("provincia"):
                updates["provincia"] = fornitore_data["provincia"]
            
            await db[Collections.SUPPLIERS].update_one(
                {"partita_iva": supplier_vat},
                {"$set": updates}
            )
            updated += 1
            continue
        
        # Crea nuovo fornitore
        fornitore_data = group.get("fornitore") or {}
        
        new_supplier = {
            "id": str(uuid.uuid4()),
            "ragione_sociale": group.get("supplier_name") or "Fornitore Sconosciuto",
            "partita_iva": supplier_vat,
            "codice_fiscale": fornitore_data.get("codice_fiscale", ""),
            "indirizzo": fornitore_data.get("indirizzo", ""),
            "cap": fornitore_data.get("cap", ""),
            "comune": fornitore_data.get("comune", ""),
            "provincia": fornitore_data.get("provincia", ""),
            "nazione": fornitore_data.get("nazione", "IT"),
            # Regola generale: nessun metodo finché non configurato esplicitamente
            # sul fornitore (vedi ensure_supplier_exists) — mai un default arbitrario.
            "metodo_pagamento": "sospesa",
            "giorni_pagamento": 30,
            "iban": "",
            "fatture_count": group["count"],
            "source": "sync_from_invoices",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "note": f"Creato automaticamente - {group['count']} fatture trovate"
        }
        
        await db[Collections.SUPPLIERS].insert_one(new_supplier.copy())
        created += 1
        
        # Aggiorna le fatture con il supplier_id
        await db[Collections.INVOICES].update_many(
            {"supplier_vat": supplier_vat, "supplier_id": {"$exists": False}},
            {"$set": {"supplier_id": new_supplier["id"]}}
        )
    
    return {
        "success": True,
        "suppliers_created": created,
        "suppliers_updated": updated,
        "suppliers_skipped": skipped,
        "total_unique_vat": len(supplier_groups)
    }


@router.post("/categorize-movements")
@handle_errors
async def categorize_all_movements() -> Dict[str, Any]:
    """
    Categorizza tutti i movimenti esistenti (Prima Nota Cassa e Banca)
    basandosi sulla descrizione e sul fornitore.
    """
    db = Database.get_db()
    
    categories_map = {
        'acquisti_merce': ['fattura', 'merce', 'prodotti', 'acquisto', 'fornitura', 'materie prime'],
        'utenze': ['enel', 'eni', 'gas', 'luce', 'acqua', 'bolletta', 'utenz', 'telecom', 'tim', 'vodafone', 'fastweb', 'wind'],
        'affitto': ['affitto', 'canone', 'locazione', 'pigione'],
        'stipendi': ['stipendio', 'salario', 'busta paga', 'dipendent', 'paghe', 'f24'],
        'tasse': ['tasse', 'tribut', 'iva', 'irpef', 'inps', 'inail', 'agenzia entrate', 'imposta'],
        'bancari': ['commissione', 'interessi', 'bonifico', 'rid', 'addebito'],
        'assicurazioni': ['assicuraz', 'polizza', 'premio', 'unipol', 'generali', 'allianz'],
        'manutenzione': ['manutenz', 'riparaz', 'assist', 'intervento', 'tecnico'],
        'consulenze': ['consulen', 'commercialista', 'avvocato', 'notaio', 'professional'],
        'marketing': ['pubblicit', 'marketing', 'promoz', 'spot', 'social'],
        'attrezzature': ['attrezzat', 'macchin', 'strument', 'computer', 'software'],
        'carburante': ['benzina', 'gasolio', 'carburant', 'eni', 'q8', 'tamoil', 'ip'],
        'vendite': ['vendita', 'incasso', 'corrispettivo', 'scontrino', 'ricavo'],
        'altro': []
    }
    
    def categorize_description(desc: str, fornitore: str = "") -> str:
        """Determina categoria basandosi su descrizione e fornitore."""
        text = f"{desc} {fornitore}".lower()
        
        for category, keywords in categories_map.items():
            for keyword in keywords:
                if keyword in text:
                    return category
        
        return 'altro'
    
    # Processa Prima Nota Cassa
    cassa_updated = 0
    cassa_movements = await db["prima_nota_cassa"].find({}).to_list(10000)
    for mov in cassa_movements:
        desc = mov.get("descrizione", "") or mov.get("causale", "")
        fornitore = mov.get("fornitore", "")
        categoria = categorize_description(desc, fornitore)
        
        await db["prima_nota_cassa"].update_one(
            {"_id": mov["_id"]},
            {"$set": {"categoria": categoria}}
        )
        cassa_updated += 1
    
    # Processa Prima Nota Banca
    banca_updated = 0
    banca_movements = await db["prima_nota_banca"].find({}).to_list(10000)
    for mov in banca_movements:
        desc = mov.get("descrizione", "") or mov.get("causale", "")
        fornitore = mov.get("fornitore", "")
        categoria = categorize_description(desc, fornitore)
        
        await db["prima_nota_banca"].update_one(
            {"_id": mov["_id"]},
            {"$set": {"categoria": categoria}}
        )
        banca_updated += 1
    
    # Categorizza anche estratto conto
    ec_updated = 0
    ec_movements = await db["estratto_conto_movimenti"].find({}).to_list(10000)
    for mov in ec_movements:
        desc = mov.get("descrizione", "") or mov.get("causale", "")
        fornitore = mov.get("fornitore", "")
        categoria = categorize_description(desc, fornitore)
        
        await db["estratto_conto_movimenti"].update_one(
            {"_id": mov["_id"]},
            {"$set": {"categoria": categoria}}
        )
        ec_updated += 1
    
    return {
        "success": True,
        "cassa_movements_categorized": cassa_updated,
        "banca_movements_categorized": banca_updated,
        "estratto_conto_categorized": ec_updated,
        "categories_available": list(categories_map.keys())
    }


@router.get("/{invoice_id}")
@handle_errors
async def get_fattura(invoice_id: str) -> Dict[str, Any]:
    """Recupera una singola fattura per ID (stessa logica di /api/fatture-ricevute/fattura/{id})."""
    from app.routers.fatture_module.crud import get_fattura_dettaglio
    return await get_fattura_dettaglio(invoice_id)


@router.put("/{invoice_id}")
@handle_errors
async def update_fattura(invoice_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiorna una fattura (stessa logica di /api/fatture-ricevute/fattura/{id})."""
    from app.routers.fatture_module.crud import update_fattura as _update_fattura_ricevute
    return await _update_fattura_ricevute(invoice_id, data)


@router.put("/{invoice_id}/classifica")
@handle_errors
async def classifica_fattura_manuale(invoice_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Classifica manualmente una fattura assegnandola a un centro di costo.
    """
    db = Database.get_db()
    
    centro_costo_id = data.get("centro_costo_id")
    if not centro_costo_id:
        raise HTTPException(status_code=400, detail="centro_costo_id richiesto")
    
    # Recupera il nome del centro di costo
    cdc = await db["centri_costo"].find_one({"codice": centro_costo_id})
    centro_costo_nome = cdc.get("nome", centro_costo_id) if cdc else centro_costo_id
    
    update_data = {
        "centro_costo_id": centro_costo_id,
        "centro_costo_nome": centro_costo_nome,
        "classificazione_manuale": True,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db[Collections.INVOICES].update_one(
        {"id": invoice_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    return {
        "success": True, 
        "message": f"Fattura classificata come '{centro_costo_nome}'",
        "centro_costo_id": centro_costo_id,
        "centro_costo_nome": centro_costo_nome
    }


@router.put("/{invoice_id}/paga")
@handle_errors
async def paga_fattura(invoice_id: str) -> Dict[str, Any]:
    """
    Segna una fattura come pagata.
    Utilizza DataPropagationService per:
    - Creare movimento in Prima Nota (Cassa o Banca)
    - Aggiornare stato fattura
    - Aggiornare saldo fornitore
    """
    db = Database.get_db()
    
    # Trova la fattura
    invoice = await db[Collections.INVOICES].find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    if invoice.get("pagato") or invoice.get("status") == "paid":
        raise HTTPException(status_code=400, detail="Fattura già pagata")
    
    metodo = invoice.get("metodo_pagamento")
    if not metodo:
        raise HTTPException(status_code=400, detail="Seleziona prima un metodo di pagamento")
    
    # Usa DataPropagationService per propagare il pagamento
    from app.services.data_propagation import get_propagation_service
    
    propagation_service = get_propagation_service()
    importo = invoice.get("total_amount") or invoice.get("importo_totale") or 0
    
    result = await propagation_service.propagate_invoice_payment(
        invoice_id=invoice_id,
        payment_amount=float(importo),
        payment_method=metodo,
        payment_date=datetime.now(timezone.utc).isoformat()[:10]
    )
    
    if not result.get("movement_created"):
        logger.warning(f"Propagation errors: {result.get('errors')}")
        raise HTTPException(
            status_code=400,
            detail=result.get("errors", ["Impossibile registrare il pagamento"])[0],
        )

    return {
        "success": True,
        "message": "Fattura pagata con successo",
        "prima_nota": {
            "movement_id": result.get("movement_id"),
            "collection": result.get("movement_collection")
        },
        "payment_status": result.get("payment_status"),
        "supplier_updated": result.get("supplier_updated")
    }


@router.delete("/{invoice_id}")
@handle_errors
async def delete_invoice(
    invoice_id: str,
    force: bool = Query(False, description="Forza eliminazione anche con warning"),
    hard_delete: bool = Query(False, description="Elimina fisicamente invece di archiviare")
) -> Dict[str, Any]:
    """
    Elimina una singola fattura con validazione business rules.
    
    **Regole:**
    - Non può eliminare fatture pagate
    - Non può eliminare fatture registrate in Prima Nota (richiede force=true)
    - Fatture con movimenti magazzino richiedono force=true
    
    **CASCADE DELETE:**
    - Elimina/archivia righe dettaglio
    - Elimina/archivia Prima Nota associata
    - Elimina/archivia scadenze
    - Annulla movimenti magazzino
    - Sgancia assegni collegati
    """
    from app.services.business_rules import BusinessRules
    from app.services.cascade_operations import CascadeOperations
    
    db = Database.get_db()
    
    # Recupera fattura
    invoice = await db[Collections.INVOICES].find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    # Verifica se ha operazioni registrate
    stato_registrazione = await CascadeOperations.is_fattura_registrata(db, invoice_id)
    entita_correlate = await CascadeOperations.get_entita_correlate(db, invoice_id)
    
    # Valida eliminazione con business rules
    validation = BusinessRules.can_delete_invoice(invoice)
    
    # Aggiungi warning per entità correlate
    if entita_correlate["totale_entita"] > 0:
        validation.warnings.append(f"Verranno eliminate {entita_correlate['totale_entita']} entità correlate")
        if entita_correlate["prima_nota_banca"] > 0 or entita_correlate["prima_nota_cassa"] > 0:
            validation.warnings.append("⚠️ ATTENZIONE: Verranno eliminate registrazioni contabili (Prima Nota)")
        if entita_correlate["movimenti_magazzino"] > 0:
            validation.warnings.append("⚠️ ATTENZIONE: Verranno annullati movimenti di magazzino")
    
    if not validation.is_valid:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Eliminazione non consentita",
                "errors": validation.errors,
                "entita_correlate": entita_correlate
            }
        )
    
    # Se ci sono warning e non è forzata, richiedi conferma (DOPPIA CONFERMA)
    if (validation.warnings or stato_registrazione["registrata"]) and not force:
        return {
            "status": "warning",
            "message": "Eliminazione richiede conferma",
            "warnings": validation.warnings,
            "stato_registrazione": stato_registrazione,
            "entita_correlate": entita_correlate,
            "require_force": True,
            "nota": "Usa force=true per confermare l'eliminazione"
        }
    
    # Esegui CASCADE DELETE
    risultato_cascade = await CascadeOperations.delete_fattura_cascade(db, invoice_id, hard_delete=hard_delete)
    
    return {
        "success": True,
        "message": "Fattura eliminata" + (" (hard delete)" if hard_delete else " (archiviata)"),
        "invoice_id": invoice_id,
        "cascade_result": risultato_cascade
    }




@router.get("/{invoice_id}/entita-correlate")
@handle_errors
async def get_entita_correlate_fattura(invoice_id: str) -> Dict[str, Any]:
    """
    Restituisce tutte le entità correlate a una fattura.
    Utile per mostrare all'utente cosa verrà modificato/eliminato.
    """
    from app.services.cascade_operations import CascadeOperations
    
    db = Database.get_db()
    
    invoice = await db[Collections.INVOICES].find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    stato = await CascadeOperations.is_fattura_registrata(db, invoice_id)
    entita = await CascadeOperations.get_entita_correlate(db, invoice_id)
    
    return {
        "fattura_id": invoice_id,
        "numero_documento": invoice.get("invoice_number") or invoice.get("numero_documento"),
        "fornitore": invoice.get("supplier_name") or invoice.get("fornitore_ragione_sociale"),
        "importo": invoice.get("total_amount") or invoice.get("importo_totale"),
        "stato_registrazione": stato,
        "entita_correlate": entita,
        "eliminabile": not stato["dettagli"]["ha_pagamenti"],
        "richiede_conferma": stato["registrata"]
    }




@router.post("/recalculate-iva")
@handle_errors
async def recalculate_iva_all_invoices() -> Dict[str, Any]:
    """
    Ricalcola IVA e imponibile per tutte le fatture.
    Aggiunge data_ricezione se mancante.
    Usa i dati dal riepilogo_iva se disponibili.
    """
    db = Database.get_db()
    
    # Tipi documento Note Credito
    NOTE_CREDITO_TYPES = ["TD04", "TD08"]
    
    updated_count = 0
    errors = []
    
    # Trova tutte le fatture
    cursor = db[Collections.INVOICES].find({}, {"_id": 0})
    fatture = await cursor.to_list(10000)
    
    for f in fatture:
        try:
            updates = {}
            
            # Aggiungi data_ricezione se mancante (default = invoice_date)
            if not f.get('data_ricezione'):
                updates['data_ricezione'] = f.get('invoice_date', '')
            
            # Ricalcola IVA/imponibile dal riepilogo_iva se presente
            riepilogo = f.get('riepilogo_iva', [])
            if riepilogo:
                imponibile_calc = 0
                iva_calc = 0
                for r in riepilogo:
                    try:
                        imponibile_calc += float(r.get('imponibile', 0) or 0)
                        iva_calc += float(r.get('imposta', 0) or 0)
                    except (ValueError, TypeError):
                        pass
                
                # Aggiorna solo se i valori calcolati sono diversi da 0
                if imponibile_calc > 0:
                    current_imponibile = float(f.get('imponibile', 0) or 0)
                    if abs(current_imponibile - imponibile_calc) > 0.01:
                        updates['imponibile'] = round(imponibile_calc, 2)
                
                if iva_calc > 0:
                    current_iva = float(f.get('iva', 0) or 0)
                    if abs(current_iva - iva_calc) > 0.01:
                        updates['iva'] = round(iva_calc, 2)
            else:
                # Se non c'è riepilogo_iva, calcola IVA dal totale (22%)
                total = float(f.get('total_amount', 0) or 0)
                if total > 0:
                    current_iva = float(f.get('iva', 0) or 0)
                    current_imponibile = float(f.get('imponibile', 0) or 0)
                    
                    if current_iva == 0:
                        iva_stimata = round(total - (total / 1.22), 2)
                        updates['iva'] = iva_stimata
                        updates['iva_stimata'] = True  # Flag per indicare che è stimata
                    
                    if current_imponibile == 0:
                        imponibile_stimato = round(total / 1.22, 2)
                        updates['imponibile'] = imponibile_stimato
            
            # Applica aggiornamenti
            if updates:
                updates['updated_at'] = datetime.now(timezone.utc).isoformat()
                await db[Collections.INVOICES].update_one(
                    {"id": f['id']},
                    {"$set": updates}
                )
                updated_count += 1
                
        except Exception as e:
            errors.append(f"Errore fattura {f.get('invoice_number', 'N/A')}: {str(e)}")
    
    return {
        "success": True,
        "fatture_analizzate": len(fatture),
        "fatture_aggiornate": updated_count,
        "errors": errors[:20] if errors else []
    }
