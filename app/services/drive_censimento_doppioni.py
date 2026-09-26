"""Censimento della cartella GESTIONALE: copie identiche e file tecnici.

Richiesta del titolare (26/09/2026): elencare tutti i doppioni della cartella
GESTIONALE e **marcarli con una rinomina**, cosi' li riguarda e li elimina lui.
Il gestionale non cancella e non sposta niente: al massimo rinomina.

* Due file sono la stessa cosa solo se Drive da' la stessa impronta MD5 e la
  stessa dimensione (le copie esatte; CLAUDE.md ammette l'MD5 solo per questo).
  Un nome uguale non basta, e un nome diverso non salva una copia.
* Per ogni gruppo resta **un originale**: quello gia' archiviato in ELABORATE,
  poi quello fuori da DOPPIONI, poi quello senza «(2)»/«copia» nel nome, poi
  il piu' vecchio. Gli altri diventano «DUPLICATO DA ELIMINARE - <nome>».
* File tecnici senza contenuto utile (``desktop.ini``, ``Thumbs.db``,
  ``.DS_Store``, i file di blocco ``~$…`` di Office, i file vuoti) diventano
  «FILE TECNICO DA ELIMINARE - <nome>».

Due interruttori su Render, come la simulazione:
``DRIVE_CENSIMENTO_DOPPIONI`` = ``off`` (difetto) | ``censisci`` (solo elenco) |
``marca`` (elenco e rinomina), e ``DRIVE_CENSIMENTO_EDIZIONE`` per rifarlo da
capo. Il lavoro va a lotti dallo scheduler e riprende dove si era fermato.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services import drive_cartella_unica as cu

logger = logging.getLogger(__name__)

REGISTRO = "drive_censimento_doppioni"
CHIAVE_STATO = "drive_censimento_doppioni"
PREFISSO_DUPLICATO = "DUPLICATO DA ELIMINARE - "
PREFISSO_TECNICO = "FILE TECNICO DA ELIMINARE - "
PREFISSI = (PREFISSO_DUPLICATO, PREFISSO_TECNICO)
NOMI_TECNICI = {"desktop.ini", "thumbs.db", ".ds_store"}
_COPIA_NEL_NOME = re.compile(r"(\(\d+\)|\bcopia\b|\bcopy\b|\bcopy of\b)", re.IGNORECASE)
_GOOGLE_NATIVO = "application/vnd.google-apps."

_lock = asyncio.Lock()


def modalita() -> str:
    valore = os.getenv("DRIVE_CENSIMENTO_DOPPIONI", "off").strip().lower()
    return valore if valore in ("censisci", "marca") else "off"


def edizione() -> str:
    return os.getenv("DRIVE_CENSIMENTO_EDIZIONE", "1").strip() or "1"


def _lotto() -> int:
    try:
        return max(1, min(int(os.getenv("DRIVE_CENSIMENTO_LOTTO", "300")), 1000))
    except ValueError:
        return 300


def marcato(nome: Optional[str]) -> bool:
    return str(nome or "").startswith(PREFISSI)


def _radice() -> Optional[str]:
    from app.services import drive_cartella_unica_simulazione as sim

    return sim.radice()


def _inventario(service, root: str) -> List[Dict[str, Any]]:
    """Tutti i file sotto ``root``, sottocartelle comprese, con il percorso."""
    file: List[Dict[str, Any]] = []
    coda = [(root, "")]
    while coda:
        cartella, percorso = coda.pop(0)
        token = None
        while True:
            risposta = service.files().list(
                q=f"'{cartella}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, md5Checksum, size, createdTime)",
                pageSize=1000, pageToken=token,
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            for f in risposta.get("files", []):
                if f.get("mimeType") == cu.CARTELLA_MIME:
                    coda.append((f["id"], f"{percorso}/{f.get('name') or f['id']}"))
                else:
                    file.append({**f, "percorso": percorso or "/"})
            token = risposta.get("nextPageToken")
            if not token:
                break
    return file


def _tecnico(f: Dict[str, Any]) -> Optional[str]:
    nome = str(f.get("name") or "")
    if nome.lower() in NOMI_TECNICI:
        return "file di sistema di Windows/Mac"
    if nome.startswith("~$"):
        return "file di blocco di Office rimasto aperto"
    if not str(f.get("mimeType") or "").startswith(_GOOGLE_NATIVO) and int(f.get("size") or 0) == 0:
        return "file vuoto (0 byte)"
    return None


def _chiave_originale(f: Dict[str, Any]) -> Tuple[int, int, int, int, str]:
    percorso = f"{f['percorso']}/".upper()
    return (
        0 if f"/{cu.ARCHIVIO}/" in percorso else 1,
        1 if f"/{cu.DOPPIONI}/" in percorso else 0,
        1 if marcato(f.get("name")) else 0,
        1 if _COPIA_NEL_NOME.search(str(f.get("name") or "")) else 0,
        str(f.get("createdTime") or ""),
    )


def classifica(file: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Una riga per file: originale, duplicato (di chi) o file tecnico."""
    righe: List[Dict[str, Any]] = []
    gruppi: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for f in file:
        motivo = _tecnico(f)
        if motivo:
            righe.append({"file": f, "ruolo": "tecnico", "motivo": motivo})
        elif f.get("md5Checksum"):
            gruppi.setdefault((f["md5Checksum"], str(f.get("size") or "")), []).append(f)
        else:
            righe.append({"file": f, "ruolo": "unico"})
    for (md5, _), membri in gruppi.items():
        if len(membri) == 1:
            righe.append({"file": membri[0], "ruolo": "unico"})
            continue
        membri.sort(key=_chiave_originale)
        originale = membri[0]
        righe.append({"file": originale, "ruolo": "originale", "gruppo": md5, "copie": len(membri) - 1})
        for copia in membri[1:]:
            righe.append({"file": copia, "ruolo": "duplicato", "gruppo": md5,
                          "originale_id": originale["id"], "originale_nome": originale.get("name"),
                          "originale_percorso": originale["percorso"],
                          "motivo": "copia identica (stessa impronta e dimensione)"})
    return righe


async def giro(db) -> Dict[str, Any]:
    if modalita() == "off":
        return {"saltato": "DRIVE_CENSIMENTO_DOPPIONI=off"}
    root = _radice()
    if not root:
        return {"saltato": "radice non impostata (DRIVE_SIMULAZIONE_RADICE)"}
    if _lock.locked():
        return {"saltato": "giro_in_corso"}
    async with _lock:
        return await _giro(db, root)


async def _giro(db, root: str) -> Dict[str, Any]:
    stato = await db["sistema_stato"].find_one({"chiave": CHIAVE_STATO}, {"_id": 0}) or {}
    ed = edizione()
    service = await asyncio.to_thread(cu._service)

    if stato.get("edizione") != ed or stato.get("radice") != root:
        file = await asyncio.to_thread(_inventario, service, root)
        righe = classifica(file)
        ora = datetime.now(timezone.utc).isoformat()
        documenti = []
        for r in righe:
            f = r.pop("file")
            documenti.append({
                "id": f"{ed}:{f['id']}", "edizione": ed, "file_id": f["id"], "nome": f.get("name"),
                "percorso": f["percorso"], "md5": f.get("md5Checksum"), "size": int(f.get("size") or 0),
                "mime": f.get("mimeType"), "creato_il": f.get("createdTime"), "censito_il": ora,
                "gia_marcato": marcato(f.get("name")), **r,
            })
        # Righe nuove per ogni edizione: nessuna riscrittura di massa.
        for i in range(0, len(documenti), 2000):
            await db[REGISTRO].insert_many(documenti[i:i + 2000])
            await asyncio.sleep(0)
        conteggi = Counter(d["ruolo"] for d in documenti)
        byte_doppi = sum(d["size"] for d in documenti if d["ruolo"] == "duplicato")
        stato = {"chiave": CHIAVE_STATO, "edizione": ed, "radice": root, "fase": "censito",
                 "file": len(documenti), "per_ruolo": dict(conteggi), "mb_duplicati": round(byte_doppi / 1048576, 1),
                 "censito_il": ora, "marcati": 0, "errori_marcatura": 0}
        await db["sistema_stato"].update_one({"chiave": CHIAVE_STATO}, {"$set": stato}, upsert=True)
        return {"censiti": len(documenti), **dict(conteggi)}

    if modalita() != "marca" or stato.get("fase") == "completato":
        return {"saltato": f"fase {stato.get('fase')}, modalita {modalita()}"}

    da_marcare = await db[REGISTRO].find({
        "edizione": ed, "ruolo": {"$in": ["duplicato", "tecnico"]},
        "gia_marcato": False, "marcatura": {"$exists": False},
    }, {"_id": 0}).limit(_lotto()).to_list(_lotto())
    marcati = errori = 0
    for riga in da_marcare:
        esito = await asyncio.to_thread(_marca, service, riga)
        await db[REGISTRO].update_one({"id": riga["id"]}, {"$set": {
            "marcatura": esito, "marcato_il": datetime.now(timezone.utc).isoformat()}})
        marcati += esito.get("esito") == "rinominato"
        errori += esito.get("esito") == "errore"
        await asyncio.sleep(0)
    aggiornamento = {"fase": "marcatura" if da_marcare else "completato",
                     "marcati": int(stato.get("marcati") or 0) + marcati,
                     "errori_marcatura": int(stato.get("errori_marcatura") or 0) + errori}
    await db["sistema_stato"].update_one({"chiave": CHIAVE_STATO}, {"$set": aggiornamento})
    return {"marcati": marcati, "errori": errori, "lotto": len(da_marcare)}


def _marca(service, riga: Dict[str, Any]) -> Dict[str, Any]:
    """Rinomina una copia dopo aver riverificato che sia ancora identica."""
    try:
        attuale = service.files().get(
            fileId=riga["file_id"], fields="id, name, md5Checksum, size, trashed",
            supportsAllDrives=True,
        ).execute()
        if attuale.get("trashed"):
            return {"esito": "saltato", "motivo": "gia' nel Cestino"}
        if marcato(attuale.get("name")):
            return {"esito": "saltato", "motivo": "gia' marcato"}
        if riga["ruolo"] == "duplicato":
            if attuale.get("md5Checksum") != riga.get("md5"):
                return {"esito": "saltato", "motivo": "contenuto cambiato dopo il censimento"}
            originale = service.files().get(
                fileId=riga["originale_id"], fields="id, md5Checksum, trashed", supportsAllDrives=True,
            ).execute()
            if originale.get("trashed") or originale.get("md5Checksum") != riga.get("md5"):
                return {"esito": "saltato", "motivo": "l'originale non c'e' piu' o e' cambiato"}
        prefisso = PREFISSO_DUPLICATO if riga["ruolo"] == "duplicato" else PREFISSO_TECNICO
        nuovo = f"{prefisso}{attuale.get('name') or riga.get('nome')}"
        service.files().update(
            fileId=riga["file_id"], body={"name": nuovo}, fields="id, name", supportsAllDrives=True,
        ).execute()
        return {"esito": "rinominato", "nuovo_nome": nuovo}
    except Exception as exc:  # il singolo file non ferma il lotto, ma resta scritto
        logger.warning("[censimento-doppioni] %s non rinominato: %s: %s",
                       riga.get("file_id"), type(exc).__name__, exc)
        return {"esito": "errore", "motivo": f"{type(exc).__name__}: {exc}"[:300]}


async def elenco(db, *, solo_da_eliminare: bool = True, limite: int = 20000) -> Dict[str, Any]:
    """Lo stato del censimento e le righe da guardare, piu' recenti prima."""
    stato = await db["sistema_stato"].find_one({"chiave": CHIAVE_STATO}, {"_id": 0}) or {}
    filtro: Dict[str, Any] = {"edizione": stato.get("edizione")}
    if solo_da_eliminare:
        filtro["ruolo"] = {"$in": ["duplicato", "tecnico"]}
    righe = await db[REGISTRO].find(filtro, {"_id": 0}).limit(limite).to_list(limite)
    righe.sort(key=lambda r: (r.get("percorso") or "", r.get("nome") or ""))
    return {"stato": stato, "righe": righe}
