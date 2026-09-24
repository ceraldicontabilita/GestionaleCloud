"""Miglior fornitore per articolo, dalle righe delle fatture XML ricevute.

Idea presa dall'app «Ceraldi Ordini» (ordiniceraldi.netlify.app): un articolo
e' marca + prodotto + formato + confezione («ACQUA FERRARELLE CL.50 CTX24»),
ogni fornitore ha il suo prezzo e si ordina da chi costa meno. Li' il catalogo
era scritto a mano e l'abbinamento fra fornitori lo faceva un'AI sulla foto
della fattura; qui l'articolo nasce dalle righe XML e l'abbinamento e'
deterministico:

* **formato** letto dal testo: ``CL.50`` = ``50CL`` = ``ML500`` = 500 ml,
  ``LT.1,5`` = ``CL.150``, ``KG.3X6`` = 3 kg per 6 pezzi, ``CTX24``/``X24``
  = 24 pezzi. I numeri di lotto (``L.372``, ``LOTTO 111``) non sono litri;
* **parole** dell'articolo senza rumore (VAP, CTX, paese d'origine, gradi
  alcolici) e senza le parole generiche (ACQUA, BIRRA, VINO...);
* stesso formato e stesse parole = **stesso articolo, certo**. Parole di un
  fornitore tutte contenute in quelle dell'altro, con le parole in piu' non
  distintive (una variante, un gusto) = **probabile**: non si accorpa da solo,
  si propone e decide una persona (``esito="stesso"`` o ``"diverso"``).

Il prezzo si confronta **per pezzo** (bottiglia, lattina, sacco), mai al litro
o al chilo per le bevande: il prezzo unitario di fattura vale per il cartone
se l'unita' di misura e' un cartone, oppure se la confezione dichiara N pezzi e
la quantita' fatturata e' minore di N. Se in un gruppo i prezzi per pezzo
distano piu' di tre volte, le unita' di fattura non sono confrontabili: il
gruppo lo dice e non sceglie un migliore invece di indovinare.

Importi in ``Decimal``; all'uscita stringhe con quattro decimali.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple

VALUTA = "EUR"
Q4 = Decimal("0.0001")

# ── lettura della descrizione ───────────────────────────────────────────────

_MOJIBAKE = {"Ã¬": "I", "Ã¨": "E", "Ã©": "E", "Ã ": "A", "Ã²": "O", "Ã¹": "U", "Â°": "°", "ï¿½": " "}

# Codici di lotto e date che non fanno parte dell'articolo
_RX_LOTTO = re.compile(
    r"\bLOTTO\s*[\w/.\-]+"
    r"|\bL\.?\s?(?=\d{3,}|\d+[-/])[\w/.\-]+"
    r"|\bSCAD\.?\s*[\d/.\-]+"
    r"|\(\s*[\dA-Z]{5,}\s*\)"
)
# Gradi alcolici e percentuali: «43°», «17.5°», «21%», «gr° 4.8»
_RX_GRADI = re.compile(r"(?:GR°\s*)?\d+(?:[.,]\d+)?\s*(?:°|%\s*VOL|%)")

_NUM = r"(\d+(?:[.,]\d+)?)"
_UNITA_VOLUME = {"ML": Decimal(1), "CL": Decimal(10), "LT": Decimal(1000), "L": Decimal(1000)}
_UNITA_PESO = {"GR": Decimal(1), "G": Decimal(1), "KG": Decimal(1000)}
# unita' prima del numero («CL.50», «KG 3») o dopo («50CL», «1,5L»)
_RX_MISURA_PRIMA = re.compile(r"\b(ML|CL|LT|L|KG|GR|G)\s*\.?\s*" + _NUM + r"(?![\d])")
_RX_MISURA_DOPO = re.compile(r"(?<![\w.,])" + _NUM + r"\s*(ML|CL|LT|L|KG|GR|G)\b")
# confezione: «CTX24», «X24», «X 24», «24PZ», «PZ.24», «8BT»
_RX_PEZZI = re.compile(r"(?:CTX|CT\s*X|X)\s*(\d{1,3})(?!\d)(?:\s*(?:PZ|BT)\b)?|\b(?:PZ|CONF)\.?\s*(\d{1,3})\b|\b(\d{1,3})\s*(?:PZ|BT)\b")

_RUMORE = {
    "VAP", "CTX", "CT", "CF", "PZ", "BT", "X", "DA", "DI", "DEL", "DELLA", "IN", "CON", "E", "ED",
    "LA", "IL", "LE", "LO", "AL", "ALLA", "CONF", "CONFEZIONE", "CARTONE", "FORMATO", "NR", "N",
    "TIPO", "PER", "ART", "COD",
    # paese d'origine che alcuni fornitori aggiungono al nome
    "ITALIA", "GERMANIA", "OLANDA", "BELGIO", "SCOZIA", "MESSICO", "DANIMARCA", "CUBA", "VENEZUELA",
    "IRLANDA", "FRANCIA", "SPAGNA", "GRECIA", "INGHILTERRA", "USA",
}
# parole di categoria: il fornitore A scrive «ACQUA FERRARELLE», B «FERRARELLE»
_GENERICHE = {
    "ACQUA", "BIRRA", "VINO", "LIQUORE", "APERITIVO", "AMARO", "BIBITA", "BEVANDA", "SUCCO",
    "SCIROPPO", "BOTT", "BOTTIGLIA",
}
# una variante: se una descrizione la ha e l'altra no, non e' lo stesso articolo
_VARIANTI = {
    "ZERO", "LIGHT", "DIET", "DEK", "DECA", "DECAFFEINATO", "SENZA", "BIO", "BIOLOGICO", "BIOLOGICA",
    "INTEGRALE", "ROSSO", "ROSSA", "BIANCO", "BIANCA", "ROSE", "ROSATO", "NERO", "NERA", "BRUT",
    "DOLCE", "SECCO", "AMABILE", "LIMONE", "PESCA", "ARANCIA", "ARANCIATA", "LIMONATA", "POMPELMO",
    "FRAGOLA", "LAMPONE", "COCCO", "MANGO", "ANANAS", "MELA", "PERA", "ALBICOCCA", "MIRTILLO",
    "BANANA", "ACE", "CEDRATA", "TONICA", "TONICAZERO", "GINGER", "CHINOTTO", "MENTA", "VANIGLIA",
    "CARAMELLO", "NOCCIOLA", "PISTACCHIO", "CIOCCOLATO", "CAFFE", "AMARENA", "NATURALE", "FRIZZANTE",
    "GASSATA", "EFFERVESCENTE", "LEGGERMENTE", "MAXI", "MINI", "MIGNON", "GRANDE", "GRANDI",
    "PICCOLO", "PICCOLA", "PICCOLI", "SURGELATO", "SURGELATA", "CONGELATO", "CONGELATA", "FRESCO",
    "FRESCA", "ANALCOLICO", "RISERVA", "SPECIALE", "GOLD", "SILVER", "PLUS", "PREMIUM",
}
# abbreviazioni lette nelle fatture vere: si riportano alla parola intera
_SINONIMI = {
    "TONIC": ("TONICA",), "TONICAZERO": ("TONICA", "ZERO"), "EXTRAV": ("EXTRAVERGINE",),
    "VEG": ("VEGETALE",), "MARG": ("MARGARINA",), "MARGAR": ("MARGARINA",),
    "MASTROBER": ("MASTROBERARDINO",), "NAT": ("NATURALE",), "FRIZZ": ("FRIZZANTE",),
    "INT": ("INTERO",), "SCR": ("SCREMATO",),
}
# contenitore: in conflitto solo se entrambe lo dicono e dicono cose diverse
_CONTENITORI = {"VETRO": "vetro", "VETR": "vetro", "LATTINA": "lattina", "LATTA": "lattina",
                "LATT": "lattina", "SLEEK": "lattina", "PET": "pet", "PLASTICA": "pet"}

_CODICI_CARTONE = {
    "CT", "CF", "CS", "CX", "CRT", "KRT", "KAR", "CA", "COL", "CARTONI", "CARTONE", "CONFEZIONI",
    "CASSA", "CASSE", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9",
}
_CODICI_PESO = {"KG", "KGM", "KGS"}

_RX_SERVIZI = re.compile(
    r"spese|trasport|spedizion|boll[oi]\b|imposta|conai|cauzion|omaggi|arrotondament|acconto|sconto|abbuono|"
    r"canone|noleggio|consulenz|onorario|compenso|manodopera|installazion|contributo|commission|"
    r"rif\.|riferimento|ns\.? ?ordine|ordine cl|riga ausiliaria|ddt|scontrino|interessi|ricarica|"
    r"abbonament|servizio|liquidaz|accisa|nota (?:di )?(?:credito|debito)|storno|colli \d",
    re.IGNORECASE,
)


def _decimale(valore: Any) -> Optional[Decimal]:
    if valore is None or valore == "":
        return None
    try:
        return Decimal(str(valore).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def pulisci(testo: Any) -> str:
    """Prima riga, maiuscolo, senza accenti ne' caratteri rotti dalla codifica."""
    riga = str(testo or "").strip().split("\n", 1)[0]
    for rotto, giusto in _MOJIBAKE.items():
        riga = riga.replace(rotto, giusto)
    riga = unicodedata.normalize("NFKD", riga)
    riga = "".join(c for c in riga if not unicodedata.combining(c))
    riga = riga.upper().replace("’", "'").replace("`", "'")
    riga = re.sub(r"^[*/.\s]+", "", riga)
    return re.sub(r"\s+", " ", riga).strip()


@dataclass(frozen=True)
class Articolo:
    """Una descrizione di fattura letta: parole, formato, pezzi per confezione."""

    descrizione: str
    parole: Tuple[str, ...]
    misura: Optional[Decimal] = None      # ml oppure g
    unita: str = ""                       # "ml" | "g" | ""
    pezzi: Optional[int] = None           # pezzi per confezione (cartone)
    contenitore: str = ""

    @property
    def chiave(self) -> str:
        misura = f"{self.misura.normalize():f}{self.unita}" if self.misura else "-"
        return f"{' '.join(self.parole)}|{misura}|x{self.pezzi or '?'}"

    @property
    def formato(self) -> str:
        if not self.misura:
            testo = ""
        elif self.unita == "ml":
            testo = f"{_fmt(self.misura / 1000)} L" if self.misura >= 1000 else f"{_fmt(self.misura / 10)} cl"
        else:
            testo = f"{_fmt(self.misura / 1000)} kg" if self.misura >= 1000 else f"{_fmt(self.misura)} g"
        if self.pezzi and self.pezzi > 1:
            testo = f"{testo} × {self.pezzi}".strip()
        return testo


def _fmt(valore: Decimal) -> str:
    testo = f"{valore.normalize():f}"
    return testo.replace(".", ",")


def leggi(descrizione: Any) -> Articolo:
    """Descrizione di fattura → articolo confrontabile."""
    testo = pulisci(descrizione)
    lavoro = _RX_LOTTO.sub(" ", testo)
    lavoro = _RX_GRADI.sub(" ", lavoro)
    lavoro = lavoro.replace("'", " ")
    lavoro = re.sub(r"(?<=[A-Z])-(?=[A-Z])", " ", lavoro)     # FEVER-TREE, COCA-COLA

    misura: Optional[Decimal] = None
    unita = ""
    trovata = _RX_MISURA_PRIMA.search(lavoro) or _RX_MISURA_DOPO.search(lavoro)
    if trovata:
        gruppi = trovata.groups()
        sigla, numero = (gruppi[0], gruppi[1]) if trovata.re is _RX_MISURA_PRIMA else (gruppi[1], gruppi[0])
        valore = _decimale(numero)
        if valore and valore > 0:
            if sigla in _UNITA_VOLUME:
                misura, unita = valore * _UNITA_VOLUME[sigla], "ml"
            else:
                misura, unita = valore * _UNITA_PESO[sigla], "g"
        # il resto della stringa dopo la misura: «CL33X24», «KG.3X6»
        coda = lavoro[trovata.end():]
        lavoro = lavoro[:trovata.start()] + " " + coda

    pezzi: Optional[int] = None
    prodotto = 1
    for m in _RX_PEZZI.finditer(lavoro):
        n = next((int(g) for g in m.groups() if g), 0)
        if n > 1:
            prodotto *= n
    if prodotto > 1:
        pezzi = prodotto
    lavoro = _RX_PEZZI.sub(" ", lavoro)

    parole: List[str] = []
    contenitore = ""
    grezze: List[str] = []
    for parola in re.split(r"[^A-Z0-9]+", lavoro):
        grezze.extend(_SINONIMI.get(parola, (parola,)))
    for parola in grezze:
        if not parola or parola in _RUMORE or len(parola) < 2 and not parola.isdigit():
            continue
        if parola in _CONTENITORI:
            contenitore = contenitore or _CONTENITORI[parola]
            continue
        if parola in _GENERICHE:
            continue
        if parola not in parole:
            parole.append(parola)
    return Articolo(
        descrizione=re.sub(r"\s+", " ", _RX_LOTTO.sub(" ", testo)).strip(" -.,"),
        parole=tuple(sorted(parole)),
        misura=misura,
        unita=unita,
        pezzi=pezzi,
        contenitore=contenitore,
    )


# ── stesso articolo? ────────────────────────────────────────────────────────


def _uguali(a: str, b: str) -> bool:
    """Stessa parola, o una e' il troncamento dell'altra (PANIFIC/PANIFICAZIONE).

    Mai per una variante: TONICA non e' l'abbreviazione di TONICAZERO.
    """
    if a == b:
        return True
    if a in _VARIANTI or b in _VARIANTI:
        return False
    corta, lunga = (a, b) if len(a) <= len(b) else (b, a)
    return len(corta) >= 4 and lunga.startswith(corta) and not corta.isdigit()


def _copertura(piccolo: Iterable[str], grande: Iterable[str]) -> Tuple[bool, List[str]]:
    """Ogni parola di `piccolo` ha la sua in `grande`? E quali avanzano in `grande`."""
    grande = list(grande)
    usate: set = set()
    for p in piccolo:
        trovata = next((g for g in grande if g not in usate and _uguali(p, g)), None)
        if trovata is None:
            return False, []
        usate.add(trovata)
    return True, [g for g in grande if g not in usate]


def confronta(a: Articolo, b: Articolo) -> Optional[str]:
    """``"certo"``, ``"probabile"`` oppure ``None``.

    Formato e confezione devono coincidere (una confezione ignota e'
    compatibile); il contenitore, se detto da entrambi, pure.
    """
    if not a.parole or not b.parole:
        return None
    if (a.misura or b.misura) and (a.misura != b.misura or a.unita != b.unita):
        return None
    if a.pezzi and b.pezzi and a.pezzi != b.pezzi:
        return None
    if a.contenitore and b.contenitore and a.contenitore != b.contenitore:
        return None
    piccolo, grande = (a.parole, b.parole) if len(a.parole) <= len(b.parole) else (b.parole, a.parole)
    coperto, avanzi = _copertura(piccolo, grande)
    if not coperto:
        return None
    if not avanzi:
        return "certo"
    if any(p in _VARIANTI or p.isdigit() or any(c.isdigit() for c in p) for p in avanzi):
        return None
    if not a.misura:
        # senza formato non si propone niente: «PASTA» e «PASTA DE CECCO» non bastano
        return None
    if not any(len(p) >= 3 for p in piccolo):
        return None
    return "probabile"


# ── prezzi dalle righe ──────────────────────────────────────────────────────


@dataclass
class Acquisto:
    fornitore: str
    fornitore_id: str
    data: str
    articolo: Articolo
    prezzo_fattura: Decimal
    unita_fattura: str
    quantita: Optional[Decimal]
    prezzo_pezzo: Decimal
    per_cartone: bool
    fattura_id: str = ""
    numero_fattura: str = ""
    aliquota_iva: str = ""


def prezzo_per_pezzo(art: Articolo, prezzo: Decimal, unita: str, quantita: Optional[Decimal]) -> Tuple[Decimal, bool]:
    """Il prezzo unitario di fattura riportato a un pezzo. Torna (prezzo, era_per_cartone)."""
    unita = (unita or "").strip().upper().rstrip(".")
    if unita in _CODICI_PESO and art.unita == "g" and art.misura:
        return (prezzo * art.misura / Decimal(1000)).quantize(Q4), False
    if art.pezzi and art.pezzi > 1:
        per_cartone = unita in _CODICI_CARTONE or (quantita is not None and quantita < art.pezzi)
        if per_cartone:
            return (prezzo / Decimal(art.pezzi)).quantize(Q4), True
    return prezzo.quantize(Q4), False


def _data_iso(valore: Any) -> str:
    testo = str(valore or "").strip()[:10]
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(testo, formato).date().isoformat()
        except ValueError:
            continue
    return testo


def chiave_fornitore(nome: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", pulisci(nome)).strip()


def identita_fornitore(fattura: Dict[str, Any], nome: str) -> str:
    """Il fornitore e' la sua partita IVA; il nome solo se la P.IVA manca."""
    piva = re.sub(r"[^0-9A-Z]", "", str(
        fattura.get("supplier_vat") or fattura.get("cedente_piva") or fattura.get("fornitore_partita_iva") or ""
    ).upper())
    piva = re.sub(r"^IT(?=\d{11}$)", "", piva)
    return f"piva:{piva}" if piva else f"nome:{chiave_fornitore(nome)}"


_TIPI_NOTA_CREDITO = {"TD04", "TD08"}


def acquisti_da_fatture(fatture: Iterable[Dict[str, Any]]) -> List[Acquisto]:
    """Le righe merce delle fatture ricevute (note di credito escluse)."""
    out: List[Acquisto] = []
    for f in fatture:
        if str(f.get("tipo_documento") or f.get("document_type") or "").upper() in _TIPI_NOTA_CREDITO:
            continue
        fornitore = str(f.get("supplier_name") or f.get("cedente_denominazione") or f.get("fornitore") or "").strip().strip('"').strip()
        if not fornitore:
            continue
        fornitore_id = identita_fornitore(f, fornitore)
        data = _data_iso(f.get("invoice_date") or f.get("data_documento") or f.get("data_fattura"))
        righe = f.get("linee") or f.get("righe") or f.get("prodotti") or f.get("lines") or []
        for riga in righe if isinstance(righe, list) else []:
            if not isinstance(riga, dict):
                continue
            descrizione = riga.get("descrizione") or riga.get("description") or ""
            if not str(descrizione).strip() or _RX_SERVIZI.search(str(descrizione)):
                continue
            prezzo = _decimale(riga.get("prezzo_unitario") or riga.get("unit_price"))
            quantita = _decimale(riga.get("quantita") or riga.get("quantity"))
            if prezzo is None or prezzo <= 0 or (quantita is not None and quantita <= 0):
                continue
            art = leggi(descrizione)
            if not art.parole:
                continue
            unita = str(riga.get("unita_misura") or riga.get("unit") or "").strip()
            pezzo, per_cartone = prezzo_per_pezzo(art, prezzo, unita, quantita)
            out.append(Acquisto(
                fornitore=fornitore,
                fornitore_id=fornitore_id,
                data=data,
                articolo=art,
                prezzo_fattura=prezzo.quantize(Q4),
                unita_fattura=unita.upper(),
                quantita=quantita,
                prezzo_pezzo=pezzo,
                per_cartone=per_cartone,
                fattura_id=str(f.get("id") or ""),
                numero_fattura=str(f.get("invoice_number") or f.get("numero_fattura") or ""),
                aliquota_iva=str(riga.get("aliquota_iva") or "").strip(),
            ))
    return out


# ── gruppi e miglior fornitore ──────────────────────────────────────────────


class _Insiemi:
    def __init__(self) -> None:
        self.padre: Dict[str, str] = {}

    def trova(self, x: str) -> str:
        self.padre.setdefault(x, x)
        while self.padre[x] != x:
            self.padre[x] = self.padre[self.padre[x]]
            x = self.padre[x]
        return x

    def unisci(self, a: str, b: str) -> None:
        ra, rb = self.trova(a), self.trova(b)
        if ra != rb:
            self.padre[max(ra, rb)] = min(ra, rb)


def _coppia(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a <= b else (b, a)


@dataclass
class Decisioni:
    stesso: set = field(default_factory=set)     # coppie di chiavi
    diverso: set = field(default_factory=set)

    @classmethod
    def da_documenti(cls, docs: Iterable[Dict[str, Any]]) -> "Decisioni":
        d = cls()
        for doc in docs:
            chiavi = doc.get("chiavi") or []
            if len(chiavi) != 2:
                continue
            coppia = _coppia(str(chiavi[0]), str(chiavi[1]))
            if doc.get("esito") == "stesso":
                d.stesso.add(coppia)
                d.diverso.discard(coppia)
            elif doc.get("esito") == "diverso":
                d.diverso.add(coppia)
                d.stesso.discard(coppia)
        return d


def raggruppa(acquisti: List[Acquisto], decisioni: Optional[Decisioni] = None) -> Tuple[Dict[str, List[Acquisto]], List[Tuple[Articolo, Articolo]]]:
    """Gruppi di acquisti dello stesso articolo e coppie probabili da decidere."""
    decisioni = decisioni or Decisioni()
    per_chiave: Dict[str, List[Acquisto]] = {}
    articoli: Dict[str, Articolo] = {}
    fornitori_chiave: Dict[str, set] = {}
    for a in acquisti:
        per_chiave.setdefault(a.articolo.chiave, []).append(a)
        articoli.setdefault(a.articolo.chiave, a.articolo)
        fornitori_chiave.setdefault(a.articolo.chiave, set()).add(a.fornitore_id)

    insiemi = _Insiemi()
    for k in articoli:
        insiemi.trova(k)
    # stesso formato: si confrontano solo gli articoli con la stessa misura
    per_misura: Dict[str, List[str]] = {}
    for k, art in articoli.items():
        if art.misura:
            # senza formato vale solo la chiave identica: nessun confronto a coppie
            per_misura.setdefault(f"{art.misura}{art.unita}", []).append(k)
    probabili: List[Tuple[Articolo, Articolo]] = []
    for chiavi in per_misura.values():
        chiavi.sort()
        for i, ka in enumerate(chiavi):
            for kb in chiavi[i + 1:]:
                coppia = _coppia(ka, kb)
                if coppia in decisioni.diverso:
                    continue
                esito = confronta(articoli[ka], articoli[kb])
                if esito == "certo" or coppia in decisioni.stesso:
                    insiemi.unisci(ka, kb)
                elif esito == "probabile" and fornitori_chiave[ka] != fornitori_chiave[kb]:
                    probabili.append((articoli[ka], articoli[kb]))
    # decisioni «stesso» fra formati diversi non esistono: il formato decide
    gruppi: Dict[str, List[Acquisto]] = {}
    for k, lista in per_chiave.items():
        gruppi.setdefault(insiemi.trova(k), []).extend(lista)
    # una coppia probabile gia' finita nello stesso gruppo non va chiesta
    probabili = [(a, b) for a, b in probabili if insiemi.trova(a.chiave) != insiemi.trova(b.chiave)]
    return gruppi, probabili


def _q(valore: Optional[Decimal]) -> Optional[str]:
    return None if valore is None else f"{valore.quantize(Q4):f}"


RAPPORTO_MASSIMO = Decimal(3)


def riepilogo_gruppo(acquisti: List[Acquisto]) -> Dict[str, Any]:
    """L'articolo con l'ultimo prezzo di ogni fornitore e il migliore."""
    per_fornitore: Dict[str, List[Acquisto]] = {}
    for a in acquisti:
        per_fornitore.setdefault(a.fornitore_id, []).append(a)
    righe = []
    for lista in per_fornitore.values():
        lista.sort(key=lambda a: (a.data, a.fattura_id))
        ultimo = lista[-1]
        prezzi = [a.prezzo_pezzo for a in lista]
        righe.append({
            "fornitore": ultimo.fornitore,
            "fornitore_id": ultimo.fornitore_id,
            "descrizione": ultimo.articolo.descrizione,
            "prezzo_pezzo": _q(ultimo.prezzo_pezzo),
            "prezzo_confezione": _q(ultimo.prezzo_pezzo * ultimo.articolo.pezzi) if ultimo.articolo.pezzi else None,
            "prezzo_fattura": _q(ultimo.prezzo_fattura),
            "unita_fattura": ultimo.unita_fattura,
            "per_cartone": ultimo.per_cartone,
            "data": ultimo.data,
            "numero_fattura": ultimo.numero_fattura,
            "fattura_id": ultimo.fattura_id,
            "aliquota_iva": ultimo.aliquota_iva,
            "acquisti": len(lista),
            "prezzo_min": _q(min(prezzi)),
            "prezzo_max": _q(max(prezzi)),
            "_pezzo": ultimo.prezzo_pezzo,
        })
    # a parita' di prezzo vince la fattura piu' recente (chi fornisce oggi)
    righe.sort(key=lambda r: (r["data"], r["fornitore"]), reverse=True)
    righe.sort(key=lambda r: r["_pezzo"])
    confrontabile = True
    motivo = ""
    if len(righe) > 1:
        minimo, massimo = righe[0]["_pezzo"], righe[-1]["_pezzo"]
        if minimo > 0 and massimo / minimo > RAPPORTO_MASSIMO:
            confrontabile = False
            motivo = ("Prezzi per pezzo troppo distanti: le unita' di fattura non sono "
                      "confrontabili (cartone contro pezzo). Da verificare sulla fattura.")
    migliore = righe[0]["fornitore"] if len(righe) > 1 and confrontabile else None
    risparmio = None
    if migliore:
        risparmio = righe[1]["_pezzo"] - righe[0]["_pezzo"]
    pari_merito = bool(migliore) and risparmio == 0
    for r in righe:
        r.pop("_pezzo")
    # nome: la descrizione piu' recente del fornitore migliore (o del primo)
    art = max(acquisti, key=lambda a: (a.fornitore_id == righe[0]["fornitore_id"], a.data)).articolo
    return {
        "chiave": art.chiave,
        "nome": art.descrizione,
        "formato": art.formato,
        "pezzi": art.pezzi,
        "n_fornitori": len(righe),
        "migliore": migliore,
        "risparmio_pezzo": _q(risparmio),
        "pari_merito": pari_merito,
        "confrontabile": confrontabile,
        "motivo": motivo,
        "valuta": VALUTA,
        "fornitori": righe,
        "chiavi": sorted({a.articolo.chiave for a in acquisti}),
        "ultima_data": max(a.data for a in acquisti),
    }


def proposta(a: Articolo, b: Articolo, acquisti_per_chiave: Dict[str, List[Acquisto]]) -> Dict[str, Any]:
    def lato(art: Articolo) -> Dict[str, Any]:
        lista = sorted(acquisti_per_chiave.get(art.chiave, []), key=lambda x: x.data)
        ultimo = lista[-1] if lista else None
        return {
            "chiave": art.chiave,
            "descrizione": art.descrizione,
            "formato": art.formato,
            "fornitori": sorted({x.fornitore for x in lista}),
            "prezzo_pezzo": _q(ultimo.prezzo_pezzo) if ultimo else None,
            "data": ultimo.data if ultimo else "",
        }
    return {"a": lato(a), "b": lato(b), "chiavi": list(_coppia(a.chiave, b.chiave))}


# ── cache in memoria ────────────────────────────────────────────────────────

_TTL = 120.0
_cache: Dict[str, Any] = {"at": 0.0, "acquisti": None}


def invalida_cache() -> None:
    _cache["at"] = 0.0
    _cache["acquisti"] = None


def cache_valida() -> bool:
    return _cache["acquisti"] is not None and time.monotonic() - _cache["at"] < _TTL


def salva_cache(acquisti: List[Acquisto]) -> None:
    _cache["acquisti"] = acquisti
    _cache["at"] = time.monotonic()
