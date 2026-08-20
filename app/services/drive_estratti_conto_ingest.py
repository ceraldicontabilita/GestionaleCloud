"""Import automatico ricorsivo dell'area Drive ``Estratti conto``.

Usa esattamente l'endpoint/pipeline dell'import manuale, quindi deduplica,
riconciliazione, assegni e Prima Nota non possono divergere tra i due canali.

La cartella reale contiene fonti diverse (BNL, BPM, carte e POS). Ogni fonte
mantiene il proprio ciclo ``Da elaborare``/``Elaborate``/``Errori``; gli
archivi non vengono mai risaliti dal job. I file POS sono instradati al
motore delle chiusure giornaliere e non diventano falsi movimenti bancari.
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.services import classificazione_estratti
from app.services.drive_invoice_ingest import (
    _download_bytes,
    _get_or_create_inbox_folder,
    _get_or_create_elaborate_folder,
    _get_or_create_error_folder,
    _load_credentials,
    _move_to_folder,
    _move_to_elaborate,
)

logger = logging.getLogger(__name__)
_STATO_KEY = "drive_estratti_conto_last_sync"
_IMPORT_REGISTRY = "drive_estratti_conto_imports"
_sync_lock = asyncio.Lock()
_FOLDER_MIME = "application/vnd.google-apps.folder"
_LIFECYCLE_NAMES = {"da elaborare", "elaborate", "errori", "duplicati"}


def _batch_size() -> int:
    """Numero massimo di documenti lavorati per ciclo, con limite sicuro."""
    try:
        configured = int(settings.DRIVE_ESTRATTI_BATCH_SIZE)
    except (TypeError, ValueError):
        configured = 1
    return max(1, min(configured, 25))


def _select_batch(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return list(files[:_batch_size()])


def _folder_id() -> Optional[str]:
    ids = _folder_ids()
    return ids[0] if ids else None


def _split_folder_ids(raw: Optional[str]) -> List[str]:
    value = str(raw or "").strip()
    if not value:
        return []
    if value.startswith("["):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            parsed = []
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [part for part in re.split(r"[\s,;]+", value) if part]


def _registry_folder_ids() -> List[str]:
    """Legge eventuali radici aggiuntive dal registro Drive senza esporle."""
    raw = str(settings.DRIVE_FOLDER_REGISTRY_JSON or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return []
    entries = payload.get("folders", []) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    result: List[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        area = re.sub(r"[^a-z0-9]+", "_", str(entry.get("area") or "").lower()).strip("_")
        group = re.sub(r"[^a-z0-9]+", "_", str(entry.get("group") or entry.get("parent_area") or "").lower()).strip("_")
        if area == "estratti_conto" or area.startswith("estratti_conto_") or group == "estratti_conto":
            folder_id = str(entry.get("folder_id") or "").strip()
            if folder_id:
                result.append(folder_id)
    return result


def _registry_nexi_folder_ids() -> List[str]:
    raw = str(settings.DRIVE_FOLDER_REGISTRY_JSON or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return []
    entries = payload.get("folders", []) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    result: List[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        area = re.sub(r"[^a-z0-9]+", "_", str(entry.get("area") or "").lower()).strip("_")
        if area in {"carte", "nexi", "carta_nexi", "estratti_conto_carte"}:
            folder_id = str(entry.get("folder_id") or "").strip()
            if folder_id:
                result.append(folder_id)
    return result


def _nexi_folder_ids() -> List[str]:
    values = [settings.DRIVE_CARTE_FOLDER_ID, *_registry_nexi_folder_ids()]
    return list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


def _folder_ids() -> List[str]:
    values: List[str] = []
    for raw in (settings.GOOGLE_DRIVE_ESTRATTI_FOLDER_IDS,):
        values.extend(_split_folder_ids(raw))
    values.extend(filter(None, (settings.GOOGLE_DRIVE_ESTRATTI_FOLDER_ID,)))
    values.extend(_registry_folder_ids())
    values.extend(_nexi_folder_ids())
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _load_credentials_estratti():
    if settings.GOOGLE_SERVICE_ACCOUNT_JSON_ESTRATTI_CONTO:
        try:
            from google.oauth2 import service_account
            from app.services.drive_invoice_ingest import _parse_sa_json, _SCOPES
            info = _parse_sa_json(settings.GOOGLE_SERVICE_ACCOUNT_JSON_ESTRATTI_CONTO)
            return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES), None
        except Exception as exc:
            return None, f"GOOGLE_SERVICE_ACCOUNT_JSON_ESTRATTI_CONTO non valido: {exc}"
    return _load_credentials()


def is_configured() -> bool:
    return bool(
        settings.ENABLE_DRIVE_ESTRATTI_CONTO_SYNC
        and _folder_ids()
        and (settings.GOOGLE_SERVICE_ACCOUNT_JSON_ESTRATTI_CONTO
             or settings.GOOGLE_DRIVE_SA_FILE or settings.GOOGLE_DRIVE_SA_JSON
             or settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON)
    )


def _build_drive_service():
    if not is_configured():
        return None
    creds, err = _load_credentials_estratti()
    if creds is None:
        logger.error("Drive estratti conto: %s", err)
        return None
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _list_children(service, parent_id: str) -> List[Dict[str, Any]]:
    query = f"'{parent_id}' in parents and trashed = false"
    out: List[Dict[str, Any]] = []
    page_token = None
    while True:
        result = service.files().list(
            q=query, fields="nextPageToken, files(id, name, mimeType)",
            pageSize=100, pageToken=page_token,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        out.extend(result.get("files", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            return out


def _route_for_path(path: str, filename: str = "") -> Optional[str]:
    """Classifica la fonte senza usare dati contabili o importi."""
    source = f"{path}/{filename}".lower()
    if "paypal" in source:
        return "paypal"
    if "nexi" in source or "carta nexi" in source:
        return "nexi"
    if "mutuo acquisto" in source:
        return "mutuo"
    if "pos bpm" in source or "pos bnl" in source:
        return "pos"
    segments = {part.strip() for part in path.lower().split("/") if part.strip()}
    if (
        "carta di credito bnl" in source
        or "carta di credito bpm" in source
        or "bnl" in segments
        or "bpm" in segments
    ):
        return "bank"
    # Nessun indizio dal percorso: decide il nome del file, e se non basta
    # decidera' il contenuto dopo lo scaricamento. Qui c'era una regola che
    # dava per bancario qualunque file con "estratto" nel nome: con l'inbox
    # unico mandava in estratto conto anche la carta di credito Nexi.
    return classificazione_estratti.route_da_nome(filename)


def _supported_file(route: Optional[str], filename: str) -> bool:
    lower = filename.lower()
    if route is None:
        # Fonte ancora ignota: si prende in carico se e' un formato di
        # quest'area, e la si riconosce dal contenuto in fase di import.
        return classificazione_estratti.estensione_trattata(lower)
    if route == "bank":
        return lower.endswith((".csv", ".xlsx", ".xls", ".pdf"))
    if route == "pos":
        return (
            lower.endswith((".csv", ".xlsx", ".xlsm"))
            and any(token in lower for token in (
                "export_mensile", "export_transazioni", "commissioni_",
            ))
        )
    if route == "mutuo":
        return lower.endswith(".pdf")
    if route == "paypal":
        return lower.endswith(".pdf")
    if route == "nexi":
        return lower.endswith(".pdf")
    return False


def _troppo_vecchio(filename: str) -> bool:
    """Documento dell'arretrato, da lasciare fermo.

    L'inbox unico contiene anni di storico. L'utente ha chiesto di lavorare
    prima l'anno in corso, quindi i documenti piu' vecchi non vengono ne'
    importati ne' spostati: restano dove sono, visibili, pronti per quando
    si abbassera' `DRIVE_ESTRATTI_ANNO_MINIMO`.

    Un nome senza anno non viene piu' scartato: deve essere scaricato e letto.
    Nella cartella reale tutti gli estratti Nexi 2026 si chiamano infatti
    ``Estratto_Conto.pdf`` o ``Estratto_Conto (N).pdf``. Il controllo prudente
    sul periodo viene eseguito sul contenuto prima di qualunque importazione.
    """
    minimo = int(getattr(settings, "DRIVE_ESTRATTI_ANNO_MINIMO", 0) or 0)
    if minimo <= 0:
        return False
    anno = classificazione_estratti.anno_del_nome(filename)
    return anno is not None and anno < minimo


def _periodo_contenuto(filename: str, content: bytes) -> Tuple[Optional[int], bool]:
    """Restituisce anno provato e indica se il documento va rimandato.

    L'assenza di un anno non viene trasformata in uno zero: resta ``None`` e
    il documento prosegue verso la classificazione, che lo fermera' in Errori
    se anche la fonte non e' dimostrabile. Se invece il contenuto prova un
    anno anteriore alla soglia, il file resta nella cartella senza scritture.
    """
    anno = classificazione_estratti.anno_documento(filename, content)
    minimo = int(getattr(settings, "DRIVE_ESTRATTI_ANNO_MINIMO", 0) or 0)
    return anno, bool(minimo > 0 and anno is not None and anno < minimo)


def _work_item_priority(item: Dict[str, Any]) -> Tuple[int, str, str]:
    """Da precedenza ai file affidati esplicitamente a ``Da elaborare``.

    Le vecchie strutture possono contenere molti file direttamente nella
    cartella della banca. Restano tutti processabili, ma non devono precedere
    un documento appena inserito nell'inbox operativo.
    """
    path = str(item.get("source_path") or "").replace("\\", "/")
    segments = {segment.strip().lower() for segment in path.split("/")}
    return (
        0 if "da elaborare" in segments else 1,
        path.lower(),
        str(item.get("id") or ""),
    )


def _discover_work_items(
    service,
    root_id: str,
    initial_route: Optional[str] = None,
    *,
    include_elaborate: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], List[str]]:
    """Scansiona le fonti supportate e, su richiesta, recupera gli archivi.

    Compatibilita' con la struttura esistente: durante la transizione legge
    sia i file storicamente messi direttamente nella cartella fonte, sia i
    nuovi file presenti in ``Da elaborare``. Dopo il primo passaggio i file
    diretti vengono spostati e resterà attivo soltanto l'inbox.
    """
    items: List[Dict[str, Any]] = []
    sources: Dict[str, Dict[str, str]] = {}
    rimandati: List[str] = []

    def walk(folder_id: str, path: str, inherited_route: Optional[str], lifecycle_parent: Optional[str]):
        children = _list_children(service, folder_id)
        direct_files = [item for item in children if item.get("mimeType") != _FOLDER_MIME]
        folders = [item for item in children if item.get("mimeType") == _FOLDER_MIME]

        current_route = _route_for_path(path) or inherited_route
        current_lifecycle = lifecycle_parent
        if current_route != inherited_route and current_route:
            current_lifecycle = folder_id
        if current_route and current_lifecycle == folder_id:
            sources.setdefault(folder_id, {
                "id": folder_id,
                "path": path or "Estratti conto",
            })

        for item in direct_files:
            route = current_route or _route_for_path(path, item.get("name") or "")
            if not _supported_file(route, item.get("name") or ""):
                continue
            if _troppo_vecchio(item.get("name") or ""):
                rimandati.append(item.get("name") or "")
                continue
            target_parent = current_lifecycle or folder_id
            sources[target_parent] = {"id": target_parent, "path": path or "Estratti conto"}
            items.append({
                **item,
                "route": route,
                "source_parent_id": folder_id,
                "lifecycle_parent_id": target_parent,
                "source_path": "/".join(part for part in (path, item.get("name") or "") if part),
            })

        for folder in folders:
            name = (folder.get("name") or "").strip()
            lower = name.lower()
            if lower in _LIFECYCLE_NAMES:
                # Si entra in "Da elaborare" anche quando il percorso non dice
                # la fonte: e' il caso dell'inbox unico, dove a classificare
                # sono il nome del file e poi il suo contenuto. Prima serviva
                # una cartella per fonte, quindi con tutto in un posto solo
                # non veniva letto nulla.
                if lower == "da elaborare" or (
                    include_elaborate and lower == "elaborate"
                ):
                    for item in _list_children(service, folder["id"]):
                        if item.get("mimeType") == _FOLDER_MIME:
                            continue
                        nome = item.get("name") or ""
                        route = current_route or classificazione_estratti.route_da_nome(nome)
                        if not _supported_file(route, nome):
                            continue
                        if _troppo_vecchio(nome):
                            rimandati.append(nome)
                            continue
                        target_parent = current_lifecycle or folder_id
                        sources[target_parent] = {"id": target_parent, "path": path or "Estratti conto"}
                        items.append({
                            **item,
                            "route": route,
                            "source_parent_id": folder["id"],
                            "lifecycle_parent_id": target_parent,
                            "source_path": "/".join(part for part in (
                                path,
                                "Elaborate" if lower == "elaborate" else "Da elaborare",
                                nome,
                            ) if part),
                            "archive_recovery": lower == "elaborate",
                        })
                continue
            child_path = "/".join(part for part in (path, name) if part)
            child_route = _route_for_path(child_path) or current_route
            child_lifecycle = current_lifecycle
            if child_route != current_route and child_route:
                child_lifecycle = folder["id"]
            walk(folder["id"], child_path, child_route, child_lifecycle)

    walk(root_id, "", initial_route, root_id if initial_route else None)
    return items, list(sources.values()), rimandati


class _UploadDrive:
    skip_duplicate_repairs = True

    def __init__(
        self, name: str, content: bytes, *, drive_file_id: Optional[str] = None,
        source_path: Optional[str] = None,
    ):
        self.filename = name
        self._content = content
        self.drive_file_id = drive_file_id
        self.source_path = source_path

    async def read(self) -> bytes:
        return self._content


async def sync(db) -> Dict[str, Any]:
    if _sync_lock.locked():
        return {"status": "running"}
    async with _sync_lock:
        if not is_configured():
            return {"status": "not_configured"}
        service = _build_drive_service()
        if service is None:
            return {"status": "error", "message": "Service Drive non disponibile"}

        from app.routers.bank.estratto_conto import import_estratto_conto
        from app.services.pos_terminal_import import importa_pos_terminal_file
        from app.services.pos_commissioni_import import importa_pos_commissioni_file
        from app.services.mutui_document_import import importa_documento_mutuo
        from app.services.paypal_statement_import import import_paypal_statement_pdf

        result: Dict[str, Any] = {
            "status": "ok", "total": 0, "processed": 0, "moved": 0,
            "new_movements": 0, "duplicates": 0, "cheques": 0,
            "pos_files": 0, "pos_days": 0, "roots": len(_folder_ids()),
            "pos_commission_files": 0, "pos_commission_days": 0,
            "mutuo_files": 0, "mutuo_duplicates": 0,
            "paypal_files": 0, "paypal_statements": 0,
            "paypal_transactions": 0, "paypal_transactions_linked": 0,
            "nexi_files": 0, "nexi_duplicates": 0,
            "nexi_transactions": 0, "unrecognized": 0,
            "sources": [], "errors": [], "deferred_content": 0,
        }
        files_by_id: Dict[str, Dict[str, Any]] = {}
        sources_by_id: Dict[str, Dict[str, str]] = {}
        rimandati: List[str] = []
        for root_id in _folder_ids():
            root_files, root_sources, root_rimandati = _discover_work_items(
                service,
                root_id,
                initial_route="nexi" if root_id in _nexi_folder_ids() else None,
                # ``Elaborate`` e' archivio: il ciclo operativo legge soltanto
                # i documenti nuovi. Riesaminare a ogni passaggio tutti gli
                # archivi contraddice il lifecycle Drive, blocca il worker e
                # puo' causare un riavvio per memoria.
                include_elaborate=False,
            )
            for item in root_files:
                files_by_id.setdefault(item["id"], item)
            for source in root_sources:
                sources_by_id.setdefault(source["id"], source)
            rimandati.extend(root_rimandati)
        # Arretrato tenuto fermo: dichiarato, mai nascosto. Un conteggio che
        # non si vede diventa "e' tutto importato" quando non lo e'.
        result["deferred"] = len(rimandati)
        result["deferred_before_year"] = int(
            getattr(settings, "DRIVE_ESTRATTI_ANNO_MINIMO", 0) or 0
        )
        if rimandati:
            logger.info("Drive estratti conto: %s documenti dell'arretrato lasciati "
                        "fermi (anno minimo %s)", len(rimandati), result["deferred_before_year"])
        discovered_files = sorted(files_by_id.values(), key=_work_item_priority)
        files = _select_batch(discovered_files)
        sources = list(sources_by_id.values())
        result["sources"] = [source["path"] for source in sources]
        result["total"] = len(discovered_files)
        result["attempted"] = len(files)
        result["pending"] = max(len(discovered_files) - len(files), 0)
        result["archive_recovered"] = 0
        result["archive_already_indexed"] = 0
        lifecycle: Dict[str, Dict[str, Optional[str]]] = {}
        for source in sources:
            source_id = source["id"]
            lifecycle[source_id] = {
                "inbox": _get_or_create_inbox_folder(service, source_id),
                "elaborate": _get_or_create_elaborate_folder(service, source_id),
                "error": _get_or_create_error_folder(service, source_id),
            }
        for item in files:
            source_id = item["source_parent_id"]
            archive_recovery = bool(item.get("archive_recovery"))
            target = lifecycle.get(item["lifecycle_parent_id"], {})
            try:
                if archive_recovery and await db[_IMPORT_REGISTRY].find_one(
                    {"drive_file_id": item["id"], "status": "processed"},
                    {"_id": 0, "drive_file_id": 1},
                ):
                    result["archive_already_indexed"] += 1
                    continue
                content = _download_bytes(service, item["id"])
                if not content:
                    raise ValueError("file vuoto")
                document_year, defer_by_content = _periodo_contenuto(
                    item["name"], content,
                )
                if defer_by_content:
                    # Non e' un errore e non va spostato: il documento e'
                    # leggibile, ma appartiene allo storico fuori perimetro.
                    # Il registro rende verificabile il motivo della mancata
                    # importazione senza creare alcun movimento contabile.
                    now_file = datetime.now(timezone.utc).isoformat()
                    await db[_IMPORT_REGISTRY].update_one(
                        {"drive_file_id": item["id"]},
                        {"$set": {
                            "drive_file_id": item["id"],
                            "filename": item.get("name"),
                            "source_path": item.get("source_path"),
                            "status": "deferred_before_year",
                            "document_year": document_year,
                            "minimum_year": result["deferred_before_year"],
                            "checked_at": now_file,
                        }},
                        upsert=True,
                    )
                    result["deferred"] += 1
                    result["deferred_content"] += 1
                    continue
                # Verifica sempre il contenuto, anche quando percorso o nome
                # sembrano gia' sufficienti. Nell'archivio reale nomi come
                # "Movimenti carta" ed "Estratto_Conto" sono ambigui.
                route_verificata, motivo_verifica = classificazione_estratti.classifica(
                    item["name"], content,
                )
                if route_verificata:
                    item["route"] = route_verificata
                if item["route"] is None:
                    # Ultima possibilita': l'intestazione del documento. Se
                    # non basta si ferma qui — attribuire la fonte a caso
                    # significherebbe scrivere movimenti su un conto che non
                    # c'entra, ed e' un danno peggiore del file non importato.
                    item["route"], motivo = classificazione_estratti.classifica(
                        item["name"], content,
                    )
                    if item["route"] is None:
                        result["unrecognized"] += 1
                        raise ValueError(f"fonte non riconosciuta: {motivo}")
                if item["route"] == "pos":
                    if "commissioni_" in item["name"].lower():
                        esito = await importa_pos_commissioni_file(
                            db, content, item["name"], drive_file_id=item["id"],
                        )
                        result["pos_commission_files"] += 1
                        result["pos_commission_days"] += int(esito.get("days") or 0)
                    else:
                        esito = await importa_pos_terminal_file(
                            db, content, item["name"], drive_file_id=item["id"],
                        )
                        result["pos_files"] += 1
                        result["pos_days"] += int(esito.get("days") or 0)
                elif item["route"] == "mutuo":
                    esito = await importa_documento_mutuo(
                        db, content, item["name"], drive_file_id=item["id"],
                    )
                    result["mutuo_files"] += 1
                    result["mutuo_duplicates"] += int(bool(esito.get("duplicate")))
                elif item["route"] == "paypal":
                    esito = await import_paypal_statement_pdf(
                        db,
                        content,
                        item["name"],
                        source="drive_paypal_statement",
                        drive_file_id=item["id"],
                        source_path=item.get("source_path"),
                    )
                    result["paypal_files"] += 1
                    result["paypal_statements"] += 1
                    result["paypal_transactions"] += int(esito.get("transazioni_inserite") or 0)
                    result["paypal_transactions_linked"] += int(esito.get("transazioni_ricollegate") or 0)
                elif item["route"] == "nexi":
                    from app.services.nexi_carta import importa_estratto_nexi_pdf

                    esito = await importa_estratto_nexi_pdf(
                        db,
                        item["name"],
                        content,
                        source="drive_documenti_nexi",
                        drive_file_id=item["id"],
                        source_path=item.get("source_path"),
                    )
                    if not esito.get("success"):
                        raise ValueError(esito.get("message") or "Parsing Nexi fallito")
                    result["nexi_files"] += 1
                    result["nexi_duplicates"] += int(bool(esito.get("duplicate")))
                    result["nexi_transactions"] += int(esito.get("operazioni") or 0)
                else:
                    esito = await import_estratto_conto(_UploadDrive(
                        item["name"], content,
                        drive_file_id=item["id"],
                        source_path=item.get("source_path"),
                    ))
                    if isinstance(esito, dict) and (esito.get("error") or esito.get("detail")):
                        raise ValueError(esito.get("error") or esito.get("detail"))
                    stats = (esito or {}).get("stats") or {}
                    result["new_movements"] += int(stats.get("nuovi") or (esito or {}).get("movimenti_nuovi_importati") or 0)
                    result["duplicates"] += int(stats.get("duplicati") or (esito or {}).get("duplicati_saltati") or 0)
                    sync_assegni = (esito or {}).get("assegni_sync") or {}
                    result["cheques"] += int(sync_assegni.get("assegni_creati") or 0)
                result["processed"] += 1
                now_file = datetime.now(timezone.utc).isoformat()
                await db[_IMPORT_REGISTRY].update_one(
                    {"drive_file_id": item["id"]},
                    {"$set": {
                        "drive_file_id": item["id"],
                        "filename": item.get("name"),
                        "source_path": item.get("source_path"),
                        "route": item.get("route"),
                        "document_year": document_year,
                        "status": "processed",
                        "archive_recovery": archive_recovery,
                        "processed_at": now_file,
                    }},
                    upsert=True,
                )
                if archive_recovery:
                    result["archive_recovered"] += 1
                elif target.get("elaborate"):
                    _move_to_elaborate(service, item["id"], source_id, target["elaborate"])
                    result["moved"] += 1
            except Exception as exc:
                logger.exception("Drive estratti conto: errore su %s", item.get("source_path"))
                result["errors"].append({"file": item.get("source_path"), "error": str(exc)})
                if not archive_recovery and target.get("error"):
                    try:
                        _move_to_folder(service, item["id"], source_id, target["error"])
                    except Exception:
                        logger.exception("Drive estratti conto: impossibile spostare %s in Errori", item.get("name"))

        if result["paypal_files"]:
            try:
                # Una sola riconciliazione a fine lotto: evita N scansioni
                # complete mentre vengono importati piu' mesi PayPal.
                from app.routers.paypal_statements import _auto_riconcilia

                result["paypal_reconciliation"] = await _auto_riconcilia(db)
            except Exception as exc:
                logger.exception("Drive PayPal: riconciliazione finale fallita")
                result["errors"].append({
                    "file": "PayPal (riconciliazione finale)",
                    "error": str(exc),
                })

        # Non basta riconciliare i soli movimenti appena inseriti. L'estratto
        # conto puo' essere arrivato prima della fattura: in quel caso il file
        # e' gia' in Elaborate e una scansione successiva non produce nuovi ID,
        # ma deve comunque riesaminare i movimenti ufficiali ancora aperti.
        # Il motore canonico applica soltanto riscontri forti e conserva in
        # sospeso quelli ambigui; qui non viene mai usato il solo importo.
        try:
            from app.services.riconciliazione_bancaria import (
                riconcilia_movimenti_banca,
            )

            # Il Drive operativo contiene dal 2026 in avanti. Limitare il
            # replay allo stesso confine evita di riprocessare migliaia di
            # movimenti storici a ogni ciclo di cinque minuti, mantenendo
            # comunque il caso essenziale EC-prima/fattura-dopo.
            anno_minimo = int(
                getattr(settings, "DRIVE_ESTRATTI_ANNO_MINIMO", 0) or 0
            )
            data_dal = f"{anno_minimo}-01-01" if anno_minimo else None
            result["bank_reconciliation"] = await riconcilia_movimenti_banca(
                data_dal=data_dal,
            )
        except Exception as exc:
            logger.exception(
                "Drive estratti conto: riprocessamento bancario finale fallito"
            )
            result["errors"].append({
                "file": "Estratti conto (riconciliazione finale)",
                "error": str(exc),
            })

        now = datetime.now(timezone.utc).isoformat()
        await db["sistema_stato"].update_one(
            {"chiave": _STATO_KEY},
            {"$set": {"valore": now, "last_result": result, "updated_at": now}},
            upsert=True,
        )
        return result
