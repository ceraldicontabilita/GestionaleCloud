"""Cartella unica «DATI SOCIETA CERALDI»: l'unico ingresso Drive dei documenti.

Decisione del titolare (25/09/2026): tutto cio' che entra nel gestionale passa
da una sola cartella con tre sottocartelle, e il gestionale legge gli
originali **solo** da li'.

    DATI SOCIETA CERALDI/
        DA ELABORARE   ← si mette qui qualunque documento, di qualunque tipo
        ELABORATE      ← gli originali registrati (archivio piatto: tipo,
                          anno, fornitore stanno nel database)
        ERRORI         ← cio' che non si e' potuto registrare, col motivo
        ARRETRATO      ← estratti conto di un anno sotto ``DRIVE_ESTRATTI_ANNO_MINIMO``
                          (difetto 2026, scelta del titolare): fermi, non errori

Il giro non ha un motore suo: ogni file passa dallo **stesso smistatore di
Documenti > Import** (``upload_documento_automatico`` →
``detect_document_type``), che riconosce il tipo dal contenuto e chiama il
motore esistente (fatture, corrispettivi, F24, quietanze, cedolini, estratti
conto, verbali, bonifici...). Ognuno di quei motori fa gia' la propria
deduplica sui dati.

Niente doppioni fra gli originali: prima di smistare, un file con la stessa
impronta Drive (md5) di un originale gia' in ELABORATE si confronta **byte per
byte**; se e' identico va nel **Cestino** (mai eliminazione permanente,
decisione del 23/09) e il registro dice di chi e' copia. Stesso md5 ma byte
diversi non e' un doppione.

Il registro ``drive_cartella_unica`` tiene una riga per originale
(``id`` = drive_file_id): SHA-256, tipo riconosciuto, esito e i riferimenti
restituiti dal motore. «Vedi documento» apre un originale solo se questo
registro lo conosce in ELABORATE.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REGISTRO = "drive_cartella_unica"
CHIAVE_STATO = "drive_cartella_unica_last_sync"
INBOX, ARCHIVIO, ERRORI = "DA ELABORARE", "ELABORATE", "ERRORI"
# Copie esatte che il Cestino non accetta: un file di proprieta' del titolare
# puo' cestinarlo solo lui (Drive risponde 403 al service account). Restano
# qui, fuori dall'archivio, finche' il titolare non svuota la cartella.
DOPPIONI = "DOPPIONI"
# Estratti conto dell'arretrato tenuti fermi per scelta del titolare: non sono
# errori e non si registrano. Per importarli si abbassa la soglia e si
# riportano i file in DA ELABORARE.
ARRETRATO = "ARRETRATO"
# I tipi di Documenti > Import che sono estratti conto (banca, Nexi, PayPal,
# mutuo, SumUp, export dei terminali POS): le sei fonti del vecchio canale.
TIPI_ESTRATTO = frozenset({
    "estratto_conto", "estratto_conto_nexi", "estratto_conto_paypal",
    "estratto_conto_mutuo", "estratto_conto_sumup", "pos_terminal",
})
CARTELLA_MIME = "application/vnd.google-apps.folder"
# Chiavi del risultato dello smistatore che identificano il record creato.
_CHIAVI_RIFERIMENTO = (
    "invoice_id", "fattura_id", "corrispettivo_id", "f24_id", "quietanza_id",
    "cedolino_id", "doc_id", "bonifico_transfer_id", "verbale_id", "movimento_id",
    "prima_nota_cassa_id", "prima_nota_banca_id",
)

_lock = asyncio.Lock()


def radice() -> Optional[str]:
    return os.getenv("GOOGLE_DRIVE_DATI_FOLDER_ID", "").strip() or None


def import_attivo() -> bool:
    """Interruttore del solo import (``DRIVE_CARTELLA_UNICA_IMPORT=false``).

    Mette in pausa lo smistatore senza togliere la cartella: credenziali,
    «vedi documento» e simulazione continuano a usarla.
    """
    return os.getenv("DRIVE_CARTELLA_UNICA_IMPORT", "true").strip().lower() not in (
        "false", "0", "no", "off")


def attivo() -> bool:
    return bool(radice()) and import_attivo()


def anno_minimo_estratti() -> int:
    """Soglia dell'arretrato; 0 = nessun filtro. Difetto 2026 (scelta del titolare)."""
    try:
        return max(0, int(os.getenv("DRIVE_ESTRATTI_ANNO_MINIMO", "2026")))
    except ValueError:
        return 2026


def _batch() -> int:
    try:
        return max(1, min(int(os.getenv("DRIVE_CARTELLA_UNICA_BATCH", "25")), 200))
    except ValueError:
        return 25


def _service():
    # La credenziale si prova sulla radice della cartella unica, non sulla
    # cartella di un canale: sparita la vecchia cartella fatture, il loader
    # delle fatture falliva e fermava lo smistatore di tutto il resto.
    from app.services.drive_credential_probe import load_credentials_for_folder

    creds, errore = load_credentials_for_folder(radice())
    if creds is None:
        raise RuntimeError(f"credenziali Drive non disponibili: {errore}")
    import google_auth_httplib2
    import httplib2
    from googleapiclient.discovery import build

    # Senza tempo massimo una connessione caduta a meta' lettura tiene fermo
    # il giro per sempre (e il lock con lui): 120 s poi l'errore, e il file
    # torna in coda come guasto di rete.
    http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(timeout=TIMEOUT_DRIVE))
    return build("drive", "v3", http=http, cache_discovery=False)


TIMEOUT_DRIVE = 120


def _cartella(service, parent_id: str, nome: str) -> Optional[str]:
    """La sottocartella ``nome`` di ``parent_id``; se manca la crea."""
    risposta = service.files().list(
        q=(f"name = '{nome}' and '{parent_id}' in parents "
           f"and mimeType = '{CARTELLA_MIME}' and trashed = false"),
        fields="files(id)", pageSize=1,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    trovate = risposta.get("files", [])
    if trovate:
        return trovate[0]["id"]
    creata = service.files().create(
        body={"name": nome, "mimeType": CARTELLA_MIME, "parents": [parent_id]},
        fields="id", supportsAllDrives=True,
    ).execute()
    return creata.get("id")


def _cartelle(service, root: str) -> Dict[str, str]:
    return {nome: _cartella(service, root, nome)
            for nome in (INBOX, ARCHIVIO, ERRORI, DOPPIONI, ARRETRATO)}


# File che il titolare ha chiesto di riguardare ed eliminare a mano
# (``drive_censimento_doppioni``): lo smistatore non li tocca.
PREFISSI_DA_ELIMINARE = ("DUPLICATO DA ELIMINARE - ", "FILE TECNICO DA ELIMINARE - ")


def _elenca(service, parent_id: str, campi: str, limite: Optional[int] = None,
            escludi_marcati: bool = False) -> List[Dict[str, Any]]:
    """Tutti i file (non cartelle) di una cartella, paginando fino in fondo."""
    trovati: List[Dict[str, Any]] = []
    token = None
    filtro = "".join(f" and not name contains '{p.strip()}'" for p in PREFISSI_DA_ELIMINARE) \
        if escludi_marcati else ""
    while True:
        risposta = service.files().list(
            q=f"'{parent_id}' in parents and trashed = false and mimeType != '{CARTELLA_MIME}'{filtro}",
            fields=f"nextPageToken, files({campi})", pageSize=1000 if limite is None else min(limite, 1000),
            orderBy="createdTime", pageToken=token,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        trovati.extend(risposta.get("files", []))
        token = risposta.get("nextPageToken")
        if not token or (limite is not None and len(trovati) >= limite):
            return trovati[:limite] if limite is not None else trovati


def _sposta(service, file_id: str, da: str, a: str, motivo: Optional[str] = None) -> None:
    corpo = {"description": f"Gestionale: {motivo}"[:1000]} if motivo else None
    service.files().update(
        fileId=file_id, addParents=a, removeParents=da, body=corpo,
        fields="id, parents", supportsAllDrives=True,
    ).execute()


def _cestina(service, file_id: str, copia_di: str) -> bool:
    """Cestino (mai eliminazione). Falso se Drive non lo consente (403)."""
    try:
        service.files().update(
            fileId=file_id, supportsAllDrives=True, fields="id, trashed",
            body={"trashed": True, "description": f"Gestionale: copia identica di {copia_di}"},
        ).execute()
        return True
    except Exception as exc:
        if getattr(getattr(exc, "resp", None), "status", None) == 403:
            return False
        raise


class _FileCaricato:
    """Lo stesso oggetto che riceve l'upload di Documenti > Import."""

    def __init__(self, nome: str, contenuto: bytes, source_context: Dict[str, Any]):
        self.filename = nome
        self.file = io.BytesIO(contenuto)
        self.source_context = source_context
        self._contenuto = contenuto

    async def read(self) -> bytes:
        return self._contenuto


async def _smista(nome: str, contenuto: bytes, contesto: Dict[str, Any]) -> Dict[str, Any]:
    from fastapi import HTTPException

    from app.routers.documenti import rileva_tipo_documento, upload_documento_automatico

    # Un tipo non riconosciuto resta su Drive in ERRORI: lo smistatore lo
    # copierebbe in base64 dentro documents_inbox, una seconda copia
    # dell'originale che la cartella unica esiste per evitare.
    tipo = await rileva_tipo_documento(nome, contenuto)
    if tipo == "auto":
        return {"success": False, "tipo_rilevato": "non_riconosciuto"}
    if tipo in TIPI_ESTRATTO and (minimo := anno_minimo_estratti()):
        from app.services.classificazione_estratti import anno_documento

        # L'anno si prova dal nome o dal contenuto (gli estratti Nexi si
        # chiamano solo «Estratto_Conto.pdf»); senza anno il file prosegue.
        anno = await asyncio.to_thread(anno_documento, nome, contenuto)
        if anno is not None and anno < minimo:
            return {"success": False, "tipo_rilevato": tipo, "arretrato": True,
                    "anno": anno, "anno_minimo": minimo}
    try:
        return await upload_documento_automatico(file=_FileCaricato(nome, contenuto, contesto))
    except HTTPException as exc:
        return {"success": False, "message": str(exc.detail), "http_status": exc.status_code}


def esito_del_risultato(risultato: Dict[str, Any]) -> tuple[str, str]:
    """(cartella di destinazione, motivo). Registrato o gia' presente → archivio."""
    if risultato.get("tipo_rilevato") == "non_riconosciuto":
        return ERRORI, "tipo di documento non riconosciuto"
    if risultato.get("arretrato"):
        return ARRETRATO, (f"estratto del {risultato.get('anno')}: arretrato fermo "
                           f"(anno minimo {risultato.get('anno_minimo')})")
    if risultato.get("success") or risultato.get("duplicate"):
        return ARCHIVIO, ""
    return ERRORI, str(risultato.get("message") or risultato.get("error") or "registrazione non riuscita")[:500]


_ESTENSIONI_XML = (".xml", ".xml.p7m", ".p7m", ".zip")


_BUSTA_PAGA = re.compile(r"LUL|CEDOLIN|BUSTA|LIBRO\s*UNICO|TREDICESIMA|QUATTORDICESIMA", re.IGNORECASE)


def ordina_coda(coda: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Prima le buste paga, poi XML (fatture, chiusure RT) e ZIP, poi il resto.

    Le buste in testa (decisione del titolare, 28/09/2026): finche' la busta
    definitiva non e' in ELABORATE, la sua stampa di controllo resta su Drive.
    Un XML si registra in un attimo e fa i conti del mese; un PDF bancario puo'
    tenere il giro per minuti. Fra gli XML vince l'ultimo caricato: nella radice
    ce ne sono oltre mille di vecchi, e le fatture appena messe dal titolare non
    devono aspettare quelle. Il resto mantiene l'ordine di elenco (radice prima
    di DA ELABORARE, il piu' vecchio prima).
    """
    def xml(f):
        return str(f.get("name") or "").lower().endswith(_ESTENSIONI_XML)

    buste = [f for f in coda if e_busta(f)]
    recenti = sorted((f for f in coda if xml(f)),
                     key=lambda f: str(f.get("createdTime") or ""), reverse=True)
    return buste + recenti + [f for f in coda if not e_busta(f) and not xml(f)]


def e_busta(f: Dict[str, Any]) -> bool:
    nome = str(f.get("name") or "")
    return nome.lower().endswith(".pdf") and bool(_BUSTA_PAGA.search(nome))


# Buste lette insieme (decisione del titolare, 28/09/2026). Solo le buste: la
# loro scrittura e' serializzata per dipendente e periodo
# (``cedolini_manager.registra_busta``); fatture e altri documenti restano uno
# alla volta, perche' la loro dedup non e' protetta contro due letture parallele.
BUSTE_IN_PARALLELO = 3
_DUP_NOME = re.compile(r"\s*\(dup\d+\)|\s*\(\d+\)", re.IGNORECASE)


async def _registra(db, file_id: str, **campi) -> None:
    campi["aggiornato_il"] = datetime.now(timezone.utc).isoformat()
    await db[REGISTRO].update_one(
        {"id": file_id}, {"$set": {"id": file_id, "drive_file_id": file_id, **campi}}, upsert=True,
    )


# Motivo che lo smistatore scriveva per una busta gia' registrata (stessa
# busta da un'altra copia del PDF): non era un errore, e quei file vanno
# riletti. Il motore ora la dichiara «gia' in archivio» e la manda in ELABORATE.
_BUSTE_GIA_PRESENTI = re.compile(r"^Cedolino non registrato: \d+ buste lette$")
# Un guasto di connessione durante la lettura non e' un difetto del file: si rilegge.
_GUASTO_DI_RETE = re.compile(r"^(SSLError|ConnectionError|ConnectionResetError|TimeoutError|timeout|"
                             r"RemoteDisconnected|BrokenPipeError|IncompleteRead)\b")


async def rimetti_in_coda_buste_gia_presenti(db, service, cartelle: Dict[str, str],
                                             limite: Optional[int] = None) -> int:
    """Riporta in DA ELABORARE le buste finite in ERRORI solo perche' gia' registrate.

    Tutte in una volta (decisione del titolare): spostarle costa solo metadati,
    la lettura poi la fa il giro a lotti.
    """
    righe = await db[REGISTRO].find(
        {"cartella": {"$in": [ERRORI, ARRETRATO]}},
        {"_id": 0, "id": 1, "nome": 1, "motivo": 1, "tipo": 1, "cartella": 1},
    ).to_list(None)
    rimessi = 0
    for riga in righe:
        if limite is not None and rimessi >= limite:
            break
        motivo = str(riga.get("motivo") or "")
        if riga.get("cartella") == ARRETRATO:
            # Una busta presa per estratto conto (cita la banca d'appoggio) e
            # parcheggiata fra l'arretrato degli estratti: va riletta da busta.
            if not e_busta({"name": riga.get("nome")}):
                continue
        else:
            gia_presente = riga.get("tipo") == "cedolino" and _BUSTE_GIA_PRESENTI.match(motivo)
            if not gia_presente and not _GUASTO_DI_RETE.match(motivo):
                continue
        try:
            await asyncio.to_thread(_sposta, service, riga["id"], cartelle[riga["cartella"]],
                                    cartelle[INBOX], "da rileggere")
            await _registra(db, riga["id"], cartella=INBOX, esito="rimesso_in_coda",
                            motivo="busta gia' in archivio, non un errore")
            rimessi += 1
        except Exception as exc:
            logger.warning("[cartella-unica] %s non rimesso in coda: %s: %s",
                           riga.get("nome") or riga["id"], type(exc).__name__, exc)
            await _registra(db, riga["id"], cartella="SCONOSCIUTA", esito="non_trovato",
                            motivo=f"non piu' in ERRORI: {type(exc).__name__}")
    return rimessi


async def giro(db) -> Dict[str, Any]:
    """Un giro sulla radice e poi su DA ELABORARE: al piu' ``DRIVE_CARTELLA_UNICA_BATCH`` file."""
    if not radice():
        return {"saltato": "GOOGLE_DRIVE_DATI_FOLDER_ID non impostata"}
    if not import_attivo():
        return {"saltato": "import in pausa (DRIVE_CARTELLA_UNICA_IMPORT=false)"}
    if _lock.locked():
        return {"saltato": "giro_in_corso"}
    async with _lock:
        return await _giro(db)


async def _giro(db) -> Dict[str, Any]:
    from app.services.drive_download import scarica_bytes

    iniziato = datetime.now(timezone.utc).isoformat()
    esito: Dict[str, Any] = {"letti": 0, "elaborati": 0, "errori": 0, "doppioni_cestinati": 0, "arretrati": 0,
                             "dettagli": [], "iniziato_at": iniziato}
    try:
        service = await asyncio.to_thread(_service)
        cartelle = await asyncio.to_thread(_cartelle, service, radice())
        esito["buste_rimesse_in_coda"] = await rimetti_in_coda_buste_gia_presenti(db, service, cartelle)
        campi = "id, name, md5Checksum, size, mimeType, createdTime"
        # Prima i file lasciati sciolti nella radice, poi DA ELABORARE
        # (decisione del titolare, 26/09/2026): la cartella unica si usa come
        # calderone e nessuno deve smistare a mano. Le sottocartelle restano
        # escluse da _elenca. Si elenca tutto (solo metadati) per poter mettere
        # in testa le fatture e le chiusure RT: erano dietro centinaia di PDF.
        in_coda = [{**f, "_da": radice()} for f in await asyncio.to_thread(
            _elenca, service, radice(), campi, None, True)]
        in_coda += [{**f, "_da": cartelle[INBOX]} for f in await asyncio.to_thread(
            _elenca, service, cartelle[INBOX], campi, None, True)]
        esito["in_coda_totale"] = len(in_coda)
        in_coda = ordina_coda(in_coda)[:_batch()]
        archivio = await asyncio.to_thread(_elenca, service, cartelle[ARCHIVIO], "id, md5Checksum")
    except Exception as exc:
        esito["errore"] = f"{type(exc).__name__}: {exc}"
        logger.warning("[cartella-unica] giro non avviato: %s", esito["errore"])
        await _salva_stato(db, esito)
        return esito

    per_md5: Dict[str, List[str]] = {}
    for f in archivio:
        if f.get("md5Checksum"):
            per_md5.setdefault(f["md5Checksum"], []).append(f["id"])

    async def lavora(f: Dict[str, Any], drive=None) -> None:
        # La connessione Drive (httplib2) non regge due thread insieme: ogni
        # lettura parallela usa la sua, quella del giro resta per i file in fila.
        drive = drive or service
        esito["letti"] += 1
        fid, nome = f["id"], f.get("name") or f["id"]
        try:
            contenuto = await asyncio.to_thread(scarica_bytes, drive, fid)
            sha256 = hashlib.sha256(contenuto).hexdigest()
            copia_di = None
            for candidato in per_md5.get(f.get("md5Checksum") or "", []):
                if await asyncio.to_thread(scarica_bytes, drive, candidato) == contenuto:
                    copia_di = candidato
                    break
            if copia_di:
                cartella = "CESTINO"
                if not await asyncio.to_thread(_cestina, drive, fid, copia_di):
                    cartella = DOPPIONI
                    await asyncio.to_thread(_sposta, drive, fid, f["_da"], cartelle[DOPPIONI],
                                            f"copia identica di {copia_di}")
                await _registra(db, fid, nome=nome, sha256=sha256, esito="doppione_cestinato",
                                cartella=cartella, duplicato_di=copia_di)
                esito["doppioni_cestinati"] += 1
                esito["dettagli"].append({"file": nome, "esito": "doppione", "copia_di": copia_di,
                                          "cartella": cartella})
                return

            contesto = {"channel": "drive_cartella_unica", "drive_file_id": fid,
                        "drive_parent_id": cartelle[ARCHIVIO], "source_sha256": sha256}
            risultato = await _smista(nome, contenuto, contesto)
            destinazione, motivo = esito_del_risultato(risultato)
            await asyncio.to_thread(_sposta, drive, fid, f["_da"], cartelle[destinazione], motivo or None)
            riferimenti = {k: risultato[k] for k in _CHIAVI_RIFERIMENTO if risultato.get(k)}
            await _registra(
                db, fid, nome=nome, sha256=sha256, md5=f.get("md5Checksum"),
                tipo=risultato.get("tipo_rilevato"), cartella=destinazione,
                esito={ARCHIVIO: "elaborato", ARRETRATO: "arretrato"}.get(destinazione, "errore"),
                gia_presente=bool(risultato.get("duplicate")), motivo=motivo or None,
                riferimenti=riferimenti,
            )
            if destinazione == ARCHIVIO:
                esito["elaborati"] += 1
                if f.get("md5Checksum"):
                    per_md5.setdefault(f["md5Checksum"], []).append(fid)
            elif destinazione == ARRETRATO:
                esito["arretrati"] += 1
            else:
                esito["errori"] += 1
            esito["dettagli"].append({"file": nome, "tipo": risultato.get("tipo_rilevato"),
                                      "esito": destinazione, "motivo": motivo or None})
        except Exception as exc:
            motivo = f"{type(exc).__name__}: {exc}"[:500]
            logger.warning("[cartella-unica] %s non elaborato: %s", nome, motivo)
            esito["errori"] += 1
            esito["dettagli"].append({"file": nome, "esito": ERRORI, "motivo": motivo})
            try:
                await asyncio.to_thread(_sposta, drive, fid, f["_da"], cartelle[ERRORI], motivo)
                await _registra(db, fid, nome=nome, cartella=ERRORI, esito="errore", motivo=motivo)
            except Exception as exc2:
                logger.warning("[cartella-unica] %s non spostato in ERRORI: %s: %s",
                               nome, type(exc2).__name__, exc2)
    blocchi: Dict[str, asyncio.Lock] = {}
    parallelo = asyncio.Semaphore(BUSTE_IN_PARALLELO)
    buste = [f for f in in_coda if e_busta(f)]
    connessioni: "asyncio.Queue" = asyncio.Queue()
    if buste:
        for _ in range(min(BUSTE_IN_PARALLELO, len(buste))):
            connessioni.put_nowait(await asyncio.to_thread(_service))

    async def lavora_busta(f: Dict[str, Any]) -> None:
        # Due copie dello stesso file o della stessa busta non si leggono insieme:
        # il confronto col gia' archiviato deve vedere la prima gia' registrata.
        chiave_nome = "nome:" + _DUP_NOME.sub("", str(f.get("name") or "")).strip().lower()
        chiave_md5 = "md5:" + str(f.get("md5Checksum") or f["id"])
        async with parallelo, blocchi.setdefault(chiave_nome, asyncio.Lock()), \
                blocchi.setdefault(chiave_md5, asyncio.Lock()):
            drive = await connessioni.get()
            try:
                await lavora(f, drive)
            finally:
                connessioni.put_nowait(drive)

    await asyncio.gather(*(lavora_busta(f) for f in buste))
    for f in in_coda:
        if not e_busta(f):
            await lavora(f)
    esito["dettagli"] = esito["dettagli"][:100]
    esito["restanti"] = max(0, int(esito.get("in_coda_totale") or 0) - esito["letti"])
    await _salva_stato(db, esito)
    return esito


_svuotamento: Dict[str, Any] = {"in_corso": False}


def svuotamento_in_corso() -> bool:
    return bool(_svuotamento.get("in_corso"))


async def svuota(db, *, max_giri: int = 60) -> Dict[str, Any]:
    """Un giro dopo l'altro finche' la cartella non e' vuota.

    Il job dei 15 minuti prende un lotto per volta; questo e' il pulsante
    «importa tutto adesso» di Documenti > Import. Si ferma quando non resta
    niente, quando un giro non legge nulla o fallisce (un file che torna
    sempre indietro non lo fa girare all'infinito).
    """
    if _svuotamento.get("in_corso"):
        return {"saltato": "svuotamento_in_corso"}
    _svuotamento["in_corso"] = True
    totale = {"giri": 0, "letti": 0, "elaborati": 0, "errori": 0, "doppioni_cestinati": 0}
    try:
        for _ in range(max_giri):
            esito = await giro(db)
            if esito.get("saltato") or esito.get("errore"):
                totale["fermato_da"] = esito.get("saltato") or esito.get("errore")
                break
            totale["giri"] += 1
            for chiave in ("letti", "elaborati", "errori", "doppioni_cestinati"):
                totale[chiave] += int(esito.get(chiave) or 0)
            totale["restanti"] = int(esito.get("restanti") or 0)
            if not esito.get("letti") or not totale["restanti"]:
                break
        return totale
    finally:
        _svuotamento["in_corso"] = False


async def _salva_stato(db, esito: Dict[str, Any]) -> None:
    ora = datetime.now(timezone.utc).isoformat()
    try:
        await db["sistema_stato"].update_one(
            {"chiave": CHIAVE_STATO},
            {"$set": {"chiave": CHIAVE_STATO, "valore": ora, "updated_at": ora,
                      "last_error": esito.get("errore"), "last_result": esito}},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("[cartella-unica] stato non salvato: %s: %s", type(exc).__name__, exc)


async def originale(db, drive_file_id: Optional[str] = None,
                    sha256: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Il documento da aprire, solo se e' un originale della cartella unica.

    Si cerca per id Drive oppure per SHA-256 del contenuto (l'impronta che i
    motori conservano come ``source_sha256``): mai per nome.
    """
    if drive_file_id:
        filtro = {"id": drive_file_id, "cartella": ARCHIVIO}
    elif sha256:
        filtro = {"sha256": sha256.strip().lower(), "cartella": ARCHIVIO}
    else:
        return None
    riga = await db[REGISTRO].find_one(filtro, {"_id": 0})
    if not riga:
        return None
    drive_file_id = riga["id"]
    from app.services.drive_download import scarica_bytes

    service = await asyncio.to_thread(_service)
    try:
        meta = await asyncio.to_thread(
            lambda: service.files().get(fileId=drive_file_id, fields="name, mimeType, trashed",
                                        supportsAllDrives=True).execute())
    except Exception as exc:
        if getattr(getattr(exc, "resp", None), "status", None) != 404:
            raise
        meta = {"trashed": True}
    if meta.get("trashed"):
        # Un protocollo non dimentica: l'originale sparito da Drive resta nel
        # registro come «rimosso», con la data, e non si apre piu'.
        await _registra(db, drive_file_id, cartella="RIMOSSO", esito="rimosso",
                        rimosso_il=datetime.now(timezone.utc).isoformat())
        return None
    contenuto = await asyncio.to_thread(scarica_bytes, service, drive_file_id)
    return {"nome": meta.get("name") or riga.get("nome"), "mime": meta.get("mimeType"),
            "contenuto": contenuto}
