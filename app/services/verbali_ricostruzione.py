"""Ricostruzione una tantum dei verbali dal loro PDF (AV3-09), con anteprima.

Un solo lettore, `verbali_document_import.leggi_documento_verbale` (lo stesso di
`process_verbale_document`): numero, IUV, targa, importo e data dell'infrazione
vengono dal **contenuto** del PDF, mai dal nome del file. Il giro:

- non scrive niente con ``dry_run`` (per difetto) e conta cosa farebbe;
- riempie **solo i campi vuoti** di un verbale che ha lo stesso numero: un valore
  diverso da quello gia' in archivio e' un conflitto, si elenca fra i candidati e
  non si applica mai;
- non identifica per solo importo, non elimina nulla: le righe `VERB-…` nate dalla
  sola PEC restano, e la loro copia conforme puo' soltanto completare il verbale
  vero con lo stesso numero (o, con ``crea_da_pec``, aprirlo dalla pipeline);
- porta sui campi canonici i doppioni del collegamento alla fattura
  (`verbali_collegamento_fattura`) e `data_infrazione` -> `data_violazione`;
- e' idempotente: il secondo giro non ha niente da fare (``da_fare = 0``);
- non tocca contabilita' (Prima Nota, giornale, pagamenti).

I verbali senza originale in archivio (`senza_originale`) non si ricostruiscono da
niente: vanno ricaricati da Documenti > Import, che ne riconosce numero o IUV, li
aggiorna e da ora conserva l'originale sul verbale.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CHIAVE_STATO = "verbali_ricostruzione"
LIMITE_ESEMPI = 20

# Campi che un PDF puo' completare su un verbale (nome nel PDF -> nome sul verbale).
CAMPI_DA_PDF = ("targa", "iuv", "importo", "data_violazione", "data_verbale",
                "numero_registro", "ora_violazione")


def _vuoto(valore: Any) -> bool:
    return valore in (None, "", [])


def _cents(valore: Any) -> Optional[int]:
    if _vuoto(valore) or isinstance(valore, bool):
        return None
    try:
        return int((Decimal(str(valore)) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None


def _stesso_valore(campo: str, a: Any, b: Any) -> bool:
    if campo == "importo":
        return _cents(a) is not None and _cents(a) == _cents(b)
    return str(a).strip().upper() == str(b).strip().upper()


def _e_riga_da_pec(riga: Dict[str, Any]) -> bool:
    """Riga nata dalla sola PEC (`VERB-…`): non e' un verbale, e' una notifica."""
    return str(riga.get("numero_verbale") or "").startswith("VERB-") or riga.get("source") == "gmail_scan"


def _dal_pdf(letto: Dict[str, Any]) -> Dict[str, Any]:
    """Campi del verbale letti dal PDF (senza valori vuoti)."""
    ai = letto.get("ai_data") or {}
    campi = {
        "targa": letto.get("targa"),
        "iuv": letto.get("iuv"),
        "importo": letto.get("importo"),
        "data_violazione": letto.get("data_violazione"),
        "data_verbale": ai.get("data_verbale"),
        "numero_registro": ai.get("numero_registro"),
        "ora_violazione": ai.get("ora_violazione"),
    }
    return {k: v for k, v in campi.items() if not _vuoto(v)}


def _differenze(riga: Dict[str, Any], dal_pdf: Dict[str, Any]) -> tuple[Dict[str, Any], List[str]]:
    """(campi da riempire, campi in conflitto). Un conflitto non si applica."""
    nuovi: Dict[str, Any] = {}
    conflitti: List[str] = []
    for campo, valore in dal_pdf.items():
        attuale = riga.get(campo)
        if _vuoto(attuale):
            nuovi[campo] = valore
        elif not _stesso_valore(campo, attuale, valore):
            conflitti.append(campo)
    return nuovi, conflitti


def _pulizia_collegamento(riga: Dict[str, Any]) -> Dict[str, Any]:
    """Cosa serve per portare il collegamento alla fattura sui soli campi canonici.

    ``set``: campi da scrivere; ``unset``: copie legacy identiche da togliere;
    ``divergente``: id diversi fra canonico e legacy (si decide a mano, non si tocca).
    """
    from app.services.verbali_collegamento_fattura import CAMPI_LEGACY_COLLEGAMENTO

    canonico = riga.get("fattura_id")
    legacy = riga.get("fattura_associata_id")
    esito: Dict[str, Any] = {"set": {}, "unset": [], "divergente": False}
    if not _vuoto(canonico) and not _vuoto(legacy) and str(canonico) != str(legacy):
        esito["divergente"] = True
        return esito
    if _vuoto(canonico) and not _vuoto(legacy):
        esito["set"]["fattura_id"] = str(legacy)
        numero = riga.get("fattura_numero") or riga.get("fattura_associata_numero")
        if not _vuoto(numero) and _vuoto(riga.get("fattura_numero")):
            esito["set"]["fattura_numero"] = str(numero)
    elif not _vuoto(canonico) and _vuoto(riga.get("fattura_numero")) and not _vuoto(riga.get("fattura_associata_numero")):
        esito["set"]["fattura_numero"] = str(riga["fattura_associata_numero"])
    if not _vuoto(canonico) or not _vuoto(legacy):
        esito["unset"] = [c for c in CAMPI_LEGACY_COLLEGAMENTO if c in riga]
    return esito


async def ricostruisci_verbali_da_pdf(
    db, *, dry_run: bool = True, crea_da_pec: bool = False,
) -> Dict[str, Any]:
    """Anteprima (o applicazione) della ricostruzione dei verbali dal PDF."""
    from app.services.verbali_document_import import leggi_documento_verbale, process_verbale_document
    from app.services.verbali_evidence import data_violazione_verbale
    from app.services.verbali_pdf_service import collect_verbale_pdfs

    esito: Dict[str, Any] = {
        "dry_run": dry_run, "crea_da_pec": crea_da_pec,
        "verbali_analizzati": 0, "righe_da_pec": 0,
        "con_originale": 0, "senza_originale": 0, "pdf_letti": 0, "pdf_non_verbale": 0,
        "illeggibili": 0,
        "da_completare": 0, "campi_da_riempire": {},
        "conflitti": 0, "elenco_conflitti": [],
        "numero_diverso_dal_pdf": 0,
        "pec_su_verbale_vero": 0, "pec_da_creare": 0, "pec_incomplete": 0, "pec_ambigue": 0,
        "elenco_pec_da_creare": [],
        "creati": 0,
        "collegamento_da_riportare": 0, "collegamento_divergente": 0, "copie_da_togliere": 0,
        "data_infrazione_da_riportare": 0,
        "verbali_con_targa_e_data_senza_driver": 0, "veicoli_noleggio_vuota": False,
        "scritti": 0, "da_fare": 0, "errori": 0,
    }
    ora = datetime.now(timezone.utc).isoformat()
    proiezione = {"_id": 0, "pdf_data": 0, "quietanza_pdf": 0}
    righe = await db["verbali_noleggio"].find({}, proiezione).to_list(None)
    righe = [r for r in righe if str(r.get("stato") or "").lower() != "quarantena"]
    veri: Dict[str, Dict[str, Any]] = {}
    duplicati_numero: set = set()
    for riga in righe:
        numero = str(riga.get("numero_verbale") or "").upper()
        if not numero or _e_riga_da_pec(riga):
            continue
        if numero in veri:
            duplicati_numero.add(numero)
        veri[numero] = riga
    for numero in duplicati_numero:
        veri.pop(numero, None)  # due verbali con lo stesso numero: mai scegliere

    esito["veicoli_noleggio_vuota"] = (await db["veicoli_noleggio"].count_documents({})) == 0
    da_scrivere: Dict[str, Dict[str, Any]] = {}   # id verbale -> {"set":…, "unset":[…]}
    visti_hash: set = set()

    def _registra(riga: Dict[str, Any], campi: Dict[str, Any], togliere: List[str] = ()) -> None:
        chiave = str(riga.get("id") or riga.get("numero_verbale"))
        voce = da_scrivere.setdefault(chiave, {"riga": riga, "set": {}, "unset": []})
        voce["set"].update(campi)
        voce["unset"].extend(c for c in togliere if c not in voce["unset"])

    for riga in righe:
        esito["verbali_analizzati"] += 1
        da_pec = _e_riga_da_pec(riga)
        if da_pec:
            esito["righe_da_pec"] += 1

        # 1. collegamento alla fattura e data dell'infrazione: campi canonici
        if not da_pec or riga.get("fattura_id") or riga.get("fattura_associata_id"):
            pulizia = _pulizia_collegamento(riga)
            if pulizia["divergente"]:
                esito["collegamento_divergente"] += 1
            elif pulizia["set"] or pulizia["unset"]:
                if pulizia["set"]:
                    esito["collegamento_da_riportare"] += 1
                esito["copie_da_togliere"] += len(pulizia["unset"])
                _registra(riga, pulizia["set"], pulizia["unset"])
        if _vuoto(riga.get("data_violazione")) and not _vuoto(riga.get("data_infrazione")):
            esito["data_infrazione_da_riportare"] += 1
            _registra(riga, {"data_violazione": str(riga["data_infrazione"])[:10]}, ["data_infrazione"])
        elif not _vuoto(riga.get("data_infrazione")):
            if str(riga["data_infrazione"])[:10] == str(riga["data_violazione"])[:10]:
                _registra(riga, {}, ["data_infrazione"])   # stessa data: resta solo la canonica
            else:
                esito["conflitti"] += 1
                if len(esito["elenco_conflitti"]) < LIMITE_ESEMPI:
                    esito["elenco_conflitti"].append({
                        "numero_verbale": str(riga.get("numero_verbale")),
                        "campo": "data_violazione", "fonte": "data_infrazione_legacy"})

        # 2. lettura dei PDF del verbale (il payload si legge per id, solo dove c'e' un PDF)
        sorgente = riga
        if (riga.get("pdf_hash") or riga.get("pdf_filename")) and riga.get("id"):
            sorgente = await db["verbali_noleggio"].find_one({"id": riga["id"]}, {"_id": 0}) or riga
        try:
            pdfs = [p for p in await collect_verbale_pdfs(db, sorgente, include_content=True)
                    if p.get("tipo") != "quietanza" and p.get("content_base64")]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Verbali ricostruzione: PDF non raccolti: %s: %s", type(exc).__name__, exc)
            esito["errori"] += 1
            continue
        if not pdfs:
            if not da_pec:
                esito["senza_originale"] += 1
            continue
        if not da_pec:
            esito["con_originale"] += 1
        for pdf in pdfs:
            try:
                contenuto = base64.b64decode(pdf["content_base64"])
            except (ValueError, TypeError):
                esito["illeggibili"] += 1
                continue
            impronta = hashlib.sha256(contenuto).hexdigest()
            if impronta in visti_hash:
                continue
            visti_hash.add(impronta)
            try:
                letto = await leggi_documento_verbale(
                    contenuto, pdf.get("filename") or "verbale.pdf", usa_ai=False)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Verbali ricostruzione: PDF non letto: %s: %s", type(exc).__name__, exc)
                esito["illeggibili"] += 1
                continue
            esito["pdf_letti"] += 1
            if letto.get("is_receipt"):
                esito["pdf_non_verbale"] += 1
                continue
            numero_pdf = str(letto.get("numero") or "").upper()
            dal_pdf = _dal_pdf(letto)

            if da_pec:
                target = veri.get(numero_pdf) if numero_pdf else None
                if numero_pdf in duplicati_numero:
                    esito["pec_ambigue"] += 1   # due verbali con quel numero: si sceglie a mano
                elif target is not None:
                    esito["pec_su_verbale_vero"] += 1
                    nuovi, conflitti = _differenze(target, dal_pdf)
                    if nuovi:
                        _registra(target, nuovi)
                    for campo in conflitti:
                        esito["conflitti"] += 1
                        if len(esito["elenco_conflitti"]) < LIMITE_ESEMPI:
                            esito["elenco_conflitti"].append({
                                "numero_verbale": numero_pdf, "campo": campo, "fonte": "copia_conforme_pec"})
                elif numero_pdf and dal_pdf.get("targa") and dal_pdf.get("importo") is not None:
                    esito["pec_da_creare"] += 1
                    if len(esito["elenco_pec_da_creare"]) < LIMITE_ESEMPI:
                        esito["elenco_pec_da_creare"].append({
                            "numero_verbale": numero_pdf, "campi_letti": sorted(dal_pdf)})
                    if crea_da_pec and not dry_run:
                        esito_pipeline = await process_verbale_document(
                            db, document_id=str(pdf.get("id") or impronta[:32]),
                            content=contenuto, filename=pdf.get("filename") or "verbale.pdf",
                            source="notifica_pec")
                        if esito_pipeline.get("status") == "linked":
                            esito["creati"] += 1
                else:
                    esito["pec_incomplete"] += 1
                continue

            # verbale vero con il suo PDF: il numero letto deve essere il suo
            if numero_pdf and numero_pdf != str(riga.get("numero_verbale") or "").upper():
                esito["numero_diverso_dal_pdf"] += 1
                continue
            nuovi, conflitti = _differenze(riga, dal_pdf)
            if nuovi:
                _registra(riga, nuovi)
            for campo in conflitti:
                esito["conflitti"] += 1
                if len(esito["elenco_conflitti"]) < LIMITE_ESEMPI:
                    esito["elenco_conflitti"].append({
                        "numero_verbale": str(riga.get("numero_verbale")), "campo": campo, "fonte": "pdf_originale"})

    # 3. driver alla data: solo conteggio (l'assegnazione resta al giro di riconciliazione)
    for riga in righe:
        if (riga.get("targa") and data_violazione_verbale(riga)
                and _vuoto(riga.get("driver_id")) and _vuoto(riga.get("driver"))):
            esito["verbali_con_targa_e_data_senza_driver"] += 1

    for voce in da_scrivere.values():
        for campo in voce["set"]:
            if campo in CAMPI_DA_PDF:
                esito["campi_da_riempire"][campo] = esito["campi_da_riempire"].get(campo, 0) + 1
        if any(campo in CAMPI_DA_PDF for campo in voce["set"]):
            esito["da_completare"] += 1

    esito["da_fare"] = len(da_scrivere) + esito["pec_da_creare"] * (1 if crea_da_pec else 0)
    if not dry_run:
        for chiave, voce in da_scrivere.items():
            riga = voce["riga"]
            filtro = {"id": riga["id"]} if riga.get("id") else {"numero_verbale": riga.get("numero_verbale")}
            campi = dict(voce["set"])
            if "importo" in campi:
                campi["importo"] = float(Decimal(str(campi["importo"])).quantize(Decimal("0.01")))
                campi.setdefault("importo_fonte", "pdf_ricostruzione")
            azione: Dict[str, Any] = {"$set": {**campi, "updated_at": ora}}
            if voce["unset"]:
                azione["$unset"] = {c: "" for c in voce["unset"]}
            await db["verbali_noleggio"].update_one(filtro, azione)
            esito["scritti"] += 1
    esito["elenco_conflitti"] = esito["elenco_conflitti"][:LIMITE_ESEMPI]
    return esito


# ── esecuzione in sottofondo, con lo stato in sistema_stato ────────────────────────────

_task: Optional["asyncio.Task"] = None


async def _esegui(db, dry_run: bool, crea_da_pec: bool) -> None:
    try:
        esito = await ricostruisci_verbali_da_pdf(db, dry_run=dry_run, crea_da_pec=crea_da_pec)
        await db["sistema_stato"].update_one(
            {"chiave": CHIAVE_STATO},
            {"$set": {"esito": esito, "errore": None, "in_corso": False,
                      "terminato_il": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    except Exception as exc:  # noqa: BLE001 - l'esito resta nello stato
        logger.exception("Ricostruzione verbali fallita: %s", type(exc).__name__)
        await db["sistema_stato"].update_one(
            {"chiave": CHIAVE_STATO},
            {"$set": {"errore": f"{type(exc).__name__}: {exc}", "in_corso": False}}, upsert=True)


async def avvia(db, *, dry_run: bool = True, crea_da_pec: bool = False) -> Dict[str, Any]:
    """Avvia il giro in sottofondo (uno solo alla volta)."""
    global _task
    if _task is not None and not _task.done():
        return {"avviato": False, **await stato(db)}
    await db["sistema_stato"].update_one(
        {"chiave": CHIAVE_STATO},
        {"$set": {"in_corso": True, "dry_run": dry_run, "crea_da_pec": crea_da_pec,
                  "avviato_il": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    _task = asyncio.create_task(_esegui(db, dry_run, crea_da_pec))
    return {"avviato": True, "stato": "avvio", "dry_run": dry_run, "crea_da_pec": crea_da_pec}


async def stato(db) -> Dict[str, Any]:
    dati = await db["sistema_stato"].find_one({"chiave": CHIAVE_STATO}, {"_id": 0})
    if not dati:
        return {"stato": "mai_avviato"}
    dati.pop("chiave", None)
    dati["stato"] = "in_corso" if _task is not None and not _task.done() else "completato"
    return dati
