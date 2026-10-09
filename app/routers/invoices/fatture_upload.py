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
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import uuid
import logging
import zipfile
import io
import re
import hashlib

from app.services.archivio_documenti_memoria import DuplicateRecordError

from app.constants.tipi_documento import TIPI_NOTA_CREDITO
from app.constants.fattura_attiva import FILTRO_FATTURA_ATTIVA, fattura_attiva
from app.database import Database, Collections
from app.utils.id_fattura import filtro_id
from app.engines.prima_nota_engine import (
    normalizza_metodo_pagamento,
)
from app.parsers.fattura_elettronica_parser import parse_fattura_xml, TIPO_DOC_MAP
from app.services.xml_invoice_processor import extract_xml_from_p7m, is_p7m_content
from app.utils.error_handler import handle_errors
from app.utils.iban import valida_iban
from app.utils.ruoli import richiedi_admin
from app.services.supplier_data_quality import apply_supplier_quality
from app.services.fatture_canonico import invoice_key as generate_invoice_key
from app.services.stato_pagamento_fattura import e_annullata, e_pagata

logger = logging.getLogger(__name__)

from app.services.eventi_fattura import costruisci_evento_fattura_created  # noqa: E402


def _iban_xml_verificato(parsed_invoice: Dict[str, Any]) -> Optional[str]:
    """Primo IBAN italiano formalmente valido dichiarato nei pagamenti XML.

    L'IBAN grezzo resta sempre nella fattura/rata. Solo quello che supera la
    validazione di formato puo' completare automaticamente un campo vuoto
    della scheda fornitore.
    """
    candidati = [
        rata.get("iban") for rata in (parsed_invoice.get("pagamento_rate") or [])
        if isinstance(rata, dict)
    ]
    pagamento = parsed_invoice.get("pagamento") or {}
    candidati.append(pagamento.get("iban"))
    for candidato in candidati:
        pulito = "".join(ch for ch in str(candidato or "") if ch.isalnum()).upper()
        if valida_iban(pulito):
            return pulito
    return None


def _analizza_pagamento_xml(
    parsed_invoice: Dict[str, Any], metodo_fornitore: Optional[str]
) -> Dict[str, Any]:
    """Conserva il metodo XML come evidenza/proposta, mai come pagamento.

    Il metodo della scheda fornitore resta il default operativo. Se l'XML
    mostra chiaramente uno strumento diverso, la singola fattura espone la
    proposta ma l'anagrafica non viene modificata senza conferma.
    """
    rate = [r for r in (parsed_invoice.get("pagamento_rate") or []) if isinstance(r, dict)]
    modalita = []
    condizioni = []
    for rata in rate:
        codice = str(rata.get("modalita") or "").strip().upper()
        if codice and codice not in modalita:
            modalita.append(codice)
        condizione = str(rata.get("condizioni_pagamento") or "").strip().upper()
        if condizione and condizione not in condizioni:
            condizioni.append(condizione)

    canonici = []
    for codice in modalita:
        canonico = normalizza_metodo_pagamento(codice)
        if canonico and canonico not in canonici:
            canonici.append(canonico)
    proposta = canonici[0] if len(canonici) == 1 else ("misto" if len(canonici) > 1 else None)
    metodo_default = normalizza_metodo_pagamento(metodo_fornitore)
    richiede_conferma = bool(proposta and proposta != metodo_default)

    return {
        "modalita_pagamento_xml": modalita,
        "condizioni_pagamento_xml": condizioni,
        "metodo_pagamento_xml_proposto": proposta,
        "metodo_pagamento_xml_richiede_conferma": richiede_conferma,
        "metodo_pagamento_xml_fonte": "FatturaPA.DatiPagamento" if modalita else None,
        "iban_pagamento_xml": _iban_xml_verificato(parsed_invoice),
    }


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

# Tipi documento FatturaPA che rappresentano una nota di credito (TD04 nota
# di credito, TD08 nota di credito semplificata): entrambe seguono la stessa
# logica "collegata a un documento precedente". Audit 19/09/2026: prima
# ridefinita qui come doppione di `TIPI_NOTA_CREDITO` (già fonte unica per
# iva.py, sync.py e i motori IVA) — un unico posto, così un futuro TD09
# (nota di debito semplificata, da NON trattare come nota di credito) si
# aggiunge una sola volta.
NOTE_CREDITO_TIPI_DOCUMENTO = set(TIPI_NOTA_CREDITO)


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
        # Recupera anche le NC arrivate prima dell'originale attraverso lo
        # stesso motore, senza un job/writer nel browser. Ogni candidata
        # deve superare tutte le verifiche del ramo NC qui sotto.
        if not fattura_attiva(invoice) or not invoice.get("id") or not invoice.get("supplier_vat") or not invoice.get("invoice_number"):
            return None
        note_in_attesa = await db[Collections.INVOICES].find({
            **FILTRO_FATTURA_ATTIVA,
            "supplier_vat": invoice["supplier_vat"],
            "tipo_documento": {"$in": list(NOTE_CREDITO_TIPI_DOCUMENTO)},
            "dati_fatture_collegate": {"$elemMatch": {"id_documento": invoice["invoice_number"]}},
            "$or": [
                {"fattura_collegata_id": {"$exists": False}},
                {"fattura_collegata_id": None},
                {"fattura_collegata_id": ""},
            ],
        }, session=session).to_list(None)
        recuperate = False
        for nota in note_in_attesa:
            if await _collega_nota_credito(db, nota, session=session):
                recuperate = True
        if not recuperate:
            return None
        originale = await db[Collections.INVOICES].find_one(filtro_id(invoice["id"]), session=session)
        return {campo: originale[campo] for campo in ("note_credito_collegate", "importo_netto") if campo in originale}

    riferimenti = invoice.get("dati_fatture_collegate") or []
    if not riferimenti:
        return None

    # Le regole della pagina Ceraldi recuperata valgono nel motore unico:
    # nessun aggancio ambiguo, nessun ricalcolo automatico di una fattura
    # gia' pagata e rispetto dell'esclusione manuale [NC-NO-AUTO].
    note_operatore = "\n".join(str(invoice.get(campo) or "") for campo in ("notes", "note"))
    if not fattura_attiva(invoice) or "[NC-NO-AUTO]" in note_operatore:
        return None
    supplier_vat = str(invoice.get("supplier_vat") or "").strip()
    if not supplier_vat:
        return None
    candidati = {}
    for rif in riferimenti:
        if not isinstance(rif, dict):
            continue
        id_doc = (rif or {}).get("id_documento")
        if not id_doc:
            continue
        trovate = await db[Collections.INVOICES].find(
            {
                **FILTRO_FATTURA_ATTIVA,
                "invoice_number": id_doc,
                "supplier_vat": supplier_vat,
                "tipo_documento": {"$nin": list(NOTE_CREDITO_TIPI_DOCUMENTO)},
            },
            session=session,
        ).to_list(2)
        for candidata in trovate:
            if candidata.get("id") is None:
                logger.warning("Nota di credito %s: fattura candidata senza identificatore", invoice.get("id"))
                return None
            if str(candidata.get("id")) != str(invoice.get("id")):
                candidati[str(candidata["id"])] = candidata
        if len(candidati) > 1:
            logger.warning("Nota di credito %s: riferimento ambiguo, nessun aggancio automatico", invoice.get("id"))
            return None

    if len(candidati) != 1:
        return None
    originale = next(iter(candidati.values()))
    if e_pagata(originale) or e_annullata(originale):
        return None
    collegata = invoice.get("fattura_collegata_id")
    if collegata is not None and str(collegata) != str(originale["id"]):
        return None

    def importo_documentato(documento):
        valore = documento.get("total_amount")
        if valore is None or valore == "":
            raise InvalidOperation("Importo documento mancante")
        risultato = Decimal(str(valore))
        if not risultato.is_finite():
            raise InvalidOperation("Importo documento non finito")
        return risultato

    try:
        importo_nc = abs(importo_documentato(invoice))
        importo_originale = importo_documentato(originale)
    except (InvalidOperation, ValueError, TypeError):
        logger.warning("Nota di credito %s: importi non validi, nessun aggancio automatico", invoice.get("id"))
        return None
    note_credito_collegate = list(originale.get("note_credito_collegate") or [])
    if not any(str(nc_id) == str(invoice["id"]) for nc_id in note_credito_collegate):
        note_credito_collegate.append(invoice["id"])

    # Somma tutte le NC collegate a questo originale (non solo quella corrente)
    # per calcolare il netto corretto anche con più note di credito parziali.
    totale_nc = Decimal("0")
    for nc_id in note_credito_collegate:
        if str(nc_id) == str(invoice["id"]):
            totale_nc += importo_nc
            continue
        nc_doc = await db[Collections.INVOICES].find_one(filtro_id(nc_id), {"total_amount": 1}, session=session)
        try:
            if not nc_doc:
                raise InvalidOperation("Nota di credito collegata assente")
            totale_nc += abs(importo_documentato(nc_doc))
        except (InvalidOperation, ValueError, TypeError):
            logger.warning("Nota di credito %s: importo della nota collegata %s assente o non valido", invoice.get("id"), nc_id)
            return None

    # Stringa decimale al confine JSON: nessun arrotondamento binario.
    importo_netto = str((importo_originale - totale_nc).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

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

    session: sessione repository opzionale, per partecipare a una transazione del
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
        "proposte_aggiornamento": {},
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
    supplier_match_key = (
        cedente_piva_norm[2:]
        if cedente_piva_norm.startswith("IT")
        else cedente_piva_norm
    )
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
    # Identita' P.IVA -> CF -> nome (fornitori_dedupe e' l'unico motore): la
    # P.IVA si cerca in tutte le sue scritture (con/senza IT) e un fornitore
    # gia' unificato (`merged_into`) non si riattiva.
    from app.services.fornitori_dedupe import varianti_piva
    _varianti = varianti_piva(supplier_vat) or [supplier_vat]
    existing = await db[Collections.SUPPLIERS].find_one(
        {"merged_into": {"$exists": False},
         "$or": [{campo: v} for v in _varianti for campo in ("partita_iva", "piva")]},
        session=session
    )

    # Stesso codice fiscale (persona o ditta) e nessuna P.IVA diversa: e' lui.
    _cf_xml = re.sub(r"[^0-9A-Z]", "", str((parsed_invoice.get("fornitore") or {}).get("codice_fiscale") or "").upper())
    if not existing and len(_cf_xml) >= 11 and _cf_xml != supplier_match_key:
        _cand_cf = await db[Collections.SUPPLIERS].find_one(
            {"merged_into": {"$exists": False}, "codice_fiscale": _cf_xml}, session=session)
        if _cand_cf:
            _p_cand = (_cand_cf.get("partita_iva") or _cand_cf.get("piva") or "").strip().upper().replace(" ", "")
            if not _p_cand or _p_cand.lstrip("IT") == cedente_piva_norm.lstrip("IT"):
                existing = _cand_cf

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
            {"merged_into": {"$exists": False},
             "$or": [
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
    iban_xml = _iban_xml_verificato(parsed_invoice)

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
            "match_key": supplier_match_key,
            "name": supplier_name,
            "vat": f"IT{supplier_match_key}" if supplier_match_key.isdigit() and len(supplier_match_key) == 11 else supplier_vat,
            "partita_iva": supplier_vat,
            "piva": supplier_vat,
            "nome": supplier_name,
            "ragione_sociale": existing.get("ragione_sociale") or supplier_name,
            "codice_fiscale": fornitore_data.get("codice_fiscale") or existing.get("codice_fiscale") or supplier_vat,
            "indirizzo": fornitore_data.get("indirizzo") or "",
            "cap": fornitore_data.get("cap") or "",
            "comune": fornitore_data.get("comune") or "",
            "provincia": fornitore_data.get("provincia") or "",
            "nazione": fornitore_data.get("nazione") or "IT",
            "telefono": fornitore_data.get("telefono") or "",
            "email": fornitore_data.get("email") or "",
            "iban": iban_xml or "",
            "rappresentante_fiscale": fornitore_data.get("rappresentante_fiscale") or None,
        }
        for field, value in field_map.items():
            if value and not existing.get(field):
                update_data[field] = value
            elif value and existing.get(field) and existing.get(field) != value:
                # L'XML e' una fonte documentale, ma non deve sovrascrivere
                # una scelta anagrafica gia' confermata. La differenza resta
                # sulla fattura come proposta esplicita da verificare.
                result["proposte_aggiornamento"][field] = {
                    "valore_attuale": existing.get(field),
                    "valore_xml": value,
                    "fonte": "fattura_xml",
                }

        if not existing.get("id"):
            update_data["id"] = supplier_id

        if update_data:
            quality = apply_supplier_quality({**existing, **update_data})
            update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            update_data.update(quality)
            source_document_id = (
                parsed_invoice.get("document_id")
                or parsed_invoice.get("source_document_id")
                or parsed_invoice.get("id")
            )
            source_hash = parsed_invoice.get("sha256") or parsed_invoice.get("document_hash")
            parser_version = parsed_invoice.get("parser_version") or "fattura_xml"
            if source_document_id or source_hash:
                update_data.setdefault("provenienza_anagrafica", {})
                for field in update_data:
                    if field in {"updated_at", "dati_incompleti", "campi_fiscali_mancanti", "contatti_incompleti", "campi_contatto_mancanti", "provenienza_anagrafica"}:
                        continue
                    update_data["provenienza_anagrafica"][field] = {
                        "source_document_id": source_document_id,
                        "source_hash": source_hash,
                        "parser_version": parser_version,
                    }
            await db[Collections.SUPPLIERS].update_one(
                {"_id": existing["_id"]},
                {"$set": update_data},
                session=session
            )
            result["supplier_updated"] = True
            logger.info(f"Fornitore {supplier_name} aggiornato con dati XML: {list(update_data.keys())}")

        if result["proposte_aggiornamento"]:
            # La proposta resta auditabile senza sovrascrivere dati confermati.
            await db["supplier_update_proposals"].update_one(
                {"supplier_id": supplier_id, "source_document_id": parsed_invoice.get("document_id") or parsed_invoice.get("id")},
                {"$set": {
                    "supplier_id": supplier_id,
                    "source_document_id": parsed_invoice.get("document_id") or parsed_invoice.get("id"),
                    "source_hash": parsed_invoice.get("sha256") or parsed_invoice.get("document_hash"),
                    "fields": result["proposte_aggiornamento"],
                    "status": "da_confermare",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True,
                session=session,
            )

        return result

    # Fornitore non esiste — CREA
    new_supplier = {
        "id": str(uuid.uuid4()),
        "match_key": supplier_match_key,
        "name": supplier_name,
        "vat": f"IT{supplier_match_key}" if supplier_match_key.isdigit() and len(supplier_match_key) == 11 else supplier_vat,
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
        "iban": iban_xml or "",
        "telefono": fornitore_data.get("telefono") or "",
        "email": fornitore_data.get("email") or "",
        "rappresentante_fiscale": fornitore_data.get("rappresentante_fiscale") or None,
        "fatture_count": 1,
        "source": "auto_from_invoice",
        # Il record appena creato può ancora mancare di contatti o comune:
        # lo stato deriva sempre dalla stessa funzione del dominio.
        **apply_supplier_quality({
            "ragione_sociale": supplier_name,
            "partita_iva": supplier_vat,
            "comune": fornitore_data.get("comune") or "",
            "email": fornitore_data.get("email") or "",
            "telefono": fornitore_data.get("telefono") or "",
        }),
        "provenienza_anagrafica": {
            "source_document_id": parsed_invoice.get("document_id") or parsed_invoice.get("id"),
            "source_hash": parsed_invoice.get("sha256") or parsed_invoice.get("document_hash"),
            "parser_version": parsed_invoice.get("parser_version") or "fattura_xml",
        },
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
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[Fatture] cache dei fornitori non invalidata: il fornitore nuovo "
            "comparira' solo alla scadenza del TTL: %s", exc)

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


def _token_identita_fornitore(nome: str) -> List[str]:
    """Token stabili per confrontare fornitore e causale bancaria."""
    stop = {
        "SRL", "SPA", "SNC", "SAS", "SOCIETA", "UNIPERSONALE",
        "ITALIA", "ITALIANA", "SEDE", "SECONDARIA", "EUROPE",
    }
    pulito = re.sub(r"[^A-Z0-9]+", " ", (nome or "").upper())
    return [p for p in pulito.split() if len(p) >= 4 and p not in stop][:6]


def _normalizza_identificativo_bancario(valore: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (valore or "").upper()).lstrip("0")


async def find_ec_match_for_invoice(
    db,
    importo: float,
    supplier_name: str = "",
    invoice_date: str = "",
    invoice_number: str = "",
    session=None,
) -> Optional[Dict[str, Any]]:
    """Cerca nell'estratto conto un'uscita compatibile con la fattura.

    Regole:
    - tollera i DUE formati storici della collection (importo assoluto oppure
      con segno negativo per le uscite);
    - esclude i movimenti già riconciliati (un movimento paga UNA fattura);
    - applica una finestra temporale plausibile rispetto alla data fattura;
    - richiede sempre importo al centesimo, numero fattura esplicito e nome
      fornitore nella descrizione; data/fuzzy non sostituiscono queste prove.
    """
    if not importo or importo <= 0:
        return None
    from app.services.bank_evidence import filtro_solo_evidenza_ufficiale
    conds: Dict[str, Any] = {
        "tipo": "uscita",
        "abbinato": {"$ne": True},
        "$and": [
            filtro_solo_evidenza_ufficiale(),
            {"$or": [
                {"riconciliato": {"$ne": True}},
                {"tipo_riconciliazione": "auto_generico"},
            ]},
            {"$or": [
                {"importo": {"$gte": importo - 0.004, "$lte": importo + 0.004}},
                {"importo": {"$gte": -importo - 0.004, "$lte": -importo + 0.004}},
            ]},
        ],
    }
    finestra = _finestra_pagamento(invoice_date)
    if finestra:
        conds["data"] = {"$gte": finestra[0], "$lte": finestra[1]}
    candidati = await db["estratto_conto_movimenti"].find(
        conds, {"_id": 0}, session=session
    ).limit(50).to_list(50)
    from app.services.payment_invoice_matching import (
        amounts_equal_to_cent,
    )
    from app.services.riconciliazione_bancaria import (
        _evidenza_forte_fattura_banca,
        _evidenza_sdd_fattura_banca,
    )
    fattura_match = {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "supplier_name": supplier_name,
        "total_amount": importo,
        "importo_residuo": importo,
    }
    forti = []
    for mov in candidati:
        testo = " ".join(str(mov.get(k) or "") for k in (
            "descrizione", "descrizione_originale", "causale", "beneficiario"
        ))
        evidenza = _evidenza_forte_fattura_banca(
            fattura_match, testo, abs(float(mov.get("importo") or 0)),
        )
        evidenza_sdd = _evidenza_sdd_fattura_banca(
            fattura_match, testo, abs(float(mov.get("importo") or 0)),
            mov.get("data") or mov.get("data_contabile") or "",
        )
        if amounts_equal_to_cent(mov.get("importo"), importo) and (
            evidenza.get("auto_ammesso") or evidenza_sdd.get("auto_ammesso")
        ):
            mov = dict(mov)
            mov["match_score"] = 1.0
            mov["match_tipo"] = (
                "sdd+fornitore+importo+data"
                if evidenza_sdd.get("auto_ammesso")
                else "numero_fattura+importo_centesimo+fornitore"
            )
            forti.append(mov)
    return forti[0] if len(forti) == 1 else None


#: Stato finanziario della fattura il cui fornitore non ha un metodo in
#: anagrafica (CLAUDE.md §29): resta sospesa e non suggerisce la Cassa.
STATO_SOSPESA_METODO_MANCANTE = "sospesa_metodo_fornitore_mancante"
#: Stato finanziario dell'attesa bancaria: la riga provvisoria in Prima Nota
#: Banca e' gia' l'attesa, l'estratto conto la chiude. Lo scrive anche
#: ``assegni_fattura_intent._collega`` per l'assegno (§39).
STATO_IN_ATTESA_ESTRATTO_CONTO = "in_attesa_estratto_conto"
#: Origine della riga Prima Nota scritta dall'import per metodo fornitore.
SOURCE_AUTO_METODO_FORNITORE = "auto_metodo_fornitore"
#: Origine della riga di attesa bancaria creata per l'assegno collegato.
SOURCE_ATTESA_ASSEGNO = "assegno_compilato_attesa_banca"


async def _pubblica_fattura_pagata(
    db, fattura_id: Any, *, metodo: str, data_pagamento: Optional[str],
    importo: float, movimento_id: Optional[str], source_module: str,
) -> None:
    """Stesso evento `fattura.pagata` del bonifico, dell'assegno in banca e
    della conferma in Provvisori: chiude partita aperta e alert. Mai
    bloccante: la scrittura contabile e' gia' fatta."""
    try:
        from app.services.event_bus import EventTypes, propagate_event
        await propagate_event(EventTypes.FATTURA_PAGATA, {
            "fattura_id": fattura_id,
            "metodo_pagamento": metodo,
            "data_pagamento": data_pagamento,
            "movimento_id": movimento_id,
            "importo": importo,
        }, db, source_module=source_module)
    except Exception as exc:  # noqa: BLE001 - un handler rotto non annulla la scrittura
        logger.exception(
            "fattura.pagata non propagata per %s (%s)", fattura_id, type(exc).__name__,
        )


async def _registra_cassa_da_metodo_fornitore(
    db, invoice: Dict[str, Any], data_fattura: str, session=None,
) -> Optional[Dict[str, Any]]:
    """Fornitore «cassa» in anagrafica: il movimento in Prima Nota Cassa nasce
    all'import (decisione del titolare 07/10/2026). La data e' quella della
    fattura: e' la dichiarazione del titolare tramite anagrafica, non un dato
    inventato. Idempotente: il writer canonico non scrive due righe per la
    stessa fattura e l'evento `fattura.pagata` parte una sola volta."""
    from app.routers.prima_nota_module.sync import registra_pagamento_fattura
    from app.services.stato_pagamento_fattura import PAGATA

    fattura_id = invoice.get("id") or invoice.get("invoice_key")
    esito = await registra_pagamento_fattura(
        invoice, "cassa", source=SOURCE_AUTO_METODO_FORNITORE, session=session,
    )
    mov_id = esito.get("cassa")
    if not mov_id:
        return None
    totale = round(abs(float(
        invoice.get("total_amount") or invoice.get("importo_totale") or 0
    )), 2)
    now_iso = datetime.now(timezone.utc).isoformat()
    if not esito.get("duplicato"):
        # Perche' questa riga esiste e da dove viene la sua data: resta
        # leggibile sul movimento, non solo nel codice.
        await db["prima_nota_cassa"].update_one(
            {"id": mov_id},
            {"$set": {
                "fonte_data": "data_fattura",
                "motivo": (
                    "Metodo cassa impostato dal titolare nell'anagrafica fornitore: "
                    "registrazione automatica all'import della fattura"
                ),
            }},
            session=session,
        )
    update: Dict[str, Any] = {
        "pagato": True,
        "paid": True,
        "stato_pagamento": PAGATA,
        "payment_status": "paid",
        "stato_finanziario": "pagata",
        "metodo_pagamento_effettivo": "cassa",
        "metodo_pagamento_previsto": "cassa",
        "data_pagamento": data_fattura,
        "fonte_data_pagamento": "data_fattura",
        "importo_pagato": totale,
        "totale_pagato": totale,
        "importo_residuo": 0,
        "residuo_da_pagare": 0,
        "provvisorio": False,
        "decisione_pagamento_richiesta": False,
        "prima_nota_id": mov_id,
        "prima_nota_tipo": "cassa",
        "prima_nota_cassa_id": mov_id,
        "registrata_auto_da_metodo_fornitore": True,
        "updated_at": now_iso,
    }
    if fattura_id:
        await db[Collections.INVOICES].update_one(
            {"id": fattura_id}, {"$set": update}, session=session
        )
    # Il dict in memoria deve dire «pagata» prima che parta `fattura.created`:
    # il payload chiede `e_pagata(invoice)` e non apre la partita.
    invoice.update(update)
    if not esito.get("duplicato"):
        await _pubblica_fattura_pagata(
            db, fattura_id, metodo="cassa", data_pagamento=data_fattura,
            importo=totale, movimento_id=mov_id,
            source_module="fatture_upload_metodo_fornitore_cassa",
        )
    return update


async def _garantisci_attesa_banca_assegno(
    db, invoice: Dict[str, Any], session=None,
) -> Optional[str]:
    """Una sola riga di attesa in Prima Nota Banca per la fattura pagata con
    assegno (§39): se l'assegno ne ha gia' una (riscontro EC, riga
    provvisoria precedente) la riusa, altrimenti la crea con il writer
    canonico e la marca con il numero dell'assegno, cosi'
    ``assegni_estratto_conto._garantisci_prima_nota`` la ritrova per
    ``assegno_id`` invece di scriverne una seconda."""
    from app.routers.prima_nota_module.sync import registra_pagamento_fattura

    fattura_id = invoice.get("id") or invoice.get("invoice_key")
    link_assegni = [
        link for link in (invoice.get("assegni_collegati") or [])
        if isinstance(link, dict) and link.get("assegno_id")
    ]
    assegno_ids = [str(link["assegno_id"]) for link in link_assegni]
    if assegno_ids:
        # Assegno gia' transitato in banca: il completamento e' di
        # `collega_assegno_riconciliato_a_fattura`, non serve un'attesa.
        gia_in_banca = await db["assegni"].find_one(
            {"id": {"$in": assegno_ids}, "$or": [
                {"movimento_estratto_conto_id": {"$nin": [None, ""]}},
                {"movimento_id": {"$nin": [None, ""]}},
            ]},
            {"_id": 0, "id": 1},
            session=session,
        )
        if gia_in_banca:
            return None
    condizioni: list = []
    if fattura_id:
        condizioni += [{"fattura_id": fattura_id}, {"riferimento": f"FATT-{fattura_id}"}]
    if assegno_ids:
        condizioni.append({"assegno_id": {"$in": assegno_ids}})
    if condizioni:
        esistente = await db["prima_nota_banca"].find_one(
            {"$or": condizioni, "status": {"$nin": ["deleted", "archived"]}},
            {"_id": 0, "id": 1},
            session=session,
        )
        if esistente:
            return esistente.get("id")
    esito = await registra_pagamento_fattura(
        invoice, "banca", source=SOURCE_ATTESA_ASSEGNO,
        session=session, allow_provisional_bank=True,
    )
    mov_id = esito.get("banca")
    if mov_id and len(link_assegni) == 1:
        await db["prima_nota_banca"].update_one(
            {"id": mov_id},
            {"$set": {
                "assegno_id": link_assegni[0]["assegno_id"],
                "assegno_numero": link_assegni[0].get("numero"),
                "numero_assegno": link_assegni[0].get("numero"),
                "metodo_pagamento_previsto": "assegno",
                "motivo_provvisorio": "assegno_in_attesa_estratto_conto",
            }},
            session=session,
        )
    return mov_id


async def auto_registra_prima_nota(db, invoice: Dict[str, Any], metodo_pagamento: str,
                                   session=None) -> Optional[Dict[str, Any]]:
    """Instrada la fattura appena importata in Prima Nota per metodo fornitore.

    REGOLA (titolare, 07/10/2026; CLAUDE.md §29 e §39): oltre la data limite
    del report «Fatture ricevute» comanda il metodo impostato in anagrafica.
      - cassa -> movimento in Prima Nota Cassa subito, data fattura, fattura
        pagata (`fattura.pagata` una sola volta);
      - banca -> riga provvisoria in Prima Nota Banca che e' l'attesa
        dell'estratto conto; con riga EC univoca e forte -> pagata e
        riconciliata;
      - assegno collegato o previsto -> pagamento dichiarato con assegno, in
        attesa di riscontro bancario (stati di `assegni_fattura_intent`),
        una sola riga di attesa; il riscontro resta ad
        `assegni_estratto_conto`;
      - misto -> Provvisoria; metodo mancante -> sospesa con alert, senza
        suggerire la Cassa come ripiego.
    Fino alla data limite comanda il report del titolare
    (`pagamenti_dichiarati_titolare`), non il metodo.

    La scrittura usa il writer canonico registra_pagamento_fattura
    (idempotente per fattura: riferimento FATT-{id}, mai due movimenti per
    la stessa fattura). Ritorna il dict di update applicato alla fattura
    (già persistito), oppure None se resta provvisoria.
    """
    from app.services.stato_pagamento_fattura import e_pagata

    if invoice.get("verifica_ai") == "in_attesa":
        return None

    # Un piano XML a piu' rate non e' una prova di pagamento: anche per un
    # fornitore configurato "cassa" resta provvisorio finche' ogni quota non
    # viene confermata con la relativa evidenza.
    if len(invoice.get("pagamento_rate") or []) > 1:
        return None

    piva = (invoice.get("supplier_vat") or invoice.get("cedente_piva") or "").strip()
    if not piva:
        return None

    # Gia' pagata (report del titolare, storia ripristinata, assegno gia' in
    # banca): nessun secondo pagamento da un altro canale.
    if e_pagata(invoice):
        return None

    # Regola del titolare: fino all'ultima operazione del suo report
    # «Fatture ricevute» comanda il report, non il metodo del fornitore.
    # Una fattura con quella data che arriva dopo resta Provvisoria.
    from app.routers.prima_nota_module.sync import _data_fattura, data_limite_dichiarazioni
    data_limite = await data_limite_dichiarazioni(db)
    data_fattura = _data_fattura(invoice)
    if data_limite and data_fattura and data_fattura <= data_limite:
        return None

    forn = await db["fornitori"].find_one(
        {"$or": [{"partita_iva": piva}, {"piva": piva}, {"vat_number": piva}]},
        {"_id": 0, "metodo_pagamento": 1, "esclude_cassa_banca": 1, "cessato": 1},
        session=session,
    )
    if (forn or {}).get("esclude_cassa_banca") or (forn or {}).get("cessato"):
        # L'esclusione riguarda solo i registri finanziari. La fattura e'
        # gia' stata salvata con imponibile, IVA, righe e XML: li lasciamo
        # intatti e annotiamo esplicitamente che resta fiscalmente valida.
        fiscal_update = {
            "esclusa_da_cassa_banca": True,
            "registrazione_fiscale_mantenuta": True,
            "stato_finanziario": "esclusa_cassa_banca",
        }
        invoice.update(fiscal_update)
        fattura_id = invoice.get("id") or invoice.get("invoice_key")
        if fattura_id:
            await db[Collections.INVOICES].update_one(
                {"id": fattura_id}, {"$set": fiscal_update}, session=session
            )
        return None

    # Senza un fornitore identificato univocamente non si crea alcun movimento:
    # nome/importo da soli non sono identita'. Se il fornitore esiste ma non ha
    # metodo, invece, la fattura resta sospesa con alert (§29). Il confronto
    # e' con None: la proiezione di un fornitore senza metodo ne' flag e' un
    # dict vuoto, e `not forn` lo scambiava per «fornitore assente».
    if forn is None:
        return None

    fattura_id = invoice.get("id") or invoice.get("invoice_key")
    metodo = ((forn or {}).get("metodo_pagamento") or "").strip().lower()
    assegno_specifico = bool(
        invoice.get("metodo_pagamento_previsto") == "assegno"
        or invoice.get("metodo_pagamento_override_source") == "assegno_compilato"
        or invoice.get("assegni_collegati")
    )

    if assegno_specifico:
        # §39: l'assegno compilato e' la pre-registrazione dell'addebito
        # futuro e prevale sul metodo del fornitore. La fattura e' «pagamento
        # dichiarato con assegno, in attesa di riscontro bancario»: gli stati
        # sono quelli gia' scritti da assegni_fattura_intent._collega, la
        # riga di attesa in Prima Nota Banca e' una sola e la chiusura spetta
        # all'estratto conto (assegni_estratto_conto). Nessuna decisione da
        # chiedere: la decisione l'ha gia' presa chi ha compilato l'assegno.
        mov_id = await _garantisci_attesa_banca_assegno(db, invoice, session=session)
        update: Dict[str, Any] = {
            "stato_finanziario": STATO_IN_ATTESA_ESTRATTO_CONTO,
            "metodo_pagamento_previsto": "assegno",
            "metodo_pagamento_effettivo": None,
            "provvisorio": True,
            "decisione_pagamento_richiesta": False,
            "registrata_auto_da_metodo_fornitore": False,
        }
        if mov_id:
            update.update({
                "prima_nota_id": mov_id,
                "prima_nota_tipo": "banca",
                "prima_nota_banca_id": mov_id,
            })
        if fattura_id:
            await db[Collections.INVOICES].update_one(
                {"id": fattura_id}, {"$set": update}, session=session
            )
        invoice.update(update)
        return update

    if not metodo:
        # §29: metodo mancante -> fattura sospesa con alert. Nessun ripiego
        # automatico su Cassa, nemmeno come suggerimento di stato.
        update = {
            "stato_finanziario": STATO_SOSPESA_METODO_MANCANTE,
            "provvisorio": True,
            "metodo_pagamento_effettivo": None,
            "decisione_pagamento_richiesta": True,
        }
        if fattura_id:
            await db[Collections.INVOICES].update_one(
                {"id": fattura_id}, {"$set": update}, session=session
            )
            try:
                from app.services.alert_engine import genera_alert
                await genera_alert(
                    "FAT_MP_NON_DEFINITO", fattura_id, Collections.INVOICES,
                    f"Fattura {invoice.get('invoice_number', '?')}: impostare il metodo "
                    "di pagamento del fornitore (Cassa o Banca)",
                    db,
                )
            except Exception:
                logger.exception("Creazione alert metodo pagamento mancante non riuscita")
        invoice.update(update)
        return update

    metodo_canonico = normalizza_metodo_pagamento(metodo)
    if metodo_canonico not in ("cassa", "banca"):
        # Misto o non riconosciuto: resta Provvisoria, decide l'operatore.
        return None

    if metodo_canonico == "cassa":
        data_fattura_iso = str(data_fattura or "")[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data_fattura_iso):
            # Senza data documento non si inventa una data di pagamento.
            return None
        from app.routers.prima_nota_module.sync import determina_tipo_movimento_fattura
        tipo_movimento, _, _ = determina_tipo_movimento_fattura(invoice)
        if tipo_movimento != "uscita":
            # Nota di credito (TD04/TD08) o importo negativo: non e' un
            # pagamento al fornitore. Un'entrata di cassa automatica
            # sarebbe un rimborso inventato (§32: la nota chiude con il
            # rimborso reale o compensando la fattura originale). Resta
            # provvisoria.
            return None
        return await _registra_cassa_da_metodo_fornitore(
            db, invoice, data_fattura_iso, session=session,
        )

    movimento_bancario = await find_ec_match_for_invoice(
        db,
        float(invoice.get("total_amount") or invoice.get("importo_totale") or 0),
        invoice.get("supplier_name") or invoice.get("cedente_denominazione") or "",
        invoice.get("invoice_date") or invoice.get("data_fattura") or "",
        invoice.get("invoice_number") or invoice.get("numero_fattura") or "",
        session=session,
    )
    destinazione = "banca"

    # NB: registra_pagamento_fattura scrive fuori dalla transazione
    # dell'import (non accetta session); è idempotente per fattura, quindi
    # un eventuale abort dell'import lascia al più un movimento riferito a
    # una fattura che verrà reimportata subito dopo con lo stesso id.
    from app.routers.prima_nota_module.sync import registra_pagamento_fattura
    esito = await registra_pagamento_fattura(
        invoice,
        destinazione,
        source=("estratto_conto_auto" if movimento_bancario else SOURCE_AUTO_METODO_FORNITORE),
        movimento_bancario=movimento_bancario,
        session=session,
        allow_provisional_bank=not bool(movimento_bancario),
    )
    mov_id = esito.get(destinazione)
    if not mov_id:
        return None

    update: Dict[str, Any] = {
        "prima_nota_id": mov_id,
        "prima_nota_tipo": destinazione,
        "prima_nota_banca_id": mov_id,
        "registrata_auto_da_metodo_fornitore": True,
    }
    if movimento_bancario:
        update.update({
            "pagato": True,
            "paid": True,
            "stato_pagamento": "pagata",
            "stato_finanziario": "pagata_banca",
            "metodo_pagamento": "bonifico",
            "metodo_pagamento_effettivo": "banca",
            "data_pagamento": movimento_bancario.get("data"),
            "provvisorio": False,
            "decisione_pagamento_richiesta": False,
            "riconciliato": True,
            "riconciliato_con_ec": True,
            "riconciliato_automaticamente": True,
            "movimento_bancario_id": movimento_bancario.get("id"),
            "match_score": movimento_bancario.get("match_score"),
            "match_tipo": movimento_bancario.get("match_tipo"),
        })
    else:
        # La riga provvisoria in Prima Nota Banca e' gia' l'attesa
        # dell'estratto conto: non c'e' nessuna decisione da chiedere.
        update.update({
            "stato_finanziario": STATO_IN_ATTESA_ESTRATTO_CONTO,
            "metodo_pagamento_previsto": "banca",
            "metodo_pagamento_effettivo": None,
            "provvisorio": True,
            "decisione_pagamento_richiesta": False,
        })

    if fattura_id:
        await db[Collections.INVOICES].update_one(
            {"id": fattura_id}, {"$set": update}, session=session
        )
    invoice.update(update)
    if movimento_bancario and not esito.get("duplicato"):
        await _pubblica_fattura_pagata(
            db, fattura_id, metodo="banca",
            data_pagamento=movimento_bancario.get("data"),
            importo=round(abs(float(
                invoice.get("total_amount") or invoice.get("importo_totale") or 0
            )), 2),
            movimento_id=mov_id,
            source_module="fatture_upload_estratto_conto_auto",
        )
    return update


async def _applica_report_titolare(db, invoice: Dict[str, Any]) -> bool:
    """Il report «Fatture ricevute» puo' essere arrivato prima dell'XML: il
    pagamento dichiarato si applica all'arrivo della fattura. Ritorna False
    solo se il tentativo e' fallito."""
    try:
        from app.services.pagamenti_dichiarati_titolare import applica_per_fattura_arrivata
        await applica_per_fattura_arrivata(db, invoice)
        return True
    except Exception as exc:  # noqa: BLE001 - l'import della fattura resta valido
        logger.exception(
            "Pagamento dichiarato non applicato all'arrivo di %s (%s)",
            invoice.get("invoice_number"), type(exc).__name__,
        )
        return False


async def riprocessa_estratto_dopo_import_fattura(
    db, invoice: Dict[str, Any],
) -> Dict[str, Any]:
    """Riesamina l'EC gia' importato quando arriva dopo la relativa fattura.

    L'ordine di arrivo non deve cambiare l'esito: vengono selezionati i
    movimenti aperti con importo esatto oppure con il numero fattura nella
    causale (necessario per bonifici cumulativi) e passati al motore canonico.
    Il timestamp resta sulla fattura per rendere verificabile l'ultima
    scansione. Per i fornitori Cassa non viene interrogato l'estratto conto.
    """
    fattura_id = invoice.get("id") or invoice.get("invoice_key")
    metodo = normalizza_metodo_pagamento(invoice.get("metodo_pagamento"))
    now = datetime.now(timezone.utc).isoformat()

    try:
        from app.services.fornitore_da_fattura_banca import assegna_alla_fattura_arrivata
        await assegna_alla_fattura_arrivata(db, invoice)
    except Exception as exc:  # noqa: BLE001 - l'import della fattura resta valido
        logger.warning(
            "Fornitore del movimento non letto dalla fattura %s (%s)",
            invoice.get("invoice_number"), type(exc).__name__,
        )

    # Solo il fornitore pagato in contanti non passa dalla banca. Un metodo
    # ancora da decidere non e' un motivo per non guardare: il movimento con
    # identita' e importo al centesimo e' la prova, qualunque cosa dica
    # l'anagrafica.
    if metodo == "cassa":
        return {"eseguita": False, "motivo": "metodo_cassa"}

    importo = abs(float(invoice.get("total_amount") or invoice.get("importo_totale") or 0))
    numero = str(invoice.get("invoice_number") or invoice.get("numero_fattura") or "").strip()
    alternative = []
    if importo > 0:
        alternative.extend([
            {"importo": {"$gte": importo - 0.004, "$lte": importo + 0.004}},
            {"importo": {"$gte": -importo - 0.004, "$lte": -importo + 0.004}},
        ])
    if numero:
        # "41" dentro un CRO/IBAN o "1410" non e' la fattura 41. La
        # ricerca per sottostringa faceva ripassare decine di operazioni
        # estranee per ogni XML, fermando anche i PDF successivi in coda.
        # Restano validi prefissi FT41, suffissi 41/A e bonifici cumulativi;
        # il motore canonico verifica comunque identita' e importi.
        numero_regex = rf"(?<!\d){re.escape(numero)}(?!\d)"
        alternative.extend([
            {"descrizione": {"$regex": numero_regex, "$options": "i"}},
            {"descrizione_originale": {"$regex": numero_regex, "$options": "i"}},
        ])

    movimento_ids = []
    if alternative:
        candidati = await db["estratto_conto_movimenti"].find(
            {
                "tipo": "uscita",
                "riconciliato": {"$ne": True},
                "$or": alternative,
            },
            {"_id": 0, "id": 1},
        ).limit(500).to_list(500)
        movimento_ids = [m.get("id") for m in candidati if m.get("id")]

    risultato = {
        "success": True,
        "totale_riconciliati": 0,
        "movimenti_analizzati": 0,
        "ambito": "nuovi_movimenti",
    }
    if movimento_ids:
        from app.services.riconciliazione_bancaria import riconcilia_movimenti_banca
        risultato = await riconcilia_movimenti_banca(movimento_ids=movimento_ids)
        # Distinte con i numeri fattura in causale e abbinamenti per identita'
        # univoca: lo stesso motore del giro, ristretto a questi movimenti.
        from app.services.bank_payment_allocations import (
            reconcile_deterministic_invoice_allocations,
        )
        ancora_aperti = [
            m["id"] for m in await db["estratto_conto_movimenti"].find(
                {"id": {"$in": movimento_ids}, "riconciliato": {"$ne": True}},
                {"_id": 0, "id": 1},
            ).to_list(len(movimento_ids))
        ]
        if ancora_aperti:
            deterministica = await reconcile_deterministic_invoice_allocations(
                db, movement_ids=ancora_aperti,
            )
            risultato["allocazioni_deterministiche"] = (
                int(deterministica.get("allocati") or 0)
                + int(deterministica.get("allocati_identita") or 0)
            )

    audit = {
        "ultima_scansione_estratto_conto_at": now,
        "ultima_scansione_estratto_conto_candidati": len(movimento_ids),
        "ultima_scansione_estratto_conto_riconciliati": int(
            risultato.get("totale_riconciliati") or 0
        ),
    }
    if fattura_id:
        await db[Collections.INVOICES].update_one(
            {"id": fattura_id}, {"$set": audit}
        )
    invoice.update(audit)
    return {"eseguita": True, "movimento_ids": movimento_ids, **risultato}


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


async def process_fattura_to_db(db, parsed: Dict[str, Any], filename: str = "upload.xml",
                                 xml_raw: Optional[str] = None) -> Dict[str, Any]:
    """
    Processa e salva una fattura parsata nel database.
    Usata da documenti.py per l'import automatico.

    Fornitore, fattura e (se generata) prima nota vengono scritti in
    un'unica transazione repository: se un passaggio fallisce a metà, tutto viene
    annullato invece di lasciare stato incoerente (es. fornitore creato ma
    fattura mai salvata, o prima nota orfana senza il link sulla fattura).
    Il client di test in sandbox (archivio del runtime effimero) non supporta le sessioni: in
    quel caso si procede senza transazione, come prima.

    Args:
        db: Database connection
        parsed: Dati fattura parsati da parse_fattura_xml
        filename: Nome file originale
        xml_raw: XML originale (stringa), se disponibile — salvato sulla
            fattura insieme a xml_body_index così `/xml-originale` può
            servirlo (prima non veniva mai persistito da questo percorso,
            bug reale, review Codex PR #71).

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
        # Stessa chiave contabile: decide `decidi_stessa_chiave`, lo stesso
        # punto del giro Drive. Stesso originale → 409 «gia' presente» (il
        # chiamante lo conta come doppione, nuovi=0); originale diverso →
        # collisione: la copia entra «da verificare», bloccata e con alert.
        existing = await db[Collections.INVOICES].find_one(
            {"invoice_key": invoice_key}, session=session
        )
        identity_collision_ids: List[Any] = []
        if existing:
            if decidi_stessa_chiave(existing, None, xml_raw) == GIA_PRESENTE:
                raise HTTPException(status_code=409, detail=duplicate_detail)
            identity_collision_ids = [existing.get("id")]

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

        # NESSUNA SCADENZA. Decisione del titolare del 19/09/2026: «decido io
        # quando pagare, non c'e' una data stabilita». Il gestionale non legge
        # ne' le condizioni di pagamento dell'XML (rimessa diretta, 30 giorni
        # data fattura) ne' le date stampate sulla fattura, e non inventa un
        # «+30». Il piano rate resta comunque conservato sul documento: e' un
        # dato dell'originale, semplicemente non guida piu' niente.
        # Conseguenza voluta: `check_scadenze_partite_task` salta le partite
        # con `data_scadenza` nulla, quindi l'avviso FAT_DA_PAGARE_SCADUTA non
        # nasce piu' per le fatture fornitore. F24 e stipendi, che una
        # scadenza vera ce l'hanno, non sono toccati.
        data_scadenza = None

        pagamento_xml = _analizza_pagamento_xml(parsed, metodo_pagamento)
        metodo_canonico = normalizza_metodo_pagamento(metodo_pagamento)
        if metodo_canonico == "banca":
            stato_finanziario = "in_attesa_estratto_conto"
        elif metodo_canonico == "cassa" and len(parsed.get("pagamento_rate") or []) > 1:
            stato_finanziario = "provvisoria_rate"
        elif metodo_canonico == "cassa":
            stato_finanziario = "da_pagare"
        elif metodo_canonico == "misto":
            stato_finanziario = "provvisoria"
        else:
            stato_finanziario = "da_verificare"

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
            "pagamento": parsed.get("pagamento", {}),
            "pagamento_rate": parsed.get("pagamento_rate", []),
            "pagamento_rate_totale": parsed.get("pagamento_rate_totale"),
            "importo_ritenuta": parsed.get("importo_ritenuta"),
            "pagamento_rate_coerente": parsed.get("pagamento_rate_coerente"),
            "metodo_pagamento": metodo_pagamento,
            **pagamento_xml,
            "fornitore_dati_proposti": supplier_result.get("proposte_aggiornamento") or {},
            "stato_classificazione": "da_classificare",
            "stato_pagamento": "da_pagare",
            "stato_finanziario": stato_finanziario,
            "status": "imported",
            "source": "xml_upload",
            "filename": filename,
            "xml_raw": xml_raw,
            # Le impronte dell'originale: senza, la prossima copia con la
            # stessa chiave non si puo' confrontare e passa per collisione.
            "content_hash": _xml_content_hash(xml_raw),
            "content_hash_canonico": _impronta_canonica(xml_raw),
            "xml_body_index": parsed.get("body_index", 0),
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
            "dati_contratto": parsed.get("dati_contratto", []),
            "dati_ddt": parsed.get("dati_ddt", []),
            "tipo_documento_desc": parsed.get("tipo_documento_desc", ""),
            "duplicate_review_required": False,
            "identity_collision_with_ids": [],
            **(campi_collisione_identita(identity_collision_ids) if identity_collision_ids else {}),
        }

        await db[Collections.INVOICES].insert_one(invoice.copy(), session=session)
        invoice.pop("_id", None)

        logger.info(f"Fattura importata: {invoice.get('invoice_number')} - {invoice.get('supplier_name')}")

        if identity_collision_ids:
            # Collisione: nessun assegno, nessuna Prima Nota, nessuna nota di
            # credito collegata finche' gli originali non sono confrontati.
            await segna_collisione_identita(db, invoice, identity_collision_ids, session=session)
            return {
                "invoice": invoice,
                "supplier_id": supplier_id,
                "supplier_result": supplier_result,
                "intento_assegno": {},
                "collisione_identita": True,
            }

        from app.services.assegni_fattura_intent import collega_intento_assegno_a_fattura
        intento_assegno = await collega_intento_assegno_a_fattura(
            db, invoice, session=session,
        )
        if intento_assegno.get("collegato"):
            logger.info(
                "Fattura %s collegata all'assegno anticipato %s",
                invoice.get("invoice_number"), intento_assegno.get("assegno_id"),
            )

        # AUTO-REGISTRA in Prima Nota per metodo del fornitore (§29): cassa
        # scrive subito, banca/assegno attendono l'estratto conto, misto e
        # metodo mancante restano in Provvisori (vedi auto_registra_prima_nota).
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

        return {
            "invoice": invoice,
            "supplier_id": supplier_id,
            "supplier_result": supplier_result,
            "intento_assegno": intento_assegno,
        }

    try:
        async with db.transaction():
            outcome = await _do_import(None)
    except DuplicateRecordError as exc:
        raise HTTPException(status_code=409, detail=duplicate_detail) from exc

    invoice = outcome["invoice"]
    supplier_id = outcome["supplier_id"]
    supplier_result = outcome["supplier_result"]
    if outcome.get("collisione_identita"):
        # Stessa decisione del giro Drive: niente evento `fattura.created`,
        # niente partita, giornale, report del titolare o riscontri bancari
        # finche' un operatore non confronta i due originali.
        invoice["collisione_identita"] = True
        return invoice
    intento_assegno = outcome.get("intento_assegno") or {}
    if intento_assegno.get("completamento_banca_pendente"):
        from app.services.assegni_estratto_conto import (
            collega_assegno_riconciliato_a_fattura,
        )
        assegno_banca = await db["assegni"].find_one(
            {"id": intento_assegno.get("assegno_id")}, {"_id": 0},
        )
        fattura_salvata = await db[Collections.INVOICES].find_one(
            {"id": invoice.get("id")}, {"_id": 0},
        )
        if assegno_banca and fattura_salvata:
            await collega_assegno_riconciliato_a_fattura(
                db,
                assegno_banca,
                fattura_salvata,
                match_auto=True,
                match_livello="INTENTO_ASSEGNO_XML_EC",
            )
            invoice = await db[Collections.INVOICES].find_one(
                {"id": invoice.get("id")}, {"_id": 0},
            ) or invoice
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

    # LIBRO GIORNALE: il registro UNICO movimenti_contabili (motore §6.1) si
    # alimenta DOPO l'event bus qui sotto — vedi `_registra_in_partita_doppia`
    # (audit 03/09/2026 §2, PR 8) — perche' il handler di classificazione
    # (app/handlers/learning.py) scrive prima `iva_detraibile` sulla fattura.
    # Il vecchio registro parallelo scritture_contabili resta solo archivio
    # storico (A7, scelta utente 2026-07-13). Vedi LOGICA_LIBRO_MASTRO.md.

    # --- EVENT BUS: propaga evento fattura creata (upload manuale) ---
    # Fuori dalla transazione per design: è già gestita come fail-safe/
    # best-effort (try/except sotto) e non deve bloccare né essere
    # annullata se l'import principale (già commesso) è andato a buon fine.
    # Attiva i 4 handler su FATTURA_CREATED: crea_partita, alert_fornitore,
    # audit, righe_magazzino. Fail-safe per non bloccare l'import.
    try:
        from app.services.event_bus import propagate_event, EventTypes
        await propagate_event(
            EventTypes.FATTURA_CREATED,
            costruisci_evento_fattura_created(
                invoice,
                supplier_result=supplier_result,
                fornitore_id=supplier_id,
                metodo_pagamento=metodo_pagamento,
                data_scadenza=data_scadenza,
            ),
            db, source_module="fatture_upload_manuale",
        )
    except Exception:
        logger.exception("Errore propagazione evento fattura.created (upload manuale)")

    await _registra_in_partita_doppia(db, invoice.get("id"))

    try:
        await _riscontra_anticipo_pendente(db, invoice)
    except Exception:
        logger.exception(f"Riscontro anticipo pendente fallito per {invoice.get('invoice_number')}")

    await _applica_report_titolare(db, invoice)

    try:
        await riprocessa_estratto_dopo_import_fattura(db, invoice)
    except Exception:
        logger.exception(
            "Riprocessamento estratto dopo import fallito per %s",
            invoice.get("invoice_number"),
        )

    try:
        from app.services.paypal_reconciliation_links import collega_fattura_paypal_appena_importata
        await collega_fattura_paypal_appena_importata(db, invoice)
    except Exception:
        logger.exception(
            "Riprocessamento PayPal dopo import fallito per %s",
            invoice.get("invoice_number"),
        )

    # Documenti e' l'unico ingresso: le Ritenute sono una proiezione
    # automatica della fattura appena importata, non una seconda importazione
    # avviata dalla pagina Ritenute.
    try:
        from app.routers.ritenute import upsert_ritenuta_da_fattura

        await upsert_ritenuta_da_fattura(db, invoice)
    except Exception:
        logger.exception(
            "Aggiornamento proiezione Ritenute fallito per %s",
            invoice.get("invoice_number"),
        )

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
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "[Fatture] data fattura non interpretabile: finestra di ricerca "
                    "+/-90 giorni non applicata: %s", exc)

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
    except zipfile.BadZipFile as exc:
        raise ValueError(f"File ZIP corrotto o non valido: {zip_filename}") from exc

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
    if result.get("status") in ("fattura_emessa", "chiusura_rt"):
        # Non e' una fattura passiva: e' andata nel suo archivio.
        return {"success": True, "tipo": result["status"], "esito": result,
                "message": ("Fattura emessa: archiviata fra le fatture emesse"
                            if result["status"] == "fattura_emessa"
                            else "Chiusura RT: consegnata ai corrispettivi")}

    invoice = await db[Collections.INVOICES].find_one({"id": result["id"]}, {"_id": 0})
    return {
        "success": True,
        "message": f"Fattura {result.get('invoice_number')} importata",
        "invoice": invoice,
        "supplier": {"nome": result.get("supplier")},
    }


_SOURCE_METADATA_FIELDS = (
    "documento_inbox_id",
    "source_document_id",
    "drive_file_id",
    "source_parent_id",
    "source_path",
    "source_web_view_link",
    "source_modified_time",
    "source_mime_type",
    "source_size",
    "source_md5",
    "file_hash",
    "source_occurrences",
    "source_documents",
)


def _xml_content_hash(xml_raw: Optional[str]) -> Optional[str]:
    if not xml_raw:
        return None
    return hashlib.sha256(xml_raw.encode("utf-8")).hexdigest()


def _impronta_canonica(xml_raw: Optional[str]) -> Optional[str]:
    """Impronta del contenuto letto dall'XML (vedi fatture_identita)."""
    if not xml_raw:
        return None
    from app.services.fatture_identita import impronta_contenuto_fattura

    return impronta_contenuto_fattura(xml_raw)


def _documentary_candidate(
    source_metadata: Optional[Dict[str, Any]], xml_raw: Optional[str],
) -> Dict[str, Any]:
    candidate = dict(source_metadata or {})
    digest = _xml_content_hash(xml_raw)
    if digest:
        candidate["content_hash"] = digest
    canonica = _impronta_canonica(xml_raw)
    if canonica:
        candidate["content_hash_canonico"] = canonica
    return candidate


def _same_documentary_original(
    existing: Dict[str, Any], source_metadata: Optional[Dict[str, Any]],
    xml_raw: Optional[str],
) -> bool:
    from app.routers.invoices.invoices_main import _same_original
    from app.services.fatture_identita import (
        _testo_xml, ha_impronta_corrente, impronta_contenuto_fattura,
    )

    left = dict(existing)
    if existing.get("xml_raw") and not existing.get("content_hash"):
        left["content_hash"] = _xml_content_hash(existing.get("xml_raw"))
    if not ha_impronta_corrente(existing):
        # 17/09/2026: lo stesso documento gia' presente (es. copia legacy con
        # l'XML in fattura_allegata) con byte diversi per BOM/a capo/codifica
        # non e' una collisione: si confronta il contenuto letto dall'XML.
        xml_esistente = _testo_xml(existing)
        if xml_esistente:
            canonica = impronta_contenuto_fattura(xml_esistente)
            if canonica:
                left["content_hash_canonico"] = canonica
    return _same_original(left, _documentary_candidate(source_metadata, xml_raw))


#: Esiti di `decidi_stessa_chiave`: la fattura con la stessa chiave contabile
#: e' lo stesso documento (`gia_presente`, nessuna scrittura) oppure un altro
#: originale (`collisione`: entra «da verificare», con alert, mai scartata).
GIA_PRESENTE = "gia_presente"
COLLISIONE = "collisione"


def decidi_stessa_chiave(
    existing: Dict[str, Any], source_metadata: Optional[Dict[str, Any]],
    xml_raw: Optional[str],
) -> str:
    """L'unico punto che decide cosa fare di una fattura con la chiave gia' in archivio.

    Numero, fornitore e data uguali non bastano a dire «doppione»: lo dice solo
    l'originale (SHA-256 dei byte, impronta canonica del contenuto, id Drive).
    Stesso originale → `GIA_PRESENTE` (`nuovi=0`). Originale diverso →
    `COLLISIONE`: fino al 02/10/2026 Documenti > Import rispondeva «duplicata»
    e buttava la seconda copia, mentre il giro Drive la metteva da verificare
    con l'alert. Senza nessuna prova documentale (ne' XML ne' metadati) non si
    puo' dimostrare la differenza, e vale il doppione.
    """
    if not (source_metadata or xml_raw):
        return GIA_PRESENTE
    if _same_documentary_original(existing, source_metadata, xml_raw):
        return GIA_PRESENTE
    return COLLISIONE


def campi_collisione_identita(collision_ids: List[Any]) -> Dict[str, Any]:
    """I campi che marcano una copia in collisione: stato non archiviato,
    derivati bloccati, `stato_import` di collisione, riferimento reciproco."""
    ids = [i for i in collision_ids if i]
    return {
        "status": "da_verificare",
        "stato_derivati": "bloccato_collisione_identita",
        "stato_import": "collisione_identita_da_verificare",
        "duplicate_review_required": True,
        "identity_collision_with_ids": ids,
    }


async def segna_collisione_identita(db, invoice: Dict[str, Any], collision_ids: List[Any],
                                    session=None) -> None:
    """Collega le due copie fra loro e apre l'alert: nessun pagamento, scadenza
    o giornale finche' un operatore non confronta gli originali."""
    ids = [i for i in collision_ids if i]
    if not ids:
        return
    await db[Collections.INVOICES].update_one(
        {"id": ids[0]},
        {"$set": {"duplicate_review_required": True},
         "$addToSet": {"identity_collision_with_ids": invoice["id"]}},
        session=session,
    )
    try:
        from app.services.alert_engine import genera_alert
        await genera_alert(
            "FATTURA_IDENTITA_DA_VERIFICARE", invoice["id"],
            Collections.INVOICES,
            "Chiave contabile coincidente ma originale documentale diverso",
            db,
            extra={"collision_with_ids": ids},
        )
    except Exception:
        logger.exception("Creazione alert collisione fattura fallita")


def _source_metadata_fields(
    metadata: Optional[Dict[str, Any]],
    existing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Conserva solo metadati di provenienza espliciti e non li perde in promozione."""
    metadata = metadata or {}
    existing = existing or {}
    result: Dict[str, Any] = {}
    for key in _SOURCE_METADATA_FIELDS:
        if key in {"source_occurrences", "source_documents"}:
            merged = []
            for value in [*(existing.get(key) or []), *(metadata.get(key) or [])]:
                if value not in merged:
                    merged.append(value)
            if merged:
                result[key] = merged
        elif existing.get(key) is not None:
            # Il primo originale registrato resta il riferimento canonico.
            result[key] = existing[key]
        elif metadata.get(key) is not None:
            result[key] = metadata[key]
    return result


#: Il tag radice di una chiusura giornaliera del registratore telematico
#: (tracciato COR10 dell'Agenzia delle Entrate). Il prefisso di namespace
#: cambia da un registratore all'altro (`n1:`, `p:`, nessuno), quindi si
#: confronta il nome locale e non la stringa intera.
_RADICE_CHIUSURA_RT = re.compile(r"<(?:[A-Za-z0-9_.-]+:)?DatiCorrispettivi[\s>]")


def e_chiusura_rt(xml_content: str) -> bool:
    """Vero se questo XML e' una chiusura di cassa, non una fattura.

    Si guarda il contenuto, mai il nome del file: i file RT si chiamano
    `<progressivo>_<piva>.xml`, cioe' esattamente come certe fatture.

    La fattura vince sempre: se nella testa del documento compare
    `FatturaElettronica`, quello e' il documento, e un `DatiCorrispettivi`
    piu' avanti puo' solo essere testo dentro un allegato o una descrizione.
    Senza questa precedenza basterebbe una parola in una riga di fattura per
    dirottare un costo vero nei ricavi.
    """
    testa = xml_content.lstrip("﻿ \t\r\n")[:4000]
    if re.search(r"<(?:[A-Za-z0-9_.-]+:)?FatturaElettronica[\s>]", testa):
        return False
    return bool(_RADICE_CHIUSURA_RT.search(testa))


async def _consegna_chiusura_rt(
    db, xml_content: str, filename: str, source: str, applica_filtro_anno: bool,
) -> Dict[str, Any]:
    """Passa una chiusura RT finita nel canale fatture al motore dei corrispettivi.

    Il 20/09/2026 in `01_FATTURE_RICEVUTE/FATTURE/2026/Errori` c'erano
    **19 chiusure RT**: il canale fatture le leggeva come XML rotti
    («FatturaElettronicaBody non trovato»), le spediva in `Errori` e le
    rileggeva a ogni giro senza mai importarle. Con loro erano fuori dai
    conti gli incassi del 25, 26 e 27 agosto.

    Non si duplica il motore: `ingest_corrispettivo_parsed` resta l'unico
    che sa registrare un corrispettivo (Prima Nota cassa per i contanti,
    banca per l'elettronico, partita doppia) ed e' idempotente, quindi una
    giornata gia' in archivio torna `duplicate` senza scrivere nulla.
    """
    from app.parsers.corrispettivi_parser import parse_corrispettivo_xml
    from app.routers.invoices.corrispettivi_helpers import ingest_corrispettivo_parsed

    parsed = parse_corrispettivo_xml(xml_content)
    if parsed.get("error"):
        logger.warning(
            "[Fatture] %s e' una chiusura RT, ma il parser dei corrispettivi la rifiuta: %s",
            filename, parsed["error"])
        return {"status": "error", "filename": filename,
                "error": f"chiusura RT illeggibile: {parsed['error']}"}
    if db is None:
        # Anteprima senza archivio (test, validazione di un upload manuale):
        # si dice che cos'e', non si scrive.
        return {"status": "chiusura_rt", "filename": filename,
                "data": parsed.get("data"), "importato": False}

    if applica_filtro_anno:
        # Nel gestionale resta solo l'anno attivo, e la regola vale per i
        # corrispettivi esattamente come per le fatture: una chiusura di un
        # anno passato non entra, l'originale resta su Drive.
        from app.services.config_import import get_anno_importazione_attivo
        data_rt = str(parsed.get("data") or "")
        anno_rt = int(data_rt[:4]) if data_rt[:4].isdigit() else None
        anno_attivo = await get_anno_importazione_attivo(db)
        if anno_rt and anno_rt != anno_attivo:
            logger.info(
                "[Fatture] %s e' la chiusura RT del %s, l'anno attivo e' %s: "
                "non entra nei corrispettivi, l'originale resta su Drive",
                filename, data_rt, anno_attivo)
            return {"status": "chiusura_rt", "filename": filename,
                    "data": data_rt, "anno": anno_rt, "anno_attivo": anno_attivo,
                    "importato": False, "azione": "skipped_altro_anno"}

    esito = await ingest_corrispettivo_parsed(
        db, parsed, filename=filename, source="xml", update_if_exists=False)
    if esito.get("action") == "scartato":
        # Chi smista manda il file in ERRORI col motivo: non e' una giornata
        # importata, e nemmeno un doppione.
        return {"status": "error", "filename": filename, "data": esito.get("data"),
                "motivo": esito.get("motivo"),
                "error": f"chiusura RT del {esito.get('data')} scartata: {esito.get('motivo')}"}
    logger.info(
        "[Fatture] %s non e' una fattura ma la chiusura RT del %s, arrivata nel "
        "canale fatture da %s: consegnata ai corrispettivi (%s)",
        filename, esito.get("data"), source, esito.get("action"))
    return {
        "status": "chiusura_rt",
        "filename": filename,
        "data": esito.get("data"),
        "azione": esito.get("action"),
        "corrispettivo_id": esito.get("corrispettivo_id"),
        "importato": esito.get("action") in ("created", "updated"),
    }


async def process_xml_bytes(
    db,
    content: bytes,
    filename: str,
    source: str = "xml_upload",
    applica_filtro_anno: bool = False,
    replay_storico: bool = False,
    promote_existing_id: Optional[str] = None,
    promote_invoice_key: Optional[str] = None,
    source_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Pipeline CONDIVISA per importare una singola fattura XML dai suoi bytes.

    Usata sia dall'upload bulk (`/upload-xml-bulk`) sia dall'ingest Google Drive,
    per non duplicare la logica di decodifica/parse/dedup/import.

    `applica_filtro_anno` (SOLO per l'ingest automatico dalla cartella Drive
    condivisa): se True e la data fattura non è nell'anno attivo, la fattura
    **non entra affatto** e si torna `skipped_altro_anno` — decisione del
    titolare del 20/09/2026, che ha superato quella del 14/07/2026 (allora
    entrava come archivio di sola consultazione). L'originale resta su Drive,
    che è la fonte documentale. Default False: l'upload manuale via UI e le
    altre fonti (PEC/SDI, fatture estere) restano invariate, un utente che
    carica volontariamente una fattura di un anno passato si aspetta che
    venga registrata normalmente.

    Ritorna un dict con `status` in {"imported", "duplicate", "error",
    "skipped_altro_anno", "chiusura_rt"}. Chi smista l'esito deve conoscerli
    tutti: uno stato sconosciuto finisce nel ramo «errore» e manda in
    `Errori` un file sano, che verrà riletto per sempre.
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

    # 1bis. Una chiusura di cassa non e' una fattura. Prima di provare a
    # leggerla come tale — cosa che fallirebbe con «FatturaElettronicaBody non
    # trovato» e la manderebbe in `Errori` per sempre — la si riconosce dal
    # contenuto e la si consegna al motore dei corrispettivi.
    if e_chiusura_rt(xml_content):
        return await _consegna_chiusura_rt(
            db, xml_content, filename, source, applica_filtro_anno)

    # 2. Parse fattura elettronica
    parsed = parse_fattura_xml(xml_content)
    if parsed.get("error"):
        return {"status": "error", "filename": filename, "error": parsed["error"]}

    # 2bis. Una fattura che abbiamo emesso noi non e' un acquisto: si
    # riconosce dal cedente (la nostra P.IVA) e va nelle fatture emesse.
    from app.services.fatture_emesse import e_fattura_emessa, registra_fattura_emessa

    if e_fattura_emessa(parsed):
        if db is None:
            return {"status": "fattura_emessa", "filename": filename, "importato": False}
        esito = await registra_fattura_emessa(
            db, parsed, xml_raw=xml_content, filename=filename, source=source)
        # Gia' in archivio o appena archiviata: per chi smista e' lavorata.
        return {**esito, "status": "error" if esito.get("status") == "error" else "fattura_emessa",
                "filename": filename}

    # Un file FatturaPA può contenere PIÙ fatture raggruppate (più
    # <FatturaElettronicaBody> sotto lo stesso header/CedentePrestatore —
    # caso reale per fatture differite spedite insieme). Prima venivano
    # lette solo dal parser e la fattura in più andava persa silenziosamente
    # (importo/righe mai registrati). "altri_body" contiene le fatture
    # aggiuntive trovate nello stesso file: vanno importate anche loro, una
    # per una, con la stessa logica della prima (bug reale 19/07/2026).
    altri_body = parsed.pop("_altri_body", None) or []

    async def _importa_una(p: Dict[str, Any]) -> Dict[str, Any]:
        parsed_key = generate_invoice_key(
            p.get("invoice_number", ""),
            p.get("supplier_vat", ""),
            p.get("invoice_date", ""),
        )
        if promote_invoice_key and parsed_key != promote_invoice_key:
            return {
                "status": "duplicate",
                "filename": filename,
                "invoice_number": p.get("invoice_number"),
                "skipped_other_body": True,
            }
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
                # Decisione del titolare (06/10/2026, supera quella del 20/09): le
                # fatture di un altro anno entrano in `invoices` come
                # `archivio_storico`, sola consultazione. Niente Prima Nota, partite,
                # giornale, IVA, magazzino, alert ne' costi: i filtri di
                # «fattura attiva» le escludono (`STATI_IMPORT_NON_ATTIVI`).
                logger.info(
                    "[Fatture] %s è del %s, l'anno attivo è %s: archivio storico, "
                    "solo consultazione", filename, anno_fattura, anno_attivo)
                # Titolare, 28/09/2026: quella dell'anno prima resta anche un debito
                # da chiudere col bonifico dell'anno attivo (niente costo né IVA).
                debito = None
                from app.services import debiti_anno_precedente as dap
                if dap.e_anno_precedente(p, anno_attivo):
                    try:
                        debito = await dap.registra(
                            db, p, drive_file_id=(source_metadata or {}).get("drive_file_id"))
                    except Exception as exc:  # noqa: BLE001 - non blocca l'import
                        logger.warning("[Fatture] %s: debito anno precedente non registrato (%s: %s)",
                                       filename, type(exc).__name__, exc)
                kwargs = {"xml_raw": xml_content, "stato_import": STATO_ARCHIVIO_STORICO}
                if source_metadata is not None:
                    kwargs["source_metadata"] = source_metadata
                esito = await import_parsed_invoice(db, p, filename, source, **kwargs)
                return {**esito, "debito_anno_precedente": debito,
                        "archivio_storico": True, "anno": anno_fattura, "anno_attivo": anno_attivo}

        if replay_storico:
            kwargs = {"xml_raw": xml_content, "replay_storico": True}
            if source_metadata is not None:
                kwargs["source_metadata"] = source_metadata
            return await import_parsed_invoice(db, p, filename, source, **kwargs)
        kwargs = {"xml_raw": xml_content}
        if source_metadata is not None:
            kwargs["source_metadata"] = source_metadata
        if promote_existing_id:
            kwargs["existing_invoice_id"] = promote_existing_id
        return await import_parsed_invoice(db, p, filename, source, **kwargs)

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


# Le fatture di un altro anno entrano come `archivio_storico` (06/10/2026): stessa
# pipeline di `import_parsed_invoice`, ma si ferma dopo aver scritto il documento.
STATO_ARCHIVIO_STORICO = "archivio_storico"


async def import_parsed_invoice(db, parsed: Dict[str, Any], filename: str, source: str,
                                 xml_raw: Optional[str] = None,
                                 piva_validator=_piva_plausibile,
                                 replay_storico: bool = False,
                                 existing_invoice_id: Optional[str] = None,
                                 source_metadata: Optional[Dict[str, Any]] = None,
                                 stato_import: Optional[str] = None) -> Dict[str, Any]:
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
    existing_invoice = await db[Collections.INVOICES].find_one(
        {"invoice_key": invoice_key}, {"_id": 0}
    )
    if existing_invoice and str(existing_invoice.get("id")) != str(existing_invoice_id or ""):
        if decidi_stessa_chiave(existing_invoice, source_metadata, xml_raw) == GIA_PRESENTE:
            provenance = _source_metadata_fields(source_metadata, existing_invoice)
            if provenance:
                await db[Collections.INVOICES].update_one(
                    {"id": existing_invoice.get("id")}, {"$set": provenance}
                )
            return {
                "status": "duplicate", "filename": filename,
                "id": existing_invoice.get("id"),
                "invoice_number": parsed.get("invoice_number"),
                "derivati_incompleti": existing_invoice.get("stato_derivati") in {
                    "da_ricalcolare", "errore",
                },
            }
        # Numero, fornitore e data coincidono ma l'originale no: non e' una
        # deduplica dimostrata. Importa separatamente e lascia la collisione
        # esplicita, senza collegare o sovrascrivere il record precedente.
        identity_collision_ids = [existing_invoice.get("id")]
    else:
        identity_collision_ids = []
    if existing_invoice_id and not existing_invoice:
        return {"status": "error", "filename": filename,
                "error": "Fattura storica da promuovere non trovata"}
    base_existing = existing_invoice if existing_invoice_id else {}

    # 4. Fornitore (crea se nuovo) + metodo pagamento
    supplier_result = await ensure_supplier_exists(db, parsed, piva_validator=piva_validator)
    # REGOLA: metodo pagamento SOLO dal fornitore (mai dal documento).
    # Se il fornitore non ha un metodo → "sospesa" → resta nei provvisori.
    metodo_pagamento = supplier_result.get("metodo_pagamento") or "sospesa"

    # Nessuna scadenza: stessa decisione del titolare applicata all'upload
    # manuale (vedi il commento esteso li').
    invoice_date = parsed.get("invoice_date", "")
    data_scadenza = None

    # 5. Documento fattura + insert (stessi campi dell'upload manuale, inclusi
    #    i campi speculari in italiano usati da filtri e pagine contabili)
    invoice = {
        "id": str(existing_invoice_id or uuid.uuid4()),
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
        "descrizione_righe_ai": parsed.get("descrizione_righe_ai") or [],
        "pagamento_rate": parsed.get("pagamento_rate", []),
        "pagamento_rate_totale": parsed.get("pagamento_rate_totale"),
        "importo_ritenuta": parsed.get("importo_ritenuta"),
        "pagamento_rate_coerente": parsed.get("pagamento_rate_coerente"),
        "causali": parsed.get("causali", []),
        "dati_fatture_collegate": parsed.get("dati_fatture_collegate", []),
        "dati_ordine_acquisto": parsed.get("dati_ordine_acquisto", []),
        "dati_contratto": parsed.get("dati_contratto", []),
        "dati_ddt": parsed.get("dati_ddt", []),
        "metodo_pagamento": metodo_pagamento,
        "status": "imported",
        "source": base_existing.get("source") or source,
        "source_history": list(dict.fromkeys([
            *(base_existing.get("source_history") or []),
            *(([base_existing.get("source")] if base_existing.get("source") else [])),
            source,
        ])),
        "filename": filename,
        "xml_raw": xml_raw,
        "content_hash": _xml_content_hash(xml_raw),
        "content_hash_canonico": _impronta_canonica(xml_raw),
        "xml_body_index": parsed.get("body_index", 0),
        "created_at": base_existing.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "cedente_piva": parsed.get("supplier_vat", ""),
        "cedente_denominazione": parsed.get("supplier_name", ""),
        "numero_fattura": parsed.get("invoice_number", ""),
        "data_fattura": invoice_date,
        "importo_totale": float(parsed.get("total_amount", 0) or 0),
        "anno": int(invoice_date[:4]) if invoice_date[:4].isdigit() else None,
        "replay_storico": replay_storico,
        "stato_derivati": "non_applicabile" if stato_import == STATO_ARCHIVIO_STORICO else "da_ricalcolare",
        "stato_import": stato_import or ("promosso_da_archivio" if existing_invoice_id else "attivo"),
        "promotion_source": source if existing_invoice_id else None,
        "promoted_at": datetime.now(timezone.utc).isoformat() if existing_invoice_id else None,
        "duplicate_review_required": False,
        "identity_collision_with_ids": [],
        **_source_metadata_fields(source_metadata, base_existing),
        **(campi_collisione_identita(identity_collision_ids) if identity_collision_ids else {}),
    }
    if parsed.get("verifica_ai") == "in_attesa":
        invoice["verifica_ai"] = "in_attesa"
        invoice["stato_derivati"] = "in_attesa_verifica_ai"
    if existing_invoice_id:
        await db[Collections.INVOICES].update_one(
            {"id": existing_invoice_id}, {"$set": invoice}
        )
    else:
        await db[Collections.INVOICES].insert_one(invoice.copy())
    invoice.pop("_id", None)

    if invoice.get("verifica_ai") == "in_attesa":
        return {"status": "imported", "filename": filename, "id": invoice["id"],
                "invoice_number": invoice.get("invoice_number"), "supplier": invoice.get("supplier_name"),
                "stato_derivati": "in_attesa_verifica_ai"}

    # Anche da qui (Drive, cartella unica) la ritenuta della parcella entra
    # nella proiezione Ritenute: prima la alimentava solo l'upload manuale.
    try:
        from app.routers.ritenute import upsert_ritenuta_da_fattura

        if stato_import != STATO_ARCHIVIO_STORICO:
            await upsert_ritenuta_da_fattura(db, invoice)
    except Exception as exc:
        logger.warning(
            "Proiezione Ritenute non aggiornata per la fattura %s (%s): %s",
            invoice.get("invoice_number"), type(exc).__name__, exc,
        )

    if identity_collision_ids:
        await segna_collisione_identita(db, invoice, identity_collision_ids)
        return {
            "status": "imported", "requires_review": True,
            "filename": filename,
            "invoice_number": parsed.get("invoice_number"),
            "supplier": parsed.get("supplier_name"), "id": invoice["id"],
        }

    # La ricostruzione dell'archivio non equivale all'arrivo di una nuova
    # fattura. Il replay deve prima rendere nuovamente consultabile il
    # documento canonico, senza riattivare in blocco magazzino, alert,
    # scadenzario e riconciliazioni storiche. Questi derivati vengono
    # ricalcolati in una fase dedicata e idempotente.
    if replay_storico or stato_import == STATO_ARCHIVIO_STORICO:
        return {
            "status": "imported",
            "filename": filename,
            "invoice_number": parsed.get("invoice_number"),
            "supplier": parsed.get("supplier_name"),
            "id": invoice["id"],
            "replay_storico": bool(replay_storico),
            "archivio_storico": stato_import == STATO_ARCHIVIO_STORICO,
        }

    # Giacenze magazzino: aggiornate qui sotto tramite l'event bus (punto 7,
    # EventTypes.FATTURA_CREATED -> on_fattura_righe_magazzino), NON in modo
    # sincrono in questa funzione. Vedi memoria/moduli/MAGAZZINO.md — questo
    # commento diceva erroneamente che l'import fatture non tocca mai
    # warehouse_inventory; in realtà l'handler dell'event bus lo aggiorna.

    # 6. Prima Nota per metodo del fornitore (§29): cassa scrive subito,
    #    banca/assegno attendono l'estratto conto, misto e metodo mancante
    #    restano in Provvisori (vedi auto_registra_prima_nota).
    derivati_errori = []
    try:
        await auto_registra_prima_nota(db, invoice, metodo_pagamento)
    except Exception:
        derivati_errori.append("prima_nota")
        logger.exception(f"Errore auto-registrazione prima nota per {filename}")

    # Nota di credito: collega alla fattura originale e ricalcola il netto.
    try:
        nc_update = await _collega_nota_credito(db, invoice)
        if nc_update:
            invoice.update(nc_update)
    except Exception:
        derivati_errori.append("nota_credito")
        logger.exception(f"Errore collegamento nota di credito per {filename}")

    # 7. Event bus: crea partita scadenziario, alert fornitore, audit.
    #    Best-effort: un errore qui non deve far fallire l'import.
    try:
        from app.services.event_bus import propagate_event, EventTypes
        await propagate_event(
            EventTypes.FATTURA_CREATED,
            costruisci_evento_fattura_created(
                invoice,
                supplier_result=supplier_result,
                metodo_pagamento=metodo_pagamento,
                data_scadenza=data_scadenza,
            ),
            db, source_module=f"fatture_upload_{source}",
        )
    except Exception:
        derivati_errori.append("evento_fattura_created")
        logger.exception(f"Errore propagazione evento fattura.created ({source})")

    if not await _applica_report_titolare(db, invoice):
        derivati_errori.append("pagamento_dichiarato_titolare")

    try:
        await riprocessa_estratto_dopo_import_fattura(db, invoice)
    except Exception:
        derivati_errori.append("riconciliazione_banca")
        logger.exception(
            "Riprocessamento estratto dopo import fallito per %s",
            invoice.get("invoice_number"),
        )

    try:
        from app.services.paypal_reconciliation_links import collega_fattura_paypal_appena_importata
        await collega_fattura_paypal_appena_importata(db, invoice)
    except Exception:
        derivati_errori.append("riconciliazione_paypal")
        logger.exception(
            "Riprocessamento PayPal dopo import fallito per %s",
            invoice.get("invoice_number"),
        )

    # 8. Libro giornale (partita doppia) — audit 03/09/2026 §2, PR 8.
    esito_giornale = await _registra_in_partita_doppia(db, invoice["id"])
    if esito_giornale.get("stato") == "errore":
        derivati_errori.append("libro_giornale")

    stato_derivati = "errore" if derivati_errori else "allineato"
    await db[Collections.INVOICES].update_one(
        {"id": invoice["id"]},
        {"$set": {
            "stato_derivati": stato_derivati,
            "derivati_errori": derivati_errori,
            "derivati_aggiornati_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    return {"status": "imported", "filename": filename,
            "invoice_number": parsed.get("invoice_number"),
            "supplier": parsed.get("supplier_name"), "id": invoice["id"],
            "stato_derivati": stato_derivati}


async def _registra_in_partita_doppia(db, fattura_id: Optional[str]) -> Dict[str, Any]:
    """Registrazione automatica nel libro giornale (motore unico
    `registrazione_contabile`, idempotente per documento).

    Rilegge la fattura dal database perche' i handler dell'event bus
    (classificazione centro di costo → `iva_detraibile`) l'hanno appena
    arricchita: senza IVA detraibile classificata il motore, per regola,
    non crea credito IVA e lascia la fattura `da_verificare`. Best-effort:
    nessun errore contabile blocca l'import.
    """
    if not fattura_id:
        return {"stato": "saltato", "motivo": "fattura senza id"}
    try:
        from app.services.registrazione_contabile import registra_documento_import
        fattura_db = await db[Collections.INVOICES].find_one(filtro_id(fattura_id), {"_id": 0})
        if not fattura_db:
            return {"stato": "saltato", "motivo": "fattura non trovata"}
        return await registra_documento_import(db, "fattura", fattura_db)
    except Exception:
        logger.exception("Registrazione in partita doppia fallita per la fattura %s", fattura_id)
        return {"stato": "errore"}


async def process_fattura_estera_pdf(db, pdf_base64: str, filename: str,
                                      source: str = "email_gmail_estera",
                                      documento_inbox_id: Optional[str] = None) -> Dict[str, Any]:
    """Fattura ESTERA arrivata come PDF via email (mai XML: lo SDI è solo
    italiano). Estrae i dati con l'AI già usata per gli altri documenti
    (`document_ai_extractor`, stessa ANTHROPIC_API_KEY già configurata) e la
    importa con la pipeline condivisa `import_parsed_invoice`: stessa
    deduplica e stesso fornitore, ma i derivati contabili attendono la
    conferma esplicita dei dati nella pagina di verifica.

    Se l'estrazione fallisce o non legge né numero né importo, non crea
    nulla: meglio lasciare il PDF solo archiviato (comportamento di prima)
    che registrare una fattura con dati inventati.

    A differenza delle fatture XML italiane (lettura deterministica), la
    fattura creata qui viene marcata `verifica_ai: "in_attesa"` e resta
    nella coda `/api/fatture-estere/da-verificare` finché l'utente non
    conferma o corregge i dati letti (scelta utente 14/07/2026, per avere
    un rating di affidabilità della lettura AI per fornitore).
    """
    # Conserva la prova prima dell'estrazione: anche un errore del lettore
    # deve lasciare l'originale consultabile, non una fattura senza PDF.
    import base64
    from app.utils.upload_validation import verifica_pdf_reale

    content = base64.b64decode(pdf_base64, validate=True)
    verifica_pdf_reale(content, filename)
    digest = hashlib.sha256(content).hexdigest()
    existing = await db[Collections.INVOICES].find_one(
        {"file_hash": digest, "entity_status": {"$ne": "deleted"}, "status": {"$ne": "deleted"}},
        {"_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1},
    )
    if not documento_inbox_id:
        inbox = await db["documents_inbox"].find_one({"sha256": digest}, {"_id": 0, "id": 1})
        documento_inbox_id = (inbox or {}).get("id") or f"fattura-pdf-{digest}"
        if not inbox:
            await db["documents_inbox"].insert_one({
                "id": documento_inbox_id, "filename": filename, "sha256": digest,
                "pdf_data": pdf_base64, "category": "fattura", "status": "da_verificare",
                "processed": False, "source": source,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        else:
            # Ripristina un payload mancante anche sulla stessa inbox. Il
            # deposito canonico lo conserva su Drive; non crea una fattura.
            await db["documents_inbox"].update_one(
                {"id": documento_inbox_id}, {"$set": {"pdf_data": pdf_base64}},
            )
    if existing:
        await db[Collections.INVOICES].update_one(
            {"id": existing["id"]}, {"$set": {"documento_inbox_id": documento_inbox_id}},
        )
        await db["documents_inbox"].update_one(
            {"id": documento_inbox_id}, {"$set": {"invoice_id": existing["id"]}},
        )
        return {"status": "duplicate", "filename": filename, "id": existing.get("id"),
                "invoice_number": existing.get("invoice_number"), "supplier": existing.get("supplier_name")}
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
    parsed["verifica_ai"] = "in_attesa"

    if not parsed.get("invoice_number") and not parsed.get("total_amount"):
        return {"status": "dati_insufficienti", "filename": filename}
    # Un fornitore italiano manda l'XML allo SDI: il suo PDF e' una copia di
    # cortesia, non una seconda fonte (e la fattura arriverebbe due volte).
    piva = str(parsed.get("supplier_vat") or "").upper().replace(" ", "")
    if piva.startswith("IT") or re.fullmatch(r"\d{11}", piva):
        return {"status": "fattura_italiana_pdf", "filename": filename,
                "error": "fornitore italiano: la fattura arriva come XML dallo SDI"}

    esito = await import_parsed_invoice(db, parsed, filename, source, xml_raw=None,
                                         piva_validator=_piva_estera_plausibile,
                                         source_metadata={"file_hash": digest, "documento_inbox_id": documento_inbox_id})

    if esito.get("id"):
        await db["documents_inbox"].update_one({"id": documento_inbox_id}, {"$set": {
            "invoice_id": esito["id"], "processed": True, "status": "elaborato",
        }})

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
        # Solo testo, senza importi: righe inventate per prezzo finirebbero
        # in magazzino e in Lotti. Servono a dire COSA si e' comprato.
        "descrizione_righe_ai": [
            str(riga).strip() for riga in (data.get("descrizione_righe") or [])
            if str(riga or "").strip()
        ],
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
        elif status in ("fattura_emessa", "chiusura_rt"):
            # Emessa da noi o chiusura di cassa: archiviata dove deve stare.
            results.setdefault("altri_archivi", []).append(
                {"filename": filename, "tipo": status, "numero": res.get("numero")})
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
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[Fatture] audit di sicurezza della cancellazione massiva "
            "NON registrato: %s", exc)
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
        filtro_id(invoice_id),
        {"$set": update_data}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    # 17/09/2026 (collaudo): la classificazione manuale scriveva solo il centro
    # di costo. Il motore del libro giornale, per regola, non registra una
    # fattura con IVA finche' `iva_detraibile` non e' classificata, quindi una
    # fattura di fornitore nuovo restava "da_verificare" senza nessuna azione
    # per sbloccarla. Ora la scelta del centro di costo ricalcola gli stessi
    # importi fiscali del handler automatico (calcola_importi_fiscali, nessuna
    # seconda formula) e chiede la registrazione al motore unico, idempotente.
    registrazione = None
    try:
        from app.services.learning_machine_cdc import (
            CENTRI_COSTO, calcola_importi_fiscali, somma_gia_dedotto_periodo_anno,
        )
        from app.services.registrazione_contabile import registra_documento_import

        cdc_config = CENTRI_COSTO.get(centro_costo_id) or next(
            (cfg for cfg in CENTRI_COSTO.values() if cfg.get("codice") == centro_costo_id), None,
        ) or (cdc if cdc and cdc.get("detraibilita_iva") is not None else None)
        fattura_db = await db[Collections.INVOICES].find_one(filtro_id(invoice_id), {"_id": 0})
        if cdc_config is not None and fattura_db:
            imponibile = float(fattura_db.get("imponibile") or fattura_db.get("subtotal") or 0)
            iva = float(fattura_db.get("iva") or fattura_db.get("total_tax") or 0)
            numero_contratto_noleggio = None
            gia_dedotto_anno = 0.0
            if cdc_config.get("limite_annuo"):
                # Stesso cumulo annuo per contratto dell'handler automatico
                # (audit 19/09/2026, punto 4): una riclassificazione manuale
                # non deve riazzerare il tetto dell'art. 164 TUIR.
                from app.services.noleggio.parsers import estrai_numero_contratto

                numero_contratto_noleggio = estrai_numero_contratto(fattura_db)
                try:
                    anno_riferimento = int(str(
                        fattura_db.get("invoice_date") or fattura_db.get("data_fattura") or ""
                    )[:4])
                except (TypeError, ValueError):
                    anno_riferimento = None
                gia_dedotto_anno = await somma_gia_dedotto_periodo_anno(
                    db, cdc_id=centro_costo_id, anno=anno_riferimento,
                    numero_contratto=numero_contratto_noleggio,
                    fornitore_piva=fattura_db.get("supplier_vat"),
                    escludi_fattura_id=invoice_id,
                )
            importi = calcola_importi_fiscali(
                imponibile, iva, cdc_config, imponibile_gia_dedotto_anno=gia_dedotto_anno,
            )
            aggiornamento = {
                "iva_detraibile": importi.get("iva_detraibile", 0),
                "iva_indetraibile": importi.get("iva_indetraibile", 0),
                "imponibile_deducibile_ires": importi.get("imponibile_deducibile_ires", 0),
                "imponibile_indeducibile_ires": importi.get("imponibile_indeducibile_ires", 0),
                "classificato_da": "manuale",
                "stato_classificazione": "classificata",
            }
            if cdc_config.get("limite_annuo"):
                aggiornamento["numero_contratto_noleggio"] = numero_contratto_noleggio
                aggiornamento["imponibile_limitato_periodo"] = importi.get("imponibile_limitato_periodo")
            await db[Collections.INVOICES].update_one(filtro_id(invoice_id), {"$set": aggiornamento})
            fattura_db = await db[Collections.INVOICES].find_one(filtro_id(invoice_id), {"_id": 0})
            registrazione = await registra_documento_import(db, "fattura", fattura_db)
        elif fattura_db is not None:
            registrazione = {"stato": "saltato",
                             "motivo": f"centro di costo {centro_costo_id} senza detraibilita' IVA configurata"}
    except Exception:
        logger.exception("Classificazione manuale: registrazione contabile non eseguita per %s", invoice_id)
        registrazione = {"stato": "errore"}

    return {
        "success": True,
        "message": f"Fattura classificata come '{centro_costo_nome}'",
        "centro_costo_id": centro_costo_id,
        "centro_costo_nome": centro_costo_nome,
        "registrazione_contabile": registrazione,
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
    invoice = await db[Collections.INVOICES].find_one(filtro_id(invoice_id))
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    if invoice.get("pagato") or invoice.get("status") == "paid":
        raise HTTPException(status_code=400, detail="Fattura già pagata")

    rate_xml = invoice.get("pagamento_rate") or []
    if len(rate_xml) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                f"La fattura contiene {len(rate_xml)} rate XML: collega e conferma "
                "le singole evidenze di pagamento, non il totale documento."
            ),
        )

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
    invoice = await db[Collections.INVOICES].find_one(filtro_id(invoice_id))
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

    invoice = await db[Collections.INVOICES].find_one(filtro_id(invoice_id))
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
