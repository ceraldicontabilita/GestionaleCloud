"""Le LIPE lette finiscono in una collezione sola, `lipe_periodi`.

Una riga per periodo (`YYYY-MM`), con i righi del quadro VP e la provenienza.
Il confronto col gestionale legge solo da qui: il PDF resta su Drive, non si
riparsa a ogni domanda.

**Un periodo che non quadra non entra.** `lipe_parser.quadra()` verifica
l'aritmetica del modulo; se non torna, la lettura non e' affidabile e la riga
viene contata fra gli scarti invece di diventare una fonte fiscale.

**Una LIPE piu' recente sostituisce la precedente sullo stesso periodo.** Una
comunicazione si puo' correggere e ritrasmettere: vince quella con il
protocollo piu' alto, e la precedente resta nello storico della riga.
"""
import asyncio
import logging
import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.constants.canale_documento import STATO_LIPE_CANONICA, canale_obbligatorio
from app.services.lipe_parser import parse_lipe, CAMPI_VP

logger = logging.getLogger(__name__)

__all__ = [
    "COLL_LIPE",
    "protocollo_da_nome",
    "e_una_lipe",
    "deposita_lipe",
    "importa_lipe_archiviate",
]

COLL_LIPE = "lipe_periodi"
COLL_INBOX = "documents_inbox"

_NOME_LIPE = re.compile(r"lipe", re.IGNORECASE)
# Nomi veri: `LIPE_2026_407141844.pdf` e, dal Cassetto Fiscale 2021-2025,
# `LIPE_2024_Itrim_358048737.pdf` / `LIPE_2022_IItrim_322737558.pdf`: il
# trimestre sta fra anno e protocollo. `LIPE_2026_T1.pdf` non ha protocollo.
_PROTOCOLLO = re.compile(
    r"LIPE[_\- ]*(\d{4})[_\- ]*(?:[IV]+\s*trim[_\- ]*)?(\d+)", re.IGNORECASE,
)


def e_una_lipe(nome_file: Optional[str]) -> bool:
    return bool(nome_file) and bool(_NOME_LIPE.search(nome_file))


def protocollo_da_nome(nome_file: Optional[str]) -> Optional[int]:
    """Il numero di protocollo in `LIPE_2026_407141844.pdf`.

    Serve a decidere quale comunicazione vince su un periodo gia' presente:
    una ritrasmissione ha protocollo piu' alto.
    """
    trovato = _PROTOCOLLO.search(nome_file or "")
    return int(trovato.group(2)) if trovato else None


def _nome_documento(doc: Dict[str, Any]) -> str:
    """In archivio il nome del file sta sotto chiavi diverse a seconda della
    collezione: `documents_inbox` usa `filename`, altri `file_name`."""
    for chiave in ("filename", "file_name", "nome_file"):
        valore = doc.get(chiave)
        if valore:
            return str(valore)
    return ""


async def deposita_lipe(
    db, pdf_bytes: bytes, *, nome_file: str, origine: str,
    drive_file_id: Optional[str] = None, dry_run: bool = False,
    source_document_id: Optional[str] = None,
    data_presentazione: Optional[str] = None, riferimento_cassetto: Optional[str] = None,
) -> Dict[str, Any]:
    """Legge una LIPE e deposita i suoi periodi. Idempotente per periodo."""
    letto = await asyncio.to_thread(parse_lipe, pdf_bytes)
    protocollo = protocollo_da_nome(nome_file)
    ora = datetime.now(timezone.utc).isoformat()
    if data_presentazione:
        from datetime import date
        data_presentazione = date.fromisoformat(data_presentazione).isoformat()

    depositati: List[str] = []
    scartati: List[Dict[str, Any]] = []
    ignorati: List[str] = []
    fonti_aggiunte: List[str] = []
    conflitti: List[str] = []

    for periodo_letto in letto["periodi"]:
        periodo = periodo_letto.get("periodo")
        if not periodo:
            scartati.append({"pagina": periodo_letto.get("pagina"),
                             "motivo": "periodo non riconosciuto"})
            continue
        if not periodo_letto.get("quadratura_ok"):
            scartati.append({"periodo": periodo, "motivo": "l'aritmetica del modulo non torna"})
            continue

        esistente = await db[COLL_LIPE].find_one({"periodo": periodo}, {"_id": 0})
        if esistente and (letto.get('parse_method') == 'cassetto_testuale' or protocollo is None):
            # An export ID or commitment date cannot rank filing revisions.
            fields = [*CAMPI_VP.values(), 'iva_dovuta_o_credito_segno', 'iva_da_versare_o_credito_segno']
            same = all(esistente.get(field) == periodo_letto.get(field) for field in fields)
            digest = hashlib.sha256(pdf_bytes).hexdigest()
            alternatives = list(esistente.get('fonti_alternative') or [])
            source = {**{k: v for k, v in periodo_letto.items() if k != 'pagina'},
                      'nome_file': nome_file, 'source_sha256': digest, 'source_page': periodo_letto.get('pagina'),
                      'source_document_id': source_document_id, 'drive_file_id': drive_file_id,
                      'coerente_con_vigente': same, 'data_presentazione': data_presentazione,
                      'data_presentazione_fonte': 'conferma_titolare' if data_presentazione else None,
                      'riferimento_cassetto': riferimento_cassetto}
            if data_presentazione:
                alternatives = [source if a.get('source_sha256') == digest else a for a in alternatives]
            old_date = esistente.get('data_presentazione')
            if same and data_presentazione:
                if not esistente.get('source_document_id') and source_document_id and esistente.get('source_sha256') != digest:
                    previous_source = {k: v for k, v in esistente.items() if k not in {'fonti_alternative', '_id', 'id'}}
                    if not any(a.get('source_sha256') == previous_source.get('source_sha256') for a in alternatives):
                        alternatives.append(previous_source)
                latest = max(data_presentazione, old_date or data_presentazione)
                differing = [a for a in alternatives if any(a.get(field) != esistente.get(field) for field in fields)]
                unresolved = any(not a.get('data_presentazione') or a['data_presentazione'] >= latest for a in differing)
                if digest != esistente.get('source_sha256') and not any(a.get('source_sha256') == digest for a in alternatives):
                    alternatives.append(source)
                if not dry_run:
                    await db[COLL_LIPE].update_one({'periodo': periodo}, {'$set': {
                        'fonti_alternative': alternatives, 'data_presentazione': latest,
                        'data_presentazione_fonte': 'conferma_titolare',
                        'data_presentazione_source_sha256': digest, 'riferimento_cassetto': riferimento_cassetto,
                        'conflitto_fonti': unresolved,
                        **({'source_document_id': source_document_id, 'source_sha256': digest,
                            'drive_file_id': drive_file_id, 'source_page': periodo_letto.get('pagina'),
                            'nome_file': nome_file} if not esistente.get('source_document_id') and source_document_id else {}),
                    }})
                fonti_aggiunte.append(periodo)
                if unresolved: conflitti.append(periodo)
                continue
            if not same and data_presentazione and old_date and data_presentazione != old_date:
                if data_presentazione > old_date:
                    old_source = {k: v for k, v in esistente.items() if k not in {'fonti_alternative', '_id', 'id'}}
                    alternatives = [a for a in alternatives if a.get('source_sha256') != digest]
                    if not any(a.get('source_sha256') == old_source.get('source_sha256') for a in alternatives):
                        alternatives.append(old_source)
                    row = {**source, 'anno': letto.get('anno'), 'origine': origine,
                           'protocollo': protocollo, 'stato': STATO_LIPE_CANONICA,
                           'canale': canale_obbligatorio(origine, drive_file_id=drive_file_id),
                           'fonti_alternative': alternatives, 'conflitto_fonti': False,
                           'aggiornato_at': ora, 'criterio_versione': 'data_presentazione_successiva'}
                    if not dry_run:
                        await db[COLL_LIPE].update_one({'periodo': periodo}, {'$set': row})
                    depositati.append(periodo)
                    continue
                source['superata_per_data_presentazione'] = True
            if digest != esistente.get('source_sha256') and not any(a.get('source_sha256') == digest for a in alternatives):
                alternatives.append(source)
                if not dry_run:
                    await db[COLL_LIPE].update_one({'periodo': periodo}, {'$set': {
                        'fonti_alternative': alternatives, 'conflitto_fonti': bool(esistente.get('conflitto_fonti')) or (not same and not source.get('superata_per_data_presentazione')),
                    }})
            fonti_aggiunte.append(periodo)
            if not same:
                conflitti.append(periodo)
            continue
        if esistente:
            vecchio = esistente.get("protocollo")
            if protocollo is not None and vecchio is not None and protocollo < vecchio:
                ignorati.append(periodo)
                continue

        # Una ritrasmissione sostituisce la precedente sullo stesso periodo:
        # la riga resta una, e ricorda quali protocolli ha sostituito.
        sostituisce = list((esistente or {}).get("sostituisce") or [])
        vecchio_protocollo = (esistente or {}).get("protocollo")
        if esistente and vecchio_protocollo is not None and vecchio_protocollo != protocollo:
            sostituisce.append(vecchio_protocollo)
        riga = {
            **{k: v for k, v in periodo_letto.items() if k != "pagina"},
            "periodo": periodo,
            "anno": letto.get("anno"),
            "protocollo": protocollo,
            "nome_file": nome_file,
            "drive_file_id": drive_file_id,
            "source_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "source_document_id": source_document_id,
            "source_page": periodo_letto.get("pagina"),
            "origine": origine,
            "canale": canale_obbligatorio(origine, drive_file_id=drive_file_id),
            "stato": STATO_LIPE_CANONICA,
            "sostituisce": sostituisce,
            "aggiornato_at": ora,
            "data_presentazione": data_presentazione,
            "data_presentazione_fonte": "conferma_titolare" if data_presentazione else None,
            "riferimento_cassetto": riferimento_cassetto,
        }
        if not dry_run:
            await db[COLL_LIPE].update_one(
                {"periodo": periodo}, {"$set": riga}, upsert=True,
            )
        depositati.append(periodo)

    return {
        "dry_run": dry_run,
        "nome_file": nome_file,
        "anno": letto.get("anno"),
        "protocollo": protocollo,
        "periodi_letti": letto["periodi_letti"],
        "depositati": depositati,
        "ignorati_perche_superati": ignorati,
        "scartati": scartati,
        "fonti_aggiunte": fonti_aggiunte,
        "periodi_con_fonti_discordanti": conflitti,
    }


def _servizio_drive():
    """La credenziale provata sulla cartella unica, dove stanno le LIPE."""
    from app.services import drive_cartella_unica as cu

    return cu._service()


def _lipe_nella_cartella_unica() -> List[Dict[str, str]]:
    """Le LIPE in «DATI SOCIETA CERALDI»: radice, DA ELABORARE ed ELABORATE.

    E' qui che arrivano dal 25/09: l'inventario di `documents_inbox` ha solo
    le LIPE 2020-2023 e senza id Drive, quindi da solo non ne trovava nessuna.
    Le copie marcate «DUPLICATO DA ELIMINARE» si saltano; fra copie con la
    stessa impronta Drive se ne legge una.
    """
    from app.services import drive_cartella_unica as cu

    root = cu.radice()
    if not root:
        return []
    service = _servizio_drive()
    cartelle = cu._cartelle(service, root)
    filtro_marcati = "".join(
        f" and not name contains '{p.strip()}'" for p in cu.PREFISSI_DA_ELIMINARE
    )
    trovate: Dict[str, Dict[str, str]] = {}
    for parent in (root, cartelle[cu.INBOX], cartelle[cu.ARCHIVIO]):
        token = None
        while True:
            risposta = service.files().list(
                q=(f"'{parent}' in parents and trashed = false and name contains 'LIPE'"
                   f" and mimeType = 'application/pdf'{filtro_marcati}"),
                fields="nextPageToken, files(id, name, md5Checksum)", pageSize=1000,
                pageToken=token, supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            for f in risposta.get("files", []):
                trovate.setdefault(f.get("md5Checksum") or f["id"], {"nome": f["name"], "id": f["id"]})
            token = risposta.get("nextPageToken")
            if not token:
                break
    return list(trovate.values())


async def importa_lipe_archiviate(db, *, dry_run: bool = True) -> Dict[str, Any]:
    """Rilegge le LIPE archiviate e ne deposita i periodi.

    Le cerca nella cartella unica su Drive e, per lo storico, fra quelle
    inventariate in `documents_inbox` con un id Drive. I PDF non stanno nel
    gestionale: ognuno si riscarica al momento.
    """
    from app.services.drive_download import scarica_bytes

    candidati: Dict[str, str] = {}
    async for doc in db[COLL_INBOX].find({}, {"_id": 0}):
        nome = _nome_documento(doc)
        if e_una_lipe(nome) and doc.get("drive_file_id"):
            candidati[str(doc["drive_file_id"])] = nome

    errori: List[Dict[str, str]] = []
    try:
        for f in await asyncio.to_thread(_lipe_nella_cartella_unica):
            candidati.setdefault(f["id"], f["nome"])
    except Exception as exc:  # noqa: BLE001 — si riporta, non si nasconde
        logger.error("LIPE: cartella unica non leggibile: %s: %s", type(exc).__name__, exc)
        errori.append({"file": "cartella unica", "errore": f"{type(exc).__name__}: {exc}"[:200]})

    # Le piu' recenti per ultime: cosi' una ritrasmissione sovrascrive.
    ordinati = sorted(candidati.items(), key=lambda c: protocollo_da_nome(c[1]) or 0)

    esiti: List[Dict[str, Any]] = []
    service = None
    for file_id, nome in ordinati:
        try:
            if service is None:
                service = _servizio_drive()
            contenuto = await asyncio.to_thread(scarica_bytes, service, file_id)
            esiti.append(await deposita_lipe(
                db, contenuto, nome_file=nome, origine="drive",
                drive_file_id=file_id, dry_run=dry_run,
            ))
        except Exception as exc:  # noqa: BLE001 — l'esito va riportato, non nascosto
            logger.exception("LIPE non leggibile: %s", nome)
            errori.append({"file": nome, "errore": f"{type(exc).__name__}: {exc}"[:200]})

    depositati = sorted({p for e in esiti for p in e["depositati"]})
    return {
        "dry_run": dry_run,
        "lipe_trovate": len(ordinati),
        "lipe_lette": len(esiti),
        "periodi_depositati": depositati,
        "periodi_scartati": [s for e in esiti for s in e["scartati"]],
        "errori": errori,
    }
