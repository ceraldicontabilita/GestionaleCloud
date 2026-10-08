"""Guardia della cessazione automatica da cedolino (canale D, V1 e V2).

Trovato il 15/09/2026 importando l'archivio storico dei cedolini dai fascicoli
Drive: una busta del 2018-2022 con dicitura di cessazione (TFR, "licenz.",
data cessazione in anagrafica) veniva applicata OGGI alla copia ``dipendenti``
del gestionale, marcando cessati Carotenuto, Capezzuto e Guarino, che hanno
buste fino al 2026-07 (riassunti dopo quella cessazione), e dando a D'Alma e
Solla una data di fine sbagliata.

Regola: una busta cessa il rapporto solo se NON esiste una busta successiva
della stessa persona, nel registro ``cedolini`` del gestionale o nel deposito
HR (``app_cedolini``, l'archivio completo). Qualsiasi errore di lettura fa
tornare ``None`` (= nessuna prova di ripresa): la guardia non blocca mai
l'import.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)


def _competenza(doc: Dict[str, Any]) -> Optional[tuple]:
    try:
        anno, mese = int(doc.get("anno")), int(doc.get("mese"))
    except (TypeError, ValueError):
        return None
    if not (1 <= mese <= 12 and 1990 <= anno <= 2100):
        return None
    return (anno, mese)


def busta_piu_recente(docs: Iterable[Dict[str, Any]], dopo: tuple,
                      codice_fiscale: str = "", dipendente_id: str = "") -> Optional[str]:
    """``"YYYY-MM"`` della busta piu' recente successiva a ``dopo`` fra ``docs``
    che appartengono alla persona (per CF, altrimenti per id); None se nessuna."""
    cf = (codice_fiscale or "").strip().upper()
    ultima = None
    for d in docs:
        stessa = (cf and str(d.get("codice_fiscale") or "").strip().upper() == cf) or (
            dipendente_id and d.get("dipendente_id") == dipendente_id)
        if not stessa:
            continue
        comp = _competenza(d)
        if comp and comp > dopo and (ultima is None or comp > ultima):
            ultima = comp
    return f"{ultima[0]:04d}-{ultima[1]:02d}" if ultima else None


async def _dal_registro_gestionale(db, dopo, codice_fiscale, dipendente_id) -> Optional[str]:
    docs = []
    for filtro in ({"dipendente_id": dipendente_id} if dipendente_id else None,
                   {"codice_fiscale": codice_fiscale} if codice_fiscale else None):
        if not filtro:
            continue
        try:
            cursore = db["cedolini"].find(filtro, {"_id": 0, "anno": 1, "mese": 1,
                                                   "codice_fiscale": 1, "dipendente_id": 1})
            docs.extend(await cursore.to_list(5000))
        except Exception:
            logger.exception("guardia cessazione: lettura registro cedolini fallita")
    return busta_piu_recente(docs, dopo, codice_fiscale, dipendente_id)


async def _dal_deposito_hr(dopo, codice_fiscale) -> Optional[str]:
    cf = (codice_fiscale or "").strip().upper()
    if not cf:
        return None
    try:
        from app.services import hr_cedolini_deposito as deposito
        dsn = deposito.dsn_hr()
        if not dsn:
            return None
        con = await deposito.connetti_hr(dsn)
        try:
            riga = await con.fetchrow(
                "SELECT max(doc->>'competenza') AS ultima FROM " + deposito.TABELLA_CEDOLINI +
                " WHERE upper(doc->>'codice_fiscale') = $1"
                "   AND doc->>'competenza' ~ '^[0-9]{4}-[0-9]{2}$'", cf)
        finally:
            await con.close()
    except Exception:
        logger.exception("guardia cessazione: lettura deposito HR fallita")
        return None
    ultima = riga["ultima"] if riga else None
    return ultima if ultima and ultima > f"{dopo[0]:04d}-{dopo[1]:02d}" else None


async def busta_successiva(db, *, dipendente_id: str = "", codice_fiscale: str = "",
                           anno: Any, mese: Any) -> Optional[str]:
    """Competenza (``"YYYY-MM"``) di una busta della stessa persona successiva
    a ``anno``/``mese``, cercata prima nel registro del gestionale e poi nel
    deposito HR. None = la busta e' davvero l'ultima: la cessazione vale."""
    try:
        dopo = (int(anno), int(mese))
    except (TypeError, ValueError):
        return None
    trovata = await _dal_registro_gestionale(db, dopo, codice_fiscale, dipendente_id)
    if trovata:
        return trovata
    return await _dal_deposito_hr(dopo, codice_fiscale)


async def riallinea_cessazioni_automatiche(db) -> Dict[str, Any]:
    """Rimette in ordine la copia ``dipendenti`` del gestionale per chi e' stato
    cessato AUTOMATICAMENTE da una busta (``cessato_automaticamente`` = True).
    L'anagrafica HR comanda (regola R1 del titolare, 14/09/2026): HR in forza →
    torna attivo e la cessazione automatica viene tolta; HR cessato con data →
    quella data. I cessati a mano non vengono mai toccati. Idempotente: gira
    dallo scheduler ogni 6 ore (primo giro 2 minuti dopo l'avvio)."""
    from datetime import datetime, timezone

    esito: Dict[str, Any] = {"esaminati": 0, "riattivati": 0, "date_corrette": 0,
                             "invariati": 0, "senza_hr": 0, "dettagli": []}
    try:
        docs = await db["dipendenti"].find({"cessato_automaticamente": True}, {"_id": 0}).to_list(2000)
    except Exception:
        logger.exception("riallineamento cessazioni: lettura dipendenti fallita")
        return esito
    if not docs:
        return esito
    from app.services import hr_cedolini_deposito as deposito
    from app.hr.services import stato_rapporto

    dsn = deposito.dsn_hr()
    if not dsn:
        esito["hr_non_configurato"] = True
        return esito
    adesso = datetime.now(timezone.utc).isoformat()
    con = await deposito.connetti_hr(dsn)
    try:
        for d in docs:
            esito["esaminati"] += 1
            cf = str(d.get("codice_fiscale") or "").strip().upper()
            hr = await deposito._trova_dipendente_hr(con, cf) if cf else None
            if not hr:
                esito["senza_hr"] += 1
                continue
            nome = f"{d.get('cognome') or ''} {d.get('nome') or ''}".strip()
            if stato_rapporto.e_in_forza(hr):
                if d.get("attivo") is False or d.get("in_carico") is False or d.get("data_cessazione"):
                    await db["dipendenti"].update_one(
                        {"id": d["id"]},
                        {"$set": {"attivo": True, "in_carico": True, "cessato_automaticamente": False,
                                  "cessazione_source": None, "cessazione_diciture": [],
                                  "data_cessazione": None, "riallineato_da_hr_il": adesso,
                                  "updated_at": adesso}},
                    )
                    esito["riattivati"] += 1
                    esito["dettagli"].append({"id": d["id"], "nome": nome, "azione": "riattivato",
                                              "era_cessato_il": d.get("data_cessazione")})
                else:
                    esito["invariati"] += 1
                continue
            data_hr = stato_rapporto.data_fine_rapporto(hr)
            if data_hr and d.get("data_cessazione") != data_hr:
                await db["dipendenti"].update_one(
                    {"id": d["id"]},
                    {"$set": {"attivo": False, "in_carico": False, "data_cessazione": data_hr,
                              "cessazione_source": "anagrafica_hr", "riallineato_da_hr_il": adesso,
                              "updated_at": adesso}},
                )
                esito["date_corrette"] += 1
                esito["dettagli"].append({"id": d["id"], "nome": nome, "azione": "data_corretta",
                                          "da": d.get("data_cessazione"), "a": data_hr})
            else:
                esito["invariati"] += 1
    finally:
        await con.close()
    return esito
