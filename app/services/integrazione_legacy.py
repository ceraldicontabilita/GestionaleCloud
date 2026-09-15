"""Integrazione dell'archivio legacy (``legacy_staging``, ex progetto
CeraldiFatture + modulo presenze) nei registri VIVI del gestionale, di HR e
di Lotti. Richiesta del titolare del 15/09/2026 («fallo tu su Supabase»):
il censimento aveva trovato dati mai integrati dopo la fusione del 14/09.

Cosa fa, sempre in modo idempotente (chiave = ``legacy_row_hash`` o
``legacy_id`` sul documento di destinazione), a lotti dallo scheduler:

* **fatture e chiusure giornaliere degli anni non ancora migrati** (2024-2025:
  la migrazione del 14/09 copriva solo il 2026) -> ``invoices`` e
  ``corrispettivi`` del gestionale, stessa forma dei documenti 2026
  (``fonte`` = ``legacy_staging_<anno>``, IVA 10% presunta, DA_VERIFICARE);
* **versamenti contanti in banca** (18, gen-ago 2026) -> prima nota cassa
  (uscita) + banca (entrata) col motore unico ``scrivi_movimento``;
* **modulo presenze** (lug-ago 2026): acconti in contanti e saldi in contanti
  delle liquidazioni -> ``paghe_mensili.acconti`` di HR + motore unico
  ``_ricalcola_stato_paga``; timbrature -> ``timbrature`` + ``presenze_cloud``
  di HR; anagrafiche HR create per chi ha movimenti ma non esiste in HR;
* **ordini fornitori storici** (54, lug-ago 2026) -> ``ordini_fornitori`` di
  Lotti (stato inviato).

Regole: dipendente riconosciuto per codice fiscale, poi per «Cognome Nome»
univoco, altrimenti la riga viene saltata e conteggiata (mai indovinato);
gli acconti pagati con bonifico NON diventano acconti HR (il bonifico arriva
dall'estratto conto: sarebbe contato due volte); i turni legacy sono tutti
bozze mai pubblicate e non vengono importati.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from datetime import timedelta

logger = logging.getLogger(__name__)

PROGETTO_LEGACY = "CeraldiFatture-staging"


def _fuso_roma():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Rome")
    except Exception:  # pragma: no cover - immagine senza tzdata: le presenze legacy sono di luglio-agosto (CEST)
        return timezone(timedelta(hours=2))


ROMA = _fuso_roma()
MARCA = "integrazione_legacy_2026-09-15"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(v: Any) -> Dict[str, Any]:
    if isinstance(v, dict):
        return v
    if isinstance(v, (str, bytes)):
        try:
            out = json.loads(v)
            return out if isinstance(out, dict) else {}
        except ValueError:
            return {}
    return {}


def _num(v: Any) -> float:
    try:
        return round(float(str(v).replace(",", ".")), 2)
    except (TypeError, ValueError):
        return 0.0


def _anno_di(data: Any) -> Optional[int]:
    testo = str(data or "")
    if len(testo) >= 4 and testo[:4].isdigit():
        return int(testo[:4])
    return None


def _norma_nome(*parti: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", " ".join(str(p or "") for p in parti).lower()).strip()


# ── lettura archivio ──────────────────────────────────────────────────────────

async def righe_legacy(con, tabella: str) -> List[Tuple[str, Dict[str, Any]]]:
    """(row_hash, row_data) di una tabella dell'archivio, righe cancellate escluse."""
    if not re.fullmatch(r"[a-z_]+", tabella):
        raise ValueError(f"tabella non ammessa: {tabella!r}")
    righe = await con.fetch(f'SELECT row_hash, row_data FROM legacy_staging."{tabella}"')
    out = []
    for r in righe:
        d = _json(r["row_data"])
        if d and not d.get("deleted_at"):
            out.append((str(r["row_hash"]), d))
    return out


# ── fatture e chiusure -> gestionale ─────────────────────────────────────────

def doc_fattura_legacy(row: Dict[str, Any], row_hash: str) -> Optional[Dict[str, Any]]:
    """Documento ``invoices`` nella forma delle 786 fatture 2026 gia' migrate."""
    anno = _anno_di(row.get("data") or row.get("data_fattura"))
    if not anno or row.get("id") in (None, ""):
        return None
    d = dict(row)
    d["_id"] = str(d["id"])
    d["anno"] = anno
    d["fonte"] = f"legacy_staging_{anno}"
    d["legacy_row_hash"] = row_hash
    d["legacy_source_table"] = "fatture"
    d["legacy_source_project"] = PROGETTO_LEGACY
    d.setdefault("data_documento", d.get("data"))
    totale = _num(d.get("importo"))
    d.setdefault("importo_totale", totale)
    d.setdefault("totale", totale)
    if d.get("totale_imponibile") is not None:
        d.setdefault("imponibile", _num(d.get("totale_imponibile")))
    imposta = d.get("totale_imposta") if d.get("totale_imposta") is not None else d.get("iva")
    if imposta is not None:
        d.setdefault("totale_iva", _num(imposta))
    d.setdefault("evidence_status", "DA_VERIFICARE")
    d.setdefault("stato_pagamento", "da_verificare")
    d["integrato_da"] = MARCA
    return d


def doc_chiusura_legacy(row: Dict[str, Any], row_hash: str) -> Optional[Dict[str, Any]]:
    """Documento ``corrispettivi`` come le 183 chiusure 2026 (IVA 10% presunta,
    normalizzazione del 14/09: nel legacy ``iva10`` conteneva l'imponibile)."""
    data = str(row.get("data") or "")
    anno = _anno_di(data)
    if not anno or row.get("id") in (None, ""):
        return None
    totale = _num(row.get("totale_corrispettivi") if row.get("totale_corrispettivi") is not None else row.get("incassato"))
    imponibile = round(totale / 1.1, 2)
    iva = round(totale - imponibile, 2)
    cassa = _num(row.get("cassa"))
    pos = _num(row.get("pos"))
    d = dict(row)
    d.update({
        "anno": anno, "mese": int(data[5:7]) if len(data) >= 7 and data[5:7].isdigit() else None,
        "fonte": f"legacy_staging_{anno}",
        "legacy_row_hash": row_hash, "legacy_source_id": str(row["id"]),
        "legacy_source_table": "chiusure_giornaliere", "legacy_source_project": PROGETTO_LEGACY,
        "legacy_totale_iva_originale": row.get("iva10"),
        "totale": totale, "totale_corrispettivi": totale, "incassato": _num(row.get("incassato")) or totale,
        "pagato_contanti": cassa, "pagato_elettronico": pos,
        "imponibile10": imponibile, "totale_imponibile": imponibile,
        "iva10": iva, "totale_iva": iva, "iva_da_versare10": iva,
        "iva_source": "chiusura_giornaliera_legacy",
        "iva_nota": ("Chiusura legacy integrata il 15/09/2026 con aliquota unica 10% presunta; "
                     "resta DA_VERIFICARE finche' non arriva l'XML RT."),
        "status": "DA_VERIFICARE", "quadratura_iva_status": "DA_VERIFICARE",
        "registrato_contabilita": False, "pos_riconciliata": bool(row.get("pos_riconciliata")),
        "integrato_da": MARCA,
    })
    return d


async def _esiste(db, collezione: str, row_hash: str, id_legacy: Any) -> bool:
    if await db[collezione].find_one({"legacy_row_hash": row_hash}, {"_id": 0, "id": 1}):
        return True
    for candidato in {id_legacy, str(id_legacy)}:
        if candidato in (None, "") or await db[collezione].find_one({"id": candidato}, {"_id": 0, "id": 1}) is None:
            continue
        return True
    return False


async def integra_fatture(db, con) -> Dict[str, Any]:
    esito = {"esaminate": 0, "inserite": 0, "gia_presenti": 0, "scartate": 0, "per_anno": {}}
    for row_hash, row in await righe_legacy(con, "fatture"):
        esito["esaminate"] += 1
        doc = doc_fattura_legacy(row, row_hash)
        if not doc:
            esito["scartate"] += 1
            continue
        if await _esiste(db, "invoices", row_hash, row.get("id")):
            esito["gia_presenti"] += 1
            continue
        await db["invoices"].insert_one(doc)
        esito["inserite"] += 1
        esito["per_anno"][str(doc["anno"])] = esito["per_anno"].get(str(doc["anno"]), 0) + 1
    return esito


async def integra_chiusure(db, con) -> Dict[str, Any]:
    esito = {"esaminate": 0, "inserite": 0, "gia_presenti": 0, "scartate": 0, "per_anno": {}}
    for row_hash, row in await righe_legacy(con, "chiusure_giornaliere"):
        esito["esaminate"] += 1
        doc = doc_chiusura_legacy(row, row_hash)
        if not doc:
            esito["scartate"] += 1
            continue
        if await _esiste(db, "corrispettivi", row_hash, row.get("id")):
            esito["gia_presenti"] += 1
            continue
        # stessa giornata gia' registrata da un'altra fonte (XML RT, CSV AdE)
        if await db["corrispettivi"].find_one({"data": doc["data"]}, {"_id": 0, "id": 1}):
            esito["gia_presenti"] += 1
            continue
        await db["corrispettivi"].insert_one(doc)
        esito["inserite"] += 1
        esito["per_anno"][str(doc["anno"])] = esito["per_anno"].get(str(doc["anno"]), 0) + 1
    return esito


# ── versamenti -> prima nota ──────────────────────────────────────────────────

def movimenti_versamento(row: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    importo = _num(row.get("importo"))
    data = str(row.get("data") or "")[:10]
    if importo <= 0 or len(data) < 10 or row.get("id") in (None, ""):
        return None
    id_cassa = f"legacy-vers-{row['id']}"
    descr = "Versamento contanti in banca"
    if row.get("note"):
        descr += f" — {row['note']}"
    comune = {"data": data, "importo": importo, "descrizione": descr, "categoria": "Versamento Banca",
              "source": "legacy_versamenti", "legacy_id": str(row["id"]), "integrato_da": MARCA,
              "created_at": row.get("created_at") or _now()}
    cassa = {"id": id_cassa, "tipo": "uscita", **comune}
    banca = {"id": f"{id_cassa}-banca", "tipo": "entrata", "movimento_cassa_id": id_cassa, **comune}
    return cassa, banca


async def integra_versamenti(db, con) -> Dict[str, Any]:
    from app.services.scritture_contabili import scrivi_movimento
    esito = {"esaminati": 0, "registrati": 0, "gia_presenti": 0, "scartati": 0, "importo": 0.0}
    for _h, row in await righe_legacy(con, "versamenti"):
        esito["esaminati"] += 1
        coppia = movimenti_versamento(row)
        if not coppia:
            esito["scartati"] += 1
            continue
        cassa, banca = coppia
        if await db["prima_nota_cassa"].find_one({"id": cassa["id"]}, {"_id": 0, "id": 1}):
            esito["gia_presenti"] += 1
            continue
        await scrivi_movimento(db, "cassa", cassa)
        await scrivi_movimento(db, "banca", banca)
        esito["registrati"] += 1
        esito["importo"] = round(esito["importo"] + cassa["importo"], 2)
    return esito


# ── modulo presenze -> HR ────────────────────────────────────────────────────

def competenza_acconto(row: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """(anno, mese) della busta a cui l'acconto si riferisce: 13/14 per
    tredicesima e quattordicesima (convenzione HR), altrimenti il mese della
    data; ``acconto_tfr`` e i bonifici non sono acconti su busta."""
    causale = str(row.get("causale") or "").lower()
    if str(row.get("modalita") or "").lower() == "bonifico" or causale == "acconto_tfr":
        return None
    try:
        if row.get("anno_riferimento") and row.get("mese_riferimento"):
            return int(row["anno_riferimento"]), int(row["mese_riferimento"])
    except (TypeError, ValueError):
        pass
    data = str(row.get("data") or "")
    anno = _anno_di(data)
    if not anno:
        return None
    if causale == "acconto_13":
        return anno, 13
    if causale == "acconto_14":
        return anno, 14
    try:
        return anno, int(data[5:7])
    except ValueError:
        return None


def ora_roma(ts: Any) -> Tuple[Optional[str], Optional[str]]:
    """(``HH:MM`` a Roma, ISO) da un timestamp legacy in UTC."""
    testo = str(ts or "").strip()
    if not testo:
        return None, None
    try:
        dt = datetime.fromisoformat(testo.replace("Z", "+00:00"))
    except ValueError:
        return None, None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ROMA).strftime("%H:%M"), dt.isoformat()


class _Anagrafica:
    """Profili legacy -> dipendenti HR: CF, poi «Cognome Nome» univoco."""

    def __init__(self, dipendenti_hr: Iterable[Dict[str, Any]], profili: Iterable[Dict[str, Any]]):
        self.per_cf: Dict[str, Dict[str, Any]] = {}
        self.per_nome: Dict[str, List[Dict[str, Any]]] = {}
        for d in dipendenti_hr:
            if d.get("merged_into"):
                continue
            cf = str(d.get("codice_fiscale") or "").strip().upper()
            if cf:
                self.per_cf.setdefault(cf, d)
            self.per_nome.setdefault(_norma_nome(d.get("cognome"), d.get("nome")), []).append(d)
        self.profili = {str(p.get("id")): p for p in profili}
        self.creati: List[Dict[str, Any]] = []
        self.senza_match: Dict[str, str] = {}

    def hr_di(self, profilo_id: Any) -> Optional[Dict[str, Any]]:
        p = self.profili.get(str(profilo_id))
        if not p:
            return None
        cf = str(p.get("codice_fiscale") or "").strip().upper()
        if cf and cf in self.per_cf:
            return self.per_cf[cf]
        candidati = self.per_nome.get(_norma_nome(p.get("cognome"), p.get("nome")), [])
        if len(candidati) == 1:
            return candidati[0]
        return None

    def nuovo_dipendente(self, profilo_id: Any) -> Optional[Dict[str, Any]]:
        """Anagrafica HR per un profilo legacy attivo che non esiste in HR."""
        p = self.profili.get(str(profilo_id))
        if not p or p.get("eliminato") or p.get("attivo") is False:
            return None
        cognome = str(p.get("cognome") or "").strip().title()
        nome = str(p.get("nome") or "").strip().title()
        cf = str(p.get("codice_fiscale") or "").strip().upper()
        if not cognome or len(cf) != 16:
            return None  # senza codice fiscale non si crea nessuno (mai indovinato)
        doc = {
            "id": str(uuid.uuid4()), "nome": nome, "cognome": cognome, "nome_completo": f"{cognome} {nome}".strip(),
            "codice_fiscale": cf,
            "data_nascita": p.get("data_nascita"), "telefono": p.get("telefono"), "email": p.get("email"),
            "indirizzo": p.get("indirizzo"), "data_assunzione": p.get("data_assunzione"),
            "livello": p.get("livello_ccnl") or "", "mansione": p.get("mansione") or "",
            "stato": "attivo", "attivo": True, "in_carico": True, "lotti_operatore": False,
            "ruolo_app": "dipendente", "ricostruito_da": MARCA,
            "note_audit": ("15/09/2026: creata dal modulo presenze del vecchio gestionale (profilo "
                           f"{p.get('id')}), che registrava per questa persona acconti/presenze/liquidazioni; "
                           "nessun cedolino in archivio: verificare inquadramento."),
            "created_at": _now(),
        }
        self.creati.append(doc)
        cf = doc["codice_fiscale"]
        if cf:
            self.per_cf[cf] = doc
        self.per_nome.setdefault(_norma_nome(cognome, nome), []).append(doc)
        return doc


async def _ricalcola(db_hr, dip_id: str, anno: int, mese: int) -> None:
    from app.hr.routers.dipendenti_cloud import _ricalcola_stato_paga
    await _ricalcola_stato_paga(db_hr, dip_id, anno, mese)


async def _aggiungi_acconto(db_hr, dip: Dict[str, Any], anno: int, mese: int, acconto: Dict[str, Any]) -> bool:
    """Aggiunge un acconto alla busta (anno, mese) se ``legacy_id`` non c'e' gia'."""
    filtro = {"dipendente_id": dip["id"], "anno": anno, "mese": mese}
    p = await db_hr.paghe_mensili.find_one(filtro)
    acconti = list((p or {}).get("acconti") or [])
    if any(a.get("legacy_id") == acconto["legacy_id"] for a in acconti):
        return False
    acconti.append(acconto)
    await db_hr.paghe_mensili.update_one(
        filtro,
        {"$set": {"acconti": acconti, "updated_at": _now()},
         "$setOnInsert": {"dipendente_id": dip["id"], "anno": anno, "mese": mese,
                          "dipendente_nome": dip.get("nome_completo") or f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip()}},
        upsert=True)
    await _ricalcola(db_hr, dip["id"], anno, mese)
    return True


async def integra_presenze_hr(db_hr, con) -> Dict[str, Any]:
    esito = {"acconti": {"esaminati": 0, "inseriti": 0, "gia_presenti": 0, "saltati_bonifico_o_tfr": 0,
                         "senza_dipendente": 0, "importo": 0.0},
             "liquidazioni": {"esaminate": 0, "saldi_contanti_inseriti": 0, "gia_presenti": 0, "senza_dipendente": 0, "importo": 0.0},
             "timbrature": {"esaminate": 0, "inserite": 0, "gia_presenti": 0, "senza_dipendente": 0, "presenze_create": 0},
             "anagrafiche_create": [], "profili_senza_match": {}}
    dipendenti = await db_hr.dipendenti.find({}, {"_id": 0, "pin_hash": 0, "pin_lookup": 0}).to_list(2000)
    profili = [r for _h, r in await righe_legacy(con, "presenze_profili")]
    ana = _Anagrafica(dipendenti, profili)

    async def dip_per(profilo_id: Any) -> Optional[Dict[str, Any]]:
        dip = ana.hr_di(profilo_id)
        if dip:
            return dip
        nuovo = ana.nuovo_dipendente(profilo_id)
        if nuovo:
            await db_hr.dipendenti.insert_one(dict(nuovo))
            esito["anagrafiche_create"].append(nuovo["nome_completo"])
            return nuovo
        p = ana.profili.get(str(profilo_id)) or {}
        esito["profili_senza_match"][str(profilo_id)] = f"{p.get('cognome', '')} {p.get('nome', '')}".strip() or "?"
        return None

    # acconti in contanti
    for _h, row in await righe_legacy(con, "presenze_acconti"):
        e = esito["acconti"]
        e["esaminati"] += 1
        comp = competenza_acconto(row)
        if not comp:
            e["saltati_bonifico_o_tfr"] += 1
            continue
        dip = await dip_per(row.get("dipendente_id"))
        if not dip:
            e["senza_dipendente"] += 1
            continue
        importo = _num(row.get("importo"))
        if importo <= 0:
            continue
        acconto = {"importo": importo, "data": str(row.get("data") or "")[:10] or None,
                   "nota": f"{row.get('causale') or 'acconto'}" + (f" — {row['note']}" if row.get("note") else ""),
                   "modalita": row.get("modalita") or "contanti", "legacy_id": f"acc:{row.get('id')}",
                   "fonte": "presenze_legacy"}
        if await _aggiungi_acconto(db_hr, dip, comp[0], comp[1], acconto):
            e["inseriti"] += 1
            e["importo"] = round(e["importo"] + importo, 2)
        else:
            e["gia_presenti"] += 1

    # saldi in contanti delle liquidazioni
    for _h, row in await righe_legacy(con, "presenze_liquidazioni"):
        e = esito["liquidazioni"]
        e["esaminate"] += 1
        contanti = _num(row.get("contanti"))
        if contanti <= 0:
            continue
        dip = await dip_per(row.get("dipendente_id"))
        if not dip:
            e["senza_dipendente"] += 1
            continue
        try:
            anno, mese = int(row.get("anno")), int(row.get("mese"))
        except (TypeError, ValueError):
            continue
        acconto = {"importo": contanti, "data": str(row.get("liquidato_il") or row.get("confermata_il") or "")[:10] or None,
                   "nota": f"Saldo stipendio {mese:02d}/{anno} in contanti (liquidazione modulo presenze)",
                   "modalita": "contanti", "legacy_id": f"liq:{row.get('id')}", "fonte": "presenze_legacy"}
        if await _aggiungi_acconto(db_hr, dip, anno, mese, acconto):
            e["saldi_contanti_inseriti"] += 1
            e["importo"] = round(e["importo"] + contanti, 2)
        else:
            e["gia_presenti"] += 1

    # timbrature -> timbrature + presenze_cloud
    for _h, row in await righe_legacy(con, "presenze"):
        e = esito["timbrature"]
        e["esaminate"] += 1
        legacy_id = str(row.get("id") or "")
        data = str(row.get("data") or "")[:10]
        ora_in, ts_in = ora_roma(row.get("ts_entrata"))
        if not legacy_id or not data or not ts_in:
            continue
        if await db_hr.timbrature.find_one({"legacy_id": legacy_id}, {"_id": 0, "id": 1}):
            e["gia_presenti"] += 1
            continue
        dip = await dip_per(row.get("dipendente_id"))
        if not dip:
            e["senza_dipendente"] += 1
            continue
        nome = dip.get("nome_completo") or f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip()
        base_rec = {"dipendente_id": dip["id"], "dipendente_nome": nome, "data": data,
                    "lat": None, "lng": None, "accuracy": None, "distanza_m": None, "fuori_sede": None,
                    "fonte": "presenze_legacy", "tipo_timbratura": row.get("tipo_timbratura"), "legacy_id": legacy_id}
        await db_hr.timbrature.insert_one({"id": f"tmb_legacy_{legacy_id[:12]}_in", "tipo": "entrata", "ora": ora_in, "ts": ts_in, **base_rec})
        ora_out, ts_out = ora_roma(row.get("ts_uscita"))
        if ts_out:
            await db_hr.timbrature.insert_one({"id": f"tmb_legacy_{legacy_id[:12]}_out", "tipo": "uscita", "ora": ora_out, "ts": ts_out, **base_rec})
        e["inserite"] += 1
        if not await db_hr.presenze_cloud.find_one({"dipendente_id": dip["id"], "data": data}, {"_id": 0, "id": 1}):
            presenza = {"dipendente_id": dip["id"], "data": data, "stato": "presente", "giustificativo": "P",
                        "origine": "timbratura_legacy", "entrata": ora_in, "validata": False, "legacy_id": legacy_id}
            if ts_out:
                minuti = round((datetime.fromisoformat(ts_out) - datetime.fromisoformat(ts_in)).total_seconds() / 60)
                presenza.update({"uscita": ora_out, "minuti": minuti, "ore_lavorate": round(minuti / 60, 2),
                                 "validata": minuti >= 60})
            await db_hr.presenze_cloud.update_one({"dipendente_id": dip["id"], "data": data}, {"$set": presenza}, upsert=True)
            e["presenze_create"] += 1
    return esito


# ── ordini storici -> Lotti ─────────────────────────────────────────────────

def _data_ordine(row: Dict[str, Any]) -> str:
    testo = str(row.get("date") or "")
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", testo)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return str(row.get("created_at") or "")[:10]


def doc_ordine_legacy(row: Dict[str, Any], calcola_totali) -> Optional[Dict[str, Any]]:
    if row.get("id") in (None, ""):
        return None
    fornitore = str(row.get("supplier") or "").strip()
    righe = []
    for it in row.get("items") or []:
        if not isinstance(it, dict) or not it.get("name"):
            continue
        righe.append({"prodotto_id": "", "nome": str(it.get("name")).strip(), "fornitore": fornitore,
                      "quantita": _num(it.get("qty")) or 1.0, "unita": str(it.get("conf") or "pz").lower(),
                      "prezzo_ultimo": _num(it.get("price")), "iva_pct": 0, "note": "", "richiesto_da": ""})
    if not righe:
        return None
    totali = calcola_totali(righe)
    totali["totale_legacy"] = _num(row.get("total"))
    creato = row.get("created_at") or _now()
    return {"id": f"legacy-ord-{row['id']}", "legacy_id": str(row["id"]), "data_ordine": _data_ordine(row),
            "stato": "inviato_fornitori", "source": "storico_gestionale_legacy", "fornitore": fornitore,
            "reparto": "", "operatore": "", "prodotti": righe, "totali": totali, "ricette_da_produrre": [],
            "note_operatore": str(row.get("note") or ""), "canale": row.get("channel"),
            "inviato_il": creato, "created_at": creato, "updated_at": _now(), "integrato_da": MARCA}


async def integra_ordini_lotti(db_lotti, con) -> Dict[str, Any]:
    from app.lotti.routers.ordini_fornitori import calcola_totali_ordine
    esito = {"esaminati": 0, "inseriti": 0, "gia_presenti": 0, "scartati": 0}
    for _h, row in await righe_legacy(con, "ceraldi_storico_ordini"):
        esito["esaminati"] += 1
        doc = doc_ordine_legacy(row, calcola_totali_ordine)
        if not doc:
            esito["scartati"] += 1
            continue
        if await db_lotti.ordini_fornitori.find_one({"id": doc["id"]}, {"_id": 0, "id": 1}):
            esito["gia_presenti"] += 1
            continue
        await db_lotti.ordini_fornitori.insert_one(doc)
        esito["inseriti"] += 1
    return esito


# ── orchestrazione ──────────────────────────────────────────────────────────

def _db_hr():
    try:
        from app.hr.database import Database as DatabaseHR, DatabaseNonConfigurato
        db = DatabaseHR.get_db()
        return None if db is None or isinstance(db, DatabaseNonConfigurato) else db
    except Exception:
        return None


def _db_lotti():
    try:
        from app.lotti.db import database
        return database
    except Exception:
        return None


async def integra_legacy(db_gest) -> Dict[str, Any]:
    """Un giro completo. Ogni blocco e' isolato: un errore non ferma gli altri."""
    from app.services import postgres_diretto
    dsn_valore = postgres_diretto.dsn()
    if not dsn_valore:
        return {"stato": "dsn_mancante"}
    esito: Dict[str, Any] = {"stato": "ok", "eseguito_il": _now()}
    con = await postgres_diretto.connetti(dsn_valore)
    try:
        blocchi = [
            ("fatture", lambda: integra_fatture(db_gest, con)),
            ("chiusure", lambda: integra_chiusure(db_gest, con)),
            ("versamenti", lambda: integra_versamenti(db_gest, con)),
        ]
        db_hr = _db_hr()
        if db_hr is not None:
            blocchi.append(("presenze_hr", lambda: integra_presenze_hr(db_hr, con)))
        else:
            esito["presenze_hr"] = {"stato": "hr_non_configurato"}
        db_lotti = _db_lotti()
        if db_lotti is not None:
            blocchi.append(("ordini_lotti", lambda: integra_ordini_lotti(db_lotti, con)))
        for nome, fn in blocchi:
            try:
                esito[nome] = await fn()
            except Exception as exc:  # noqa: BLE001 - un blocco non ferma gli altri
                logger.exception("integrazione legacy: blocco %s fallito", nome)
                esito[nome] = {"stato": "errore", "errore": str(exc)}
                esito["stato"] = "parziale"
    finally:
        await con.close()
    return esito
