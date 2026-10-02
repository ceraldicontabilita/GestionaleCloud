"""Proposte AI sui documenti che i lettori deterministici non riconoscono.

Decisione del titolare (02/10/2026): un agente per settore legge i file fermi
(ERRORI della cartella unica Drive, ``documents_inbox`` senza categoria) e
**propone** tipo, dati letti e candidato; il titolare conferma con un tocco e
ad applicare resta il motore deterministico esistente (lo smistatore di
Documenti > Import con ``tipo_rilevato_noto``). Qui non si scrive mai in
contabilita'.

Un solo client (``anthropic_llm_client.LlmChat``): timeout, ritentativi,
``usage`` per chiamata in ``agenti_ai_chiamate``, tetto giornaliero
``AGENTI_AI_TETTO_GIORNALIERO`` (giorno di Roma) e cache per impronta
SHA-256 del documento + versione del prompt. Si spegne con ``AGENTI_AI=false``;
senza ``ANTHROPIC_API_KEY`` non fa nulla e lo dice nello stato.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

COLL_PROPOSTE = "agenti_proposte"
COLL_CHIAMATE = "agenti_ai_chiamate"
SCOPO = "agenti_proposte"
CHIAVE_STATO = "agenti_proposte"
VERSIONE_PROMPT = 1
LOTTO = 10
TETTO_DEFAULT = 200
MAX_BYTE_DOCUMENTO = 20 * 1024 * 1024
MAX_CARATTERI_XML = 60_000

STATO_PROPOSTA, STATO_CONFERMATA, STATO_RIFIUTATA = "proposta", "confermata", "rifiutata"
CONFIDENZE = ("alta", "media", "bassa")
#: Motivi di rifiuto a chip (le mani sporche: niente testo libero, «altro» e' l'eccezione).
MOTIVI_RIFIUTO = ("tipo_sbagliato", "dati_sbagliati", "non_contabile", "doppione", "altro")

#: I tipi che lo smistatore di Documenti > Import sa consegnare a un lettore
#: (``rileva_tipo_documento``): una proposta fuori da questi non si applica.
TIPI_SMISTATORE = frozenset({
    "fattura", "corrispettivo", "corrispettivi_csv_ade", "f24", "quietanza_f24", "cedolino",
    "bonifici", "distinte_bpm", "estratto_conto", "estratto_conto_sumup", "spese_sumup",
    "verbale_codice_strada", "avviso_pagopa", "ricevuta_pagopa", "cartella_pagamento",
    "ricevuta_cbill", "ricevuta_mav", "ricevuta_rav", "ricevuta_bollettino_postale",
    "dichiarazione_fiscale", "atto_giudiziario", "dimissioni_telematiche", "nota_rettifica_inps",
    "report_fatture_ricevute", "pagamenti_buoni", "pos_terminal", "tari_avviso",
    "tari_istanza_compensazione", "ader_definizione_agevolata", "ader_sospensione",
    "anagrafica_clienti", "documento_identita", "visura_camerale", "archivio_zip",
})
NON_RICONOSCIUTO = "non_riconosciuto"

#: Settore di ogni tipo: uno per cruscotto. Il resto va in «altro».
SETTORE_DEL_TIPO = {
    "verbale_codice_strada": "verbali", "avviso_pagopa": "verbali", "ricevuta_pagopa": "verbali",
    "cedolino": "cedolini", "dimissioni_telematiche": "cedolini", "nota_rettifica_inps": "cedolini",
    "bonifici": "bonifici", "distinte_bpm": "bonifici", "estratto_conto": "bonifici",
    "estratto_conto_sumup": "bonifici", "spese_sumup": "bonifici",
    "fattura": "fatture", "report_fatture_ricevute": "fatture",
    "corrispettivo": "corrispettivi", "corrispettivi_csv_ade": "corrispettivi", "pos_terminal": "corrispettivi",
    "f24": "f24", "quietanza_f24": "f24", "dichiarazione_fiscale": "f24", "cartella_pagamento": "f24",
    "ricevuta_cbill": "f24", "tari_avviso": "f24", "tari_istanza_compensazione": "f24",
    "ader_definizione_agevolata": "f24", "ader_sospensione": "f24",
}
SETTORE_ALTRO = "altro"

_SISTEMA = (
    "Sei l'archivista contabile di una pasticceria italiana (societa' di capitali). Ti do un documento "
    "che i lettori automatici non hanno riconosciuto. Devi dire SOLO che documento e' e quali dati porta, "
    "senza inventare nulla: un dato che non leggi resta null. Rispondi con UN SOLO oggetto JSON, "
    "nessun altro testo, con esattamente queste chiavi:\n"
    '{"tipo_documento": "<uno dei tipi ammessi, oppure non_riconosciuto>", '
    '"campi": {"numero": null, "data": "AAAA-MM-GG o null", "importo_cents": null, '
    '"controparte": null, "partita_iva": null, "codice_fiscale": null, "periodo": null, '
    '"codici_tributo": [], "targa": null, "iuv": null, "dipendente": null, "note": null}, '
    '"confidenza": "alta|media|bassa", "prove": ["frase letterale del documento che prova il tipo", "..."], '
    '"motivo": "perche\' hai scelto questo tipo o perche\' non lo riconosci"}\n'
    "importo_cents e' l'importo totale in centesimi di euro (intero), mai un decimale. "
    "I codici tributo sono stringhe, mai numeri. confidenza alta solo se il tipo e' inequivocabile "
    "e i dati principali sono leggibili. Tipi ammessi: {tipi}."
)


def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


def oggi_roma() -> str:
    return datetime.now(ZoneInfo("Europe/Rome")).date().isoformat()


def attivo() -> bool:
    return os.getenv("AGENTI_AI", "true").strip().lower() not in ("false", "0", "no", "off")


def chiave_api() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "").strip()


def tetto_giornaliero() -> int:
    try:
        return max(0, int(os.getenv("AGENTI_AI_TETTO_GIORNALIERO", str(TETTO_DEFAULT))))
    except ValueError:
        return TETTO_DEFAULT


def settore_del_tipo(tipo: Any) -> str:
    return SETTORE_DEL_TIPO.get(str(tipo or ""), SETTORE_ALTRO)


def nuovo_client(client=None, db=None):
    """Il solo client ammesso: ``LlmChat``. Senza chiave torna None.

    ``registra=False``: il registro lo scrive questo modulo con i suoi campi
    (impronta, versione del prompt, proposta), con lo stesso scrittore unico."""
    if client is not None:
        return client
    chiave = chiave_api()
    if not chiave:
        return None
    from app.services.anthropic_llm_client import LlmChat, document_model_name

    return LlmChat(chiave, system_prompt=_SISTEMA.replace("{tipi}", ", ".join(sorted(TIPI_SMISTATORE))),
                   model=document_model_name(), scopo=SCOPO, db=db, registra=False)


# ---------------------------------------------------------------------------
# Tetto e registro delle chiamate
# ---------------------------------------------------------------------------

async def chiamate_oggi(db) -> int:
    from app.services.anthropic_llm_client import chiamate_oggi as _chiamate

    return await _chiamate(db, scopo=SCOPO)


async def _registra_chiamata(db, *, sha256: str, esito: str, usage: Optional[Dict[str, Any]],
                             modello: Optional[str], tentativi: int, errore: Optional[str],
                             proposta: Optional[Dict[str, Any]]) -> None:
    from app.services.anthropic_llm_client import registra_chiamata

    await registra_chiamata(db, scopo=SCOPO, esito=esito, usage=usage, modello=modello, tentativi=tentativi,
                            errore=errore, sha256=sha256, versione_prompt=VERSIONE_PROMPT, proposta=proposta)


async def _risposta_in_cache(db, sha256: str) -> Optional[Dict[str, Any]]:
    """La stessa impronta gia' letta con questa versione del prompt: nessuna seconda chiamata."""
    riga = await db[COLL_CHIAMATE].find_one(
        {"sha256": sha256, "versione_prompt": VERSIONE_PROMPT, "esito": "ok"},
        {"_id": 0, "proposta": 1})
    return riga.get("proposta") if riga and isinstance(riga.get("proposta"), dict) else None


# ---------------------------------------------------------------------------
# Lettura della risposta
# ---------------------------------------------------------------------------

def _json_oggetto(testo: str) -> Dict[str, Any]:
    testo = (testo or "").strip()
    testo = re.sub(r"^```(?:json)?\s*|\s*```$", "", testo)
    try:
        dato = json.loads(testo)
        if isinstance(dato, dict):
            return dato
    except json.JSONDecodeError:
        pass
    inizio, fine = testo.find("{"), testo.rfind("}")
    if inizio >= 0 and fine > inizio:
        try:
            dato = json.loads(testo[inizio:fine + 1])
            if isinstance(dato, dict):
                return dato
        except json.JSONDecodeError:
            pass
    return {}


def _cents(valore: Any) -> Optional[int]:
    if valore is None or isinstance(valore, bool):
        return None
    if isinstance(valore, int):
        return valore
    if isinstance(valore, float):
        return int(round(valore))
    testo = re.sub(r"[^\d-]", "", str(valore))
    return int(testo) if testo.lstrip("-").isdigit() else None


def valida_proposta(grezzo: Dict[str, Any]) -> Dict[str, Any]:
    """La struttura che si salva: tipo fra quelli ammessi, confidenza nota, campi puliti."""
    tipo = str(grezzo.get("tipo_documento") or NON_RICONOSCIUTO).strip().lower()
    if tipo not in TIPI_SMISTATORE:
        tipo = NON_RICONOSCIUTO
    confidenza = str(grezzo.get("confidenza") or "bassa").strip().lower()
    if confidenza not in CONFIDENZE or tipo == NON_RICONOSCIUTO:
        confidenza = "bassa"
    campi_grezzi = grezzo.get("campi") if isinstance(grezzo.get("campi"), dict) else {}
    campi: Dict[str, Any] = {}
    for chiave, valore in campi_grezzi.items():
        if valore in (None, "", [], {}):
            continue
        if chiave == "importo_cents":
            cents = _cents(valore)
            if cents is not None:
                campi[chiave] = cents
        elif chiave == "codici_tributo":
            codici = valore if isinstance(valore, list) else [valore]
            campi[chiave] = [str(c).strip() for c in codici if str(c).strip()]
        else:
            campi[chiave] = str(valore).strip()[:300]
    prove = grezzo.get("prove") if isinstance(grezzo.get("prove"), list) else []
    return {
        "tipo_documento": tipo,
        "campi": campi,
        "confidenza": confidenza,
        "prove": [str(p)[:300] for p in prove if str(p).strip()][:8],
        "motivo": str(grezzo.get("motivo") or "")[:500],
    }


# ---------------------------------------------------------------------------
# Candidati e lettura dei byte
# ---------------------------------------------------------------------------

_ESTENSIONI = (".pdf", ".xml", ".p7m", ".jpg", ".jpeg", ".png")


def _leggibile(nome: Any) -> bool:
    return str(nome or "").lower().endswith(_ESTENSIONI)


async def _impronte_gia_proposte(db) -> set:
    righe = await db[COLL_PROPOSTE].find(
        {"versione_prompt": VERSIONE_PROMPT},
        {"_id": 0, "documento.sha256": 1, "documento.drive_id": 1, "documento.inbox_id": 1}).to_list(None)
    chiavi = set()
    for r in righe:
        doc = r.get("documento") or {}
        for k in ("sha256", "drive_id", "inbox_id"):
            if doc.get(k):
                chiavi.add(f"{k}:{doc[k]}")
    return chiavi


async def candidati(db, limite: int = LOTTO) -> List[Dict[str, Any]]:
    """I file fermi senza una proposta: prima ERRORI della cartella unica, poi l'inbox."""
    from app.document_repository import metadata_projection
    from app.services.drive_cartella_unica import ERRORI, REGISTRO

    gia = await _impronte_gia_proposte(db)
    scelti: List[Dict[str, Any]] = []
    errori = await db[REGISTRO].find(
        {"cartella": ERRORI},
        {"_id": 0, "id": 1, "nome": 1, "sha256": 1, "tipo": 1, "motivo": 1, "aggiornato_il": 1},
    ).to_list(None)
    errori.sort(key=lambda r: str(r.get("aggiornato_il") or ""), reverse=True)
    for r in errori:
        if len(scelti) >= limite:
            break
        if not _leggibile(r.get("nome")):
            continue
        if f"drive_id:{r['id']}" in gia or (r.get("sha256") and f"sha256:{r['sha256']}" in gia):
            continue
        scelti.append({"origine": "drive", "drive_id": r["id"], "inbox_id": None, "nome": r.get("nome"),
                       "sha256": r.get("sha256"), "tipo_tentato": r.get("tipo"), "motivo_fermo": r.get("motivo")})
    if len(scelti) < limite:
        inbox = await db["documents_inbox"].find(
            {"$and": [
                {"$or": [{"categoria": None}, {"categoria": ""}, {"categoria": {"$exists": False}}]},
                {"processed": {"$ne": True}},
            ]},
            metadata_projection("documents_inbox", {"_id": 0, "id": 1, "filename": 1, "sha256": 1,
                                                    "file_hash": 1, "downloaded_at": 1}),
        ).to_list(None)
        inbox.sort(key=lambda r: str(r.get("downloaded_at") or ""), reverse=True)
        for r in inbox:
            if len(scelti) >= limite:
                break
            if not r.get("id") or not _leggibile(r.get("filename")):
                continue
            sha = r.get("sha256")
            if f"inbox_id:{r['id']}" in gia or (sha and f"sha256:{sha}" in gia):
                continue
            scelti.append({"origine": "inbox", "drive_id": None, "inbox_id": r["id"], "nome": r.get("filename"),
                           "sha256": sha, "tipo_tentato": None, "motivo_fermo": "inbox senza categoria"})
    return scelti


async def leggi_byte(db, candidato: Dict[str, Any]) -> bytes:
    if candidato["origine"] == "drive":
        from app.services.drive_download import scarica_originale

        return await scarica_originale(candidato["drive_id"])
    riga = await db["documents_inbox"].find_one({"id": candidato["inbox_id"]}, {"_id": 0, "pdf_data": 1})
    dato = (riga or {}).get("pdf_data")
    if isinstance(dato, bytes):
        return dato
    if isinstance(dato, str) and dato:
        return base64.b64decode(dato)
    raise ValueError("documento dell'inbox senza contenuto (pdf_data vuoto)")


def _messaggio(nome: str, contenuto: bytes):
    from app.services.anthropic_llm_client import FileContentWithMimeType, ImageContent, UserMessage

    basso = (nome or "").lower()
    testo = f'Nome del file: «{nome}». Rispondi con il solo JSON.'
    if basso.endswith(".pdf"):
        return UserMessage(content=testo, files=[FileContentWithMimeType(
            file_data=base64.b64encode(contenuto).decode("ascii"), mime_type="application/pdf")])
    if basso.endswith((".jpg", ".jpeg", ".png")):
        mime = "image/png" if basso.endswith(".png") else "image/jpeg"
        return UserMessage(content=testo, images=[ImageContent(
            image_data=base64.b64encode(contenuto).decode("ascii"), mime_type=mime)])
    if basso.endswith(".p7m"):
        from app.services.xml_invoice_processor import extract_xml_from_p7m

        contenuto = extract_xml_from_p7m(contenuto) or contenuto
    xml = contenuto.decode("utf-8", errors="replace")[:MAX_CARATTERI_XML]
    return UserMessage(content=f"{testo}\n\nContenuto del file:\n{xml}")


# ---------------------------------------------------------------------------
# Il giro
# ---------------------------------------------------------------------------

async def _salva_stato(db, esito: Dict[str, Any]) -> None:
    try:
        await db["sistema_stato"].update_one(
            {"chiave": CHIAVE_STATO},
            {"$set": {"chiave": CHIAVE_STATO, "ultimo_giro": esito.get("eseguito_at"), "esito": esito,
                      "updated_at": _adesso()}},
            upsert=True,
        )
    except Exception as exc:  # noqa: BLE001 - l'esito e' comunque nel log
        logger.warning("[agenti-proposte] stato non salvato: %s: %s", type(exc).__name__, exc)


async def stato(db) -> Dict[str, Any]:
    """Per il cruscotto: acceso, chiave, tetto, chiamate di oggi, ultimo giro."""
    riga = await db["sistema_stato"].find_one({"chiave": CHIAVE_STATO}, {"_id": 0}) or {}
    return {
        "attivo": attivo(), "chiave_presente": bool(chiave_api()), "tetto": tetto_giornaliero(),
        "chiamate_oggi": await chiamate_oggi(db), "versione_prompt": VERSIONE_PROMPT,
        "ultimo_giro": riga.get("ultimo_giro"), "ultimo_esito": riga.get("esito"),
    }


async def giro(db, *, client=None, limite: int = LOTTO) -> Dict[str, Any]:
    """Un lotto di file fermi: una proposta per file, mai un'applicazione.

    Spento (``AGENTI_AI=false``) o senza chiave: nessuna lettura, e lo stato lo
    dice. Il tetto giornaliero conta le chiamate vere (la cache non costa).
    """
    esito: Dict[str, Any] = {"eseguito_at": _adesso(), "candidati": 0, "proposte": 0, "da_cache": 0,
                             "chiamate": 0, "errori": 0, "saltati_tetto": 0}
    if not attivo():
        esito["motivo"] = "spento (AGENTI_AI=false)"
        await _salva_stato(db, esito)
        return esito
    client = nuovo_client(client, db)
    if client is None:
        esito["motivo"] = "ANTHROPIC_API_KEY non configurata"
        await _salva_stato(db, esito)
        return esito
    tetto = tetto_giornaliero()
    for cand in await candidati(db, limite):
        esito["candidati"] += 1
        try:
            contenuto = await leggi_byte(db, cand)
        except Exception as exc:  # noqa: BLE001 - il file resta fermo, si riprova al giro dopo
            esito["errori"] += 1
            esito["ultimo_errore"] = f"{cand.get('nome')}: {type(exc).__name__}: {exc}"[:300]
            logger.warning("[agenti-proposte] %s non letto: %s: %s", cand.get("nome"), type(exc).__name__, exc)
            continue
        if len(contenuto) > MAX_BYTE_DOCUMENTO:
            esito["errori"] += 1
            esito["ultimo_errore"] = f"{cand.get('nome')}: oltre {MAX_BYTE_DOCUMENTO // (1024 * 1024)} MB"
            continue
        sha256 = hashlib.sha256(contenuto).hexdigest()
        cand["sha256"] = sha256
        proposta = await _risposta_in_cache(db, sha256)
        usage = modello = None
        tentativi = 0
        if proposta is not None:
            esito["da_cache"] += 1
        else:
            if await chiamate_oggi(db) >= tetto:
                esito["saltati_tetto"] += 1
                esito["motivo"] = f"tetto giornaliero raggiunto ({tetto})"
                break
            try:
                risposta = await client.send_message_con_usage(_messaggio(cand.get("nome") or "", contenuto))
            except Exception as exc:  # noqa: BLE001 - la chiamata si registra fallita e si riprova al giro dopo
                esito["chiamate"] += 1
                esito["errori"] += 1
                esito["ultimo_errore"] = f"{cand.get('nome')}: {type(exc).__name__}: {exc}"[:300]
                await _registra_chiamata(db, sha256=sha256, esito="errore", usage=None, modello=None,
                                         tentativi=0, errore=esito["ultimo_errore"], proposta=None)
                logger.warning("[agenti-proposte] lettura AI fallita per %s: %s: %s",
                               cand.get("nome"), type(exc).__name__, exc)
                continue
            esito["chiamate"] += 1
            usage, modello, tentativi = risposta.get("usage"), risposta.get("modello"), int(risposta.get("tentativi") or 1)
            proposta = valida_proposta(_json_oggetto(risposta.get("testo") or ""))
            await _registra_chiamata(db, sha256=sha256, esito="ok", usage=usage, modello=modello,
                                     tentativi=tentativi, errore=None, proposta=proposta)
        await db[COLL_PROPOSTE].insert_one({
            "id": f"prop_{uuid.uuid4().hex[:12]}",
            "settore": settore_del_tipo(proposta["tipo_documento"]),
            "documento": {"origine": cand["origine"], "drive_id": cand.get("drive_id"),
                          "inbox_id": cand.get("inbox_id"), "nome": cand.get("nome"), "sha256": sha256,
                          "tipo_tentato": cand.get("tipo_tentato"), "motivo_fermo": cand.get("motivo_fermo")},
            "proposta": proposta, "confidenza": proposta["confidenza"],
            "stato": STATO_PROPOSTA, "creato": _adesso(), "deciso_da": None, "deciso_il": None,
            "versione_prompt": VERSIONE_PROMPT, "modello": modello, "usage": usage,
        })
        esito["proposte"] += 1
    esito["chiamate_oggi"] = await chiamate_oggi(db)
    await _salva_stato(db, esito)
    return esito


# ---------------------------------------------------------------------------
# Elenco, conferma, rifiuto
# ---------------------------------------------------------------------------

async def elenco(db, *, settore: Optional[str] = None, stato_filtro: Optional[str] = STATO_PROPOSTA,
                 limite: int = 200) -> List[Dict[str, Any]]:
    filtro: Dict[str, Any] = {}
    if settore:
        filtro["settore"] = settore
    if stato_filtro:
        filtro["stato"] = stato_filtro
    righe = await db[COLL_PROPOSTE].find(filtro, {"_id": 0}).to_list(None)
    righe.sort(key=lambda r: str(r.get("creato") or ""), reverse=True)
    return righe[:limite]


async def conteggio_in_attesa(db) -> Dict[str, int]:
    """Proposte aperte per settore (proiezione senza payload: il documento e' solo riferimenti)."""
    righe = await db[COLL_PROPOSTE].find({"stato": STATO_PROPOSTA}, {"_id": 0, "settore": 1}).to_list(None)
    conteggi: Dict[str, int] = {}
    for r in righe:
        conteggi[r.get("settore") or SETTORE_ALTRO] = conteggi.get(r.get("settore") or SETTORE_ALTRO, 0) + 1
    return conteggi


class PropostaNonTrovata(LookupError):
    pass


class PropostaNonApplicabile(ValueError):
    pass


async def _applica_inbox(db, proposta: Dict[str, Any], tipo: str, utente: str) -> Dict[str, Any]:
    """L'inbox: il file passa allo smistatore col tipo deciso; la riga riceve la categoria come la classificazione esistente."""
    from fastapi import HTTPException

    from app.routers.documenti import upload_documento_automatico
    from app.services.drive_cartella_unica import FileCaricato

    doc = proposta["documento"]
    contenuto = await leggi_byte(db, {"origine": "inbox", "inbox_id": doc["inbox_id"]})
    contesto = {"channel": "documents_inbox", "inbox_id": doc["inbox_id"], "source_sha256": doc.get("sha256"),
                "tipo_deciso_da": utente}
    try:
        risultato = await upload_documento_automatico(file=FileCaricato(doc.get("nome") or "documento", contenuto,
                                                                         contesto, tipo))
    except HTTPException as exc:
        return {"success": False, "message": str(exc.detail), "http_status": exc.status_code}
    ok = bool(risultato.get("success") or risultato.get("duplicate"))
    if ok:
        await db["documents_inbox"].update_one({"id": doc["inbox_id"]}, {"$set": {
            "categoria": tipo, "auto_classified_at": _adesso(), "classificato_da": utente,
            "agente_proposta_id": proposta["id"], "processed": True,
            "status": "elaborato" if risultato.get("success") else "duplicato",
        }})
    return {"success": ok, "message": risultato.get("message"), "duplicate": bool(risultato.get("duplicate")),
            "tipo_rilevato": risultato.get("tipo_rilevato")}


async def conferma(db, proposta_id: str, utente: str) -> Dict[str, Any]:
    """Applica attraverso il motore del tipo proposto. Una proposta gia' decisa non si riapplica."""
    from app.services.audit_logger import log_evento

    proposta = await db[COLL_PROPOSTE].find_one({"id": proposta_id}, {"_id": 0})
    if not proposta:
        raise PropostaNonTrovata(proposta_id)
    if proposta.get("stato") != STATO_PROPOSTA:
        return {"proposta": proposta, "gia_decisa": True, "esito": proposta.get("esito_applicazione")}
    tipo = (proposta.get("proposta") or {}).get("tipo_documento")
    if tipo not in TIPI_SMISTATORE:
        raise PropostaNonApplicabile(f"tipo «{tipo}» non e' fra quelli dello smistatore")
    doc = proposta.get("documento") or {}
    if doc.get("origine") == "drive" and doc.get("drive_id"):
        from app.services.drive_cartella_unica import rielabora_con_tipo

        esito = await rielabora_con_tipo(db, doc["drive_id"], tipo, deciso_da=utente)
    elif doc.get("origine") == "inbox" and doc.get("inbox_id"):
        esito = await _applica_inbox(db, proposta, tipo, utente)
    else:
        raise PropostaNonApplicabile("documento senza origine Drive ne' inbox")
    adesso = _adesso()
    campi: Dict[str, Any] = {"esito_applicazione": {**esito, "applicata_il": adesso}}
    if esito.get("success"):
        campi.update({"stato": STATO_CONFERMATA, "deciso_da": utente, "deciso_il": adesso})
    await db[COLL_PROPOSTE].update_one({"id": proposta_id}, {"$set": campi})
    await log_evento(modulo="agenti", azione="proposta_confermata" if esito.get("success") else "proposta_non_applicata",
                     entita_id=proposta_id, entita_collection=COLL_PROPOSTE, db=db,
                     vecchio_stato={"stato": STATO_PROPOSTA},
                     nuovo_stato={"stato": campi.get("stato", STATO_PROPOSTA), "tipo": tipo},
                     fonte="agenti_proposte", utente=utente,
                     dettaglio=str(esito.get("message") or esito.get("motivo") or "")[:300])
    aggiornata = await db[COLL_PROPOSTE].find_one({"id": proposta_id}, {"_id": 0})
    return {"proposta": aggiornata, "gia_decisa": False, "esito": esito}


async def rifiuta(db, proposta_id: str, utente: str, motivo: str, nota: str = "") -> Dict[str, Any]:
    from app.services.audit_logger import log_evento

    if motivo not in MOTIVI_RIFIUTO:
        raise PropostaNonApplicabile(f"motivo «{motivo}» non ammesso: {', '.join(MOTIVI_RIFIUTO)}")
    proposta = await db[COLL_PROPOSTE].find_one({"id": proposta_id}, {"_id": 0})
    if not proposta:
        raise PropostaNonTrovata(proposta_id)
    if proposta.get("stato") != STATO_PROPOSTA:
        return {"proposta": proposta, "gia_decisa": True}
    adesso = _adesso()
    await db[COLL_PROPOSTE].update_one({"id": proposta_id}, {"$set": {
        "stato": STATO_RIFIUTATA, "deciso_da": utente, "deciso_il": adesso,
        "rifiuto": {"motivo": motivo, "nota": (nota or "")[:300]},
    }})
    await log_evento(modulo="agenti", azione="proposta_rifiutata", entita_id=proposta_id,
                     entita_collection=COLL_PROPOSTE, db=db, vecchio_stato={"stato": STATO_PROPOSTA},
                     nuovo_stato={"stato": STATO_RIFIUTATA, "motivo": motivo}, fonte="agenti_proposte",
                     utente=utente, dettaglio=(nota or "")[:300])
    aggiornata = await db[COLL_PROPOSTE].find_one({"id": proposta_id}, {"_id": 0})
    return {"proposta": aggiornata, "gia_decisa": False}


async def conferma_sicure(db, utente: str, *, settore: Optional[str] = None) -> Dict[str, Any]:
    """«Conferma tutte le sicure»: solo confidenza alta, una per una, col motore di ciascuna."""
    aperte = await elenco(db, settore=settore, stato_filtro=STATO_PROPOSTA, limite=10_000)
    esito: Dict[str, Any] = {"candidate": 0, "confermate": 0, "non_applicate": 0, "dettagli": []}
    for p in aperte:
        if p.get("confidenza") != "alta":
            continue
        esito["candidate"] += 1
        try:
            r = await conferma(db, p["id"], utente)
        except PropostaNonApplicabile as exc:
            esito["non_applicate"] += 1
            esito["dettagli"].append({"id": p["id"], "esito": "non_applicabile", "motivo": str(exc)})
            continue
        ok = bool((r.get("esito") or {}).get("success"))
        esito["confermate" if ok else "non_applicate"] += 1
        esito["dettagli"].append({"id": p["id"], "esito": "confermata" if ok else "non_applicata",
                                  "motivo": (r.get("esito") or {}).get("message") or (r.get("esito") or {}).get("motivo")})
    return esito
