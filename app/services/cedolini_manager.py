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
import asyncio
import base64
import logging
from typing import Dict, Any, List, Optional

from app.constants.canale_documento import canale_obbligatorio
from app.services import cedolini_motore as _cedolini_motore

PAYROLL_MIN_YEAR = _cedolini_motore.PAYROLL_MIN_YEAR

logger = logging.getLogger(__name__)


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


async def _scrivi_scheda(db, lettura, contenuto: bytes, filename: str, source_file_hash: str,
                         drive_file_id: str, source_path: str, results: Dict[str, Any]) -> None:
    """Scheda Markdown della lettura (buste, presenze o storico): mai bloccante."""
    import hashlib
    import re

    from app.services.schede_markdown import salva_scheda_cedolino

    if lettura["esito"] not in ("buste", "presenze", "fuori_periodo"):
        return
    sha = (source_file_hash or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        sha = hashlib.sha256(contenuto).hexdigest()
    try:
        scheda = await salva_scheda_cedolino(
            db, lettura, sha256=sha, filename=filename,
            drive_file_id=drive_file_id or "", source_path=source_path or filename,
        )
        results["scheda_markdown"] = scheda["id"]
    except Exception as exc:
        logger.warning("[Cedolini] scheda Markdown di %s non scritta: %s: %s",
                       filename, type(exc).__name__, exc)
        results["errori"].append(f"Scheda Markdown non scritta: {type(exc).__name__}: {exc}")


async def _busta_gia_in_archivio(db, ced: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Un cedolino con lo stesso contenuto (``doppioni_archivio.identita_cedolino``)."""
    from app.services.doppioni_archivio import identita_cedolino

    chiave = identita_cedolino(ced)
    if chiave is None:
        return None
    candidati = await db["cedolini"].find(
        {"codice_fiscale": chiave[0], "anno": chiave[1], "mese": chiave[2]},
        {"_id": 0, "id": 1, "codice_fiscale": 1, "anno": 1, "mese": 1, "tipo_cedolino": 1,
         "netto": 1, "netto_mese": 1, "lordo": 1, "totale_trattenute": 1},
    ).to_list(None)
    return next((c for c in candidati if identita_cedolino(c) == chiave), None)


# Una busta alla volta per dipendente e periodo: lo smistatore legge piu' PDF
# insieme, e due copie della stessa busta non devono superare entrambe il
# controllo «gia' in archivio» prima che la prima sia scritta.
_LOCK_BUSTE: Dict[Any, asyncio.Lock] = {}


def _lock_busta(ced: Dict[str, Any]) -> asyncio.Lock:
    chiave = (str(ced.get("codice_fiscale") or ced.get("nome_dipendente") or "").upper(),
              ced.get("anno"), ced.get("mese"))
    return _LOCK_BUSTE.setdefault(chiave, asyncio.Lock())


async def registra_busta(db, ced: Dict[str, Any], *, filename: str, pdf_data: Optional[str],
                         pdf_text: str, results: Dict[str, Any]) -> None:
    """Scrive una busta letta: in contabilita' se il netto e' verificato, altrimenti solo in HR.

    E' l'unico punto di scrittura di una busta, sia dalla lettura di un PDF
    sia dalla ricarica di una scheda Markdown (``schede_markdown``).
    """
    from app.services.tfr_anticipo_busta import registra_dalla_busta

    async with _lock_busta(ced):
        errori_prima = len(results["errori"])
        await _registra_busta(db, ced, filename=filename, pdf_data=pdf_data,
                              pdf_text=pdf_text, results=results)
        if len(results["errori"]) > errori_prima:
            return
        # Anticipo TFR pagato dentro la busta: va nel motore degli acconti TFR
        # (una volta sola, idempotente), anche se la busta e' gia' in archivio.
        # Sotto lo stesso lock: due copie della busta non lo registrano due volte.
        esito = await registra_dalla_busta(db, ced)
        if esito:
            results.setdefault("anticipi_tfr", []).append(
                {"codice_fiscale": ced.get("codice_fiscale"), "anno": ced.get("anno"),
                 "mese": ced.get("mese"), **esito})


def _annota_busta(results: Dict[str, Any], ced: Dict[str, Any], esito: str) -> None:
    """Cosa e' successo a ogni busta, per chi deve mostrarlo (Libro Unico in HR)."""
    results.setdefault("dettaglio", []).append({
        "dipendente": ced.get("nome_dipendente") or ced.get("codice_fiscale"),
        "codice_fiscale": ced.get("codice_fiscale"),
        "anno": ced.get("anno"), "mese": ced.get("mese"),
        "tipo_cedolino": ced.get("tipo_cedolino") or "mensile",
        "netto": ced.get("netto"), "esito": esito,
    })


async def _registra_busta(db, ced: Dict[str, Any], *, filename: str, pdf_data: Optional[str],
                          pdf_text: str, results: Dict[str, Any]) -> None:
    from app.constants.stati_netto import alimenta_salari
    from app.services import cedolini_versioni as versioni
    from app.services.hr_cedolini_deposito import deposita_cedolino_in_hr
    from app.services.salari_unificati_v2 import processa_cedolino_v2

    chi = ced.get("nome_dipendente") or ced.get("codice_fiscale") or "N/D"

    # Solo un netto verificato dalla cella alimenta Salari (fallisce chiuso).
    if not ced.get("netto") or not alimenta_salari(ced.get("stato_netto")):
        deposito = await deposita_cedolino_in_hr({
            **ced, "filename": filename, "pdf_data": pdf_data,
            "source": "cedolino_v2",
        })
        if deposito.get("esito") in ("inserito", "gia_presente"):
            results["buste_senza_netto"] += 1
            _annota_busta(results, ced, "solo_hr")
        else:
            results["errori"].append(
                f"{chi}: busta senza netto verificato non depositata in HR ({deposito.get('esito')})"
            )
        return

    # La stessa busta arrivata da un altro PDF (Libro Unico, «Variante 1», copia)
    # non diventa un secondo cedolino: se ne annota solo la provenienza.
    gia = await _busta_gia_in_archivio(db, ced)
    if gia:
        await db["cedolini"].update_one({"id": gia["id"]}, {"$addToSet": {"source_occurrences": {
            "filename": filename, "drive_file_id": ced.get("drive_file_id"),
            "source_file_hash": ced.get("source_file_hash"),
        }}})
        originale = await db["cedolini"].find_one({"id": gia["id"]}, {"_id": 0, "pdf_data": 0})
        deposito = await deposita_cedolino_in_hr(originale)
        if deposito.get("esito") not in {"inserito", "gia_presente", "aggiornato", "sostituita"}:
            results["errori"].append(f"{chi}: busta in ERP, deposito HR non completato ({deposito.get('esito')})")
        results["gia_presenti"] = results.get("gia_presenti", 0) + 1
        _annota_busta(results, ced, "gia_presente")
        return

    # Un'altra versione della stessa busta con un netto diverso (stampa di
    # controllo, «Variante N»): un motore solo decide chi vale
    # (`cedolini_versioni`). Se la busta in arrivo e' quella superata si salva
    # subito «sostituito», mai come secondo cedolino attivo.
    arrivo = await versioni.decidi_arrivo(db, {**ced, "pdf_text": pdf_text}, filename=filename)
    sostituita = None
    if arrivo["esito"] == "arrivo_perdente":
        sostituita = {"sostituito_da": arrivo["vincitore"]["id"],
                      "sostituito_motivo": arrivo.get("motivo") or "versione superata"}

    try:
        res = await processa_cedolino_v2(
            db=db,
            cedolino_data=ced,
            pdf_text=pdf_text,
            filename=filename,
            pdf_data=pdf_data,
            sostituita=sostituita,
        )
    except Exception as exc:
        logger.exception("[Cedolini] scrittura di %s (%s) fallita", filename, chi)
        results["errori"].append(f"{chi}: scrittura fallita: {type(exc).__name__}: {exc}")
        return

    if res.get("success") and sostituita:
        results["sostituite"] = results.get("sostituite", 0) + 1
        _annota_busta(results, ced, "sostituita")
        results.setdefault("versioni", []).append({
            "codice_fiscale": ced.get("codice_fiscale"), "anno": ced.get("anno"),
            "mese": ced.get("mese"), "esito": "arrivo_perdente",
            "cedolino_id": res.get("cedolino_id"), **sostituita})
        return

    if res.get("success") and arrivo["esito"] in ("arrivo_vincitore", versioni.ESITO_DA_DECIDERE):
        try:
            voce = await versioni.applica_arrivo(db, arrivo, res["cedolino_id"])
        except Exception as exc:  # noqa: BLE001 - la busta e' scritta, la decisione si ripete dal giro d'archivio
            logger.warning("[Cedolini] versioni di %s (%s) non decise: %s: %s",
                           filename, chi, type(exc).__name__, exc)
            voce = {"esito": "errore", "motivo": f"{type(exc).__name__}: {exc}"}
        results.setdefault("versioni", []).append({
            "codice_fiscale": ced.get("codice_fiscale"), "anno": ced.get("anno"),
            "mese": ced.get("mese"), "cedolino_id": res.get("cedolino_id"),
            "esito": voce.get("esito"), "motivo": voce.get("motivo"),
            "scartate": voce.get("scartate") or []})
        if voce.get("esito") == versioni.ESITO_DA_DECIDERE:
            results["versioni_da_decidere"] = results.get("versioni_da_decidere", 0) + 1

    if res.get("success"):
        results["cedolini_processati"] += 1
        _annota_busta(results, ced, "scritta")
        if res.get("anagrafica_creata"):
            results["anagrafiche_create"] += 1
        if res.get("prima_nota_creata") or res.get("prima_nota_id"):
            results["prima_nota_create"] += 1
        if res.get("riconciliato"):
            results["riconciliati"] += 1
        if res.get("deposito_hr") not in {"inserito", "gia_presente", "aggiornato"}:
            results["errori"].append(f"{chi}: busta in ERP, deposito HR non completato ({res.get('deposito_hr') or 'errore'})")
    elif res.get("errore"):
        results["errori"].append(f"{chi}: {res.get('errore')}")


async def processa_tutti_cedolini_pdf(
    db,
    pdf_data: str,
    filename: str,
    source_path: str = "",
    source_container: str = "",
    drive_file_id: str = "",
    source_file_hash: str = "",
    fonte: str = "",
) -> Dict[str, Any]:
    """Lo scrittore unico dei cedolini: posta, Drive e Documenti > Import.

    ``fonte`` dice da che canale arriva il PDF (``posta``, ``caricato``, o un
    valore grezzo che ``canale_da_fonte`` sa ridurre); senza, ``drive_file_id``
    vale Drive. Ogni busta scritta porta ``canale``.

    Legge col motore unico (``cedolini_motore.leggi_pdf``) e scrive ogni busta
    una volta sola. Una busta col netto verificato va in contabilita' (registro
    ``cedolini``, Prima Nota salari, deposito HR) con
    ``salari_unificati_v2.processa_cedolino_v2``; una busta col netto nullo o a
    zero entra solo nell'archivio HR, dove la vedono le persone, perche' non
    c'e' niente da pagare ne' da registrare in Prima Nota.

    ``esito`` dice sempre cosa c'era nel file (``buste``, ``presenze``,
    ``fuori_periodo``, ``non_cedolino``, ``illeggibile``); ``success`` e' falso
    solo quando il file non si e' potuto leggere o nessuna busta e' stata
    scritta.
    """
    from app.services.cedolini_motore import ESITO_BUSTE, ESITO_ILLEGGIBILE, leggi_pdf

    results = {
        "success": True,
        "esito": None,
        "motivo": "",
        "cedolini_processati": 0,
        "buste_senza_netto": 0,
        "fogli_presenze": 0,
        "anagrafiche_create": 0,
        "prima_nota_create": 0,
        "riconciliati": 0,
        "errori": [],
        "metodo": "motore_unico",
    }

    try:
        file_content = base64.b64decode(pdf_data)
    except Exception as exc:
        results.update(success=False, esito=ESITO_ILLEGGIBILE, motivo="PDF non decodificabile")
        results["errori"].append(f"Errore decodifica Base64: {type(exc).__name__}: {exc}")
        return results

    try:
        lettura = await asyncio.to_thread(leggi_pdf, file_content)
    except Exception as exc:
        logger.warning("[Cedolini] lettura di %s fallita: %s: %s", filename, type(exc).__name__, exc)
        results.update(success=False, esito=ESITO_ILLEGGIBILE, motivo="PDF non leggibile")
        results["errori"].append(f"Lettura PDF fallita: {type(exc).__name__}: {exc}")
        return results

    results.update(
        esito=lettura["esito"], motivo=lettura["motivo"],
        fogli_presenze=len(lettura["presenze"]),
    )
    canale = canale_obbligatorio(fonte or source_container, drive_file_id=drive_file_id)
    drive_md5 = None
    blob_key = None
    if lettura["esito"] == ESITO_BUSTE and not drive_file_id:
        from app.services.email_drive_archive import archive_binary_copy

        try:
            originale = await asyncio.to_thread(
                archive_binary_copy, file_content, filename,
                source=canale, area="cedolini",
            )
            if originale.get("status") not in {"archived", "duplicate"} or not originale.get("drive_file_id"):
                motivo = originale.get("reason") or originale.get("status")
                raise ValueError(f"Originale non archiviato su Drive: {motivo}")
            drive_file_id = originale["drive_file_id"]
            drive_md5 = originale.get("md5")
        except Exception as exc:
            # Il caricamento manuale non dipende dalla quota del service account
            # Drive: il deposito protetto conserva un solo originale, per SHA.
            from app.services.cedolino_originale import conserva_originale
            try:
                blob_key = await conserva_originale(db, file_content)
                logger.info("Originale cedolini conservato nel deposito protetto (%s)", type(exc).__name__)
            except Exception as storage_error:
                results.update(success=False, motivo="Impossibile conservare il PDF originale")
                results["errori"].append(f"{results['motivo']}: {storage_error}")
                return results
    await _scrivi_scheda(db, lettura, file_content, filename, source_file_hash, drive_file_id,
                         source_path, results)
    if lettura["esito"] != ESITO_BUSTE:
        if lettura["esito"] == ESITO_ILLEGGIBILE:
            results["success"] = False
            results["errori"].append(f"{filename}: {lettura['motivo']}")
        return results

    for ced in lettura["buste"]:
        ced["source_path"] = source_path or filename
        ced["source_container"] = source_container or None
        ced["canale"] = canale
        if drive_file_id:
            ced["drive_file_id"] = drive_file_id
            ced["drive_md5"] = drive_md5
            ced["pdf_source_scope"] = "document"
        elif blob_key:
            ced["blob_key"] = blob_key
            ced["pdf_source_scope"] = "document"
        if source_file_hash:
            ced["source_file_hash"] = source_file_hash
        cedolino_pdf_data = ced.pop("_pdf_data", pdf_data)
        ced_pdf_text = ced.pop("_raw_text", "")
        await registra_busta(db, ced, filename=filename, pdf_data=cedolino_pdf_data,
                             pdf_text=ced_pdf_text, results=results)

    # Una busta gia' in archivio e' un esito, non un guasto: la copia di un
    # PDF gia' letto finiva in ERRORI come «1 buste lette» e non ne usciva.
    # Lo stesso per una versione superata, salvata «sostituito».
    if not (results["cedolini_processati"] or results["buste_senza_netto"]
            or results.get("gia_presenti") or results.get("sostituite")):
        results["success"] = False
    if results["errori"]:
        results["success"] = False
        results["partial"] = bool(results["cedolini_processati"] or results["buste_senza_netto"] or results.get("gia_presenti"))
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
    cedolini = await db["cedolini"].find(
        {"codice_fiscale": codice_fiscale},
        {"_id": 0}
    ).sort([("anno", -1), ("mese", -1)]).to_list(100)

    # Totali
    totale_netto = sum(c.get("netto_mese") or 0 for c in cedolini)

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
