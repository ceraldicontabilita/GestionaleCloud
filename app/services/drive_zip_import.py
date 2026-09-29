"""Import di uno ZIP grande o di una cartella Drive, a voci e riprendibile.

Documenti > Import accetta uno ZIP fino a 100 MB perche' lo tiene tutto in
memoria. Uno ZIP da centinaia di MB (il «MINISITO» del titolare: 638 MB) non
entra, e spezzarlo a mano non e' un lavoro da chiedere a chi ha altro da fare.
Qui lo ZIP **resta su Drive**: se ne leggono solo l'indice (in fondo al file) e,
una alla volta, le voci che servono, con richieste a intervalli di byte.

Ogni voce passa dallo stesso smistatore della cartella unica
(`drive_cartella_unica._smista` -> `upload_documento_automatico`), quindi ha le
stesse regole di riconoscimento e di doppioni: un secondo passaggio deve dare
`importati=0`. Niente si sposta e niente si cancella su Drive.

Una **cartella** Drive (con le sue sottocartelle, come il «MINISITO» messo dentro
«DATI SOCIETA CERALDI») si importa allo stesso modo: l'albero si legge in sola
lettura, ogni file passa dallo smistatore, la struttura resta dov'e'. Lo smistatore
della cartella unica non scende nelle sottocartelle, e non deve svuotarle.

Lo stato (cursore, contatori, voci non riconosciute) sta in `sistema_stato`
sotto `import_zip_drive:<file_id>`: se il servizio si riavvia a meta', un nuovo
avvio riparte dalla voce dopo l'ultima elaborata. `dry_run` e' la sola
anteprima: conta cosa c'e', senza importare.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

CHIAVE = "import_zip_drive"
BLOCCO_BYTE = 4 * 1024 * 1024
BLOCCHI_IN_CACHE = 4
MAX_VOCE_BYTE = 50 * 1024 * 1024
MAX_RAPPORTO_COMPRESSIONE = 200
SUFFISSI_AMMESSI = {".pdf", ".xml", ".p7m", ".xlsx", ".xls", ".csv"}
# Le liste nello stato restano corte: sono per capire cosa guardare, non l'archivio.
MAX_ELENCO = 300

_lavoro: Optional[asyncio.Task] = None
_lock = asyncio.Lock()


class FileDriveARange(io.RawIOBase):
    """File a sola lettura su Drive: `zipfile` legge l'indice e le voci a blocchi."""

    def __init__(self, fetch: Callable[[int, int], bytes], size: int):
        super().__init__()
        self._fetch = fetch
        self._size = size
        self._pos = 0
        self._blocchi: Dict[int, bytes] = {}
        self._ordine: List[int] = []

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self._pos = offset
        elif whence == io.SEEK_CUR:
            self._pos += offset
        elif whence == io.SEEK_END:
            self._pos = self._size + offset
        self._pos = max(0, self._pos)
        return self._pos

    def _blocco(self, indice: int) -> bytes:
        if indice not in self._blocchi:
            inizio = indice * BLOCCO_BYTE
            fine = min(inizio + BLOCCO_BYTE, self._size) - 1
            self._blocchi[indice] = self._fetch(inizio, fine)
            self._ordine.append(indice)
            while len(self._ordine) > BLOCCHI_IN_CACHE:
                self._blocchi.pop(self._ordine.pop(0), None)
        return self._blocchi[indice]

    def read(self, n: int = -1) -> bytes:
        if self._pos >= self._size:
            return b""
        fine = self._size if n is None or n < 0 else min(self._size, self._pos + n)
        pezzi: List[bytes] = []
        while self._pos < fine:
            indice = self._pos // BLOCCO_BYTE
            blocco = self._blocco(indice)
            da = self._pos - indice * BLOCCO_BYTE
            a = min(len(blocco), da + (fine - self._pos))
            pezzo = blocco[da:a]
            if not pezzo:
                break
            pezzi.append(pezzo)
            self._pos += len(pezzo)
        return b"".join(pezzi)

    def readinto(self, buffer) -> int:
        dati = self.read(len(buffer))
        buffer[:len(dati)] = dati
        return len(dati)


def _sorgente_drive(file_id: str):
    """(fetch, size, nome) di un file Drive, con la credenziale della cartella unica."""
    from app.services.drive_cartella_unica import _service

    service = _service()
    meta = service.files().get(
        fileId=file_id, fields="name, size", supportsAllDrives=True,
    ).execute()
    uri = service.files().get_media(fileId=file_id, supportsAllDrives=True).uri

    def fetch(inizio: int, fine: int) -> bytes:
        risposta, contenuto = service._http.request(
            uri, "GET", headers={"Range": f"bytes={inizio}-{fine}"},
        )
        if int(risposta.status) not in (200, 206):
            raise OSError(f"Drive ha risposto {risposta.status} per i byte {inizio}-{fine}")
        return contenuto

    return fetch, int(meta["size"]), meta.get("name") or file_id


def _voci(archivio: zipfile.ZipFile) -> List[zipfile.ZipInfo]:
    return [v for v in archivio.infolist()
            if not v.is_dir() and not v.filename.startswith("__MACOSX/")]


def _motivo_saltata(voce: zipfile.ZipInfo) -> Optional[str]:
    nome = Path(voce.filename.replace("\\", "/")).name
    suffisso = Path(nome).suffix.lower()
    if not nome or nome.startswith("."):
        return "file di sistema"
    if suffisso == ".zip":
        return "archivio annidato: non si apre"
    if suffisso not in SUFFISSI_AMMESSI:
        return "formato che l'import non legge"
    if voce.file_size > MAX_VOCE_BYTE:
        return "voce oltre 50 MB"
    if voce.file_size and voce.compress_size == 0:
        return "rapporto di compressione non valido"
    if voce.compress_size and voce.file_size / voce.compress_size > MAX_RAPPORTO_COMPRESSIONE:
        return "compressione sospetta"
    return None


@dataclass
class _Voce:
    """Un file da importare, che venga da uno ZIP o da una cartella Drive."""
    percorso: str
    nome: str
    motivo: Optional[str]
    leggi: Callable[[], Awaitable[bytes]]


CARTELLA_MIME = "application/vnd.google-apps.folder"


def _elenca_albero(service, cartella_id: str, nome_radice: str) -> List[Dict[str, Any]]:
    """Tutti i file sotto una cartella Drive (sola lettura), in ordine di percorso."""
    trovati: List[Dict[str, Any]] = []
    coda = [(cartella_id, nome_radice)]
    while coda:
        corrente, base = coda.pop(0)
        token = None
        while True:
            risposta = service.files().list(
                q=f"'{corrente}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, size, md5Checksum)",
                pageSize=1000, pageToken=token,
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            for f in risposta.get("files", []):
                percorso = f"{base}/{f['name']}"
                if f.get("mimeType") == CARTELLA_MIME:
                    coda.append((f["id"], percorso))
                else:
                    trovati.append({**f, "percorso": percorso})
            token = risposta.get("nextPageToken")
            if not token:
                break
    trovati.sort(key=lambda f: (f["percorso"], f["id"]))
    return trovati


def _motivo_file_drive(f: Dict[str, Any]) -> Optional[str]:
    nome = str(f.get("name") or "")
    suffisso = Path(nome).suffix.lower()
    if not nome or nome.startswith("."):
        return "file di sistema"
    if str(f.get("mimeType") or "").startswith("application/vnd.google-apps."):
        return "documento Google: non e' un file"
    if suffisso == ".zip":
        return "archivio annidato: non si apre"
    if suffisso not in SUFFISSI_AMMESSI:
        return "formato che l'import non legge"
    if int(f.get("size") or 0) > MAX_VOCE_BYTE:
        return "file oltre 50 MB"
    return None


def _voci_da_cartella(file_drive: List[Dict[str, Any]]) -> List[_Voce]:
    from app.services.drive_download import scarica_originale

    def lettore(fid: str, md5: Optional[str]):
        return lambda: scarica_originale(fid, md5=md5)

    return [
        _Voce(f["percorso"], f["name"], _motivo_file_drive(f),
              lettore(f["id"], f.get("md5Checksum")))
        for f in file_drive
    ]


def _voci_da_zip(archivio: zipfile.ZipFile) -> List[_Voce]:
    def lettore(voce: zipfile.ZipInfo):
        return lambda: asyncio.to_thread(archivio.read, voce)

    return [
        _Voce(v.filename.replace("\\", "/"), Path(v.filename.replace("\\", "/")).name,
              _motivo_saltata(v), lettore(v))
        for v in _voci(archivio)
    ]


async def _stato_salvato(db, chiave: str) -> Dict[str, Any]:
    return await db["sistema_stato"].find_one({"chiave": chiave}, {"_id": 0}) or {}


async def _salva(db, chiave: str, **campi) -> None:
    await db["sistema_stato"].update_one(
        {"chiave": chiave},
        {"$set": {**campi, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


def _contatori_vuoti() -> Dict[str, int]:
    return {"importati": 0, "gia_presenti": 0, "non_riconosciuti": 0,
            "saltati": 0, "errori": 0}


async def anteprima(archivio: zipfile.ZipFile) -> Dict[str, Any]:
    """Cosa c'e' nello ZIP, senza importare niente (simulazione)."""
    voci = _voci(archivio)
    per_suffisso: Dict[str, int] = {}
    saltate: Dict[str, int] = {}
    for v in voci:
        motivo = _motivo_saltata(v)
        if motivo:
            saltate[motivo] = saltate.get(motivo, 0) + 1
            continue
        s = Path(v.filename).suffix.lower()
        per_suffisso[s] = per_suffisso.get(s, 0) + 1
    return {"dry_run": True, "voci": len(voci), "da_importare": sum(per_suffisso.values()),
            "per_formato": per_suffisso, "saltate_per_motivo": saltate,
            "non_compresso_byte": sum(max(0, v.file_size) for v in voci)}


async def _elabora_voci(
    db, chiave: str, voci: List[_Voce], *, origine: str, impronta: str,
    limite: Optional[int] = None, riparti_se_completato: bool = False,
) -> Dict[str, Any]:
    """Elabora le voci dal cursore in poi. `limite`: al massimo N voci (i test, i lotti)."""
    from app.services.drive_cartella_unica import _smista, esito_del_risultato

    salvato = await _stato_salvato(db, chiave)
    indice = int(salvato.get("indice") or 0)
    contatori = {**_contatori_vuoti(), **(salvato.get("contatori") or {})}
    non_riconosciuti: List[Dict[str, Any]] = list(salvato.get("non_riconosciuti") or [])
    errori: List[Dict[str, Any]] = list(salvato.get("errori") or [])
    if riparti_se_completato and salvato.get("stato") == "completato":
        # Una cartella cambia nel tempo: un nuovo passaggio riguarda tutto, e
        # cio' che e' gia' entrato torna «gia_presenti» senza riscrivere niente.
        indice, contatori, non_riconosciuti, errori = 0, _contatori_vuoti(), [], []
    fatte = 0

    while indice < len(voci) and (limite is None or fatte < limite):
        voce = voci[indice]
        percorso, nome = voce.percorso, voce.nome
        if voce.motivo:
            contatori["saltati"] += 1
        else:
            try:
                dati = await voce.leggi()
                if not dati:
                    raise OSError("contenuto non leggibile da Drive")
                risultato = await _smista(nome, dati, {
                    "archive_filename": origine, "archive_path": percorso,
                    "archive_group": str(Path(percorso).parent).replace("\\", "/"),
                    "archive_sha256": impronta,
                })
                cartella, perche = esito_del_risultato(risultato)
                if risultato.get("tipo_rilevato") == "non_riconosciuto":
                    contatori["non_riconosciuti"] += 1
                    if len(non_riconosciuti) < MAX_ELENCO:
                        non_riconosciuti.append({"percorso": percorso, "motivo": perche})
                elif risultato.get("duplicate"):
                    contatori["gia_presenti"] += 1
                elif risultato.get("success"):
                    contatori["importati"] += 1
                else:
                    contatori["errori"] += 1
                    if len(errori) < MAX_ELENCO:
                        errori.append({"percorso": percorso, "motivo": perche})
            except Exception as exc:  # noqa: BLE001 - una voce guasta non ferma le altre
                contatori["errori"] += 1
                logger.warning("Voce %s di %s non importata: %s: %s",
                               percorso, origine, type(exc).__name__, exc)
                if len(errori) < MAX_ELENCO:
                    errori.append({"percorso": percorso, "motivo": f"{type(exc).__name__}: {exc}"[:300]})
        indice += 1
        fatte += 1
        if fatte % 10 == 0:
            await _salva(db, chiave, stato="in_corso", nome_zip=origine, voci=len(voci),
                         indice=indice, contatori=contatori,
                         non_riconosciuti=non_riconosciuti, errori=errori)

    finito = indice >= len(voci)
    await _salva(db, chiave, stato="completato" if finito else "in_corso", nome_zip=origine,
                 voci=len(voci), indice=indice, contatori=contatori,
                 non_riconosciuti=non_riconosciuti, errori=errori, errore=None)
    return {"voci": len(voci), "indice": indice, "completato": finito, "contatori": contatori}


async def elabora(
    db, file_id: str, archivio: zipfile.ZipFile, *, nome_zip: str = "",
    limite: Optional[int] = None,
) -> Dict[str, Any]:
    """Le voci di uno ZIP, dal cursore in poi."""
    impronta = hashlib.sha256(f"{file_id}:{nome_zip}".encode()).hexdigest()
    esito = await _elabora_voci(
        db, f"{CHIAVE}:{file_id}", _voci_da_zip(archivio), origine=nome_zip,
        impronta=impronta, limite=limite,
    )
    return {"file_id": file_id, **esito}


async def elabora_cartella(
    db, cartella_id: str, file_drive: List[Dict[str, Any]], *, nome: str = "",
    limite: Optional[int] = None,
) -> Dict[str, Any]:
    """I file di una cartella Drive (e sottocartelle), dal cursore in poi."""
    impronta = hashlib.sha256(f"{cartella_id}:{nome}".encode()).hexdigest()
    esito = await _elabora_voci(
        db, f"{CHIAVE}:{cartella_id}", _voci_da_cartella(file_drive), origine=nome,
        impronta=impronta, limite=limite, riparti_se_completato=True,
    )
    return {"file_id": cartella_id, **esito}


def anteprima_cartella(file_drive: List[Dict[str, Any]]) -> Dict[str, Any]:
    per_suffisso: Dict[str, int] = {}
    saltate: Dict[str, int] = {}
    for f in file_drive:
        motivo = _motivo_file_drive(f)
        if motivo:
            saltate[motivo] = saltate.get(motivo, 0) + 1
            continue
        s = Path(str(f.get("name") or "")).suffix.lower()
        per_suffisso[s] = per_suffisso.get(s, 0) + 1
    return {"dry_run": True, "voci": len(file_drive), "da_importare": sum(per_suffisso.values()),
            "per_formato": per_suffisso, "saltate_per_motivo": saltate,
            "byte": sum(int(f.get("size") or 0) for f in file_drive)}


def _tipo_e_nome(file_id: str) -> tuple[str, str]:
    from app.services.drive_cartella_unica import _service

    meta = _service().files().get(
        fileId=file_id, fields="name, mimeType", supportsAllDrives=True,
    ).execute()
    return meta.get("mimeType") or "", meta.get("name") or file_id


async def _esegui(db, file_id: str, dry_run: bool) -> None:
    async with _lock:
        chiave = f"{CHIAVE}:{file_id}"
        try:
            mime, nome = await asyncio.to_thread(_tipo_e_nome, file_id)
            if mime == CARTELLA_MIME:
                from app.services.drive_cartella_unica import _service

                file_drive = await asyncio.to_thread(_elenca_albero, _service(), file_id, nome)
                if dry_run:
                    await _salva(db, f"{chiave}:anteprima", stato="completato", nome_zip=nome,
                                 risultato=anteprima_cartella(file_drive), errore=None)
                else:
                    await elabora_cartella(db, file_id, file_drive, nome=nome)
                return
            fetch, size, nome = await asyncio.to_thread(_sorgente_drive, file_id)
            archivio = await asyncio.to_thread(zipfile.ZipFile, FileDriveARange(fetch, size))
            try:
                if dry_run:
                    esito = await anteprima(archivio)
                    await _salva(db, f"{chiave}:anteprima", stato="completato", nome_zip=nome,
                                 risultato=esito, errore=None)
                else:
                    await elabora(db, file_id, archivio, nome_zip=nome)
            finally:
                archivio.close()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Import da Drive %s fallito", file_id)
            await _salva(db, f"{chiave}:anteprima" if dry_run else chiave, stato="errore",
                         errore=f"{type(exc).__name__}: {exc}"[:500])


async def avvia(db, file_id: str, *, dry_run: bool = True) -> Dict[str, Any]:
    """Avvia in background (§4: oltre 5 minuti il proxy taglia la richiesta)."""
    global _lavoro
    if _lock.locked() or (_lavoro is not None and not _lavoro.done()):
        return {"avviato": False, **await stato(db, file_id)}
    _lavoro = asyncio.create_task(_esegui(db, file_id, dry_run))
    return {"avviato": True, "dry_run": dry_run, "file_id": file_id}


async def importa_cartelle_configurate(db) -> Dict[str, Any]:
    """Giro dello scheduler: le cartelle in `DRIVE_IMPORT_CARTELLE_ID` (ids separati da virgola).

    Vuoto = spento. Una cartella gia' completata non si rilegge prima di un
    giorno: e' un controllo dei file arrivati dopo, non un ciclo continuo.
    """
    import os

    ids = [i.strip() for i in os.getenv("DRIVE_IMPORT_CARTELLE_ID", "").split(",") if i.strip()]
    if not ids:
        return {"saltato": "nessuna cartella configurata"}
    esito: Dict[str, Any] = {}
    for file_id in ids:
        salvato = await _stato_salvato(db, f"{CHIAVE}:{file_id}")
        if salvato.get("stato") == "completato":
            try:
                aggiornato = datetime.fromisoformat(str(salvato.get("updated_at")))
                if (datetime.now(timezone.utc) - aggiornato).total_seconds() < 86400:
                    esito[file_id] = "completato da meno di un giorno"
                    continue
            except ValueError:
                pass
        avviato = await avvia(db, file_id, dry_run=False)
        esito[file_id] = "avviato" if avviato.get("avviato") else "gia' in corso"
        if not avviato.get("avviato"):
            break
    return esito


async def stato(db, file_id: str) -> Dict[str, Any]:
    chiave = f"{CHIAVE}:{file_id}"
    esito = {k: v for k, v in (await _stato_salvato(db, chiave)).items() if k != "chiave"}
    anteprima_salvata = {k: v for k, v in
                         (await _stato_salvato(db, f"{chiave}:anteprima")).items() if k != "chiave"}
    if not esito and not anteprima_salvata:
        return {"stato": "mai_avviato"}
    return {**esito, **({"anteprima": anteprima_salvata} if anteprima_salvata else {})}
