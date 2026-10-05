"""Candidati della coda «Bonifici da associare» e avviso multi-dipendente.

Regola (CLAUDE.md, «Identita', prove e attese»): nessuna entita' si associa per
solo importo e **un candidato non si applica mai**. Qui si elencano fino a 10
dipendenti-busta possibili per ogni bonifico in coda, con la prova che li
porta, e la persona sceglie. Non si scrive nessun pagamento.

Forza della prova, dalla piu' alla meno sicura:

1. codice fiscale o nome completo nella causale;
2. cognome nella causale **e** importo uguale al centesimo al residuo della
   busta del periodo (un cognome condiviso fra due dipendenti li elenca
   entrambi: senza il nome proprio non se ne sceglie uno);
3. importo uguale al centesimo al residuo di una busta, ma solo se la causale
   scrive il periodo (mese e anno). Senza periodo scritto l'importo da solo
   non produce nessun candidato.

Un bonifico gia' confermato a mano da un'altra riga (la stessa operazione
vista dalla ricevuta e dall'estratto) e' consumato: nessun candidato.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from app.constants.stati_associazione_bonifico import (
    AVVISI_MULTI_DIPENDENTE,
    AVVISO_BENEFICIARI_VARI,
    AVVISO_COGNOME_CONDIVISO,
    AVVISO_NOTA_DI_TERZI,
    AVVISO_STESSO_IMPORTO_PIU_BUSTE,
    ETA_MASSIMA_CANDIDATI_SECONDI,
    MAX_CANDIDATI,
    PROVA_CF,
    PROVA_COGNOME_CONDIVISO,
    PROVA_COGNOME_IMPORTO,
    PROVA_COGNOME_UNIVOCO,
    PROVA_IMPORTO_PERIODO,
    PROVA_NOME_COMPLETO,
    PROVE_DA_PROPOSTA,
    PROVE_TESTO,
    PUNTEGGI_PROVA,
    VERSIONE_CANDIDATI,
)
from app.services.conferma_bonifico import chiavi_confermate, e_consumato

logger = logging.getLogger(__name__)

#: Quante righe ricalcolate si scrivono per lettura: la lettura non deve
#: trasformarsi in centinaia di scritture al primo passaggio.
MAX_SCRITTURE_PER_LETTURA = 50


def cents(valore: Any) -> Optional[int]:
    """Centesimi interi da un importo (mai float nei confronti)."""
    if valore is None or valore == "" or isinstance(valore, bool):
        return None
    try:
        return int((Decimal(str(valore)) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None


def _nome(dip: Dict[str, Any]) -> str:
    return (dip.get("nome_completo")
            or " ".join(p for p in (dip.get("cognome"), dip.get("nome")) if p)).strip()


async def carica_id_cedolini(db) -> Dict[Tuple[Any, Any, Any], Any]:
    """``(dipendente_id, mese, anno) -> id del cedolino``: una lettura, senza PDF."""
    ced_id: Dict[Tuple[Any, Any, Any], Any] = {}
    try:
        async for c in db.cedolini.find({}, {"_id": 0, "pdf_data": 0}):
            ced_id.setdefault((c.get("dipendente_id"), c.get("mese"), c.get("anno")), c.get("id"))
    except Exception as exc:  # noqa: BLE001 - senza id i risultati restano validi
        logger.warning("Cedolini non letti, senza cedolino_id (%s: %s)", type(exc).__name__, exc)
    return ced_id


async def carica_buste_hr(db) -> Dict[str, List[Dict[str, Any]]]:
    """Buste aperte per dipendente: ``dipendente_id -> [{mese, anno, cedolino_id,
    importo_busta_cents, residuo_cents}]``. Una lettura per tabella (regola 4:
    un prefetch unico), residuo = busta - bonifici - acconti come
    ``_ricalcola_stato_paga``."""
    ced_id = await carica_id_cedolini(db)
    buste: Dict[str, List[Dict[str, Any]]] = {}
    async for p in db.paghe_mensili.find({}, {"_id": 0}):
        dip = p.get("dipendente_id")
        busta = cents(p.get("importo_busta"))
        if not dip or not busta or busta <= 0:
            continue
        erogato = (cents(p.get("bonifico_importo")) or 0) + sum(
            cents(a.get("importo")) or 0 for a in (p.get("acconti") or []))
        buste.setdefault(str(dip), []).append({
            "mese": p.get("mese"), "anno": p.get("anno"),
            "cedolino_id": ced_id.get((dip, p.get("mese"), p.get("anno"))),
            "importo_busta_cents": busta, "residuo_cents": busta - erogato,
        })
    return buste


def _candidato(dip: Dict[str, Any], prova: str, mese: Optional[int], anno: Optional[int],
               busta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "dipendente_id": dip.get("id"), "nome": _nome(dip),
        "cedolino_id": (busta or {}).get("cedolino_id"),
        "mese": mese, "anno": anno,
        "periodo": ("%02d/%d" % (mese, anno)) if mese and anno else None,
        "importo_residuo_cents": (busta or {}).get("residuo_cents"),
        "prova": prova, "prova_testo": PROVE_TESTO[prova], "punteggio": PUNTEGGI_PROVA[prova],
    }


def _busta_del_periodo(buste: Dict[str, List[Dict[str, Any]]], dip_id: Any,
                       periodo: Optional[Tuple[int, int]]) -> Optional[Dict[str, Any]]:
    if not periodo:
        return None
    for b in buste.get(str(dip_id), []):
        if (b.get("mese"), b.get("anno")) == (int(periodo[0]), int(periodo[1])):
            return b
    return None


def calcola_candidati(
    *, testo: str, importo: Any, data: Optional[str], indici: Dict[str, Any],
    buste: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """``{candidati, avviso_multi_dipendente, avviso_motivo, proposta}`` per un bonifico.

    Funzione pura: nessuna lettura, nessuna scrittura."""
    from app.services.distinte_bonifici import e_distinta, nota_distinta
    from app.services.hr_pagamenti_deposito import dipendenti_citati, periodo_bonifico, risolvi_dipendente
    from app.services.stipendi_bonifici import estrai_periodo_causale

    importo_c = cents(importo)
    livello, citati = dipendenti_citati(indici, testo)
    periodo_atteso = periodo_bonifico(testo, data)
    periodo_scritto = estrai_periodo_causale(testo)

    per_chiave: Dict[Tuple[Any, Any, Any], Dict[str, Any]] = {}

    def _aggiungi(cand: Dict[str, Any]) -> None:
        chiave = (cand["dipendente_id"], cand["mese"], cand["anno"])
        vecchio = per_chiave.get(chiave)
        if vecchio is None or cand["punteggio"] > vecchio["punteggio"]:
            per_chiave[chiave] = cand

    def _combacia(busta: Optional[Dict[str, Any]]) -> bool:
        return bool(busta) and importo_c is not None and busta["residuo_cents"] == importo_c

    if livello in ("cf", "nome"):
        prova = PROVA_CF if livello == "cf" else PROVA_NOME_COMPLETO
        for dip in citati:
            busta = _busta_del_periodo(buste, dip["id"], periodo_atteso)
            _aggiungi(_candidato(dip, prova, *(periodo_atteso or (None, None)), busta))
    elif livello == "cognome":
        for dip in citati:
            busta = _busta_del_periodo(buste, dip["id"], periodo_atteso)
            if _combacia(busta):
                prova = PROVA_COGNOME_IMPORTO
            elif len(citati) > 1:
                prova = PROVA_COGNOME_CONDIVISO
            else:
                prova = PROVA_COGNOME_UNIVOCO
            _aggiungi(_candidato(dip, prova, *(periodo_atteso or (None, None)), busta))
    elif periodo_scritto and importo_c is not None:
        # Nessun nome nella causale: l'importo vale solo dentro il periodo che
        # la causale scrive, mai fra periodi diversi.
        dip_per_id = {d["id"]: d for d in (indici.get("cf") or {}).values()}
        for d in (indici.get("nome") or {}).values():
            dip_per_id.setdefault(d["id"], d)
        for lista in (indici.get("cogn") or {}).values():
            for d in lista:
                dip_per_id.setdefault(d["id"], d)
        for dip_id, dip in dip_per_id.items():
            busta = _busta_del_periodo(buste, dip_id, periodo_scritto)
            if _combacia(busta):
                _aggiungi(_candidato(dip, PROVA_IMPORTO_PERIODO, periodo_scritto[0], periodo_scritto[1], busta))

    candidati = sorted(
        per_chiave.values(),
        key=lambda c: (-c["punteggio"], c["importo_residuo_cents"] is None, c["nome"], c["periodo"] or ""),
    )[:MAX_CANDIDATI]

    # ── avviso multi-dipendente ──────────────────────────────────────────────
    nota = nota_distinta(testo)
    nota_nomina = bool(nota) and risolvi_dipendente(indici, nota)[0] is not None
    motivi = set()
    if e_distinta(testo) and nota_nomina:
        motivi.add(AVVISO_NOTA_DI_TERZI)
    if e_distinta(testo) or (livello in ("cf", "nome") and len(citati) > 1):
        motivi.add(AVVISO_BENEFICIARI_VARI)
    if livello == "cognome" and len(citati) > 1:
        motivi.add(AVVISO_COGNOME_CONDIVISO)
    con_importo = [c for c in candidati if c["prova"] in (PROVA_COGNOME_IMPORTO, PROVA_IMPORTO_PERIODO)]
    if len(con_importo) > 1:
        motivi.add(AVVISO_STESSO_IMPORTO_PIU_BUSTE)
    motivo = next((m for m in AVVISI_MULTI_DIPENDENTE if m in motivi), None)

    # ── proposta: solo se il candidato e' uno e non c'e' nessun avviso ───────
    proposta = None
    if motivo is None and len(candidati) == 1 and candidati[0]["prova"] in PROVE_DA_PROPOSTA:
        c = candidati[0]
        proposta = {"dipendente_id": c["dipendente_id"], "dipendente_nome": c["nome"],
                    "tipo": "stipendio", "mese": c["mese"], "anno": c["anno"],
                    "prova": c["prova_testo"]}
    return {"candidati": candidati, "avviso_multi_dipendente": motivo is not None,
            "avviso_motivo": motivo, "proposta": proposta}


def testo_riga_coda(riga: Dict[str, Any]) -> str:
    """Il testo su cui si cercano i nomi: causale e nome del file."""
    return " ".join(str(p) for p in (riga.get("causale"), riga.get("pdf_filename")) if p)


def _campi_calcolati(esito: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "candidati": esito["candidati"],
        "avviso_multi_dipendente": esito["avviso_multi_dipendente"],
        "avviso_motivo": esito["avviso_motivo"],
        "proposta": esito["proposta"],
        "candidati_versione": VERSIONE_CANDIDATI,
        "candidati_calcolati_il": datetime.now(timezone.utc).isoformat(),
    }


def calcola_per_riga(riga: Dict[str, Any], indici: Dict[str, Any],
                     buste: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """I campi da salvare sulla riga in coda (candidati, avviso, proposta)."""
    return _campi_calcolati(calcola_candidati(
        testo=testo_riga_coda(riga), importo=riga.get("importo"), data=riga.get("data"),
        indici=indici, buste=buste))


def _e_stantio(riga: Dict[str, Any], adesso: datetime) -> bool:
    if riga.get("candidati_versione") != VERSIONE_CANDIDATI or "candidati" not in riga:
        return True
    try:
        calcolati = datetime.fromisoformat(str(riga.get("candidati_calcolati_il")))
        if calcolati.tzinfo is None:
            calcolati = calcolati.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return True
    return (adesso - calcolati).total_seconds() > ETA_MASSIMA_CANDIDATI_SECONDI


async def arricchisci_coda(db, righe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Alla lettura della coda: candidati e avviso sono quelli salvati se freschi,
    altrimenti si ricalcolano (e si salvano, al massimo ``MAX_SCRITTURE_PER_LETTURA``
    righe per volta). Un bonifico gia' confermato a mano da un'altra riga esce
    con ``gia_confermato_altrove`` e nessun candidato, sempre, anche se salvato."""
    from app.hr.routers.dipendenti_cloud import _indici_dipendenti
    from app.services.hr_pagamenti_deposito import rif_interno_banca

    adesso = datetime.now(timezone.utc)
    confermate = await chiavi_confermate(db)
    indici = buste = None
    scritte = 0
    for riga in righe:
        riga["gia_confermato_altrove"] = e_consumato(riga, confermate)
        riga["rif_banca"] = riga.get("rif_banca") or rif_interno_banca(riga.get("causale"), riga.get("pdf_filename"))
        riga.setdefault("cro", None)
        if riga["gia_confermato_altrove"]:
            riga.update({"candidati": [], "avviso_multi_dipendente": False,
                         "avviso_motivo": None, "proposta": None})
            continue
        if _e_stantio(riga, adesso):
            if indici is None:
                indici = await _indici_dipendenti(db)
                buste = await carica_buste_hr(db)
            campi = calcola_per_riga(riga, indici, buste)
            riga.update(campi)
            if scritte < MAX_SCRITTURE_PER_LETTURA and riga.get("id"):
                scritte += 1
                try:
                    await db.bonifici_da_associare.update_one({"id": riga["id"]}, {"$set": campi})
                except Exception as exc:  # noqa: BLE001 - la lettura non fallisce per un salvataggio
                    logger.warning("Candidati bonifico %s non salvati (%s: %s)",
                                   riga.get("id"), type(exc).__name__, exc)
    return righe



def integra_dettagli_distinta(riga: Dict[str, Any], distinta: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiunge i dati della distinta senza trasformare una nota di terzi in proposta."""
    riga["distinta"] = distinta
    if distinta.get("suggerimento_nota"):
        riga.update({"avviso_multi_dipendente": True, "avviso_motivo": AVVISO_NOTA_DI_TERZI,
                     "proposta": None})
    return riga


async def arricchisci_distinte(db, righe: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Alle righe della pagina «Distinte» (una per distinta ancora da associare)
    aggiunge gli stessi campi della coda: candidati, avviso, ``cro``, ``rif_banca``.

    La nota scritta nell'estratto che nomina un dipendente e' sempre ``nota_di_terzi``
    (la distinta puo' pagare piu' persone) e in quel caso non c'e' nessuna proposta."""
    if not righe:
        return righe
    coda = await db.bonifici_da_associare.find(
        {"id": {"$in": [r["id"] for r in righe]}}, {"_id": 0, "pdf_data": 0}).to_list(2000)
    per_id = {c["id"]: c for c in await arricchisci_coda(db, coda)}
    for riga in righe:
        voce = per_id.get(riga["id"])
        if not voce:
            continue
        riga.update({k: voce.get(k) for k in (
            "candidati", "avviso_multi_dipendente", "avviso_motivo", "proposta", "cro", "rif_banca",
            "gia_confermato_altrove")})
        integra_dettagli_distinta(riga, riga.get("distinta") or {})
    return righe
