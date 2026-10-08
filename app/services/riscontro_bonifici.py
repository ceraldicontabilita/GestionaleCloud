"""Riscontro bonifico <-> busta: una vista in sola lettura.

Per ogni busta dice se il pagamento e' provato, in quale misura e da quale
fonte. **Non scrive niente** (ne' pagamenti, ne' Prima Nota, ne' stati): e' la
lettura, per una persona, di cio' che l'archivio gia' contiene. Stessa forma del
``riscontro`` del minisito del titolare (``cedolini_canonici.json``).

Stati (``constants/stati_associazione_bonifico``) e come si leggono
dall'archivio che gia' esiste:

* ``confermato``: il pagamento e' provato. Corrisponde a ``stato_bonifico``
  ``riconciliato`` / ``stato_pagamento`` ``pagato`` **con prova**: conferma del
  titolare, oppure causale che scrive il periodo, oppure un solo bonifico
  d'importo uguale gia' riconciliato (``bonifico_riconciliato``);
* ``differenza``: c'e' una prova ma il pagato non fa il netto. Corrisponde a
  ``parzialmente_riconciliato`` / ``parziale``; ``differenza_cents`` = netto
  meno pagato (negativo = pagato piu' del netto);
* ``da_verificare``: ci sono bonifici ma nessuna prova (solo importo o solo
  vicinanza): li elenca, non decide. E' quello che l'archivio chiama ``pagato``
  senza ``bonifico_riconciliato``;
* ``nessun_bonifico_trovato``: nessun pagamento (``in_attesa_pagamento``);
* ``non_riscontrabile``: prima dell'inizio dei dati bancari, senza nessun
  bonifico depositato. Non e' «senza bonifico»: non si puo' dire.

Confidenza: ``alta_causale_esplicita`` (la causale scrive il periodo della
busta), ``media_importo_su_singolo_bonifico`` (un solo bonifico d'importo
uguale, senza periodo scritto), ``None`` (conferma manuale: la dice la fonte).
Fonte, per priorita': ``manuale`` > ``ricevuta`` (PDF del singolo bonifico) >
``estratto`` (riga d'estratto conto).
"""
from __future__ import annotations

import calendar
from typing import Any, Dict, List, Optional

from app.constants.stati_associazione_bonifico import (
    CAMPO_CONFERMATO,
    CONFIDENZA_ALTA_CAUSALE,
    CONFIDENZA_MEDIA_IMPORTO,
    FONTE_ESTRATTO,
    FONTE_MANUALE,
    FONTE_RICEVUTA,
    INIZIO_DATI_BANCARI,
    PRIORITA_FONTI,
    RISCONTRO_CONFERMATO,
    RISCONTRO_DA_VERIFICARE,
    RISCONTRO_DIFFERENZA,
    RISCONTRO_NESSUN_BONIFICO,
    RISCONTRO_NON_RISCONTRABILE,
)
from app.services.candidati_bonifico import carica_id_cedolini, cents

#: Limite di righe per risposta: il riscontro di un anno intero sta in una pagina.
LIMITE_RIGHE = 1000


def _fonte_esito(esito: Dict[str, Any]) -> str:
    """Da dove viene il pagamento: la conferma del titolare, la ricevuta PDF o l'estratto."""
    if esito.get(CAMPO_CONFERMATO) is True or str(esito.get("key") or "").startswith("beneficiari-diversi:"):
        return FONTE_MANUALE
    if esito.get("modificato_manualmente"):
        return FONTE_MANUALE
    origine = str(esito.get("origine") or "")
    if origine == "gestionale-estratto-conto" or str(esito.get("key") or "").startswith("ecm:"):
        return FONTE_ESTRATTO
    return FONTE_RICEVUTA


def _periodo_scritto(causale: Any, mese: int, anno: int) -> bool:
    from app.services.stipendi_bonifici import estrai_periodo_causale

    return estrai_periodo_causale(str(causale or "")) == (mese, anno)


def _fine_periodo(anno: int, mese: int) -> str:
    """Ultimo giorno del mese di competenza (13ª e 14ª contano come dicembre e luglio)."""
    m = 12 if mese == 13 else 7 if mese == 14 else mese
    return "%04d-%02d-%02d" % (anno, m, calendar.monthrange(anno, m)[1])


def riscontra_busta(paga: Dict[str, Any], esiti: List[Dict[str, Any]],
                    inizio_dati: str = INIZIO_DATI_BANCARI) -> Dict[str, Any]:
    """Il riscontro di una busta (riga di ``paghe_mensili``) coi suoi pagamenti
    (``pagamenti_esiti`` dello stesso dipendente e periodo). Funzione pura."""
    anno, mese = int(paga.get("anno") or 0), int(paga.get("mese") or 0)
    busta_c = cents(paga.get("importo_busta")) or 0
    acconti_c = sum(cents(a.get("importo")) or 0 for a in (paga.get("acconti") or []))
    bonifici = [{
        "id": e.get("key"), "cro": e.get("cro"), "data": e.get("data"),
        "importo_cents": cents(e.get("importo")) or 0, "fonte": _fonte_esito(e),
    } for e in sorted(esiti, key=lambda e: str(e.get("data") or ""))]
    totale_c = sum(b["importo_cents"] for b in bonifici)
    base = {
        "stato": None, "confidenza": None, "fonte": None,
        "bonifici": bonifici, "totale_bonifici_cents": totale_c,
        "acconti_cents": acconti_c, "importo_busta_cents": busta_c,
        "differenza_cents": busta_c - totale_c - acconti_c,
    }

    if not bonifici:
        prima_dei_dati = bool(anno and mese) and _fine_periodo(anno, mese) < inizio_dati
        return {**base, "differenza_cents": None,
                "stato": RISCONTRO_NON_RISCONTRABILE if prima_dei_dati else RISCONTRO_NESSUN_BONIFICO}
    if busta_c <= 0:
        # Un pagamento senza busta col netto: niente da confrontare, lo decide una persona.
        return {**base, "differenza_cents": None, "stato": RISCONTRO_DA_VERIFICARE,
                "fonte": next(f for f in PRIORITA_FONTI if any(b["fonte"] == f for b in bonifici))}

    fonte = next(f for f in PRIORITA_FONTI if any(b["fonte"] == f for b in bonifici))
    con_periodo = any(_periodo_scritto(e.get("causale"), mese, anno) for e in esiti)
    quadra = base["differenza_cents"] == 0
    riconciliato = paga.get("bonifico_riconciliato") is True

    if fonte == FONTE_MANUALE:
        prova, confidenza = True, None
    elif con_periodo:
        prova, confidenza = True, CONFIDENZA_ALTA_CAUSALE
    elif len(bonifici) == 1 and quadra and riconciliato:
        prova, confidenza = True, CONFIDENZA_MEDIA_IMPORTO
    else:
        prova, confidenza = False, None

    if not prova:
        stato = RISCONTRO_DA_VERIFICARE
    elif quadra:
        stato = RISCONTRO_CONFERMATO
    else:
        stato = RISCONTRO_DIFFERENZA
    return {**base, "stato": stato, "confidenza": confidenza, "fonte": fonte}


async def riscontro_periodo(db, *, anno: Optional[int] = None, mese: Optional[int] = None,
                            dipendente_id: Optional[str] = None,
                            inizio_dati: str = INIZIO_DATI_BANCARI) -> Dict[str, Any]:
    """Il riscontro di tutte le buste di un periodo o di un dipendente.

    Un prefetch per tabella, proiezioni senza PDF, nessuna scrittura."""
    filtro: Dict[str, Any] = {}
    if anno:
        filtro["anno"] = int(anno)
    if mese:
        filtro["mese"] = int(mese)
    if dipendente_id:
        filtro["dipendente_id"] = dipendente_id

    esiti_idx: Dict[tuple, List[Dict[str, Any]]] = {}
    async for e in db.pagamenti_esiti.find(filtro, {"_id": 0, "pdf_data": 0}):
        esiti_idx.setdefault((e.get("dipendente_id"), e.get("mese"), e.get("anno")), []).append(e)
    nomi: Dict[Any, str] = {}
    async for d in db.dipendenti.find({}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1}):
        nomi[d.get("id")] = (d.get("nome_completo")
                             or " ".join(p for p in (d.get("cognome"), d.get("nome")) if p)).strip()
    ced_id = await carica_id_cedolini(db)

    righe: List[Dict[str, Any]] = []
    async for p in db.paghe_mensili.find(filtro, {"_id": 0}):
        if not cents(p.get("importo_busta")) and not esiti_idx.get((p.get("dipendente_id"), p.get("mese"), p.get("anno"))):
            continue  # ne' busta ne' pagamenti: niente da riscontrare
        chiave = (p.get("dipendente_id"), p.get("mese"), p.get("anno"))
        r = riscontra_busta(p, esiti_idx.get(chiave, []), inizio_dati)
        righe.append({
            "dipendente_id": p.get("dipendente_id"), "dipendente": nomi.get(p.get("dipendente_id")) or p.get("dipendente_id"),
            "anno": p.get("anno"), "mese": p.get("mese"), "cedolino_id": ced_id.get(chiave), **r,
        })
    righe.sort(key=lambda r: ((r["anno"] or 0), (r["mese"] or 0), r["dipendente"] or ""), reverse=True)
    conteggi: Dict[str, int] = {}
    for r in righe:
        conteggi[r["stato"]] = conteggi.get(r["stato"], 0) + 1
    return {"righe": righe[:LIMITE_RIGHE], "count": len(righe), "limite": LIMITE_RIGHE,
            "conteggi": conteggi, "inizio_dati_bancari": inizio_dati}
