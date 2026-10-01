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
* Se il movimento punta una copia archiviata, vale la gemella attiva (numero, totale e P.IVA uguali, una sola).
* Piu' bonifici dello stesso fornitore sulla stessa fattura (acconti) si collegano solo se, con quelli
  gia' legati, sommano il totale al centesimo; ognuno con il suo riferimento banca nel movimento.
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

RE_RIF_BANCA = re.compile(r"\bMB[A-Z0-9]{2}\d{8}\b")  # MBVT… (ordinario) e MB0B… (urgente)
ESITI_HR_GIA_DECISI = {"arricchito", "depositato", "in_coda", "duplicato"}
CATEGORIE_DEL_MOTORE_STIPENDI = {"Stipendi"}
REGOLA = "rif_banca_in_estratto+importo_esatto+fattura_del_movimento"
REGOLA_ACCONTI = "rif_banca_in_estratto+acconti_che_sommano_il_totale+fattura_del_movimento"
EVIDENZE_ACCONTI = ["rif_banca_in_estratto", "acconti_sommano_il_totale_al_centesimo",
                    "fattura_individuata_dal_movimento"]
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


def _id_fattura_del_movimento(m: Dict[str, Any]) -> Any:
    return (m.get("fattura_ids") or [None])[0] or m.get("fattura_id") or m.get("candidate_fattura_id")


async def _gemella_attiva(db, id_fattura: Any) -> Optional[Dict[str, Any]]:
    """La fattura attiva che e' la stessa del documento indicato dal movimento, se questo e' archiviato.

    Il motore bancario puo' aver puntato la copia archiviata: l'identita' e' numero, totale e
    P.IVA del cedente, e vale solo se la gemella attiva e' una sola.
    """
    puntata = await db["invoices"].find_one({"id": {"$in": _id_possibili(id_fattura)}}, {"_id": 0})
    numero = (puntata or {}).get("invoice_number")
    piva = (puntata or {}).get("supplier_vat") or (puntata or {}).get("cedente_piva")
    if not puntata or not numero or not piva:
        return None
    gemelle = await db["invoices"].find(
        {"invoice_number": numero, **FILTRO_FATTURA_ATTIVA}, {"_id": 0}).to_list(None)
    gemelle = [
        g for g in gemelle
        if (g.get("supplier_vat") or g.get("cedente_piva")) == piva and _cents(g.get("total_amount")) == _cents(puntata.get("total_amount"))
    ]
    return gemelle[0] if len(gemelle) == 1 else None


async def _riallinea_bonifico_ids(db, trasferimenti: List[Dict[str, Any]]) -> int:
    """Rimette sulla fattura il bonifico che questo motore le aveva collegato dal solo lato del bonifico.

    Con l'`id` numerico la fattura non veniva trovata e il suo `bonifico_ids` restava vuoto.
    """
    riallineate = 0
    for t in trasferimenti:
        if "rif_banca_in_estratto" not in (t.get("fattura_associazione_evidenze") or []):
            continue
        for id_fattura in t.get("fattura_ids") or []:
            fattura = await db["invoices"].find_one(
                {"id": {"$in": _id_possibili(id_fattura)}}, {"_id": 0, "id": 1, "bonifico_ids": 1})
            if not fattura or str(t.get("id")) in {str(x) for x in fattura.get("bonifico_ids") or []}:
                continue
            await db["invoices"].update_one(
                {"id": {"$in": _id_possibili(id_fattura)}},
                {"$addToSet": {"bonifico_ids": str(t.get("id")), "payment_document_ids": str(t.get("id"))}})
            riallineate += 1
    if riallineate:
        logger.info("[BONIFICI-ESTRATTO] fatture riallineate con il loro bonifico: %d", riallineate)
    return riallineate


async def abbina_bonifici_via_estratto(db, *, anno: Optional[int] = None, dry_run: bool = False) -> Dict[str, Any]:
    """Abbina i bonifici PDF ancora senza esito al loro movimento d'estratto e ne eredita l'esito."""
    esito: Dict[str, Any] = {
        "dry_run": dry_run, "esaminati": 0, "movimento_trovato": 0, "fatture_collegate": 0,
        "destinazioni_certe": 0, "senza_esito_certo": 0, "fattura_non_collegabile": 0, "acconti_collegati": 0,
    }
    filtro: Dict[str, Any] = {}
    if anno:
        filtro["data"] = {"$regex": f"^{anno}"}
    trasferimenti = await db["bonifici_transfers"].find(
        filtro, {"_id": 0, "pdf_data": 0, "pdf_base64": 0, "contenuto_b64": 0}
    ).to_list(None)
    if not dry_run:
        esito["fatture_riallineate"] = await _riallinea_bonifico_ids(db, trasferimenti)
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
    acconti: Dict[str, Dict[str, Any]] = {}
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
        if len(candidati) > 1 and prova == "rif_banca":
            # Stesso riferimento banca e stesso importo = la stessa operazione letta da due fonti (la riga
            # del vecchio archivio e quella dell'estratto ufficiale): vale la copia che porta la fattura,
            # a patto che le copie con fattura non ne indichino due diverse.
            con_fattura = [m for m in candidati if _id_fattura_del_movimento(m)]
            if con_fattura and len({str(_id_fattura_del_movimento(m)) for m in con_fattura}) == 1:
                candidati = con_fattura[:1]
        if len(candidati) != 1:
            continue  # nessun movimento, o piu' di uno: non si indovina
        movimento = candidati[0]
        esito["movimento_trovato"] += 1
        categoria = movimento.get("categoria")
        if categoria in CATEGORIE_DEL_MOTORE_STIPENDI:
            continue

        id_fattura = _id_fattura_del_movimento(movimento)
        if id_fattura:
            fattura = await db["invoices"].find_one(
                {"id": {"$in": _id_possibili(id_fattura)}, **FILTRO_FATTURA_ATTIVA}, {"_id": 0})
            if not fattura:
                fattura = await _gemella_attiva(db, id_fattura)
            altri = {str(x) for x in (fattura or {}).get("bonifico_ids") or []} - {str(t.get("id"))}
            atteso = _importo_atteso_cents(fattura) if fattura else None
            if fattura and not altri and atteso == cents:
                pass  # importo uguale al centesimo: collegamento diretto
            elif fattura and prova == "rif_banca" and atteso and cents < atteso:
                # Un acconto: si decide a fine giro, solo se tutti i bonifici della fattura sommano il totale.
                gruppo = acconti.setdefault(str(fattura.get("id")), {"fattura": fattura, "voci": []})
                gruppo["voci"].append((t, movimento, cents))
                continue
            else:
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
    per_id = {str(t.get("id")): t for t in trasferimenti}
    for gruppo in acconti.values():
        fattura, voci = gruppo["fattura"], gruppo["voci"]
        id_voci = {str(v[0].get("id")) for v in voci}
        gia_legati = [per_id.get(str(x)) for x in fattura.get("bonifico_ids") or [] if str(x) not in id_voci]
        if any(x is None for x in gia_legati):
            esito["fattura_non_collegabile"] += len(voci)
            continue
        somma = sum(c for _, _, c in voci) + sum(_cents(x.get("importo")) or 0 for x in gia_legati)
        if somma != _importo_atteso_cents(fattura):
            esito["fattura_non_collegabile"] += len(voci)
            continue
        for t, movimento, _cents_voce in voci:
            if not dry_run:
                await db["bonifici_transfers"].update_one(
                    {"id": t["id"]}, {"$set": {"movimento_estratto_conto_id": movimento["id"]}})
                await collega_bonifico_fatture(
                    db, {**t, "movimento_estratto_conto_id": movimento["id"]}, [fattura], auto=True,
                    evidenze=EVIDENZE_ACCONTI, regola=REGOLA_ACCONTI)
            esito["fatture_collegate"] += 1
            esito["acconti_collegati"] += 1
    logger.info("[BONIFICI-ESTRATTO] %s", esito)
    return esito
