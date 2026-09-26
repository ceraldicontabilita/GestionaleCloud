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
from typing import Dict, Any, List

from app.services.cedolini_motore import PAYROLL_MIN_YEAR  # noqa: F401 (re-export)

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


async def processa_tutti_cedolini_pdf(
    db,
    pdf_data: str,
    filename: str,
    source_path: str = "",
    source_container: str = "",
    drive_file_id: str = "",
    source_file_hash: str = "",
) -> Dict[str, Any]:
    """Lo scrittore unico dei cedolini: posta, Drive e Documenti > Import.

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
    if lettura["esito"] != ESITO_BUSTE:
        if lettura["esito"] == ESITO_ILLEGGIBILE:
            results["success"] = False
            results["errori"].append(f"{filename}: {lettura['motivo']}")
        return results

    from app.constants.stati_netto import alimenta_salari
    from app.services.hr_cedolini_deposito import deposita_cedolino_in_hr
    from app.services.salari_unificati_v2 import processa_cedolino_v2

    for ced in lettura["buste"]:
        ced["source_path"] = source_path or filename
        ced["source_container"] = source_container or None
        if drive_file_id:
            ced["drive_file_id"] = drive_file_id
        if source_file_hash:
            ced["source_file_hash"] = source_file_hash
        cedolino_pdf_data = ced.pop("_pdf_data", pdf_data)
        ced_pdf_text = ced.pop("_raw_text", "")
        chi = ced.get("nome_dipendente") or ced.get("codice_fiscale") or "N/D"

        # Solo un netto verificato dalla cella alimenta Salari (fallisce chiuso).
        if not ced.get("netto") or not alimenta_salari(ced.get("stato_netto")):
            deposito = await deposita_cedolino_in_hr({
                **ced, "filename": filename, "pdf_data": cedolino_pdf_data,
                "source": "cedolino_v2",
            })
            if deposito.get("esito") in ("inserito", "gia_presente"):
                results["buste_senza_netto"] += 1
            else:
                results["errori"].append(
                    f"{chi}: busta senza netto verificato non depositata in HR ({deposito.get('esito')})"
                )
            continue

        try:
            res = await processa_cedolino_v2(
                db=db,
                cedolino_data=ced,
                pdf_text=ced_pdf_text,
                filename=filename,
                pdf_data=cedolino_pdf_data,
            )
        except Exception as exc:
            logger.exception("[Cedolini] scrittura di %s (%s) fallita", filename, chi)
            results["errori"].append(f"{chi}: scrittura fallita: {type(exc).__name__}: {exc}")
            continue

        if res.get("success"):
            results["cedolini_processati"] += 1
            if res.get("anagrafica_creata"):
                results["anagrafiche_create"] += 1
            if res.get("prima_nota_creata") or res.get("prima_nota_id"):
                results["prima_nota_create"] += 1
            if res.get("riconciliato"):
                results["riconciliati"] += 1
        elif res.get("errore"):
            results["errori"].append(f"{chi}: {res.get('errore')}")

    if not (results["cedolini_processati"] or results["buste_senza_netto"]):
        results["success"] = False
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
