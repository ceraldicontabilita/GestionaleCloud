"""
Pulizia cartella Drive fatture per ANNO (strumento Rollback admin).

Caso d'uso (richiesta utente 10/07): dopo aver eliminato dal gestionale i
dati di un anno (Admin → Rollback), i file XML/P7M restano su Drive e la
sincronizzazione oraria + la quadratura li REIMPORTEREBBERO. Questo servizio
scandisce la cartella indicata (comprese le sottocartelle, quindi anche
"Elaborate"), determina l'ANNO di ogni fattura leggendo la data del
documento dentro l'XML (<DatiGeneraliDocumento>…<Data>YYYY-…) e sposta nel
CESTINO di Drive i file degli anni scelti.

Sicurezza:
  - niente eliminazione definitiva: i file vanno nel cestino Drive
    (recuperabili per 30 giorni);
  - un file il cui anno NON è determinabile con certezza NON viene toccato
    (finisce nel conteggio "non_determinati");
  - modalità dry_run per contare prima di agire (stesso pattern conta →
    conferma del resto del Rollback).
"""
import logging
import re
from typing import Any, Dict, List, Optional

from app.services.drive_invoice_ingest import _load_credentials, _download_bytes

logger = logging.getLogger(__name__)

# Data del documento: il primo <Data> dentro DatiGeneraliDocumento.
# Funziona anche sui .p7m: l'XML viaggia in chiaro dentro la busta PKCS#7.
_RE_DATA_DOC = re.compile(r"<DatiGeneraliDocumento>.*?<Data>\s*(\d{4})-", re.DOTALL)
# Fallback: qualsiasi <Data>YYYY-MM-DD</Data> (se tutte concordano sull'anno)
_RE_DATA_ANY = re.compile(r"<Data>\s*(\d{4})-\d{2}-\d{2}\s*</Data>")

_ESTENSIONI_FATTURA = (".xml", ".p7m")


def estrai_id_cartella(valore: str) -> str:
    """Accetta sia l'ID nudo sia l'URL completo della cartella Drive."""
    v = (valore or "").strip()
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", v)
    return m.group(1) if m else v


def anno_da_contenuto(content: bytes) -> Optional[int]:
    """Anno del documento dal contenuto del file, None se non determinabile."""
    if not content:
        return None
    testo = content.decode("utf-8", errors="ignore")
    m = _RE_DATA_DOC.search(testo)
    if m:
        return int(m.group(1))
    anni = {int(a) for a in _RE_DATA_ANY.findall(testo)}
    if len(anni) == 1:
        return anni.pop()
    return None


def _build_service():
    creds, err = _load_credentials()
    if creds is None:
        return None, err
    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds, cache_discovery=False), None
    except Exception as e:
        return None, str(e)


def _list_children(service, parent_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    page_token = None
    while True:
        res = service.files().list(
            q=f"'{parent_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=200, pageToken=page_token,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        out.extend(res.get("files", []))
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return out


def _raccogli_file(service, folder_id: str, profondita: int = 0) -> List[Dict[str, Any]]:
    """Tutti i file fattura nella cartella e nelle sottocartelle (es. Elaborate)."""
    if profondita > 3:
        return []
    files: List[Dict[str, Any]] = []
    for f in _list_children(service, folder_id):
        if f.get("mimeType") == "application/vnd.google-apps.folder":
            files.extend(_raccogli_file(service, f["id"], profondita + 1))
        elif f.get("name", "").lower().endswith(_ESTENSIONI_FATTURA):
            files.append(f)
    return files


async def pulizia_fatture_drive(
    folder_id: str, anni: List[int], dry_run: bool = True
) -> Dict[str, Any]:
    """Scandisce la cartella e sposta nel cestino i file degli anni scelti.

    dry_run=True: solo conteggio, nessun file toccato.
    """
    folder_id = estrai_id_cartella(folder_id)
    if not folder_id:
        return {"status": "error", "message": "Indicare l'ID (o l'URL) della cartella Drive"}
    anni = sorted({int(a) for a in (anni or [])})
    if not anni:
        return {"status": "error", "message": "Indicare almeno un anno"}

    service, err = _build_service()
    if service is None:
        return {"status": "error", "message": f"Credenziali/servizio Drive non disponibili: {err}"}

    esito: Dict[str, Any] = {
        "status": "ok", "dry_run": dry_run, "folder_id": folder_id, "anni": anni,
        "esaminati": 0, "da_eliminare": 0, "eliminati": 0,
        "non_determinati": 0, "altri_anni": 0, "errori": 0,
        "per_anno": {str(a): 0 for a in anni}, "dettagli": [],
    }

    try:
        files = _raccogli_file(service, folder_id)
    except Exception as e:
        logger.error(f"Pulizia Drive: impossibile leggere la cartella {folder_id}: {e}")
        return {"status": "error",
                "message": f"Impossibile leggere la cartella (condivisa col service account?): {e}"}

    for f in files:
        esito["esaminati"] += 1
        try:
            content = _download_bytes(service, f["id"])
            anno = anno_da_contenuto(content)
            if anno is None:
                esito["non_determinati"] += 1
                if len(esito["dettagli"]) < 20:
                    esito["dettagli"].append({"file": f["name"], "anno": None, "azione": "saltato"})
                continue
            if anno not in anni:
                esito["altri_anni"] += 1
                continue
            esito["da_eliminare"] += 1
            esito["per_anno"][str(anno)] += 1
            if not dry_run:
                service.files().update(
                    fileId=f["id"], body={"trashed": True}, supportsAllDrives=True
                ).execute()
                esito["eliminati"] += 1
            if len(esito["dettagli"]) < 20:
                esito["dettagli"].append({
                    "file": f["name"], "anno": anno,
                    "azione": "cestinato" if not dry_run else "da cestinare",
                })
        except Exception as e:
            esito["errori"] += 1
            logger.error(f"Pulizia Drive: errore su {f.get('name')}: {e}")
            if len(esito["dettagli"]) < 20:
                esito["dettagli"].append({"file": f.get("name"), "error": str(e)})

    logger.info(
        f"Pulizia Drive {'(conta)' if dry_run else ''} cartella {folder_id} anni {anni}: "
        f"esaminati={esito['esaminati']} da_eliminare={esito['da_eliminare']} "
        f"eliminati={esito['eliminati']} non_determinati={esito['non_determinati']}"
    )
    return esito
