"""Simulazione della migrazione nella cartella unica: sola lettura.

Prima di spostare i documenti in «DA ELABORARE», il titolare vuole sapere
come finira' ogni file. La simulazione percorre un albero Drive (le cartelle
di oggi) e, per ogni file, chiede allo **stesso** classificatore e alla
**stessa** anteprima di Documenti > Import (``detect_document_type`` e
``build_import_preview``) che tipo e', cosa ne leggerebbe il motore e se e'
gia' nel gestionale. Non sposta, non importa, non scrive nulla fuori dal
proprio registro ``drive_cartella_unica_simulazione``.

Gira a lotti riprendibili dallo scheduler (``DRIVE_SIMULAZIONE_RADICE``):
prima l'inventario dell'albero, poi al piu' ``DRIVE_SIMULAZIONE_BATCH`` file
per giro. Un deploy la interrompe senza perdere nulla: al giro dopo riparte
dai file ancora da leggere.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services import drive_cartella_unica as cu

logger = logging.getLogger(__name__)

REGISTRO = "drive_cartella_unica_simulazione"
CHIAVE_STATO = "drive_cartella_unica_simulazione"
# Oltre questa soglia il file non si scarica: la simulazione deve restare
# leggera anche con la RAM del servizio vicina al limite.
MAX_BYTES = 25 * 1024 * 1024
_GOOGLE_NATIVO = "application/vnd.google-apps."
# Solo questi formati hanno un motore in Documenti > Import: gli altri (codice,
# appunti, immagini, Word) finirebbero comunque in ERRORI, e scaricarli per
# saperlo costa tempo e memoria.
FORMATI_GESTITI = (".pdf", ".xml", ".p7m", ".zip", ".xls", ".xlsx", ".xlsm", ".csv")

# Campi dell'esito di una lettura: una nuova edizione li toglie prima di rileggere.
_ESITO = ("tipo", "esito_previsto", "motivo", "errori", "gia_presente", "anno",
          "fuori_anno", "sha256", "pagine", "fornitore", "numero")

_lock = asyncio.Lock()


def radice() -> Optional[str]:
    return os.getenv("DRIVE_SIMULAZIONE_RADICE", "").strip() or None


def edizione() -> str:
    """Si cambia per rileggere tutto dopo una correzione ai lettori."""
    return os.getenv("DRIVE_SIMULAZIONE_EDIZIONE", "1").strip() or "1"


def _batch() -> int:
    try:
        return max(1, min(int(os.getenv("DRIVE_SIMULAZIONE_BATCH", "40")), 200))
    except ValueError:
        return 40


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inventario(service, root: str, escluse: set) -> List[Dict[str, Any]]:
    """Tutti i file sotto ``root`` con il loro percorso, cartelle escluse."""
    file: List[Dict[str, Any]] = []
    coda = [(root, "")]
    while coda:
        cartella, percorso = coda.pop(0)
        token = None
        while True:
            risposta = service.files().list(
                q=f"'{cartella}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, md5Checksum, size)",
                pageSize=1000, pageToken=token,
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            for f in risposta.get("files", []):
                if f.get("mimeType") == cu.CARTELLA_MIME:
                    # Le immagini hanno la loro cartella e il loro canale.
                    if (f.get("name") or "").strip().upper() == "FOTO E IMMAGINI":
                        continue
                    if f["id"] not in escluse:
                        coda.append((f["id"], f"{percorso}/{f.get('name') or f['id']}"))
                    continue
                file.append({**f, "percorso": percorso or "/"})
            token = risposta.get("nextPageToken")
            if not token:
                break
    return file


async def _esame_fattura(db, nome: str, contenuto: bytes) -> Dict[str, Any]:
    """Anno e presenza con la stessa chiave dell'import (numero + P.IVA + data)."""
    try:
        from app.routers.invoices.fatture_upload import generate_invoice_key, parse_fattura_xml

        testo = contenuto
        if nome.lower().endswith(".p7m"):
            from app.services.xml_invoice_processor import extract_xml_from_p7m

            testo = extract_xml_from_p7m(contenuto) or b""
        xml = None
        for codifica in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                xml = testo.decode(codifica)
                break
            except UnicodeDecodeError:
                continue
        parsed = parse_fattura_xml(xml or "")
        if not parsed or parsed.get("error"):
            return {"errore": "XML fattura non leggibile"}
        from app.services.config_import import get_anno_importazione_attivo

        data = str(parsed.get("invoice_date") or "")
        anno = int(data[:4]) if data[:4].isdigit() else None
        anno_attivo = await get_anno_importazione_attivo(db)
        chiave = generate_invoice_key(parsed.get("invoice_number", ""),
                                      parsed.get("supplier_vat", ""), data)
        trovata = await db["invoices"].find_one({"invoice_key": chiave}, {"_id": 0, "id": 1})
        return {"anno": anno, "fuori_anno": bool(anno and anno != anno_attivo),
                "gia_presente": bool(trovata),
                "fornitore": parsed.get("supplier_name"), "numero": parsed.get("invoice_number")}
    except Exception as exc:
        logger.warning("[simulazione] %s: identita' fattura non letta: %s: %s",
                       nome, type(exc).__name__, exc)
        return {"errore": f"{type(exc).__name__}: {exc}"[:300]}


async def esamina(db, nome: str, contenuto: bytes) -> Dict[str, Any]:
    """Cosa succederebbe a questo file nella cartella unica, senza scrivere."""
    from app.routers.documenti import detect_document_type
    from app.services.document_import_preview import build_import_preview

    tipo = detect_document_type(nome, contenuto)
    if tipo == "auto":
        return {"tipo": "non_riconosciuto", "esito_previsto": cu.ERRORI,
                "motivo": "tipo di documento non riconosciuto"}
    anteprima = await build_import_preview(db, content=contenuto, filename=nome, document_type=tipo)
    esito: Dict[str, Any] = {"tipo": tipo, "gia_presente": bool(anteprima.get("duplicate")),
                             "pagine": (anteprima.get("file") or {}).get("page_count")}
    errori = [str(e) for e in anteprima.get("blocking_errors") or []]
    if tipo == "fattura":
        fattura = await _esame_fattura(db, nome, contenuto)
        if fattura.get("errore"):
            errori.append(fattura.pop("errore"))
        esito["gia_presente"] = esito["gia_presente"] or bool(fattura.pop("gia_presente", False))
        esito.update(fattura)
        if fattura.get("fuori_anno"):
            esito["motivo"] = f"fattura del {fattura['anno']}: resta solo su Drive (fuori anno attivo)"
    esito["errori"] = errori or None
    esito["esito_previsto"] = cu.ERRORI if errori else cu.ARCHIVIO
    return esito


async def giro(db) -> Dict[str, Any]:
    """Un lotto di simulazione; no-op se la radice non e' impostata o e' finita."""
    root = radice()
    if not root:
        return {"saltato": "DRIVE_SIMULAZIONE_RADICE non impostata"}
    if _lock.locked():
        return {"saltato": "giro_in_corso"}
    async with _lock:
        return await _giro(db, root)


async def _giro(db, root: str) -> Dict[str, Any]:
    from app.services.drive_download import scarica_bytes

    stato = await db["sistema_stato"].find_one({"chiave": CHIAVE_STATO}, {"_id": 0}) or {}
    stessa = stato.get("radice") == root and stato.get("edizione") == edizione()
    if stessa and stato.get("fase") == "completata":
        return {"saltato": "simulazione_completata"}
    service = await asyncio.to_thread(cu._service)

    if not stessa or stato.get("fase") != "lettura":
        # Inventario: una riga per file, tutte «da_leggere». Le cartelle della
        # cartella unica stessa non fanno parte di cio' che si migra.
        escluse = set()
        if cu.radice():
            escluse = set((await asyncio.to_thread(cu._cartelle, service, cu.radice())).values())
        file = await asyncio.to_thread(_inventario, service, root, escluse)
        gia = await db[REGISTRO].find({}, {"_id": 0, "id": 1, "radice": 1}).to_list(None)
        noti = {r["id"] for r in gia}
        noti_radice = {r["id"] for r in gia if r.get("radice") == root}
        ora = _ora()
        righe = [{"id": f["id"], "radice": root, "nome": f.get("name"),
                  "percorso": f["percorso"], "md5": f.get("md5Checksum"),
                  "mime": f.get("mimeType"), "size": int(f.get("size") or 0),
                  "stato": "da_leggere", "aggiornato_il": ora} for f in file]
        nuove = [r for r in righe if r["id"] not in noti]
        if nuove:
            await db[REGISTRO].insert_many(nuove)
        # Le righe gia' note tornano in coda con UN aggiornamento: una scrittura
        # per riga su 23.000 file teneva il giro fermo per ore.
        await db[REGISTRO].update_many(
            {"radice": root},
            {"$set": {"stato": "da_leggere", "aggiornato_il": ora},
             "$unset": {k: "" for k in _ESITO}},
        )
        for r in righe:
            if r["id"] in noti and r["id"] not in noti_radice:
                await db[REGISTRO].update_one({"id": r["id"]}, {"$set": r})
        stato = {"chiave": CHIAVE_STATO, "radice": root, "edizione": edizione(),
                 "fase": "lettura", "file_totali": len(file), "iniziata_il": ora}
        await db["sistema_stato"].update_one({"chiave": CHIAVE_STATO}, {"$set": stato}, upsert=True)
        return {"inventario": len(file)}

    da_leggere = await db[REGISTRO].find(
        {"radice": root, "stato": "da_leggere"}, {"_id": 0}
    ).limit(_batch()).to_list(_batch())
    for riga in da_leggere:
        esito: Dict[str, Any]
        if str(riga.get("mime") or "").startswith(_GOOGLE_NATIVO):
            esito = {"tipo": "documento_google", "esito_previsto": cu.ERRORI,
                     "motivo": "file nativo Google (Documenti/Fogli): va esportato in PDF o Excel"}
        elif not str(riga.get("nome") or "").lower().endswith(FORMATI_GESTITI):
            esito = {"tipo": "formato_non_gestito", "esito_previsto": cu.ERRORI,
                     "motivo": "formato che il gestionale non importa"}
        elif riga.get("size", 0) > MAX_BYTES:
            esito = {"tipo": "troppo_grande", "esito_previsto": "da_verificare",
                     "motivo": f"oltre {MAX_BYTES // (1024 * 1024)} MB, non letto in simulazione"}
        else:
            try:
                contenuto = await asyncio.to_thread(scarica_bytes, service, riga["id"])
                esito = await esamina(db, riga.get("nome") or riga["id"], contenuto)
                esito["sha256"] = hashlib.sha256(contenuto).hexdigest()
            except Exception as exc:
                esito = {"tipo": "errore_lettura", "esito_previsto": cu.ERRORI,
                         "motivo": f"{type(exc).__name__}: {exc}"[:500]}
        await db[REGISTRO].update_one(
            {"id": riga["id"]}, {"$set": {**esito, "stato": "letto", "aggiornato_il": _ora()}})

    restanti = await db[REGISTRO].count_documents({"radice": root, "stato": "da_leggere"})
    if not restanti:
        await db["sistema_stato"].update_one(
            {"chiave": CHIAVE_STATO}, {"$set": {"fase": "completata", "completata_il": _ora()}})
    return {"letti": len(da_leggere), "restanti": restanti}


async def riepilogo(db) -> Dict[str, Any]:
    """Conteggi per tipo ed esito previsto, copie identiche, elenco dei non riconosciuti."""
    stato = await db["sistema_stato"].find_one({"chiave": CHIAVE_STATO}, {"_id": 0}) or {}
    root = stato.get("radice")
    righe = await db[REGISTRO].find(
        {"radice": root}, {"_id": 0, "id": 1, "nome": 1, "percorso": 1, "md5": 1, "stato": 1,
                           "tipo": 1, "esito_previsto": 1, "gia_presente": 1, "motivo": 1,
                           "errori": 1, "anno": 1, "fuori_anno": 1},
    ).to_list(None) if root else []
    lette = [r for r in righe if r.get("stato") == "letto"]
    fuori_anno = Counter(r.get("anno") for r in lette if r.get("fuori_anno"))
    per_md5 = Counter(r["md5"] for r in righe if r.get("md5"))
    return {
        "stato": stato,
        "file": len(righe),
        "letti": len(lette),
        "per_tipo": dict(Counter(r.get("tipo") for r in lette).most_common()),
        "per_esito": dict(Counter(r.get("esito_previsto") for r in lette).most_common()),
        "gia_presenti": sum(1 for r in lette if r.get("gia_presente")),
        "fatture_fuori_anno": dict(fuori_anno),
        "copie_identiche": sum(n - 1 for n in per_md5.values() if n > 1),
        "da_guardare": [
            {k: r.get(k) for k in ("nome", "percorso", "tipo", "motivo", "errori")}
            for r in lette if r.get("esito_previsto") != cu.ARCHIVIO
        ][:500],
    }
