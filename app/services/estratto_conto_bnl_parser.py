"""Lettore dell'estratto conto cartaceo BNL (conto storico 4500/3192, chiuso).

Il PDF trimestrale di BNL stampa i movimenti in una tabella a sei colonne:
data contabile, data valuta, causale ABI (due cifre), descrizione, «PER UNA
USCITA DI», «PER UNA ENTRATA DI». Il testo piatto perde l'ultima
informazione: «597,86 €» esce uguale che sia un'uscita o un'entrata. Il verso
si legge quindi **dalla posizione** della parola importo rispetto alle due
intestazioni di colonna della stessa pagina, come fa il lettore SumUp.

La descrizione puo' continuare sulla riga sotto («di cui 1,50 per
Commiss/Spese»): quella riga non ha date e comincia nella colonna della
descrizione, e si attacca al movimento precedente.

La prova non e' il lettore ma l'aritmetica del riepilogo in testa: saldo
iniziale + entrate complessive − uscite complessive = saldo finale, e i
totali devono coincidere con la somma delle righe lette. Un estratto che non
torna **non si importa**: una riga persa o col verso sbagliato diventerebbe
un movimento inventato su cui si riconciliano assegni, F24 e bonifici.

Il modulo lavora su parole gia' estratte (``text``, ``x0``, ``x1``, ``top``),
cosi' i collaudi non dipendono da un PDF reale; ``leggi_estratto_bnl`` le
ricava con pdfplumber.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence

Parola = Dict[str, Any]

#: Valore di ``fonte``/``source`` dei movimenti scritti in archivio da questo lettore.
FONTE_BNL = "estratto_bnl_pdf"
BANCA_BNL = "BNL"

_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_IMPORTO = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2}$")
_ABI = re.compile(r"^[0-9A-Z]{2}$")   # causale ABI: due cifre, o due lettere (es. «ZG» accredito derivati)
# ABI 01005 = Banca Nazionale del Lavoro.
_IBAN_BNL = re.compile(r"\bIT\d{2}[A-Z]01005\d{5}[0-9A-Z]{12}\b")
_NUMERO_ESTRATTO = re.compile(r"ESTRATTO CONTO N\.\s*(\d+/\d{4})", re.IGNORECASE)
_PERIODO = re.compile(r"MOVIMENTI DAL\s+(\d{2}/\d{2}/\d{4})\s+AL\s+(\d{2}/\d{2}/\d{4})", re.IGNORECASE)
_CONTO = re.compile(r"C/C N\.\s*(\d+/\d+)")
_SEGNO_IMPORTO = r"\s*([+-])?\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*€"
_SALDO_INIZIALE = re.compile(r"saldo iniziale al \d{2}/\d{2}/\d{4}\?" + _SEGNO_IMPORTO, re.IGNORECASE)
_ENTRATE = re.compile(r"entrate complessive di questo periodo\?" + _SEGNO_IMPORTO, re.IGNORECASE)
_USCITE = re.compile(r"uscite complessive di questo periodo\?" + _SEGNO_IMPORTO, re.IGNORECASE)
_SALDO_FINALE = re.compile(r"saldo finale al \d{2}/\d{2}/\d{4}\?" + _SEGNO_IMPORTO, re.IGNORECASE)

# Parole nella stessa riga di stampa: la riga «IL SALDO FINALE … QUINDI:» ha
# l'importo spostato di 1,4 pt rispetto all'etichetta.
_TOLLERANZA_RIGA = 3.0
# Le intestazioni «PER UNA USCITA DI / PER UNA ENTRATA DI» stanno a ~20 pt
# sopra «(DATA CONTABILE)»; il titolo «MOVIMENTI IN ENTRATA E IN USCITA»
# e' piu' su e non va confuso con esse.
_FINESTRA_INTESTAZIONE = 30.0
_TOLLERANZA_COLONNA = 8.0


class EstrattoBNLNonValido(ValueError):
    """Il PDF non e' un estratto BNL leggibile, o i saldi non tornano."""


@dataclass
class RigaBNL:
    data_contabile: str          # AAAA-MM-GG
    data_valuta: str             # AAAA-MM-GG
    causale_abi: str             # due caratteri (cifre o lettere), stringa
    descrizione: str             # intera, continuazioni comprese
    importo: Decimal             # sempre positivo
    tipo: str                    # «entrata» | «uscita»
    pagina: int

    @property
    def importo_netto(self) -> Decimal:
        return self.importo if self.tipo == "entrata" else -self.importo

    def come_dict(self) -> Dict[str, Any]:
        return {
            "data_contabile": self.data_contabile, "data_valuta": self.data_valuta,
            "causale_abi": self.causale_abi, "descrizione": self.descrizione,
            "importo": str(self.importo), "tipo": self.tipo, "pagina": self.pagina,
        }


@dataclass
class EstrattoBNL:
    numero_estratto: Optional[str]
    periodo_dal: Optional[str]
    periodo_al: Optional[str]
    conto: Optional[str]
    iban: Optional[str]
    saldo_iniziale: Decimal
    saldo_finale: Decimal
    totale_entrate: Decimal
    totale_uscite: Decimal
    righe: List[RigaBNL] = field(default_factory=list)
    #: Saldo stampato in coda alla tabella («IL SALDO FINALE AL … E' QUINDI:»).
    saldo_finale_tabella: Optional[Decimal] = None
    #: Saldo della prima riga della tabella («SALDO INIZIALE»).
    saldo_iniziale_tabella: Optional[Decimal] = None


def e_estratto_bnl(testo: str) -> bool:
    """Segni esclusivi dell'estratto del conto corrente BNL.

    Serve il titolo «ESTRATTO CONTO N.», la banca (ragione sociale o IBAN con
    ABI 01005) e la tabella con la data contabile. L'estratto della carta
    «BNL Business» ha un altro lettore e resta fuori.
    """
    minuscolo = (testo or "").lower()
    if "estratto conto n." not in minuscolo or "carta bnl business" in minuscolo:
        return False
    if "data contabile" not in minuscolo:
        return False
    return "banca nazionale del lavoro" in minuscolo or bool(_IBAN_BNL.search(testo or ""))


def _decimale(testo: str) -> Decimal:
    try:
        return Decimal(testo.replace(".", "").replace(",", "."))
    except (InvalidOperation, AttributeError) as exc:
        raise EstrattoBNLNonValido(f"Importo illeggibile: {testo!r}") from exc


def _con_segno(segno: Optional[str], testo: str) -> Decimal:
    valore = _decimale(testo)
    return -valore if segno == "-" else valore


def _data_iso(testo: str) -> str:
    try:
        return datetime.strptime(testo, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise EstrattoBNLNonValido(f"Data illeggibile: {testo!r}") from exc


def _righe_di_stampa(parole: Sequence[Parola]) -> List[List[Parola]]:
    """Parole raggruppate per riga di stampa, dall'alto in basso, da sinistra a destra."""
    ordinate = sorted(parole, key=lambda w: (float(w["top"]), float(w["x0"])))
    righe: List[List[Parola]] = []
    for parola in ordinate:
        if righe and abs(float(parola["top"]) - float(righe[-1][0]["top"])) <= _TOLLERANZA_RIGA:
            righe[-1].append(parola)
        else:
            righe.append([parola])
    for riga in righe:
        riga.sort(key=lambda w: float(w["x0"]))
    return righe


def testo_da_parole(pagine: Sequence[Sequence[Parola]]) -> str:
    """Il testo delle pagine ricostruito dalle parole, per i campi d'intestazione."""
    return "\n".join(
        " ".join(str(w["text"]) for w in riga)
        for pagina in pagine for riga in _righe_di_stampa(pagina)
    )


@dataclass
class _Colonne:
    data_contabile_x0: float
    data_valuta_x0: float
    abi_x0: float
    descrizione_x0: float
    uscita_centro: float
    entrata_centro: float
    inizio_tabella_top: float


def _colonne(parole: Sequence[Parola]) -> Optional[_Colonne]:
    """Fasce delle colonne lette dall'intestazione della pagina, o None se manca."""
    contabile = next((w for w in parole if w["text"] == "CONTABILE)"), None)
    if contabile is None:
        return None
    top = float(contabile["top"])
    stessa_riga = [w for w in parole if abs(float(w["top"]) - top) <= _TOLLERANZA_RIGA]
    date = sorted((w for w in stessa_riga if w["text"] == "(DATA"), key=lambda w: float(w["x0"]))
    if len(date) < 2:
        return None
    sopra = [w for w in parole if top - _FINESTRA_INTESTAZIONE <= float(w["top"]) < top]

    def centro(etichetta: str) -> Optional[float]:
        candidate = [w for w in sopra if w["text"] == etichetta]
        if not candidate:
            return None
        parola = max(candidate, key=lambda w: float(w["top"]))
        # «DI» subito a destra, sulla stessa riga: la colonna e' «USCITA DI».
        seguente = next(
            (w for w in sopra if w["text"] == "DI"
             and abs(float(w["top"]) - float(parola["top"])) <= _TOLLERANZA_RIGA
             and 0 <= float(w["x0"]) - float(parola["x1"]) <= 6),
            None,
        )
        destra = float(seguente["x1"]) if seguente else float(parola["x1"])
        return (float(parola["x0"]) + destra) / 2

    uscita, entrata = centro("USCITA"), centro("ENTRATA")
    abi = next((w for w in sopra if w["text"] == "ABI"), None) or next(
        (w for w in sopra if w["text"] == "CAUS."), None)
    if uscita is None or entrata is None or abi is None:
        return None
    return _Colonne(
        data_contabile_x0=float(date[0]["x0"]),
        data_valuta_x0=float(date[1]["x0"]),
        abi_x0=float(abi["x0"]),
        # La descrizione comincia dopo il codice ABI e prima della fascia importi.
        descrizione_x0=float(abi["x1"]) + 4,
        uscita_centro=uscita,
        entrata_centro=entrata,
        inizio_tabella_top=top + _TOLLERANZA_RIGA,
    )


def _vicino(valore: float, riferimento: float) -> bool:
    return abs(valore - riferimento) <= _TOLLERANZA_COLONNA


def _verso(parola: Parola, colonne: _Colonne) -> str:
    centro = (float(parola["x0"]) + float(parola["x1"])) / 2
    return ("entrata" if abs(centro - colonne.entrata_centro) < abs(centro - colonne.uscita_centro)
            else "uscita")


def _importo_della_riga(riga: List[Parola], colonne: _Colonne) -> Optional[Parola]:
    """La parola importo nella fascia delle due colonne, o None.

    Un importo dentro la descrizione («di cui 1,50 per …») sta a sinistra della
    fascia e non viene mai preso.
    """
    soglia = min(colonne.uscita_centro, colonne.entrata_centro) - 45
    candidati = [w for w in riga if _IMPORTO.match(str(w["text"])) and float(w["x0"]) >= soglia]
    if len(candidati) > 1:
        raise EstrattoBNLNonValido(
            "Riga con due importi nelle colonne uscita/entrata: "
            + " ".join(str(w["text"]) for w in riga)
        )
    return candidati[0] if candidati else None


def leggi_parole_bnl(pagine: Sequence[Sequence[Parola]], testo: Optional[str] = None) -> EstrattoBNL:
    """Legge l'estratto da parole posizionate e verifica i saldi. Solleva se non torna.

    ``pagine``: per ogni pagina la lista delle parole ``{text, x0, x1, top}``
    (quelle di ``pdfplumber.Page.extract_words``). ``testo``: il testo piatto
    per i campi d'intestazione; se manca si ricostruisce dalle parole.
    """
    testo = testo if testo is not None else testo_da_parole(pagine)
    if not e_estratto_bnl(testo):
        raise EstrattoBNLNonValido("Non e' un estratto del conto corrente BNL")

    righe: List[RigaBNL] = []
    saldo_iniziale_tabella: Optional[Decimal] = None
    saldo_finale_tabella: Optional[Decimal] = None
    chiusa = False
    for indice, parole in enumerate(pagine, start=1):
        if chiusa:
            break
        colonne = _colonne(parole)
        if colonne is None:
            continue
        corrente: Optional[RigaBNL] = None
        # Il margine sinistro porta segni di stampa verticali («1.01», «.rev»)
        # a sinistra della prima colonna: non appartengono alla tabella.
        in_tabella = [w for w in parole
                      if float(w["x0"]) >= colonne.data_contabile_x0 - _TOLLERANZA_COLONNA]
        for riga in _righe_di_stampa(in_tabella):
            if float(riga[0]["top"]) <= colonne.inizio_tabella_top:
                continue
            prima = riga[0]
            testo_riga = " ".join(str(w["text"]) for w in riga)
            if _DATA.match(str(prima["text"])) and _vicino(float(prima["x0"]), colonne.data_contabile_x0):
                importo = _importo_della_riga(riga, colonne)
                valuta = next((w for w in riga[1:] if _DATA.match(str(w["text"]))
                               and _vicino(float(w["x0"]), colonne.data_valuta_x0)), None)
                # I codici alfabetici stretti (ZI) sono allineati a destra:
                # il bordo sinistro puo' distare quasi 10 pt dall'etichetta.
                # Restiamo nella fascia ABI, prima della descrizione.
                abi = next((w for w in riga if _ABI.match(str(w["text"]))
                            and colonne.abi_x0 - _TOLLERANZA_COLONNA <= float(w["x0"])
                            and float(w["x1"]) <= colonne.descrizione_x0 + 1), None)
                esclusi = {id(prima), id(importo) if importo else None,
                           id(valuta) if valuta else None, id(abi) if abi else None}
                descrizione = " ".join(
                    str(w["text"]) for w in riga
                    if id(w) not in esclusi and str(w["text"]) != "€"
                ).strip()
                if "SALDO INIZIALE" in descrizione.upper():
                    if importo is None:
                        raise EstrattoBNLNonValido("Riga «SALDO INIZIALE» senza importo")
                    valore = _decimale(str(importo["text"]))
                    saldo_iniziale_tabella = valore if _verso(importo, colonne) == "entrata" else -valore
                    corrente = None
                    continue
                if importo is None or valuta is None or abi is None:
                    raise EstrattoBNLNonValido(
                        f"Riga di movimento incompleta a pagina {indice}: {testo_riga}"
                    )
                corrente = RigaBNL(
                    data_contabile=_data_iso(str(prima["text"])),
                    data_valuta=_data_iso(str(valuta["text"])),
                    causale_abi=str(abi["text"]),
                    descrizione=descrizione,
                    importo=_decimale(str(importo["text"])),
                    tipo=_verso(importo, colonne),
                    pagina=indice,
                )
                righe.append(corrente)
                continue
            if "SALDO FINALE" in testo_riga.upper():
                importo = _importo_della_riga(riga, colonne)
                if importo is not None:
                    valore = _decimale(str(importo["text"]))
                    saldo_finale_tabella = valore if _verso(importo, colonne) == "entrata" else -valore
                chiusa = True
                break
            if corrente is not None and float(prima["x0"]) >= colonne.descrizione_x0 \
                    and float(prima["x0"]) < min(colonne.uscita_centro, colonne.entrata_centro) - 45:
                corrente.descrizione = f"{corrente.descrizione} {testo_riga}".strip()
                continue
            # Testo fuori dalle colonne (note a pie' di pagina): la tabella
            # della pagina e' finita.
            break

    if not righe:
        raise EstrattoBNLNonValido("Nessuna riga di movimento trovata")

    def _campo(regex: re.Pattern, nome: str) -> Decimal:
        trovato = regex.search(testo)
        if not trovato:
            raise EstrattoBNLNonValido(f"Riepilogo senza «{nome}»: impossibile verificare i saldi")
        return _con_segno(trovato.group(1), trovato.group(2))

    numero = _NUMERO_ESTRATTO.search(testo)
    periodo = _PERIODO.search(testo)
    conto = _CONTO.search(testo)
    iban = _IBAN_BNL.search(testo)
    estratto = EstrattoBNL(
        numero_estratto=numero.group(1) if numero else None,
        periodo_dal=_data_iso(periodo.group(1)) if periodo else None,
        periodo_al=_data_iso(periodo.group(2)) if periodo else None,
        conto=conto.group(1) if conto else None,
        iban=iban.group(0) if iban else None,
        saldo_iniziale=_campo(_SALDO_INIZIALE, "saldo iniziale"),
        saldo_finale=_campo(_SALDO_FINALE, "saldo finale"),
        totale_entrate=_campo(_ENTRATE, "entrate complessive"),
        totale_uscite=_campo(_USCITE, "uscite complessive").copy_abs(),
        righe=righe,
        saldo_finale_tabella=saldo_finale_tabella,
        saldo_iniziale_tabella=saldo_iniziale_tabella,
    )
    verifica_saldi(estratto)
    return estratto


def verifica_saldi(estratto: EstrattoBNL) -> None:
    """Riepilogo contro righe: tutto al centesimo, altrimenti si rifiuta."""
    entrate = sum((r.importo for r in estratto.righe if r.tipo == "entrata"), Decimal("0"))
    uscite = sum((r.importo for r in estratto.righe if r.tipo == "uscita"), Decimal("0"))
    if entrate != estratto.totale_entrate or uscite != estratto.totale_uscite:
        raise EstrattoBNLNonValido(
            f"Totali del riepilogo diversi dalle righe lette: entrate {entrate} contro "
            f"{estratto.totale_entrate}, uscite {uscite} contro {estratto.totale_uscite}"
        )
    atteso = estratto.saldo_iniziale + estratto.totale_entrate - estratto.totale_uscite
    if atteso != estratto.saldo_finale:
        raise EstrattoBNLNonValido(
            f"Il saldo non torna: {estratto.saldo_iniziale} + {estratto.totale_entrate} "
            f"- {estratto.totale_uscite} = {atteso}, sul PDF {estratto.saldo_finale}"
        )
    if (estratto.saldo_iniziale_tabella is not None
            and estratto.saldo_iniziale_tabella != estratto.saldo_iniziale):
        raise EstrattoBNLNonValido(
            f"Saldo iniziale della tabella {estratto.saldo_iniziale_tabella} diverso "
            f"dal riepilogo {estratto.saldo_iniziale}"
        )
    if (estratto.saldo_finale_tabella is not None
            and estratto.saldo_finale_tabella != estratto.saldo_finale):
        raise EstrattoBNLNonValido(
            f"Saldo finale della tabella {estratto.saldo_finale_tabella} diverso "
            f"dal riepilogo {estratto.saldo_finale}"
        )


def _parole_pdf(pdf_bytes: bytes):
    """(testo delle prime due pagine, parole per pagina) con pdfplumber."""
    import io

    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            testo = "\n".join((p.extract_text() or "") for p in pdf.pages[:2])
            pagine = [
                [{"text": w["text"], "x0": w["x0"], "x1": w["x1"], "top": w["top"]}
                 for w in pagina.extract_words()]
                for pagina in pdf.pages
            ]
    except Exception as exc:  # PDF danneggiato: il motivo va detto
        raise EstrattoBNLNonValido(f"PDF non apribile ({type(exc).__name__}: {exc})") from exc
    return testo, pagine


def e_estratto_bnl_pdf(pdf_bytes: bytes) -> bool:
    """Riconoscimento dal contenuto, mai dal nome; un PDF illeggibile non e' BNL."""
    try:
        import io

        import pdfplumber

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return False
            return e_estratto_bnl(pdf.pages[0].extract_text() or "")
    except Exception:
        return False


def leggi_estratto_bnl(pdf_bytes: bytes) -> EstrattoBNL:
    """Legge il PDF e verifica i saldi. Solleva ``EstrattoBNLNonValido`` se non torna."""
    testo, pagine = _parole_pdf(pdf_bytes)
    if not e_estratto_bnl(testo):
        raise EstrattoBNLNonValido("Non e' un estratto del conto corrente BNL")
    # L'intestazione (riepilogo, periodo, IBAN) sta nelle prime pagine; i
    # campi si cercano nel testo piatto di pdfplumber, piu' fedele agli
    # a-capo del PDF di quello ricostruito dalle parole.
    return leggi_parole_bnl(pagine, testo=testo)


def movimenti_per_archivio(estratto: EstrattoBNL, *, sha256: str) -> List[Dict[str, Any]]:
    """Le righe nella forma che ``import_estratto_conto`` scrive in archivio.

    Stessa forma e stessa chiave di deduplica dei movimenti BPM; cambiano il
    conto contabile (BNL, non BPM), la fonte e il riferimento al PDF. Gli
    importi dell'archivio sono numeri come per tutte le altre fonti: il
    Decimal resta nel lettore, dove si verifica l'aritmetica.
    """
    from app.routers.bank.estratto_conto import (
        estrai_fornitore_pulito, estrai_numero_fattura, is_versamento_contanti,
    )
    from app.services.conti_pos import CONTO_BNL
    from app.services.doppioni_estratto_conto import numero_assegno
    from app.services.estratto_conto_bpm_parser import extract_f24_info, is_pagamento_f24

    movimenti: List[Dict[str, Any]] = []
    for riga in estratto.righe:
        importo = float(riga.importo_netto)
        movimento: Dict[str, Any] = {
            "data": datetime.strptime(riga.data_contabile, "%Y-%m-%d").date(),
            "ragione_sociale": None,
            "fornitore": estrai_fornitore_pulito(riga.descrizione),
            "importo": importo,
            "numero_fattura": estrai_numero_fattura(riga.descrizione),
            "data_pagamento": datetime.strptime(riga.data_valuta, "%Y-%m-%d").date(),
            "categoria": "",
            "descrizione_originale": riga.descrizione,
            "banca": BANCA_BNL,
            "rapporto": estratto.conto,
            "divisa": "EUR",
            "hashtag": None,
            "tipo": riga.tipo,
            # Campi propri di questa fonte, passati tali e quali al record.
            "conto_contabile": CONTO_BNL,
            "fonte": FONTE_BNL,
            "source": FONTE_BNL,
            "iban": estratto.iban,
            "causale_abi": riga.causale_abi,
            "numero_estratto": estratto.numero_estratto,
            "periodo_dal": estratto.periodo_dal,
            "periodo_al": estratto.periodo_al,
            "file_sha256": sha256,
        }
        # Natura riconosciuta con gli stessi helper del conto BPM: niente
        # seconda lista di parole chiave.
        if is_pagamento_f24(riga.descrizione):
            movimento["natura"] = "f24"
            movimento["f24_info"] = extract_f24_info(
                riga.descrizione, datetime.strptime(riga.data_contabile, "%Y-%m-%d"))
        elif is_versamento_contanti(riga.descrizione):
            movimento["natura"] = "versamento_contanti"
        else:
            assegno = numero_assegno({"descrizione": riga.descrizione})
            if assegno:
                movimento["natura"] = "assegno"
                movimento["numero_assegno"] = assegno
        movimenti.append(movimento)
    return movimenti
