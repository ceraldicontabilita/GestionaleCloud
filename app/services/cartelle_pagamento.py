"""Cartella di pagamento dell'Agente della riscossione (contravvenzioni e ruoli).

La cartella e' un fatto autorevole: crea subito l'attesa «da pagare» (una prova
successiva non crea mai l'obbligo che dovrebbe dimostrare). La soddisfa solo la
ricevuta di pagamento con lo **stesso IUV** e lo stesso importo al centesimo; con
lo stesso IUV e importo diverso resta ``DA_VERIFICARE``.

- Il termine e' 60 giorni dalla **notifica**, e la data di notifica non sta nel
  PDF: finche' il titolare non la dice, la scadenza resta vuota (mai inventata).
- Ogni riga di ruolo porta il numero del verbale e la targa: il verbale si
  aggancia solo se e' uno solo e la targa coincide; altrimenti si mostrano i
  candidati e nessun collegamento viene applicato.
- L'originale si conserva una volta sola per SHA-256, come gli atti giudiziari.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from app.services.expectation_policy import (
    ExpectationStatus, expectation_evidence_fields, expectation_fields,
)

logger = logging.getLogger(__name__)

COLL = "cartelle_pagamento"
PREFISSO_BLOB = "cartella-pagamento:"
TIPO_ATTESA = "CARTELLA_DA_PAGARE"
OWNER_ATTESA = "fiscale"
GIORNI_PAGAMENTO = 60

_NUMERO = re.compile(r"CARTELLA DI PAGAMENTO N\.\s*(\d{3}\s+\d{4}\s+\d{8}\s+\d{2}\s*/\s*\d{3})")
_RUOLO = re.compile(r"RUOLO N\.\s*(\d{4}/\d+)")
_ENTE = re.compile(r"RUOLO EMESSO DA\s*\n\s*([^\n]+)")
# Codice avviso pagoPA dell'Agente della riscossione: cifra iniziale + IUV di 17 cifre (800…).
_AVVISO = re.compile(r"\b(1800\d{14})\b")
_CBILL = re.compile(r"\b([A-Z0-9]{5})\s*\n\s*1800\d{14}\b")
_CF = re.compile(r"Destinatario\s+Cod\s*\.\s*Fisc(?:ale|\.)\s+([A-Z0-9]{16}|\d{11})\b", re.I)
_TOTALE = re.compile(
    r"Totale\s+da\s+pagare\s+entro\s+60\s+giorni\s+dalla\s+data\s+di\s+notifica"
    r"\s*(?:euro|€)?\s*([\d.]+,\d{2})\b", re.I,
)
_IMPORTO_RIGA = re.compile(r"^\s*([\d.]+,\d{2})\s*$")
_RIGA = re.compile(
    r"^\s*(\d{1,3})\s*\n\s*(\d{4})\s*\n\s*(\d{3,5})\s+([^\n]+)\n\s*([\d.]+,\d{2})\s*\n"
    r"(?:\s*VER\.\s*(\S+)\s+(\d{2}/\d{2}/\d{4})\s+NOT\.\s*IL\s+(\d{2}/\d{2}/\d{4})\s+TG\.\s*([A-Z0-9]+))?",
    re.MULTILINE,
)


def e_cartella_pagamento(testo: str) -> bool:
    """Vero se il testo e' una cartella di pagamento dell'Agente della riscossione."""
    compatto = re.sub(r"\s+", " ", testo or "").upper()
    return ("CARTELLA DI PAGAMENTO N." in compatto
            and "AGENZIA DELLE ENTRATE-RISCOSSIONE" in compatto.replace(" - ", "-"))


def _importo(valore: str) -> Decimal:
    return Decimal(valore.replace(".", "").replace(",", "."))


def _centesimi(valore: Decimal) -> int:
    return int(valore.quantize(Decimal("0.01")) * 100)


def _testo(contenuto: bytes) -> str:
    try:
        import fitz

        with fitz.open(stream=contenuto, filetype="pdf") as documento:
            return "\n".join(pagina.get_text() for pagina in documento)
    except Exception as exc:  # noqa: BLE001 - un PDF illeggibile non e' una cartella
        logger.info("Cartella di pagamento non leggibile: %s: %s", type(exc).__name__, exc)
        return ""


def _normalizza_numero(numero: str) -> str:
    return re.sub(r"\s+", " ", numero.replace(" /", "/").replace("/ ", "/")).strip()


def _numero_fiscale(numero: str) -> str:
    """Numero canonico AdeR a 20 cifre, senza cambiare quello stampato."""
    return re.sub(r"\D", "", numero or "")


async def _deposita_posizione_fiscale(
    db, *, nome: str, contenuto: bytes, dati: Dict[str, Any], drive_file_id: str | None,
    drive_md5: str | None,
) -> Dict[str, Any]:
    """Collega l'originale alla posizione fiscale senza sovrascrivere lo snapshot AdeR.

    La cartella prova il debito originario. Uno snapshot successivo del portale
    può dire che il residuo è zero, ma non diventa per questo una quietanza.
    """
    from app.config import settings
    from app.db_collections import COLL_TAX_COLLECTION_CLAIMS
    from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService
    from app.services.fiscal_evidence import link_evidence, normalize_evidence, stable_id

    company_id = str(dati.get("codice_fiscale_destinatario") or settings.FISCAL_COMPANY_ID or "")
    if not company_id or company_id != str(settings.FISCAL_COMPANY_ID or company_id):
        raise ValueError("Cartella riferita a un contribuente diverso")
    numero = _numero_fiscale(dati["numero_cartella"])
    if len(numero) != 20:
        raise ValueError("Numero cartella AdeR non normalizzabile")
    sha256 = hashlib.sha256(contenuto).hexdigest()
    source_metadata = {"source_sha256": sha256}
    if drive_file_id:
        source_metadata["drive_file_id"] = drive_file_id
    if drive_md5:
        source_metadata["drive_md5"] = drive_md5
    reference = await FiscalDocumentIngestionService(db, company_id).ingest(
        content=contenuto, filename=nome, source="cartella_pagamento",
        source_metadata=source_metadata, expected_sha256=sha256,
        category_hint="riscossione",
    )
    claim_id = stable_id("taxclaim", company_id, numero)
    # ``leggi_cartella`` restituisce già importi normalizzati con il punto
    # decimale (es. ``118.88``): non ripassarli dal lettore del formato
    # italiano, che scambierebbe il punto per un separatore delle migliaia.
    totale_cents = _centesimi(Decimal(str(dati["totale"]))) if dati.get("totale") is not None else None
    now = datetime.now(timezone.utc).isoformat()
    initial_state = {
        "business_status": "PAYABLE" if dati.get("importi_quadrano") else "REVIEW_REQUIRED",
        "residual_cents": totale_cents,
    }
    await db[COLL_TAX_COLLECTION_CLAIMS].update_one(
        {"company_id": company_id, "id": claim_id},
        {"$setOnInsert": {
            "id": claim_id, "company_id": company_id, "collection_number": numero,
            "created_at": now, **initial_state,
        }, "$set": {
            "original_document_id": reference["document_id"],
            "original_version_id": reference["version_id"],
            "original_sha256": sha256,
            "original_filename": nome,
            "original_total_cents": totale_cents,
            "original_creditor": dati.get("ente_creditore"),
            "original_role": dati.get("ruolo"),
            "original_tax_lines": dati.get("righe") or [],
            "original_notification_cost_cents": (
                _centesimi(Decimal(str(dati["diritti_notifica"])))
                if dati.get("diritti_notifica") is not None else None
            ),
            "updated_at": now,
        }},
        upsert=True,
    )
    evidence = normalize_evidence(
        document_id=reference["document_id"], version_id=reference["version_id"],
        page_number=1, field="collection_number", raw_value=dati["numero_cartella"],
        normalized_value=numero, parser_version="cartella-riepilogo-v2",
        reason="original_collection_notice",
    )
    await link_evidence(
        db, company_id=company_id, entity_type="tax_collection_claim", entity_id=claim_id,
        relation_type="original_collection_notice", evidence=[evidence],
        actor="cartella_pagamento_import",
    )
    claim = await db[COLL_TAX_COLLECTION_CLAIMS].find_one(
        {"company_id": company_id, "id": claim_id}, {"_id": 0},
    )
    return {
        "claim_id": claim_id,
        "document_id": reference["document_id"],
        "version_id": reference["version_id"],
        "business_status": (claim or {}).get("business_status"),
        "residual_cents": (claim or {}).get("residual_cents"),
    }


def _snapshot_supera_attesa(fiscal: Dict[str, Any] | None) -> bool:
    """Residuo AdeR zero chiude l'attesa corrente, ma non prova il pagamento."""
    return bool(fiscal and fiscal.get("residual_cents") == 0)


def _riepilogo_importi(testo: str):
    """Legge il riepilogo entro 60 giorni, inclusi gli oneri dei modelli precedenti.

    Le prime cifre del PDF possono essere i subtotali di più enti. Il totale è
    quello etichettato; la tabella SOMME DA PAGARE deve confermarlo, al centesimo.
    """
    match = _TOTALE.search(testo)
    if not match:
        return None, None, None, None, False
    totale = _importo(match.group(1))
    sezione = re.search(r"SOMME\s+DA\s+PAGARE\s*\n", testo[match.end():], re.I)
    # Alcuni estrattori restituiscono il riepilogo senza il titolo della tabella.
    blocco = testo[match.end():]
    if sezione:
        blocco = blocco[sezione.end():]
    gruppi, gruppo = [], []
    for line in blocco.splitlines():
        m = _IMPORTO_RIGA.fullmatch(line)
        if m:
            gruppo.append(_importo(m.group(1)))
        elif line.strip():
            if gruppo:
                gruppi.append(gruppo)
                gruppo = []
            if sezione and gruppi:
                break  # La colonna oltre 60 giorni non è il dovuto iniziale.
        if not sezione and re.search(r"RUOLO|DETTAGLIO", line, re.I):
            break
    if gruppo:
        gruppi.append(gruppo)
    for valori in gruppi:
        if len(valori) not in (3, 4) or valori[-1] != totale:
            continue
        if sum(valori[:-1], Decimal("0")) != totale:
            continue
        ente, diritti = valori[0], valori[-2]
        oneri = valori[1] if len(valori) == 4 else Decimal("0.00")
        return ente, diritti, oneri, totale, True
    return None, None, None, totale, False


def leggi_cartella(testo: str) -> Optional[Dict[str, Any]]:
    """I dati della cartella, o None se non lo e'. Importi in stringa, mai float."""
    if not e_cartella_pagamento(testo):
        return None
    numero = _NUMERO.search(testo)
    if not numero:
        return None
    ente = _ENTE.search(testo)
    ruolo = _RUOLO.search(testo)
    avviso = _AVVISO.search(testo)
    cbill = _CBILL.search(testo)
    cf = _CF.search(testo)
    righe: List[Dict[str, Any]] = []
    for m in _RIGA.finditer(testo):
        riga = {
            "progressivo": m.group(1), "anno": m.group(2), "codice_tributo": m.group(3),
            "descrizione": m.group(4).strip(), "importo": str(_importo(m.group(5))),
        }
        if m.group(6):
            riga.update({"numero_verbale": m.group(6).upper(), "data_verbale": m.group(7),
                         "data_notifica_verbale": m.group(8), "targa": m.group(9).upper()})
        righe.append(riga)
    ente_importo, diritti, oneri, totale, riepilogo_quadra = _riepilogo_importi(testo)
    somma_righe = sum((Decimal(r["importo"]) for r in righe), Decimal("0"))
    quadra = bool(
        riepilogo_quadra and (not righe or somma_righe == ente_importo)
    )
    verbali = sorted({(r["numero_verbale"], r["targa"]) for r in righe if r.get("numero_verbale")})
    return {
        "numero_cartella": _normalizza_numero(numero.group(1)),
        "ente_creditore": ente.group(1).strip() if ente else None,
        "ruolo": ruolo.group(1) if ruolo else None,
        "codice_fiscale_destinatario": cf.group(1) if cf else None,
        "righe": righe,
        "importo_ente": str(ente_importo) if ente_importo is not None else None,
        "diritti_notifica": str(diritti) if diritti is not None else None,
        "oneri_riscossione": str(oneri) if oneri is not None else None,
        "totale": str(totale) if totale is not None else None,
        "parser_version": "cartella-riepilogo-v2",
        "importi_quadrano": quadra,
        "codice_avviso": avviso.group(1) if avviso else None,
        # Lo IUV e' il codice avviso senza la cifra iniziale (aux digit).
        "iuv": avviso.group(1)[1:] if avviso else None,
        "codice_cbill": cbill.group(1) if cbill else None,
        "verbali": [{"numero_verbale": n, "targa": t} for n, t in verbali],
        "termine": f"{GIORNI_PAGAMENTO} giorni dalla data di notifica",
    }


def scadenza_da_notifica(data_notifica: str) -> str:
    """60 giorni dalla notifica; un sabato o una domenica passa al lunedi' (festivita' escluse)."""
    giorno = date.fromisoformat(data_notifica) + timedelta(days=GIORNI_PAGAMENTO)
    while giorno.weekday() >= 5:
        giorno += timedelta(days=1)
    return giorno.isoformat()


def _archivio():
    from app.database import Database
    from app.services.blob_store import blob_store_per_runtime

    return blob_store_per_runtime(Database.db)


def _chiave(numero_verbale: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(numero_verbale or "").upper())


async def _candidati_verbale(db, numero: str, targa: str) -> List[Dict[str, Any]]:
    """I verbali in archivio con quel numero (e, se la scheda la ha, quella targa)."""
    chiave = _chiave(numero)
    trovati: List[Dict[str, Any]] = []
    for collezione in ("verbali_noleggio", "verbali_noleggio_completi"):
        async for v in db[collezione].find({}, {"_id": 0, "id": 1, "numero_verbale": 1, "targa": 1}):
            if _chiave(v.get("numero_verbale")) != chiave:
                continue
            if v.get("targa") and str(v["targa"]).upper() != targa:
                continue
            trovati.append({"collezione": collezione, "id": v.get("id"),
                            "numero_verbale": v.get("numero_verbale")})
    return trovati


async def collega_verbali(db, cartella_id: str) -> Dict[str, Any]:
    """Aggancia i verbali citati dalla cartella: solo se univoci (numero e targa)."""
    doc = await db[COLL].find_one({"id": cartella_id}, {"_id": 0})
    if not doc:
        return {"collegati": 0}
    collegati, candidati = [], {}
    for v in doc.get("verbali") or []:
        trovati = await _candidati_verbale(db, v["numero_verbale"], v["targa"])
        if len(trovati) == 1:
            collegati.append({**v, **trovati[0]})
        elif trovati:
            candidati[v["numero_verbale"]] = trovati
    await db[COLL].update_one({"id": cartella_id}, {"$set": {
        "verbali_collegati": collegati, "verbali_candidati": candidati,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"collegati": len(collegati), "candidati": sum(len(x) for x in candidati.values())}


async def registra_cartella(
    db, nome: str, contenuto: bytes, *, drive_file_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Conserva l'originale, apre l'attesa «da pagare» e cerca ricevuta e verbale."""
    dati = leggi_cartella(_testo(contenuto))
    if not dati:
        return {"success": False, "message": "Non e' una cartella di pagamento riconoscibile"}
    ora = datetime.now(timezone.utc).isoformat()
    id_cartella = "cartella:" + re.sub(r"\W+", "", dati["numero_cartella"])
    impronta = hashlib.sha256(contenuto).hexdigest()
    esistente = await db[COLL].find_one({"id": id_cartella}, {"_id": 0, "contenuto_b64": 0})
    if esistente:
        aggiornati = False
        if (esistente.get("sha256") == impronta and not esistente.get("parser_version")
                and dati.get("totale") is not None):
            campi = ("importo_ente", "diritti_notifica", "oneri_riscossione", "totale",
                     "importi_quadrano", "parser_version", "codice_fiscale_destinatario")
            result = await db[COLL].update_one(
                {"id": id_cartella, "sha256": impronta, "parser_version": None},
                {"$set": {**{k: dati[k] for k in campi}, "ultimo_caricamento": ora,
                          "parser_precedente": {k: esistente.get(k) for k in campi},
                          "parser_aggiornato_il": ora}},
            )
            aggiornati = bool(result.matched_count)
        else:
            await db[COLL].update_one({"id": id_cartella}, {"$set": {"ultimo_caricamento": ora}})
        fiscal = await _deposita_posizione_fiscale(
            db, nome=nome, contenuto=contenuto, dati=dati,
            drive_file_id=esistente.get("drive_file_id"), drive_md5=esistente.get("drive_md5"),
        )
        ricevuta = await chiudi_da_ricevuta_esistente(db, id_cartella)
        if not ricevuta and _snapshot_supera_attesa(fiscal):
            await db[COLL].update_one(
                {"id": id_cartella, "expectation_status": {"$ne": ExpectationStatus.SODDISFATTO.value}},
                {"$set": {
                    "expectation_status": ExpectationStatus.SUPERATO.value,
                    "expectation_resolution": "ADER_CURRENT_RESIDUAL_ZERO_WITHOUT_PAYMENT_EVIDENCE",
                    "tax_collection_claim_id": fiscal["claim_id"], "updated_at": ora,
                }},
            )
        return {"success": True, "duplicate": True, "id": id_cartella, **dati,
                "metadati_aggiornati": aggiornati, "ricevuta": ricevuta,
                "fiscal": fiscal}
    documento: Dict[str, Any] = {
        "id": id_cartella, "sha256": impronta, "nome": nome, "dimensione": len(contenuto),
        "mime": "application/pdf", "caricato_il": ora, "ultimo_caricamento": ora,
        "drive_file_id": drive_file_id, "data_notifica": None, "scadenza": None,
        **dati,
        **expectation_fields(
            expectation_type=TIPO_ATTESA, owner=OWNER_ATTESA, source_fact_id=id_cartella,
        ),
    }
    if not dati["importi_quadrano"]:
        # Le somme non tornano: si conserva, ma non si dichiara un dovuto certo.
        documento["expectation_status"] = ExpectationStatus.DA_VERIFICARE.value
    archivio = _archivio()
    drive_md5 = None
    if getattr(archivio, "persistent", False):
        if not drive_file_id:
            from app.services.email_drive_archive import archive_binary_copy

            esito = await asyncio.to_thread(
                archive_binary_copy, contenuto, nome,
                source="cartelle_pagamento", area=COLL,
            )
            if esito.get("status") not in {"archived", "duplicate"}:
                raise RuntimeError("Cartella non verificata su Drive")
            drive_file_id = esito["drive_file_id"]
            drive_md5 = esito.get("md5")
            documento["drive_md5"] = drive_md5
        documento["drive_file_id"] = drive_file_id
        documento["drive_archive_status"] = "verified"
    else:
        documento["contenuto_b64"] = base64.b64encode(contenuto).decode("ascii")
    fiscal = await _deposita_posizione_fiscale(
        db, nome=nome, contenuto=contenuto, dati=dati,
        drive_file_id=drive_file_id, drive_md5=drive_md5,
    )
    documento["tax_collection_claim_id"] = fiscal["claim_id"]
    documento["fiscal_document_id"] = fiscal["document_id"]
    if _snapshot_supera_attesa(fiscal):
        documento["expectation_status"] = ExpectationStatus.SUPERATO.value
        documento["expectation_resolution"] = "ADER_CURRENT_RESIDUAL_ZERO_WITHOUT_PAYMENT_EVIDENCE"
    await db[COLL].insert_one(documento)
    verbali = await collega_verbali(db, id_cartella)
    ricevuta = await chiudi_da_ricevuta_esistente(db, id_cartella)
    # La PEC che l'ha notificata puo' essere arrivata prima della cartella: la data si mette adesso.
    from app.services.notifiche_pec_cartelle import applica_notifiche_in_attesa

    notifica = await applica_notifiche_in_attesa(db, id_cartella)
    return {"success": True, "duplicate": False, "id": id_cartella, **dati,
            "verbali": verbali, "ricevuta": ricevuta, "notifica_pec": notifica,
            "fiscal": fiscal}


async def imposta_notifica(db, cartella_id: str, data_notifica: str) -> Dict[str, Any]:
    """Il titolare dice quando la cartella e' stata notificata: parte il termine di 60 giorni."""
    try:
        scadenza = scadenza_da_notifica(data_notifica)
    except ValueError:
        return {"success": False, "message": "Data di notifica non valida (aaaa-mm-gg)"}
    trovata = await db[COLL].find_one({"id": cartella_id}, {"_id": 0, "id": 1})
    if not trovata:
        return {"success": False, "message": "Cartella non trovata"}
    await db[COLL].update_one({"id": cartella_id}, {"$set": {
        "data_notifica": data_notifica, "scadenza": scadenza,
        "scadenza_nota": "60 giorni dalla notifica, salvo festivita'",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"success": True, "scadenza": scadenza}


def _stesso_importo(totale: Optional[str], importo: Any) -> bool:
    try:
        return totale is not None and Decimal(str(totale)) == Decimal(str(importo)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return False


async def _applica_ricevuta(db, cartella: Dict[str, Any], ricevuta: Dict[str, Any], quota=None, dettaglio=None) -> str:
    importo = quota if quota is not None else ricevuta.get("operation_amount", ricevuta.get("importo"))
    if importo is None:
        return cartella.get("expectation_status")
    key = ":".join((str(ricevuta.get("identificativo_bolletta") or ricevuta.get("iuv") or ricevuta["id"]),
                    str(ricevuta.get("data_pagamento") or "")))
    pagamenti = [r for r in cartella.get("pagamenti_documentati", [])
                 if r.get("payment_key") != key and r.get("ricevuta_id") != ricevuta["id"]]
    pagamento = {"payment_key": key, "ricevuta_id": ricevuta["id"],
                 "importo": str(importo), "data_pagamento": ricevuta.get("data_pagamento")}
    # Il totale iniziale e' entro 60 giorni. Gli interessi successivi devono
    # essere espliciti nella quietanza della stessa cartella, mai dedotti
    # dalla sola differenza tra pagamento e dovuto.
    if dettaglio and dettaglio.get("quadra") is True:
        try:
            mora = Decimal(str(dettaglio.get("interessi_mora") or "0"))
            if mora > 0 and _stesso_importo(cartella.get("totale"), Decimal(str(importo)) - mora):
                pagamento["interessi_mora_documentati"] = str(mora)
        except (InvalidOperation, ValueError):
            pass
    pagamenti.append(pagamento)
    versato = sum((Decimal(str(r["importo"])) for r in pagamenti), Decimal("0"))
    mora = sum((Decimal(r.get("interessi_mora_documentati", "0")) for r in pagamenti), Decimal("0"))
    torna = _stesso_importo(cartella.get("totale"), versato - mora)
    ids = [r["ricevuta_id"] for r in pagamenti]
    campi = expectation_evidence_fields(satisfied=torna, evidence_ids=ids)
    await db[COLL].update_one({"id": cartella["id"]}, {"$set": {
        **campi, "ricevuta_id": ricevuta.get("id"), "pagamenti_documentati": pagamenti,
        "importo_pagato_documentale": str(versato),
        "interessi_mora_documentati": str(mora),
        "data_pagamento": ricevuta.get("data_pagamento"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    await db["ricevute_pagopa"].update_one({"id": ricevuta["id"]},
        {"$addToSet": {"cartelle_collegate": cartella["id"]}})
    return campi["expectation_status"]


def _forme_del_codice(codice: Any) -> List[str]:
    """Lo stesso pagamento citato come IUV (17 cifre) o come codice avviso (cifra iniziale + IUV).

    La ricevuta CBILL della banca riporta il codice avviso di 18 cifre
    («180071502664980543»), la cartella tiene lo IUV senza la cifra iniziale: sono lo
    stesso identificativo, e confrontarli per uguaglianza di stringa lasciava la cartella
    aperta anche dopo il pagamento. Resta testo (mai numero: lo zero iniziale conta).
    """
    testo = re.sub(r"\s+", "", str(codice or ""))
    if not testo.isdigit():
        return [testo] if testo else []
    forme = [testo]
    if len(testo) == 18:
        forme.append(testo[1:])
    return forme


async def chiudi_da_ricevuta(db, ricevuta: Dict[str, Any]) -> Optional[str]:
    """IUV oppure numero cartella esplicito e quota documentata; nessuna ripartizione stimata."""
    if ricevuta.get("duplicate_of") or ricevuta.get("is_payment_receipt") is False:
        return None
    documenti = ricevuta.get("documenti") or []
    if documenti and ricevuta.get("importi_quadrano") is not True:
        return None
    linked = set()
    result = None
    for doc in documenti:
        if not doc.get("numero") or doc.get("totale") is None or doc.get("quadra") is not True:
            continue
        ident = "cartella:" + re.sub(r"\W+", "", doc["numero"])
        cartella = await db[COLL].find_one({"id": ident}, {"_id": 0})
        if not cartella:
            continue
        debtor = ricevuta.get("codice_fiscale_debitore")
        if debtor and cartella.get("codice_fiscale_destinatario") and debtor != cartella["codice_fiscale_destinatario"]:
            continue
        result = await _applica_ricevuta(db, cartella, ricevuta, doc["totale"], dettaglio=doc)
        linked.add(cartella["id"])
    # Se il PDF contiene piu' quote non usare il totale dell'intera ricevuta
    # contro una singola cartella: fanno fede i dettagli sopra.
    if documenti:
        return result
    forme = _forme_del_codice(ricevuta.get("identificativo_bolletta") or ricevuta.get("iuv"))
    if not forme:
        return None
    cartelle = await db[COLL].find(
        {"$or": [{"iuv": {"$in": forme}}, {"codice_avviso": {"$in": forme}}]}, {"_id": 0}).to_list(10)
    if len(cartelle) != 1:
        return None
    return await _applica_ricevuta(db, cartelle[0], ricevuta)


async def chiudi_da_ricevuta_esistente(db, cartella_id: str) -> Optional[str]:
    """Cerca anche le attestazioni arrivate prima della cartella originale."""
    cartella = await db[COLL].find_one({"id": cartella_id}, {"_id": 0})
    if not cartella:
        return None
    forme = list(dict.fromkeys(_forme_del_codice(cartella.get("iuv")) + _forme_del_codice(cartella.get("codice_avviso"))))
    numero = re.sub(r"\W+", "", cartella.get("numero_cartella") or cartella_id.removeprefix("cartella:"))
    rows = await db["ricevute_pagopa"].find({"duplicate_of": {"$exists": False}, "$or": [
        {"identificativo_bolletta": {"$in": forme}}, {"iuv": {"$in": forme}},
        {"documenti.numero": numero},
    ]}, {"_id": 0, "pdf_data": 0}).to_list(100)
    result = None
    for row in rows:
        result = await chiudi_da_ricevuta(db, row) or result
    return result


async def contenuto(db, cartella_id: str) -> Optional[Tuple[bytes, str]]:
    """(byte, nome) dell'originale, o None."""
    doc = await db[COLL].find_one({"id": cartella_id}, {"_id": 0})
    if not doc:
        return None
    if doc.get("drive_file_id"):
        from app.services.drive_download import scarica_originale

        originale = await scarica_originale(str(doc["drive_file_id"]), md5=doc.get("drive_md5"))
        if originale:
            return originale, doc.get("nome") or f"cartella_{cartella_id[-12:]}.pdf"
    dati = doc.get("contenuto_b64")
    if not dati and doc.get("blob_key"):
        dati = await _archivio().get(doc["blob_key"])
    if not dati:
        return None
    return base64.b64decode(dati), doc.get("nome") or f"cartella_{cartella_id[-12:]}.pdf"
