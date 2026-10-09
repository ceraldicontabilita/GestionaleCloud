"""Anteprima e conferma uniche per la ripartizione salari da ERP e HR."""
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fastapi import HTTPException

from app.services.conferma_bonifico import chiavi_bonifico, campi_conferma
from app.services.pagamenti_mensilita import competenza_in_causale
from app.services import posizione_dipendente as pos
from app.services.ripartizione_salari import ripartisci_movimenti, valida_destinazioni, indice_quote


async def _carica(db, dip_id):
    filtro = {"dipendente_id": dip_id}
    dati = {}
    for nome in ("paghe_mensili", "pagamenti_esiti", "cedolini", "acconti_dipendenti", "bonifici_da_associare"):
        dati[nome] = await db[nome].find(filtro, {"_id": 0, "pdf_data": 0}).to_list(None)
    return dati


def _registro(dati, dip, esiti, coda):
    return pos.componi_movimenti(paghe=dati["paghe_mensili"], cedolini=dati["cedolini"],
        esiti=esiti, acconti=dati["acconti_dipendenti"], pagamenti_senza_competenza=coda,
        conciliazioni=[], rapporto=dip)["registro"]


async def anteprima(db, pagamento, dip_id, destinazioni=None, collega_key=None):
    dip = await db.dipendenti.find_one({"id": dip_id}, {"_id": 0, "pdf_data": 0})
    if not dip:
        raise HTTPException(404, "Dipendente non trovato")
    try:
        data = date.fromisoformat(str(pagamento.get("data") or "")[:10]).isoformat()
        totale = pos.importo(pagamento.get("importo"))
        if totale is None or totale <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, "Per associare servono data effettiva e importo positivo del pagamento") from None
    dati = await _carica(db, dip_id)
    # Ricerca globale: una ricevuta non può pagare due dipendenti diversi.
    esiti_tutti = await db.pagamenti_esiti.find({}, {"_id": 0, "pdf_data": 0}).to_list(None)
    identita = chiavi_bonifico(pagamento)
    esistenti = [e for e in esiti_tutti if identita & chiavi_bonifico(e)
                 or (pagamento.get("id") and e.get("bonifico_da_associare_id") == pagamento["id"])]
    if any(e.get("dipendente_id") != dip_id for e in esistenti):
        raise HTTPException(409, "Questo pagamento è già assegnato a un altro dipendente")
    if len(esistenti) > 1:
        raise HTTPException(409, "Più registrazioni hanno lo stesso riferimento bancario: verificare il duplicato")
    possibili = [e for e in dati["pagamenti_esiti"] if e not in esistenti
                 and str(e.get("data") or "")[:10] == data and pos.importo(e.get("importo")) == totale]
    if collega_key:
        scelto = next((e for e in possibili + esistenti if e.get("key") == collega_key), None)
        if not scelto or (esistenti and scelto not in esistenti):
            raise HTTPException(409, "Il pagamento da collegare non corrisponde a dipendente, data e importo")
        esistenti = [scelto]
    esistente = esistenti[0] if esistenti else None
    if esistente and pos.importo(esistente.get("importo")) != totale:
        raise HTTPException(409, "Lo stesso riferimento bancario ha un importo diverso in archivio")
    key = (esistente or {}).get("key") or "ripartizione-salari:" + str(pagamento["id"])
    anno, mese = (esistente or {}).get("anno"), (esistente or {}).get("mese")
    comp = competenza_in_causale(pagamento.get("causale"))
    if comp:
        mese, anno = comp
    base = [e for e in dati["pagamenti_esiti"] if e.get("key") != key]
    coda = [e for e in dati["bonifici_da_associare"] if e.get("id") != pagamento["id"]
            and not identita & chiavi_bonifico(e)]
    registro = _registro(dati, dip, base, coda)
    periodi = {tuple(m["competenza"]) for m in registro if m["tipo"] == "busta" and m.get("competenza")}
    try:
        scelte = valida_destinazioni(
            (esistente or {}).get("destinazioni_salari", []) if destinazioni is None else destinazioni, totale, periodi)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    candidato = {**(esistente or {}), **pagamento, "key": key, "dipendente_id": dip_id,
                 "data": data, "importo": float(totale), "anno": anno, "mese": mese,
                 "destinazioni_salari": scelte, "confermato_manuale": True}
    # La busta precedentemente derivata da questo pagamento non è un altro credito.
    per_calcolo = {**dati, "paghe_mensili": [dict(p) for p in dati["paghe_mensili"]]}
    if esistente:
        for p in per_calcolo["paghe_mensili"]:
            if p.get("bonifico_da_esiti"):
                p["bonifico_importo"] = 0
    registro = _registro(per_calcolo, dip, base + [candidato], coda)
    rip = ripartisci_movimenti(registro)
    if any(r["key"] == key for r in rip["scelte_non_applicate"]):
        raise HTTPException(422, "La quota scelta supera il residuo disponibile del cedolino alla data del pagamento")
    quote, acconto = [], pos.ZERO
    for mv in rip["movimenti"]:
        if mv.get("link", {}).get("key") != key:
            continue
        if mv.get("competenza"):
            a, m = mv["competenza"]
            quote.append({"anno": a, "mese": m, "importo": float(mv["avere"]),
                          "criterio": mv["link"].get("criterio_ripartizione"),
                          "residuo_cedolino": pos._eur(rip["residui"].get((a, m)))})
        else:
            acconto += mv.get("avere") or pos.ZERO
    buste = []
    for mv in registro:
        if mv["tipo"] == "busta" and mv.get("competenza"):
            a, m = mv["competenza"]
            buste.append({"anno": a, "mese": m, "descrizione": pos._nome_periodo(a, m),
                          "dovuto": pos._eur(mv["dare"]), "residuo": pos._eur(rip["residui"].get((a, m))),
                          "cedolino_id": mv["link"].get("cedolino_id")})
    firma = hashlib.sha256(json.dumps([dati, pagamento, scelte, key], default=str, sort_keys=True).encode()).hexdigest()
    return {"dipendente_id": dip_id, "dipendente": f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip(),
            "data": data, "importo": float(totale), "quote": quote, "acconto": float(acconto),
            "assegnato": float(totale-acconto), "cedolini": buste, "versione": firma,
            "destinazioni": scelte, "pagamento_esistente": esistente.get("key") if esistente else None,
            "possibili_duplicati": [{"key": e.get("key"), "causale": e.get("causale"),
                                     "anno": e.get("anno"), "mese": e.get("mese")} for e in possibili],
            "_esito": candidato, "_registro": registro, "_dati": dati}


def pubblica(anteprima):
    return {k: v for k, v in anteprima.items() if not k.startswith("_")}


class _PoolConnessione:
    def __init__(self, con):
        self.con = con

    @asynccontextmanager
    async def acquire(self):
        yield self.con


@asynccontextmanager
async def _transazione(db):
    # Un unico commit per pagamento e coda; lock condiviso da entrambe le UI.
    from app.services.archivio_documenti_memoria import ArchivioDocumenti
    if isinstance(db, ArchivioDocumenti):
        async with db.transaction():
            yield db
        return
    from app.hr.db_supabase import SupabaseDatabase
    if not isinstance(db, SupabaseDatabase):
        raise TypeError("Archivio HR non supportato")
    for nome in ("dipendenti", "paghe_mensili", "pagamenti_esiti", "cedolini", "acconti_dipendenti", "bonifici_da_associare"):
        await db[nome]._assicura_tabella()
    async with db._pool.acquire() as con:
        async with con.transaction():
            await con.execute("SELECT pg_advisory_xact_lock(hashtext('hr:associazione-salari'))")
            tx = SupabaseDatabase(_PoolConnessione(con), schema=db._schema)
            # Cache privata della transazione: nessun dato del processo precedente,
            # i PDF si idratano solo per la riga aggiornata e non per tutta la tabella.
            tx._cache_attiva = True
            tx._tabelle_pronte.update(db._tabelle_pronte)
            yield tx
    await db.refresh_collections("pagamenti_esiti", "paghe_mensili", "bonifici_da_associare")


async def conferma(db, pagamento, dip_id, payload, attore="admin"):
    async with _transazione(db) as tx:
        piano = await anteprima(tx, pagamento, dip_id, payload.get("destinazioni"), payload.get("collega_key"))
        if piano["possibili_duplicati"] and not piano["pagamento_esistente"] and not payload.get("conferma_distinto"):
            raise HTTPException(409, "Esiste un pagamento dello stesso importo e data: collegalo oppure conferma che è un altro pagamento")
        if payload.get("versione") != piano["versione"]:
            raise HTTPException(409, "La situazione è cambiata: aggiorna l'anteprima prima di confermare")
        now = datetime.now(timezone.utc).isoformat()
        esito = piano["_esito"]
        # Non copiare l'id della ricevuta sopra l'id del fatto di pagamento.
        esistente = await tx.pagamenti_esiti.find_one({"key": esito["key"]}, {"_id": 0, "pdf_data": 0})
        esito["id"] = (esistente or {}).get("id") or "pe_" + hashlib.sha256(esito["key"].encode()).hexdigest()[:30]
        campi = campi_conferma(attore)
        esito.update(campi, destinazioni_salari=piano["destinazioni"],
                     bonifico_da_associare_id=pagamento["id"], ripartizione_salari_versione=1,
                     updated_at=now, associazione_certa=True)
        esito["ripartizione_salari_prima"] = ((esistente or {}).get("ripartizione_salari_prima")
            if "ripartizione_salari_prima" in (esistente or {}) else esistente)
        esito.pop("_id", None)
        esito.pop("pdf_data", None)
        await tx.pagamenti_esiti.update_one({"key": esito["key"]},
            {"$set": esito, "$push": {"storico_ripartizioni": {"il": now, "da": attore,
                "destinazioni": piano["destinazioni"], "quote": piano["quote"], "acconto": piano["acconto"]}}}, upsert=True)
        await tx.bonifici_da_associare.update_one({"id": pagamento["id"]}, {"$set": {
            **campi, "stato": "associato", "associato_a": dip_id, "associato_tipo": "stipendio",
            "pagamento_esito_key": esito["key"], "ripartizione_salari_versione": 1,
            "destinazioni_salari": piano["destinazioni"], "associato_il": now}})
        await aggiorna_proiezioni(tx, dip_id)

    return {"ok": True, **pubblica(piano), "pagamento_key": esito["key"]}


async def annulla(db, key):
    """Ritira le quote; un pagamento preesistente resta nella prima nota."""
    async with _transazione(db) as tx:
        e = await tx.pagamenti_esiti.find_one({"key": key}, {"_id": 0, "pdf_data": 0})
        if not e or e.get("ripartizione_salari_versione") != 1:
            raise HTTPException(409, "Ripartizione non trovata")
        prima = e.get("ripartizione_salari_prima")
        if prima:
            await tx.pagamenti_esiti.update_one({"key": key}, {
                "$set": prima, "$unset": {k: "" for k in e if k not in prima}})
        else:
            await tx.pagamenti_esiti.delete_one({"key": key})
        await tx.bonifici_da_associare.update_one({"id": e.get("bonifico_da_associare_id")}, {
            "$set": {"stato": "da_associare", "confermato_manuale": False},
            "$unset": {k: "" for k in ("pagamento_esito_key", "ripartizione_salari_versione",
                "destinazioni_salari", "associato_a", "associato_tipo", "associato_il")}})
        await aggiorna_proiezioni(tx, e["dipendente_id"])

    return {"ok": True}


async def aggiorna_proiezioni(db, dip_id):
    from app.constants.stati_associazione_bonifico import stato_paga_mese, esiti_confermati, ha_riscontro_bancario
    from app.services.pagamenti_mensilita import indice_coperture
    dati = await _carica(db, dip_id)
    dip = await db.dipendenti.find_one({"id": dip_id}, {"_id": 0}) or {}
    registro = _registro(dati, dip, dati["pagamenti_esiti"], dati["bonifici_da_associare"])
    quote = indice_quote(registro, dati["pagamenti_esiti"])
    dovuti = {tuple(m["competenza"]): m["dare"] for m in registro if m["tipo"] == "busta" and m.get("competenza")}
    coperture = indice_coperture(dati["pagamenti_esiti"])
    stati = {}
    for p in dati["paghe_mensili"]:
        comp = p.get("anno"), p.get("mese")
        q = quote.get(comp, [])
        bonifici = [e for e in q if e["quota_tipo"] == "bonifico"]
        bon = sum((pos.importo(e["importo"]) for e in bonifici), pos.ZERO)
        erogato = sum((pos.importo(e["importo"]) for e in q), pos.ZERO)
        dovuto = dovuti.get(comp)
        prove = coperture.get((dip_id, *comp), [])
        stato = stato_paga_mese(dovuto, erogato)
        if bon and dovuto is not None and not esiti_confermati(bonifici):
            stato = "da_verificare"
        if prove:
            stato = "pagato_documentato"
        stati[comp] = stato
        patch = {"bonifico_importo": float(bon), "bonifico_da_esiti": True,
                 "bonifico_ricevuto": bool(bonifici) and all(ha_riscontro_bancario(e) for e in bonifici),
                 "stato_pagamento": stato, "pagamenti_copertura": prove,
                 "saldo": 0.0 if prove else pos._eur(dovuto-erogato) if dovuto is not None else None}
        if not p.get("bonifico_da_esiti") and pos.importo(p.get("bonifico_importo")):
            patch["bonifico_registro_originale"] = {"importo": p["bonifico_importo"], "data": p.get("bonifico_data")}
        if any(p.get(k) != v for k, v in patch.items()):
            await db.paghe_mensili.update_one({"dipendente_id": dip_id, "anno": comp[0], "mese": comp[1]}, {"$set": patch})
    return stati
