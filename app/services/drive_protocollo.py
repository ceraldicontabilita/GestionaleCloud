"""Protocollo-indice vivo dei documenti su Google Drive.

Una riga per file sotto la radice GESTIONALE nella tabella relazionale
``gestionale.protocollo_drive`` (asyncpg, non l'archivio documentale a RPC:
30.000 righe di inventario non vanno idratate in memoria a ogni avvio).

Il giro periodico RICONCILIA Drive con la tabella, non accoda:
- file nuovo            -> riga nuova;
- file cambiato         -> riga aggiornata (nome, cartella, hash, date);
- file sparito da Drive -> riga marcata ``stato='rimosso'`` con la data,
                           MAI cancellata. E' un protocollo: deve ricordare
                           che il documento e' esistito, con il suo hash.

L'hash MD5 arriva dall'API Drive (``md5Checksum``): i duplicati certi si
trovano senza scaricare nulla. Le impronte dei documenti gia' in archivio
(cedolini e bonifici HR, allegati fattura) si calcolano una volta sola nel DB
(``gestionale.md5_base64_sicuro``) e finiscono in ``protocollo_impronte``:
cosi' ogni file Drive puo' essere collegato al documento del gestionale che lo
contiene, per contenuto e non per nome.

La cancellazione fisica non esiste qui: i duplicati si SPOSTANO in quarantena
(``GOOGLE_DRIVE_QUARANTENA_FOLDER_ID``) solo su richiesta esplicita, mai in
automatico, e mai la copia canonica.
"""
from __future__ import annotations

import asyncio
import logging
import posixpath
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.config import settings
from app.services import postgres_diretto

logger = logging.getLogger(__name__)

CARTELLA_MIME = "application/vnd.google-apps.folder"
CAMPI_LIST = (
    "nextPageToken, files(id, name, mimeType, size, md5Checksum, "
    "createdTime, modifiedTime, parents, webViewLink)"
)
PAGINA_DRIVE = 1000
LOTTO_UPSERT = 1000
# Cartelle che non devono mai vincere come copia canonica di un duplicato.
PREFISSI_NON_CANONICI = ("90_ARCHIVIO_STORICO/", "00_DA_CLASSIFICARE/", "_QUARANTENA")
# Cartelle strutturali che non identificano mai il soggetto di un documento
# (stati lifecycle e sotto-sezioni del fascicolo dipendente).
CARTELLE_NON_SOGGETTO = frozenset({
    "da elaborare", "elaborate", "errori",
    "bonifici", "certificazioni uniche", "contratti", "documenti",
})
_ANNO_RE = re.compile(r"(?<!\d)(20[0-3]\d)(?!\d)")
_sync_lock = asyncio.Lock()


# ── configurazione ────────────────────────────────────────────────────────────

def abilitato() -> bool:
    return bool(settings.PROTOCOLLO_DRIVE_ENABLED)


def radice() -> Optional[str]:
    return (settings.GOOGLE_DRIVE_GESTIONALE_ROOT_FOLDER_ID or "").strip() or None


def cartella_quarantena() -> Optional[str]:
    return (settings.GOOGLE_DRIVE_QUARANTENA_FOLDER_ID or "").strip() or None


def costruisci_service():
    """Client Drive v3 del service account (stesso delle altre ingest)."""
    from app.services.drive_document_index import build_drive_service

    return build_drive_service()


# ── funzioni pure (testabili senza rete) ──────────────────────────────────────

def anno_da(nome: str, cartelle: Sequence[str]) -> Optional[int]:
    """Anno del documento: prima una cartella che E' un anno, poi il nome file."""
    for cartella in reversed(list(cartelle)):
        if re.fullmatch(r"20[0-3]\d", cartella.strip()):
            return int(cartella.strip())
    trovati = _ANNO_RE.findall(nome or "")
    if trovati:
        return int(trovati[-1])
    for cartella in reversed(list(cartelle)):
        trovati = _ANNO_RE.findall(cartella)
        if trovati:
            return int(trovati[-1])
    return None


def estensione_di(nome: str) -> Optional[str]:
    base, ext = posixpath.splitext(nome or "")
    return ext[1:].lower() or None if base else None


def _ts(valore: Any) -> Optional[datetime]:
    if not valore:
        return None
    try:
        return datetime.fromisoformat(str(valore).replace("Z", "+00:00"))
    except ValueError:
        return None


def deriva_riga(file: Dict[str, Any], cartelle: Sequence[str]) -> Dict[str, Any]:
    """Riga di protocollo da un file Drive e dal percorso delle cartelle
    (nomi, dalla prima sotto la radice fino alla cartella del file)."""
    cartelle = [c for c in cartelle if c]
    nome = file.get("name") or ""
    percorso = "/".join([*cartelle, nome])
    parents = file.get("parents") or []
    dimensione = file.get("size")
    return {
        "drive_id": file["id"],
        "nome": nome,
        "mime": file.get("mimeType"),
        "estensione": estensione_di(nome),
        "dimensione": int(dimensione) if dimensione not in (None, "") else None,
        "md5": file.get("md5Checksum"),
        "parent_id": parents[0] if parents else None,
        "percorso": percorso,
        "area": cartelle[0] if cartelle else None,
        "categoria": cartelle[1] if len(cartelle) > 1 else None,
        "anno": anno_da(nome, cartelle),
        "creato_drive": _ts(file.get("createdTime")),
        "modificato_drive": _ts(file.get("modifiedTime")),
        "link": file.get("webViewLink") or f"https://drive.google.com/file/d/{file['id']}/view",
    }


def scegli_canonico(gruppo: Iterable[Dict[str, Any]]) -> str:
    """Fra copie con lo stesso MD5, la canonica: fuori da archivio storico/
    quarantena/da classificare, poi la piu' vecchia su Drive, poi il percorso
    piu' corto, poi l'id. Deterministico: due giri danno lo stesso esito."""
    def chiave(riga: Dict[str, Any]):
        percorso = riga.get("percorso") or ""
        scartata = any(percorso.startswith(p) for p in PREFISSI_NON_CANONICI)
        creato = riga.get("creato_drive") or datetime.max.replace(tzinfo=timezone.utc)
        return (scartata, creato, len(percorso), riga.get("drive_id") or "")

    return min(gruppo, key=chiave)["drive_id"]


def riga_pubblica(riga: Dict[str, Any]) -> Dict[str, Any]:
    """Forma compatibile con il tab 'Indice Drive' del hub Documenti."""
    percorso = riga.get("percorso") or ""
    cartelle = percorso.split("/")[:-1]
    # Il soggetto e' l'ultima cartella "parlante": per un cedolino in
    # DIPENDENTI/ROSSI MARIO/ELABORATE il soggetto e' ROSSI MARIO, non lo
    # stato lifecycle ne' la sotto-sezione del fascicolo (BONIFICI, ...).
    parlanti = [c for c in cartelle if c.casefold() not in CARTELLE_NON_SOGGETTO]
    soggetto = parlanti[-1] if parlanti else None
    stato = "RIMOSSO" if riga.get("stato") == "rimosso" else (
        "DUPLICATO" if riga.get("duplicato_di") else "ATTIVO")
    dimensione = riga.get("dimensione")
    modificato = riga.get("modificato_drive")
    pezzi = []
    if dimensione:
        pezzi.append(f"{dimensione / 1024:.0f} KB")
    if modificato:
        pezzi.append("modificato " + modificato.strftime("%d/%m/%Y"))
    if riga.get("collegamento_tipo"):
        pezzi.append("collegato: " + str(riga["collegamento_tipo"]))
    return {
        "document_id": riga.get("drive_id"),
        "domain": riga.get("area"),
        "category": riga.get("categoria"),
        "subject": soggetto,
        "year": riga.get("anno"),
        "filename": riga.get("nome"),
        "display_title": posixpath.splitext(riga.get("nome") or "")[0] or riga.get("nome"),
        "extension": riga.get("estensione"),
        "size_bytes": dimensione,
        "md5": riga.get("md5"),
        "sha256": None,
        "drive_path": percorso,
        "drive_url": riga.get("link"),
        "status": stato,
        "summary": " · ".join(pezzi),
        "duplicate_of": riga.get("duplicato_di"),
        "linked_type": riga.get("collegamento_tipo"),
        "linked_id": riga.get("collegamento_id"),
        "removed_at": riga["rimosso_il"].isoformat() if riga.get("rimosso_il") else None,
    }


# ── lettura Drive ─────────────────────────────────────────────────────────────

def _elenca_figli(service, parent_id: str) -> List[Dict[str, Any]]:
    q = f"'{parent_id}' in parents and trashed = false"
    out: List[Dict[str, Any]] = []
    token = None
    while True:
        res = service.files().list(
            q=q, fields=CAMPI_LIST, pageSize=PAGINA_DRIVE, pageToken=token,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        out.extend(res.get("files", []))
        token = res.get("nextPageToken")
        if not token:
            break
    return out


def percorri_drive(service, radice_id: str) -> List[Dict[str, Any]]:
    """Visita l'intero albero sotto la radice e restituisce le righe di
    protocollo dei soli FILE (le cartelle danno il percorso, non una riga)."""
    righe: List[Dict[str, Any]] = []
    coda: List[tuple] = [(radice_id, [])]
    visitate = set()
    while coda:
        folder_id, cartelle = coda.pop(0)
        if folder_id in visitate:
            continue
        visitate.add(folder_id)
        for item in _elenca_figli(service, folder_id):
            if item.get("mimeType") == CARTELLA_MIME:
                coda.append((item["id"], [*cartelle, item.get("name") or ""]))
            else:
                righe.append(deriva_riga(item, cartelle))
    return righe


# ── scrittura nel protocollo ──────────────────────────────────────────────────

_COLONNE = (
    "drive_id", "nome", "mime", "estensione", "dimensione", "md5", "parent_id",
    "percorso", "area", "categoria", "anno", "creato_drive", "modificato_drive", "link",
)
_TIPI = (
    "text", "text", "text", "text", "bigint", "text", "text",
    "text", "text", "text", "integer", "timestamptz", "timestamptz", "text",
)

SQL_UPSERT = (
    "insert into gestionale.protocollo_drive (" + ", ".join(_COLONNE) + ", stato, rimosso_il, visto_il, aggiornato_il) "
    "select " + ", ".join(f"r.{c}" for c in _COLONNE) + ", 'attivo', null, $15, now() "
    "from unnest(" + ", ".join(f"${i + 1}::{t}[]" for i, t in enumerate(_TIPI)) + ") "
    "as r(" + ", ".join(_COLONNE) + ") "
    "on conflict (drive_id) do update set "
    + ", ".join(f"{c} = excluded.{c}" for c in _COLONNE if c != "drive_id")
    + ", stato = 'attivo', rimosso_il = null, visto_il = excluded.visto_il, aggiornato_il = now() "
    "returning (xmax = 0) as inserito"
)
SQL_RIMOSSI = (
    "update gestionale.protocollo_drive set stato = 'rimosso', rimosso_il = now(), "
    "duplicato_di = null, aggiornato_il = now() "
    "where stato = 'attivo' and visto_il < $1"
)
SQL_DUPLICATI = """
with g as (
  select drive_id,
         first_value(drive_id) over (
           partition by md5
           order by (percorso like '90\\_ARCHIVIO\\_STORICO/%' or percorso like '00\\_DA\\_CLASSIFICARE/%' or percorso like '\\_QUARANTENA%') asc,
                    creato_drive asc nulls last, length(percorso) asc, drive_id asc
         ) as canonico
  from gestionale.protocollo_drive
  where stato = 'attivo' and md5 is not null
)
update gestionale.protocollo_drive p
   set duplicato_di = case when g.canonico = p.drive_id then null else g.canonico end,
       aggiornato_il = now()
  from g
 where g.drive_id = p.drive_id
   and p.duplicato_di is distinct from (case when g.canonico = p.drive_id then null else g.canonico end)
"""
SQL_IMPRONTE = {
    "hr_cedolino": (
        "insert into gestionale.protocollo_impronte (origine, doc_id, md5) "
        "select 'hr_cedolino', c.id, gestionale.md5_base64_sicuro(c.doc->>'pdf_data') from hr.app_cedolini c "
        "where not exists (select 1 from gestionale.protocollo_impronte i where i.origine = 'hr_cedolino' and i.doc_id = c.id)"
    ),
    "hr_bonifico": (
        "insert into gestionale.protocollo_impronte (origine, doc_id, md5) "
        "select 'hr_bonifico', b.id, gestionale.md5_base64_sicuro(b.doc->>'pdf_data') from hr.app_bonifici b "
        "where not exists (select 1 from gestionale.protocollo_impronte i where i.origine = 'hr_bonifico' and i.doc_id = b.id)"
    ),
    # Le fatture passano da una funzione SECURITY DEFINER che espone solo
    # (id, md5): il ruolo applicativo non legge l'archivio documentale.
    "invoice": (
        "insert into gestionale.protocollo_impronte (origine, doc_id, md5) "
        "select 'invoice', f.doc_id, f.md5 from gestionale.impronte_fatture() f "
        "where not exists (select 1 from gestionale.protocollo_impronte i where i.origine = 'invoice' and i.doc_id = f.doc_id)"
    ),
}
SQL_COLLEGA = """
update gestionale.protocollo_drive p
   set collegamento_tipo = i.origine, collegamento_id = i.doc_id, aggiornato_il = now()
  from gestionale.protocollo_impronte i
 where i.md5 = p.md5 and i.md5 is not null
   and p.collegamento_id is null
"""


def _conta(esito: Any) -> int:
    """asyncpg restituisce 'UPDATE 12' / 'INSERT 0 12'."""
    try:
        return int(str(esito).split()[-1])
    except (ValueError, IndexError):
        return 0


async def _upsert(conn, righe: List[Dict[str, Any]], visto_il: datetime) -> tuple[int, int]:
    nuovi = aggiornati = 0
    for inizio in range(0, len(righe), LOTTO_UPSERT):
        lotto = righe[inizio:inizio + LOTTO_UPSERT]
        colonne = [[r.get(c) for r in lotto] for c in _COLONNE]
        esiti = await conn.fetch(SQL_UPSERT, *colonne, visto_il)
        for e in esiti:
            if e["inserito"]:
                nuovi += 1
            else:
                aggiornati += 1
    return nuovi, aggiornati


async def sincronizza(service=None, conn=None) -> Dict[str, Any]:
    """Un giro completo: Drive -> protocollo. Serializzato: mai due giri insieme."""
    if not abilitato():
        return {"esito": "disattivato", "message": "PROTOCOLLO_DRIVE_ENABLED=false"}
    radice_id = radice()
    if not radice_id:
        return {"esito": "non_configurato",
                "message": "Imposta GOOGLE_DRIVE_GESTIONALE_ROOT_FOLDER_ID su Render"}
    dsn = postgres_diretto.dsn()
    if not dsn:
        return {"esito": "non_configurato", "message": "DSN Postgres non configurato"}

    async with _sync_lock:
        avvio = datetime.now(timezone.utc)
        chiudi = conn is None
        conn = conn or await postgres_diretto.connetti(dsn)
        # Un giro rimasto 'in_corso' appartiene a un processo che non c'e' piu'
        # (riavvio/deploy a meta' della scansione, 14/09/2026 18:05): chiuso
        # come 'interrotto', altrimenti resterebbe aperto per sempre.
        await conn.execute(
            "update gestionale.protocollo_drive_giri set fine=now(), esito='interrotto', "
            "dettaglio='processo riavviato durante la scansione' where esito='in_corso'")
        giro_id = await conn.fetchval(
            "insert into gestionale.protocollo_drive_giri (avvio, esito) values ($1, 'in_corso') returning id", avvio)
        try:
            service = service or costruisci_service()
            righe = await asyncio.to_thread(percorri_drive, service, radice_id)
            nuovi, aggiornati = await _upsert(conn, righe, avvio)
            rimossi = _conta(await conn.execute(SQL_RIMOSSI, avvio))
            duplicati = _conta(await conn.execute(SQL_DUPLICATI))
            for origine, sql in SQL_IMPRONTE.items():
                try:
                    await conn.execute(sql)
                except Exception as exc:  # noqa: BLE001 - un'impronta non ferma il giro
                    logger.warning("[PROTOCOLLO-DRIVE] impronte %s saltate: %s", origine, exc)
            collegati = _conta(await conn.execute(SQL_COLLEGA))
            fine = datetime.now(timezone.utc)
            await conn.execute(
                "update gestionale.protocollo_drive_giri set fine=$2, esito='ok', file_visti=$3, nuovi=$4, "
                "aggiornati=$5, rimossi=$6, duplicati=$7, collegati=$8 where id=$1",
                giro_id, fine, len(righe), nuovi, aggiornati, rimossi, duplicati, collegati)
            esito = {"esito": "ok", "giro_id": giro_id, "file_visti": len(righe), "nuovi": nuovi,
                     "aggiornati": aggiornati, "rimossi": rimossi, "duplicati_marcati": duplicati,
                     "collegati": collegati, "durata_s": round((fine - avvio).total_seconds(), 1)}
            logger.info("[PROTOCOLLO-DRIVE] %s", esito)
            return esito
        except Exception as exc:
            await conn.execute(
                "update gestionale.protocollo_drive_giri set fine=now(), esito='errore', dettaglio=$2 where id=$1",
                giro_id, str(exc)[:1000])
            logger.error("[PROTOCOLLO-DRIVE] giro %s fallito: %s", giro_id, exc)
            raise
        finally:
            if chiudi:
                await conn.close()


# ── letture per l'interfaccia ─────────────────────────────────────────────────

async def _connessione():
    dsn = postgres_diretto.dsn()
    if not dsn:
        raise RuntimeError("DSN Postgres non configurato")
    return await postgres_diretto.connetti(dsn)


async def stato() -> Dict[str, Any]:
    conn = await _connessione()
    try:
        tot = await conn.fetchrow(
            "select count(*) filter (where stato='attivo') as attivi, "
            "count(*) filter (where stato='rimosso') as rimossi, "
            "count(*) filter (where stato='attivo' and duplicato_di is not null) as duplicati, "
            "count(*) filter (where stato='attivo' and collegamento_id is not null) as collegati "
            "from gestionale.protocollo_drive")
        aree = await conn.fetch(
            "select area, count(*) as n from gestionale.protocollo_drive where stato='attivo' "
            "group by area order by area nulls last")
        giro = await conn.fetchrow(
            "select id, avvio, fine, esito, file_visti, nuovi, aggiornati, rimossi, duplicati, collegati, dettaglio "
            "from gestionale.protocollo_drive_giri order by id desc limit 1")
        return {
            "configurato": bool(radice()),
            "abilitato": abilitato(),
            "documents": int(tot["attivi"]) if tot else 0,
            "attivi": int(tot["attivi"]) if tot else 0,
            "rimossi": int(tot["rimossi"]) if tot else 0,
            "duplicati": int(tot["duplicati"]) if tot else 0,
            "collegati": int(tot["collegati"]) if tot else 0,
            "aree": [{"area": r["area"], "documenti": int(r["n"])} for r in aree],
            "ultimo_giro": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in dict(giro).items()} if giro else None,
        }
    finally:
        await conn.close()


async def cerca(q: Optional[str] = None, area: Optional[str] = None, anno: Optional[int] = None,
                includi_rimossi: bool = False, solo_duplicati: bool = False, limit: int = 200) -> Dict[str, Any]:
    conn = await _connessione()
    try:
        condizioni, parametri = [], []
        if not includi_rimossi:
            condizioni.append("stato = 'attivo'")
        if solo_duplicati:
            condizioni.append("duplicato_di is not null")
        if q:
            parametri.append(f"%{q}%")
            n = len(parametri)
            condizioni.append(f"(nome ilike ${n} or percorso ilike ${n} or md5 = ${n + 1})")
            parametri.append(q)
        if area:
            parametri.append(area)
            condizioni.append(f"area = ${len(parametri)}")
        if anno:
            parametri.append(int(anno))
            condizioni.append(f"anno = ${len(parametri)}")
        where = (" where " + " and ".join(condizioni)) if condizioni else ""
        parametri.append(max(1, min(int(limit), 500)))
        righe = await conn.fetch(
            "select * from gestionale.protocollo_drive" + where +
            f" order by percorso limit ${len(parametri)}", *parametri)
        totale = await conn.fetchval("select count(*) from gestionale.protocollo_drive where stato='attivo'")
        return {"total_indexed": int(totale or 0), "returned": len(righe),
                "results": [riga_pubblica(dict(r)) for r in righe]}
    finally:
        await conn.close()


async def documento(drive_id: str) -> Optional[Dict[str, Any]]:
    conn = await _connessione()
    try:
        riga = await conn.fetchrow("select * from gestionale.protocollo_drive where drive_id = $1", drive_id)
        if not riga:
            return None
        out = riga_pubblica(dict(riga))
        copie = await conn.fetch(
            "select drive_id, percorso, stato from gestionale.protocollo_drive "
            "where md5 = $1 and md5 is not null and drive_id <> $2 order by percorso", riga["md5"], drive_id)
        out["same_content"] = [dict(c) for c in copie]
        return out
    finally:
        await conn.close()


async def duplicati(limit: int = 200) -> Dict[str, Any]:
    conn = await _connessione()
    try:
        righe = await conn.fetch(
            "select p.md5, p.duplicato_di as canonico, c.percorso as percorso_canonico, "
            "array_agg(p.drive_id order by p.percorso) as copie, array_agg(p.percorso order by p.percorso) as percorsi, "
            "max(p.dimensione) as dimensione "
            "from gestionale.protocollo_drive p join gestionale.protocollo_drive c on c.drive_id = p.duplicato_di "
            "where p.stato='attivo' and p.duplicato_di is not null "
            "group by p.md5, p.duplicato_di, c.percorso order by count(*) desc, c.percorso limit $1", limit)
        gruppi = [{"md5": r["md5"], "canonico": r["canonico"], "percorso_canonico": r["percorso_canonico"],
                   "copie": list(r["copie"]), "percorsi": list(r["percorsi"]), "dimensione": r["dimensione"]}
                  for r in righe]
        spazio = sum((g["dimensione"] or 0) * len(g["copie"]) for g in gruppi)
        return {"gruppi": gruppi, "copie_totali": sum(len(g["copie"]) for g in gruppi),
                "spazio_recuperabile_bytes": spazio}
    finally:
        await conn.close()


async def sposta_in_quarantena(drive_ids: Sequence[str], service=None) -> Dict[str, Any]:
    """Sposta in quarantena SOLO copie marcate duplicate (mai la canonica).
    Nessuna cancellazione: il file resta su Drive, in un'altra cartella."""
    destinazione = cartella_quarantena()
    if not destinazione:
        raise RuntimeError("Imposta GOOGLE_DRIVE_QUARANTENA_FOLDER_ID su Render")
    conn = await _connessione()
    try:
        righe = await conn.fetch(
            "select drive_id, parent_id, percorso, duplicato_di from gestionale.protocollo_drive "
            "where drive_id = any($1::text[]) and stato = 'attivo'", list(drive_ids))
        service = service or costruisci_service()
        spostati, rifiutati = [], []
        for r in righe:
            if not r["duplicato_di"]:
                rifiutati.append({"drive_id": r["drive_id"], "motivo": "non e' una copia duplicata (o e' la canonica)"})
                continue
            try:
                await asyncio.to_thread(
                    lambda rid=r["drive_id"], parent=r["parent_id"]: service.files().update(
                        fileId=rid, addParents=destinazione, removeParents=parent or "",
                        fields="id, parents", supportsAllDrives=True).execute())
                spostati.append(r["drive_id"])
            except Exception as exc:  # noqa: BLE001
                rifiutati.append({"drive_id": r["drive_id"], "motivo": str(exc)[:200]})
        return {"spostati": spostati, "rifiutati": rifiutati, "quarantena": destinazione}
    finally:
        await conn.close()
