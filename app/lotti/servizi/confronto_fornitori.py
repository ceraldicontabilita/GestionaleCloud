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

Accanto alle fatture entrano i **listini** dei fornitori (``origine="listino"``,
per esempio il catalogo riservato Barone): prezzo dichiarato oggi, con la sua
data, mai confuso con un prezzo pagato. Il prezzo di listino vale per l'unita'
scritta dal fornitore («12 PZ» = 12 pezzi), poi segue le stesse regole della
fattura.

La **lettura AI** (``servizi/lettura_articoli_ai.py``) legge ogni descrizione
una volta sola: completa formato e confezione quando il testo li scrive in un
modo che le espressioni regolari non capiscono, e da' a ogni articolo marca e
prodotto standard. Due descrizioni con la stessa lettura (marca, prodotto,
variante, formato, confezione) sono lo stesso articolo anche se il testo e'
diverso: l'abbinamento si dichiara (``abbinato_ai``) e una persona lo puo'
sciogliere con ``esito="diverso"``.

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
        chiave = f"{' '.join(self.parole)}|{misura}|x{self.pezzi or '?'}"
        # vetro e lattina hanno prezzi diversi: il contenitore scritto fa parte dell'articolo
        return f"{chiave}|{self.contenitore}" if self.contenitore else chiave

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
    origine: str = "fattura"          # "fattura" | "listino"
    descrizione_originale: str = ""   # il testo come scritto, chiave della lettura AI
    cartone_senza_pezzi: bool = False  # fatturato a cartone, pezzi per cartone non scritti
    # solo listino
    fornitore_key: str = ""
    codice_articolo: str = ""
    ean: str = ""
    link: str = ""
    unita_vendita: str = ""
    pezzi_vendita: int = 1
    offerta_fino: str = ""
    # lettura AI
    chiave_ai: str = ""
    nome_ai: str = ""


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
            codice_unita = unita.strip().upper().rstrip(".")
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
                descrizione_originale=str(descrizione),
                cartone_senza_pezzi=codice_unita in _CODICI_CARTONE and not art.pezzi,
            ))
    return out


# ── listini dei fornitori ───────────────────────────────────────────────────


def prezzo_listino_per_pezzo(art: Articolo, prezzo: Decimal, pezzi_vendita: int, sigla: str) -> Tuple[Decimal, bool]:
    """Prezzo di listino → prezzo per pezzo, con le regole della fattura.

    Il prezzo vale per ``pezzi_vendita`` unita' della sigla scritta («12 PZ»
    a 8,52 € = 0,71 € l'uno); una unita' «CT» di un articolo «X24» e' un
    cartone da 24; «KG» e' il prezzo al chilo."""
    n = pezzi_vendita if pezzi_vendita and pezzi_vendita > 0 else 1
    return prezzo_per_pezzo(art, prezzo / Decimal(n), sigla, None)


def acquisti_da_listini(prodotti: Iterable[Dict[str, Any]], fonti: Iterable[Dict[str, Any]]) -> List[Acquisto]:
    """Gli articoli dei listini (``catalogo_forno_prodotti`` con ``prezzo_listino``).

    Il fornitore e' la fonte del listino: nome e partita IVA dal registro dei
    cataloghi, cosi' un listino e le fatture dello stesso fornitore sono una
    riga sola nel confronto (vince la data piu' recente)."""
    per_chiave = {str(f.get("fornitore_key") or ""): f for f in fonti}
    out: List[Acquisto] = []
    for p in prodotti:
        if p.get("nel_listino") is False:
            continue
        prezzo = _decimale(p.get("prezzo_listino"))
        if prezzo is None or prezzo <= 0:
            continue
        key = str(p.get("fornitore") or "")
        fonte = per_chiave.get(key) or {}
        nome = str(fonte.get("nome") or p.get("fornitore_nome") or key).strip()
        if not nome:
            continue
        descrizione = str(p.get("nome_completo") or p.get("nome") or "")
        art = leggi(descrizione)
        if not art.parole:
            continue
        piva = fonte.get("partita_iva") or ""
        fornitore_id = identita_fornitore({"supplier_vat": piva}, nome)
        pezzi_vendita = int(p.get("pezzi_vendita") or 1)
        sigla = str(p.get("sigla_unita") or "")
        pezzo, per_cartone = prezzo_listino_per_pezzo(art, prezzo, pezzi_vendita, sigla)
        out.append(Acquisto(
            fornitore=nome,
            fornitore_id=fornitore_id,
            data=_data_iso(p.get("prezzo_listino_data")),
            articolo=art,
            prezzo_fattura=prezzo.quantize(Q4),
            unita_fattura=sigla,
            quantita=None,
            prezzo_pezzo=pezzo,
            per_cartone=per_cartone or pezzi_vendita > 1,
            aliquota_iva=str(p.get("aliquota_iva") if p.get("aliquota_iva") is not None else ""),
            origine="listino",
            descrizione_originale=descrizione,
            fornitore_key=key,
            codice_articolo=str(p.get("codice_articolo") or ""),
            ean=str(p.get("ean") or ""),
            link=str(p.get("link_prodotto") or ""),
            unita_vendita=str(p.get("unita_vendita") or sigla),
            pezzi_vendita=pezzi_vendita,
            offerta_fino=str(p.get("offerta_fino") or ""),
        ))
    return out


# ── lettura AI applicata agli acquisti ──────────────────────────────────────

_PAROLE_VUOTE_AI = _RUMORE | {"ALL", "ALLO", "AI", "AGLI", "DELLE", "DEI", "DEGLI", "SU", "A", "UN", "UNA", "O"}


def impronta_descrizione(descrizione: Any) -> str:
    """Chiave della lettura AI: il testo ripulito (prima riga, maiuscolo)."""
    import hashlib

    return hashlib.sha256(pulisci(descrizione).encode("utf-8")).hexdigest()[:32]


def _parole_ai(testo: Any) -> List[str]:
    parole = re.split(r"[^A-Z0-9]+", pulisci(testo).replace("'", " "))
    return sorted({p for p in parole if p and p not in _PAROLE_VUOTE_AI and (len(p) > 1 or p.isdigit())})


def chiave_da_lettura(lettura: Dict[str, Any], art: Articolo) -> str:
    """Marca + prodotto + variante + formato + confezione: la stessa per due
    descrizioni diverse dello stesso articolo. Vuota se la lettura non basta."""
    if not lettura or lettura.get("servizio"):
        return ""
    prodotto = _parole_ai(lettura.get("prodotto"))
    if not prodotto:
        return ""
    marca = "".join(_parole_ai(lettura.get("marca")))
    variante = " ".join(_parole_ai(lettura.get("variante")))
    misura = f"{art.misura.normalize():f}{art.unita}" if art.misura else "-"
    return f"ai:{marca}|{' '.join(prodotto)}|{variante}|{misura}|x{art.pezzi or '?'}"


def _completa_articolo(art: Articolo, lettura: Dict[str, Any]) -> Articolo:
    """Formato e confezione dalla lettura AI, solo dove il testo non li ha dati
    alle espressioni regolari. Mai al posto di un dato gia' letto."""
    from dataclasses import replace

    misura, unita, pezzi = art.misura, art.unita, art.pezzi
    if misura is None:
        valore = _decimale(lettura.get("misura"))
        if valore and valore > 0 and lettura.get("unita") in ("g", "ml"):
            misura, unita = valore, lettura["unita"]
    if pezzi is None:
        try:
            n = int(lettura.get("pezzi") or 0)
        except (TypeError, ValueError):
            n = 0
        if n > 1:
            pezzi = n
    if (misura, unita, pezzi) == (art.misura, art.unita, art.pezzi):
        return art
    return replace(art, misura=misura, unita=unita, pezzi=pezzi)


def applica_letture(acquisti: List[Acquisto], letture: Dict[str, Dict[str, Any]]) -> List[Acquisto]:
    """Acquisti con formato completato, nome standard e chiave AI."""
    from dataclasses import replace

    if not letture:
        return acquisti
    out: List[Acquisto] = []
    for a in acquisti:
        lettura = letture.get(impronta_descrizione(a.descrizione_originale or a.articolo.descrizione))
        if not lettura or lettura.get("servizio"):
            out.append(a)
            continue
        art = _completa_articolo(a.articolo, lettura)
        if art is not a.articolo:
            if a.origine == "listino":
                pezzo, per_cartone = prezzo_listino_per_pezzo(art, a.prezzo_fattura, a.pezzi_vendita, a.unita_fattura)
                per_cartone = per_cartone or a.pezzi_vendita > 1
            else:
                pezzo, per_cartone = prezzo_per_pezzo(art, a.prezzo_fattura, a.unita_fattura, a.quantita)
            a = replace(a, articolo=art, prezzo_pezzo=pezzo, per_cartone=per_cartone,
                        cartone_senza_pezzi=a.cartone_senza_pezzi and not art.pezzi)
        out.append(replace(a, chiave_ai=chiave_da_lettura(lettura, art), nome_ai=str(lettura.get("nome") or "").strip()))
    return out


# ── gruppi e miglior fornitore ──────────────────────────────────────────────


class _Insiemi:
    """Unione di chiavi. Un gruppo che contiene «vetro» non si unisce mai a uno
    che contiene «lattina», nemmeno passando per una descrizione che il
    contenitore non lo dice (la transitivita' li mescolava)."""

    def __init__(self, contenitori: Optional[Dict[str, str]] = None) -> None:
        self.padre: Dict[str, str] = {}
        self.contenitori: Dict[str, set] = {k: {c} for k, c in (contenitori or {}).items() if c}

    def trova(self, x: str) -> str:
        self.padre.setdefault(x, x)
        while self.padre[x] != x:
            self.padre[x] = self.padre[self.padre[x]]
            x = self.padre[x]
        return x

    def unisci(self, a: str, b: str) -> bool:
        ra, rb = self.trova(a), self.trova(b)
        if ra == rb:
            return True
        ca, cb = self.contenitori.get(ra, set()), self.contenitori.get(rb, set())
        if ca and cb and ca != cb:
            return False
        nuova, vecchia = min(ra, rb), max(ra, rb)
        self.padre[vecchia] = nuova
        if ca or cb:
            self.contenitori[nuova] = ca | cb
        return True


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


class Gruppi(dict):
    """Gruppi per radice; ``via_ai`` sono le radici unite dalla lettura AI (o
    dall'EAN), ``archi_ai`` le coppie di chiavi che l'hanno fatto."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.via_ai: set = set()
        self.archi_ai: Dict[str, List[Tuple[str, str]]] = {}


def _formati_compatibili(a: Articolo, b: Articolo) -> bool:
    if (a.misura or b.misura) and (a.misura != b.misura or a.unita != b.unita):
        return False
    if a.pezzi and b.pezzi and a.pezzi != b.pezzi:
        return False
    if a.contenitore and b.contenitore and a.contenitore != b.contenitore:
        return False
    return True


def raggruppa(acquisti: List[Acquisto], decisioni: Optional[Decisioni] = None) -> Tuple[Dict[str, List[Acquisto]], List[Tuple[Articolo, Articolo]]]:
    """Gruppi di acquisti dello stesso articolo e coppie probabili da decidere."""
    decisioni = decisioni or Decisioni()
    per_chiave: Dict[str, List[Acquisto]] = {}
    articoli: Dict[str, Articolo] = {}
    fornitori_chiave: Dict[str, set] = {}
    chiavi_ai: Dict[str, set] = {}
    chiavi_ean: Dict[str, set] = {}
    for a in acquisti:
        per_chiave.setdefault(a.articolo.chiave, []).append(a)
        articoli.setdefault(a.articolo.chiave, a.articolo)
        fornitori_chiave.setdefault(a.articolo.chiave, set()).add(a.fornitore_id)
        if a.chiave_ai:
            chiavi_ai.setdefault(a.chiave_ai, set()).add(a.articolo.chiave)
        if a.ean:
            chiavi_ean.setdefault(a.ean, set()).add(a.articolo.chiave)

    insiemi = _Insiemi({k: art.contenitore for k, art in articoli.items()})
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
    # stesso EAN o stessa lettura AI: stesso articolo, se il formato non lo smentisce
    archi: List[Tuple[str, str]] = []
    for insieme in list(chiavi_ean.values()) + list(chiavi_ai.values()):
        chiavi = sorted(insieme)
        for kb in chiavi[1:]:
            ka = chiavi[0]
            coppia = _coppia(ka, kb)
            if coppia in decisioni.diverso or not _formati_compatibili(articoli[ka], articoli[kb]):
                continue
            if insiemi.trova(ka) != insiemi.trova(kb) and insiemi.unisci(ka, kb):
                archi.append(coppia)
    gruppi = Gruppi()
    for k, lista in per_chiave.items():
        gruppi.setdefault(insiemi.trova(k), []).extend(lista)
    for ka, kb in archi:
        radice = insiemi.trova(ka)
        gruppi.via_ai.add(radice)
        gruppi.archi_ai.setdefault(radice, []).append((ka, kb))
    # una coppia probabile gia' finita nello stesso gruppo non va chiesta
    probabili = [(a, b) for a, b in probabili if insiemi.trova(a.chiave) != insiemi.trova(b.chiave)]
    return gruppi, probabili


def _q(valore: Optional[Decimal]) -> Optional[str]:
    return None if valore is None else f"{valore.quantize(Q4):f}"


RAPPORTO_MASSIMO = Decimal(3)


def _pezzi_cartone_da_listino(acquisti: List[Acquisto]) -> Tuple[Optional[int], str]:
    """Pezzi per cartone scritti da un listino dello stesso articolo («6 PZ»)."""
    for a in sorted(acquisti, key=lambda x: x.data, reverse=True):
        if a.origine == "listino" and a.pezzi_vendita > 1 and a.unita_fattura == "PZ" and not a.articolo.pezzi:
            return a.pezzi_vendita, a.fornitore
    return None, ""


def riepilogo_gruppo(acquisti: List[Acquisto], abbinato_ai: bool = False) -> Dict[str, Any]:
    """L'articolo con l'ultimo prezzo di ogni fornitore e il migliore."""
    per_fornitore: Dict[str, List[Acquisto]] = {}
    for a in acquisti:
        per_fornitore.setdefault(a.fornitore_id, []).append(a)
    pezzi_listino, fonte_pezzi = _pezzi_cartone_da_listino(acquisti)
    righe = []
    for lista in per_fornitore.values():
        lista.sort(key=lambda a: (a.data, a.origine == "listino", a.fattura_id))
        ultimo = lista[-1]
        prezzi = [a.prezzo_pezzo for a in lista]
        pezzo = ultimo.prezzo_pezzo
        nota_pezzi = ""
        # cartone fatturato senza i pezzi scritti: se il listino di un altro
        # fornitore dice quanti pezzi ha lo stesso articolo, si usa quel numero
        # e lo si dichiara
        if ultimo.origine == "fattura" and ultimo.cartone_senza_pezzi and pezzi_listino:
            pezzo = (ultimo.prezzo_fattura / Decimal(pezzi_listino)).quantize(Q4)
            nota_pezzi = f"cartone da {pezzi_listino} pezzi letto dal listino {fonte_pezzi}: da verificare"
        righe.append({
            "fornitore": ultimo.fornitore,
            "fornitore_id": ultimo.fornitore_id,
            "origine": ultimo.origine,
            "descrizione": ultimo.articolo.descrizione,
            "nome_ai": ultimo.nome_ai,
            "chiave": ultimo.articolo.chiave,
            "prezzo_pezzo": _q(pezzo),
            "prezzo_confezione": _q(pezzo * ultimo.articolo.pezzi) if ultimo.articolo.pezzi else None,
            "prezzo_fattura": _q(ultimo.prezzo_fattura),
            "unita_fattura": ultimo.unita_fattura,
            "per_cartone": ultimo.per_cartone or bool(nota_pezzi),
            "nota_pezzi": nota_pezzi,
            "data": ultimo.data,
            "numero_fattura": ultimo.numero_fattura,
            "fattura_id": ultimo.fattura_id,
            "aliquota_iva": ultimo.aliquota_iva,
            "fornitore_key": ultimo.fornitore_key,
            "codice_articolo": ultimo.codice_articolo,
            "ean": ultimo.ean,
            "link": ultimo.link,
            "unita_vendita": ultimo.unita_vendita,
            "pezzi_vendita": ultimo.pezzi_vendita,
            "offerta_fino": ultimo.offerta_fino,
            "acquisti": sum(1 for a in lista if a.origine == "fattura"),
            "prezzo_min": _q(min(prezzi)),
            "prezzo_max": _q(max(prezzi)),
            "_pezzo": pezzo,
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
    scelto = max(acquisti, key=lambda a: (a.fornitore_id == righe[0]["fornitore_id"], a.data))
    art = scelto.articolo
    nome_standard = next((a.nome_ai for a in sorted(acquisti, key=lambda x: x.data, reverse=True) if a.nome_ai), "")
    return {
        "chiave": art.chiave,
        "nome": art.descrizione,
        "nome_standard": nome_standard,
        "formato": art.formato,
        "pezzi": art.pezzi,
        "n_fornitori": len(righe),
        "migliore": migliore,
        "risparmio_pezzo": _q(risparmio),
        "pari_merito": pari_merito,
        "confrontabile": confrontabile,
        "motivo": motivo,
        "abbinato_ai": abbinato_ai,
        "con_listino": any(r["origine"] == "listino" for r in righe),
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
_cache: Dict[str, Any] = {"at": 0.0, "acquisti": None, "riepiloghi": None}


def invalida_cache() -> None:
    _cache["at"] = 0.0
    _cache["acquisti"] = None
    _cache["riepiloghi"] = None


def cache_valida() -> bool:
    return _cache["acquisti"] is not None and time.monotonic() - _cache["at"] < _TTL


def salva_cache(acquisti: List[Acquisto]) -> None:
    _cache["acquisti"] = acquisti
    _cache["at"] = time.monotonic()
