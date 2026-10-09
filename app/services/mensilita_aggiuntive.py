"""13ª e 14ª per dipendente: ratei maturati, busta, pagato e spostamenti.

Nessun motore nuovo: i numeri vengono da ``posizione_dipendente.componi_movimenti``
(dare = busta, avere = bonifici e acconti con competenza ``(anno, 13|14)``) e i
ratei da ``dati_chiave`` delle buste mensili, letti dal PDF dal lettore unico.
Uno spostamento **modifica lo stesso record** (stessa chiave, stesso id) e ne
annota il prima: un pagamento non si duplica mai, e «riporta» lo rimette dov'era.

Il bonifico vero (``pagamenti_esiti``) si sposta col motore che c'e' gia'
(``PUT /paghe/pagamento-esito/{key}``, mese 1-14): qui si elencano solo i
candidati e si spostano gli acconti (``acconti_dipendenti`` e quelli scritti
nella riga paga), che quel motore non copre.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.services import posizione_dipendente as pos

logger = logging.getLogger(__name__)

MENSILITA = {"13": ("tredicesima", "Tredicesima"), "14": ("quattordicesima", "Quattordicesima")}
TIPI_ORDINARI = ("ordinario", "mensile", "", None)
ZERO = Decimal("0")
CAMPI_CEDOLINO = {"_id": 0, "pdf_data": 0}


class ErroreMensilita(ValueError):
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}

    def come_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mese_mensilita(valore: Any) -> int:
    if str(valore) not in MENSILITA:
        raise ErroreMensilita("MENSILITA_NON_VALIDA", "La mensilità è 13 (tredicesima) o 14 (quattordicesima)",
                              {"mensilita": valore})
    return int(str(valore))


# ── ratei maturati ───────────────────────────────────────────────────────────

def ratei_maturati(cedolini: List[Dict[str, Any]], anno: int) -> Dict[str, Dict[str, Any]]:
    """Somma dei ratei letti dalle buste mensili.

    13ª: gennaio-dicembre dell'anno; 14ª: luglio dell'anno prima - giugno
    dell'anno (CCNL: 13ª a dicembre, 14ª a luglio). Una busta senza rateo
    letto non vale zero: si conta a parte, cosi' il buco si vede.
    """
    out = {"13": {"totale": ZERO, "buste_con_rateo": 0, "buste_mensili": 0},
           "14": {"totale": ZERO, "buste_con_rateo": 0, "buste_mensili": 0}}
    viste = set()
    from app.services.cedolini_versioni import attiva
    for c in cedolini:
        if not attiva(c) or c.get("varianti_da_decidere"):
            continue
        if str(c.get("tipo_cedolino") or "").strip().lower() not in TIPI_ORDINARI:
            continue
        a, m = pos._intero(c.get("anno")), pos._intero(c.get("mese"))
        if not a or not m or not 1 <= m <= 12 or (a, m) in viste:
            continue
        finestre = []
        if a == anno:
            finestre.append("13")
        if (a, m) >= (anno - 1, 7) and (a, m) <= (anno, 6):
            finestre.append("14")
        if not finestre:
            continue
        viste.add((a, m))
        chiave = c.get("dati_chiave") or {}
        for f in finestre:
            out[f]["buste_mensili"] += 1
            valore = pos.importo(chiave.get(f"rateo_{f}ma_importo"))
            if valore is not None:
                out[f]["totale"] += valore
                out[f]["buste_con_rateo"] += 1
    return out


def componenti_documentate(cedolini, anno=None, tipi=None):
    """Voci lorde già comprese nei cedolini; non sono altri debiti/pagamenti."""
    from app.services.cedolini_versioni import attiva

    out = []
    viste = set()
    for c in cedolini:
        if not attiva(c) or c.get("varianti_da_decidere") or (anno and pos._intero(c.get("anno")) != anno):
            continue
        if tipi and set(tipi) <= {"13", "14"} and str(c.get("tipo_cedolino") or "").strip().lower() not in TIPI_ORDINARI:
            continue  # le mensilità autonome hanno già la loro busta netta
        for voce in (c.get("dati_chiave") or {}).get("componenti_busta") or []:
            if tipi and voce.get("tipo") not in tipi:
                continue
            imp = pos.importo(voce.get("importo"))
            if imp is None:
                continue
            key = (c.get("anno"), c.get("mese"), c.get("tipo_cedolino"), voce.get("tipo"),
                   voce.get("pagina"), tuple(voce.get("bbox") or []), imp)
            if key in viste:
                continue
            viste.add(key)
            out.append({**voce, "cedolino_id": c.get("id"), "anno": c.get("anno"),
                        "mese": c.get("mese"), "importo": pos._eur(imp)})
    return sorted(out, key=lambda v: (pos._intero(v.get("anno")) or 0, pos._intero(v.get("mese")) or 0), reverse=True)


# ── riepilogo ────────────────────────────────────────────────────────────────

def _blocco(mov: List[Dict[str, Any]], ratei: Dict[str, Any], anno: int, mese: int) -> Dict[str, Any]:
    dell_anno = [m for m in mov if m["competenza"] == (anno, mese)]
    busta = sum((m["dare"] or ZERO for m in dell_anno), ZERO)
    pagato = sum((m["avere"] or ZERO for m in dell_anno), ZERO)
    return {
        "rateo_maturato": pos._eur(ratei["totale"]),
        "buste_con_rateo": ratei["buste_con_rateo"], "buste_mensili": ratei["buste_mensili"],
        "busta": pos._eur(busta), "pagato": pos._eur(pagato), "saldo": pos._eur(busta - pagato),
        "busta_presente": any(m["tipo"] == "busta" for m in dell_anno),
        "movimenti": [pos._riga_json(m) for m in dell_anno],
    }


async def riepilogo(db, anno: int) -> Dict[str, Any]:
    """Una lettura per collezione (senza PDF), poi il calcolo per dipendente."""
    dipendenti = await db.dipendenti.find({}, {"_id": 0, "id": 1, "nome_completo": 1, "stato": 1}).to_list(2000)
    per_dip: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    async def _carica(collezione: str, campi: Dict[str, Any], chiave: str, limite: int) -> None:
        for r in await db[collezione].find({}, campi).to_list(limite):
            if r.get("dipendente_id"):
                per_dip.setdefault(str(r["dipendente_id"]), {}).setdefault(chiave, []).append(r)

    await _carica("paghe_mensili", {"_id": 0}, "paghe", 50000)
    await _carica("pagamenti_esiti", CAMPI_CEDOLINO, "esiti", 50000)
    await _carica("cedolini", CAMPI_CEDOLINO, "cedolini", 50000)
    await _carica("acconti_dipendenti", {"_id": 0}, "acconti", 20000)

    anni = set()
    righe: List[Dict[str, Any]] = []
    for dip in sorted(dipendenti, key=lambda d: str(d.get("nome_completo") or "")):
        dati = per_dip.get(str(dip.get("id")), {})
        if not dati:
            continue
        for c in dati.get("cedolini", []):
            a = pos._intero(c.get("anno"))
            if a:
                anni.add(a)
        mov = pos.componi_movimenti(paghe=dati.get("paghe", []), esiti=dati.get("esiti", []),
                                    cedolini=dati.get("cedolini", []), acconti=dati.get("acconti", []),
                                    conciliazioni=[])["registro"]
        ratei = ratei_maturati(dati.get("cedolini", []), anno)
        tredicesima = _blocco(mov, ratei["13"], anno, 13)
        quattordicesima = _blocco(mov, ratei["14"], anno, 14)
        for tipo, blocco in (("13", tredicesima), ("14", quattordicesima)):
            voci = componenti_documentate(dati.get("cedolini", []), anno, {tipo})
            blocco["componenti_ordinarie"] = voci
            blocco["componenti_lorde"] = round(sum(v["importo"] for v in voci), 2) if voci else None
        if not any((tredicesima["busta"], tredicesima["pagato"], tredicesima["rateo_maturato"],
                    quattordicesima["busta"], quattordicesima["pagato"], quattordicesima["rateo_maturato"],
                    tredicesima["componenti_lorde"] is not None, quattordicesima["componenti_lorde"] is not None)):
            continue
        righe.append({"dipendente_id": dip["id"], "nome": dip.get("nome_completo"),
                      "stato": dip.get("stato"), "tredicesima": tredicesima,
                      "quattordicesima": quattordicesima})
    totali = {}
    for chiave in ("tredicesima", "quattordicesima"):
        totali[chiave] = {campo: round(sum(r[chiave][campo] or 0 for r in righe), 2)
                          for campo in ("rateo_maturato", "busta", "pagato", "saldo", "componenti_lorde")}
        if not any(r[chiave]["componenti_lorde"] is not None for r in righe):
            totali[chiave]["componenti_lorde"] = None
    return {"anno": anno, "anni": sorted(anni | {anno}), "valuta": pos.VALUTA, "righe": righe, "totali": totali}


# ── candidati alla tendina ───────────────────────────────────────────────────

def _etichetta(anno: int, mese: int) -> str:
    return pos._nome_periodo(anno, mese)


def _collocazione_acconto(acc: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    comp = str(acc.get("scalato_su_anno_mese") or "")
    a, m = pos._intero(comp[:4]), pos._intero(comp[5:7])
    return (a, m) if a and m else None


async def candidati(db, dipendente_id: str, anno: int) -> List[Dict[str, Any]]:
    """Bonifici e acconti del dipendente spostabili su 13ª/14ª, dal piu' recente."""
    vicino = lambda d: bool(d) and str(anno - 1) <= str(d)[:4] <= str(anno + 1)  # noqa: E731
    out: List[Dict[str, Any]] = []

    async for e in db.pagamenti_esiti.find({"dipendente_id": dipendente_id}, CAMPI_CEDOLINO):
        imp, a, m = pos.importo(e.get("importo")), pos._intero(e.get("anno")), pos._intero(e.get("mese"))
        if imp is None or not a or not m or not vicino(e.get("data") or f"{a}"):
            continue
        out.append({"sorgente": "esito", "id": e.get("key"), "data": pos._data_iso(e.get("data")),
                    "importo": pos._eur(imp), "descrizione": "Bonifico" + (f" — {str(e.get('causale'))[:60]}" if e.get("causale") else ""),
                    "anno": a, "mese": m, "collocazione": _etichetta(a, m), "sulla_mensilita": m in (13, 14)})

    async for acc in db.acconti_dipendenti.find({"dipendente_id": dipendente_id}, {"_id": 0}):
        if str(acc.get("tipo") or "") not in pos.TIPI_ACCONTO_STIPENDIO or acc.get("stato") == "annullato":
            continue
        imp, dove = pos.importo(acc.get("importo")), _collocazione_acconto(acc)
        if imp is None or not dove or not vicino(acc.get("data")):
            continue
        mezzo = "bonifico" if acc.get("source") == "bonifici_da_associare" else str(acc.get("tipo_bonifico") or "")
        out.append({"sorgente": "acconto", "id": acc.get("id"), "data": pos._data_iso(acc.get("data")),
                    "importo": pos._eur(imp), "descrizione": "Acconto" + (f" ({mezzo})" if mezzo else ""),
                    "anno": dove[0], "mese": dove[1], "collocazione": _etichetta(*dove),
                    "sulla_mensilita": dove[1] in (13, 14)})

    async for paga in db.paghe_mensili.find({"dipendente_id": dipendente_id}, {"_id": 0}):
        a, m = pos._intero(paga.get("anno")), pos._intero(paga.get("mese"))
        for i, acc in enumerate(paga.get("acconti") or []):
            imp = pos.importo(acc.get("importo"))
            if imp is None or imp <= 0 or not a or not m or not vicino(acc.get("data") or f"{a}"):
                continue
            out.append({"sorgente": "paga", "id": f"{a}:{m}:{i}", "data": pos._data_iso(acc.get("data")),
                        "importo": pos._eur(imp), "descrizione": "Acconto in contanti", "anno": a, "mese": m,
                        "collocazione": _etichetta(a, m), "sulla_mensilita": m in (13, 14)})
    return sorted(out, key=lambda r: (r["data"] or "", r["importo"] or 0), reverse=True)


# ── spostamento degli acconti (lo stesso record, mai una copia) ──────────────

async def _ricalcola(db, dipendente_id: str, periodi: List[Tuple[int, int]]) -> None:
    from app.hr.routers.dipendenti_cloud import _ricalcola_stato_paga

    for a, m in dict.fromkeys(periodi):
        await _ricalcola_stato_paga(db, dipendente_id, a, m)


async def sposta_acconto(db, dipendente_id: str, acconto_id: str, mensilita: str, anno: int) -> Dict[str, Any]:
    """Un acconto del registro diventa 13ª o 14ª: cambiano tipo e competenza."""
    mese = _mese_mensilita(mensilita)
    acc = await db.acconti_dipendenti.find_one({"id": acconto_id}, {"_id": 0})
    if not acc or str(acc.get("dipendente_id")) != str(dipendente_id):
        raise ErroreMensilita("ACCONTO_NON_TROVATO", "Acconto non trovato per questo dipendente")
    if acc.get("stato") == "annullato":
        raise ErroreMensilita("ACCONTO_ANNULLATO", "Un acconto annullato non si sposta")
    tipo, _ = MENSILITA[str(mese)]
    nuova = f"{anno}-{mese:02d}"
    if acc.get("tipo") == tipo and acc.get("scalato_su_anno_mese") == nuova:
        return {"ok": True, "gia_assegnato": True, "id": acconto_id}
    storia = list(acc.get("modifiche_manuali") or [])
    storia.append({"da_tipo": acc.get("tipo"), "da_scalato_su_anno_mese": acc.get("scalato_su_anno_mese"),
                   "a_tipo": tipo, "a_scalato_su_anno_mese": nuova, "at": _adesso()})
    await db.acconti_dipendenti.update_one({"id": acconto_id}, {"$set": {
        "tipo": tipo, "scalato_su_anno_mese": nuova, "modificato_manualmente": True,
        "modifiche_manuali": storia[-20:], "updated_at": _adesso()}})
    return {"ok": True, "gia_assegnato": False, "id": acconto_id, "mensilita": mensilita, "anno": anno}


async def riporta_acconto(db, dipendente_id: str, acconto_id: str) -> Dict[str, Any]:
    acc = await db.acconti_dipendenti.find_one({"id": acconto_id}, {"_id": 0})
    if not acc or str(acc.get("dipendente_id")) != str(dipendente_id):
        raise ErroreMensilita("ACCONTO_NON_TROVATO", "Acconto non trovato per questo dipendente")
    storia = list(acc.get("modifiche_manuali") or [])
    if not storia:
        raise ErroreMensilita("NIENTE_DA_RIPORTARE", "L'acconto non è mai stato spostato")
    prima = storia[-1]
    storia.append({"da_tipo": acc.get("tipo"), "da_scalato_su_anno_mese": acc.get("scalato_su_anno_mese"),
                   "a_tipo": prima.get("da_tipo"), "a_scalato_su_anno_mese": prima.get("da_scalato_su_anno_mese"),
                   "at": _adesso(), "nota": "riportato dov'era"})
    await db.acconti_dipendenti.update_one({"id": acconto_id}, {"$set": {
        "tipo": prima.get("da_tipo"), "scalato_su_anno_mese": prima.get("da_scalato_su_anno_mese"),
        "modifiche_manuali": storia[-20:], "updated_at": _adesso()}})
    return {"ok": True, "id": acconto_id}


def _indice_paga(identificativo: str) -> Tuple[int, int, int]:
    try:
        a, m, i = (int(x) for x in str(identificativo).split(":"))
        return a, m, i
    except ValueError as exc:
        raise ErroreMensilita("ACCONTO_NON_VALIDO", "Identificativo dell'acconto non valido",
                              {"id": identificativo}) from exc


async def sposta_acconto_paga(db, dipendente_id: str, identificativo: str, mensilita: str, anno: int,
                              *, data: Optional[str], importo: Any) -> Dict[str, Any]:
    """Un acconto in contanti scritto nella riga paga passa alla riga della 13ª/14ª.

    La voce esce da una riga ed entra nell'altra nello stesso passaggio; ``data``
    e ``importo`` inviati devono coincidere, cosi' un indice cambiato nel
    frattempo non sposta l'acconto sbagliato.
    """
    mese = _mese_mensilita(mensilita)
    a0, m0, i0 = _indice_paga(identificativo)
    if (a0, m0) == (anno, mese):
        return {"ok": True, "gia_assegnato": True}
    sorgente = await db.paghe_mensili.find_one({"dipendente_id": dipendente_id, "anno": a0, "mese": m0}, {"_id": 0})
    lista = list((sorgente or {}).get("acconti") or [])
    if not sorgente or i0 >= len(lista):
        raise ErroreMensilita("ACCONTO_NON_TROVATO", "Acconto non trovato nella riga paga")
    voce = lista[i0]
    if pos.importo(voce.get("importo")) != pos.importo(importo) or \
            (pos._data_iso(voce.get("data")) or None) != (pos._data_iso(data) or None):
        raise ErroreMensilita("ACCONTO_CAMBIATO", "L'acconto è cambiato: ricarica l'elenco")
    del lista[i0]
    nuova = {**voce, "spostato_da": {"anno": a0, "mese": m0}, "spostato_il": _adesso()}
    destinazione = await db.paghe_mensili.find_one(
        {"dipendente_id": dipendente_id, "anno": anno, "mese": mese}, {"_id": 0}) or {}
    voci = list(destinazione.get("acconti") or []) + [nuova]
    await db.paghe_mensili.update_one(
        {"dipendente_id": dipendente_id, "anno": anno, "mese": mese},
        {"$set": {"dipendente_id": dipendente_id, "anno": anno, "mese": mese, "acconti": voci,
                  "updated_at": _adesso()}}, upsert=True)
    await db.paghe_mensili.update_one(
        {"dipendente_id": dipendente_id, "anno": a0, "mese": m0},
        {"$set": {"acconti": lista, "updated_at": _adesso()}})
    await _ricalcola(db, dipendente_id, [(a0, m0), (anno, mese)])
    return {"ok": True, "gia_assegnato": False, "id": f"{anno}:{mese}:{len(voci) - 1}"}


async def riporta_acconto_paga(db, dipendente_id: str, identificativo: str) -> Dict[str, Any]:
    a0, m0, i0 = _indice_paga(identificativo)
    paga = await db.paghe_mensili.find_one({"dipendente_id": dipendente_id, "anno": a0, "mese": m0}, {"_id": 0})
    lista = list((paga or {}).get("acconti") or [])
    if not paga or i0 >= len(lista) or not lista[i0].get("spostato_da"):
        raise ErroreMensilita("NIENTE_DA_RIPORTARE", "L'acconto non è stato spostato da un altro mese")
    return await _riporta_a_mese(db, dipendente_id, a0, m0, i0, lista[i0]['spostato_da'])


async def _riporta_a_mese(db, dipendente_id: str, a0: int, m0: int, i0: int,
                          origine: Dict[str, Any]) -> Dict[str, Any]:
    """Rimette la voce nella riga da cui era partita (un mese ordinario)."""
    paga = await db.paghe_mensili.find_one({"dipendente_id": dipendente_id, "anno": a0, "mese": m0}, {"_id": 0})
    lista = list(paga.get("acconti") or [])
    voce = dict(lista.pop(i0))
    voce.pop("spostato_da", None)
    voce.pop("spostato_il", None)
    a1, m1 = int(origine["anno"]), int(origine["mese"])
    dest = await db.paghe_mensili.find_one({"dipendente_id": dipendente_id, "anno": a1, "mese": m1}, {"_id": 0}) or {}
    voci = list(dest.get("acconti") or []) + [voce]
    await db.paghe_mensili.update_one(
        {"dipendente_id": dipendente_id, "anno": a1, "mese": m1},
        {"$set": {"dipendente_id": dipendente_id, "anno": a1, "mese": m1, "acconti": voci,
                  "updated_at": _adesso()}}, upsert=True)
    await db.paghe_mensili.update_one(
        {"dipendente_id": dipendente_id, "anno": a0, "mese": m0},
        {"$set": {"acconti": lista, "updated_at": _adesso()}})
    await _ricalcola(db, dipendente_id, [(a0, m0), (a1, m1)])
    return {"ok": True, "id": f"{a1}:{m1}:{len(voci) - 1}"}
