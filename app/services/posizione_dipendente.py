"""Posizione dare/avere di un dipendente: un solo registro, due viste.

Decisione del titolare (28/09/2026). Per ogni dipendente:

* **DARE (dovuto)**: il netto di ogni busta, 13ª e 14ª comprese. Se la busta
  stessa recupera un acconto gia' dato (voce Zucchetti ``000306`` «Recupero
  acconto»: ``cedolino_voci.VOCI_ACCONTO_RECUPERATO``), il
  dovuto del mese e' netto + acconto: l'acconto era paga di quel mese, data
  prima. Poi le parti **non bonus** di una conciliazione.
* **AVERE (pagato)**: bonifici (``pagamenti_esiti``), acconti in contanti del
  registro paghe, acconti del registro ``acconti_dipendenti`` pagati fuori
  busta (un acconto non si somma mai a un netto: e' un pagamento), pagamenti
  collegati alla parte non bonus di una conciliazione.
* **Saldo progressivo** con riporto: ogni anno apre col saldo di chiusura del
  precedente.
* **Bonus** delle conciliazioni in un riquadro a parte, col suo dovuto, pagato
  e saldo: non entra nel conto delle paghe.

Lo stesso elenco di movimenti alimenta anche la vecchia «prima nota salari»
(``GET /paghe/prima-nota``), raggruppata per mese di competenza: non esiste un
secondo registro. Gli importi si contano in ``Decimal``; diventano numeri solo
nella risposta JSON (``valuta`` = EUR).
"""
from __future__ import annotations

import base64
import calendar
import hashlib
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

VALUTA = "EUR"
CENT = Decimal("0.01")
ZERO = Decimal("0.00")
#: Arrotondamento della busta fra il netto del mese e busta + acconto (lo
#: stesso della riverifica dei netti, ``cedolini_hr_riverifica``).
SCARTO_ARROTONDAMENTO = Decimal("1.00")

COLL_CONCILIAZIONI = "conciliazioni"
#: Eccedenze dei pagamenti di conciliazione (titolare 02/10/2026): il bonifico
#: copre la conciliazione al centesimo, quello che avanza resta qui
#: ``da_attribuire`` finche' il titolare non sceglie stipendio, acconto o bonus.
COLL_ECCEDENZE = "eccedenze_pagamenti"
ECCEDENZA_DA_ATTRIBUIRE = "da_attribuire"
ECCEDENZA_ATTRIBUITA = "attribuita"
#: Dove puo' andare un'eccedenza: mai da sola, sempre una scelta del titolare.
DESTINAZIONI_ECCEDENZA = {"stipendio": "Stipendio del mese", "acconto": "Acconto",
                          "bonus": "Bonus della conciliazione"}
PREFISSO_BLOB = "conciliazione:"
DOCUMENTO_MAX_BYTE = 15 * 1024 * 1024
MIME_DOCUMENTO = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
}

#: Voci di una conciliazione (lista chiusa: si sceglie, non si scrive).
VOCI_CONCILIAZIONE = {
    "straordinari": "Straordinari",
    "lavoro_ordinario": "Lavoro ordinario",
    "bonus_transattivo": "Bonus transattivo",
    "tfr": "TFR",
    "ferie": "Ferie",
    "tredicesima": "Tredicesima",
    "quattordicesima": "Quattordicesima",
    "domeniche": "Domeniche",
    "festivita": "Festività",
    "altro": "Altro (scrivi tu)",
}
VOCE_BONUS = "bonus_transattivo"
TIPI_CONCILIAZIONE = {
    "conciliazione_sindacale": "Conciliazione sindacale",
    "saldo_spettanze": "Saldo spettanze",
    "altro": "Altro",
}
MODALITA_PAGAMENTO = {"bonifico": "Bonifico", "assegno": "Assegno", "contanti": "Contanti", "misto": "Misto"}
#: Un pagamento di conciliazione paga la parte ordinaria o il bonus: mai tutte e due.
PARTI_PAGAMENTO = {"conciliazione": "Parte ordinaria", "bonus": "Bonus"}
STATI_CONCILIAZIONE = ("da_pagare", "pagata_in_parte", "pagata")
#: Che cosa diventa un bonifico della coda «Bonifici da associare».
TIPI_BONIFICO_CODA = {"stipendio": "Stipendio", "acconto": "Acconto",
                      "conciliazione": "Conciliazione", "bonus": "Bonus conciliazione"}
#: Acconti del registro ``acconti_dipendenti`` che sono stipendio anticipato.
#: ``tfr`` e ``prestito`` no: sono un altro conto.
TIPI_ACCONTO_STIPENDIO = ("stipendio", "ferie", "tredicesima", "quattordicesima")
#: Tipi di busta che fanno dovuto (come ``sincronizza_paghe_mensili``).
TIPI_BUSTA_DOVUTO = ("ordinario", "mensile", "tredicesima", "quattordicesima", "", None)

_MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
         "agosto", "settembre", "ottobre", "novembre", "dicembre"]


class ErrorePosizione(ValueError):
    """Errore di validazione con codice stabile (il router lo rende 400)."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}

    def come_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


# ── importi e date ───────────────────────────────────────────────────────────

def importo(valore: Any) -> Optional[Decimal]:
    """Decimale al centesimo da numero, «1.000,00» o «1000.00»; None se assente."""
    if valore is None or valore == "" or isinstance(valore, bool):
        return None
    if isinstance(valore, Decimal):
        d = valore
    elif isinstance(valore, (int, float)):
        d = Decimal(str(valore))
    else:
        testo = str(valore).strip().replace("€", "").replace(" ", "")
        if "," in testo:
            testo = testo.replace(".", "").replace(",", ".")
        try:
            d = Decimal(testo)
        except InvalidOperation:
            return None
    if not d.is_finite():
        return None
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def _eur(d: Optional[Decimal]) -> Optional[float]:
    return None if d is None else float(d.quantize(CENT))


def _txt(d: Optional[Decimal]) -> Optional[str]:
    return None if d is None else str(d.quantize(CENT))


def _data_iso(valore: Any) -> Optional[str]:
    testo = str(valore or "").strip()[:10]
    try:
        return date.fromisoformat(testo).isoformat()
    except ValueError:
        return None


def _fine_mese(anno: int, mese: int) -> str:
    """Giorno che ordina una busta: l'ultimo del mese (13ª a dicembre, 14ª a luglio)."""
    m = 12 if mese == 13 else 7 if mese == 14 else mese
    return date(anno, m, calendar.monthrange(anno, m)[1]).isoformat()


def _nome_periodo(anno: int, mese: int) -> str:
    if mese == 13:
        return f"Tredicesima {anno}"
    if mese == 14:
        return f"Quattordicesima {anno}"
    return f"{_MESI[mese - 1].capitalize()} {anno}" if 1 <= mese <= 12 else f"{mese}/{anno}"


def _intero(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _mese_registro(ced: Dict[str, Any]) -> Optional[int]:
    tipo = str(ced.get("tipo_cedolino") or "").strip().lower()
    if tipo == "tredicesima":
        return 13
    if tipo == "quattordicesima":
        return 14
    return _intero(ced.get("mese"))


# ── la busta: netto + acconto recuperato ─────────────────────────────────────

def acconto_in_busta(ced: Dict[str, Any], netto_cella: Optional[Decimal]) -> Tuple[Decimal, Optional[str]]:
    """Acconto gia' dato e recuperato in questa busta, e da dove si legge.

    1. la voce codificata (``dati_chiave.acconto_recuperato_busta``, dal
       lettore unico con ``VOCI_ACCONTO_RECUPERATO``);
    2. ``acconti.acconto_recuperato`` del vecchio lettore;
    3. competenze − trattenute oltre la cella del netto di piu' di 1,00 €.
    """
    dati = ced.get("dati_chiave") or {}
    voce = importo(dati.get("acconto_recuperato_busta"))
    if voce and voce > 0:
        return voce, "voce " + str(dati.get("acconto_recuperato_voce") or "acconto")
    registrato = importo((ced.get("acconti") or {}).get("acconto_recuperato"))
    if registrato and registrato > 0:
        return registrato, "acconto recuperato in busta"
    calcolato = _netto_calcolato(ced)
    if calcolato is not None and netto_cella is not None and calcolato - netto_cella > SCARTO_ARROTONDAMENTO:
        return calcolato - netto_cella, "competenze meno trattenute"
    return ZERO, None


def _netto_calcolato(ced: Dict[str, Any]) -> Optional[Decimal]:
    comp, tratt = importo(ced.get("competenze")), importo(ced.get("trattenute"))
    if comp is None or tratt is None:
        return None
    return comp - tratt


def dovuto_busta(paga: Dict[str, Any], ced: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Il dovuto di un mese: netto della busta piu' l'acconto recuperato in busta.

    Un importo corretto a mano nel registro paghe vince (e' il numero del
    titolare). In HR il ``netto`` di una busta riverificata e' gia' il totale
    del mese e la cella sta in ``netto_busta``: l'acconto non si somma due volte.
    """
    registro = importo(paga.get("importo_busta"))
    if paga.get("importo_busta_manuale") or not ced:
        return {"dovuto": registro, "netto_busta": registro, "acconto": ZERO, "fonte_acconto": None,
                "manuale": bool(paga.get("importo_busta_manuale"))}
    netto = importo(ced.get("netto"))
    if netto is None:
        netto = registro
    cella = importo(ced.get("netto_busta"))
    base = cella if cella is not None else netto
    if base is None:
        return {"dovuto": None, "netto_busta": None, "acconto": ZERO, "fonte_acconto": None, "manuale": False}
    acconto, fonte = acconto_in_busta(ced, base)
    if not acconto:
        return {"dovuto": netto if cella is None else cella, "netto_busta": base, "acconto": ZERO,
                "fonte_acconto": None, "manuale": False}
    if cella is None:
        calcolato = _netto_calcolato(ced)
        if (fonte != "competenze meno trattenute" and calcolato is not None
                and abs(calcolato - netto) <= SCARTO_ARROTONDAMENTO):
            # il netto registrato e' gia' busta + acconto (vecchio import):
            # la cella si ricava togliendo l'acconto
            return {"dovuto": netto, "netto_busta": netto - acconto, "acconto": acconto,
                    "fonte_acconto": fonte, "manuale": False}
    return {"dovuto": base + acconto, "netto_busta": base, "acconto": acconto,
            "fonte_acconto": fonte, "manuale": False}


# ── conciliazioni ────────────────────────────────────────────────────────────

def _scelta(valore: Any, ammessi: Dict[str, str], campo: str) -> str:
    v = str(valore or "").strip().lower()
    if v not in ammessi:
        raise ErrorePosizione("VALORE_NON_AMMESSO", f"{campo}: scegli fra {', '.join(ammessi)}",
                              {"campo": campo, "ammessi": list(ammessi)})
    return v


def normalizza_conciliazione(dati: Dict[str, Any]) -> Dict[str, Any]:
    """Campi validati di una conciliazione (senza pagamenti, documento e stato).

    Il totale deve essere la somma delle voci al centesimo. Con
    ``importi_non_compilati`` (verbale con gli importi in bianco) il totale
    resta nullo e nessun importo si inventa.
    """
    dip = str(dati.get("dipendente_id") or "").strip()
    if not dip:
        raise ErrorePosizione("DIPENDENTE_MANCANTE", "Scegli il dipendente")
    data = _data_iso(dati.get("data"))
    if not data:
        raise ErrorePosizione("DATA_NON_VALIDA", "Data della conciliazione non valida (aaaa-mm-gg)")
    tipo = _scelta(dati.get("tipo"), TIPI_CONCILIAZIONE, "tipo")
    modalita = _scelta(dati.get("modalita_pagamento") or "bonifico", MODALITA_PAGAMENTO, "modalita_pagamento")
    non_compilati = bool(dati.get("importi_non_compilati"))

    voci: List[Dict[str, Any]] = []
    for i, v in enumerate(dati.get("voci") or []):
        nome = _scelta((v or {}).get("voce"), VOCI_CONCILIAZIONE, f"voci[{i}].voce")
        descr = str((v or {}).get("descrizione") or "").strip()
        if nome == "altro" and not descr:
            raise ErrorePosizione("DESCRIZIONE_MANCANTE", "La voce «Altro» vuole una descrizione",
                                  {"riga": i})
        imp = importo((v or {}).get("importo"))
        if not non_compilati:
            if imp is None or imp <= 0:
                raise ErrorePosizione("IMPORTO_NON_VALIDO", "Ogni voce vuole un importo maggiore di zero",
                                      {"riga": i})
        elif imp is not None:
            raise ErrorePosizione("IMPORTI_NON_COMPILATI", "Con «importi non compilati» le voci restano senza importo",
                                  {"riga": i})
        voci.append({"voce": nome, "descrizione": descr or None, "importo": _txt(imp)})
    if not voci:
        raise ErrorePosizione("VOCI_MANCANTI", "Aggiungi almeno una voce")

    totale = importo(dati.get("totale"))
    if non_compilati:
        if totale is not None:
            raise ErrorePosizione("IMPORTI_NON_COMPILATI", "Con «importi non compilati» il totale resta vuoto")
        bonus = None
    else:
        somma = sum((importo(v["importo"]) for v in voci), ZERO)
        if totale is None or totale != somma:
            raise ErrorePosizione("TOTALE_NON_QUADRA", "Il totale non è la somma delle voci al centesimo",
                                  {"totale": _txt(totale), "somma_voci": _txt(somma)})
        bonus = sum((importo(v["importo"]) for v in voci if v["voce"] == VOCE_BONUS), ZERO)

    rate: List[Dict[str, Any]] = []
    for i, r in enumerate(dati.get("rate") or []):
        imp = importo((r or {}).get("importo"))
        entro = _data_iso((r or {}).get("entro_il"))
        if imp is None or imp <= 0 or not entro:
            raise ErrorePosizione("RATA_NON_VALIDA", "Ogni rata vuole importo e data «entro il»", {"riga": i})
        rate.append({"importo": _txt(imp), "entro_il": entro})
    if totale is not None and rate and sum((importo(r["importo"]) for r in rate), ZERO) > totale:
        raise ErrorePosizione("RATE_OLTRE_TOTALE", "Le rate superano il totale della conciliazione")

    return {
        "dipendente_id": dip, "data": data, "tipo": tipo, "voci": voci,
        "totale": _txt(totale), "bonus": _txt(bonus),
        "parte_ordinaria": _txt(totale - bonus) if totale is not None else None,
        "modalita_pagamento": modalita, "rate": sorted(rate, key=lambda r: r["entro_il"]),
        "importi_non_compilati": non_compilati,
        "note": str(dati.get("note") or "").strip() or None,
        "valuta": VALUTA,
    }


def normalizza_pagamento(dati: Dict[str, Any], conciliazione: Dict[str, Any]) -> Dict[str, Any]:
    imp = importo(dati.get("importo"))
    if imp is None or imp <= 0:
        raise ErrorePosizione("IMPORTO_NON_VALIDO", "Importo del pagamento maggiore di zero")
    data = _data_iso(dati.get("data"))
    if not data:
        raise ErrorePosizione("DATA_NON_VALIDA", "Data del pagamento non valida (aaaa-mm-gg)")
    parte = _scelta(dati.get("parte") or "conciliazione", PARTI_PAGAMENTO, "parte")
    if parte == "bonus" and conciliazione.get("totale") is not None and not importo(conciliazione.get("bonus")):
        raise ErrorePosizione("SENZA_BONUS", "Questa conciliazione non ha un bonus da pagare")
    modalita = _scelta(dati.get("modalita") or "bonifico", MODALITA_PAGAMENTO, "modalita")
    return {"id": str(dati.get("id") or uuid.uuid4()), "data": data, "importo": _txt(imp),
            "modalita": modalita, "parte": parte, "origine": dati.get("origine") or "manuale",
            "bonifico_da_associare_id": dati.get("bonifico_da_associare_id"),
            "movimento_id": dati.get("movimento_id"),
            "nota": str(dati.get("nota") or "").strip() or None}


def stato_conciliazione(conc: Dict[str, Any]) -> str:
    pagato = sum((importo(p.get("importo")) or ZERO for p in conc.get("pagamenti") or []), ZERO)
    totale = importo(conc.get("totale"))
    if pagato <= 0:
        return "da_pagare"
    if totale is None or pagato < totale:
        return "pagata_in_parte"
    return "pagata"


def vista_conciliazione(conc: Dict[str, Any]) -> Dict[str, Any]:
    """Documento per la pagina: stato ricalcolato, pagato per parte, niente contenuti binari."""
    out = {k: v for k, v in conc.items() if k not in ("_id", "file_data")}
    pag = conc.get("pagamenti") or []
    per_parte = {p: sum((importo(x.get("importo")) or ZERO for x in pag if x.get("parte") == p), ZERO)
                 for p in PARTI_PAGAMENTO}
    out["pagato_ordinaria"] = _txt(per_parte["conciliazione"])
    out["pagato_bonus"] = _txt(per_parte["bonus"])
    out["pagato_totale"] = _txt(per_parte["conciliazione"] + per_parte["bonus"])
    out["stato"] = stato_conciliazione(conc)
    if conc.get("documento"):
        out["documento"] = {k: v for k, v in conc["documento"].items() if k != "contenuto_b64"}
    return out


# ── i movimenti del registro ─────────────────────────────────────────────────

def _mov(data: str, tipo: str, descrizione: str, *, dare: Optional[Decimal] = None,
         avere: Optional[Decimal] = None, competenza: Optional[Tuple[int, int]] = None,
         fonte: str, link: Optional[Dict[str, Any]] = None, avviso: Optional[str] = None,
         ordine: int = 1) -> Dict[str, Any]:
    return {"data": data, "tipo": tipo, "descrizione": descrizione, "dare": dare, "avere": avere,
            "competenza": competenza, "fonte": fonte, "link": link or {}, "avviso": avviso,
            "ordine": ordine}


def componi_movimenti(*, paghe: Iterable[Dict[str, Any]], esiti: Iterable[Dict[str, Any]],
                      cedolini: Iterable[Dict[str, Any]], acconti: Iterable[Dict[str, Any]],
                      conciliazioni: Iterable[Dict[str, Any]],
                      eccedenze: Iterable[Dict[str, Any]] = ()) -> Dict[str, List[Dict[str, Any]]]:
    """Tutti i movimenti di UN dipendente: ``registro`` (paghe) e ``bonus`` a parte.

    Un'eccedenza ``da_attribuire`` compare nel registro **senza** dare ne'
    avere, con l'avviso: non e' un pagamento di stipendio finche' il titolare
    non lo dice (una attribuita e' gia' un bonifico, un acconto o un bonus)."""
    registro: List[Dict[str, Any]] = []
    bonus: List[Dict[str, Any]] = []

    paghe_idx: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for p in paghe:
        a, m = _intero(p.get("anno")), _intero(p.get("mese"))
        if a and m:
            paghe_idx[(a, m)] = p
    ced_per_id: Dict[str, Dict[str, Any]] = {}
    ced_idx: Dict[Tuple[int, int], Dict[str, Any]] = {}
    from app.services.cedolini_versioni import attiva

    for c in cedolini:
        tipo = str(c.get("tipo_cedolino") or "").strip().lower() or None
        # una versione superata della busta (`sostituito`) non e' un dovuto
        if tipo not in TIPI_BUSTA_DOVUTO or not attiva(c):
            continue
        if c.get("id"):
            ced_per_id[c["id"]] = c
        a, m = _intero(c.get("anno")), _mese_registro(c)
        if a and m:
            ced_idx.setdefault((a, m), c)

    esiti = list(esiti)
    periodi_con_esiti = {(_intero(e.get("anno")), _intero(e.get("mese"))) for e in esiti}

    # DARE: una busta per periodo (registro paghe e cedolini, uniti per periodo)
    for chiave in sorted(set(paghe_idx) | set(ced_idx)):
        a, m = chiave
        paga = paghe_idx.get(chiave) or {}
        ced = ced_per_id.get(paga.get("cedolino_id")) or ced_idx.get(chiave)
        d = dovuto_busta(paga, ced)
        link = {"cedolino_id": (ced or {}).get("id") or paga.get("cedolino_id"), "anno": a, "mese": m}
        if d["dovuto"] is None:
            if ced is not None:
                registro.append(_mov(_fine_mese(a, m), "busta", f"Busta {_nome_periodo(a, m)}",
                                     competenza=chiave, fonte="cedolino", link=link, ordine=0,
                                     avviso="netto non leggibile: non entra nel saldo"))
        elif d["dovuto"] > 0 or ced:
            descr = f"Busta {_nome_periodo(a, m)}"
            if d["acconto"]:
                descr += (f" (netto in busta {d['netto_busta']:.2f} + acconto recuperato "
                          f"{d['acconto']:.2f}, {d['fonte_acconto']})")
            elif d["manuale"]:
                descr += " (importo corretto a mano)"
            # senza voce ne' annotazione l'acconto e' dedotto dai totali: se il
            # lettore ha preso solo una parte delle trattenute sembra un acconto
            avviso = ("acconto dedotto da competenze − trattenute: verificarlo sulla busta"
                      if d["fonte_acconto"] == "competenze meno trattenute" else None)
            registro.append(_mov(_fine_mese(a, m), "busta", descr, dare=d["dovuto"], competenza=chiave,
                                 fonte="cedolino" if ced else "registro_paghe", link=link, ordine=0,
                                 avviso=avviso))

        # registro paghe senza bonifici singoli: l'importo del mese
        bon = importo(paga.get("bonifico_importo"))
        if bon and bon > 0 and chiave not in periodi_con_esiti:
            registro.append(_mov(_data_iso(paga.get("bonifico_data")) or _fine_mese(a, m), "bonifico",
                                 f"Bonifico {_nome_periodo(a, m)} (registro paghe)", avere=bon,
                                 competenza=chiave, fonte="registro_paghe", link={"anno": a, "mese": m}))

    # AVERE: bonifici reali
    for e in esiti:
        imp = importo(e.get("importo"))
        a, m = _intero(e.get("anno")), _intero(e.get("mese"))
        if not imp or not a or not m:
            continue
        causale = str(e.get("causale") or "").strip()
        registro.append(_mov(_data_iso(e.get("data")) or _fine_mese(a, m), "bonifico",
                             f"Bonifico per {_nome_periodo(a, m)}" + (f" — {causale[:80]}" if causale else ""),
                             avere=imp, competenza=(a, m), fonte="pagamenti_esiti",
                             link={"key": e.get("key"), "anno": a, "mese": m}))

    # AVERE: acconti in contanti del registro paghe e acconti del registro acconti
    visti = set()
    for (a, m), paga in sorted(paghe_idx.items()):
        for acc in paga.get("acconti") or []:
            imp = importo(acc.get("importo"))
            if not imp or imp <= 0:
                continue
            data = _data_iso(acc.get("data")) or _fine_mese(a, m)
            visti.add((data, imp))
            registro.append(_mov(data, "acconto", f"Acconto in contanti ({_nome_periodo(a, m)})",
                                 avere=imp, competenza=(a, m), fonte="registro_paghe",
                                 link={"anno": a, "mese": m}))
    for acc in acconti:
        if str(acc.get("tipo") or "") not in TIPI_ACCONTO_STIPENDIO or acc.get("stato") == "annullato":
            continue
        imp = importo(acc.get("importo"))
        data = _data_iso(acc.get("data"))
        if not imp or imp <= 0 or not data:
            continue
        if (data, imp) in visti:
            continue  # lo stesso acconto gia' scritto nel registro paghe
        visti.add((data, imp))
        comp = str(acc.get("scalato_su_anno_mese") or data[:7])
        a, m = _intero(comp[:4]), _intero(comp[5:7])
        mezzo = "bonifico" if acc.get("source") == "bonifici_da_associare" else str(acc.get("tipo_bonifico") or "")
        registro.append(_mov(data, "acconto",
                             f"Acconto {acc.get('tipo')}" + (f" ({mezzo})" if mezzo else ""),
                             avere=imp, competenza=(a, m) if a and m else None,
                             fonte="acconti_dipendenti", link={"acconto_id": acc.get("id")}))

    # Conciliazioni: parte ordinaria nel registro, bonus a parte
    for c in conciliazioni:
        if c.get("annullata"):
            continue
        data = _data_iso(c.get("data"))
        if not data:
            continue
        a, m = int(data[:4]), int(data[5:7])
        nome = TIPI_CONCILIAZIONE.get(c.get("tipo"), "Conciliazione")
        link = {"conciliazione_id": c.get("id")}
        if c.get("importi_non_compilati") or c.get("totale") is None:
            registro.append(_mov(data, "conciliazione", f"{nome} del {data}", competenza=(a, m),
                                 fonte="conciliazioni", link=link, ordine=0,
                                 avviso="importi non compilati: non entra nel saldo"))
        else:
            ordinaria = importo(c.get("totale")) - (importo(c.get("bonus")) or ZERO)
            if ordinaria > 0:
                registro.append(_mov(data, "conciliazione", f"{nome} del {data} (senza bonus)",
                                     dare=ordinaria, competenza=(a, m), fonte="conciliazioni",
                                     link=link, ordine=0))
            b = importo(c.get("bonus")) or ZERO
            if b > 0:
                bonus.append(_mov(data, "conciliazione", f"Bonus — {nome} del {data}", dare=b,
                                  fonte="conciliazioni", link=link, ordine=0))
        for p in c.get("pagamenti") or []:
            imp = importo(p.get("importo"))
            pdata = _data_iso(p.get("data")) or data
            if not imp:
                continue
            descr = f"Pagamento {MODALITA_PAGAMENTO.get(p.get('modalita'), '').lower()} — {nome} del {data}"
            mov = _mov(pdata, "pagamento_conciliazione", descr, avere=imp,
                       competenza=(int(pdata[:4]), int(pdata[5:7])), fonte="conciliazioni",
                       link={**link, "pagamento_id": p.get("id")})
            (bonus if p.get("parte") == "bonus" else registro).append(mov)

    for ecc in eccedenze:
        if ecc.get("stato") != ECCEDENZA_DA_ATTRIBUIRE:
            continue
        imp, data = importo(ecc.get("importo")), _data_iso(ecc.get("data"))
        if not imp or not data:
            continue
        registro.append(_mov(data, "eccedenza", f"Eccedenza di {imp:.2f} € sul pagamento di conciliazione",
                             competenza=(int(data[:4]), int(data[5:7])), fonte="eccedenze_pagamenti",
                             link={"eccedenza_id": ecc.get("id"), "conciliazione_id": ecc.get("conciliazione_id")},
                             avviso="da attribuire: scegli stipendio, acconto o bonus (non entra nel saldo)"))

    ordina = lambda x: (x["data"], x["ordine"], x["tipo"], x["descrizione"])  # noqa: E731
    return {"registro": sorted(registro, key=ordina), "bonus": sorted(bonus, key=ordina)}


def _con_saldo(movimenti: List[Dict[str, Any]], partenza: Decimal = ZERO) -> Tuple[List[Dict[str, Any]], Decimal]:
    saldo, out = partenza, []
    for mv in movimenti:
        saldo += (mv["dare"] or ZERO) - (mv["avere"] or ZERO)
        out.append({**mv, "saldo": saldo})
    return out, saldo


def _riga_json(mv: Dict[str, Any]) -> Dict[str, Any]:
    return {"data": mv["data"], "tipo": mv["tipo"], "descrizione": mv["descrizione"],
            "dare": _eur(mv["dare"]), "avere": _eur(mv["avere"]), "saldo": _eur(mv.get("saldo")),
            "fonte": mv["fonte"], "link": mv["link"], "avviso": mv["avviso"]}


def _mese_di(valore: Any) -> Optional[Tuple[int, int]]:
    iso = _data_iso(valore)
    return (int(iso[:4]), int(iso[5:7])) if iso else None


def mesi_mancanti(registro: List[Dict[str, Any]], anno: int,
                  rapporto: Optional[Dict[str, Any]] = None,
                  oggi: Optional[date] = None) -> List[Tuple[int, int]]:
    """Mesi dell'anno senza nessuna busta, dentro il rapporto di lavoro.

    Parte dall'assunzione (se manca, dalla prima busta in archivio: nessuna data
    inventata) e si ferma alla cessazione o al mese scorso. 13ª e 14ª non sono
    mesi. Un mese è mancante solo se nessun cedolino né riga paga lo copre.
    """
    coperti = {mv["competenza"] for mv in registro if mv["tipo"] == "busta" and mv["competenza"]}
    if not coperti:
        return []
    oggi = oggi or datetime.now(timezone.utc).date()
    rapporto = rapporto or {}
    inizio = _mese_di(rapporto.get("data_assunzione")) or min(c for c in coperti if c[1] <= 12)
    fine = (oggi.year, oggi.month - 1) if oggi.month > 1 else (oggi.year - 1, 12)
    cess = _mese_di(rapporto.get("data_cessazione"))
    if cess and cess < fine:
        fine = cess
    return [(anno, m) for m in range(1, 13)
            if inizio <= (anno, m) <= fine and (anno, m) not in coperti]


def posizione(movimenti: Dict[str, List[Dict[str, Any]]], anno: Optional[int] = None,
              rapporto: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Posizione con riporto: apertura = saldo di chiusura dell'anno prima."""
    registro = movimenti["registro"]
    anni = sorted({int(mv["data"][:4]) for mv in registro})
    if anno is None:
        anno = anni[-1] if anni else datetime.now(timezone.utc).year
    prima = [mv for mv in registro if int(mv["data"][:4]) < anno]
    nell_anno = [mv for mv in registro if int(mv["data"][:4]) == anno]
    mancanti = mesi_mancanti(registro, anno, rapporto)
    nell_anno = sorted(nell_anno + [
        _mov(_fine_mese(a, m), "mese_mancante", f"Busta {_nome_periodo(a, m)}: mese mancante",
             competenza=(a, m), fonte="controllo_archivio", ordine=0,
             avviso="busta non trovata in archivio né su Drive")
        for a, m in mancanti], key=lambda x: (x["data"], x["ordine"], x["tipo"], x["descrizione"]))
    _, apertura = _con_saldo(prima)
    righe, chiusura = _con_saldo(nell_anno, apertura)
    per_anno, saldo = [], ZERO
    for a in anni:
        dell_anno = [mv for mv in registro if int(mv["data"][:4]) == a]
        dare = sum((mv["dare"] or ZERO for mv in dell_anno), ZERO)
        avere = sum((mv["avere"] or ZERO for mv in dell_anno), ZERO)
        per_anno.append({"anno": a, "apertura": _eur(saldo), "dare": _eur(dare), "avere": _eur(avere),
                         "chiusura": _eur(saldo + dare - avere)})
        saldo += dare - avere

    righe_bonus, saldo_bonus = _con_saldo(movimenti["bonus"])
    return {
        "valuta": VALUTA, "anno": anno, "anni": anni,
        "apertura": _eur(apertura), "chiusura": _eur(chiusura),
        "totale_dare": _eur(sum((mv["dare"] or ZERO for mv in nell_anno), ZERO)),
        "totale_avere": _eur(sum((mv["avere"] or ZERO for mv in nell_anno), ZERO)),
        "righe": [_riga_json(mv) for mv in righe],
        "mesi_mancanti": [{"anno": a, "mese": m} for a, m in mancanti],
        "per_anno": per_anno,
        "avvisi": [mv["descrizione"] + ": " + mv["avviso"] for mv in nell_anno if mv["avviso"]],
        "bonus": {
            "dovuto": _eur(sum((mv["dare"] or ZERO for mv in righe_bonus), ZERO)),
            "pagato": _eur(sum((mv["avere"] or ZERO for mv in righe_bonus), ZERO)),
            "saldo": _eur(saldo_bonus),
            "righe": [_riga_json(mv) for mv in righe_bonus],
        },
    }


def prima_nota_mensile(movimenti: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Vista per mese di competenza dello stesso registro (modale «Prima nota»)."""
    mesi: Dict[Tuple[int, int], Dict[str, Decimal]] = {}
    for mv in movimenti["registro"]:
        comp = mv["competenza"] or (int(mv["data"][:4]), int(mv["data"][5:7]))
        r = mesi.setdefault(comp, {"busta": ZERO, "acconto_in_busta": ZERO, "bonifico": ZERO,
                                   "acconti": ZERO, "altro_dare": ZERO, "altro_avere": ZERO})
        if mv["tipo"] == "busta":
            r["busta"] += mv["dare"] or ZERO
        elif mv["tipo"] == "bonifico":
            r["bonifico"] += mv["avere"] or ZERO
        elif mv["tipo"] == "acconto":
            r["acconti"] += mv["avere"] or ZERO
        else:
            r["altro_dare"] += mv["dare"] or ZERO
            r["altro_avere"] += mv["avere"] or ZERO
    righe, saldo = [], ZERO
    for (a, m) in sorted(mesi):
        r = mesi[(a, m)]
        dovuto = r["busta"] + r["altro_dare"]
        erogato = r["bonifico"] + r["acconti"] + r["altro_avere"]
        if not dovuto and not erogato:
            continue
        saldo += dovuto - erogato
        righe.append({"anno": a, "mese": m, "busta": _eur(dovuto), "bonifico": _eur(r["bonifico"]),
                      "acconti": _eur(r["acconti"]), "erogato": _eur(erogato),
                      "saldo_progressivo": _eur(saldo)})
    return {"righe": righe, "saldo_finale": _eur(saldo), "valuta": VALUTA}


# ── lettura dall'archivio HR ─────────────────────────────────────────────────

async def carica_movimenti(db, dipendente_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """Una lettura per collezione, filtrata sul dipendente, senza PDF."""
    senza_pdf = {"_id": 0, "pdf_data": 0}
    paghe = await db.paghe_mensili.find({"dipendente_id": dipendente_id}, {"_id": 0}).to_list(5000)
    esiti = await db.pagamenti_esiti.find({"dipendente_id": dipendente_id}, senza_pdf).to_list(5000)
    cedolini = await db.cedolini.find({"dipendente_id": dipendente_id}, senza_pdf).to_list(5000)
    acconti = await db.acconti_dipendenti.find({"dipendente_id": dipendente_id}, {"_id": 0}).to_list(2000)
    conc = await db[COLL_CONCILIAZIONI].find(
        {"dipendente_id": dipendente_id}, {"_id": 0, "file_data": 0}).to_list(500)
    ecc = await db[COLL_ECCEDENZE].find({"dipendente_id": dipendente_id}, {"_id": 0}).to_list(500)
    return componi_movimenti(paghe=paghe, esiti=esiti, cedolini=cedolini, acconti=acconti,
                             conciliazioni=conc, eccedenze=ecc)


def vista_eccedenza(ecc: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in ecc.items() if k != "_id"}
    out["importo"] = _txt(importo(ecc.get("importo")))
    out["destinazioni"] = [{"id": k, "label": v} for k, v in DESTINAZIONI_ECCEDENZA.items()]
    return out


async def eccedenze_da_attribuire(db, dipendente_id: str) -> List[Dict[str, Any]]:
    righe = await db[COLL_ECCEDENZE].find(
        {"dipendente_id": dipendente_id, "stato": ECCEDENZA_DA_ATTRIBUIRE}, {"_id": 0}).to_list(500)
    righe.sort(key=lambda r: r.get("data") or "")
    return [vista_eccedenza(r) for r in righe]


async def posizione_dipendente(db, dipendente_id: str, anno: Optional[int] = None) -> Dict[str, Any]:
    rapporto = await db.dipendenti.find_one(
        {"id": dipendente_id}, {"_id": 0, "data_assunzione": 1, "data_cessazione": 1}) or {}
    out = posizione(await carica_movimenti(db, dipendente_id), anno, rapporto)
    out["dipendente_id"] = dipendente_id
    # Le eccedenze da attribuire si mostrano sempre, di qualunque anno: sono
    # soldi usciti che non hanno ancora una destinazione.
    out["eccedenze_da_attribuire"] = await eccedenze_da_attribuire(db, dipendente_id)
    return out


async def prima_nota_dipendente(db, dipendente_id: str) -> Dict[str, Any]:
    return prima_nota_mensile(await carica_movimenti(db, dipendente_id))


# ── scritture ────────────────────────────────────────────────────────────────

def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


def residuo_parte(conc: Dict[str, Any], parte: str) -> Optional[Decimal]:
    """Quanto manca a coprire la parte (``conciliazione`` o ``bonus``), al
    centesimo; ``None`` se gli importi non sono compilati."""
    totale = importo(conc.get("totale"))
    if totale is None:
        return None
    bonus = importo(conc.get("bonus")) or ZERO
    dovuto = bonus if parte == "bonus" else totale - bonus
    pagato = sum((importo(p.get("importo")) or ZERO for p in conc.get("pagamenti") or []
                  if p.get("parte") == parte), ZERO)
    return dovuto - pagato


async def aggiungi_pagamento(db, conciliazione_id: str, dati: Dict[str, Any]) -> Dict[str, Any]:
    """Un pagamento sulla conciliazione; idempotente per bonifico della coda.

    Titolare (02/10/2026): il pagamento copre la parte scelta **al centesimo**;
    quello che supera il residuo non si attribuisce da solo a niente: resta in
    ``eccedenze_pagamenti`` ``da_attribuire`` sulla posizione del dipendente,
    e il titolare sceglie stipendio, acconto o bonus (``attribuisci_eccedenza``).
    La risposta porta ``eccedenza`` quando ne nasce una."""
    conc = await db[COLL_CONCILIAZIONI].find_one({"id": conciliazione_id}, {"_id": 0, "file_data": 0})
    if not conc or conc.get("annullata"):
        raise ErrorePosizione("CONCILIAZIONE_NON_TROVATA", "Conciliazione non trovata o annullata")
    if dati.get("dipendente_id") and dati["dipendente_id"] != conc.get("dipendente_id"):
        raise ErrorePosizione("DIPENDENTE_DIVERSO", "La conciliazione è di un altro dipendente")
    pag = normalizza_pagamento(dati, conc)
    pagamenti = list(conc.get("pagamenti") or [])
    coda = pag.get("bonifico_da_associare_id")
    if coda and (any(p.get("bonifico_da_associare_id") == coda for p in pagamenti)
                 or await db[COLL_ECCEDENZE].find_one({"bonifico_da_associare_id": coda}, {"_id": 0, "id": 1})):
        return vista_conciliazione(conc)

    versato = importo(pag["importo"])
    residuo = residuo_parte(conc, pag["parte"])
    eccedenza: Optional[Dict[str, Any]] = None
    if residuo is not None and versato > residuo:
        avanzo = versato - max(residuo, ZERO)
        eccedenza = {
            "id": str(uuid.uuid4()), "dipendente_id": conc["dipendente_id"],
            "conciliazione_id": conciliazione_id, "pagamento_id": pag["id"] if residuo > 0 else None,
            "parte": pag["parte"], "data": pag["data"], "importo": _txt(avanzo),
            "importo_versato": _txt(versato), "residuo_coperto": _txt(max(residuo, ZERO)),
            "modalita": pag["modalita"], "origine": pag.get("origine"),
            "bonifico_da_associare_id": coda, "movimento_id": pag.get("movimento_id"),
            "stato": ECCEDENZA_DA_ATTRIBUIRE, "valuta": VALUTA,
            "created_at": _adesso(), "updated_at": _adesso(),
        }
        await db[COLL_ECCEDENZE].insert_one(dict(eccedenza))
        if residuo <= 0:
            # parte gia' coperta: niente da scrivere sulla conciliazione
            out = vista_conciliazione(conc)
            out["eccedenza"] = vista_eccedenza(eccedenza)
            return out
        pag["importo"] = _txt(residuo)
        pag["eccedenza_id"] = eccedenza["id"]
        pag["importo_versato"] = _txt(versato)
    pagamenti.append(pag)
    conc["pagamenti"] = pagamenti
    agg = {"pagamenti": pagamenti, "stato": stato_conciliazione(conc), "updated_at": _adesso()}
    await db[COLL_CONCILIAZIONI].update_one({"id": conciliazione_id}, {"$set": agg})
    conc.update(agg)
    out = vista_conciliazione(conc)
    if eccedenza:
        out["eccedenza"] = vista_eccedenza(eccedenza)
    return out


async def attribuisci_eccedenza(db, eccedenza_id: str, dati: Dict[str, Any],
                                attore: Optional[str] = None) -> Dict[str, Any]:
    """Il titolare dice dove va un'eccedenza: ``stipendio`` (bonifico del mese,
    ``pagamenti_esiti``), ``acconto`` (registro unico ``acconti_dipendenti``) o
    ``bonus`` (pagamento del bonus della stessa conciliazione, solo se ci sta
    al centesimo). Mai da sola; una gia' attribuita non si tocca."""
    ecc = await db[COLL_ECCEDENZE].find_one({"id": eccedenza_id}, {"_id": 0})
    if not ecc:
        raise ErrorePosizione("ECCEDENZA_NON_TROVATA", "Eccedenza non trovata")
    if ecc.get("stato") != ECCEDENZA_DA_ATTRIBUIRE:
        raise ErrorePosizione("ECCEDENZA_GIA_ATTRIBUITA", "Questa eccedenza è già stata attribuita",
                              {"stato": ecc.get("stato"), "attribuita_a": ecc.get("attribuita_a")})
    destinazione = _scelta(dati.get("destinazione"), DESTINAZIONI_ECCEDENZA, "destinazione")
    imp, data = importo(ecc.get("importo")), _data_iso(ecc.get("data"))
    if not imp or imp <= 0 or not data:
        raise ErrorePosizione("ECCEDENZA_INCOMPLETA", "L'eccedenza non ha importo o data")
    dip_id = ecc["dipendente_id"]
    anno = _intero(dati.get("anno")) or int(data[:4])
    mese = _intero(dati.get("mese")) or int(data[5:7])
    if not (1 <= mese <= 14) or anno < 2000:
        raise ErrorePosizione("PERIODO_NON_VALIDO", "mese 1-14 e anno >= 2000", {"anno": anno, "mese": mese})
    ora = _adesso()
    riferimento: Dict[str, Any]

    if destinazione == "bonus":
        conc = await db[COLL_CONCILIAZIONI].find_one({"id": ecc.get("conciliazione_id")}, {"_id": 0, "file_data": 0})
        if not conc or conc.get("annullata"):
            raise ErrorePosizione("CONCILIAZIONE_NON_TROVATA", "Conciliazione non trovata o annullata")
        residuo = residuo_parte(conc, "bonus")
        if residuo is None or residuo < imp:
            raise ErrorePosizione("OLTRE_BONUS", "Il bonus della conciliazione non copre l'eccedenza al centesimo",
                                  {"residuo_bonus": _txt(residuo), "eccedenza": _txt(imp)})
        pag = normalizza_pagamento({"data": data, "importo": imp, "parte": "bonus",
                                    "modalita": ecc.get("modalita") or "bonifico",
                                    "origine": "eccedenza_attribuita",
                                    "movimento_id": ecc.get("movimento_id"),
                                    "nota": "eccedenza attribuita dal titolare"}, conc)
        pag["eccedenza_id"] = eccedenza_id
        pagamenti = list(conc.get("pagamenti") or []) + [pag]
        conc["pagamenti"] = pagamenti
        await db[COLL_CONCILIAZIONI].update_one(
            {"id": conc["id"]}, {"$set": {"pagamenti": pagamenti, "stato": stato_conciliazione(conc),
                                          "updated_at": ora}})
        riferimento = {"conciliazione_id": conc["id"], "pagamento_id": pag["id"]}
    elif destinazione == "acconto":
        dip = await db.dipendenti.find_one({"id": dip_id}, {"_id": 0, "nome_completo": 1}) or {}
        acconto = {
            "id": str(uuid.uuid4()), "dipendente_id": dip_id, "dipendente_nome": dip.get("nome_completo", ""),
            "tipo": "stipendio", "importo": float(imp), "data": data,
            "anno": int(data[:4]), "mese": int(data[5:7]),
            "note": "eccedenza del pagamento di conciliazione, attribuita dal titolare",
            "natura_acconto": "su_futuro", "tipo_bonifico": "standard",
            "scalato_su_anno_mese": "%04d-%02d" % (anno, mese),
            "stato": "registrato", "movimento_bancario_id": ecc.get("movimento_id"), "riconciliato_il": None,
            "cedolino_id": None, "importo_scalato_effettivo": None,
            "source": "eccedenze_pagamenti", "eccedenza_id": eccedenza_id,
            "created_at": ora, "updated_at": ora,
        }
        await db.acconti_dipendenti.insert_one(dict(acconto))
        riferimento = {"acconto_id": acconto["id"], "anno": anno, "mese": mese}
    else:
        dip = await db.dipendenti.find_one({"id": dip_id}, {"_id": 0, "nome_completo": 1}) or {}
        key = f"eccedenza:{eccedenza_id}"
        esito = {"key": key, "cro": None, "dipendente_id": dip_id, "data": data, "importo": float(imp),
                 "causale": "Eccedenza del pagamento di conciliazione attribuita a stipendio",
                 "beneficiario": dip.get("nome_completo"), "mese": mese, "anno": anno,
                 "origine": "eccedenze_pagamenti", "eccedenza_id": eccedenza_id,
                 "bonifico_da_associare_id": ecc.get("bonifico_da_associare_id")}
        await db.pagamenti_esiti.update_one({"key": key}, {"$set": esito}, upsert=True)
        await db.paghe_mensili.update_one(
            {"dipendente_id": dip_id, "anno": anno, "mese": mese},
            {"$set": {"dipendente_id": dip_id, "anno": anno, "mese": mese, "updated_at": ora}}, upsert=True)
        riferimento = {"key": key, "anno": anno, "mese": mese}

    if destinazione in ("stipendio", "acconto"):
        # lo stato del mese segue subito (motore unico delle paghe)
        from app.hr.routers.dipendenti_cloud import _ricalcola_bonifico_periodo, _ricalcola_stato_paga

        if destinazione == "stipendio":
            await _ricalcola_bonifico_periodo(db, dip_id, anno, mese)
        else:
            await _ricalcola_stato_paga(db, dip_id, anno, mese)

    agg = {"stato": ECCEDENZA_ATTRIBUITA, "attribuita_a": destinazione, "attribuita_il": ora,
           "attribuita_da": attore, "riferimento": riferimento, "updated_at": ora,
           "storico": list(ecc.get("storico") or []) + [{"azione": "attribuisci", "destinazione": destinazione,
                                                          "da": attore, "il": ora, **riferimento}]}
    await db[COLL_ECCEDENZE].update_one({"id": eccedenza_id}, {"$set": agg})
    ecc.update(agg)
    return vista_eccedenza(ecc)


#: Campi che il titolare puo' correggere su un pagamento scritto da lui.
CAMPI_PAGAMENTO_MODIFICABILI = ("data", "importo", "parte", "modalita", "nota")


def pagamento_modificabile(pag: Dict[str, Any]) -> bool:
    """Contanti e pagamenti scritti a mano si correggono; un pagamento provato
    da un bonifico ha la data e l'importo della banca, e quelli non si toccano."""
    return pag.get("origine") == "manuale" or pag.get("modalita") == "contanti"


async def modifica_pagamento(db, conciliazione_id: str, pagamento_id: str,
                             dati: Dict[str, Any]) -> Dict[str, Any]:
    """Corregge un pagamento della conciliazione; il valore di prima resta in ``storico``."""
    conc = await db[COLL_CONCILIAZIONI].find_one({"id": conciliazione_id}, {"_id": 0, "file_data": 0})
    if not conc or conc.get("annullata"):
        raise ErrorePosizione("CONCILIAZIONE_NON_TROVATA", "Conciliazione non trovata o annullata")
    pagamenti = list(conc.get("pagamenti") or [])
    idx = next((i for i, p in enumerate(pagamenti) if p.get("id") == pagamento_id), None)
    if idx is None:
        raise ErrorePosizione("PAGAMENTO_NON_TROVATO", "Pagamento non trovato")
    vecchio = pagamenti[idx]
    if not pagamento_modificabile(vecchio):
        raise ErrorePosizione("PAGAMENTO_DA_BANCA",
                              "Un pagamento provato da un bonifico tiene la data e l'importo della banca",
                              {"origine": vecchio.get("origine")})
    unito = {**{k: vecchio.get(k) for k in CAMPI_PAGAMENTO_MODIFICABILI},
             **{k: v for k, v in dati.items() if k in CAMPI_PAGAMENTO_MODIFICABILI}}
    nuovo = normalizza_pagamento({**vecchio, **unito, "id": vecchio["id"]}, conc)
    nuovo["origine"] = vecchio.get("origine")
    prima = {k: vecchio.get(k) for k in CAMPI_PAGAMENTO_MODIFICABILI}
    if prima != {k: nuovo.get(k) for k in CAMPI_PAGAMENTO_MODIFICABILI}:
        nuovo["storico"] = list(vecchio.get("storico") or []) + [{"prima": prima, "modificato_il": _adesso()}]
    else:
        nuovo["storico"] = list(vecchio.get("storico") or [])
    pagamenti[idx] = nuovo
    conc["pagamenti"] = pagamenti
    agg = {"pagamenti": pagamenti, "stato": stato_conciliazione(conc), "updated_at": _adesso()}
    await db[COLL_CONCILIAZIONI].update_one({"id": conciliazione_id}, {"$set": agg})
    conc.update(agg)
    return vista_conciliazione(conc)


def acconti_registro_del_mese(acconti: Iterable[Dict[str, Any]], anno: int, mese: int,
                              acconti_in_busta: Iterable[Dict[str, Any]] = ()) -> Decimal:
    """Quanto del registro acconti (``acconti_dipendenti``) la busta di quel mese ha gia' avuto.

    Gli stessi criteri della posizione (``componi_movimenti``): un acconto e' un
    pagamento, conta se e' di stipendio (``TIPI_ACCONTO_STIPENDIO``), non e'
    annullato, ha una data valida e la sua competenza (``scalato_su_anno_mese``,
    altrimenti il mese della data) e' questa busta; lo stesso (data, importo)
    gia' scritto fra gli acconti in contanti del registro paghe non si conta due
    volte. Lo stato del mese (``paghe_mensili``) e la posizione devono dire la
    stessa cosa: senza questo una busta chiusa dalla posizione restava «parziale»."""
    if not 1 <= int(mese) <= 12:
        return ZERO
    visti = {(_data_iso(a.get("data")), importo(a.get("importo"))) for a in acconti_in_busta}
    totale = ZERO
    for acc in acconti:
        if str(acc.get("tipo") or "") not in TIPI_ACCONTO_STIPENDIO or acc.get("stato") == "annullato":
            continue
        imp, data = importo(acc.get("importo")), _data_iso(acc.get("data"))
        if not imp or imp <= 0 or not data or (data, imp) in visti:
            continue
        comp = str(acc.get("scalato_su_anno_mese") or data[:7])
        if (_intero(comp[:4]), _intero(comp[5:7])) != (int(anno), int(mese)):
            continue
        visti.add((data, imp))
        totale += imp
    return totale


async def registra_acconto_da_coda(db, in_coda: Dict[str, Any], dip: Dict[str, Any],
                                   anno: int, mese: int) -> Dict[str, Any]:
    """Un bonifico della coda che e' un acconto: va nel registro unico degli
    acconti (``acconti_dipendenti``), mai in ``pagamenti_esiti`` — la busta del
    mese lo recupera, e sommarlo li' lo conterebbe due volte."""
    esistente = await db.acconti_dipendenti.find_one({"bonifico_da_associare_id": in_coda["id"]}, {"_id": 0})
    if esistente:
        return esistente
    data = _data_iso(in_coda.get("data"))
    imp = importo(in_coda.get("importo"))
    if not data or not imp or imp <= 0:
        raise ErrorePosizione("BONIFICO_INCOMPLETO", "Il bonifico in coda non ha data o importo")
    ora = _adesso()
    acconto = {
        "id": str(uuid.uuid4()), "dipendente_id": dip["id"], "dipendente_nome": dip.get("nome_completo", ""),
        "tipo": "stipendio", "importo": float(imp), "data": data,
        "anno": int(data[:4]), "mese": int(data[5:7]), "note": in_coda.get("causale") or "",
        "natura_acconto": "su_futuro", "tipo_bonifico": "standard",
        "scalato_su_anno_mese": "%04d-%02d" % (int(anno), int(mese)),
        "stato": "registrato", "movimento_bancario_id": None, "riconciliato_il": None,
        "cedolino_id": None, "importo_scalato_effettivo": None,
        "source": "bonifici_da_associare", "bonifico_da_associare_id": in_coda["id"],
        "created_at": ora, "updated_at": ora,
    }
    await db.acconti_dipendenti.insert_one(dict(acconto))
    return acconto


def _archivio():
    from app.database import Database
    from app.services.blob_store import blob_store_per_runtime

    return blob_store_per_runtime(Database.db)


def mime_documento(nome: str) -> Optional[str]:
    nome = str(nome or "").lower()
    for est, mime in MIME_DOCUMENTO.items():
        if nome.endswith(est):
            return mime
    return None


async def salva_documento(db, conciliazione_id: str, nome: str, contenuto: bytes) -> Dict[str, Any]:
    """Il verbale originale in ``gestionale.blobs`` (chiave SHA-256); sulla
    conciliazione restano impronta, nome e chiave. Un documento sostituito non
    si cancella: resta nell'archivio dei blob, citato dallo ``storico_documenti``."""
    conc = await db[COLL_CONCILIAZIONI].find_one({"id": conciliazione_id}, {"_id": 0, "file_data": 0})
    if not conc:
        raise ErrorePosizione("CONCILIAZIONE_NON_TROVATA", "Conciliazione non trovata")
    mime = mime_documento(nome)
    if not mime:
        raise ErrorePosizione("FORMATO_NON_AMMESSO", "Formato ammesso: PDF, DOCX, DOC, JPG, PNG")
    if not contenuto or len(contenuto) > DOCUMENTO_MAX_BYTE:
        raise ErrorePosizione("DIMENSIONE_NON_AMMESSA", "File vuoto o oltre 15 MB")
    impronta = hashlib.sha256(contenuto).hexdigest()
    dati = base64.b64encode(contenuto).decode("ascii")
    documento = {"sha256": impronta, "nome": nome, "mime": mime, "dimensione": len(contenuto),
                 "caricato_il": _adesso()}
    agg: Dict[str, Any] = {"updated_at": _adesso()}
    archivio = _archivio()
    if getattr(archivio, "persistent", False):
        documento["blob_key"] = PREFISSO_BLOB + impronta
        await archivio.put(documento["blob_key"], dati)
    else:
        # Senza Supabase (test, sviluppo) il contenuto resta nella riga, nel
        # campo pesante che la cache dell'adattatore HR non tiene in memoria.
        agg["file_data"] = dati
    precedente = conc.get("documento")
    if precedente and precedente.get("sha256") != impronta:
        agg["storico_documenti"] = list(conc.get("storico_documenti") or []) + [precedente]
    agg["documento"] = documento
    await db[COLL_CONCILIAZIONI].update_one({"id": conciliazione_id}, {"$set": agg})
    return documento


async def leggi_documento(db, conciliazione_id: str) -> Optional[Tuple[bytes, str, str]]:
    conc = await db[COLL_CONCILIAZIONI].find_one({"id": conciliazione_id}, {"_id": 0})
    doc = (conc or {}).get("documento")
    if not doc:
        return None
    dati = conc.get("file_data") if not doc.get("blob_key") else await _archivio().get(doc["blob_key"])
    if not dati:
        return None
    return base64.b64decode(dati), doc.get("nome") or "conciliazione.pdf", doc.get("mime") or "application/pdf"


def vocabolari() -> Dict[str, Any]:
    """Le tendine della pagina: un solo posto per le scelte ammesse."""
    lista = lambda d: [{"id": k, "label": v} for k, v in d.items()]  # noqa: E731
    return {"voci": lista(VOCI_CONCILIAZIONE), "tipi": lista(TIPI_CONCILIAZIONE),
            "modalita": lista(MODALITA_PAGAMENTO), "parti": lista(PARTI_PAGAMENTO),
            "tipi_bonifico_coda": lista(TIPI_BONIFICO_CODA), "voce_bonus": VOCE_BONUS,
            "destinazioni_eccedenza": lista(DESTINAZIONI_ECCEDENZA),
            "valuta": VALUTA}
