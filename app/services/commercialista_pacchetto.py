"""Il pacchetto mensile per il commercialista: periodo, voci, allegati.

Un solo posto per:

* il **periodo** (``intervallo_periodo``): mese, trimestre, anno o intervallo libero, sempre
  come ``dal``/``al`` ISO. ``mese=0`` resta «intero anno», come nelle rotte ``/{anno}/{mese}``;
* le **voci** (``VOCI``): ognuna legge la sua fonte canonica con proiezioni senza payload e
  restituisce la stessa struttura (stato, conteggio, totale, sezioni con colonne e righe);
* gli **allegati** di ogni voce (PDF dal generatore unico ``commercialista_pdf``; per le
  presenze il PDF/CSV di HR).

Non inventa numeri: una fonte assente o illeggibile e' «Non disponibile» col motivo, una voce
senza righe e' «Vuota», una voce con righe ma con qualcosa che manca e' «Incompleta» e dice
cosa. Gli importi sono ``Decimal``; le date dell'interfaccia sono gg/mm/aaaa.
"""
from __future__ import annotations

import asyncio
import calendar
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

MESI_NOMI = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
             "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
MAX_GIORNI_PERIODO = 400
MAX_RIGHE = 20000
GIORNI_ATTESA_RT = 2  # come completezza_commercialista: l'XML dell'RT arriva la sera dopo

STATO_PRONTO = "pronto"
STATO_INCOMPLETO = "incompleto"
STATO_VUOTO = "vuoto"
STATO_NON_DISPONIBILE = "non_disponibile"
STATO_DA_INVIARE = "da_inviare"
STATO_GIA_INVIATO = "gia_inviato"
STATI_INVIABILI = (STATO_PRONTO, STATO_INCOMPLETO, STATO_DA_INVIARE, STATO_GIA_INVIATO)

_VALIDI = {"entity_status": {"$ne": "deleted"},
           "status": {"$nin": ["deleted", "archived", "archiviata"]}}


# ---------------------------------------------------------------------------
# Periodo
# ---------------------------------------------------------------------------

def it_data(valore: Any) -> str:
    """``2026-09-30`` (o data ISO con ora) -> ``30/09/2026``; vuoto resta vuoto."""
    testo = str(valore or "")[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", testo):
        return f"{testo[8:10]}/{testo[5:7]}/{testo[:4]}"
    return testo


@dataclass(frozen=True)
class Periodo:
    dal: str
    al: str
    etichetta: str

    def filtro(self, campo: str = "data") -> Dict[str, Any]:
        """Filtro sul campo data (stringa ISO, con o senza ora): ``al`` incluso."""
        return {campo: {"$gte": self.dal, "$lte": self.al + "~"}}

    def contiene(self, valore: Any) -> bool:
        giorno = str(valore or "")[:10]
        return self.dal <= giorno <= self.al

    @property
    def anni(self) -> List[int]:
        return list(range(int(self.dal[:4]), int(self.al[:4]) + 1))

    def mesi(self) -> List[Tuple[int, int]]:
        """I mesi (anno, mese) toccati dal periodo, dal primo all'ultimo."""
        a, m = int(self.dal[:4]), int(self.dal[5:7])
        fine = (int(self.al[:4]), int(self.al[5:7]))
        out = []
        while (a, m) <= fine:
            out.append((a, m))
            a, m = (a + 1, 1) if m == 12 else (a, m + 1)
        return out

    def al_dovuto(self, oggi: Optional[date] = None) -> str:
        """Ultimo giorno gia' dovuto: l'XML di ieri e di oggi non e' ancora arrivato."""
        limite = ((oggi or date.today()) - timedelta(days=GIORNI_ATTESA_RT)).isoformat()
        return min(self.al, limite)


def _etichetta_intervallo(dal: date, al: date) -> str:
    ultimo = calendar.monthrange(al.year, al.month)[1]
    if dal.year == al.year and dal.month == al.month and dal.day == 1 and al.day == ultimo:
        return f"{MESI_NOMI[dal.month]} {dal.year}"
    if dal.year == al.year and (dal.month, dal.day) == (1, 1) and (al.month, al.day) == (12, 31):
        return f"Intero anno {dal.year}"
    if dal.year == al.year and dal.day == 1 and al.day == ultimo and dal.month % 3 == 1 \
            and al.month == dal.month + 2:
        return f"{(dal.month - 1) // 3 + 1}° trimestre {dal.year}"
    return f"dal {it_data(dal.isoformat())} al {it_data(al.isoformat())}"


def intervallo_periodo(anno: Optional[int] = None, mese: Optional[int] = None,
                       dal: Optional[str] = None, al: Optional[str] = None) -> Periodo:
    """Il periodo scelto: ``dal``/``al`` ISO se dati, altrimenti ``anno``/``mese`` (0 = anno intero).

    Solleva ``ValueError`` con un messaggio leggibile se il periodo non e' valido.
    """
    if dal or al:
        if not (dal and al):
            raise ValueError("Servono sia la data di inizio sia quella di fine")
        try:
            d1, d2 = date.fromisoformat(str(dal)[:10]), date.fromisoformat(str(al)[:10])
        except ValueError as exc:
            raise ValueError("Date non valide: formato atteso aaaa-mm-gg") from exc
        if d1 > d2:
            raise ValueError("La data di inizio e' dopo quella di fine")
        if (d2 - d1).days > MAX_GIORNI_PERIODO:
            raise ValueError(f"Periodo troppo lungo (massimo {MAX_GIORNI_PERIODO} giorni)")
        return Periodo(d1.isoformat(), d2.isoformat(), _etichetta_intervallo(d1, d2))
    if not anno:
        raise ValueError("Anno mancante")
    mese = int(mese or 0)
    if mese < 0 or mese > 12:
        raise ValueError("Mese deve essere tra 0 e 12")
    if mese == 0:
        return Periodo(f"{anno}-01-01", f"{anno}-12-31", f"Intero anno {anno}")
    ultimo = calendar.monthrange(anno, mese)[1]
    return Periodo(f"{anno}-{mese:02d}-01", f"{anno}-{mese:02d}-{ultimo:02d}", f"{MESI_NOMI[mese]} {anno}")


# ---------------------------------------------------------------------------
# Numeri e testi
# ---------------------------------------------------------------------------

def dec(valore: Any) -> Optional[Decimal]:
    """Numero tollerante (``1.234,56``, ``12.5``, ``None``); None se non e' un numero."""
    if valore is None or valore == "" or isinstance(valore, bool):
        return None
    if isinstance(valore, Decimal):
        return valore
    testo = str(valore).strip().replace("€", "").replace(" ", "")
    if "," in testo:
        testo = testo.replace(".", "").replace(",", ".")
    try:
        return Decimal(testo)
    except (InvalidOperation, ValueError):
        return None


def euro(valore: Optional[Decimal]) -> str:
    """``1234.5`` -> ``1.234,50``; None resta vuoto (mai uno zero di comodo)."""
    if valore is None:
        return ""
    q = valore.quantize(Decimal("0.01"))
    intero, _, decimali = f"{abs(q):.2f}".partition(".")
    gruppi = f"{int(intero):,}".replace(",", ".")
    return f"{'-' if q < 0 else ''}{gruppi},{decimali}"


def _somma(valori: Sequence[Optional[Decimal]]) -> Decimal:
    return sum((v for v in valori if v is not None), Decimal("0"))


def _troncato(testo: Any, n: int) -> str:
    t = " ".join(str(testo or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def iban_mascherato(iban: Any) -> str:
    """Solo le ultime quattro cifre: l'IBAN intero non esce mai dal gestionale."""
    testo = re.sub(r"\s+", "", str(iban or ""))
    return f"****{testo[-4:]}" if len(testo) >= 8 else ""


def _slug(testo: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", testo).strip("_")


# ---------------------------------------------------------------------------
# Struttura di una voce
# ---------------------------------------------------------------------------

def _sezione(titolo: str, colonne: List[str], allinea: List[str], righe: List[List[str]],
             totali: Optional[List[List[str]]] = None, pesi: Optional[List[int]] = None) -> Dict[str, Any]:
    return {"titolo": titolo, "colonne": colonne, "allinea": allinea, "righe": righe,
            "totali": totali or [], "pesi": pesi}


def _voce(voce: str, titolo: str, sezioni: List[Dict[str, Any]], *, totale: Optional[Decimal] = None,
          riepilogo: Optional[List[List[str]]] = None, avvisi: Optional[List[str]] = None,
          fonte: str = "") -> Dict[str, Any]:
    conteggio = sum(len(s["righe"]) for s in sezioni)
    avvisi = [a for a in (avvisi or []) if a]
    if not conteggio:
        stato = STATO_VUOTO
        motivo = "; ".join(avvisi) or "Nessun dato nel periodo"
    elif avvisi:
        stato, motivo = STATO_INCOMPLETO, "; ".join(avvisi)
    else:
        stato, motivo = STATO_PRONTO, None
    return {"voce": voce, "titolo": titolo, "stato": stato, "motivo": motivo, "conteggio": conteggio,
            "totale": euro(totale) if (totale is not None and conteggio) else None,
            "riepilogo": riepilogo or [],
            "avvisi": avvisi, "sezioni": sezioni, "fonte": fonte}


def voce_non_disponibile(voce: str, titolo: str, motivo: str) -> Dict[str, Any]:
    return {"voce": voce, "titolo": titolo, "stato": STATO_NON_DISPONIBILE, "motivo": motivo,
            "conteggio": 0, "totale": None, "riepilogo": [], "avvisi": [], "sezioni": [], "fonte": ""}


def _verso(movimento: Dict[str, Any]) -> Tuple[str, Optional[Decimal]]:
    """(``entrata``|``uscita``, importo positivo). Il verso e' ``tipo``, altrimenti il segno."""
    importo = dec(movimento.get("importo") if movimento.get("importo") is not None
                  else movimento.get("amount"))
    tipo = str(movimento.get("tipo") or movimento.get("type") or "").strip().lower()
    if importo is None:
        return ("entrata" if tipo in ("entrata", "income", "in") else "uscita"), None
    if tipo in ("entrata", "income", "in"):
        return "entrata", abs(importo)
    if tipo in ("uscita", "expense", "out"):
        return "uscita", abs(importo)
    return ("uscita", abs(importo)) if importo < 0 else ("entrata", importo)


def _testata_movimenti(movimenti: List[Dict[str, Any]]):
    """Somma entrate e uscite di righe con verso; restituisce (entrate, uscite, senza_importo)."""
    entrate = uscite = Decimal("0")
    senza = 0
    for m in movimenti:
        verso, importo = _verso(m)
        if importo is None:
            senza += 1
        elif verso == "entrata":
            entrate += importo
        else:
            uscite += importo
    return entrate, uscite, senza


# ---------------------------------------------------------------------------
# Prima Nota Cassa e fatture pagate per cassa
# ---------------------------------------------------------------------------

async def movimenti_cassa(db, p: Periodo) -> List[Dict[str, Any]]:
    """Righe di Prima Nota Cassa del periodo (ordine: data, poi categoria)."""
    righe = await db["prima_nota_cassa"].find(p.filtro("data"), {"_id": 0}).sort(
        [("data", 1), ("categoria", 1)]).to_list(5000)
    if not righe:
        righe = await db["prima_nota_cassa"].find(
            {"tipo_conto": "cassa", "$or": [p.filtro("data"), p.filtro("date")]}, {"_id": 0},
        ).sort([("data", 1), ("categoria", 1)]).to_list(5000)
    return righe


async def voce_prima_nota_cassa(db, p: Periodo, opz: Dict[str, Any]) -> Dict[str, Any]:
    movimenti = await movimenti_cassa(db, p)
    entrate, uscite, senza = _testata_movimenti(movimenti)
    righe = []
    for m in movimenti:
        verso, importo = _verso(m)
        righe.append([it_data(m.get("data") or m.get("date")),
                      _troncato(m.get("descrizione") or m.get("causale") or m.get("description"), 80),
                      str(m.get("categoria") or m.get("category") or ""),
                      euro(importo) if verso == "entrata" else "",
                      euro(importo) if verso == "uscita" else ""])
    saldo = entrate - uscite
    totali = [["Totale entrate", euro(entrate)], ["Totale uscite", euro(uscite)],
              ["Saldo del periodo", euro(saldo)]]
    sez = _sezione("", ["Data", "Descrizione", "Categoria", "Entrate", "Uscite"],
                   ["l", "l", "l", "r", "r"], righe, totali, [10, 42, 20, 14, 14])
    return _voce("prima_nota_cassa", "Prima Nota Cassa", [sez], totale=saldo, riepilogo=totali,
                 avvisi=[f"{senza} movimenti senza importo" if senza else ""], fonte="prima_nota_cassa")


_PROIEZIONE_FATTURA_CASSA = {
    "_id": 0, "id": 1, "invoice_number": 1, "numero_fattura": 1, "invoice_date": 1,
    "data_fattura": 1, "supplier_name": 1, "cedente_denominazione": 1,
    "supplier_vat": 1, "total_amount": 1, "importo_totale": 1, "tipo_documento": 1,
}


async def fatture_pagate_in_cassa(db, p: Periodo) -> list:
    """Fatture pagate per cassa nel periodo: le righe ATTIVE di Prima Nota Cassa in uscita
    collegate a una fattura (``fattura_id``), per data del pagamento. Le righe di ripiego
    senza prova (``SOURCES_ESCLUSE``, es. la cassa d'ufficio
    ``metodo_fornitore_assente_provvisorio``) non sono un pagamento."""
    from app.constants.fattura_attiva import FILTRO_FATTURA_ATTIVA
    from app.routers.prima_nota_module.common import SOURCES_ESCLUSE

    righe = await db["prima_nota_cassa"].find({
        **p.filtro("data"),
        "tipo": "uscita",
        "fattura_id": {"$nin": [None, ""]},
        "status": {"$nin": ["deleted", "archived"]},
        "entity_status": {"$ne": "deleted"},
        "source": {"$nin": SOURCES_ESCLUSE},
    }, {"_id": 0, "id": 1, "fattura_id": 1, "data": 1, "importo": 1}).to_list(20000)

    per_fattura: Dict[str, Dict[str, Any]] = {}
    for riga in righe:
        voce = per_fattura.setdefault(str(riga["fattura_id"]), {"importo": 0.0, "date": [], "righe": []})
        voce["importo"] += abs(float(riga.get("importo") or 0))
        voce["date"].append(str(riga.get("data") or "")[:10])
        voce["righe"].append(riga.get("id"))
    if not per_fattura:
        return []
    fatture = await db["invoices"].find(
        {"id": {"$in": list(per_fattura)}, **FILTRO_FATTURA_ATTIVA},
        _PROIEZIONE_FATTURA_CASSA,
    ).to_list(len(per_fattura))
    esito = []
    for fattura in fatture:
        pagamento = per_fattura[str(fattura["id"])]
        esito.append({
            **fattura,
            "data_pagamento": max(pagamento["date"]),
            "importo_pagato_cassa": round(pagamento["importo"], 2),
            "prima_nota_cassa_ids": pagamento["righe"],
        })
    esito.sort(key=lambda f: (f["data_pagamento"], str(f.get("invoice_number") or "")))
    return esito


async def voce_fatture_cassa(db, p: Periodo, opz: Dict[str, Any]) -> Dict[str, Any]:
    fatture = await fatture_pagate_in_cassa(db, p)
    righe = [[it_data(f["data_pagamento"]),
              str(f.get("invoice_number") or f.get("numero_fattura") or ""),
              it_data(f.get("invoice_date") or f.get("data_fattura")),
              _troncato(f.get("supplier_name") or f.get("cedente_denominazione"), 44),
              euro(dec(f["importo_pagato_cassa"]))] for f in fatture]
    totale = _somma([dec(f["importo_pagato_cassa"]) for f in fatture])
    sez = _sezione("", ["Pagata il", "N. fattura", "Data fattura", "Fornitore", "Pagato in cassa"],
                   ["l", "l", "l", "l", "r"], righe, [["Totale pagato in cassa", euro(totale)]],
                   [10, 14, 12, 40, 16])
    return _voce("fatture_cassa", "Fatture pagate per cassa", [sez], totale=totale,
                 riepilogo=[["Fatture", str(len(righe))], ["Totale", euro(totale)]],
                 fonte="prima_nota_cassa")


# ---------------------------------------------------------------------------
# Carnet assegni
# ---------------------------------------------------------------------------

DA_COLLEGARE = "Da collegare"


def dati_riga_assegno(a: Dict[str, Any]) -> Dict[str, str]:
    """Fornitore, numero e data fattura di un assegno gia' arricchito dalla lista assegni.

    Il beneficiario non e' una colonna: e' il ripiego del fornitore. Cio' che manca resta
    «Da collegare»: nessun collegamento si fa qui (identita' + importo al centesimo sono
    del motore assegni).
    """
    dettaglio = a.get("fatture_dettaglio") or []
    date_fattura = list(dict.fromkeys(
        it_data(d.get("data_fattura")) for d in dettaglio if d.get("data_fattura")))
    data_fattura = it_data(a.get("data_fattura")) or ", ".join(date_fattura)
    fornitore = (a.get("fornitore_fattura") or a.get("fornitore_ragione_sociale")
                 or a.get("beneficiario") or "")
    numero = a.get("numero_fattura") or a.get("fattura_numero") or ""
    return {"fornitore": str(fornitore).strip() or DA_COLLEGARE,
            "numero_fattura": str(numero).strip() or DA_COLLEGARE,
            "data_fattura": data_fattura or DA_COLLEGARE}


def assegno_senza_fattura(a: Dict[str, Any]) -> bool:
    return dati_riga_assegno(a)["numero_fattura"] == DA_COLLEGARE


async def _assegni_arricchiti(anni: Sequence[int]) -> List[Dict[str, Any]]:
    """La lista assegni del gestionale (con fornitore e fattura dedotti), anno per anno."""
    from app.routers.bank.assegni import list_assegni

    visti, out = set(), []
    for anno in anni:
        for a in await list_assegni(skip=0, limit=1000, stato=None, fornitore_piva=None,
                                    search=None, anno=anno):
            chiave = a.get("id") or a.get("numero")
            if chiave in visti:
                continue
            visti.add(chiave)
            out.append(a)
    return out


def carnet_id_assegno(a: Dict[str, Any]) -> str:
    """Il carnet come lo raggruppa la pagina: le prime 8 cifre del numero."""
    return (str(a.get("numero") or a.get("numero_assegno") or "")[:8]) or "Sconosciuto"


async def voce_carnet(db, p: Periodo, opz: Dict[str, Any]) -> Dict[str, Any]:
    from app.constants.stati_assegno import STATI_DISPONIBILI

    ids = [str(i) for i in (opz.get("carnet_ids") or [])]
    if ids:
        assegni = [a for a in await _assegni_arricchiti(p.anni) if carnet_id_assegno(a) in ids]
        titolo = "Carnet assegni " + ", ".join(ids)
    else:
        assegni = [a for a in await _assegni_arricchiti(p.anni)
                   if a.get("stato") not in STATI_DISPONIBILI and p.contiene(a.get("data_emissione"))]
        titolo = "Assegni emessi"
    assegni.sort(key=lambda a: (carnet_id_assegno(a), str(a.get("numero") or "")))
    righe, senza = [], 0
    for a in assegni:
        d = dati_riga_assegno(a)
        senza += d["numero_fattura"] == DA_COLLEGARE
        data = a.get("data_emissione") or a.get("data_incasso") or a.get("data_fattura")
        righe.append([str(a.get("numero") or ""), it_data(data), _troncato(d["fornitore"], 40),
                      _troncato(d["numero_fattura"], 24), d["data_fattura"],
                      euro(dec(a.get("importo"))), str(a.get("stato") or "")])
    totale = _somma([dec(a.get("importo")) for a in assegni])
    sez = _sezione("", ["N. assegno", "Data", "Fornitore", "N. fattura", "Data fattura", "Importo", "Stato"],
                   ["l", "l", "l", "l", "l", "r", "l"], righe, [["Totale assegni", euro(totale)]],
                   [14, 10, 30, 16, 12, 12, 10])
    return _voce("carnet_assegni", titolo, [sez], totale=totale,
                 riepilogo=[["Assegni", str(len(righe))], ["Totale", euro(totale)]],
                 avvisi=[f"{senza} assegn{'o' if senza == 1 else 'i'} senza fattura collegata" if senza else ""],
                 fonte="assegni")


# ---------------------------------------------------------------------------
# Banca (estratto conto BPM)
# ---------------------------------------------------------------------------

async def voce_banca(db, p: Periodo, opz: Dict[str, Any]) -> Dict[str, Any]:
    from app.services import conti_pos
    from app.services.completezza_commercialista import copertura_estratto_bpm

    movimenti = await db["estratto_conto_movimenti"].find(
        {**p.filtro("data"), **_VALIDI},
        {"_id": 0, "id": 1, "data": 1, "descrizione": 1, "descrizione_originale": 1, "causale": 1,
         "importo": 1, "tipo": 1, "categoria": 1, "conto_contabile": 1,
         "evidenza_bancaria_ufficiale": 1, "in_attesa_estratto_ufficiale": 1},
    ).sort([("data", 1)]).to_list(MAX_RIGHE)
    # Il conto della pagina e' la banca (BPM): le altre carte hanno il loro estratto.
    movimenti = [m for m in movimenti if m.get("conto_contabile") in (None, "", conti_pos.CONTO_BPM)]
    def provvisorio(m):
        return m.get("in_attesa_estratto_ufficiale") is True or m.get("evidenza_bancaria_ufficiale") is not True

    provvisori = [m for m in movimenti if provvisorio(m)]
    righe = []
    for m in movimenti:
        verso, importo = _verso(m)
        ufficiale = not provvisorio(m)
        righe.append([it_data(m.get("data")),
                      _troncato(m.get("descrizione_originale") or m.get("descrizione") or m.get("causale"), 90),
                      str(m.get("categoria") or ""),
                      euro(importo) if verso == "entrata" else "",
                      euro(importo) if verso == "uscita" else "",
                      "Ufficiale" if ufficiale else "Provvisorio"])
    entrate, uscite, senza = _testata_movimenti(movimenti)
    saldo = entrate - uscite
    totali = [["Totale entrate", euro(entrate)], ["Totale uscite", euro(uscite)],
              ["Saldo del periodo", euro(saldo)]]
    avvisi = []
    if provvisori and movimenti:
        avvisi.append(f"{len(provvisori)} movimenti su {len(movimenti)} non sono ancora nell'estratto conto ufficiale")
    if senza:
        avvisi.append(f"{senza} movimenti senza importo")
    copertura = await copertura_estratto_bpm(db, p.dal, p.al_dovuto())
    if p.dal <= p.al_dovuto() and not copertura["completo"]:
        if copertura["movimenti"]:
            avvisi.append(f"L'estratto conto copre solo dal {it_data(copertura['primo'])} "
                          f"al {it_data(copertura['ultimo'])}")
        else:
            avvisi.append("Nessun movimento nel periodo: estratto conto da caricare")
    sez = _sezione("", ["Data", "Causale", "Categoria", "Entrate", "Uscite", "Stato"],
                   ["l", "l", "l", "r", "r", "l"], righe, totali, [9, 44, 16, 12, 12, 10])
    return _voce("banca", "Banca (conto BPM)", [sez], totale=saldo, riepilogo=totali, avvisi=avvisi,
                 fonte="estratto_conto_movimenti")


# ---------------------------------------------------------------------------
# PayPal
# ---------------------------------------------------------------------------

async def voce_paypal(db, p: Periodo, opz: Dict[str, Any]) -> Dict[str, Any]:
    from app.routers.paypal_statements import get_paypal_transactions

    mesi = p.mesi()
    chiamate = [(mesi[0][0], mesi[0][1])] if len(mesi) == 1 else [(a, None) for a in p.anni]
    tutte, troncato = [], False
    for anno, mese in chiamate:
        esito = await get_paypal_transactions(anno=anno, mese=mese, tipo=None, solo_pagamenti=False,
                                              limit=2000)
        troncato = troncato or len(esito["transactions"]) >= 2000
        tutte.extend(t for t in esito["transactions"]
                     if p.contiene(t.get("data")) and not t.get("is_conversione"))
    tutte.sort(key=lambda t: str(t.get("data") or ""))
    righe, estere, entrate, uscite = [], 0, Decimal("0"), Decimal("0")
    for t in tutte:
        valuta = t.get("valuta_originale") or t.get("currency")
        importo = dec(t["importo_eur"]) if t.get("importo_eur") is not None else (
            dec(t.get("lordo")) if not valuta or valuta == "EUR" else None)
        if importo is None:
            estere += 1
        elif importo >= 0:
            entrate += importo
        else:
            uscite += abs(importo)
        collegamento = str(t.get("stato_collegamento_fattura") or "")
        righe.append([it_data(t.get("data")),
                      _troncato(t.get("nome_controparte"), 36),
                      _troncato(t.get("descrizione"), 50),
                      euro(importo) if importo is not None and importo >= 0 else "",
                      euro(abs(importo)) if importo is not None and importo < 0 else "",
                      f"{valuta}: importo non convertito" if importo is None else "",
                      collegamento.replace("_", " ")])
    saldo = entrate - uscite
    totali = [["Totale accrediti", euro(entrate)], ["Totale pagamenti", euro(uscite)],
              ["Saldo del periodo", euro(saldo)]]
    avvisi = [f"{estere} movimenti in valuta estera senza conversione: importo escluso dai totali" if estere else "",
              "Elenco troncato a 2000 movimenti: restringere il periodo" if troncato else ""]
    sez = _sezione("", ["Data", "Controparte", "Descrizione", "Accrediti", "Pagamenti", "Nota", "Fattura"],
                   ["l", "l", "l", "r", "r", "l", "l"], righe, totali, [9, 22, 30, 11, 11, 14, 14])
    return _voce("paypal", "PayPal", [sez], totale=saldo, riepilogo=totali, avvisi=avvisi,
                 fonte="paypal_transactions")


# ---------------------------------------------------------------------------
# SumUp
# ---------------------------------------------------------------------------

async def voce_sumup(db, p: Periodo, opz: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.sumup_sync import COLL_TRANSAZIONI, STATO_VALIDO, TIPO_VENDITA

    movimenti = await db["sumup_conto_movimenti"].find(
        p.filtro("data"),
        {"_id": 0, "data": 1, "ora": 1, "riferimento": 1, "causale": 1, "tipo_transazione": 1,
         "entrata": 1, "uscita": 1, "commissione": 1, "saldo": 1},
    ).sort([("data", 1), ("ora", 1)]).to_list(MAX_RIGHE)
    entrate = _somma([dec(m.get("entrata")) for m in movimenti])
    uscite = _somma([dec(m.get("uscita")) for m in movimenti])
    commissioni = _somma([dec(m.get("commissione")) for m in movimenti])
    righe = [[it_data(m.get("data")),
              _troncato(m.get("riferimento") or m.get("causale") or m.get("tipo_transazione"), 60),
              euro(dec(m.get("entrata"))) if (dec(m.get("entrata")) or 0) else "",
              euro(abs(dec(m.get("uscita")))) if (dec(m.get("uscita")) or 0) else "",
              euro(dec(m.get("commissione"))) if (dec(m.get("commissione")) or 0) else "",
              euro(dec(m.get("saldo")))] for m in movimenti]
    payout = await db["sumup_payouts"].find(
        p.filtro("data"),
        {"_id": 0, "payout_id": 1, "data": 1, "netto": 1, "commissione_api": 1, "stato": 1, "riferimento": 1},
    ).sort([("data", 1)]).to_list(MAX_RIGHE)
    righe_payout = [[it_data(x.get("data")), str(x.get("payout_id") or ""),
                     euro(dec(x.get("netto"))), euro(dec(x.get("commissione_api"))),
                     str(x.get("stato") or "")] for x in payout]
    netto_payout = _somma([dec(x.get("netto")) for x in payout])
    vendite = await db[COLL_TRANSAZIONI].find(
        {**p.filtro("data"), "tipo": TIPO_VENDITA, "stato": STATO_VALIDO},
        {"_id": 0, "importo": 1}).to_list(MAX_RIGHE)
    totale_vendite = _somma([dec(v.get("importo")) for v in vendite])
    sezioni = [
        _sezione("Movimenti del conto carta SumUp", ["Data", "Riferimento", "Entrate", "Uscite",
                                                     "Commissioni", "Saldo"],
                 ["l", "l", "r", "r", "r", "r"], righe,
                 [["Totale entrate", euro(entrate)], ["Totale uscite", euro(uscite)],
                  ["Totale commissioni", euro(commissioni)]], [9, 40, 12, 12, 12, 12]),
        _sezione("Accrediti (payout) dall'API SumUp", ["Data", "Payout", "Netto", "Commissione", "Stato"],
                 ["l", "l", "r", "r", "l"], righe_payout, [["Totale accreditato", euro(netto_payout)]],
                 [10, 30, 14, 14, 14]),
    ]
    riepilogo = [["Vendite SumUp del periodo (" + str(len(vendite)) + ")", euro(totale_vendite)],
                 ["Accreditato con i payout", euro(netto_payout)],
                 ["Entrate sul conto carta", euro(entrate)], ["Uscite dal conto carta", euro(uscite)]]
    avvisi = []
    if payout and not movimenti:
        avvisi.append("Estratto conto SumUp non caricato per il periodo: solo i payout dell'API")
    return _voce("sumup", "SumUp", sezioni, totale=entrate - uscite, riepilogo=riepilogo, avvisi=avvisi,
                 fonte="sumup_conto_movimenti, sumup_payouts, sumup_transactions")


# ---------------------------------------------------------------------------
# Bonifici effettuati
# ---------------------------------------------------------------------------

def _id_fatture(transfer: Dict[str, Any]) -> List[str]:
    ids = list(transfer.get("fattura_ids") or [])
    if transfer.get("fattura_associata_id"):
        ids.append(transfer["fattura_associata_id"])
    return [str(i) for i in dict.fromkeys(ids) if i]


async def voce_bonifici(db, p: Periodo, opz: Dict[str, Any]) -> Dict[str, Any]:
    from app.document_repository import metadata_projection

    bonifici = await db["bonifici_transfers"].find(
        p.filtro("data"), metadata_projection("bonifici_transfers")).sort([("data", 1)]).to_list(MAX_RIGHE)
    bonifici = [b for b in bonifici if b.get("entity_status") != "deleted"
                and b.get("status") not in ("deleted", "archived", "archiviata")]
    ids = sorted({i for b in bonifici for i in _id_fatture(b)})
    numeri: Dict[str, str] = {}
    if ids:
        possibili = ids + [int(i) for i in ids if i.isdigit()]
        for f in await db["invoices"].find({"id": {"$in": possibili}},
                                           {"_id": 0, "id": 1, "invoice_number": 1, "numero_fattura": 1}
                                           ).to_list(len(possibili)):
            numeri[str(f["id"])] = str(f.get("invoice_number") or f.get("numero_fattura") or f["id"])
    righe, senza_collegamento = [], 0
    for b in bonifici:
        benef = b.get("beneficiario") if isinstance(b.get("beneficiario"), dict) else {}
        collegati = [numeri.get(i, i) for i in _id_fatture(b)]
        if collegati:
            collegato = "Fattura " + ", ".join(collegati)
        elif b.get("dipendente_nome"):
            collegato = "Stipendio " + str(b["dipendente_nome"])
        else:
            collegato = DA_COLLEGARE
            senza_collegamento += 1
        importo = dec(b.get("importo"))
        righe.append([it_data(b.get("data")),
                      _troncato(benef.get("nome") or b.get("beneficiario_nome"), 36),
                      iban_mascherato(benef.get("iban")), str(b.get("cro_trn") or ""),
                      _troncato(b.get("causale"), 40), _troncato(collegato, 36),
                      euro(abs(importo)) if importo is not None else "",
                      "In banca" if b.get("riconciliato") else "Solo PDF"])
    totale = _somma([abs(dec(b.get("importo"))) for b in bonifici if dec(b.get("importo")) is not None])
    sez = _sezione("", ["Data", "Beneficiario", "IBAN", "CRO/TRN", "Causale", "Collegato a", "Importo",
                        "Stato"], ["l", "l", "l", "l", "l", "l", "r", "l"], righe,
                   [["Totale bonifici", euro(totale)]], [8, 18, 9, 14, 18, 16, 10, 8])
    return _voce("bonifici", "Bonifici effettuati", [sez], totale=totale,
                 riepilogo=[["Bonifici", str(len(righe))], ["Totale", euro(totale)]],
                 avvisi=[f"{senza_collegamento} bonifici senza fattura o dipendente collegato"
                         if senza_collegamento else ""], fonte="bonifici_transfers")


# ---------------------------------------------------------------------------
# Corrispettivi RT
# ---------------------------------------------------------------------------

async def voce_corrispettivi(db, p: Periodo, opz: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.completezza_commercialista import chiusure_rt_mancanti
    from app.services.conto_economico_gestionale import (
        FILTRO_CORRISPETTIVI_VALIDI, imponibile_corrispettivo, _iva_corrispettivo)

    docs = await db["corrispettivi"].find(
        {**FILTRO_CORRISPETTIVI_VALIDI, **p.filtro("data")},
        {"_id": 0, "id": 1, "data": 1, "totale": 1, "totale_imponibile": 1, "imponibile": 1,
         "totale_iva": 1, "iva": 1, "pagato_contanti": 1, "pagato_elettronico": 1, "pagato_pos": 1,
         "non_riscosso": 1},
    ).sort([("data", 1)]).to_list(MAX_RIGHE)
    per_giorno: Dict[str, Dict[str, Decimal]] = {}
    for d in docs:
        giorno = str(d.get("data") or "")[:10]
        g = per_giorno.setdefault(giorno, {k: Decimal("0") for k in
                                           ("totale", "contanti", "pos", "non_riscosso", "imponibile", "iva")})
        g["totale"] += dec(d.get("totale")) or Decimal("0")
        g["contanti"] += dec(d.get("pagato_contanti")) or Decimal("0")
        pos = d.get("pagato_elettronico") if d.get("pagato_elettronico") is not None else d.get("pagato_pos")
        g["pos"] += dec(pos) or Decimal("0")
        g["non_riscosso"] += dec(d.get("non_riscosso")) or Decimal("0")
        g["imponibile"] += imponibile_corrispettivo(d) or Decimal("0")
        g["iva"] += _iva_corrispettivo(d)
    righe = [[it_data(g), euro(v["contanti"]), euro(v["pos"]), euro(v["non_riscosso"]), euro(v["totale"]),
              euro(v["imponibile"]), euro(v["iva"])] for g, v in sorted(per_giorno.items())]
    tot = {k: sum((v[k] for v in per_giorno.values()), Decimal("0"))
           for k in ("totale", "contanti", "pos", "non_riscosso", "imponibile", "iva")}
    totali = [["Incasso totale", euro(tot["totale"])], ["di cui contanti", euro(tot["contanti"])],
              ["di cui POS", euro(tot["pos"])], ["di cui non riscosso", euro(tot["non_riscosso"])],
              ["Imponibile", euro(tot["imponibile"])], ["IVA", euro(tot["iva"])]]
    avvisi = []
    fine = p.al_dovuto()
    if p.dal <= fine:
        mancanti = await chiusure_rt_mancanti(db, p.dal, fine)
        if mancanti:
            avvisi.append(f"Mancano {len(mancanti)} chiusure RT: " + ", ".join(it_data(g) for g in mancanti[:8])
                          + ("…" if len(mancanti) > 8 else ""))
    sez = _sezione("", ["Giorno", "Contanti", "POS", "Non riscosso", "Totale", "Imponibile", "IVA"],
                   ["l", "r", "r", "r", "r", "r", "r"], righe, totali)
    return _voce("corrispettivi", "Corrispettivi RT", [sez], totale=tot["totale"], riepilogo=totali,
                 avvisi=avvisi, fonte="corrispettivi")


# ---------------------------------------------------------------------------
# Fatture ricevute per metodo di pagamento
# ---------------------------------------------------------------------------

_ETICHETTE_METODO = {"bonifico": "Bonifico", "cassa": "Cassa", "contanti": "Cassa", "carta": "Carta",
                     "assegno": "Assegno", "paypal": "PayPal", "misto": "Misto", "sdd": "Addebito diretto",
                     "riba": "Ri.Ba."}
_ETICHETTE_STATO = {"pagata": "Pagata", "parziale": "Parziale", "da_pagare": "Da pagare",
                    "da_verificare": "Da verificare", "annullata": "Annullata"}


def etichetta_metodo(valore: Any) -> str:
    from app.constants.metodi_pagamento import metodo_non_configurato

    if metodo_non_configurato(valore):
        return "Da configurare"
    testo = str(valore).strip().lower()
    return _ETICHETTE_METODO.get(testo, testo.capitalize())


async def voce_fatture_ricevute(db, p: Periodo, opz: Dict[str, Any]) -> Dict[str, Any]:
    from app.constants.fattura_attiva import FILTRO_FATTURA_ATTIVA
    from app.constants.tipi_documento import TIPI_NOTA_CREDITO
    from app.services.stato_pagamento_fattura import stato_pagamento

    fatture = await db["invoices"].find(
        {"$and": [dict(FILTRO_FATTURA_ATTIVA), p.filtro("invoice_date")]},
        {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1, "supplier_name": 1,
         "total_amount": 1, "tipo_documento": 1, "metodo_pagamento": 1, "stato": 1, "stato_pagamento": 1,
         "payment_status": 1, "pagato": 1, "paid": 1},
    ).sort([("invoice_date", 1)]).to_list(MAX_RIGHE)
    per_metodo: Dict[str, Dict[str, Any]] = {}
    righe, senza_metodo = [], 0
    for f in fatture:
        totale = dec(f.get("total_amount"))
        if totale is not None and f.get("tipo_documento") in TIPI_NOTA_CREDITO:
            totale = -abs(totale)
        metodo = etichetta_metodo(f.get("metodo_pagamento"))
        senza_metodo += metodo == "Da configurare"
        voce = per_metodo.setdefault(metodo, {"n": 0, "totale": Decimal("0")})
        voce["n"] += 1
        voce["totale"] += totale or Decimal("0")
        righe.append([it_data(f.get("invoice_date")), str(f.get("invoice_number") or ""),
                      _troncato(f.get("supplier_name"), 40), metodo,
                      _ETICHETTE_STATO.get(stato_pagamento(f), "Da verificare"), euro(totale)])
    totale_generale = _somma([v["totale"] for v in per_metodo.values()])
    riepilogo = [[f"{m}: {v['n']} fatture", euro(v["totale"])] for m, v in sorted(per_metodo.items())]
    sez = _sezione("", ["Data", "N. fattura", "Fornitore", "Metodo", "Pagamento", "Totale"],
                   ["l", "l", "l", "l", "l", "r"], righe,
                   riepilogo + [["Totale fatture", euro(totale_generale)]], [9, 13, 34, 13, 12, 12])
    return _voce("fatture_ricevute", "Fatture ricevute per metodo di pagamento", [sez],
                 totale=totale_generale, riepilogo=riepilogo + [["Totale fatture", euro(totale_generale)]],
                 avvisi=[f"{senza_metodo} fatture senza metodo di pagamento configurato" if senza_metodo else ""],
                 fonte="invoices")


# ---------------------------------------------------------------------------
# F24 e quietanze
# ---------------------------------------------------------------------------

async def voce_f24(db, p: Periodo, opz: Dict[str, Any]) -> Dict[str, Any]:
    from app.services import f24_controllo_incrociato as reg
    from app.services.registro_fiscale_f24 import QUIETANZA, documenti_f24, righe_da_registro

    registro = await reg.carica_registro(db)
    documenti = documenti_f24(righe_da_registro(registro))
    nel_periodo = [d for d in documenti if p.contiene(d.get("payment_date"))]
    senza_data = sum(1 for d in documenti if not d.get("payment_date"))
    nel_periodo.sort(key=lambda d: (str(d.get("payment_date")), str(d.get("protocol") or "")))
    righe = []
    for d in nel_periodo:
        codici = list(dict.fromkeys(str(r.get("tax_code")) for r in d["rows"] if r.get("tax_code")))
        quietanza = d.get("evidence_state") == QUIETANZA
        righe.append([it_data(d.get("payment_date")), str(d.get("protocol") or ""),
                      "Quietanza" if quietanza else "Modello del commercialista",
                      _troncato(", ".join(codici[:8]) + ("…" if len(codici) > 8 else ""), 40),
                      euro(dec(d.get("debit_amount"))), euro(dec(d.get("credit_amount"))),
                      euro(dec(d.get("net_amount")))])
    debito = _somma([dec(d.get("debit_amount")) for d in nel_periodo])
    credito = _somma([dec(d.get("credit_amount")) for d in nel_periodo])
    totali = [["Totale a debito", euro(debito)], ["Totale a credito", euro(credito)],
              ["Saldo", euro(debito - credito)]]
    sez = _sezione("", ["Versato il", "Protocollo", "Documento", "Codici tributo", "Debito", "Credito", "Saldo"],
                   ["l", "l", "l", "l", "r", "r", "r"], righe, totali, [9, 16, 16, 24, 11, 11, 11])
    return _voce("f24", "F24 e quietanze", [sez], totale=debito - credito, riepilogo=totali,
                 avvisi=[f"{senza_data} F24 senza data di versamento non sono nell'elenco" if senza_data else ""],
                 fonte="registro unico F24")


# ---------------------------------------------------------------------------
# Stipendi e cedolini
# ---------------------------------------------------------------------------

_TIPI_BUSTA = {"": "Mensile", "mensile": "Mensile", "13a": "13ª", "tredicesima": "13ª", "14a": "14ª",
               "quattordicesima": "14ª"}


async def voce_stipendi(db, p: Periodo, opz: Dict[str, Any]) -> Dict[str, Any]:
    from app.constants.stati_netto import alimenta_salari

    mesi = set(p.mesi())
    buste = await db["cedolini"].find(
        {"anno": {"$in": [a for anno in p.anni for a in (anno, str(anno))]},
         "entity_status": {"$ne": "deleted"},
         "status": {"$nin": ["deleted", "archived", "archiviata", "sostituito"]}},
        {"_id": 0, "id": 1, "anno": 1, "mese": 1, "nome_dipendente": 1, "dipendente_nome": 1,
         "dipendente": 1, "tipo_cedolino": 1, "netto": 1, "lordo": 1, "stato_netto": 1, "pagato": 1},
    ).to_list(MAX_RIGHE)

    def periodo_busta(b):
        try:
            return int(b.get("anno")), int(b.get("mese"))
        except (TypeError, ValueError):
            return None

    buste = [b for b in buste if periodo_busta(b) in mesi]
    buste.sort(key=lambda b: (periodo_busta(b), str(b.get("nome_dipendente") or b.get("dipendente_nome") or "")))
    righe, non_verificati, senza_lordo = [], 0, 0
    netto_tot, lordo_tot = Decimal("0"), Decimal("0")
    for b in buste:
        a, m = periodo_busta(b)
        verificato = alimenta_salari(b.get("stato_netto"))
        netto = dec(b.get("netto")) if verificato else None
        lordo = dec(b.get("lordo"))
        non_verificati += netto is None
        senza_lordo += lordo is None
        netto_tot += netto or Decimal("0")
        lordo_tot += lordo or Decimal("0")
        tipo = _TIPI_BUSTA.get(str(b.get("tipo_cedolino") or "").strip().lower(),
                               str(b.get("tipo_cedolino")))
        righe.append([_troncato(b.get("nome_dipendente") or b.get("dipendente_nome") or b.get("dipendente"), 36),
                      f"{m:02d}/{a}", tipo, euro(lordo),
                      euro(netto) if netto is not None else "Da verificare",
                      "Pagata" if b.get("pagato") is True else "Da pagare"])
    # I bonifici partiti verso i dipendenti (con collegamento alla busta o al dipendente).
    from app.document_repository import metadata_projection

    bonifici = await db["bonifici_transfers"].find(
        p.filtro("data"), metadata_projection("bonifici_transfers")).sort([("data", 1)]).to_list(MAX_RIGHE)
    bonifici = [b for b in bonifici if (b.get("salario_associato") is True or b.get("dipendente_nome"))
                and b.get("entity_status") != "deleted"]
    righe_bonifici = [[it_data(b.get("data")), _troncato(b.get("dipendente_nome"), 36),
                       str(b.get("cro_trn") or ""), euro(abs(dec(b.get("importo")) or Decimal("0")))
                       if dec(b.get("importo")) is not None else "",
                       "In banca" if b.get("riconciliato") else "Solo PDF"] for b in bonifici]
    bonifici_tot = _somma([abs(dec(b.get("importo"))) for b in bonifici if dec(b.get("importo")) is not None])
    sezioni = [
        _sezione("Buste paga del periodo", ["Dipendente", "Competenza", "Tipo", "Lordo", "Netto", "Pagamento"],
                 ["l", "l", "l", "r", "r", "l"], righe,
                 [["Totale lordo", euro(lordo_tot)], ["Totale netto verificato", euro(netto_tot)]],
                 [30, 10, 10, 12, 14, 10]),
        _sezione("Bonifici stipendio", ["Data", "Dipendente", "CRO/TRN", "Importo", "Stato"],
                 ["l", "l", "l", "r", "l"], righe_bonifici, [["Totale bonifici", euro(bonifici_tot)]],
                 [10, 32, 22, 12, 10]),
    ]
    avvisi = [f"{non_verificati} buste con netto non verificato dal cedolino" if non_verificati else "",
              f"{senza_lordo} buste senza lordo" if senza_lordo else ""]
    return _voce("stipendi", "Stipendi e cedolini", sezioni, totale=netto_tot,
                 riepilogo=[["Buste paga", str(len(buste))], ["Totale lordo", euro(lordo_tot)],
                            ["Totale netto verificato", euro(netto_tot)],
                            ["Bonifici stipendio", euro(bonifici_tot)]],
                 avvisi=avvisi, fonte="cedolini, bonifici_transfers")


# ---------------------------------------------------------------------------
# Presenze (HR)
# ---------------------------------------------------------------------------

async def voce_presenze(db, p: Periodo, opz: Dict[str, Any]) -> Dict[str, Any]:
    from app.hr.services import presenze_consulente as pc

    righe, mesi = [], []
    for anno, mese in p.mesi():
        if not await pc.mese_ha_presenze(anno, mese):
            continue
        invii = await pc.invii_presenze(anno, mese)
        ultimo = invii[0] if invii else None
        mesi.append({"anno": anno, "mese": mese, "etichetta": f"{MESI_NOMI[mese]} {anno}",
                     "inviato_il": ultimo.get("data_invio") if ultimo else None,
                     "destinatario": ultimo.get("destinatario") if ultimo else None})
        righe.append([f"{MESI_NOMI[mese]} {anno}", "Già inviato" if ultimo else "Da inviare",
                      it_data(ultimo.get("data_invio")) if ultimo else "",
                      str(ultimo.get("destinatario") or "") if ultimo else ""])
    da_inviare = [m for m in mesi if not m["inviato_il"]]
    sez = _sezione("Presenze del mese registrate in HR", ["Mese", "Stato", "Inviato il", "A"],
                   ["l", "l", "l", "l"], righe)
    voce = _voce("presenze", "Presenze (HR)", [sez], fonte="presenze_invii")
    if not mesi:
        voce["motivo"] = "Nessuna presenza registrata in HR per il periodo"
    elif da_inviare:
        voce["stato"] = STATO_DA_INVIARE
        voce["motivo"] = "Presenze registrate in HR, invio al consulente non ancora fatto"
    else:
        voce["stato"] = STATO_GIA_INVIATO
        voce["motivo"] = "Già inviato il " + it_data(max(m["inviato_il"] for m in mesi))
    voce["mesi"] = mesi
    return voce


# ---------------------------------------------------------------------------
# Registro delle voci
# ---------------------------------------------------------------------------

Builder = Callable[[Any, Periodo, Dict[str, Any]], Awaitable[Dict[str, Any]]]

#: id -> (titolo, builder), nell'ordine con cui compaiono in pagina.
VOCI: Dict[str, Tuple[str, Builder]] = {
    "prima_nota_cassa": ("Prima Nota Cassa", voce_prima_nota_cassa),
    "fatture_cassa": ("Fatture pagate per cassa", voce_fatture_cassa),
    "carnet_assegni": ("Carnet assegni", voce_carnet),
    "banca": ("Banca (conto BPM)", voce_banca),
    "paypal": ("PayPal", voce_paypal),
    "sumup": ("SumUp", voce_sumup),
    "bonifici": ("Bonifici effettuati", voce_bonifici),
    "corrispettivi": ("Corrispettivi RT", voce_corrispettivi),
    "fatture_ricevute": ("Fatture ricevute per metodo di pagamento", voce_fatture_ricevute),
    "f24": ("F24 e quietanze", voce_f24),
    "stipendi": ("Stipendi e cedolini", voce_stipendi),
    "presenze": ("Presenze (HR)", voce_presenze),
}


async def costruisci_voce(db, voce: str, p: Periodo, opz: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Una voce del pacchetto; un guasto della fonte la rende «Non disponibile», mai un errore."""
    titolo, builder = VOCI[voce]
    try:
        return await builder(db, p, opz or {})
    except Exception as exc:  # noqa: BLE001 - una voce guasta non ferma le altre
        logger.warning("Voce %s del pacchetto non costruita: %s: %s", voce, type(exc).__name__, exc)
        return voce_non_disponibile(voce, titolo, f"Fonte non leggibile ({type(exc).__name__})")


async def costruisci_voci(db, voci: Sequence[str], p: Periodo,
                          opz: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    return list(await asyncio.gather(*(costruisci_voce(db, v, p, opz) for v in voci)))


def riassunto(voce: Dict[str, Any]) -> Dict[str, Any]:
    """La voce senza righe: quanto serve alla scheda della pagina."""
    return {k: voce.get(k) for k in ("voce", "titolo", "stato", "motivo", "conteggio", "totale", "avvisi",
                                     "mesi", "fonte")}


# ---------------------------------------------------------------------------
# Allegati
# ---------------------------------------------------------------------------

def nome_file(voce: str, p: Periodo, estensione: str) -> str:
    return f"{_slug(VOCI[voce][0])}_{p.dal}_{p.al}.{estensione}"


async def allegati_voce(db, voce: Dict[str, Any], p: Periodo,
                        opz: Optional[Dict[str, Any]] = None
                        ) -> Tuple[List[Tuple[bytes, str, str, str]], Dict[str, Any]]:
    """Gli allegati (bytes, maintype, subtype, nome) di una voce gia' costruita.

    Il secondo valore porta cio' che serve a registrare l'invio: per le presenze i mesi
    inclusi (``presenze_mesi``, con il numero di dipendenti del foglio).
    """
    from app.services.commercialista_pdf import pdf_voce

    if voce["voce"] == "presenze":
        from app.hr.services import presenze_consulente as pc

        rinvia = bool((opz or {}).get("presenze_rinvia"))
        allegati, inclusi = [], []
        for m in voce.get("mesi") or []:
            if m["inviato_il"] and not rinvia:
                continue
            foglio = await pc.righe_presenze_mese(m["anno"], m["mese"])
            if not pc.ha_presenze(foglio["righe"]):
                continue
            allegati += pc.allegati_presenze(m["anno"], m["mese"], foglio["giorni"], foglio["righe"])
            inclusi.append({"anno": m["anno"], "mese": m["mese"], "n_dipendenti": len(foglio["righe"])})
        return allegati, {"presenze_mesi": inclusi}
    return ([(pdf_voce(voce, p.etichetta, p.dal, p.al), "application", "pdf",
              nome_file(voce["voce"], p, "pdf"))], {})
