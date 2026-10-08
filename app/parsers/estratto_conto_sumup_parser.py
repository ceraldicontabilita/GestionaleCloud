"""Lettore dell'estratto della carta Mastercard SumUp (conto business SumUp).

Il PDF («Estratto conto SumUp», SumUp Limited, IBAN ``IE..SUMU..``) è una
tabella stampata **ruotata**: il testo semplice esce con le celle mescolate
(«Pagamento 08/08/26, CO46NLZEKL … in 07:33»). Si legge quindi **per
posizione**, come la LIPE: ogni riga comincia con la data «gg/mm/aa,» e le
celle stanno nella colonna della loro intestazione.

La prova non è il lettore ma l'aritmetica: ogni riga porta il saldo
disponibile, e ``saldo precedente + entrata − uscita − commissione`` deve dare
il saldo della riga, dalla più vecchia alla più recente, partendo dal saldo
iniziale del riepilogo e arrivando al saldo finale. Un estratto che non torna
**non si importa**: una riga letta male diventerebbe un movimento inventato.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

_DATA_RIGA = re.compile(r"^(\d{2})/(\d{2})/(\d{2}),$")
_ORA = re.compile(r"^\d{2}:\d{2}$")
_IMPORTO = re.compile(r"^-?\d+\.\d{2}$")
_CODICE = re.compile(r"^C[0-9A-Z]{9}$")
_IBAN_SUMUP = re.compile(r"\bIE\d{2}SUMU\d{14}\b")
_PID = re.compile(r"\bPID\d+\b")

# Colonne, dalla prima all'ultima. Nella pagina ruotata la colonna è la
# coordinata «y» della parola: si prende dall'intestazione della pagina.
_INTESTAZIONI = (
    ("data", "Data"),
    ("codice", "Codice"),
    ("tipo", "Tipo"),
    ("riferimento", "Riferimento"),
    ("causale", "Causale"),
    ("stato", "Stato"),
    ("uscita", "Importo"),     # prima «Importo»: fatturazione in uscita
    ("entrata", "Importo"),    # seconda «Importo»: fatturazione in entrata
    ("commissione", "Commis"),
    ("saldo", "Saldo"),
)


class EstrattoSumUpNonValido(ValueError):
    """Il PDF non è un estratto SumUp leggibile, o i saldi non tornano."""


@dataclass
class RigaSumUp:
    data: str                     # AAAA-MM-GG
    ora: str
    codice: str                   # codice transazione SumUp (Cxxxxxxxxx)
    tipo_transazione: str         # «Pagamento da SumUp», «Bonifico bancario in uscita», …
    riferimento: str
    causale: str
    stato: str
    uscita: Decimal
    entrata: Decimal
    commissione: Decimal
    saldo: Decimal
    pid: Optional[str] = None     # riferimento del payout SumUp («PID1772679»)

    @property
    def importo_netto(self) -> Decimal:
        """Effetto sul saldo: positivo se entra, negativo se esce."""
        return self.entrata - self.uscita - self.commissione

    def come_dict(self) -> Dict[str, Any]:
        return {
            "data": self.data, "ora": self.ora, "codice": self.codice,
            "tipo_transazione": self.tipo_transazione, "riferimento": self.riferimento,
            "causale": self.causale, "stato": self.stato,
            "uscita": str(self.uscita), "entrata": str(self.entrata),
            "commissione": str(self.commissione), "saldo": str(self.saldo),
            "pid": self.pid,
        }


@dataclass
class EstrattoSumUp:
    iban: Optional[str]
    id_utente: Optional[str]
    numero_carta: Optional[str]
    periodo_dal: Optional[str]
    periodo_al: Optional[str]
    saldo_iniziale: Decimal
    saldo_finale: Decimal
    totale_entrate: Decimal
    totale_uscite: Decimal
    righe: List[RigaSumUp] = field(default_factory=list)


def e_estratto_sumup(testo: str) -> bool:
    """Segni esclusivi dell'estratto SumUp: mai il solo «estratto conto»."""
    minuscolo = (testo or "").lower()
    return "estratto conto sumup" in minuscolo or bool(_IBAN_SUMUP.search(testo or ""))


def _decimale(testo: str) -> Decimal:
    try:
        return Decimal(testo)
    except (InvalidOperation, TypeError) as exc:
        raise EstrattoSumUpNonValido(f"Importo illeggibile: {testo!r}") from exc


def _data_iso(testo: str) -> str:
    gg, mm, aa = re.match(r"(\d{2})/(\d{2})/(\d{2})", testo).groups()
    return datetime(2000 + int(aa), int(mm), int(gg)).strftime("%Y-%m-%d")


def _colonne(parole: List[tuple]) -> Optional[List[Tuple[str, float, float]]]:
    """Fascia di ogni colonna, letta dall'intestazione della tabella.

    Restituisce ``[(nome, y_basso, y_alto)]`` nell'ordine delle colonne, o
    ``None`` se la pagina non ha l'intestazione (dalla seconda pagina in poi
    SumUp non la ristampa: vale quella della prima). Nella pagina ruotata il
    testo di ogni cella parte dal bordo alto della colonna, lo stesso
    dell'intestazione: la colonna va da lì al bordo alto della successiva.
    """
    # Solo le parole della fascia d'intestazione della tabella: «Codice»
    # compare anche in «Codice IBAN» del riepilogo, «Saldo» in «Saldo finale».
    ancora = next((w for w in parole if w[4] == "Riferimento"), None)
    if ancora is None:
        return None
    ordinate = sorted(
        (w for w in parole if abs(w[0] - ancora[0]) <= 30),
        key=lambda w: -w[3],
    )
    alti: List[Tuple[str, float]] = []
    usate = set()
    for nome, etichetta in _INTESTAZIONI:
        candidata = next(
            (w for w in ordinate
             if w[4] == etichetta and id(w) not in usate
             and (not alti or w[3] < alti[-1][1] - 1)),
            None,
        )
        if candidata is None:
            return None
        usate.add(id(candidata))
        alti.append((nome, candidata[3]))
    margine = 3.0
    fasce: List[Tuple[str, float, float]] = []
    for indice, (nome, alto) in enumerate(alti):
        basso = alti[indice + 1][1] + margine if indice + 1 < len(alti) else float("-inf")
        fasce.append((nome, basso, alto + margine if indice else float("inf")))
    return fasce


def _colonna_di(parola: tuple, colonne: List[Tuple[str, float, float]]) -> Optional[str]:
    """La colonna che contiene il centro della parola."""
    centro = (parola[1] + parola[3]) / 2
    for nome, basso, alto in colonne:
        if basso <= centro < alto:
            return nome
    return None


def _righe_pagina(pagina, colonne: List[Tuple[str, float, float]]) -> List[RigaSumUp]:
    parole = pagina.get_text("words")
    bordo_codice = next(alto for nome, _, alto in colonne if nome == "codice")
    # Fine della tabella: il piè di pagina di SumUp Limited.
    piede = min(
        (w[0] for w in parole if w[4] in ("Harcourt", "Istituto")),
        default=float("inf"),
    ) - 25
    inizi = sorted(
        w[0] for w in parole
        if _DATA_RIGA.match(w[4]) and w[1] > bordo_codice and w[0] < piede
    )
    righe: List[RigaSumUp] = []
    for indice, inizio in enumerate(inizi):
        fine = inizi[indice + 1] if indice + 1 < len(inizi) else piede
        celle: Dict[str, List[tuple]] = {nome: [] for nome, _, _ in colonne}
        for w in parole:
            if inizio - 1 <= w[0] < fine - 1:
                nome = _colonna_di(w, colonne)
                if nome:
                    celle[nome].append(w)

        def testo(nome: str) -> str:
            ordinate = sorted(celle[nome], key=lambda w: (round(w[0]), -w[1]))
            return " ".join(w[4] for w in ordinate).strip()

        data_parole = [w[4] for w in celle["data"]]
        data = next((t for t in data_parole if _DATA_RIGA.match(t)), None)
        ora = next((t for t in data_parole if _ORA.match(t)), "")
        codice = next((w[4] for w in celle["codice"] if _CODICE.match(w[4])), "")
        importi = {}
        for nome in ("uscita", "entrata", "commissione", "saldo"):
            valori = [w[4] for w in celle[nome] if _IMPORTO.match(w[4])]
            if len(valori) != 1:
                raise EstrattoSumUpNonValido(
                    f"Riga del {data}: colonna «{nome}» con {len(valori)} importi"
                )
            importi[nome] = _decimale(valori[0])
        if not data or not codice:
            raise EstrattoSumUpNonValido(f"Riga senza data o codice vicino a {data}")
        riferimento = testo("riferimento")
        causale = testo("causale")
        pid = _PID.search(f"{riferimento} {causale}")
        righe.append(RigaSumUp(
            data=_data_iso(data), ora=ora, codice=codice,
            tipo_transazione=testo("tipo"), riferimento=riferimento,
            causale=causale, stato=testo("stato"),
            uscita=importi["uscita"], entrata=importi["entrata"],
            commissione=importi["commissione"], saldo=importi["saldo"],
            pid=pid.group(0) if pid else None,
        ))
    return righe


def _valore_dopo(testo: str, etichetta: str) -> List[Decimal]:
    return [Decimal(v) for v in re.findall(re.escape(etichetta) + r"\s*(-?\d+\.\d{2})", testo)]


def leggi_estratto_sumup(pdf_bytes: bytes) -> EstrattoSumUp:
    """Legge il PDF e verifica la catena dei saldi. Solleva se non torna."""
    import fitz  # PyMuPDF

    try:
        documento = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # PDF danneggiato: il motivo va detto
        raise EstrattoSumUpNonValido(
            f"PDF non apribile ({type(exc).__name__}: {exc})"
        ) from exc
    testo_prima = documento[0].get_text("text") if len(documento) else ""
    if not e_estratto_sumup(testo_prima):
        raise EstrattoSumUpNonValido("Non è un estratto della carta SumUp")

    righe: List[RigaSumUp] = []
    colonne = None
    for pagina in documento:
        colonne = _colonne(pagina.get_text("words")) or colonne
        if colonne is not None:
            righe.extend(_righe_pagina(pagina, colonne))
    if not righe:
        raise EstrattoSumUpNonValido("Nessuna riga di movimento trovata")

    iban = _IBAN_SUMUP.search(testo_prima)
    utente = re.search(r"ID utente:\s*(\S+)", testo_prima)
    carta = re.search(r"Numero carta:\s*(\S+)", testo_prima)
    periodo = re.search(r"(\d{2}/\d{2}/\d{2})\s*-\s*(\d{2}/\d{2}/\d{2})", testo_prima)
    iniziali = _valore_dopo(testo_prima, "Saldo iniziale:")
    finali = _valore_dopo(testo_prima, "Saldo finale:")
    entrate = _valore_dopo(testo_prima, "Pagamenti in entrata:")
    uscite = _valore_dopo(testo_prima, "Pagamenti in uscita:")
    if not iniziali or not finali:
        raise EstrattoSumUpNonValido("Riepilogo senza saldo iniziale o finale")

    estratto = EstrattoSumUp(
        iban=iban.group(0) if iban else None,
        id_utente=utente.group(1) if utente else None,
        numero_carta=carta.group(1) if carta else None,
        periodo_dal=_data_iso(periodo.group(1)) if periodo else None,
        periodo_al=_data_iso(periodo.group(2)) if periodo else None,
        saldo_iniziale=iniziali[0],
        saldo_finale=finali[-1],
        totale_entrate=entrate[-1] if entrate else Decimal("0"),
        totale_uscite=uscite[-1] if uscite else Decimal("0"),
        righe=righe,
    )
    verifica_saldi(estratto)
    return estratto


def verifica_saldi(estratto: EstrattoSumUp) -> None:
    """La catena dei saldi, dalla riga più vecchia alla più recente.

    Le righe del PDF vanno dalla più recente alla più vecchia: si ripercorrono
    al contrario partendo dal saldo iniziale del riepilogo.
    """
    saldo = estratto.saldo_iniziale
    for riga in reversed(estratto.righe):
        atteso = saldo + riga.importo_netto
        if atteso != riga.saldo:
            raise EstrattoSumUpNonValido(
                f"Il saldo non torna al {riga.data} ({riga.codice}): "
                f"{saldo} + {riga.importo_netto} = {atteso}, sul PDF {riga.saldo}"
            )
        saldo = riga.saldo
    if saldo != estratto.saldo_finale:
        raise EstrattoSumUpNonValido(
            f"Saldo finale {estratto.saldo_finale} diverso dall'ultima riga {saldo}"
        )
    entrate = sum((r.entrata for r in estratto.righe), Decimal("0"))
    uscite = sum((r.uscita + r.commissione for r in estratto.righe), Decimal("0"))
    if entrate != estratto.totale_entrate or uscite != estratto.totale_uscite:
        raise EstrattoSumUpNonValido(
            f"Totali del riepilogo diversi dalle righe: entrate {entrate} contro "
            f"{estratto.totale_entrate}, uscite {uscite} contro {estratto.totale_uscite}"
        )


# --- Resoconto transazioni in CSV ------------------------------------------
#
# Lo stesso conto si scarica anche come «Resoconto_transazioni_<utente>_<data>.csv».
# Due stranezze che un ``csv.DictReader`` ingenuo non regge:
#
# - data e ora sono separate da una virgola libera (``26/09/26, 07:42,...``),
#   quindi finiscono in due campi;
# - una riga la cui causale contiene virgole arriva racchiusa per intero fra
#   virgolette, con quelle interne raddoppiate.
#
# Il CSV non ha il riepilogo del PDF: saldo iniziale e totali si ricavano
# dalle righe, e la prova resta la catena dei saldi riga per riga.

_COLONNE_RESOCONTO = ("codice transazione", "tipo transazione", "saldo disponibile")
# Stati in cui il denaro si e' mosso: un pagamento rifiutato o in attesa no.
_STATI_MOVIMENTATI = {"approvato", "pagamento in entrata", "rimborsata", "completato"}


def e_resoconto_sumup_csv(testo: str) -> bool:
    """Vero se la prima riga ha le colonne del resoconto SumUp."""
    prima = (testo or "").lstrip("﻿").splitlines()[:1]
    intestazione = prima[0].casefold() if prima else ""
    return all(colonna in intestazione for colonna in _COLONNE_RESOCONTO)


def _righe_csv(testo: str) -> List[List[str]]:
    import csv
    import io

    righe = []
    for riga in csv.reader(io.StringIO(testo.lstrip("﻿"))):
        if len(riga) == 1 and "," in riga[0]:
            # Riga intera fra virgolette: il contenuto e' a sua volta un CSV.
            riga = next(csv.reader(io.StringIO(riga[0])))
        if any(campo.strip() for campo in riga):
            righe.append([campo.strip() for campo in riga])
    return righe


def leggi_resoconto_sumup_csv(contenuto: bytes) -> EstrattoSumUp:
    """Legge il CSV e verifica la catena dei saldi. Solleva se non torna."""
    testo = None
    for codifica in ("utf-8-sig", "latin-1"):
        try:
            testo = contenuto.decode(codifica)
            break
        except UnicodeDecodeError:
            continue
    if not testo or not e_resoconto_sumup_csv(testo):
        raise EstrattoSumUpNonValido("Non è un resoconto transazioni SumUp")

    righe_csv = _righe_csv(testo)
    intestazione = righe_csv[0]
    righe: List[RigaSumUp] = []
    for campi_riga in righe_csv[1:]:
        ora = ""
        if len(campi_riga) == len(intestazione) + 1:
            # «26/09/26, 07:42» spezzato in due campi.
            ora = campi_riga[1]
            campi_riga = [campi_riga[0]] + campi_riga[2:]
        if len(campi_riga) != len(intestazione):
            raise EstrattoSumUpNonValido(
                f"Riga con {len(campi_riga)} colonne invece di {len(intestazione)}: "
                f"{','.join(campi_riga)[:80]}"
            )
        campi = dict(zip(intestazione, campi_riga))
        stato = campi.get("Stato", "")
        if stato.casefold() not in _STATI_MOVIMENTATI:
            continue
        data = campi.get("Data transazione", "")
        if not re.match(r"\d{2}/\d{2}/\d{2}", data):
            raise EstrattoSumUpNonValido(f"Data illeggibile: {data!r}")
        riferimento = re.sub(r"\s+", " ", campi.get("Riferimento", "")).strip()
        causale = re.sub(r"\s+", " ", campi.get("Causale pagamento", "")).strip()
        pid = _PID.search(f"{riferimento} {causale}")
        righe.append(RigaSumUp(
            data=_data_iso(data), ora=ora or data[10:].strip(),
            codice=campi.get("Codice transazione", ""),
            tipo_transazione=campi.get("Tipo transazione", ""),
            riferimento=riferimento, causale=causale, stato=stato,
            uscita=_decimale(campi.get("Importo transazione in uscita") or "0"),
            entrata=_decimale(campi.get("Importo transazione in entrata") or "0"),
            commissione=_decimale(campi.get("Commissione") or "0"),
            saldo=_decimale(campi.get("Saldo disponibile") or "0"),
            pid=pid.group(0) if pid else None,
        ))
    if not righe:
        raise EstrattoSumUpNonValido("Nessuna riga di movimento trovata")
    if any(not riga.codice for riga in righe):
        raise EstrattoSumUpNonValido("Riga senza codice transazione")

    # Le righe vanno dalla più recente alla più vecchia, come nel PDF.
    piu_vecchia = righe[-1]
    estratto = EstrattoSumUp(
        iban=None, id_utente=None, numero_carta=None,
        periodo_dal=piu_vecchia.data, periodo_al=righe[0].data,
        saldo_iniziale=piu_vecchia.saldo - piu_vecchia.importo_netto,
        saldo_finale=righe[0].saldo,
        totale_entrate=sum((r.entrata for r in righe), Decimal("0")),
        totale_uscite=sum((r.uscita + r.commissione for r in righe), Decimal("0")),
        righe=righe,
    )
    verifica_saldi(estratto)
    return estratto
