"""Dilazione amministrativa INPS: il piano letto e ogni rata col suo pagamento.

La PEC dell'INPS (``inpscomunica@postacert.inps.gov.it``, oggetto «Sede INPS
5100, matricola …, Dilazione amministrativa») porta in ``Allegato.zip`` la
lettera di accoglimento con il piano di ammortamento: numero rata, quota
capitale, interessi, totale, scadenza, e le coordinate della sezione INPS
dell'F24 (sede, causale ``RC01``, matricola, periodo da/a).

Il piano e' il fatto che crea le attese: una per rata. La soddisfa la
quietanza F24 che ha nella sezione INPS la stessa sede, causale, matricola e
periodo **e** l'importo della rata al centesimo, versata dopo la domanda; il
suo addebito in banca e' quello gia' riscontrato sulla quietanza
(``riscontro_banca``). Rate di pari importo si abbinano in ordine di
scadenza, un pagamento per rata. Niente si abbina per solo importo.
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.db_collections import COLL_QUIETANZE_F24

logger = logging.getLogger(__name__)

TIPO = "dilazione_inps"
COLL_DILAZIONI_INPS = "dilazioni_inps"
ALERT_RATA_NON_PAGATA = "DILAZIONE_INPS_RATA_NON_PAGATA"
MITTENTE_PEC = "inpscomunica@postacert.inps.gov.it"

RATA_PAGATA = "PAGATA"
RATA_DA_PAGARE = "DA_PAGARE"
RATA_SCADUTA = "SCADUTA_NON_PAGATA"
# Versamento con le coordinate della dilazione ma importo diverso dalla rata:
# resta aperta (il piano chiede l'importo intero), col versamento accanto.
RATA_IMPORTO_DIVERSO = "VERSATA_IMPORTO_DIVERSO"

_IMPORTO = r"\d{1,3}(?:\.\d{3})*,\d{2}"
_RE_RIF = re.compile(r"INPS\.(\d{4})\.(\d{2}/\d{2}/\d{4})\.(\d+)")
_RE_MATRICOLA = re.compile(r"MATRICOLA\s+(\d{10})\b")
_RE_CF = re.compile(r"CODICE\s+FISCALE\s+(\d{11}|[A-Z0-9]{16})\b")
_RE_DATA_DOMANDA = re.compile(r"DATA\s+DELLA\s+(\d{2}/\d{2}/\d{4})")
_RE_DELIBERA = re.compile(r"DATA\s+DELIBERA\s+DI\s+ACCOGLIMENTO\s+(\d{2}/\d{2}/\d{4})")
_RE_NUMERO_RATE = re.compile(r"RATE\s+MENSILI:\s*(\d{1,3})\b")
_RE_TOTALE = re.compile(rf"TOTALE\s+DEL\s+DEBITO\s+({_IMPORTO})")
_RE_RATA = re.compile(
    rf"(?<![\d.,/])(\d{{1,3}})\s+({_IMPORTO})\s+({_IMPORTO})\s+({_IMPORTO})\s+(\d{{2}}/\d{{2}}/\d{{4}})"
)
# Sezione INPS dell'F24 d'esempio: periodo da, sede, causale, matricola,
# importo della prima rata, periodo a.
_RE_COORDINATE = re.compile(
    rf"(\d{{2}}/\d{{4}})\s+(\d{{4}})\s+([A-Z][A-Z0-9]{{1,3}})\s+(\d{{10}})\s+({_IMPORTO})\s+(\d{{2}}/\d{{4}})"
)

_ZIP_MAX_VOCI = 20
_ZIP_MAX_BYTE = 10 * 1024 * 1024


def _testo(testo: str) -> str:
    return re.sub(r"\s+", " ", (testo or "").upper())


def riconosci(testo: str) -> bool:
    """La lettera di accoglimento con piano: tutte e tre le prove nel testo."""
    t = _testo(testo)
    return all(m in t for m in ("ACCOGLIMENTO RICHIESTA RATEAZIONE", "PIANO DI AMMORTAMENTO", "MATRICOLA"))


def _cents(valore: str) -> int:
    return int(valore.replace(".", "").replace(",", ""))


def _iso(data_it: Optional[str]) -> Optional[str]:
    if not data_it:
        return None
    g, m, a = data_it.split("/")
    return f"{a}-{m}-{g}"


def _chiave_periodo(periodo: str) -> Tuple[int, int]:
    m, a = periodo.split("/")
    return int(a), int(m)


def leggi_piano(testo: str) -> Dict[str, Any]:
    """Il piano come dati; ``quadra`` dice se la somma delle rate e' il debito.

    Un campo che non si legge resta ``None`` e finisce in ``mancanti``: il
    piano che non quadra o manca di coordinate non abbina niente.
    """
    t = _testo(testo)
    rif = _RE_RIF.search(t)
    matricola = _RE_MATRICOLA.search(t)
    cf = _RE_CF.search(t)
    domanda = _RE_DATA_DOMANDA.search(t)
    delibera = _RE_DELIBERA.search(t)
    numero_rate = _RE_NUMERO_RATE.search(t)
    totale = _RE_TOTALE.search(t)

    rate: List[Dict[str, Any]] = []
    inizio = t.find("DATA SCADENZA")
    for m in _RE_RATA.finditer(t, inizio if inizio >= 0 else 0):
        numero = int(m.group(1))
        if numero != len(rate) + 1:
            continue
        rate.append({
            "numero": numero,
            "quota_capitale_cents": _cents(m.group(2)),
            "quota_interessi_cents": _cents(m.group(3)),
            "importo_cents": _cents(m.group(4)),
            "scadenza": _iso(m.group(5)),
        })

    coordinate = _RE_COORDINATE.search(t)
    periodi = sorted((coordinate.group(1), coordinate.group(6)), key=_chiave_periodo) if coordinate else [None, None]
    piano = {
        "rif": rif.group(0) if rif else None,
        "codice_sede": coordinate.group(2) if coordinate else (rif.group(1) if rif else None),
        "causale": coordinate.group(3) if coordinate else None,
        "matricola": (coordinate.group(4) if coordinate else None) or (matricola.group(1) if matricola else None),
        "periodo_da": periodi[0],
        "periodo_a": periodi[1],
        "codice_fiscale": cf.group(1) if cf else None,
        "data_domanda": _iso(domanda.group(1)) if domanda else None,
        "data_delibera": _iso(delibera.group(1)) if delibera else None,
        "numero_rate_dichiarato": int(numero_rate.group(1)) if numero_rate else None,
        "totale_debito_cents": _cents(totale.group(1)) if totale else None,
        "rate": rate,
    }
    somma = sum(r["importo_cents"] for r in rate)
    piano["somma_rate_cents"] = somma
    # La prova del piano e' il totale: la somma delle rate lette deve essere
    # il debito al centesimo. Il numero di rate stampato in lettera puo'
    # contare anche la prima («12 rate» con una prima rata e 10 costanti,
    # piano 14/02/2020): resta un'avvertenza visibile, non un rifiuto.
    piano["quadra"] = bool(rate and piano["totale_debito_cents"] == somma)
    piano["avvertenze"] = (
        [f"rate dichiarate {piano['numero_rate_dichiarato']}, lette {len(rate)}"]
        if rate and piano["numero_rate_dichiarato"] not in (None, len(rate)) else []
    )
    piano["mancanti"] = [k for k in ("rif", "codice_sede", "causale", "matricola", "periodo_da", "data_domanda")
                         if not piano[k]]
    return piano


# ── abbinamento rata ↔ quietanza ──────────────────────────────────────────

def _periodo_riga(riga: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    da = riga.get("periodo_da") or riga.get("periodo_riferimento")
    a = riga.get("periodo_a")
    if not a:
        # «9 2025 9 2025»: il periodo a e' la seconda coppia mese/anno.
        coppie = re.findall(r"(\d{1,2})\s+(\d{4})", str(riga.get("periodo_raw") or ""))
        if len(coppie) == 2:
            a = f"{int(coppie[1][0]):02d}/{coppie[1][1]}"
    return da, a


def _riga_della_dilazione(riga: Dict[str, Any], piano: Dict[str, Any]) -> bool:
    da, a = _periodo_riga(riga)
    return (
        str(riga.get("codice_sede") or "") == piano["codice_sede"]
        and str(riga.get("causale") or "").upper() == piano["causale"]
        and str(riga.get("matricola") or "") == piano["matricola"]
        and da == piano["periodo_da"]
        and (a is None or a == piano["periodo_a"])
    )


def _cents_riga(riga: Dict[str, Any]) -> Optional[int]:
    if isinstance(riga.get("importo_debito_cents"), int):
        return riga["importo_debito_cents"]
    try:
        return round(float(riga.get("importo_debito") or 0) * 100)
    except (TypeError, ValueError):
        return None


def pagamenti_della_dilazione(piano: Dict[str, Any], quietanze: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """I versamenti della dilazione, uno per pagamento (le copie si uniscono)."""
    gruppi: Dict[str, Dict[str, Any]] = {}
    for q in quietanze:
        if q.get("entity_status") == "deleted" or q.get("status") == "eliminato":
            continue
        data = str(q.get("data_pagamento") or "")[:10]
        if not data or (piano.get("data_domanda") and data < piano["data_domanda"]):
            continue
        righe = [r for r in (q.get("sezione_inps") or []) if _riga_della_dilazione(r, piano)]
        if len(righe) != 1:
            continue  # due righe della stessa dilazione nella stessa delega: da guardare a mano
        cents = _cents_riga(righe[0])
        protocollo = q.get("protocollo_telematico") or (q.get("dati_generali") or {}).get("protocollo_telematico")
        chiave = f"{protocollo}|{data}|{cents}" if protocollo else f"id:{q.get('id')}"
        p = gruppi.setdefault(chiave, {
            "chiave": chiave, "data": data, "protocollo": protocollo, "importo_cents": cents,
            "quietanza_ids": [], "movimento_id": None,
        })
        p["quietanza_ids"].append(str(q.get("id")))
        riscontro = q.get("riscontro_banca") or {}
        if riscontro.get("stato") == "RISCONTRATO_BANCA" and riscontro.get("movimento_id"):
            p["movimento_id"] = riscontro["movimento_id"]
    for p in gruppi.values():
        p["quietanza_ids"].sort()
    return sorted(gruppi.values(), key=lambda p: (p["data"], p["chiave"]))


def abbina_rate(piano: Dict[str, Any], quietanze: Iterable[Dict[str, Any]], oggi: Optional[str] = None) -> Dict[str, Any]:
    """Ogni rata col suo pagamento; i pagamenti in piu' restano elencati."""
    oggi = oggi or date.today().isoformat()
    pagamenti = pagamenti_della_dilazione(piano, quietanze) if not piano.get("mancanti") and piano.get("quadra") else []
    usati: set = set()
    rate = []
    for rata in sorted(piano.get("rate") or [], key=lambda r: r["numero"]):
        scelto = next((p for p in pagamenti if p["chiave"] not in usati
                       and p["importo_cents"] == rata["importo_cents"]), None)
        esito = {**rata, "quietanza_ids": [], "movimento_id": None, "data_pagamento": None}
        if scelto:
            usati.add(scelto["chiave"])
            esito.update(stato=RATA_PAGATA, quietanza_ids=scelto["quietanza_ids"],
                         movimento_id=scelto["movimento_id"], data_pagamento=scelto["data"],
                         protocollo=scelto["protocollo"],
                         oltre_scadenza=bool(rata["scadenza"] and scelto["data"] > rata["scadenza"]))
        else:
            esito["stato"] = RATA_SCADUTA if rata["scadenza"] and rata["scadenza"] < oggi else RATA_DA_PAGARE
        rate.append(esito)
    # I versamenti della dilazione rimasti senza rata si affiancano, in ordine,
    # alle rate senza pagamento: e' un fatto da verificare, non un pagamento.
    restanti = [p for p in pagamenti if p["chiave"] not in usati]
    aperte = [r for r in rate if r["stato"] != RATA_PAGATA]
    for rata, p in zip(aperte, restanti):
        rata.update(stato=RATA_IMPORTO_DIVERSO, versamento_diverso={
            "data": p["data"], "importo_cents": p["importo_cents"], "protocollo": p["protocollo"],
            "quietanza_ids": p["quietanza_ids"], "movimento_id": p["movimento_id"],
            "differenza_cents": p["importo_cents"] - rata["importo_cents"],
        })
        usati.add(p["chiave"])
    pagate = sum(1 for r in rate if r["stato"] == RATA_PAGATA)
    return {
        "rate": rate,
        "pagamenti_non_previsti": [p for p in pagamenti if p["chiave"] not in usati],
        "stato": "SALDATA" if rate and pagate == len(rate) else "IN_CORSO",
        "rate_pagate": pagate,
        "residuo_cents": sum(r["importo_cents"] for r in rate if r["stato"] != RATA_PAGATA),
    }


# ── scrittura ─────────────────────────────────────────────────────────────

def id_dilazione(piano: Dict[str, Any]) -> str:
    return f"dilazione_inps:{piano['rif']}"


async def deposita_piano(db, piano: Dict[str, Any], *, documento_id: Optional[str], filename: str,
                         sha256: Optional[str]) -> Optional[str]:
    """Il piano entra (o si aggiorna) in ``dilazioni_inps``; stesso rif, stessa riga."""
    if not piano.get("rif") or not piano.get("quadra") or piano.get("mancanti"):
        return None
    did = id_dilazione(piano)
    now = datetime.now(timezone.utc).isoformat()
    dati = {k: v for k, v in piano.items() if k not in ("rate", "mancanti")}
    await db[COLL_DILAZIONI_INPS].update_one(
        {"id": did},
        {"$set": {**dati, "piano": piano["rate"], "documento_id": documento_id,
                  "filename": filename, "sha256": sha256, "aggiornato_il": now},
         "$setOnInsert": {"id": did, "creato_il": now}},
        upsert=True,
    )
    return did


def _etichetta(dil: Dict[str, Any], rata: Dict[str, Any]) -> Dict[str, Any]:
    return {"dilazione_id": dil["id"], "rif": dil.get("rif"), "rata": rata["numero"],
            "di": len(dil.get("piano") or []), "scadenza": rata["scadenza"]}


async def collega_dilazioni(db, *, dry_run: bool = False, oggi: Optional[str] = None) -> Dict[str, Any]:
    """Abbina le rate di ogni piano; scrive solo cio' che cambia; apre e chiude alert."""
    from app.services.alert_engine import genera_alert, risolvi_alert

    dilazioni = await db[COLL_DILAZIONI_INPS].find({}, {"_id": 0}).to_list(500)
    if not dilazioni:
        return {"dilazioni": 0}
    causali = sorted({d.get("causale") for d in dilazioni if d.get("causale")})
    quietanze = await db[COLL_QUIETANZE_F24].find(
        {"codici_tributo": {"$in": causali}}, {"_id": 0, "pdf_data": 0},
    ).to_list(5000)

    scritti = {"dilazioni": 0, "quietanze": 0, "alert_aperti": 0, "alert_chiusi": 0}
    esiti = []
    etichette: Dict[str, Dict[str, Any]] = {}
    for dil in dilazioni:
        piano = {**dil, "rate": dil.get("piano") or [], "mancanti": []}
        esito = abbina_rate(piano, quietanze, oggi=oggi)
        esiti.append({"id": dil["id"], "rif": dil.get("rif"), **esito})
        for r in esito["rate"]:
            for qid in r["quietanza_ids"]:
                etichette[qid] = _etichetta(dil, r)
            for qid in (r.get("versamento_diverso") or {}).get("quietanza_ids") or []:
                etichette[qid] = {**_etichetta(dil, r), "importo_diverso": True}
        if dry_run:
            continue
        nuovo = {"rate": esito["rate"], "stato": esito["stato"], "rate_pagate": esito["rate_pagate"],
                 "residuo_cents": esito["residuo_cents"],
                 "pagamenti_non_previsti": esito["pagamenti_non_previsti"]}
        if any(dil.get(k) != v for k, v in nuovo.items()):
            await db[COLL_DILAZIONI_INPS].update_one({"id": dil["id"]}, {"$set": nuovo})
            scritti["dilazioni"] += 1
        for r in esito["rate"]:
            entita = f"{dil['id']}#{r['numero']}"
            if r["stato"] in (RATA_SCADUTA, RATA_IMPORTO_DIVERSO):
                diverso = r.get("versamento_diverso")
                fatto = (
                    f"versati {diverso['importo_cents'] / 100:.2f} EUR il {diverso['data']} "
                    f"(differenza {diverso['differenza_cents'] / 100:+.2f} EUR)" if diverso else
                    f"nessuna quietanza F24 con sede {dil.get('codice_sede')}, causale {dil.get('causale')}, "
                    f"matricola {dil.get('matricola')}, periodo {dil.get('periodo_da')}"
                )
                creato = await genera_alert(
                    ALERT_RATA_NON_PAGATA, entita, COLL_DILAZIONI_INPS,
                    f"Dilazione INPS {dil.get('rif')}: rata {r['numero']}/{len(esito['rate'])} da "
                    f"{r['importo_cents'] / 100:.2f} EUR con scadenza {r['scadenza']}: {fatto}.", db,
                    extra={"record": [{"dilazione_id": dil["id"], **r}]},
                )
                scritti["alert_aperti"] += int(bool(creato))
            else:
                scritti["alert_chiusi"] += await risolvi_alert(ALERT_RATA_NON_PAGATA, entita, db)

    if not dry_run:
        for q in quietanze:
            qid = str(q.get("id"))
            voluta = etichette.get(qid)
            if q.get("dilazione_inps") == voluta:
                continue
            aggiornamento = {"$set": {"dilazione_inps": voluta}} if voluta else {"$unset": {"dilazione_inps": ""}}
            if voluta or "dilazione_inps" in q:
                await db[COLL_QUIETANZE_F24].update_one({"id": qid}, aggiornamento)
                scritti["quietanze"] += 1
    return {"dilazioni": len(dilazioni), "dry_run": dry_run, "esiti": esiti, "scritti": scritti}


# ── ingresso: Documenti > Import e posta ──────────────────────────────────

async def archivia_dilazione(db, *, filename: str, content: bytes, testo: str,
                             source_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Conserva l'originale, deposita il piano e abbina subito le rate."""
    import hashlib

    from app.routers.documenti import _archive_non_payment_document

    piano = leggi_piano(testo)
    metadata = {
        "rif": piano["rif"], "matricola": piano["matricola"], "causale": piano["causale"],
        "periodo_da": piano["periodo_da"], "periodo_a": piano["periodo_a"],
        "numero_rate": len(piano["rate"]), "totale_debito_cents": piano["totale_debito_cents"],
        "quadra": piano["quadra"], "mancanti": piano["mancanti"], "avvertenze": piano["avvertenze"],
        # Il piano non e' un pagamento: gli obblighi sono le rate, in dilazioni_inps.
        "obligation_status": "APERTO",
        "relation_keys": {"rif_dilazione": piano["rif"], "matricola_inps": piano["matricola"]},
    }
    archiviato = await _archive_non_payment_document(
        db, filename=filename, content=content, document_type=TIPO,
        metadata=metadata, source_context=source_context,
    )
    documento_id = archiviato.get("doc_id")
    did = await deposita_piano(db, piano, documento_id=documento_id, filename=filename,
                               sha256=hashlib.sha256(content).hexdigest())
    esito = None
    if did and documento_id:
        # Letto e depositato: nella coda documenti non resta «da verificare».
        await db["documents_inbox"].update_one(
            {"id": documento_id, "status": "da_verificare"},
            {"$set": {"status": "archiviato", "dilazione_id": did}},
        )
    if did:
        try:
            esito = await collega_dilazioni(db)
        except Exception as exc:  # noqa: BLE001 - il piano resta depositato, lo riprende il giro F24
            logger.error("Dilazione %s depositata ma rate non abbinate: %s: %s", did, type(exc).__name__, exc)
    archiviato.update({
        "workflow": "DILAZIONE_INPS", "dilazione_id": did, "piano": piano,
        "message": (
            f"Dilazione INPS {piano['rif']}: {len(piano['rate'])} rate, "
            f"{sum(r['importo_cents'] for r in piano['rate']) / 100:.2f} EUR"
            if did else
            f"Dilazione INPS conservata ma non letta per intero (quadra={piano['quadra']}, "
            f"mancano: {', '.join(piano['mancanti']) or '-'})"
        ),
        "abbinamento": {k: v for k, v in (esito or {}).items() if k != "esiti"} or None,
    })
    return archiviato


# Versione della ripresa: un piano «da verificare» si rilegge una volta per
# versione del lettore, mai a ogni giro.
RIPRESA_V = 1


async def riprendi_da_verificare(db, *, limite: int = 5) -> Dict[str, Any]:
    """Rilegge dall'originale i piani conservati in Documenti ma mai depositati
    in ``dilazioni_inps`` (lettura precedente «non quadra»); deposita quelli
    che oggi quadrano. Caso reale: il piano INPS.5100.14/02/2020.0079479,
    11 rate lette e «12» dichiarate, fermo da ottobre 2026."""
    import asyncio

    from app.services.originale_documento import OriginaleErrore, apri_per_impronta

    candidati = await db["documents_inbox"].find(
        {"document_type": TIPO, "status": "da_verificare", "dilazione_id": {"$exists": False},
         "ripresa_v": {"$ne": RIPRESA_V}},
        {"_id": 0, "id": 1, "filename": 1, "sha256": 1, "file_hash": 1, "parsed_metadata": 1},
    ).to_list(max(limite * 4, 20))
    esito: Dict[str, Any] = {"candidati": len(candidati), "depositati": 0, "ancora_non_quadra": 0,
                             "originale_assente": 0, "esiti": []}
    for doc in candidati[:limite]:
        sha = doc.get("sha256") or doc.get("file_hash")
        try:
            originale = await apri_per_impronta(db, sha)
        except (OriginaleErrore, Exception) as exc:  # noqa: BLE001 - il documento resta, si segnala
            esito["originale_assente"] += 1
            esito["esiti"].append({"id": doc["id"], "filename": doc.get("filename"),
                                   "esito": "originale_assente", "errore": f"{type(exc).__name__}: {exc}"[:200]})
            await db["documents_inbox"].update_one({"id": doc["id"]}, {"$set": {"ripresa_v": RIPRESA_V}})
            continue
        from app.routers.documenti import _pdf_text_for_detection

        testo = await asyncio.to_thread(_pdf_text_for_detection, originale.contenuto)
        piano = leggi_piano(testo)
        did = await deposita_piano(db, piano, documento_id=doc["id"], filename=doc.get("filename") or "",
                                   sha256=sha)
        metadata = {**(doc.get("parsed_metadata") or {}), "quadra": piano["quadra"],
                    "mancanti": piano["mancanti"], "avvertenze": piano["avvertenze"],
                    "numero_rate": len(piano["rate"]), "totale_debito_cents": piano["totale_debito_cents"]}
        aggiornamento: Dict[str, Any] = {"ripresa_v": RIPRESA_V, "parsed_metadata": metadata}
        if did:
            aggiornamento.update({"status": "archiviato", "dilazione_id": did})
            esito["depositati"] += 1
        else:
            esito["ancora_non_quadra"] += 1
        esito["esiti"].append({"id": doc["id"], "filename": doc.get("filename"), "rif": piano.get("rif"),
                               "esito": "depositato" if did else "non_quadra", "dilazione_id": did,
                               "avvertenze": piano["avvertenze"], "mancanti": piano["mancanti"]})
        await db["documents_inbox"].update_one({"id": doc["id"]}, {"$set": aggiornamento})
    return esito


def pdf_da_zip(contenuto: bytes) -> List[Tuple[str, bytes]]:
    """I PDF di ``Allegato.zip``: niente percorsi, voci e dimensioni limitate."""
    out: List[Tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(contenuto)) as archivio:
        voci = archivio.infolist()
        if len(voci) > _ZIP_MAX_VOCI:
            raise ValueError(f"ZIP con {len(voci)} voci")
        for voce in voci:
            nome = voce.filename
            if voce.is_dir() or not nome.lower().endswith(".pdf"):
                continue
            if "/" in nome or "\\" in nome or ".." in nome:
                raise ValueError(f"percorso non ammesso nello ZIP: {nome!r}")
            if voce.file_size > _ZIP_MAX_BYTE:
                raise ValueError(f"{nome}: {voce.file_size} byte decompressi")
            with archivio.open(voce) as f:
                dati = f.read(_ZIP_MAX_BYTE + 1)
            if len(dati) > _ZIP_MAX_BYTE:
                raise ValueError(f"{nome}: oltre {_ZIP_MAX_BYTE} byte")
            out.append((nome, dati))
    return out
