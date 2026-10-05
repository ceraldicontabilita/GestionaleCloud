"""
Router Verbali Noleggio - Scarica verbali dalla posta e li associa alle fatture.

Cerca nelle cartelle email i verbali (pattern Bxxxxxxxxxx) e li associa
alle righe corrispondenti nelle fatture noleggio.

Endpoint rimossi il 14/07/2026 (piano residuo op.10, zero chiamanti verificati):
associa-fatture, cartelle-verbali, classifica-verbali-posta, operazioni-sospese,
riclassifica-verbale, riconcilia, risolvi-sospeso, scansiona-fatture,
scarica-tutti, stats, tutti-verbali, verbale/{numero_verbale}, verbali,
verbali-attesa-fattura, verbali-privati, verifica-nuove-fatture — codice
conservato nella cronologia git.
"""
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Body
from typing import Dict, Any
import base64
import hashlib
from datetime import datetime, timezone
from decimal import Decimal

from app.database import Database
from app.utils.error_handler import handle_errors
from app.utils.dependencies import get_current_admin_user
from app.services.verbali_evidence import amount_to_cents

router = APIRouter(prefix="/api/verbali-noleggio", tags=["Verbali Noleggio"])

# Collection
COLLECTION_VERBALI = "verbali_noleggio"


async def _find_verbale(db, numero_verbale: str):
    query = {"$or": [
        {"numero_verbale": numero_verbale}, {"numero_verbale_old": numero_verbale},
        {"numero_verbale": numero_verbale.upper()}, {"numero_verbale_old": numero_verbale.upper()},
    ]}
    for collection in ("verbali_noleggio", "verbali_noleggio_completi"):
        item = await db[collection].find_one(query, {"_id": 0})
        if item:
            return collection, item
    return None, None


@router.post("/documenti-drive/collega")
@handle_errors
async def collega_documenti_drive_dal_foglio(
    file: UploadFile = File(...),
    dry_run: bool = True,
    admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Registra sui verbali i file Drive indicati dal foglio «Collegamenti» (xlsx).

    Non scarica né sposta niente: il dettaglio del verbale apre ogni file per id Drive con
    l'endpoint unico degli originali. `dry_run` per difetto: mostra cosa si collegherebbe.
    """
    from app.services.verbali_documenti_drive import collega_documenti_drive, righe_da_xlsx

    contenuto = await file.read()
    if not contenuto:
        raise HTTPException(status_code=400, detail="File vuoto")
    try:
        righe = righe_da_xlsx(contenuto)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Foglio non leggibile: {type(exc).__name__}: {exc}") from exc
    return await collega_documenti_drive(
        Database.get_db(), righe, dry_run=dry_run, autore=admin.get("email") or admin.get("user_id"))


@router.post("/notifiche-pec/aggancia")
@handle_errors
async def aggancia_notifiche_pec_ai_verbali(
    dry_run: bool = True,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Aggancia le PEC di notifica in archivio al verbale con lo stesso numero.

    `dry_run` per difetto: mostra cosa si aggancerebbe e cosa resta «da agganciare».
    """
    from app.services.notifiche_pec_verbali import aggancia_notifiche_pec

    return await aggancia_notifiche_pec(Database.get_db(), dry_run=dry_run)


@router.post("/ricostruisci-da-pdf")
@handle_errors
async def ricostruisci_verbali_dal_pdf(
    dry_run: bool = True,
    crea_da_pec: bool = False,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Ricostruzione una tantum dei verbali dal loro PDF, in sottofondo.

    `dry_run` per difetto: conta e mostra esempi (senza dati personali), non scrive.
    `crea_da_pec` (solo con `dry_run=false`) apre dalla pipeline i verbali che hanno
    solo la copia conforme della PEC. Esito in `GET …/ricostruisci-da-pdf/stato`.
    """
    from app.services import verbali_ricostruzione

    return await verbali_ricostruzione.avvia(Database.get_db(), dry_run=dry_run, crea_da_pec=crea_da_pec)


@router.get("/ricostruisci-da-pdf/stato")
@handle_errors
async def stato_ricostruzione_verbali(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    from app.services import verbali_ricostruzione

    return await verbali_ricostruzione.stato(Database.get_db())


@router.post("/associa-pdf/{numero_verbale:path}")
@handle_errors
async def associa_pdf_verbale(
    numero_verbale: str,
    file: UploadFile = File(...),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Conserva e collega un PDF originale al verbale, con hash e provenienza."""
    from app.utils.upload_validation import verifica_pdf_reale
    from app.services.verbali_document_import import process_verbale_document, _extract_text, _extract_numero

    db = Database.get_db()
    collection, verbale = await _find_verbale(db, numero_verbale)
    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")
    content = await file.read()
    filename = file.filename or f"verbale_{numero_verbale}.pdf"
    verifica_pdf_reale(content, filename)
    extracted_number = _extract_numero(f"{filename}\n{_extract_text(content)}")
    accepted = {str(verbale.get("numero_verbale") or "").upper(), str(verbale.get("numero_verbale_old") or "").upper()}
    if extracted_number and extracted_number.upper() not in accepted:
        raise HTTPException(status_code=409, detail=f"Il PDF indica il verbale {extracted_number}, non {numero_verbale}")
    digest = hashlib.sha256(content).hexdigest()
    existing = await db["documents_inbox"].find_one({"file_hash": digest}, {"_id": 0, "id": 1})
    doc_id = (existing or {}).get("id") or f"verbale_pdf_{digest[:24]}"
    now = datetime.now(timezone.utc).isoformat()
    if not existing:
        await db["documents_inbox"].insert_one({
            "id": doc_id, "filename": filename, "pdf_data": base64.b64encode(content).decode("ascii"),
            "file_hash": digest, "sha256": digest, "size": len(content), "category": "verbale_codice_strada",
            "tipo_documento": "verbale", "evidence_role": "obbligazione", "source": "upload_dettaglio_verbale",
            "numero_verbale": verbale.get("numero_verbale"), "verbale_id": verbale.get("id"),
            "created_at": now, "updated_at": now, "processed": False, "status": "da_elaborare",
        })
    await db[collection].update_one(
        {"id": verbale.get("id")} if verbale.get("id") else {"numero_verbale": verbale.get("numero_verbale")},
        {"$addToSet": {"document_ids": doc_id}, "$set": {"updated_at": now}},
    )
    outcome = await process_verbale_document(db, document_id=doc_id, content=content,
        filename=filename, source="upload_dettaglio_verbale",
        parsed_metadata={"numero_verbale": verbale.get("numero_verbale")})
    return {"success": True, "duplicate": bool(existing), "document_id": doc_id, "elaborazione": outcome}


@router.post("/ricalcola-pdf/{numero_verbale:path}")
@handle_errors
async def ricalcola_verbale_da_pdf(
    numero_verbale: str,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Rilegge i PDF gia collegati e corregge soltanto conflitti documentali certi."""
    from app.services.verbali_pdf_service import collect_verbale_pdfs
    from app.services.verbali_document_import import process_verbale_document
    db = Database.get_db()
    _collection, verbale = await _find_verbale(db, numero_verbale)
    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")
    pdfs = await collect_verbale_pdfs(db, verbale, include_content=True)
    results = []
    for index, pdf in enumerate(pdfs):
        encoded = pdf.get("content_base64")
        if not encoded or pdf.get("tipo") == "quietanza":
            continue
        content = base64.b64decode(encoded)
        doc_id = pdf.get("document_id") or verbale.get("source_document_id") or f"ricalcolo_{hashlib.sha256(content).hexdigest()[:24]}"
        results.append(await process_verbale_document(db, document_id=doc_id, content=content,
            filename=pdf.get("filename") or f"verbale_{index + 1}.pdf", source="ricalcolo_pdf_collegato",
            parsed_metadata={"numero_verbale": verbale.get("numero_verbale")}))
    refreshed = await db["verbali_noleggio"].find_one({"numero_verbale": verbale.get("numero_verbale")}, {"_id": 0}) or verbale
    return {"success": True, "pdf_elaborati": len(results), "importo": refreshed.get("importo"), "risultati": results}


@router.post("/correggi-importo/{numero_verbale:path}")
@handle_errors
async def correggi_importo_verbale(
    numero_verbale: str,
    data: Dict[str, Any] = Body(...),
    admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Corregge l'importo con audit esplicito quando la scansione non e' leggibile."""
    db = Database.get_db()
    collection, verbale = await _find_verbale(db, numero_verbale)
    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")
    amount_cents = amount_to_cents(data.get("importo"))
    if amount_cents is None:
        raise HTTPException(status_code=400, detail="Importo non valido")
    if amount_cents <= 0 or amount_cents > 100000 * 100:
        raise HTTPException(status_code=400, detail="Importo fuori intervallo")
    amount = float(Decimal(amount_cents) / Decimal(100))
    now = datetime.now(timezone.utc).isoformat()
    previous = verbale.get("importo")
    update = {"importo": amount, "importo_centesimi": amount_cents, "importo_fonte": "correzione_manuale_da_pdf",
              # La correzione di un admin, con audit, e' una conferma: senza questi due campi
              # `describe_verbale_amount` resta «da verificare» e il pagamento (ricevuta pagoPA,
              # bonifico) non si riconcilia mai al verbale.
              "importo_verificato": True, "importo_stato": "CONFERMATO_OPERATORE",
              "importo_precedente": previous, "importo_corretto_at": now,
              "importo_corretto_da": admin.get("email") or admin.get("user_id"), "updated_at": now}
    query = {"id": verbale.get("id")} if verbale.get("id") else {"numero_verbale": verbale.get("numero_verbale")}
    await db[collection].update_one(query, {"$set": update})
    await db["audit_log"].insert_one({
        "id": f"verbale_importo_{hashlib.sha256(f'{numero_verbale}:{now}'.encode()).hexdigest()[:24]}",
        "modulo": "verbali_noleggio", "azione": "correzione_importo_da_pdf",
        "entita_id": verbale.get("id") or verbale.get("numero_verbale"),
        "numero_verbale": verbale.get("numero_verbale"), "valore_precedente": previous,
        "valore_nuovo": amount, "fonte": data.get("fonte") or "verifica_pdf_operatore",
        "utente": admin.get("email") or admin.get("user_id"), "created_at": now,
    })
    return {"success": True, "numero_verbale": verbale.get("numero_verbale"),
            "importo_precedente": previous, "importo": amount, "fonte": update["importo_fonte"]}


@router.post("/correggi-trasgressore/{numero_verbale:path}")
@handle_errors
async def correggi_trasgressore_verbale(
    numero_verbale: str,
    data: Dict[str, Any] = Body(...),
    admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Registra il trasgressore verificato senza confonderlo con il driver."""
    db = Database.get_db()
    collection, verbale = await _find_verbale(db, numero_verbale)
    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")
    trasgressore = " ".join(str(data.get("trasgressore") or "").split()).strip()
    if len(trasgressore) < 3 or len(trasgressore) > 200:
        raise HTTPException(status_code=400, detail="Trasgressore non valido")
    now = datetime.now(timezone.utc).isoformat()
    previous = verbale.get("trasgressore")
    query = {"id": verbale.get("id")} if verbale.get("id") else {"numero_verbale": verbale.get("numero_verbale")}
    await db[collection].update_one(query, {"$set": {
        "trasgressore": trasgressore, "trasgressore_verificato": True,
        "trasgressore_fonte": data.get("fonte") or "verifica_documento_operatore",
        "trasgressore_verificato_at": now, "updated_at": now,
    }})
    await db["audit_log"].insert_one({
        "id": f"verbale_trasgressore_{hashlib.sha256(f'{numero_verbale}:{now}'.encode()).hexdigest()[:24]}",
        "modulo": "verbali_noleggio", "azione": "correzione_trasgressore",
        "entita_id": verbale.get("id") or verbale.get("numero_verbale"),
        "numero_verbale": verbale.get("numero_verbale"),
        "valore_precedente": previous, "valore_nuovo": trasgressore,
        "utente": admin.get("email") or admin.get("user_id"), "created_at": now,
    })
    return {"success": True, "numero_verbale": verbale.get("numero_verbale"),
            "trasgressore": trasgressore, "trasgressore_precedente": previous}


@router.get("/verbali-completi")
@handle_errors
async def get_verbali_completi(
    anno: int = None,
    targa: str = None,
    stato_pagamento: str = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Restituisce i verbali con tutte le associazioni.

    Filtri opzionali:
    - anno: Anno del verbale
    - targa: Filtra per targa veicolo
    - stato_pagamento: da_verificare, pagato, sospeso
    """
    # ATTENZIONE: import locale con nome diverso dalla costante di modulo
    # COLLECTION_VERBALI (riga 23, = "verbali_noleggio") — questo endpoint
    # legge invece "verbali_noleggio_completi" (alimentata dalle fatture,
    # vedi app/services/verbali_service.py). Rinominato per non shadoware
    # in modo fuorviante lo stesso identificatore con due valori diversi
    # (piano residuo op.15, indagine 14/07/2026 — nessun cambio di
    # comportamento, solo leggibilità).
    from app.services.verbali_service import COLLECTION_VERBALI as COLLECTION_VERBALI_COMPLETI
    db = Database.get_db()

    query = {}
    if anno:
        query["anno"] = str(anno)
    if targa:
        query["targa"] = targa.upper()
    if stato_pagamento:
        query["stato_pagamento"] = stato_pagamento

    cursor = db[COLLECTION_VERBALI_COMPLETI].find(query, {"_id": 0}).sort("data_fattura", -1).limit(limit)
    verbali = await cursor.to_list(limit)

    # Statistiche
    totale = await db[COLLECTION_VERBALI_COMPLETI].count_documents(query if query else {})
    pagati = await db[COLLECTION_VERBALI_COMPLETI].count_documents({"stato_pagamento": "pagato"})
    sospesi = await db[COLLECTION_VERBALI_COMPLETI].count_documents({"stato_pagamento": "sospeso"})
    da_verificare = await db[COLLECTION_VERBALI_COMPLETI].count_documents({"stato_pagamento": "da_verificare"})

    return {
        "verbali": verbali,
        "count": len(verbali),
        "totale": totale,
        "statistiche": {
            "pagati": pagati,
            "sospesi": sospesi,
            "da_verificare": da_verificare
        }
    }


# Endpoint canonico unico: il converter :path gestisce anche numeri verbale
# contenenti slash (es. "S/2259"), senza una seconda route shadowata.
@router.get("/dettaglio/{numero_verbale:path}")
@handle_errors
async def get_dettaglio_verbale(numero_verbale: str) -> Dict[str, Any]:
    """
    Restituisce il dettaglio completo di un verbale con tutti i documenti associati.
    """
    # Vedi nota in get_verbali_completi sopra: nome rinominato per non
    # shadoware COLLECTION_VERBALI di modulo con un valore diverso.
    from app.services.verbali_service import COLLECTION_VERBALI as COLLECTION_VERBALI_COMPLETI
    db = Database.get_db()

    # Cerca nel nuovo sistema (incluso vecchio numero)
    verbale = await db[COLLECTION_VERBALI_COMPLETI].find_one(
        {"$or": [
            {"numero_verbale": numero_verbale},
            {"numero_verbale_old": numero_verbale},
            {"numero_verbale": numero_verbale.upper()},
            {"numero_verbale_old": numero_verbale.upper()},
            {"id": numero_verbale},
        ]},
        {"_id": 0}
    )

    if not verbale:
        # Cerca nel vecchio sistema
        verbale = await db["verbali_noleggio"].find_one(
            {"$or": [
                {"numero_verbale": numero_verbale},
                {"numero_verbale_old": numero_verbale},
                {"id": numero_verbale},
            ]},
            {"_id": 0}
        )

    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")

    # Carica info aggiuntive
    risultato = {**verbale}

    # Driver: preserva l'arricchimento che prima viveva soltanto
    # nella route duplicata dedicata ai numeri con slash.
    if verbale.get("driver_id"):
        driver = await db["dipendenti"].find_one(
            {"id": verbale["driver_id"]}, {"_id": 0}
        )
        if driver:
            risultato["driver_dettaglio"] = {
                "nome": driver.get("nome"),
                "cognome": driver.get("cognome"),
                "codice_fiscale": driver.get("codice_fiscale"),
            }

    # Carica info veicolo se presente
    if verbale.get("targa"):
        veicolo = await db["veicoli_noleggio"].find_one(
            {"targa": verbale["targa"]},
            {"_id": 0}
        )
        risultato["veicolo_info"] = veicolo

    # Carica fattura se presente
    if verbale.get("fattura_id"):
        fattura = await db["invoices"].find_one(
            {"id": verbale["fattura_id"]},
            {"_id": 0, "linee": 0}  # Escludi linee per non appesantire
        )
        risultato["fattura_info"] = fattura

    # Carica il movimento bancario dalla sorgente canonica usata dal motore di
    # riconciliazione. Il vecchio archivio prima_nota_banca resta un fallback
    # di sola lettura per i record storici.
    if verbale.get("movimento_banca_id"):
        movimento_id = verbale["movimento_banca_id"]
        movimento = await db["estratto_conto_movimenti"].find_one(
            {"$or": [{"id": movimento_id}, {"_id": movimento_id}]},
            {"_id": 0}
        )
        if not movimento:
            movimento = await db["prima_nota_banca"].find_one(
                {"id": movimento_id}, {"_id": 0}
            )
        risultato["movimento_info"] = movimento

    from app.services.verbali_pdf_service import collect_verbale_pdfs, pdf_metadata
    documenti = pdf_metadata(await collect_verbale_pdfs(
        db, verbale, include_content=False
    ))
    risultato["pdf_disponibili"] = documenti

    def _testo_ruolo(documento) -> str:
        # Il ruolo di un file lo dicono il suo tipo e il suo nome: l'origine («source») puo' contenere
        # «verbale» per un file che e' una ricevuta, e farebbe finire lo stesso PDF in due caselle.
        return " ".join(str(documento.get(campo) or "") for campo in ("tipo", "filename")).casefold()

    _TERMINI_QUIETANZA = ("quietanz", "ricevut", "partenopay", "pagopa", "attestazione", "pagamento")
    # Ogni file ha UN solo ruolo: prima quietanza, poi notifica, il resto e' il verbale.
    documento_quietanza = next((d for d in documenti if any(t in _testo_ruolo(d) for t in _TERMINI_QUIETANZA)), None)
    documento_notifica = next((d for d in documenti if d is not documento_quietanza and "notific" in _testo_ruolo(d)), None)
    restanti = [d for d in documenti if d is not documento_quietanza and d is not documento_notifica
                and not any(t in _testo_ruolo(d) for t in _TERMINI_QUIETANZA)]
    documento_verbale = next((d for d in restanti if "verbale" in _testo_ruolo(d)), None) or (restanti[0] if restanti else None)

    source_files = [str(path) for path in (verbale.get("source_files") or [])]
    quietanza_archivio = next((path for path in source_files if any(
        token in path.casefold() for token in ("quietanz", "ricevut", "pagamento")
    )), None)
    notifica_archivio = next((path for path in source_files if "notific" in path.casefold()), None)

    # Documenti Drive collegati dal foglio dei collegamenti: ognuno nella casella del suo tipo (letto dal contenuto).
    def _drive(*tipi: str):
        return [d for d in (verbale.get("documenti_drive") or []) if isinstance(d, dict) and d.get("tipo") in tipi]

    drive_verbale, drive_notifica, drive_quietanza = _drive("verbale"), _drive("notifica"), _drive("quietanza", "ricevuta")

    risultato["fascicolo"] = {
        "verbale": {
            "presente": bool(documento_verbale or drive_verbale),
            "documento": documento_verbale,
            "documenti_drive": drive_verbale,
        },
        "notifica": {
            "presente": bool(documento_notifica or drive_notifica or notifica_archivio or verbale.get("data_ricezione_notifica")),
            "data": verbale.get("data_ricezione_notifica") or verbale.get("data_notifica"),
            "documento": documento_notifica,
            "documenti_drive": drive_notifica,
            "riferimento_archivio": notifica_archivio,
        },
        "pagamento_banca": {
            "presente": bool(risultato.get("movimento_info")),
            "verificato": bool(verbale.get("banca_verificata")),
            "movimento": risultato.get("movimento_info"),
        },
        "quietanza": {
            "presente": bool(documento_quietanza or drive_quietanza or quietanza_archivio or verbale.get("quietanza_ricevuta")),
            "fonte": verbale.get("psp") or verbale.get("fonte_pagamento"),
            "documento": documento_quietanza,
            "documenti_drive": drive_quietanza,
            "riferimento_archivio": quietanza_archivio,
            "pagamento_documentale_verificato": bool(verbale.get("pagato_documentalmente")),
        },
    }

    # Non inviare dati binari pesanti nel response JSON
    risultato.pop("pdf_data", None)
    risultato.pop("quietanza_pdf", None)

    return risultato


# NB: l'endpoint POST /unifica-verbali che era qui è stato rimosso: il corpo
# del loop era vuoto (endpoint tronco che rispondeva sempre null senza fare
# nulla — bug #16 audit memoria/endpoints/README.md), zero chiamanti.
