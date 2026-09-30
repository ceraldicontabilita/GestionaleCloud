"""Import idempotente e probatorio degli archivi PartenoPay navigabili."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import posixpath
import re
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict


ROOT = "package_clean/"
DATA_PATH = ROOT + "data.json"
MANIFEST_PATH = ROOT + "documenti/MANIFEST_SHA256.csv"
_VERBALE_RE = re.compile(r"VERBALE\s+N(?:[.:°])*\s*([A-Z0-9/-]+)", re.I)
_TARGA_RE = re.compile(r"TARGA:\s*([A-Z]{2}\d{3}[A-Z]{2})", re.I)


def is_partenopay_archive(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return DATA_PATH in archive.namelist() and MANIFEST_PATH in archive.namelist()
    except (OSError, zipfile.BadZipFile):
        return False


def _safe_name(name: str) -> str:
    normalized = posixpath.normpath(str(name or "").replace("\\", "/"))
    if normalized.startswith("../") or normalized.startswith("/") or normalized == "..":
        raise ValueError(f"Percorso ZIP non sicuro: {name}")
    return normalized


def _chiavi_manifest(percorso: str) -> list[str]:
    """Varianti con cui un file puo' comparire nel manifest (relativo al pacchetto o a `documenti/`)."""
    pulito = _safe_name(percorso)
    if pulito.startswith(ROOT):
        pulito = pulito[len(ROOT):]
    varianti = [pulito]
    if pulito.startswith("documenti/"):
        varianti.append(pulito[len("documenti/"):])
    else:
        varianti.append("documenti/" + pulito)
    return varianti


def leggi_manifest(testo: str) -> Dict[str, str]:
    """`MANIFEST_SHA256.csv` come {percorso: sha256}: prima colonna il file, seconda l'hash.

    L'intestazione puo' chiamarli «file/path/percorso» e «sha256/hash»; righe
    vuote o senza hash si saltano (le conta chi confronta).
    """
    righe = list(csv.reader(io.StringIO(testo.lstrip("\ufeff"))))
    if not righe:
        return {}
    intestazione = [c.strip().lower() for c in righe[0]]
    def colonna(nomi: tuple[str, ...], default: int) -> int:
        for nome in nomi:
            if nome in intestazione:
                return intestazione.index(nome)
        return default
    i_file = colonna(("file", "path", "percorso", "nome"), 0)
    i_sha = colonna(("sha256", "sha-256", "hash"), 1)
    manifest: Dict[str, str] = {}
    for riga in righe[1:]:
        if len(riga) <= max(i_file, i_sha) or not riga[i_file].strip():
            continue
        manifest[_safe_name(riga[i_file].strip())] = riga[i_sha].strip().lower()
    return manifest


def _iso_date(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def inspect_partenopay_archive(content: bytes) -> Dict[str, Any]:
    """Valida struttura, nomi, manifest SHA-256 e restituisce il piano import."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Archivio PartenoPay non valido: {exc}") from exc
    with archive:
        if archive.testzip() is not None:
            raise ValueError("Archivio PartenoPay corrotto")
        names = {_safe_name(item.filename) for item in archive.infolist() if not item.is_dir()}
        if DATA_PATH not in names or MANIFEST_PATH not in names:
            raise ValueError("data.json o manifest SHA-256 assente")
        manifest = leggi_manifest(archive.read(MANIFEST_PATH).decode("utf-8-sig", errors="replace"))
        payload = json.loads(archive.read(DATA_PATH))
        required = {"summary", "records", "emails", "files"}
        if not isinstance(payload, dict) or not required.issubset(payload):
            raise ValueError("Schema data.json PartenoPay non riconosciuto")
        file_rows = payload.get("files") or []
        errors = []
        warnings: list[str] = []
        verified = 0
        manifest_verificati = 0
        manifest_usati: set = set()
        file_sha256: Dict[str, str] = {}
        for row in file_rows:
            relative = _safe_name(row.get("file"))
            full = relative if relative.startswith(ROOT) else ROOT + relative
            if full not in names:
                errors.append({"file": relative, "errore": "assente_nello_zip"})
                continue
            expected = str(row.get("sha256") or "").strip().lower()
            actual = hashlib.sha256(archive.read(full)).hexdigest()
            # GC-17: un file senza hash dichiarato non e' verificato; l'hash
            # usato da qui in avanti e' quello calcolato sui byte veri.
            if not expected:
                errors.append({"file": relative, "errore": "sha256_assente"})
            elif expected != actual:
                errors.append({"file": relative, "errore": "sha256_non_coincide"})
            else:
                verified += 1
                file_sha256[str(row.get("file"))] = actual
            # Il manifest del pacchetto e' una seconda prova, indipendente da data.json:
            # con righe, ogni file dell'indice vi compare e coincide con i byte veri.
            if manifest:
                voce = next((v for v in _chiavi_manifest(relative) if v in manifest), None)
                if voce is None:
                    errors.append({"file": relative, "errore": "non_nel_manifest"})
                elif manifest[voce] != actual:
                    errors.append({"file": relative, "errore": "manifest_sha256_non_coincide"})
                else:
                    manifest_verificati += 1
                    manifest_usati.add(voce)
        if not manifest:
            warnings.append("manifest_vuoto")
        else:
            senza_file = [v for v in manifest if v not in manifest_usati]
            if senza_file:
                warnings.append(f"manifest_voci_non_nell_indice:{len(senza_file)}")
        return {
            "manifest_righe": len(manifest),
            "manifest_verificati": manifest_verificati,
            "avvisi": warnings,
            "payload": payload,
            "files_verified": verified,
            "file_sha256": file_sha256,
            "integrity_errors": errors,
            "archive_sha256": hashlib.sha256(content).hexdigest(),
        }


def _testo_identificativo(value: Any) -> str:
    """Codice avviso/IUV sempre come testo: un float ha perso cifre e non si indovina."""
    if value is None or isinstance(value, (bool, float)):
        return ""
    return re.sub(r"\s+", "", str(value))


def _record_identity(record: Dict[str, Any]) -> tuple[str, str | None, str | None]:
    notice = _testo_identificativo(record.get("codice_avviso"))
    text = str(record.get("oggetto_pagamento") or "")
    number_match = _VERBALE_RE.search(text)
    number = None
    if number_match:
        from app.services.verbali_document_import import normalizza_numero_verbale
        number = normalizza_numero_verbale(number_match.group(1).rstrip("-./"))
    plate = (_TARGA_RE.search(text).group(1).upper() if _TARGA_RE.search(text) else None)
    key = notice or number or hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:24]
    return key, number, plate


async def import_partenopay_archive(db, content: bytes, *, dry_run: bool = True) -> Dict[str, Any]:
    plan = inspect_partenopay_archive(content)
    if plan["integrity_errors"]:
        return {"success": False, "dry_run": dry_run,
                **{k: v for k, v in plan.items() if k not in ("payload", "file_sha256")}}
    payload = plan.pop("payload")
    file_sha256 = plan.pop("file_sha256")
    result: Dict[str, Any] = {
        "success": True,
        "dry_run": dry_run,
        **plan,
        "records": len(payload.get("records") or []),
        "emails": len(payload.get("emails") or []),
        "files": len(payload.get("files") or []),
        "inserted_or_updated": 0,
        "nuovi": 0, "aggiornati": 0, "invariati": 0,
        "email_nuove": 0, "file_nuovi": 0,
        "ambiguous": 0,
    }
    if dry_run:
        return result

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    archive_sha = result["archive_sha256"]

    # Conserva una sola copia integrale e verificata del pacchetto. I file
    # interni restano indirizzabili tramite archive_path senza moltiplicare
    # 141 chiamate Drive dentro la richiesta HTTP.
    import_run_id = f"partenopay_{archive_sha[:32]}"
    previous_run = await db["partenopay_import_runs"].find_one(
        {"id": import_run_id}, {"_id": 0, "drive_archive_status": 1}
    )
    previous_archive_status = str((previous_run or {}).get("drive_archive_status") or "")
    if previous_archive_status not in {"archived", "duplicate", "archived_manual_oauth"}:
        try:
            from app.services.email_drive_archive import archive_document_copy
            drive_archive = archive_document_copy(
                {"id": import_run_id, "filename": "PARTENOPAY_NAVIGABILE_PRONTO.zip",
                 "file_hash": archive_sha, "content": content},
                "partenopay",
            )
        except Exception as exc:
            drive_archive = {"status": "error", "reason": str(exc)}
    else:
        drive_archive = {"status": previous_archive_status}
    await db["partenopay_import_runs"].update_one(
        {"id": import_run_id},
        {"$set": {"id": import_run_id, "archive_sha256": archive_sha,
                  "filename": "PARTENOPAY_NAVIGABILE_PRONTO.zip",
                  "drive_archive_status": drive_archive.get("status"),
                  "drive_archive_reason": drive_archive.get("reason"),
                  "drive_archived_at": drive_archive.get("archived_at"),
                  "updated_at": now_iso},
         "$setOnInsert": {"created_at": now_iso}}, upsert=True,
    )

    for email in payload.get("emails") or []:
        email_id = str(email.get("id") or "").strip() or hashlib.sha256(
            json.dumps(email, sort_keys=True).encode()
        ).hexdigest()[:32]
        if await db["verbali_email_archive"].find_one({"id": email_id}, {"_id": 0, "id": 1}):
            continue   # un'email archiviata non cambia: il secondo giro non la riscrive
        result["email_nuove"] += 1
        await db["verbali_email_archive"].update_one(
            {"id": email_id},
            {"$set": {
                "id": email_id, "gmail_message_id": email.get("id"),
                "gmail_url": email.get("gmail_url"), "thread_id": email.get("thread_id"),
                "mittente": email.get("mittente"), "destinatario": email.get("destinatario"),
                "oggetto": email.get("oggetto_email"), "testo": email.get("testo"),
                "data_email": email.get("data_email"), "etichette": email.get("etichette"),
                "allegati": email.get("allegati") or [], "fonte": "partenopay_zip",
                "archive_sha256": archive_sha, "updated_at": now_iso,
            }, "$setOnInsert": {"created_at": now_iso}}, upsert=True,
        )

    file_by_path = {str(item.get("file")): item for item in payload.get("files") or []}
    # GC-17 (AV3-09): ogni file e' gia' stato riletto e confrontato con il
    # manifest in inspect_partenopay_archive; qui si usa l'hash calcolato.
    for relative, item in file_by_path.items():
        sha = file_sha256[relative]
        doc_id = f"partenopay_{sha[:32]}"
        if await db["documents_inbox"].find_one({"id": doc_id}, {"_id": 0, "id": 1}):
            continue   # stesso contenuto (SHA-256 calcolato): gia' registrato
        result["file_nuovi"] += 1
        await db["documents_inbox"].update_one(
            {"id": doc_id},
            {"$set": {
                "id": doc_id, "filename": item.get("nome") or posixpath.basename(relative),
                "file_hash": sha, "sha256": sha, "source": "partenopay_zip",
                "fonte": "partenopay_zip", "archive_path": relative,
                "archive_sha256": archive_sha, "categoria_partenopay": item.get("categoria"),
                "codice_avviso_estratto": item.get("codice_avviso"),
                "source_archive_id": import_run_id,
                "drive_archive_status": "contained_in_source_archive",
                "original_preserved": True, "updated_at": now_iso,
            }, "$setOnInsert": {"created_at": now_iso, "processed": False, "status": "importato"}},
            upsert=True,
        )

    for record in payload.get("records") or []:
        key, number, plate = _record_identity(record)
        linked_files = list(record.get("files") or [])
        states = str(record.get("stati") or "").casefold()
        has_receipt = any("02_quietanze" in str(path).casefold() for path in linked_files)
        record_id = f"verbale_{hashlib.sha256(('partenopay:' + key).encode()).hexdigest()[:32]}"
        codice_avviso = _testo_identificativo(record.get("codice_avviso"))
        query = {"codice_avviso": codice_avviso} if codice_avviso else {"id": record_id}
        existing = await db["verbali_noleggio"].find_one(query, {"_id": 0})
        payment_declared = "pagamento eseguito" in states
        payment_verified = has_receipt and payment_declared
        payment_state = (
            "pagato" if payment_verified
            else "pagato_attesa_quietanza" if payment_declared
            else ((existing or {}).get("stato") or "salvato")
        )
        # Una prova piu' forte gia' acquisita (banca, chiusura a mano) o la quarantena
        # non tornano indietro per un reimport del pacchetto.
        if str((existing or {}).get("stato") or "").lower() in {"riconciliato", "chiuso", "quarantena"}:
            payment_state = existing["stato"]
        if existing and number and existing.get("numero_verbale") not in (None, "", number):
            result["ambiguous"] += 1
            await db["verbali_match_candidates"].update_one(
                {"id": f"candidate_{record_id}"},
                {"$set": {"id": f"candidate_{record_id}", "tipo": "VERBALE", "record": record,
                          "motivo": "numero_verbale_in_conflitto", "status": "scelta_manual_required",
                          "updated_at": now_iso}}, upsert=True,
            )
            continue
        values = {
            "id": (existing or {}).get("id") or record_id,
            "numero_verbale": number or (existing or {}).get("numero_verbale"),
            "codice_avviso": codice_avviso or None,
            "iuv": codice_avviso or None,
            "targa": plate, "importo": record.get("importo"),
            "importo_verificato": record.get("importo") is not None,
            "data_pagamento": _iso_date(record.get("data_pagamento")),
            "ente_creditore": record.get("ente"), "intestatario": record.get("intestatario"),
            "cf_piva": record.get("cf_piva"), "oggetto_pagamento": record.get("oggetto_pagamento"),
            "source": "partenopay_zip", "archive_sha256": archive_sha,
            "source_files": linked_files, "pagato_documentalmente": payment_verified,
            "quietanza_ricevuta": has_receipt,
            "stato_pagamento_documentale": "PAGATO_VERIFICATO" if payment_verified else "DA_VERIFICARE",
            "stato": payment_state,
        }
        da_scrivere = {k: v for k, v in values.items() if v not in (None, "")}
        if existing is not None and all(existing.get(k) == v for k, v in da_scrivere.items()):
            result["invariati"] += 1
            continue   # niente da cambiare: nessuna scrittura, nessun promemoria nuovo
        if existing is None:
            # Scadenza operativa e promemoria nascono una volta, alla scoperta: un secondo
            # giro (anche il giorno dopo) non sposta la scadenza ne' ne crea altri.
            da_scrivere["scadenza_operativa"] = (now + timedelta(days=5)).date().isoformat()
            da_scrivere["scadenza_operativa_motivo"] = "5 giorni dalla scoperta; distinta dalla scadenza legale"
        da_scrivere["updated_at"] = now_iso
        await db["verbali_noleggio"].update_one(
            query, {"$set": da_scrivere, "$setOnInsert": {"created_at": now_iso}}, upsert=True,
        )
        if existing is None:
            for offset, kind in ((0, "scoperta"), (3, "promemoria_3_giorni"), (4, "promemoria_1_giorno"), (5, "scadenza")):
                notification_id = f"{record_id}:{kind}"
                await db["notification_log"].update_one(
                    {"id": notification_id},
                    {"$setOnInsert": {"id": notification_id, "tipo": "verbale", "verbale_id": record_id,
                                      "evento": kind, "scheduled_for": (now + timedelta(days=offset)).isoformat(),
                                      "status": "pending", "created_at": now_iso}}, upsert=True,
                )
            result["nuovi"] += 1
        else:
            result["aggiornati"] += 1
        result["inserted_or_updated"] += 1
    return result


async def dispatch_due_verbali_notifications(db) -> Dict[str, Any]:
    """Invia una sola volta i promemoria maturati; conserva sempre il log."""
    now = datetime.now(timezone.utc)
    due = await db["notification_log"].find({
        "tipo": "verbale", "status": "pending", "scheduled_for": {"$lte": now.isoformat()},
    }, {"_id": 0}).limit(200).to_list(200)
    sent = failed = 0
    for item in due:
        verbale = await db["verbali_noleggio"].find_one({"id": item.get("verbale_id")}, {"_id": 0})
        number = (verbale or {}).get("numero_verbale") or item.get("verbale_id")
        message = f"Verbale {number}: {item.get('evento')}. Verifica scadenza, driver e pagamento nel gestionale."
        channels = []
        try:
            from app.services.websocket_manager import notify_data_change
            await notify_data_change("verbali_scan", {"verbale_id": item.get("verbale_id"),
                                                     "evento": item.get("evento"), "message": message},
                                     "notifications")
            channels.append("websocket")
        except Exception:
            pass
        try:
            from app.services.telegram_notifications import is_configured, send_notification
            if is_configured() and await send_notification(message):
                channels.append("telegram")
        except Exception:
            pass
        status = "sent" if channels else "failed_no_channel"
        await db["notification_log"].update_one(
            {"id": item["id"]}, {"$set": {"status": status, "channels": channels,
                                             "attempted_at": now.isoformat()}},
        )
        if channels:
            sent += 1
        else:
            failed += 1
    return {"due": len(due), "sent": sent, "failed": failed}
