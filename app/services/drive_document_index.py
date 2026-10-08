"""Catalogo documentale Drive in sola lettura.

L'Excel e' il ponte tra Drive e il gestionale. Questo servizio non accede a
Drive/Supabase e non scarica i documenti indicizzati: scarica soltanto l'indice e,
quando richiesto, risolve il percorso fino al link Drive del file originale.
"""

from __future__ import annotations

import io
import posixpath
import re
import threading
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List

from openpyxl import load_workbook

from app.config import settings

FOLDER_MIME = "application/vnd.google-apps.folder"
INDEX_FOLDER_NAME = "INDICI GESTIONALE"
INDEX_FILE_NAME = "INDICE_DOCUMENTALE_DRIVE.xlsx"
INDEX_SHEET_NAME = "DOCUMENTI"
REQUIRED_HEADERS = (
    "ID documento", "Dominio", "Categoria", "Anno", "Nome file",
    "Estensione", "Dimensione byte", "SHA-256", "Percorso Drive",
    "Cartella Drive", "ZIP origine", "Percorso nel pacchetto", "Stato",
    "Numero documento",
)
F24_HEADERS = (
    "ID documento", "Anno pagamento", "Data pagamento", "Sezione",
    "Tipo riga", "Codice tributo", "Descrizione", "Periodo tributo",
    "Ente", "Debito", "Credito", "Protocollo", "Tipo documento",
    "SHA-256", "Percorso Drive", "Pagina", "Testo sorgente", "Fonte",
)
DECLARATION_HEADERS = ("Anno", "Tipo", "Protocollo", "Percorso archivio")
DUPLICATE_HEADERS = (
    "ZIP origine", "Percorso nel pacchetto", "Nome", "Estensione",
    "Dimensione byte", "SHA-256", "Esito", "Percorso Drive collegato",
)
_CACHE_LOCK = threading.Lock()
_CACHE_KEY: tuple[str, str | None] | None = None
_CACHE_CATALOG: dict[str, list[dict[str, Any]]] | None = None


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _list_children(service, parent_id: str) -> List[Dict[str, Any]]:
    """Figli diretti di una cartella Drive, tutte le pagine."""
    q = f"'{parent_id}' in parents and trashed = false"
    out: List[Dict[str, Any]] = []
    page_token = None
    while True:
        res = service.files().list(
            q=q, fields="nextPageToken, files(id, name, mimeType, md5Checksum, size)",
            pageSize=100, pageToken=page_token,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        out.extend(res.get("files", []))
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return out


def build_drive_service():
    # Credenziale provata sulla cartella unica, non sulla cartella cedolini:
    # smontata quella, ogni pagina che apriva un file Drive dava errore.
    from app.services.drive_cartella_unica import _service

    return _service()


def _unique_named(items: Iterable[dict[str, Any]], name: str, *, folder: bool) -> dict[str, Any]:
    matches = [
        item for item in items
        if _norm(item.get("name")) == _norm(name)
        and (item.get("mimeType") == FOLDER_MIME) is folder
    ]
    if len(matches) != 1:
        raise ValueError(f"Elemento Drive assente o ambiguo: {name} ({len(matches)} corrispondenze)")
    return matches[0]


def _discover_index_file_sync(service, root_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    root = service.files().get(
        fileId=root_id,
        fields="id,name,mimeType,trashed",
        supportsAllDrives=True,
    ).execute()
    if root.get("trashed") or root.get("mimeType") != FOLDER_MIME:
        raise ValueError("La radice dell'archivio documentale non e' una cartella Drive attiva")
    folder = _unique_named(_list_children(service, root_id), INDEX_FOLDER_NAME, folder=True)
    index_file = _unique_named(_list_children(service, folder["id"]), INDEX_FILE_NAME, folder=False)
    metadata = service.files().get(
        fileId=index_file["id"],
        fields="id,name,mimeType,parents,trashed,modifiedTime,md5Checksum,size,webViewLink",
        supportsAllDrives=True,
    ).execute()
    if metadata.get("trashed"):
        raise ValueError("L'indice documentale risulta nel cestino")
    return folder, metadata


def _download_index_sync(service, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload
    output = io.BytesIO()
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(output, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return output.getvalue()


def _parse_sheet_records(workbook, sheet_name: str, required_headers: tuple[str, ...]) -> list[dict[str, Any]]:
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"Foglio obbligatorio assente: {sheet_name}")
    rows = workbook[sheet_name].iter_rows(values_only=True)
    try:
        headers = tuple(str(value or "").strip() for value in next(rows))
    except StopIteration as exc:
        raise ValueError(f"Foglio vuoto: {sheet_name}") from exc
    missing = [header for header in required_headers if header not in headers]
    if missing:
        raise ValueError(f"Colonne obbligatorie assenti in {sheet_name}: {', '.join(missing)}")
    records = []
    for values in rows:
        record = {headers[i]: values[i] for i in range(min(len(headers), len(values)))}
        if any(value is not None for value in record.values()):
            records.append(record)
    return records


def _parse_index_workbook(content: bytes) -> dict[str, list[dict[str, Any]]]:
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    documents = _parse_sheet_records(workbook, INDEX_SHEET_NAME, REQUIRED_HEADERS)
    return {
        "documents": [record for record in documents if record.get("ID documento")],
        "f24_rows": _parse_sheet_records(workbook, "F24_RIGHE", F24_HEADERS),
        "declarations": _parse_sheet_records(workbook, "DICHIARAZIONI", DECLARATION_HEADERS),
        "duplicates": _parse_sheet_records(workbook, "DUPLICATI_SCARTI", DUPLICATE_HEADERS),
    }


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    display = _record_display_fields(record)
    return {
        "document_id": record.get("ID documento"),
        "domain": record.get("Dominio"),
        "category": record.get("Categoria"),
        "year": record.get("Anno"),
        "filename": record.get("Nome file"),
        "extension": record.get("Estensione"),
        "size_bytes": record.get("Dimensione byte"),
        "sha256": record.get("SHA-256"),
        "drive_path": record.get("Percorso Drive"),
        "source_zip": record.get("ZIP origine"),
        "source_path": record.get("Percorso nel pacchetto"),
        "status": record.get("Stato"),
        "document_number": record.get("Numero documento"),
        **display,
    }


def _record_display_fields(record: dict[str, Any]) -> dict[str, Any]:
    """Etichette operative sintetiche; non fingono dati non letti dal PDF."""
    filename = str(record.get("Nome file") or "")
    path = str(record.get("Percorso Drive") or "")
    extension = _norm(record.get("Estensione")).lstrip(".")
    searchable = f"{filename} {path} {record.get('Categoria') or ''}"
    normalized = _norm(searchable)
    words = re.sub(r"[_-]+", " ", normalized)
    from app.services.personal_family_registry import match_family_person
    person = match_family_person(searchable)
    subject = person["display_name"] if person else (
        "Ceraldi Group Srl" if "ceraldi group" in normalized or "04523831214" in normalized else "Da identificare"
    )
    if extension == "zip":
        document_type = "Pacchetto sorgente"
        if "archivio fiscale pulito" in words:
            title = "Archivio fiscale verificato 2019-2026"
        elif "partenopay" in normalized:
            title = "Pacchetto PartenoPay completo"
        elif "5 mittenti" in words:
            title = "Raccolta PEC dei 5 mittenti"
        else:
            title = "Archivio ZIP originale"
        summary = "Contenitore di originali: consultare i singoli atti estratti nell'indice operativo."
    elif "r da 2023" in words or "definizione agevolata" in words:
        document_type = "Definizione agevolata AdeR"
        title = "Domanda Rottamazione-quater"
        summary = "Richiesta presentata ad AdeR: attendere esito, piano/importo e successive prove di pagamento."
    elif "verbale" in normalized or "polizia locale" in normalized:
        document_type = "Verbale"
        title = "Verbale Codice della strada"
        summary = "Estrarre numero, targa, date, importi, soggetti e scadenze; il pagamento resta da provare."
    elif "tari" in normalized or "tares" in normalized or "tarsu" in normalized:
        document_type = "Tributo locale"
        title = "TARI / tributo locale"
        summary = "Estrarre contribuente, posizione, immobile, anno, importi e scadenze."
    elif "dimission" in normalized or "unilav" in normalized:
        document_type = "Rapporto di lavoro"
        title = "Dimissioni / comunicazione lavoro"
        summary = "Documento aziendale da collegare al dipendente; non prova pagamenti."
    elif "cartelle esattoriali" in normalized or "agenzia riscossione" in normalized:
        document_type = "Atto AdeR"
        title = "Atto Agenzia Entrate-Riscossione"
        summary = "Leggere numeri di cartella/avviso, contribuente, importi, stato e relazioni documentali."
    else:
        document_type = str(record.get("Categoria") or "Documento")
        title = document_type
        summary = "Metadati catalogati; aprire l'originale o la sezione associata per la lavorazione."
    return {
        "display_title": title,
        "subject": subject,
        "document_type_label": document_type,
        "summary": summary,
        "is_source_package": extension == "zip",
    }


def _basename(value: Any) -> str:
    normalized = str(value or "").replace("\\", "/")
    return PurePosixPath(posixpath.normpath(normalized)).name.casefold()


def _amount(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _is_documentary_payment(row: dict[str, Any]) -> bool:
    """Una quietanza prova documentalmente il pagamento, non il riscontro bancario."""
    document_type = re.sub(r"[_-]+", " ", _norm(row.get("Tipo documento")))
    protocol = re.sub(r"\D", "", str(row.get("Protocollo") or ""))
    # Il vecchio indice etichettava questi PDF come "Formato stampabile
    # (considerato quietanza)". Il contenuto e' invece una delega F24 con gli
    # estremi bancari ancora da compilare: non prova un versamento eseguito.
    if "stampabile" in document_type:
        return False
    return "quietanza" in document_type and len(protocol) >= 12


def validate_relations(catalog: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    documents = catalog["documents"]
    f24_rows = catalog["f24_rows"]
    declarations = catalog["declarations"]
    duplicates = catalog["duplicates"]
    by_id = {str(record.get("ID documento")): record for record in documents}
    names: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in documents:
        names[_basename(record.get("Nome file"))].append(record)

    checks = {
        "document_ids_unique": len(by_id) == len(documents),
        "document_hashes_unique": len({_norm(item.get("SHA-256")) for item in documents}) == len(documents),
        "drive_paths_unique": len({_norm(item.get("Percorso Drive")) for item in documents}) == len(documents),
        "all_f24_documents_exist": all(str(row.get("ID documento")) in by_id for row in f24_rows),
        "all_f24_sha_match_document": all(
            str(row.get("ID documento")) in by_id
            and _norm(row.get("SHA-256")) == _norm(by_id[str(row.get("ID documento"))].get("SHA-256"))
            for row in f24_rows
        ),
        "all_f24_paths_match_document": all(
            str(row.get("ID documento")) in by_id
            and _norm(row.get("Percorso Drive")) == _norm(by_id[str(row.get("ID documento"))].get("Percorso Drive"))
            for row in f24_rows
        ),
        "f24_amounts_nonnegative": all(
            _amount(row.get("Debito")) >= 0 and _amount(row.get("Credito")) >= 0
            for row in f24_rows
        ),
        "all_declarations_link_exactly_one_document": all(
            len(names.get(_basename(row.get("Percorso archivio")), [])) == 1
            for row in declarations
        ),
    }
    return {
        "all_true": all(checks.values()),
        "checks": checks,
        "counts": {
            "documents": len(documents),
            "f24_rows": len(f24_rows),
            "f24_documents": len({str(row.get("ID documento")) for row in f24_rows}),
            "documentary_payment_rows": sum(1 for row in f24_rows if _is_documentary_payment(row)),
            "documentary_payment_documents": len({
                str(row.get("ID documento")) for row in f24_rows if _is_documentary_payment(row)
            }),
            "tax_debit_rows": sum(1 for row in f24_rows if _amount(row.get("Debito")) > 0),
            "declarations": len(declarations),
            "duplicates_and_discards": len(duplicates),
        },
    }


def load_catalog(service=None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source, catalog = load_full_catalog(service)
    return source, catalog["documents"]


def load_full_catalog(service=None) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    global _CACHE_KEY, _CACHE_CATALOG
    service = service or build_drive_service()
    root_id = settings.DRIVE_DOCUMENT_INDEX_ROOT_FOLDER_ID.strip()
    folder, metadata = _discover_index_file_sync(service, root_id)
    cache_key = (str(metadata["id"]), metadata.get("modifiedTime"))
    with _CACHE_LOCK:
        if _CACHE_KEY == cache_key and _CACHE_CATALOG is not None:
            catalog = _CACHE_CATALOG
        else:
            catalog = _parse_index_workbook(_download_index_sync(service, metadata["id"]))
            _CACHE_KEY = cache_key
            _CACHE_CATALOG = catalog
    return {"folder": folder, "index": metadata, "root_id": root_id}, catalog


def get_status(service=None) -> dict[str, Any]:
    source, catalog = load_full_catalog(service)
    metadata = source["index"]
    validation = validate_relations(catalog)
    return {
        "status": "ok",
        "mode": "drive_index_read_only",
        "documents": len(catalog["documents"]),
        "validation": validation,
        "index_name": metadata.get("name"),
        "index_modified_time": metadata.get("modifiedTime"),
        "index_size_bytes": metadata.get("size"),
        "index_url": metadata.get("webViewLink"),
        "stores_document_binaries_in_database": False,
    }


_ADMINISTRATIVE_AREA_TERMS = {
    "tributi_locali": ("tributi locali", "tari", "tares", "tarsu"),
    "riscossione": ("cartelle esattoriali", "agenzia riscossione", "ader"),
    "personale": ("dimission", "unilav"),
    "famiglia": (),
}


# Eccezioni documentali verificate sul PDF originale. La chiave SHA-256 evita
# che omonimie, importi o la cartella PEC trasformino un documento personale in
# un costo aziendale. Questi metadati sono solo descrittivi: non generano
# movimenti contabili, pagamenti o riconciliazioni.
_PERSONAL_FAMILY_DOCUMENTS = {
    "d3edc9fd5c999343a4370d441bf2e67fe672d41eb6c370e4a43b589d01bcd45a": {
        "contribuente": "Ceraldi Antonietta",
        "codice_contribuente": "1804135",
        "anno_tributo": "2024",
        "oggetto": "Avviso di pagamento TARI - Acconto 2024",
        "immobile": "Via Cavallerizza 46, Napoli",
    },
}


def _administrative_area(record: dict[str, Any]) -> str | None:
    if _norm(record.get("SHA-256")) in _PERSONAL_FAMILY_DOCUMENTS:
        return "famiglia"
    # La collocazione operativa Drive decide l'area. Il percorso storico nel
    # pacchetto puo' descrivere solo l'email a cui un allegato apparteneva (per
    # esempio un documento d'identita' allegato a una pratica TARI) e non deve
    # quindi promuovere quell'allegato ad atto amministrativo.
    searchable_raw = " ".join(str(record.get(field) or "") for field in (
        "Dominio", "Categoria", "Nome file", "Percorso Drive",
    ))
    searchable = _norm(searchable_raw)
    from app.services.personal_family_registry import (
        is_company_context, is_employment_context, match_family_person,
    )
    # Un documento di rapporto di lavoro resta aziendale anche quando il
    # lavoratore e' contemporaneamente un familiare.
    if is_employment_context(searchable_raw):
        if any(term in searchable for term in _ADMINISTRATIVE_AREA_TERMS["personale"]):
            return "personale"
        return None
    person = match_family_person(searchable_raw)
    # Pane Giuseppina compare anche come legale rappresentante. Nell'indice
    # Drive (che non contiene il testo del PDF) un atto AdeR col solo suo CF e'
    # ambiguo e resta aziendale/documentale; il parser del contenuto potra'
    # spostarlo in Famiglia solo quando l'intestatario persona fisica e' certo.
    if person and person["person_id"] == "pane-giuseppina" and any(
        term in searchable for term in _ADMINISTRATIVE_AREA_TERMS["riscossione"]
    ):
        return "riscossione"
    if person and not is_company_context(searchable_raw):
        return "famiglia"
    for area, terms in _ADMINISTRATIVE_AREA_TERMS.items():
        if any(term in searchable for term in terms):
            return area
    return None


def list_administrative_documents(
    service=None, *, area: str | None = None, year: str | None = None,
    q: str | None = None, review_only: bool = False, limit: int = 500,
) -> dict[str, Any]:
    """Atti amministrativi dall'indice Drive, senza copiare i PDF nel DB."""
    _, records = load_catalog(service)
    overview_counts = {key: 0 for key in _ADMINISTRATIVE_AREA_TERMS}
    overview_review = 0
    matches: list[dict[str, Any]] = []
    query = _norm(q)
    from app.services.personal_family_registry import family_search_terms, match_family_person
    query_terms = family_search_terms(q) if query else set()

    for record in records:
        if _norm(record.get("Estensione")).lstrip(".") != "pdf":
            continue
        record_area = _administrative_area(record)
        if not record_area:
            continue
        status = _norm(record.get("Stato"))
        category = _norm(record.get("Categoria"))
        requires_review = (
            status in {"da verificare", "da_verificare", "errore"}
            or not str(record.get("Anno") or "").strip()
            or category in {"esistente su drive", "documento"}
        )
        overview_counts[record_area] += 1
        overview_review += int(requires_review)

        if area and record_area != area:
            continue
        if year and _norm(record.get("Anno")) != _norm(year):
            continue
        if review_only and not requires_review:
            continue
        record_search = _norm(" ".join(str(value or "") for value in record.values()))
        if query and not any(term.casefold() in record_search for term in query_terms):
            continue

        public = _public_record(record)
        personal_metadata = _PERSONAL_FAMILY_DOCUMENTS.get(_norm(public["sha256"]), {})
        family_person = match_family_person(record_search)
        if family_person:
            personal_metadata = {
                **personal_metadata,
                "person_id": family_person["person_id"],
                "persona": family_person["display_name"],
                "identity_matched_by": family_person["matched_by"],
                "lavoratore_cf": next(iter(family_person.get("identifiers", {}).get("codice_fiscale", ())), None),
            }
        accounting_excluded = record_area == "famiglia"
        matches.append({
            "id": public["document_id"],
            "filename": public["filename"],
            "category": public["category"],
            "category_label": public["category"] or public["domain"],
            "administrative_area": record_area,
            "document_date_display": public["year"],
            "status": public["status"] or "indicizzato_drive",
            "sha256": public["sha256"],
            "source_kind": "drive_index",
            "source_label": "Google Drive",
            "accounting_scope": "personal_family" if accounting_excluded else "business_documentary",
            "accounting_excluded": accounting_excluded,
            "accounting_exclusion_reason": (
                "Documento personale/familiare: escluso da bilanci, costi, Prima Nota e riconciliazioni aziendali."
                if accounting_excluded else None
            ),
            "source_context": {
                "archive_path": public["drive_path"],
                "source_zip": public["source_zip"],
                "source_path": public["source_path"],
            },
            "parsed_metadata": {
                "requires_review": requires_review,
                "numero_documento": public["document_number"],
                **personal_metadata,
            },
        })

    matches.sort(key=lambda item: (
        str(item.get("document_date_display") or ""), str(item.get("filename") or "").casefold(),
    ), reverse=True)
    return {
        "items": matches[:limit],
        "total": len(matches),
        "counts": dict(Counter(item["administrative_area"] for item in matches)),
        "requires_review": sum(bool(item["parsed_metadata"]["requires_review"]) for item in matches),
        "overview": {
            "counts": overview_counts,
            "total": sum(overview_counts.values()),
            "requires_review": overview_review,
        },
        "source": "drive_excel_index",
    }
