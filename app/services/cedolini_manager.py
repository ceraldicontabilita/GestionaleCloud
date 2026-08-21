"""
Servizio Gestione Completa Cedolini e Dipendenti
================================================

Flusso automatico quando si carica un cedolino PDF:
1. Parsing del PDF (multi-formato)
2. Verifica anagrafica dipendente → Se non esiste, CREA automaticamente
3. Salva cedolino in riepilogo_cedolini
4. Crea movimento in prima_nota_salari
5. Tenta riconciliazione automatica con estratto conto

Questo processo avviene automaticamente:
- Download da posta elettronica (ogni 10 minuti)
- Upload da Import/Export Manager
"""
import base64
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Per scelta operativa del 03/08/2026 lo storico autorizzato parte dal 2018.
# La guardia evita che un file piu' vecchio, caricato per errore, entri nei
# registri o generi prima nota/partite aperte.
PAYROLL_MIN_YEAR = 2018


def _chiave_documentale_cedolino(cedolino_data: Dict[str, Any], pdf_data: str = None) -> str:
    """Identifica il PDF, non soltanto dipendente e mese."""
    from app.services.cedolini_canonico import chiave_cedolino

    content_hash = ""
    if pdf_data:
        try:
            content_hash = hashlib.md5(base64.b64decode(pdf_data)).hexdigest()
        except Exception:
            content_hash = ""
    identity = dict(cedolino_data)
    if content_hash:
        identity["file_hash"] = content_hash
    return chiave_cedolino(identity)


async def processa_cedolino_completo(
    db,
    cedolino_data: Dict[str, Any],
    filename: str,
    pdf_data: str = None
) -> Dict[str, Any]:
    """
    Processa un singolo cedolino con flusso completo:
    1. Anagrafica dipendente (crea se non esiste)
    2. Riepilogo cedolini
    3. Prima nota salari
    4. Riconciliazione automatica

    Args:
        db: Registro Sheets
        cedolino_data: Dati estratti dal parser
        filename: Nome file PDF
        pdf_data: Contenuto PDF in Base64 (architettura Drive/Sheets)

    Returns:
        Risultato del processamento
    """
    result = {
        "success": False,
        "anagrafica_creata": False,
        "anagrafica_aggiornata": False,
        "cedolino_salvato": False,
        "prima_nota_creata": False,
        "riconciliato": False,
        "dipendente_id": None,
        "errore": None
    }

    try:
        cf = cedolino_data.get("codice_fiscale", "").upper()
        nome = cedolino_data.get("nome_dipendente", "")
        mese = cedolino_data.get("mese")
        anno = cedolino_data.get("anno")
        netto = cedolino_data.get("netto_mese", 0)
        cedolino_dedup_key = _chiave_documentale_cedolino(cedolino_data, pdf_data)

        if not cf or not mese or not anno:
            result["errore"] = "Dati mancanti (CF, mese o anno)"
            return result

        if netto == 0:
            result["errore"] = "Netto = 0, probabilmente foglio presenze"
            return result

        # ============================================
        # 1. ANAGRAFICA DIPENDENTE
        # ============================================
        dipendente = await db["dipendenti"].find_one(
            {"codice_fiscale": cf}
        )

        if dipendente:
            # Aggiorna dati esistenti se necessario
            dipendente_id = dipendente.get("id")

            update_data = {
                "ultimo_cedolino": f"{mese:02d}/{anno}",
                "ultimo_netto": netto,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

            # Aggiorna IBAN se presente e diverso
            iban = cedolino_data.get("iban")
            if iban and iban != dipendente.get("iban"):
                update_data["iban"] = iban

            await db["dipendenti"].update_one(
                {"codice_fiscale": cf},
                {"$set": update_data}
            )
            result["anagrafica_aggiornata"] = True

        else:
            # CREA NUOVA ANAGRAFICA
            dipendente_id = str(uuid.uuid4())

            # Estrai cognome e nome
            parti_nome = nome.split() if nome else []
            cognome = parti_nome[0] if parti_nome else ""
            nome_proprio = " ".join(parti_nome[1:]) if len(parti_nome) > 1 else ""

            nuova_anagrafica = {
                "id": dipendente_id,
                "codice_fiscale": cf,
                "cognome": cognome,
                "nome": nome_proprio,
                "nome_completo": nome,
                "iban": cedolino_data.get("iban"),
                "livello": cedolino_data.get("livello"),
                "qualifica": cedolino_data.get("qualifica"),
                "data_assunzione": cedolino_data.get("data_assunzione"),
                "stato": "attivo",
                "primo_cedolino": f"{mese:02d}/{anno}",
                "ultimo_cedolino": f"{mese:02d}/{anno}",
                "ultimo_netto": netto,
                "totale_netto_anno": netto,
                "source": "auto_cedolino",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

            await db["dipendenti"].insert_one(dict(nuova_anagrafica).copy())
            result["anagrafica_creata"] = True
            logger.info(f"📋 Nuova anagrafica dipendente creata: {nome} ({cf})")

        result["dipendente_id"] = dipendente_id

        # ============================================
        # 2. RIEPILOGO CEDOLINI
        # ============================================
        cedolino_record = {
            "dipendente_id": dipendente_id,
            "nome_dipendente": nome,
            "codice_fiscale": cf,
            "mese": mese,
            "anno": anno,
            "periodo_competenza": f"{mese:02d}/{anno}",
            "netto_mese": netto,
            "lordo": cedolino_data.get("lordo", 0),
            "totale_trattenute": cedolino_data.get("totale_trattenute", 0),
            "detrazioni_fiscali": cedolino_data.get("detrazioni_fiscali", 0),
            "tfr_quota": cedolino_data.get("tfr_quota", 0),
            "ore_lavorate": cedolino_data.get("ore_lavorate", 0),
            "iban": cedolino_data.get("iban"),
            "filename": filename,
            "pdf_data": pdf_data,  # Architettura Drive/Sheets
            "formato": cedolino_data.get("formato_rilevato"),
            "tipo_cedolino": cedolino_data.get("tipo_cedolino", "mensile"),
            "cedolino_dedup_key": cedolino_dedup_key,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        riepilogo_esistente = await db["riepilogo_cedolini"].find_one({
            "$or": [
                {"cedolino_dedup_key": cedolino_dedup_key},
                {
                    "cedolino_dedup_key": {"$exists": False},
                    "codice_fiscale": cf, "mese": mese, "anno": anno,
                    "filename": filename, "netto_mese": netto,
                    "lordo": cedolino_data.get("lordo", 0),
                },
            ]
        })
        if riepilogo_esistente:
            filtro_riepilogo = (
                {"_id": riepilogo_esistente["_id"]}
                if riepilogo_esistente.get("_id") is not None
                else {"cedolino_dedup_key": riepilogo_esistente.get("cedolino_dedup_key")}
            )
            await db["riepilogo_cedolini"].update_one(
                filtro_riepilogo, {"$set": cedolino_record}
            )
        else:
            await db["riepilogo_cedolini"].insert_one(dict(cedolino_record))
        result["cedolino_salvato"] = True

        # ============================================
        # 3. PRIMA NOTA SALARI
        # ============================================
        # Controlla se esiste già
        from app.services.salari_periodo import periodo_ammesso_in_prima_nota
        periodo_contabile = periodo_ammesso_in_prima_nota(anno, mese)
        existing_pn = None
        if periodo_contabile:
            existing_pn = await db["prima_nota_salari"].find_one({
                "$or": [
                    {"cedolino_dedup_key": cedolino_dedup_key},
                    {
                        "cedolino_dedup_key": {"$exists": False},
                        "dipendente_id": dipendente_id, "mese": mese, "anno": anno,
                        "importo": netto,
                    },
                    {
                        "cedolino_dedup_key": {"$exists": False},
                        "dipendente_id": dipendente_id, "mese": mese, "anno": anno,
                        "importo_busta": netto,
                    },
                ]
            })
        else:
            # Il PDF e il riepilogo storico restano conservati, ma il cedolino
            # non deve generare una scrittura nella contabilita' operativa.
            existing_pn = {"id": None, "cedolino_dedup_key": cedolino_dedup_key}
            result["prima_nota_fuori_periodo"] = True

        # movimento_id garantito in entrambi i rami (if existing_pn / if not)
        # Necessario per publish evento sotto
        movimento_id = None
        if existing_pn:
            movimento_id = existing_pn.get("id")
            if not existing_pn.get("cedolino_dedup_key"):
                await db["prima_nota_salari"].update_one(
                    {"id": movimento_id},
                    {"$set": {"cedolino_dedup_key": cedolino_dedup_key}},
                )

        if not existing_pn:
            movimento_id = str(uuid.uuid4())

            # Data movimento = ultimo giorno del mese
            import calendar
            ultimo_giorno = calendar.monthrange(anno, mese)[1]
            data_movimento = f"{anno}-{mese:02d}-{ultimo_giorno:02d}"

            movimento_pn = {
                "id": movimento_id,
                "dipendente_id": dipendente_id,
                "dipendente_nome": nome,
                "codice_fiscale": cf,
                "data": data_movimento,
                "mese": mese,
                "anno": anno,
                "importo": netto,
                "tipo": "stipendio",
                "descrizione": f"Stipendio {nome} - {mese:02d}/{anno}",
                "iban_pagamento": cedolino_data.get("iban"),
                "riconciliato": False,
                "bonifico_id": None,
                "estratto_conto_id": None,
                "cedolino_dedup_key": cedolino_dedup_key,
                "source": "cedolino_auto",
                "created_at": datetime.now(timezone.utc).isoformat()
            }

            await db["prima_nota_salari"].insert_one(dict(movimento_pn).copy())
            result["prima_nota_creata"] = True

            # ============================================
            # 4. RICONCILIAZIONE AUTOMATICA
            # ============================================
            # Cerca nel estratto conto un bonifico con importo simile
            # nello stesso periodo

            riconciliato = await riconcilia_stipendio_automatico(
                db,
                dipendente_nome=nome,
                importo=netto,
                mese=mese,
                anno=anno,
                movimento_id=movimento_id,
                iban=cedolino_data.get("iban")
            )

            result["riconciliato"] = riconciliato

        result["success"] = True

        # ── EVENT BUS UNICO: partita aperta, alert, prima nota salari, TFR,
        # notifica WS. Prima qui c'era un doppio publish su due bus separati
        # (bus core per prima_nota/TFR/notifiche + bus relazionale per partita/
        # alert): ora tutti gli handler vivono sull'unico bus e questo è
        # l'unico punto di pubblicazione.
        try:
            from app.services.event_bus import propagate_event, EventTypes
            await propagate_event(EventTypes.CEDOLINO_IMPORTATO, {
                "cedolino_id": movimento_id,
                "dipendente_id": dipendente_id,
                "dipendente_nome": nome,
                "codice_fiscale": cf,
                "netto": netto,
                "lordo": cedolino_data.get("lordo", 0),
                "tfr_quota_mese": cedolino_data.get("tfr_quota_mese", 0),
                "mese": mese,
                "anno": anno,
                "tipo_cedolino": cedolino_data.get("tipo_cedolino", "mensile"),
                "cedolino_dedup_key": cedolino_dedup_key,
            }, db, source_module="cedolini_manager_v1")
        except Exception:
            logger.exception("Errore propagazione cedolino.importato (canale D V1)")

        # --- AUTO-CESSAZIONE DA CEDOLINO (canale D V1 fallback) ---
        # Stessa logica della V2 ma senza pdf_text: si affida solo ai campi
        # 'cessato'/'cessazione_diciture' se già popolati dal parser upstream.
        if cedolino_data.get("cessato") and dipendente_id:
            try:
                data_cess = cedolino_data.get("data_cessazione_rilevata")
                if not data_cess:
                    import calendar as _cal
                    ug = _cal.monthrange(anno, mese)[1]
                    data_cess = f"{anno:04d}-{mese:02d}-{ug:02d}"

                dip_now = await db["dipendenti"].find_one(
                    {"id": dipendente_id},
                    {"_id": 0, "attivo": 1, "in_carico": 1, "data_cessazione": 1}
                )
                gia_cessato = dip_now and (
                    dip_now.get("attivo") is False
                    or dip_now.get("in_carico") is False
                    or dip_now.get("data_cessazione")
                )

                if not gia_cessato:
                    await db["dipendenti"].update_one(
                        {"id": dipendente_id},
                        {"$set": {
                            "attivo": False,
                            "in_carico": False,
                            "data_cessazione": data_cess,
                            "cessato_automaticamente": True,
                            "cessazione_source": "cedolino_auto_v1",
                            "cessazione_diciture": cedolino_data.get("cessazione_diciture", []),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }}
                    )
                    logger.info(
                        f"[Canale D V1] Dipendente {nome} ({dipendente_id}) AUTO-CESSATO"
                    )
                    from app.services.event_bus import propagate_event as _pe, EventTypes as _et
                    await _pe(_et.DIPENDENTE_CESSATO, {
                        "dipendente_id": dipendente_id,
                        "nome_completo": nome,
                        "codice_fiscale": cf,
                        "data_cessazione": data_cess,
                        "auto_from_cedolino": True,
                        "cessazione_diciture": cedolino_data.get("cessazione_diciture", []),
                    }, db, source_module="cedolini_manager_v1")
                    result["cessato_auto"] = True
            except Exception:
                logger.exception(f"Errore auto-cessazione V1 per dip {dipendente_id}")

    except Exception as e:
        logger.error(f"Errore processamento cedolino: {e}")
        result["errore"] = str(e)

    return result


async def riconcilia_stipendio_automatico(
    db,
    dipendente_nome: str,
    importo: float,
    mese: int,
    anno: int,
    movimento_id: str,
    iban: str = None
) -> bool:
    """Usa il motore canonico: nome completo, centesimo e periodo.

    I parametri sono mantenuti per compatibilita' con i parser esistenti; la
    riga ``movimento_id`` appena creata e' la fonte canonica dei dati.
    """
    try:
        if not movimento_id:
            return False
        from app.services.stipendi_bonifici import associa_bonifici_stipendi
        result = await associa_bonifici_stipendi(db, stipendio_id=movimento_id)
        return bool(result.get("bonifici_associati"))
    except Exception as e:
        logger.error(f"Errore riconciliazione automatica: {e}")
        return False


def _summary_cedolino(
    summary: Dict[str, Any],
    raw_text: str,
    *,
    pdf_bytes: bytes,
    page_start: int,
    page_end: int,
    document_pages: int,
) -> Dict[str, Any]:
    """Converte un riepilogo deterministico conservando provenienza e PDF."""
    import base64

    return {
        "nome_dipendente": summary.get("dipendente_nome") or "",
        "codice_fiscale": summary.get("codice_fiscale") or "",
        "tipo_cedolino": summary.get("tipo_cedolino") or "mensile",
        "mese": summary.get("mese"),
        "anno": summary.get("anno"),
        "lordo": summary.get("lordo") or 0,
        "netto": summary.get("netto") or 0,
        "netto_mese": summary.get("netto") or 0,
        "totale_trattenute": summary.get("trattenute") or 0,
        "tfr_quota": summary.get("tfr_quota") or 0,
        "ore_lavorate": summary.get("ore_lavorate") or 0,
        "formato_rilevato": summary.get("template") or "multi_template",
        "ferie_permessi": {
            "ferie_residuo": summary.get("ferie_residuo") or 0,
            "ferie_godute": summary.get("ferie_godute") or 0,
            "permessi_residuo": summary.get("permessi_residuo") or 0,
            "permessi_goduti": summary.get("permessi_goduti") or 0,
        },
        "cessato": summary.get("cessato", False),
        "cessazione_diciture": summary.get("cessazione_diciture", []),
        "data_cessazione_rilevata": summary.get("data_cessazione_rilevata"),
        "source_page_start": page_start,
        "source_page_end": page_end,
        "source_document_pages": document_pages,
        "_raw_text": raw_text,
        "_pdf_data": base64.b64encode(pdf_bytes).decode("ascii"),
    }


def _summary_complete(parsed: Dict[str, Any], summary: Dict[str, Any]) -> bool:
    return bool(
        parsed.get("parse_success")
        and parsed.get("tipo_documento") != "foglio_presenze"
        and summary.get("codice_fiscale")
        and summary.get("mese")
        and summary.get("anno")
        and summary.get("netto")
    )


def _parse_multi_template_units(file_content: bytes) -> List[Dict[str, Any]]:
    """Separa un fascicolo multipagina per dipendente e periodo.

    Le pagine di continuazione restano aggregate al cedolino precedente. Se il
    fascicolo contiene un solo dipendente, viene conservato integralmente.
    """
    import fitz
    from app.parsers.busta_paga_multi_template import (
        extract_summary,
        parse_busta_paga_from_bytes,
    )

    document = fitz.open(stream=file_content, filetype="pdf")
    try:
        page_count = len(document)
        raw_pages = [page.get_text() for page in document]

        def page_bytes(start: int, end: int) -> bytes:
            output = fitz.open()
            try:
                output.insert_pdf(document, from_page=start, to_page=end)
                return output.tobytes(garbage=3, deflate=True)
            finally:
                output.close()

        if page_count <= 1:
            parsed = parse_busta_paga_from_bytes(file_content)
            summary = extract_summary(parsed)
            if not _summary_complete(parsed, summary):
                return []
            return [_summary_cedolino(
                summary, "\n".join(raw_pages), pdf_bytes=file_content,
                page_start=1, page_end=page_count, document_pages=page_count,
            )]

        candidates: List[Optional[Tuple[Tuple[str, int, int, str], Dict[str, Any]]]] = []
        for index in range(page_count):
            single = page_bytes(index, index)
            parsed = parse_busta_paga_from_bytes(single)
            summary = extract_summary(parsed)
            if _summary_complete(parsed, summary):
                key = (
                    str(summary.get("codice_fiscale") or "").upper(),
                    int(summary["mese"]),
                    int(summary["anno"]),
                    str(summary.get("tipo_cedolino") or "mensile").lower(),
                )
                candidates.append((key, summary))
            else:
                candidates.append(None)

        distinct_keys = {candidate[0] for candidate in candidates if candidate}
        if len(distinct_keys) <= 1:
            parsed = parse_busta_paga_from_bytes(file_content)
            summary = extract_summary(parsed)
            if not _summary_complete(parsed, summary):
                return []
            return [_summary_cedolino(
                summary, "\n".join(raw_pages), pdf_bytes=file_content,
                page_start=1, page_end=page_count, document_pages=page_count,
            )]

        starts: List[Tuple[int, Tuple[str, int, int, str], Dict[str, Any]]] = []
        current_key: Optional[Tuple[str, int, int, str]] = None
        for index, candidate in enumerate(candidates):
            if not candidate:
                continue
            key, summary = candidate
            if key != current_key:
                starts.append((index, key, summary))
                current_key = key

        units: List[Dict[str, Any]] = []
        seen_keys = set()
        for position, (start, expected_key, page_summary) in enumerate(starts):
            if expected_key in seen_keys:
                continue
            seen_keys.add(expected_key)
            end = starts[position + 1][0] - 1 if position + 1 < len(starts) else page_count - 1
            if position == 0:
                start = 0
            chunk = page_bytes(start, end)
            parsed = parse_busta_paga_from_bytes(chunk)
            summary = extract_summary(parsed)
            if not _summary_complete(parsed, summary):
                summary = page_summary
            units.append(_summary_cedolino(
                summary,
                "\n".join(raw_pages[start:end + 1]),
                pdf_bytes=chunk,
                page_start=start + 1,
                page_end=end + 1,
                document_pages=page_count,
            ))
        return units
    finally:
        document.close()


async def processa_tutti_cedolini_pdf(
    db,
    pdf_data: str,
    filename: str,
    source_path: str = "",
    source_container: str = "",
) -> Dict[str, Any]:
    """
    Processa un file PDF di cedolini con flusso completo.
    Gestisce PDF multi-pagina con più dipendenti.

    Architettura Drive/Sheets: accetta pdf_data in Base64.
    Usa come prima scelta il parser deterministico multi-template dei modelli
    aziendali, poi Document AI e infine il parser regex storico.

    Args:
        db: Registro Sheets
        pdf_data: Contenuto PDF in Base64
        filename: Nome del file PDF
    """
    import base64

    results = {
        "success": True,
        "cedolini_processati": 0,
        "anagrafiche_create": 0,
        "prima_nota_create": 0,
        "riconciliati": 0,
        "errori": [],
        "metodo": "multi_template"  # Traccia quale metodo è stato usato
    }

    # Decodifica PDF da Base64
    try:
        file_content = base64.b64decode(pdf_data)
    except Exception as e:
        results["success"] = False
        results["errori"].append(f"Errore decodifica Base64: {str(e)}")
        return results

    cedolini = []

    # Estrai testo grezzo del PDF (per detect_cessazione e fallback V2)
    # Estratto una volta sola perché il parsing Document AI non espone il raw text
    raw_text = ""
    try:
        import fitz  # PyMuPDF
        import tempfile
        import os as _os
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        try:
            doc = fitz.open(tmp_path)
            raw_text = "\n".join(page.get_text() for page in doc)
            doc.close()
        finally:
            try:
                _os.unlink(tmp_path)
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"Estrazione pdf_text fallita (non bloccante): {e}")

    # PRIMA SCELTA: parser deterministico multi-template.
    # Supporta i modelli aziendali Zucchetti Aut.299/301, LUL e TeamSystem
    # Aut.92267. Il parser storico per-pagina perdeva TeamSystem e poteva
    # duplicare lo stesso cedolino quando il PDF aveva più pagine.
    try:
        cedolini = _parse_multi_template_units(file_content)
    except Exception as e:
        logger.warning("Parser multi-template fallito per %s: %s", filename, e)

    # SECONDA SCELTA: Document AI per eventuali formati futuri non noti.
    if not cedolini:
        try:
            from app.services.document_ai_extractor import extract_document_data

            ai_result = await extract_document_data(
                file_content=file_content,
                filename=filename,
                document_type="busta_paga"
            )

            if ai_result.get("structured_data", {}).get("success"):
                data = ai_result["structured_data"].get("data", {})
                cedolino = {
                    "nome_dipendente": data.get("dipendente", {}).get("nome_cognome", ""),
                    "codice_fiscale": data.get("dipendente", {}).get("codice_fiscale", ""),
                    "mese": data.get("periodo", {}).get("mese"),
                    "anno": data.get("periodo", {}).get("anno"),
                    "lordo": data.get("retribuzione", {}).get("lordo"),
                    "netto": data.get("retribuzione", {}).get("netto"),
                    "azienda": data.get("azienda", {}).get("denominazione", ""),
                    "raw_data": data
                }
                cedolini = [cedolino]
                results["metodo"] = "document_ai"
        except Exception as e:
            logger.warning("Document AI fallito per %s: %s", filename, e)

    # ULTIMO FALLBACK: parser regex legacy per formati storici non coperti.
    if not cedolini:
        try:
            from app.parsers.payslip_parser_v2 import parse_payslip_pdf
            # Il parser accetta pdf_content bytes
            cedolini = parse_payslip_pdf(pdf_content=file_content)
            results["metodo"] = "regex_fallback"
        except Exception as e:
            results["success"] = False
            results["errori"].append(f"Entrambi i parser falliti: {str(e)}")
            return results

    # Processa i cedolini trovati
    for ced in cedolini:
        try:
            cedolino_anno = int(ced.get("anno") or 0)
        except (TypeError, ValueError):
            cedolino_anno = 0
        if cedolino_anno and cedolino_anno < PAYROLL_MIN_YEAR:
            results["errori"].append(
                f"{filename}: annualita {cedolino_anno} esclusa (storico autorizzato dal {PAYROLL_MIN_YEAR})"
            )
            continue
        ced["source_path"] = source_path or filename
        ced["source_container"] = source_container or None
        cedolino_pdf_data = ced.pop("_pdf_data", pdf_data)
        # pdf_text preferenziale: _raw_text del singolo cedolino (parser_v2 regex),
        # altrimenti il raw_text globale estratto all'inizio (Document AI path)
        ced_pdf_text = ced.get("_raw_text", "") or raw_text

        # Arricchisci cedolino_data con detect_cessazione se non già presente,
        # così anche il fallback V1 ha il flag 'cessato' senza dover riparsare
        if ced_pdf_text and not ced.get("cessato"):
            try:
                from app.parsers.busta_paga_multi_template import detect_cessazione
                _cess = detect_cessazione(ced_pdf_text)
                if _cess.get("cessato"):
                    ced["cessato"] = True
                    ced["cessazione_diciture"] = _cess.get("diciture_trovate", [])
                    ced["data_cessazione_rilevata"] = _cess.get("data_cessazione_rilevata")
            except Exception:
                logger.debug("detect_cessazione arricchimento fallito (non bloccante)")

        # Usa processamento V2 che estrae anche ferie/ROL/contributi
        try:
            from app.services.salari_unificati_v2 import processa_cedolino_v2

            res = await processa_cedolino_v2(
                db=db,
                cedolino_data=ced,
                pdf_text=ced_pdf_text,
                filename=filename,
                pdf_data=cedolino_pdf_data
            )
        except Exception as e:
            logger.warning(f"V2 fallito, uso V1: {e}")
            res = await processa_cedolino_completo(
                db=db,
                cedolino_data=ced,
                filename=filename,
                pdf_data=cedolino_pdf_data
            )

        if res.get("success"):
            results["cedolini_processati"] += 1
            if res.get("anagrafica_creata"):
                results["anagrafiche_create"] += 1
            if res.get("prima_nota_creata"):
                results["prima_nota_create"] += 1
            if res.get("riconciliato"):
                results["riconciliati"] += 1
        else:
            if res.get("errore"):
                results["errori"].append(f"{ced.get('nome_dipendente', 'N/D')}: {res.get('errore')}")

    return results


async def get_anagrafica_dipendenti(db, attivi_solo: bool = True) -> List[Dict[str, Any]]:
    """Restituisce l'elenco dei dipendenti."""
    filtro = {}
    if attivi_solo:
        filtro["stato"] = "attivo"

    dipendenti = await db["dipendenti"].find(
        filtro,
        {"_id": 0}
    ).sort("cognome", 1).to_list(500)

    return dipendenti


async def get_riepilogo_dipendente(db, codice_fiscale: str) -> Dict[str, Any]:
    """Restituisce il riepilogo completo di un dipendente."""

    # Anagrafica
    anagrafica = await db["dipendenti"].find_one(
        {"codice_fiscale": codice_fiscale},
        {"_id": 0}
    )

    if not anagrafica:
        return {"errore": "Dipendente non trovato"}

    # Cedolini
    cedolini = await db["riepilogo_cedolini"].find(
        {"codice_fiscale": codice_fiscale},
        {"_id": 0}
    ).sort([("anno", -1), ("mese", -1)]).to_list(100)

    # Totali
    totale_netto = sum(c.get("netto_mese", 0) for c in cedolini)

    # Prima nota
    prima_nota = await db["prima_nota_salari"].find(
        {"codice_fiscale": codice_fiscale},
        {"_id": 0}
    ).sort([("anno", -1), ("mese", -1)]).to_list(100)

    riconciliati = sum(1 for p in prima_nota if p.get("riconciliato"))

    return {
        "anagrafica": anagrafica,
        "cedolini": cedolini,
        "totale_cedolini": len(cedolini),
        "totale_netto": totale_netto,
        "prima_nota": prima_nota,
        "movimenti_riconciliati": riconciliati,
        "movimenti_da_riconciliare": len(prima_nota) - riconciliati
    }
