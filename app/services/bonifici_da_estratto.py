"""Il bonifico PDF si abbina da solo al movimento d'estratto, e da lui alla fattura.

La ricevuta di un bonifico porta il «Rif. interno» della banca (MBVT40188610) e l'importo; la
riga dell'estratto conto ha lo stesso riferimento nella causale («VS.DISP. RIF. MBVT40188610/…»).
Quel riferimento, con l'importo al centesimo, e' una prova di identita': il movimento e' il
pagamento di quel PDF. Dal movimento si legge poi a cosa appartiene (la fattura che il motore
bancario ha gia' individuato, oppure una categoria senza documento), e il PDF la eredita: nessuno
deve scegliere a mano un bonifico che la banca ha gia' spiegato.

* Mai per solo importo: servono riferimento banca **e** importo al centesimo.
* La fattura si collega solo se esiste, e' attiva, non e' gia' legata a un altro bonifico e il suo
  importo (al netto dell'eventuale ritenuta) e' quello del bonifico.
* Gli stipendi restano al motore HR; una riga senza esito certo non si tocca.
* Idempotente: il secondo giro da' ``nuovi = 0``.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.fattura_attiva import FILTRO_FATTURA_ATTIVA
from app.services.identity_matching import nome_presente_nel_testo
from app.services.payment_document_links import collega_bonifico_fatture

logger = logging.getLogger(__name__)

RE_RIF_BANCA = re.compile(r"\bMB[A-Z]{2}\d{8}\b")
ESITI_HR_GIA_DECISI = {"arricchito", "depositato", "in_coda", "duplicato"}
CATEGORIE_DEL_MOTORE_STIPENDI = {"Stipendi"}
REGOLA = "rif_banca_in_estratto+importo_esatto+fattura_del_movimento"
REGOLA_NOME = "nome_beneficiario_in_estratto+importo_esatto+data_vicina+fattura_del_movimento"
EVIDENZE_FATTURA_NOME = ["nome_beneficiario_in_estratto", "importo_esatto_al_centesimo", "data_entro_3_giorni",
                         "fattura_individuata_dal_movimento"]
EVIDENZE_FATTURA = ["rif_banca_in_estratto", "importo_esatto_al_centesimo", "fattura_individuata_dal_movimento"]


def _cents(valore: Any) -> Optional[int]:
    try:
        return int(round(abs(float(valore)) * 100))
    except (TypeError, ValueError):
        return None


def _rif(testo: Any) -> Optional[str]:
    trovato = RE_RIF_BANCA.search(str(testo or "").upper())
    return trovato.group(0) if trovato else None


def _id_possibili(valore: Any) -> List[Any]:
    testo = str(valore)
    return [testo, int(testo)] if testo.isdigit() else [testo]


def _giorni_tra(a: Any, b: Any) -> Optional[int]:
    try:
        da = datetime.strptime(str(a)[:10], "%Y-%m-%d")
        db_ = datetime.strptime(str(b)[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return abs((da - db_).days)


def _importo_atteso_cents(fattura: Dict[str, Any]) -> Optional[int]:
    totale = fattura.get("total_amount")
    if totale in (None, ""):
        totale = fattura.get("importo_totale") if fattura.get("importo_totale") not in (None, "") else fattura.get("totale")
    lordo = _cents(totale)
    if lordo is None:
        return None
    ritenuta = _cents(fattura.get("importo_ritenuta")) or 0
    return lordo - ritenuta


def _gia_decisa(t: Dict[str, Any]) -> bool:
    return bool(
        t.get("fattura_associata") is True or t.get("fattura_associata_id") or t.get("fattura_id")
        or t.get("salario_associato") or t.get("destinazione_automatica")
        or (t.get("hr_deposito") or {}).get("esito") in ESITI_HR_GIA_DECISI
    )


async def abbina_bonifici_via_estratto(db, *, anno: Optional[int] = None, dry_run: bool = False) -> Dict[str, Any]:
    """Abbina i bonifici PDF ancora senza esito al loro movimento d'estratto e ne eredita l'esito."""
    esito: Dict[str, Any] = {
        "dry_run": dry_run, "esaminati": 0, "movimento_trovato": 0, "fatture_collegate": 0,
        "destinazioni_certe": 0, "senza_esito_certo": 0, "fattura_non_collegabile": 0,
    }
    filtro: Dict[str, Any] = {}
    if anno:
        filtro["data"] = {"$regex": f"^{anno}"}
    trasferimenti = await db["bonifici_transfers"].find(
        filtro, {"_id": 0, "pdf_data": 0, "pdf_base64": 0, "contenuto_b64": 0}
    ).to_list(None)
    da_fare = [t for t in trasferimenti if not _gia_decisa(t) and (t.get("rif_interno") or t.get("cro_trn"))]
    if not da_fare:
        return esito

    movimenti = await db["estratto_conto_movimenti"].find(
        {"tipo": "uscita", **({"data": {"$regex": f"^{anno}"}} if anno else {})},
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "descrizione": 1, "causale": 1, "categoria": 1,
         "candidate_fattura_id": 1, "fattura_id": 1, "fattura_ids": 1},
    ).to_list(None)
    per_chiave: Dict[tuple, List[Dict[str, Any]]] = {}
    per_importo: Dict[int, List[Dict[str, Any]]] = {}
    for m in movimenti:
        rif = _rif(m.get("descrizione") or m.get("causale"))
        cents = _cents(m.get("importo"))
        if cents:
            per_importo.setdefault(cents, []).append(m)
        if rif and cents:
            per_chiave.setdefault((rif, cents), []).append(m)

    ora = datetime.now(timezone.utc).isoformat()
    for t in da_fare:
        esito["esaminati"] += 1
        rif = _rif(t.get("rif_interno"))
        cents = _cents(t.get("importo"))
        candidati = per_chiave.get((rif, cents), []) if rif and cents else []
        prova = "rif_banca"
        if not candidati and cents:
            # Senza riferimento (ricevuta scritta a mano, bonifico da altra banca): nome completo del
            # beneficiario nella causale, importo al centesimo e al massimo 3 giorni di scarto.
            nome = (t.get("beneficiario") or {}).get("nome") or ""
            candidati = [
                m for m in per_importo.get(cents, [])
                if (_giorni_tra(t.get("data"), m.get("data")) or 99) <= 3
                and nome_presente_nel_testo(nome, str(m.get("descrizione") or m.get("causale") or ""))
            ]
            prova = "nome_importo_data"
        if len(candidati) != 1:
            continue  # nessun movimento, o piu' di uno: non si indovina
        movimento = candidati[0]
        esito["movimento_trovato"] += 1
        categoria = movimento.get("categoria")
        if categoria in CATEGORIE_DEL_MOTORE_STIPENDI:
            continue

        id_fattura = (movimento.get("fattura_ids") or [None])[0] or movimento.get("fattura_id") or movimento.get("candidate_fattura_id")
        if id_fattura:
            fattura = await db["invoices"].find_one(
                {"id": {"$in": _id_possibili(id_fattura)}, **FILTRO_FATTURA_ATTIVA}, {"_id": 0})
            altri = {str(x) for x in (fattura or {}).get("bonifico_ids") or []} - {str(t.get("id"))}
            if not fattura or altri or _importo_atteso_cents(fattura) != cents:
                esito["fattura_non_collegabile"] += 1
                continue
            if not dry_run:
                await db["bonifici_transfers"].update_one(
                    {"id": t["id"]}, {"$set": {"movimento_estratto_conto_id": movimento["id"]}})
                await collega_bonifico_fatture(
                    db, {**t, "movimento_estratto_conto_id": movimento["id"]}, [fattura], auto=True,
                    evidenze=EVIDENZE_FATTURA if prova == "rif_banca" else EVIDENZE_FATTURA_NOME,
                    regola=REGOLA if prova == "rif_banca" else REGOLA_NOME)
            esito["fatture_collegate"] += 1
        elif categoria:
            if not dry_run:
                await db["bonifici_transfers"].update_one({"id": t["id"]}, {"$set": {
                    "movimento_estratto_conto_id": movimento["id"],
                    "destinazione_automatica": {
                        "categoria": categoria, "movimento_id": movimento["id"], "rif_banca": rif,
                        "regola": f"{prova}+importo_esatto", "at": ora},
                    "updated_at": ora}})
            esito["destinazioni_certe"] += 1
        else:
            esito["senza_esito_certo"] += 1
    logger.info("[BONIFICI-ESTRATTO] %s", esito)
    return esito
