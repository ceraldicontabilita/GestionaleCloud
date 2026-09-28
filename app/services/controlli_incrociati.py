"""Controlli incrociati: segnali, mai correzioni.

Tre domande che nessun motore di abbinamento si fa, perche' ognuno guarda il
suo pezzo:

1. **Incongruenze di pagamento**
   - il beneficiario scritto dalla banca («FAVORE X») non e' il fornitore
     della fattura collegata;
   - una fattura ha due o piu' uscite in Prima Nota Banca, ognuna per
     l'importo intero (pagata due volte o collegata due volte);
   - una fattura degli ultimi 45 giorni supera di 4 volte la mediana del
     suo fornitore (almeno 6 confronti).
2. **Copertura degli estratti**: per ogni fonte, i mesi dell'anno senza
   nemmeno un movimento, dal primo mese in cui la fonte esiste al mese
   scorso. BPM, SumUp e terminale Numia hanno movimenti ogni mese: un mese
   vuoto e' un estratto non caricato e apre un avviso (anche Telegram, una
   volta). PayPal e' saltuario: il mese vuoto si mostra, non si avvisa. Nexi
   ha il suo avviso per periodo (`ESTRATTO_NEXI_MANCANTE`), il mutuo un
   estratto l'anno.
3. **RT dimenticata**: un giorno con incassi POS e senza chiusura RT, in
   mezzo a giorni chiusi regolarmente (prima dell'ultimo corrispettivo), che
   la chiusura del giorno dopo non copre e che non e' una chiusura
   dell'attivita'. La coda finale e' gia' di `fonti_ferme`.

Ogni avviso nomina il record. Un avviso che il titolare ha ignorato non
rinasce al giro dopo.
"""
from __future__ import annotations

import logging
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

GIORNI_IMPORTO_ANOMALO = 45
MOLTIPLICATORE_ANOMALO = 4
CONFRONTI_MINIMI = 6
GIORNI_ATTESA_RT = 2

_STATI_RIGA_ANNULLATA = {"deleted", "eliminato", "annullato", "stornato", "quarantena"}
_FORME_SOCIETARIE = {
    "srl", "srls", "spa", "sas", "snc", "sapa", "scarl", "soc", "societa", "coop",
    "responsabilita", "limitata", "sede", "secondaria", "italia", "group", "ditta",
    "ing", "dott", "avv", "rag", "ragioniere", "geom", "arch", "studio", "import", "export",
}

FONTI_ESTRATTO: tuple[dict[str, Any], ...] = (
    {"chiave": "bpm", "etichetta": "Estratto conto BPM",
     "collection": "estratto_conto_movimenti", "campo": "data", "avvisa": True},
    {"chiave": "sumup", "etichetta": "Estratto SumUp (Mastercard)",
     "collection": "sumup_conto_movimenti", "campo": "data", "avvisa": True},
    {"chiave": "numia", "etichetta": "Transazioni terminale Numia",
     "collection": "pos_terminal_transactions", "campo": "data", "avvisa": True},
    {"chiave": "paypal", "etichetta": "PayPal",
     "collection": "paypal_transactions", "campo": "data", "avvisa": False},
)


def _oggi() -> date:
    return datetime.now(timezone.utc).date()


def _giorno(valore: Any) -> str:
    if isinstance(valore, datetime):
        return valore.strftime("%Y-%m-%d")
    testo = str(valore or "")[:10]
    return testo if re.fullmatch(r"\d{4}-\d{2}-\d{2}", testo) else ""


def _numero(valore: Any) -> Optional[float]:
    try:
        return float(valore)
    except (TypeError, ValueError):
        return None


async def _gia_segnalato(db, codice: str, entita_id: str) -> bool:
    """Aperto o ignorato dal titolare: in entrambi i casi non si riapre."""
    esistente = await db["alerts"].find_one(
        {"codice": codice, "entita_id": entita_id, "stato": {"$in": ["aperto", "ignorato"]}},
        {"_id": 0, "id": 1},
    )
    return bool(esistente)


async def _segnala(db, codice: str, entita_id: str, collection: str, dettaglio: str,
                   extra: Dict[str, Any], *, telegram: bool = False) -> bool:
    from app.services.alert_engine import genera_alert

    if await _gia_segnalato(db, codice, entita_id):
        return False
    nuovo = await genera_alert(codice, entita_id, collection, dettaglio, db, extra=extra)
    if nuovo and telegram:
        from app.services.telegram_notifications import send_notification

        esito = await send_notification(f"<b>{nuovo['titolo']}</b>\n{dettaglio}")
        if not esito.get("success"):
            logger.warning("Controlli incrociati: Telegram non inviato per %s %s (%s)",
                           codice, entita_id, esito.get("error"))
    return bool(nuovo)


async def _chiudi_superati(db, codice: str, attuali: Set[str], tieni=None) -> int:
    """Chiude gli avvisi aperti di ``codice`` il cui problema non c'e' piu'.

    ``tieni`` protegge quelli che questo giro non ha potuto guardare (fonte
    illeggibile, giorno fuori finestra): non visto non vuol dire risolto."""
    from app.services.alert_engine import risolvi_alert

    aperti = await db["alerts"].find(
        {"codice": codice, "stato": "aperto"}, {"_id": 0, "entita_id": 1}).to_list(None)
    chiusi = 0
    for alert in aperti:
        entita = str(alert.get("entita_id") or "")
        if entita and entita not in attuali and not (tieni and tieni(entita)):
            chiusi += await risolvi_alert(codice, entita, db, resolved_by="controlli_incrociati")
    return chiusi


# --- 1. Incongruenze di pagamento ------------------------------------------

def beneficiario_della_causale(testo: str) -> str:
    """«... FAVORE Rosaria Marotta NOTPROVIDE - ...» → «Rosaria Marotta»."""
    trovato = re.search(r"\bFAVORE\s+(.+?)(?:\s+NOT\s?PROVIDE|\s+-\s|$)", str(testo or ""), re.I)
    return trovato.group(1).strip() if trovato else ""


def _parole_nome(nome: str) -> Set[str]:
    parole = re.findall(r"[a-z0-9]+", str(nome or "").lower().replace("'", " "))
    return {p for p in parole if len(p) >= 3 and p not in _FORME_SOCIETARIE}


def stesso_soggetto(beneficiario: str, fornitore: str) -> bool:
    """Almeno una parola del nome in comune, forme societarie e titoli esclusi.

    La banca tronca («EDILIZIA SANTAMARIA IMPORT EXPORT S») e inverte nome e
    cognome («FABIANA CIERVO»): una parola vera in comune basta. Un
    beneficiario illeggibile non e' una prova di niente.
    """
    b, f = _parole_nome(beneficiario), _parole_nome(fornitore)
    if not b or not f:
        return True
    if b & f:
        return True
    # «L.MORELLI» diventa «lmorelli»: vale anche una parola contenuta nell'altra.
    return any(x in y or y in x for x in b for y in f if min(len(x), len(y)) >= 5)


async def _fatture_per_id(db, ids: Set[str]) -> Dict[str, Dict[str, Any]]:
    if not ids:
        return {}
    righe = await db["invoices"].find(
        {"id": {"$in": sorted(ids)}},
        {"_id": 0, "id": 1, "supplier_name": 1, "invoice_number": 1, "total_amount": 1,
         "invoice_date": 1, "supplier_vat": 1},
    ).to_list(None)
    return {str(r["id"]): r for r in righe if r.get("id")}


async def controlla_beneficiari(db) -> List[Dict[str, Any]]:
    movimenti = await db["estratto_conto_movimenti"].find(
        {"$or": [{"fattura_id": {"$nin": [None, ""]}}, {"fattura_ids.0": {"$exists": True}}]},
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "descrizione": 1,
         "descrizione_originale": 1, "fattura_id": 1, "fattura_ids": 1},
    ).to_list(None)
    per_movimento: Dict[str, List[str]] = {}
    for m in movimenti:
        ids = [str(i) for i in (m.get("fattura_ids") or []) if i] or [str(m.get("fattura_id"))]
        per_movimento[str(m.get("id"))] = ids
    fatture = await _fatture_per_id(db, {i for ids in per_movimento.values() for i in ids})
    trovati = []
    for m in movimenti:
        beneficiario = beneficiario_della_causale(
            m.get("descrizione_originale") or m.get("descrizione"))
        if not beneficiario:
            continue
        for fid in per_movimento[str(m.get("id"))]:
            fattura = fatture.get(fid)
            if not fattura or stesso_soggetto(beneficiario, fattura.get("supplier_name")):
                continue
            trovati.append({"movimento_id": m.get("id"), "fattura_id": fid,
                            "beneficiario": beneficiario,
                            "fornitore": fattura.get("supplier_name"),
                            "numero": fattura.get("invoice_number"),
                            "data": _giorno(m.get("data")), "importo": m.get("importo")})
    return trovati


async def controlla_pagate_due_volte(db) -> List[Dict[str, Any]]:
    from app.routers.prima_nota_module.common import SOURCES_ESCLUSE

    righe = await db["prima_nota_banca"].find(
        {"fattura_id": {"$nin": [None, ""]}},
        {"_id": 0, "id": 1, "fattura_id": 1, "importo": 1, "data": 1, "source": 1,
         "status": 1, "entity_status": 1, "tipo": 1},
    ).to_list(None)
    per_fattura: Dict[str, List[Dict[str, Any]]] = {}
    for r in righe:
        if str(r.get("status") or "").lower() in _STATI_RIGA_ANNULLATA:
            continue
        if str(r.get("entity_status") or "").lower() == "deleted":
            continue
        if r.get("source") in SOURCES_ESCLUSE:
            continue
        per_fattura.setdefault(str(r["fattura_id"]), []).append(r)
    candidati = {fid for fid, lista in per_fattura.items() if len(lista) >= 2}
    fatture = await _fatture_per_id(db, candidati)
    trovati = []
    for fid in sorted(candidati):
        fattura = fatture.get(fid)
        totale = _numero((fattura or {}).get("total_amount"))
        if not totale:
            continue
        intere = [r for r in per_fattura[fid]
                  if abs(abs(_numero(r.get("importo")) or 0) - abs(totale)) < 0.005]
        if len(intere) >= 2:
            trovati.append({"fattura_id": fid, "fornitore": fattura.get("supplier_name"),
                            "numero": fattura.get("invoice_number"), "totale": totale,
                            "righe": [{"id": r.get("id"), "data": _giorno(r.get("data")),
                                       "source": r.get("source")} for r in intere]})
    return trovati


async def controlla_importi_anomali(db, *, oggi: Optional[date] = None) -> List[Dict[str, Any]]:
    from app.document_repository import metadata_projection
    from app.services.fattura_attiva import FILTRO_FATTURA_ATTIVA, e_nota_credito

    riferimento = oggi or _oggi()
    soglia_data = (riferimento - timedelta(days=GIORNI_IMPORTO_ANOMALO)).isoformat()
    fatture = await db["invoices"].find(FILTRO_FATTURA_ATTIVA, metadata_projection("invoices")).to_list(None)
    per_fornitore: Dict[str, List[Dict[str, Any]]] = {}
    for f in fatture:
        piva = str(f.get("supplier_vat") or "").strip().upper()
        totale = _numero(f.get("total_amount"))
        if not piva or not totale or totale <= 0 or e_nota_credito(f):
            continue
        per_fornitore.setdefault(piva, []).append(f)
    trovati = []
    for lista in per_fornitore.values():
        for f in lista:
            if _giorno(f.get("invoice_date")) < soglia_data:
                continue
            altri = [_numero(x.get("total_amount")) for x in lista if x.get("id") != f.get("id")]
            if len(altri) < CONFRONTI_MINIMI:
                continue
            mediana = statistics.median(altri)
            totale = _numero(f.get("total_amount"))
            if mediana > 0 and totale > MOLTIPLICATORE_ANOMALO * mediana:
                trovati.append({"fattura_id": f.get("id"), "fornitore": f.get("supplier_name"),
                                "numero": f.get("invoice_number"),
                                "data": _giorno(f.get("invoice_date")),
                                "totale": round(totale, 2), "mediana": round(mediana, 2),
                                "confronti": len(altri)})
    return trovati


# --- 2. Copertura degli estratti --------------------------------------------

def _mesi(da: str, a: str) -> List[str]:
    """Mesi ``YYYY-MM`` da ``da`` ad ``a`` compresi."""
    anno, mese = int(da[:4]), int(da[5:7])
    fine = (int(a[:4]), int(a[5:7]))
    out = []
    while (anno, mese) <= fine:
        out.append(f"{anno}-{mese:02d}")
        anno, mese = (anno + 1, 1) if mese == 12 else (anno, mese + 1)
    return out


async def copertura_estratti(db, *, anno: Optional[int] = None,
                             oggi: Optional[date] = None) -> List[Dict[str, Any]]:
    riferimento = oggi or _oggi()
    anno = anno or riferimento.year
    primo_del_mese = riferimento.replace(day=1)
    ultimo_mese = (primo_del_mese - timedelta(days=1)).strftime("%Y-%m")
    righe = []
    for fonte in FONTI_ESTRATTO:
        try:
            documenti = await db[fonte["collection"]].find(
                {}, {"_id": 0, fonte["campo"]: 1}).to_list(None)
        except Exception as exc:  # noqa: BLE001 - una fonte illeggibile non ferma le altre
            logger.warning("Copertura estratti: %s non leggibile (%s: %s)",
                           fonte["collection"], type(exc).__name__, exc)
            righe.append({**_testata(fonte), "leggibile": False, "mesi_presenti": [],
                          "mesi_mancanti": [], "dal": None})
            continue
        mesi_visti = {g[:7] for g in (_giorno(d.get(fonte["campo"])) for d in documenti) if g}
        primo = min(mesi_visti) if mesi_visti else None
        inizio = max(f"{anno}-01", primo) if primo else None
        fine = min(f"{anno}-12", ultimo_mese)
        attesi = _mesi(inizio, fine) if inizio and inizio <= fine else []
        righe.append({
            **_testata(fonte), "leggibile": True, "dal": primo,
            "mesi_presenti": sorted(m for m in mesi_visti if m.startswith(str(anno))),
            "mesi_mancanti": [m for m in attesi if m not in mesi_visti],
        })
    return righe


def _testata(fonte: Dict[str, Any]) -> Dict[str, Any]:
    return {"fonte": fonte["chiave"], "etichetta": fonte["etichetta"],
            "avvisa": fonte["avvisa"]}


# --- 3. RT dimenticata ------------------------------------------------------

async def controlla_rt_dimenticata(db, *, oggi: Optional[date] = None,
                                   giorni: int = 60) -> List[Dict[str, Any]]:
    from app.routers.pos_corrispettivi_check import (
        _aggrega_corrispettivi_per_giorno, _carica_pos_per_circuito, _giornate_senza_xml,
    )
    from app.services.chiusure_attivita import giorni_chiusi

    riferimento = oggi or _oggi()
    da = (riferimento - timedelta(days=giorni)).isoformat()
    a = (riferimento - timedelta(days=GIORNI_ATTESA_RT)).isoformat()
    corrispettivi = await db["corrispettivi"].find(
        {"data": {"$gte": da}, "entity_status": {"$ne": "deleted"},
         "status": {"$nin": ["deleted", "archived", "archiviata"]}},
        {"_id": 0, "data": 1, "pagato_elettronico": 1, "pagato_pos": 1, "stato": 1,
         "totale_xml": 1, "totale": 1, "totale_manuale": 1, "source": 1,
         "data_import_xml": 1, "content_hash": 1, "filename": 1},
    ).to_list(None)
    corr_by_date = _aggrega_corrispettivi_per_giorno(corrispettivi)
    if not corr_by_date:
        return []
    ultimo_corrispettivo = max(corr_by_date)
    pos = await _carica_pos_per_circuito(db)
    pos_giorno = {g: round(sum(v.values()), 2) for g, v in pos.items() if da <= g}
    giorni_ordinati = sorted(set(corr_by_date) | set(pos_giorno))
    chiusa_con, _ = _giornate_senza_xml(giorni_ordinati, corr_by_date, pos_giorno)
    chiusi = await giorni_chiusi(db, da, a)
    trovati = []
    for giorno in giorni_ordinati:
        if giorno > a or giorno >= ultimo_corrispettivo:
            continue
        if giorno in corr_by_date or giorno in chiusa_con or giorno in chiusi:
            continue
        if float(pos_giorno.get(giorno) or 0) <= 0:
            continue
        trovati.append({"data": giorno, "pos": pos_giorno[giorno],
                        "per_circuito": pos.get(giorno) or {}})
    return trovati


# --- Giro --------------------------------------------------------------------

async def esegui_controlli(db, *, oggi: Optional[date] = None) -> Dict[str, Any]:
    riferimento = oggi or _oggi()
    esito: Dict[str, Any] = {"nuovi_alert": 0}

    def _it(giorno: str) -> str:
        return f"{giorno[8:10]}/{giorno[5:7]}/{giorno[:4]}" if giorno else "—"

    beneficiari = await controlla_beneficiari(db)
    for r in beneficiari:
        esito["nuovi_alert"] += await _segnala(
            db, "BNK_BENEFICIARIO_DIVERSO", f"{r['movimento_id']}:{r['fattura_id']}",
            "estratto_conto_movimenti",
            f"Il bonifico del {_it(r['data'])} va a «{r['beneficiario']}», ma e' collegato "
            f"alla fattura {r['numero']} di {r['fornitore']}.", r,
        )
    doppie = await controlla_pagate_due_volte(db)
    for r in doppie:
        esito["nuovi_alert"] += await _segnala(
            db, "FAT_PAGATA_DUE_VOLTE", r["fattura_id"], "invoices",
            f"La fattura {r['numero']} di {r['fornitore']} ({r['totale']:.2f} EUR) ha "
            f"{len(r['righe'])} uscite in Prima Nota Banca, ognuna per l'importo intero.", r,
        )
    anomali = await controlla_importi_anomali(db, oggi=riferimento)
    for r in anomali:
        esito["nuovi_alert"] += await _segnala(
            db, "FAT_IMPORTO_ANOMALO", str(r["fattura_id"]), "invoices",
            f"La fattura {r['numero']} di {r['fornitore']} del {_it(r['data'])} vale "
            f"{r['totale']:.2f} EUR: piu' di {MOLTIPLICATORE_ANOMALO} volte la mediana del "
            f"fornitore ({r['mediana']:.2f} EUR su {r['confronti']} fatture).", r,
        )
    copertura = await copertura_estratti(db, oggi=riferimento)
    for fonte in copertura:
        if not fonte["avvisa"]:
            continue
        for mese in fonte["mesi_mancanti"]:
            esito["nuovi_alert"] += await _segnala(
                db, "ESTRATTO_MESE_MANCANTE", f"{fonte['fonte']}:{mese}", "estratti_conto_originali",
                f"{fonte['etichetta']}: nessun movimento di {mese[5:7]}/{mese[:4]}. "
                "Manca l'estratto del mese: finche' non si carica, quel mese non si riconcilia.",
                {"fonte": fonte["fonte"], "mese": mese}, telegram=True,
            )
    dimenticate = await controlla_rt_dimenticata(db, oggi=riferimento)
    for r in dimenticate:
        esito["nuovi_alert"] += await _segnala(
            db, "RT_GIORNO_SENZA_CHIUSURA", r["data"], "corrispettivi",
            f"Il {_it(r['data'])} il POS ha incassato {r['pos']:.2f} EUR ma non c'e' la "
            "chiusura RT, e la chiusura del giorno dopo non lo copre: registratore "
            "dimenticato o XML da recuperare.", r,
        )
    esito["alert_chiusi"] = 0
    illeggibili = tuple(f"{f['fonte']}:" for f in copertura if not f["leggibile"])
    inizio_finestra_rt = (riferimento - timedelta(days=60)).isoformat()
    for codice, attuali, tieni in (
        ("BNK_BENEFICIARIO_DIVERSO",
         {f"{r['movimento_id']}:{r['fattura_id']}" for r in beneficiari}, None),
        ("FAT_PAGATA_DUE_VOLTE", {r["fattura_id"] for r in doppie}, None),
        ("ESTRATTO_MESE_MANCANTE",
         {f"{f['fonte']}:{m}" for f in copertura for m in f["mesi_mancanti"]},
         # Un mese di un anno che questo giro non guarda resta com'e'.
         lambda e: e.startswith(illeggibili) or e.split(":", 1)[-1][:4] != str(riferimento.year)),
        ("RT_GIORNO_SENZA_CHIUSURA", {r["data"] for r in dimenticate},
         lambda e: e < inizio_finestra_rt),
    ):
        esito["alert_chiusi"] += await _chiudi_superati(db, codice, attuali, tieni)
    esito.update({"beneficiari_diversi": len(beneficiari), "pagate_due_volte": len(doppie),
                  "importi_anomali": len(anomali), "rt_dimenticate": len(dimenticate),
                  "mesi_mancanti": {f["fonte"]: f["mesi_mancanti"] for f in copertura}})
    return esito
