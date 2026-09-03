"""Deposito dei cedolini letti dal gestionale nell'archivio dell'app HR.

Decisione del titolare (03/09/2026): UN SOLO sistema cedolini = l'app HR
(AppDipendenti, montata a ``/hr``). Il gestionale continua a scaricare le
buste paga da posta e Drive e a ricavarne la Prima Nota salari, ma l'archivio
che gli utenti vedono e' ``public.app_cedolini`` del Postgres dell'app HR
(``HR_SUPABASE_DB_URL``, fallback ``APPDIPENDENTI_DB_URL`` e
``SUPABASE_DB_URL`` — le stesse variabili lette da ``app/hr/database.py``).

Questo modulo NON tocca il codice di ``app/hr``: scrive direttamente nella
tabella ``app_<collection>`` (colonne ``id text`` + ``doc jsonb``) con la
stessa forma prodotta dall'adattatore ``app/hr/db_supabase.py`` (``id`` =
``doc["id"]``, JSON serializzato con ``default=str``) e con le chiavi che
l'app HR legge davvero:

* portale (``app/hr/routers/portale_buste.py``): ``dipendente_id`` o
  ``codice_fiscale`` per il proprietario, ``nome_dipendente``/
  ``dipendente_nome``, ``mese``, ``anno``, ``competenza``, ``netto``,
  ``lordo``, ``filename``/``pdf_filename``, ``pdf_data`` (base64);
* gestione (``app/hr/routers/dipendenti_cloud/__init__.py``, ``/buste-paga``):
  ``id``, ``dipendente_id``, ``nome_dipendente``, ``mese``, ``anno``,
  ``lordo``, ``netto``, ``trattenute``, ``stato``, ``created_at``.

I 1291 documenti gia' presenti nell'archivio HR hanno ``mese``/``anno``
numerici, ``competenza`` ``"YYYY-MM"``, ``competenze``/``trattenute``
numerici, ``tipo_cedolino`` ``ordinario``/``tredicesima``/``quattordicesima``,
``fonte`` testuale e ``parser_template`` con i nomi dei modelli
(``zucchetti_new``, ``csc_napoli``, ``zucchetti_classic``, ``teamsystem``):
il mapping qui sotto produce esattamente quella forma.

Regole:
* dedup su (CF maiuscolo, anno, mese, tipo) e su ``cedolino_dedup_key``
  (chiave documentale del gestionale, conservata anche nel documento HR):
  un cedolino gia' presente in HR NON viene mai sovrascritto;
* ``dipendente_id``/``dipendente_nome`` risolti da ``app_dipendenti`` per
  codice fiscale (mai dagli id del gestionale, che sono un altro spazio);
* se nessuna DSN e' configurata il deposito e' un no-op segnalato una volta
  sola nel log: l'ingestione contabile non deve mai fallire per l'HR.

CLI (prova a secco sull'intero registro ``cedolini`` del gestionale)::

    python -m app.services.hr_cedolini_deposito --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Stesso ordine di ricerca di app/hr/database.py (_env).
ENV_DSN_HR = ("HR_SUPABASE_DB_URL", "APPDIPENDENTI_DB_URL", "SUPABASE_DB_URL")

TABELLA_CEDOLINI = 'public."app_cedolini"'
TABELLA_DIPENDENTI = 'public."app_dipendenti"'

FONTE_HR = "gestionale_cloud"

# Nomi modello riconosciuti dall'app HR (parser multi-template originale);
# `formato_rilevato` del gestionale usa gli stessi identificatori.
PARSER_TEMPLATE_HR = {"zucchetti_new", "zucchetti_classic", "csc_napoli", "teamsystem"}

# L'app HR archivia la mensilita' ordinaria come "ordinario" (1200+ documenti);
# il gestionale la chiama "mensile".
_TIPI_HR = {
    "": "ordinario",
    "mensile": "ordinario",
    "ordinario": "ordinario",
    "tredicesima": "tredicesima",
    "quattordicesima": "quattordicesima",
}

TIMEOUT_CONNESSIONE = 10
TIMEOUT_COMANDO = 60

_avviso_non_configurato_emesso = False

_SQL_DIPENDENTE = (
    "SELECT doc FROM " + TABELLA_DIPENDENTI +
    " WHERE upper(doc->>'codice_fiscale') = $1"
    " ORDER BY (doc->>'attivo') = 'true' DESC, doc->>'created_at' DESC NULLS LAST"
    " LIMIT 1"
)

_SQL_ESISTENTI = (
    "SELECT id, doc->>'tipo_cedolino' AS tipo, doc->>'cedolino_dedup_key' AS dedup_key"
    " FROM " + TABELLA_CEDOLINI +
    " WHERE (upper(doc->>'codice_fiscale') = $1"
    "        AND doc->>'anno' ~ '^[0-9]+$' AND (doc->>'anno')::int = $2"
    "        AND doc->>'mese' ~ '^[0-9]+$' AND (doc->>'mese')::int = $3)"
    "    OR ($4 <> '' AND doc->>'cedolino_dedup_key' = $4)"
)

_SQL_INSERISCI = (
    "INSERT INTO " + TABELLA_CEDOLINI + " (id, doc) VALUES ($1, $2::jsonb)"
)


# ── configurazione e connessione ─────────────────────────────────────────────

def dsn_hr() -> Optional[str]:
    """DSN Postgres dell'app HR, letta ad ogni chiamata (mai cachata)."""
    for nome in ENV_DSN_HR:
        valore = os.environ.get(nome)
        if valore:
            return valore
    return None


async def connetti_hr(dsn: str):
    """Apre una connessione asyncpg con timeout. Punto unico da sostituire nei test."""
    import asyncpg

    return await asyncpg.connect(
        dsn, timeout=TIMEOUT_CONNESSIONE, command_timeout=TIMEOUT_COMANDO
    )


def _segnala_non_configurato() -> None:
    global _avviso_non_configurato_emesso
    if not _avviso_non_configurato_emesso:
        _avviso_non_configurato_emesso = True
        logger.warning(
            "[HR deposito] nessuna DSN HR configurata (%s): i cedolini restano "
            "solo nel gestionale finche' la variabile non viene impostata",
            "/".join(ENV_DSN_HR),
        )


# ── mapping gestionale -> HR ─────────────────────────────────────────────────

def _numero(*valori: Any) -> Optional[float]:
    for v in valori:
        if v is None or v == "" or isinstance(v, bool):
            continue
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            continue
    return None


def _intero(v: Any) -> Optional[int]:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _codice_fiscale(cedolino: Dict[str, Any]) -> str:
    for chiave in ("codice_fiscale", "dipendente_cf", "cf"):
        valore = cedolino.get(chiave)
        if valore:
            return str(valore).strip().upper()
    return ""


def _anno_mese(cedolino: Dict[str, Any]):
    """(anno, mese) dai campi espliciti, da ``periodo`` dict/stringa o da
    ``periodo_anno``/``periodo_mese`` (forme usate dai vari writer del gestionale)."""
    anno = _intero(cedolino.get("anno"))
    mese = _intero(cedolino.get("mese"))
    if anno and mese:
        return anno, mese
    periodo = cedolino.get("periodo")
    if isinstance(periodo, dict):
        anno = anno or _intero(periodo.get("anno"))
        mese = mese or _intero(periodo.get("mese"))
    elif periodo:
        from app.services.cedolini_canonico import _anno_mese as _da_stringa

        a, m = _da_stringa({"periodo": periodo})
        anno = anno or _intero(a)
        mese = mese or _intero(m)
    anno = anno or _intero(cedolino.get("periodo_anno"))
    mese = mese or _intero(cedolino.get("periodo_mese"))
    return anno, mese


def tipo_cedolino_hr(valore: Any) -> str:
    tipo = str(valore or "").strip().lower()
    return _TIPI_HR.get(tipo, tipo)


def _pdf_base64(valore: Any) -> Optional[str]:
    if not valore:
        return None
    if isinstance(valore, (bytes, bytearray)):
        return base64.b64encode(bytes(valore)).decode("ascii")
    return str(valore)


def mappa_cedolino_per_hr(cedolino: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Documento nella forma di ``app_cedolini`` (senza ``id``/``created_at``/
    ``dipendente_id``, aggiunti al deposito). ``None`` se mancano CF, anno o mese."""
    cf = _codice_fiscale(cedolino)
    anno, mese = _anno_mese(cedolino)
    if not cf or not anno or not mese:
        return None

    nome = (
        cedolino.get("nome_dipendente")
        or cedolino.get("dipendente_nome")
        or cedolino.get("dipendente")
        or ""
    )
    lordo = _numero(cedolino.get("lordo"), cedolino.get("lordo_totale"),
                    cedolino.get("totale_competenze"))
    filename = cedolino.get("filename") or cedolino.get("pdf_filename")
    doc: Dict[str, Any] = {
        "codice_fiscale": cf,
        "anno": int(anno),
        "mese": int(mese),
        "competenza": "%04d-%02d" % (int(anno), int(mese)),
        "tipo_cedolino": tipo_cedolino_hr(cedolino.get("tipo_cedolino")),
        "nome_dipendente": str(nome).strip(),
        "dipendente_nome": str(nome).strip(),
        "netto": _numero(cedolino.get("netto"), cedolino.get("netto_mese"),
                         cedolino.get("netto_pagato"), cedolino.get("netto_in_busta")),
        "lordo": lordo,
        "competenze": _numero(cedolino.get("totale_competenze"), cedolino.get("competenze")) or lordo,
        "trattenute": _numero(cedolino.get("totale_trattenute"), cedolino.get("trattenute")),
        "filename": filename,
        "pdf_filename": cedolino.get("pdf_filename") or filename,
        "fonte": FONTE_HR,
        # provenienza nel gestionale (chiavi extra: l'app HR le ignora)
        "gestionale_cedolino_id": cedolino.get("id"),
        "gestionale_source": cedolino.get("source") or cedolino.get("import_source"),
        "cedolino_dedup_key": cedolino.get("cedolino_dedup_key") or cedolino.get("dedup_key"),
    }
    formato = str(cedolino.get("formato") or cedolino.get("formato_rilevato")
                  or cedolino.get("parser_template") or "").strip().lower()
    if formato in PARSER_TEMPLATE_HR:
        doc["parser_template"] = formato
    for chiave in ("giorni_lavorati", "ore_lavorate"):
        valore = _numero(cedolino.get(chiave))
        if valore is not None:
            doc[chiave] = valore
    if cedolino.get("livello") not in (None, ""):
        doc["livello"] = str(cedolino["livello"])
    if isinstance(cedolino.get("retribuzione"), dict):
        doc["retribuzione"] = cedolino["retribuzione"]
    pdf = _pdf_base64(cedolino.get("pdf_data"))
    if pdf:
        doc["pdf_data"] = pdf
    return doc


# ── accesso all'archivio HR ──────────────────────────────────────────────────

def _json(valore: Any) -> Dict[str, Any]:
    return json.loads(valore) if isinstance(valore, str) else dict(valore or {})


async def _trova_dipendente_hr(con, cf: str) -> Optional[Dict[str, Any]]:
    righe = await con.fetch(_SQL_DIPENDENTE, cf)
    if not righe:
        return None
    return _json(righe[0]["doc"])


async def _cerca_esistente_hr(con, cf: str, anno: int, mese: int,
                              tipo: str, dedup_key: str) -> Optional[Dict[str, Any]]:
    """Primo cedolino HR con stessa chiave documentale, oppure stesso
    (CF, anno, mese) e stesso tipo (13a/14a restano distinte dall'ordinario)."""
    righe = await con.fetch(_SQL_ESISTENTI, cf, int(anno), int(mese), dedup_key or "")
    for riga in righe:
        if dedup_key and riga["dedup_key"] == dedup_key:
            return {"id": riga["id"], "motivo": "cedolino_dedup_key"}
    for riga in righe:
        if tipo_cedolino_hr(riga["tipo"]) == tipo:
            return {"id": riga["id"], "motivo": "cf_anno_mese_tipo"}
    return None


def _nome_da_anagrafica(dip: Dict[str, Any]) -> str:
    return (
        dip.get("nome_completo")
        or " ".join(p for p in (dip.get("cognome"), dip.get("nome")) if p)
        or ""
    ).strip()


async def deposita_cedolino_in_hr(
    cedolino: Dict[str, Any],
    *,
    con=None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Deposita UN cedolino del gestionale in ``app_cedolini`` se non c'e' gia'.

    Esiti: ``hr_non_configurato`` (nessuna DSN), ``dati_insufficienti``
    (senza CF/anno/mese non esiste identita' HR), ``gia_presente`` (mai
    sovrascritto), ``inserito``, ``da_inserire`` (solo con ``dry_run``),
    ``errore`` (problema di rete/DB, gia' loggato: l'ingestione prosegue).
    ``con`` permette al backfill di riusare una sola connessione.
    """
    doc = mappa_cedolino_per_hr(cedolino)
    if doc is None:
        logger.info("[HR deposito] saltato: cedolino senza CF/anno/mese (id gestionale=%s)",
                    cedolino.get("id"))
        return {"esito": "dati_insufficienti", "id": None}

    chiave = "%s %04d-%02d %s" % (doc["codice_fiscale"], doc["anno"], doc["mese"], doc["tipo_cedolino"])
    propria = con is None
    if propria:
        dsn = dsn_hr()
        if not dsn:
            _segnala_non_configurato()
            return {"esito": "hr_non_configurato", "id": None}
    try:
        if propria:
            con = await connetti_hr(dsn)
        try:
            esistente = await _cerca_esistente_hr(
                con, doc["codice_fiscale"], doc["anno"], doc["mese"],
                doc["tipo_cedolino"], doc.get("cedolino_dedup_key") or "",
            )
            if esistente:
                logger.info("[HR deposito] gia_presente %s -> id=%s (%s)",
                            chiave, esistente["id"], esistente["motivo"])
                return {"esito": "gia_presente", "id": esistente["id"], **_riepilogo(doc)}

            dip = await _trova_dipendente_hr(con, doc["codice_fiscale"])
            if dip:
                doc["dipendente_id"] = dip.get("id")
                doc["nome_dipendente"] = _nome_da_anagrafica(dip) or doc["nome_dipendente"]
                doc["dipendente_nome"] = doc["nome_dipendente"]
            else:
                doc["dipendente_id"] = None
                logger.warning("[HR deposito] %s: nessun dipendente HR con questo CF, "
                               "busta visibile per CF ma senza anagrafica", chiave)

            if dry_run:
                logger.info("[HR deposito] da_inserire %s (prova a secco)", chiave)
                return {"esito": "da_inserire", "id": None, **_riepilogo(doc)}

            doc["id"] = str(uuid.uuid4())
            doc["created_at"] = datetime.now(timezone.utc).isoformat()
            await con.execute(_SQL_INSERISCI, doc["id"], json.dumps(doc, default=str))
            logger.info("[HR deposito] inserito %s -> id=%s (dipendente_id=%s, pdf=%s)",
                        chiave, doc["id"], doc["dipendente_id"], "si" if doc.get("pdf_data") else "no")
            return {"esito": "inserito", "id": doc["id"], **_riepilogo(doc)}
        finally:
            if propria:
                await con.close()
    except Exception as exc:  # rete/DB: mai bloccare il flusso contabile
        logger.warning("[HR deposito] errore su %s: %s", chiave, exc)
        return {"esito": "errore", "id": None, "errore": str(exc), **_riepilogo(doc)}


def _riepilogo(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "codice_fiscale": doc["codice_fiscale"],
        "anno": doc["anno"],
        "mese": doc["mese"],
        "tipo_cedolino": doc["tipo_cedolino"],
    }


# ── backfill: tutto il registro `cedolini` del gestionale ───────────────────

async def deposita_tutti_i_cedolini(db, *, dry_run: bool = False) -> Dict[str, Any]:
    """Deposita in HR ogni cedolino del registro ``cedolini`` del gestionale.

    Una sola connessione per l'intero giro. Ritorna i conteggi per esito;
    ``dettagli`` elenca i primi errori con l'identita' del cedolino.
    """
    conteggi = {
        "totale": 0, "inseriti": 0, "gia_presenti": 0, "da_inserire": 0,
        "saltati": 0, "errori": 0,
    }
    esiti_contati = {
        "inserito": "inseriti", "gia_presente": "gia_presenti",
        "da_inserire": "da_inserire", "dati_insufficienti": "saltati",
        "errore": "errori",
    }
    dettagli: List[Dict[str, Any]] = []

    dsn = dsn_hr()
    if not dsn:
        _segnala_non_configurato()
    docs = await db["cedolini"].find({}, {"_id": 0}).to_list(20000)
    conteggi["totale"] = len(docs)

    con = None
    try:
        if dsn:
            con = await connetti_hr(dsn)
        for cedolino in docs:
            if dsn:
                esito = await deposita_cedolino_in_hr(cedolino, con=con, dry_run=dry_run)
            else:
                esito = {"esito": "hr_non_configurato", "id": None}
            campo = esiti_contati.get(esito.get("esito"))
            if campo:
                conteggi[campo] += 1
            if esito.get("esito") == "errore" and len(dettagli) < 20:
                dettagli.append({
                    "gestionale_cedolino_id": cedolino.get("id"),
                    "codice_fiscale": esito.get("codice_fiscale"),
                    "anno": esito.get("anno"), "mese": esito.get("mese"),
                    "errore": esito.get("errore"),
                })
    except Exception as exc:
        logger.exception("[HR deposito] backfill interrotto")
        dettagli.append({"errore": str(exc)})
        conteggi["errori"] += 1
    finally:
        if con is not None:
            try:
                await con.close()
            except Exception:
                logger.debug("[HR deposito] chiusura connessione fallita", exc_info=True)

    return {
        "hr_configurato": bool(dsn),
        "dry_run": dry_run,
        **conteggi,
        "dettagli": dettagli,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

async def _main_async(dry_run: bool) -> Dict[str, Any]:
    from app.database import Database

    await Database.connect_db()
    try:
        return await deposita_tutti_i_cedolini(Database.get_db(), dry_run=dry_run)
    finally:
        await Database.close_db()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deposita i cedolini del gestionale nell'archivio HR (app_cedolini)."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="conta cosa verrebbe inserito senza scrivere nulla in HR")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    risultato = asyncio.run(_main_async(args.dry_run))
    print(json.dumps(risultato, indent=2, ensure_ascii=False))
    return 1 if risultato.get("errori") else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
