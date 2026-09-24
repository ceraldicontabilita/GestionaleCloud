"""Posizione noleggio: l'estratto conto in partita doppia di ogni auto e di ogni driver.

Un solo motore risponde alla domanda «a che punto e' questa auto (o questo
driver)?»: per ogni targa mette in fila, nell'ordine del tempo, i **costi**
(fatture del noleggiatore per categoria, verbali arrivati dalla posta) in
DARE e le **prove di pagamento** in AVERE. Il saldo e' quello che resta da
pagare al noleggiatore o all'ente.

Le prove ammesse sono solo quelle strutturate che il gestionale gia' produce:

* per le fatture, un'allocazione bancaria confermata
  (`bank_payment_allocations`), una riga di Prima Nota Banca con estratto
  conto agganciato, oppure un movimento di estratto conto che cita la
  fattura. Una riga di Prima Nota **senza** estratto conto e' un pagamento
  dichiarato, non provato: si mostra a parte e non chiude il saldo;
* per i verbali, la quietanza (PartenoPay, Mooney, PayPal, PagoPA) o il
  movimento Banca BPM che `verbali_pagamento_finder` ha gia' agganciato al
  verbale con riferimento strutturato e importo al centesimo.

Questo modulo non associa niente: legge le relazioni esistenti e le espone.
Un movimento bancario verso un noleggiatore o verso il Comune di Napoli che
nessuna relazione spiega resta un **candidato** in una lista a parte, mai un
pagamento attribuito per importo o per data (regola «Identita', prove e
attese» di CLAUDE.md).

Il responsabile di ogni riga e' il driver **alla data** della riga
(`driver_alla_data`), non quello attuale: un canone di marzo e un verbale di
marzo pesano su chi aveva l'auto a marzo.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.constants.stati_verbale import e_pagato
from app.services.noleggio.constants import FORNITORI_NOLEGGIO
from app.services.noleggio.controlli import STATI_CONTRATTO_CHIUSI, driver_alla_data
from app.services.verbali_evidence import amount_to_cents, sanitize_verbale_evidence

logger = logging.getLogger(__name__)

__all__ = [
    "CATEGORIE_COSTO",
    "costruisci_posizione_noleggio",
    "etichetta_fonte_quietanza",
    "ripartisci_centesimi",
]

#: Le categorie di costo che il motore fatture (`scan_fatture_noleggio`)
#: produce per ogni targa. `verbali` e' l'ultima perche' ha anche una fonte
#: propria (la posta) e un trattamento a parte.
CATEGORIE_COSTO: Tuple[str, ...] = (
    "canoni", "bollo", "pedaggio", "riparazioni", "costi_extra", "verbali",
)

#: Chi puo' aver incassato un verbale, riconosciuto dal testo della prova.
#: L'ordine conta: «PartenoPay» passa da PagoPA e va nominato per primo.
_FONTI_QUIETANZA: Tuple[Tuple[str, str], ...] = (
    ("partenopay", "PartenoPay"),
    ("mooney", "Mooney"),
    ("paytipper", "Mooney"),
    ("paypal", "PayPal"),
    ("pagopa", "PagoPA"),
    ("gmail", "PagoPA"),
    ("estratto_conto", "Banca BPM"),
    ("bonifico", "Banca BPM"),
    ("bpm", "Banca BPM"),
    ("banca", "Banca BPM"),
)

#: Testi con cui i noleggiatori e il Comune compaiono nelle causali bancarie.
_CONTROPARTI_BANCA: Tuple[Tuple[str, str], ...] = (
    ("ALD AUTOMOTIVE", "ALD"),
    ("AYVENS", "ALD"),
    ("ARVAL", "ARVAL"),
    ("LEASYS", "Leasys"),
    ("LEASEPLAN", "LeasePlan"),
    ("COMUNE DI NAPOLI", "Comune di Napoli"),
)

_STATI_ALLOCAZIONE_VALIDI = frozenset({"confirmed", "confermata", "confermato"})


# ── denaro ────────────────────────────────────────────────────────────────

def _cents(value: Any) -> int:
    """Centesimi interi da qualunque rappresentazione; `None`/vuoto → 0."""
    cents = amount_to_cents(value)
    return int(cents) if cents is not None else 0


def _eur(cents: int) -> float:
    return float(Decimal(cents) / Decimal(100))


def ripartisci_centesimi(totale: int, pesi: List[int]) -> List[int]:
    """Divide `totale` centesimi in proporzione ai `pesi`, senza perdere un
    centesimo: il resto va alle quote con la frazione piu' grande (metodo dei
    resti maggiori). Pesi tutti nulli → tutto sulla prima quota."""
    if not pesi:
        return []
    somma = sum(abs(p) for p in pesi)
    if somma == 0:
        return [totale] + [0] * (len(pesi) - 1)
    grezzi = [Decimal(totale) * Decimal(abs(p)) / Decimal(somma) for p in pesi]
    quote = [int(g) if g >= 0 else -int(-g) for g in grezzi]
    resto = totale - sum(quote)
    segno = 1 if resto >= 0 else -1
    ordine = sorted(range(len(pesi)), key=lambda i: abs(grezzi[i] - quote[i]), reverse=True)
    for i in ordine[: abs(resto)]:
        quote[i] += segno
    return quote


def _norm_piva(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper()).removeprefix("IT")


def _norm_numero(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _data(value: Any) -> str:
    return str(value or "")[:10]


# ── fonti di pagamento dei verbali ───────────────────────────────────────

def etichetta_fonte_quietanza(verbale: Dict[str, Any]) -> Optional[str]:
    """Chi ha incassato il verbale, letto dalla prova agganciata al record.

    Restituisce `None` quando il verbale non porta nessuna prova: non si
    inventa un canale.
    """
    testo = " ".join(str(verbale.get(k) or "") for k in (
        "psp", "fonte_pagamento", "fonte_riconciliazione", "metodo_pagamento",
    )).lower()
    for chiave, etichetta in _FONTI_QUIETANZA:
        if chiave in testo:
            return etichetta
    if verbale.get("paypal_transaction_id"):
        return "PayPal"
    if verbale.get("ricevuta_pagopa_id"):
        return "PagoPA"
    if verbale.get("movimento_banca_id"):
        return "Banca BPM"
    psp = str(verbale.get("psp") or "").strip()
    return psp or None


def _prova_verbale(verbale: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """La prova di pagamento di un verbale, solo se il record ne porta una
    strutturata (id della ricevuta, della transazione o del movimento)."""
    ricevuta = verbale.get("ricevuta_pagopa_id")
    paypal = verbale.get("paypal_transaction_id")
    movimento = verbale.get("movimento_banca_id")
    if not (ricevuta or paypal or movimento or verbale.get("pagato_documentalmente") is True):
        return None
    return {
        "tipo": "quietanza",
        "fonte": etichetta_fonte_quietanza(verbale),
        "id": ricevuta or paypal or movimento or verbale.get("pagamento_id"),
        "data": _data(verbale.get("data_pagamento")),
        "banca_verificata": bool(movimento or verbale.get("banca_verificata") is True),
        "documentale": bool(ricevuta or paypal or verbale.get("pagato_documentalmente") is True),
        "movimento_id": movimento,
        "ricevuta_pagopa_id": ricevuta,
        "paypal_transaction_id": paypal,
    }


# ── prefetch ─────────────────────────────────────────────────────────────

async def _tutti(cursor, limite: int = 20000) -> List[Dict[str, Any]]:
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(limite)
    return [doc async for doc in cursor]


async def _fatture_noleggio_leggere(db, anno: Optional[int]) -> List[Dict[str, Any]]:
    """Identita' delle fatture attive dei noleggiatori, senza righe ne' XML."""
    from app.services.noleggio.processors import FILTRO_FATTURA_ATTIVA

    query: Dict[str, Any] = {
        "supplier_vat": {"$in": list(FORNITORI_NOLEGGIO.values())},
        **FILTRO_FATTURA_ATTIVA,
    }
    if anno is not None:
        query["invoice_date"] = {"$regex": f"^{anno}"}
    proiezione = {
        "_id": 1, "id": 1, "invoice_id": 1, "invoice_number": 1, "invoice_date": 1,
        "supplier_vat": 1, "supplier_name": 1, "total_amount": 1, "tipo_documento": 1,
    }
    return await _tutti(db["invoices"].find(query, proiezione))


def _mappa_alias_fatture(fatture: Iterable[Dict[str, Any]]) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, Dict[str, Any]]]:
    """Ogni identificativo con cui una fattura viene citata (`_id`, `id`,
    `invoice_id`) porta alla stessa chiave stabile `piva|numero`."""
    alias: Dict[str, str] = {}
    per_numero: Dict[str, str] = {}
    numeri_ambigui: set = set()
    info: Dict[str, Dict[str, Any]] = {}
    for f in fatture:
        chiave = f"{_norm_piva(f.get('supplier_vat'))}|{_norm_numero(f.get('invoice_number'))}"
        for campo in ("_id", "id", "invoice_id"):
            valore = f.get(campo)
            if valore:
                alias[str(valore)] = chiave
        numero = _norm_numero(f.get("invoice_number"))
        if numero:
            if numero in per_numero and per_numero[numero] != chiave:
                numeri_ambigui.add(numero)
            per_numero.setdefault(numero, chiave)
        info.setdefault(chiave, {
            "numero": f.get("invoice_number"),
            "data": _data(f.get("invoice_date")),
            "fornitore": f.get("supplier_name"),
            "supplier_vat": f.get("supplier_vat"),
            "id": str(f.get("id") or f.get("_id") or ""),
            "totale_cents": _cents(f.get("total_amount")),
        })
    for numero in numeri_ambigui:
        per_numero.pop(numero, None)
    return alias, per_numero, info


async def _prove_fatture(db, alias: Dict[str, str], per_numero: Dict[str, str]) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]], set]:
    """Le prove di pagamento delle fatture, raccolte dalle tre relazioni che
    il gestionale scrive quando riconcilia. Ritorna (prove per chiave
    fattura, pagamenti dichiarati senza estratto conto, id movimenti usati).
    """
    prove: Dict[str, List[Dict[str, Any]]] = {}
    dichiarati: List[Dict[str, Any]] = []
    viste: set = set()
    movimenti_usati: set = set()

    def _chiave(*candidati: Any) -> Optional[str]:
        for c in candidati:
            if c and str(c) in alias:
                return alias[str(c)]
        return None

    def _aggiungi(chiave: str, prova: Dict[str, Any]) -> None:
        firma = (prova.get("movimento_id") or prova.get("prima_nota_id") or prova.get("id"), chiave)
        if firma in viste:
            return
        viste.add(firma)
        prove.setdefault(chiave, []).append(prova)
        if prova.get("movimento_id"):
            movimenti_usati.add(str(prova["movimento_id"]))

    # 1) allocazioni bancarie confermate: la prova piu' precisa (quota in cents)
    allocazioni = await _tutti(db["bank_payment_allocations"].find({}, {
        "_id": 0, "allocation_id": 1, "fattura_id": 1, "fattura_numero": 1, "quota_cents": 1,
        "movimento_id": 1, "data_pagamento": 1, "metodo_pagamento": 1, "status": 1,
        "confirmed_by": 1,
    }))
    for a in allocazioni:
        if str(a.get("status") or "").lower() not in _STATI_ALLOCAZIONE_VALIDI:
            continue
        chiave = _chiave(a.get("fattura_id")) or per_numero.get(_norm_numero(a.get("fattura_numero")))
        if not chiave:
            continue
        _aggiungi(chiave, {
            "tipo": "movimento_banca", "fonte": "Banca BPM",
            "id": a.get("movimento_id") or a.get("allocation_id"),
            "movimento_id": a.get("movimento_id"), "prima_nota_id": None,
            "data": _data(a.get("data_pagamento")), "importo_cents": int(a.get("quota_cents") or 0),
            "metodo": a.get("metodo_pagamento"), "banca_verificata": True,
            "origine": "allocazione_banca", "conferma": a.get("confirmed_by"),
        })

    # 2) Prima Nota Banca con fattura: prova solo se c'e' l'estratto conto.
    # Si legge la proiezione intera (poche centinaia di righe) e si filtra
    # qui: un `$exists` su indice di array non e' garantito dal runtime.
    righe_pn = await _tutti(db["prima_nota_banca"].find({}, {
        "_id": 0, "id": 1, "data": 1, "importo": 1, "fattura_id": 1, "invoice_id": 1,
        "fattura_ids": 1, "estratto_conto_id": 1, "movimento_bancario_id": 1,
        "movimento_estratto_conto_id": 1, "pagato_con": 1, "metodo_pagamento": 1,
        "source": 1, "numero_fattura": 1, "allocazioni_fatture": 1, "descrizione": 1,
        "stornato": 1, "annullato": 1,
    }))
    for r in righe_pn:
        if r.get("stornato") or r.get("annullato"):
            continue
        if not (r.get("fattura_id") or r.get("invoice_id") or r.get("fattura_ids")):
            continue
        movimento = (r.get("estratto_conto_id") or r.get("movimento_bancario_id")
                     or r.get("movimento_estratto_conto_id"))
        allocazioni_riga = r.get("allocazioni_fatture") or []
        if allocazioni_riga:
            # gia' coperte dal punto 1 (stessa firma movimento+fattura)
            for a in allocazioni_riga:
                chiave = _chiave(a.get("fattura_id")) or per_numero.get(_norm_numero(a.get("fattura_numero")))
                if chiave and movimento:
                    _aggiungi(chiave, {
                        "tipo": "movimento_banca", "fonte": "Banca BPM", "id": movimento,
                        "movimento_id": movimento, "prima_nota_id": r.get("id"),
                        "data": _data(a.get("data_pagamento") or r.get("data")),
                        "importo_cents": int(a.get("quota_cents") or 0),
                        "metodo": a.get("metodo_pagamento") or r.get("pagato_con"),
                        "banca_verificata": True, "origine": "prima_nota_banca",
                    })
            continue
        ids = [x for x in (r.get("fattura_ids") or []) if x] or [r.get("fattura_id") or r.get("invoice_id")]
        ids = [x for x in ids if x]
        if len(ids) != 1:
            continue  # cumulativo senza allocazioni: ambiguo, non si spartisce a occhio
        chiave = _chiave(ids[0]) or per_numero.get(_norm_numero(r.get("numero_fattura")))
        if not chiave:
            continue
        prova = {
            "tipo": "movimento_banca" if movimento else "prima_nota",
            "fonte": "Banca BPM" if movimento else "Prima Nota (dichiarato)",
            "id": movimento or r.get("id"), "movimento_id": movimento,
            "prima_nota_id": r.get("id"), "data": _data(r.get("data")),
            "importo_cents": _cents(r.get("importo")),
            "metodo": r.get("pagato_con") or r.get("metodo_pagamento"),
            "banca_verificata": bool(movimento), "origine": r.get("source") or "prima_nota_banca",
            "descrizione": r.get("descrizione"),
        }
        if movimento:
            _aggiungi(chiave, prova)
        else:
            dichiarati.append({**prova, "chiave_fattura": chiave})

    # 3) movimenti di estratto conto che citano direttamente la fattura
    movimenti = await _tutti(db["estratto_conto_movimenti"].find(
        {"fattura_id": {"$nin": [None, ""]}},
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "fattura_id": 1, "descrizione": 1,
         "descrizione_originale": 1},
    ))
    for m in movimenti:
        chiave = _chiave(m.get("fattura_id"))
        if not chiave or not m.get("id"):
            continue
        _aggiungi(chiave, {
            "tipo": "movimento_banca", "fonte": "Banca BPM", "id": m.get("id"),
            "movimento_id": m.get("id"), "prima_nota_id": None, "data": _data(m.get("data")),
            "importo_cents": abs(_cents(m.get("importo"))), "metodo": None,
            "banca_verificata": True, "origine": "estratto_conto",
            "descrizione": m.get("descrizione_originale") or m.get("descrizione"),
        })
    return prove, dichiarati, movimenti_usati


async def _candidati_banca(db, anno: Optional[int], movimenti_usati: set) -> List[Dict[str, Any]]:
    """Uscite bancarie verso un noleggiatore o verso il Comune di Napoli che
    nessuna relazione spiega: candidati da lavorare, non pagamenti."""
    proiezione = {
        "_id": 0, "id": 1, "data": 1, "importo": 1, "descrizione": 1, "descrizione_originale": 1,
        "fattura_id": 1, "riconciliato": 1, "ricevuta_pagopa_id": 1, "verbale_id": 1,
        "numero_verbale_collegato": 1, "tipo": 1,
    }
    query: Dict[str, Any] = {}
    if anno is not None:
        query["data"] = {"$regex": f"^{anno}"}
    candidati: List[Dict[str, Any]] = []
    for m in await _tutti(db["estratto_conto_movimenti"].find(query, proiezione)):
        importo = _cents(m.get("importo"))
        if importo >= 0:
            continue
        testo = " ".join(str(m.get(k) or "") for k in ("descrizione_originale", "descrizione")).upper()
        controparte = next((nome for chiave, nome in _CONTROPARTI_BANCA if chiave in testo), None)
        if not controparte:
            continue
        if (str(m.get("id") or "") in movimenti_usati or m.get("fattura_id")
                or m.get("ricevuta_pagopa_id") or m.get("verbale_id") or m.get("numero_verbale_collegato")):
            continue
        candidati.append({
            "movimento_id": m.get("id"), "data": _data(m.get("data")), "importo": _eur(-importo),
            "descrizione": (m.get("descrizione_originale") or m.get("descrizione") or "").strip(),
            "controparte": controparte,
            "per": "verbale" if controparte == "Comune di Napoli" else "fattura",
            "riconciliato_altrove": bool(m.get("riconciliato")),
        })
    candidati.sort(key=lambda c: c["data"], reverse=True)
    return candidati


async def _verbali_posta(db) -> Dict[str, Dict[str, Any]]:
    """I verbali della posta (PEC/Gmail/ricevute), indicizzati per numero,
    senza i PDF: qui servono solo stato, prova e importo verificato."""
    proiezione = {
        "_id": 0, "pdf_data": 0, "pdf_allegati": 0, "quietanza_pdf": 0, "testo": 0,
        "testo_estratto": 0, "email_body": 0, "raw": 0,
    }
    per_numero: Dict[str, Dict[str, Any]] = {}
    for v in await _tutti(db["verbali_noleggio"].find({}, proiezione)):
        numero = v.get("numero_verbale") or v.get("numero_verbale_old")
        if numero:
            per_numero[str(numero)] = v
    return per_numero


async def _trattenute(db) -> Dict[str, List[Dict[str, Any]]]:
    per_verbale: Dict[str, List[Dict[str, Any]]] = {}
    for t in await _tutti(db["trattenute_dipendenti"].find({}, {
        "_id": 0, "id": 1, "numero_verbale": 1, "dipendente_id": 1, "dipendente_nome": 1,
        "importo": 1, "stato": 1, "mese": 1, "anno": 1,
    })):
        numero = str(t.get("numero_verbale") or "")
        if numero:
            per_verbale.setdefault(numero, []).append(t)
    return per_verbale


async def _nomi_dipendenti(db) -> Dict[str, str]:
    nomi: Dict[str, str] = {}
    for d in await _tutti(db["dipendenti"].find({}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1})):
        if d.get("id"):
            nomi[str(d["id"])] = f"{d.get('nome', '')} {d.get('cognome', '')}".strip()
    return nomi


# ── costruzione ──────────────────────────────────────────────────────────

def _stato_costo(dare: int, avere: int) -> str:
    if dare <= 0:
        return "storno"
    if avere >= dare:
        return "pagata"
    if avere > 0:
        return "parziale"
    return "aperta"


def _riepilogo_vuoto() -> Dict[str, Any]:
    return {
        "dare_cents": 0, "avere_cents": 0, "avere_non_verificato_cents": 0,
        "per_categoria": {c: {"dare_cents": 0, "avere_cents": 0} for c in CATEGORIE_COSTO},
    }


def _chiudi_riepilogo(r: Dict[str, Any]) -> Dict[str, Any]:
    out = {
        "dare": _eur(r["dare_cents"]), "avere": _eur(r["avere_cents"]),
        "saldo": _eur(r["dare_cents"] - r["avere_cents"]),
        "avere_non_verificato": _eur(r["avere_non_verificato_cents"]),
        "per_categoria": {},
    }
    for cat, v in r["per_categoria"].items():
        out["per_categoria"][cat] = {
            "dare": _eur(v["dare_cents"]), "avere": _eur(v["avere_cents"]),
            "saldo": _eur(v["dare_cents"] - v["avere_cents"]),
        }
    return out


def _righe_fatture_veicolo(
    veicolo: Dict[str, Any], alias: Dict[str, str], prove: Dict[str, List[Dict[str, Any]]],
    quote_targa: Dict[Tuple[str, str], int], totale_fattura: Dict[str, int],
    dichiarati_per_chiave: Dict[str, List[Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    """Righe DARE (costo) e AVERE (prova) delle fatture di una targa."""
    targa = veicolo.get("targa")
    righe: List[Dict[str, Any]] = []
    riepilogo = _riepilogo_vuoto()
    aperte: List[Dict[str, Any]] = []

    # i record di costo per fattura, su questa targa
    per_chiave: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
    for cat in CATEGORIE_COSTO:
        for rec in veicolo.get(cat) or []:
            if cat == "verbali" and not rec.get("fattura_id"):
                continue  # verbale della posta: trattato a parte
            chiave = alias.get(str(rec.get("fattura_id") or ""))
            if not chiave:
                chiave = f"?|{_norm_numero(rec.get('numero_fattura'))}"
            per_chiave.setdefault(chiave, []).append((cat, rec))

    for chiave, records in per_chiave.items():
        pesi = [_cents(rec.get("totale")) for _, rec in records]
        quota_targa_cents = sum(pesi)
        totale = totale_fattura.get(chiave) or quota_targa_cents or 1
        # la quota di ogni prova che spetta a questa targa, poi alle sue categorie
        prove_fattura = prove.get(chiave, [])
        avere_per_record = [0] * len(records)
        prove_righe: List[Tuple[Dict[str, Any], List[int]]] = []
        # una fattura che cita piu' targhe: la prova si spartisce prima fra le
        # targhe (con le loro quote di costo), poi fra le categorie della targa
        targhe = sorted({targa} | {k[0] for k in quote_targa if k[1] == chiave})
        for prova in prove_fattura:
            quota = ripartisci_centesimi(
                int(prova.get("importo_cents") or 0),
                [quote_targa.get((t, chiave), 0) for t in targhe],
            )
            quota_mia = quota[targhe.index(targa)]
            per_record = ripartisci_centesimi(quota_mia, pesi)
            prove_righe.append((prova, per_record))
            for i, q in enumerate(per_record):
                avere_per_record[i] += q
        for i, (cat, rec) in enumerate(records):
            dare = _cents(rec.get("totale"))
            documento = {
                "tipo": "fattura", "id": rec.get("fattura_id"), "numero": rec.get("numero_fattura"),
                "data": _data(rec.get("data")), "fornitore": rec.get("fornitore"),
            }
            if dare >= 0:
                riga = {
                    "data": _data(rec.get("data")), "tipo": "costo", "categoria": cat,
                    "descrizione": _descrizione_record(cat, rec), "dare": _eur(dare), "avere": 0.0,
                    "documento": documento, "prova": None,
                    "stato": _stato_costo(dare, avere_per_record[i]),
                    "pagato": _eur(avere_per_record[i]), "residuo": _eur(max(dare - avere_per_record[i], 0)),
                }
                riepilogo["dare_cents"] += dare
                riepilogo["per_categoria"][cat]["dare_cents"] += dare
            else:
                riga = {
                    "data": _data(rec.get("data")), "tipo": "storno", "categoria": cat,
                    "descrizione": _descrizione_record(cat, rec), "dare": 0.0, "avere": _eur(-dare),
                    "documento": documento, "prova": None, "stato": "storno",
                }
                riepilogo["avere_cents"] += -dare
                riepilogo["per_categoria"][cat]["avere_cents"] += -dare
            righe.append(riga)
            if riga["stato"] in ("aperta", "parziale"):
                aperte.append({**documento, "categoria": cat, "importo": riga["dare"],
                               "residuo": riga.get("residuo")})
            for prova, per_record in prove_righe:
                q = per_record[i]
                if q == 0:
                    continue
                righe.append({
                    "data": prova.get("data") or _data(rec.get("data")), "tipo": "pagamento",
                    "categoria": cat,
                    "descrizione": f"Pagamento {prova.get('metodo') or ''} fattura {rec.get('numero_fattura') or ''}".replace("  ", " ").strip(),
                    "dare": 0.0, "avere": _eur(q), "documento": documento,
                    "prova": {k: v for k, v in prova.items() if k != "importo_cents"},
                    "stato": "verificata" if prova.get("banca_verificata") else "dichiarata",
                })
                riepilogo["avere_cents"] += q
                riepilogo["per_categoria"][cat]["avere_cents"] += q
        for d in dichiarati_per_chiave.get(chiave, []):
            quota = ripartisci_centesimi(int(d.get("importo_cents") or 0), [quota_targa_cents, max(totale - quota_targa_cents, 0)])[0]
            riepilogo["avere_non_verificato_cents"] += quota
            righe.append({
                "data": d.get("data"), "tipo": "pagamento_dichiarato", "categoria": records[0][0],
                "descrizione": d.get("descrizione") or "Pagamento registrato in Prima Nota senza estratto conto",
                "dare": 0.0, "avere": 0.0, "avere_non_verificato": _eur(quota),
                "documento": {"tipo": "fattura", "id": records[0][1].get("fattura_id"),
                              "numero": records[0][1].get("numero_fattura"),
                              "data": _data(records[0][1].get("data"))},
                "prova": {k: v for k, v in d.items() if k not in ("importo_cents", "chiave_fattura")},
                "stato": "dichiarata",
            })
    return righe, riepilogo, aperte


def _descrizione_record(cat: str, rec: Dict[str, Any]) -> str:
    voci = rec.get("voci") or []
    if voci:
        testo = "; ".join(str(v.get("descrizione") or "") for v in voci[:3] if v.get("descrizione"))
        if len(voci) > 3:
            testo += f" (+{len(voci) - 3})"
        if testo:
            return testo
    if rec.get("descrizione"):
        return str(rec["descrizione"])
    return f"{cat} fattura {rec.get('numero_fattura') or ''}".strip()


def _righe_verbali_veicolo(
    veicolo: Dict[str, Any], posta: Dict[str, Dict[str, Any]],
    trattenute: Dict[str, List[Dict[str, Any]]], riepilogo: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Ogni verbale della targa con importo verificato, prova di pagamento
    (fonte quietanza), riaddebito in fattura, trattenuta al driver e driver
    competente alla data dell'infrazione."""
    righe: List[Dict[str, Any]] = []
    schede: List[Dict[str, Any]] = []
    visti: set = set()
    for rec in veicolo.get("verbali") or []:
        numero = str(rec.get("numero_verbale") or "")
        if not numero or numero in visti:
            continue
        visti.add(numero)
        record_posta = posta.get(numero)
        evidenza = sanitize_verbale_evidence(record_posta) if record_posta else None
        prova = _prova_verbale(record_posta) if record_posta else None
        data_verbale = _data(rec.get("data_verbale") or rec.get("data")
                             or (record_posta or {}).get("data_verbale") or (record_posta or {}).get("data_violazione"))
        driver = driver_alla_data(veicolo, data_verbale or _data(rec.get("data")))
        in_fattura = bool(rec.get("fattura_id"))
        importo_riaddebito = _cents(rec.get("totale")) if in_fattura else 0
        importo_verificato = (evidenza or {}).get("importo_centesimi")
        pagato_documentalmente = bool(record_posta and (e_pagato(record_posta.get("stato")) or prova))
        scheda = {
            "numero_verbale": numero, "data_verbale": data_verbale,
            "driver_competente": driver,
            "in_fattura": in_fattura,
            "fattura": {"id": rec.get("fattura_id"), "numero": rec.get("fattura_numero") or rec.get("numero_fattura")} if in_fattura else None,
            "importo_riaddebito": _eur(importo_riaddebito) if in_fattura else None,
            "importo_verificato": _eur(importo_verificato) if importo_verificato is not None else None,
            "importo_da_verificare": bool(evidenza and evidenza.get("importo_candidato_presente") and importo_verificato is None),
            "stato": (record_posta or {}).get("stato") or rec.get("stato"),
            "pagato": pagato_documentalmente or bool(rec.get("pagato")),
            "fonte_quietanza": prova.get("fonte") if prova else None,
            "prova": prova,
            "trattenute": trattenute.get(numero, []),
            "fonte": rec.get("fonte"),
        }
        schede.append(scheda)
        if in_fattura:
            continue  # il costo e la sua prova stanno gia' nelle righe fattura
        if importo_verificato is not None:
            righe.append({
                "data": data_verbale, "tipo": "costo", "categoria": "verbali",
                "descrizione": f"Verbale {numero}", "dare": _eur(importo_verificato), "avere": 0.0,
                "documento": {"tipo": "verbale", "id": (record_posta or {}).get("id") or numero, "numero": numero},
                "prova": None, "stato": "pagata" if prova else "aperta", "driver": driver,
            })
            riepilogo["dare_cents"] += importo_verificato
            riepilogo["per_categoria"]["verbali"]["dare_cents"] += importo_verificato
            if prova:
                righe.append({
                    "data": prova.get("data") or data_verbale, "tipo": "pagamento", "categoria": "verbali",
                    "descrizione": f"Quietanza {prova.get('fonte') or ''} verbale {numero}".replace("  ", " "),
                    "dare": 0.0, "avere": _eur(importo_verificato),
                    "documento": {"tipo": "verbale", "id": (record_posta or {}).get("id") or numero, "numero": numero},
                    "prova": prova, "stato": "verificata" if prova.get("banca_verificata") else "documentale",
                    "driver": driver,
                })
                riepilogo["avere_cents"] += importo_verificato
                riepilogo["per_categoria"]["verbali"]["avere_cents"] += importo_verificato
        else:
            righe.append({
                "data": data_verbale, "tipo": "costo", "categoria": "verbali",
                "descrizione": f"Verbale {numero} (importo da verificare)", "dare": None, "avere": 0.0,
                "documento": {"tipo": "verbale", "id": (record_posta or {}).get("id") or numero, "numero": numero},
                "prova": prova, "stato": "importo_da_verificare", "driver": driver,
            })
    schede.sort(key=lambda s: s.get("data_verbale") or "", reverse=True)
    return righe, schede


def _stub_veicolo(targa: str, record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "targa": targa, "marca": "", "modello": "", "fornitore_noleggio": record.get("fornitore"),
        "driver": None, "driver_id": None, "assegnazioni": [], "stato_contratto": None,
        **{c: [] for c in CATEGORIE_COSTO},
    }


async def costruisci_posizione_noleggio(db, anno: Optional[int] = None) -> Dict[str, Any]:
    """La posizione di ogni auto e di ogni driver per l'anno (o tutto)."""
    # Il motore fatture-per-targa e' `get_veicoli` del router noleggio (unione
    # di fatture, veicoli salvati, collegamenti manuali e verbali): lo si
    # riusa, non si riscrive. Import pigro per non legare il servizio al
    # router a tempo di import.
    from app.routers.noleggio import get_veicoli

    dati = await get_veicoli(anno=anno)
    veicoli_input: List[Dict[str, Any]] = dati.get("veicoli") or []

    fatture = await _fatture_noleggio_leggere(db, anno)
    alias, per_numero, info_fatture = _mappa_alias_fatture(fatture)
    prove, dichiarati, movimenti_usati = await _prove_fatture(db, alias, per_numero)
    dichiarati_per_chiave: Dict[str, List[Dict[str, Any]]] = {}
    for d in dichiarati:
        dichiarati_per_chiave.setdefault(d["chiave_fattura"], []).append(d)
    posta = await _verbali_posta(db)
    trattenute = await _trattenute(db)
    nomi = await _nomi_dipendenti(db)
    candidati = await _candidati_banca(db, anno, movimenti_usati)

    # verbali della posta con targa nota ma senza veicolo nel risultato
    per_targa = {str(v.get("targa") or "").upper(): v for v in veicoli_input}
    verbali_senza_targa: List[Dict[str, Any]] = []
    for numero, v in posta.items():
        targa = str(v.get("targa") or "").upper()
        if not targa:
            verbali_senza_targa.append({
                "numero_verbale": numero, "stato": v.get("stato"),
                "fattura_numero": v.get("fattura_numero") or v.get("numero_fattura"),
                "fornitore": v.get("fornitore"),
            })
            continue
        veicolo = per_targa.get(targa)
        if veicolo is None:
            veicolo = _stub_veicolo(targa, v)
            per_targa[targa] = veicolo
            veicoli_input.append(veicolo)
        if not any(str(x.get("numero_verbale") or "") == numero for x in veicolo.get("verbali") or []):
            veicolo.setdefault("verbali", []).append({
                "numero_verbale": numero, "data_verbale": _data(v.get("data_verbale") or v.get("data_violazione")),
                "fonte": "posta", "stato": v.get("stato"),
            })

    # quote per targa di ogni fattura (per spartire i pagamenti cumulativi)
    quote_targa: Dict[Tuple[str, str], int] = {}
    totale_fattura: Dict[str, int] = {}
    for veicolo in veicoli_input:
        targa = str(veicolo.get("targa") or "").upper()
        for cat in CATEGORIE_COSTO:
            for rec in veicolo.get(cat) or []:
                if cat == "verbali" and not rec.get("fattura_id"):
                    continue
                chiave = alias.get(str(rec.get("fattura_id") or "")) or f"?|{_norm_numero(rec.get('numero_fattura'))}"
                quote_targa[(targa, chiave)] = quote_targa.get((targa, chiave), 0) + _cents(rec.get("totale"))
    for (targa, chiave), cents in quote_targa.items():
        totale_fattura[chiave] = totale_fattura.get(chiave, 0) + cents

    risultato_veicoli: List[Dict[str, Any]] = []
    driver_pos: Dict[str, Dict[str, Any]] = {}
    fatture_aperte_tot: List[Dict[str, Any]] = []
    verbali_senza_quietanza: List[Dict[str, Any]] = []
    auto_senza_driver: List[str] = []
    totali = _riepilogo_vuoto()

    for veicolo in veicoli_input:
        targa = str(veicolo.get("targa") or "").upper()
        veicolo["targa"] = targa
        righe, riepilogo, aperte = _righe_fatture_veicolo(
            veicolo, alias, prove, quote_targa, totale_fattura, dichiarati_per_chiave,
        )
        righe_verbali, schede_verbali = _righe_verbali_veicolo(veicolo, posta, trattenute, riepilogo)
        righe.extend(righe_verbali)
        for riga in righe:
            if "driver" not in riga:
                # Il pagamento segue il costo che salda: il canone di marzo
                # pagato ad aprile pesa su chi aveva l'auto a marzo.
                data_costo = (riga.get("documento") or {}).get("data") or riga.get("data")
                riga["driver"] = driver_alla_data(veicolo, data_costo)
            d = riga["driver"]
            if d.get("driver_id") and not d.get("driver"):
                d["driver"] = nomi.get(str(d["driver_id"]))
        righe.sort(key=lambda r: (r.get("data") or "", 0 if r.get("tipo") == "costo" else 1), reverse=True)

        stato_contratto = (veicolo.get("stato_contratto") or "attivo")
        driver_attuale = {"driver": veicolo.get("driver") or veicolo.get("driver_nome"),
                          "driver_id": veicolo.get("driver_id")}
        if driver_attuale["driver_id"] and not driver_attuale["driver"]:
            driver_attuale["driver"] = nomi.get(str(driver_attuale["driver_id"]))
        if not (driver_attuale["driver"] or driver_attuale["driver_id"]) and stato_contratto.lower() not in STATI_CONTRATTO_CHIUSI:
            auto_senza_driver.append(targa)

        for cat in CATEGORIE_COSTO:
            totali["per_categoria"][cat]["dare_cents"] += riepilogo["per_categoria"][cat]["dare_cents"]
            totali["per_categoria"][cat]["avere_cents"] += riepilogo["per_categoria"][cat]["avere_cents"]
        totali["dare_cents"] += riepilogo["dare_cents"]
        totali["avere_cents"] += riepilogo["avere_cents"]
        totali["avere_non_verificato_cents"] += riepilogo["avere_non_verificato_cents"]

        for a in aperte:
            fatture_aperte_tot.append({**a, "targa": targa})
        for s in schede_verbali:
            if not s["pagato"]:
                verbali_senza_quietanza.append({"targa": targa, **{k: s[k] for k in (
                    "numero_verbale", "data_verbale", "importo_verificato", "importo_riaddebito",
                    "in_fattura", "driver_competente", "stato")}})

        # posizione per driver: ogni riga pesa su chi aveva l'auto alla sua data
        for riga in righe:
            d = riga.get("driver") or {}
            chiave_driver = str(d.get("driver_id") or d.get("driver") or "").strip()
            if not chiave_driver:
                chiave_driver = "__senza_driver__"
            pos = driver_pos.setdefault(chiave_driver, {
                "driver_id": d.get("driver_id"), "driver": d.get("driver") or (None if chiave_driver == "__senza_driver__" else chiave_driver),
                "veicoli": set(), "dare_cents": 0, "avere_cents": 0,
                "verbali": 0, "verbali_aperti": 0, "verbali_cents": 0, "trattenute_cents": 0,
            })
            pos["veicoli"].add(targa)
            pos["dare_cents"] += _cents(riga.get("dare"))
            pos["avere_cents"] += _cents(riga.get("avere"))
        for s in schede_verbali:
            d = s.get("driver_competente") or {}
            chiave_driver = str(d.get("driver_id") or d.get("driver") or "").strip() or "__senza_driver__"
            pos = driver_pos.setdefault(chiave_driver, {
                "driver_id": d.get("driver_id"), "driver": d.get("driver") or (None if chiave_driver == "__senza_driver__" else chiave_driver),
                "veicoli": set(), "dare_cents": 0, "avere_cents": 0,
                "verbali": 0, "verbali_aperti": 0, "verbali_cents": 0, "trattenute_cents": 0,
            })
            pos["veicoli"].add(targa)
            pos["verbali"] += 1
            if not s["pagato"]:
                pos["verbali_aperti"] += 1
            pos["verbali_cents"] += _cents(s.get("importo_riaddebito") if s.get("in_fattura") else s.get("importo_verificato"))
            pos["trattenute_cents"] += sum(_cents(t.get("importo")) for t in s.get("trattenute") or [])

        risultato_veicoli.append({
            "targa": targa, "marca": veicolo.get("marca") or "", "modello": veicolo.get("modello") or "",
            "fornitore_noleggio": veicolo.get("fornitore_noleggio"), "fornitore_piva": veicolo.get("fornitore_piva"),
            "contratto": veicolo.get("contratto"), "stato_contratto": stato_contratto,
            "data_inizio": veicolo.get("data_inizio"), "data_fine": veicolo.get("data_fine"),
            "driver_attuale": driver_attuale, "assegnazioni": veicolo.get("assegnazioni") or [],
            "riepilogo": _chiudi_riepilogo(riepilogo),
            "righe": righe, "verbali": schede_verbali,
            "fatture_aperte": len(aperte), "verbali_aperti": sum(1 for s in schede_verbali if not s["pagato"]),
        })

    risultato_veicoli.sort(key=lambda v: (v["stato_contratto"].lower() in STATI_CONTRATTO_CHIUSI, -v["riepilogo"]["saldo"], v["targa"]))

    driver_out: List[Dict[str, Any]] = []
    for chiave_driver, pos in driver_pos.items():
        driver_out.append({
            "driver_id": pos["driver_id"], "driver": pos["driver"],
            "senza_driver": chiave_driver == "__senza_driver__",
            "veicoli": sorted(pos["veicoli"]),
            "dare": _eur(pos["dare_cents"]), "avere": _eur(pos["avere_cents"]),
            "saldo": _eur(pos["dare_cents"] - pos["avere_cents"]),
            "verbali": pos["verbali"], "verbali_aperti": pos["verbali_aperti"],
            "verbali_importo": _eur(pos["verbali_cents"]), "trattenute": _eur(pos["trattenute_cents"]),
        })
    driver_out.sort(key=lambda d: (d["senza_driver"], -d["saldo"], d["driver"] or ""))

    return {
        "anno": anno,
        "veicoli": risultato_veicoli,
        "driver": driver_out,
        "totali": _chiudi_riepilogo(totali),
        "pagamenti_senza_documento": candidati,
        "controlli": {
            "auto_senza_driver": auto_senza_driver,
            "fatture_senza_pagamento": fatture_aperte_tot,
            "verbali_senza_quietanza": verbali_senza_quietanza,
            "verbali_senza_targa": len(verbali_senza_targa),
            "verbali_senza_targa_esempi": verbali_senza_targa[:10],
            "pagamenti_senza_documento": len(candidati),
            "pagamenti_dichiarati_non_verificati": len(dichiarati),
        },
        "fatture_noleggio_attive": len(info_fatture),
        "regola": "dare=costi documentati, avere=prove strutturate; mai per solo importo",
    }
