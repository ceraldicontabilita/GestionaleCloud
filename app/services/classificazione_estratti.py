"""Riconosce la fonte di un documento dell'area Drive ``Estratti conto``.

Fino a ieri la fonte si deduceva dal nome della cartella: ``POS BNL``,
``POS BPM``, ``Carta Nexi``, e cosi' via. L'utente ha scelto di tenere tutto
in un'unica cartella ``Da elaborare`` — "per non perdere la testa tra pos
bnl, pos bpm, estratti ordinari" — e con l'indizio del percorso sparisce
anche la classificazione: i file POS non venivano nemmeno letti, e un
estratto della carta di credito Nexi finiva classificato come movimento
bancario.

L'ordine dei controlli e' voluto:

1. il nome, quando contiene un segno inequivocabile (``Export_Mensile_``,
   ``-MSR-``, ``Estratto mutuo``);
2. il contenuto, per i PDF che si chiamano tutti ``Estratto_Conto.pdf`` ma
   arrivano da emittenti diversi.

Un documento che non si riesce a riconoscere NON viene indovinato: la
funzione restituisce ``None`` e il chiamante lo ferma in ``Errori`` con il
motivo. Sbagliare fonte e' peggio che fermarsi — le spese Amazon della carta
di credito importate come movimenti bancari creerebbero uscite dal conto che
non sono mai avvenute.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

POS = "pos"
PAYPAL = "paypal"
NEXI = "nexi"
MUTUO = "mutuo"
BANCA = "bank"

# Estensioni che questa area sa trattare. Tutto il resto (zip, immagini,
# documenti di testo) non viene nemmeno preso in carico.
ESTENSIONI_TRATTATE = (".csv", ".xlsx", ".xls", ".xlsm", ".pdf")

# Report PayPal: 84B9EHMDDE6B4-MSR-20250301000000-20250331235959.PDF
_PAYPAL_REPORT = re.compile(r"-(msr|csr)-\d{14}-\d{14}", re.IGNORECASE)

# Quanto testo basta per riconoscere l'emittente: l'intestazione sta sempre
# nella prima pagina, non serve aprire estratti da centinaia di movimenti.
_PAGINE_DA_LEGGERE = 2


_ANNO = re.compile(r"(?<!\d)(19|20)\d{2}(?!\d)")


def _pulisci(nome: str) -> str:
    return str(nome or "").strip().lower()


def anno_del_nome(nome: str) -> Optional[int]:
    """Anno leggibile nel nome del file, se c'e' ed e' uno solo.

    Serve a tenere fermo l'arretrato senza aprire i documenti. Con piu' anni
    nel nome (``2019-Q4 Estratto BNL 4-2019``) vale il piu' recente: e' il
    periodo del documento, gli altri sono riferimenti.
    """
    anni = [int(trovato.group(0)) for trovato in _ANNO.finditer(str(nome or ""))]
    return max(anni) if anni else None


def estensione_trattata(nome: str) -> bool:
    return _pulisci(nome).endswith(ESTENSIONI_TRATTATE)


def route_da_nome(nome: str) -> Optional[str]:
    """Fonte deducibile dal solo nome del file, quando e' certa.

    Solo segni che una fonte usa e le altre no. ``estratto conto`` da solo
    non e' un segno: lo scrivono tutti, banca, carta e PayPal.
    """
    testo = _pulisci(nome)
    if not testo:
        return None

    # POS: sono gli export dei terminali, con nomi generati dal gestore.
    if testo.startswith(("export_mensile", "export_transazioni", "commissioni_")):
        return POS

    if _PAYPAL_REPORT.search(testo) or "paypal" in testo:
        return PAYPAL

    if "mutuo" in testo:
        return MUTUO

    # Carta di credito: Nexi per nome, oppure l'export "Movimenti carta".
    if "nexi" in testo or testo.startswith("movimenti carta"):
        return NEXI

    if any(segno in testo for segno in (
        "elencoentrateuscite", "movimenti_bnl_bpm", "estratto conto corrente",
    )):
        return BANCA
    # "BNL"/"BPM" come parola a se': evita di agganciare parole che le
    # contengono per caso.
    if re.search(r"\b(bnl|bpm)\b", testo):
        return BANCA

    return None


def _testo_del_pdf(contenuto: bytes) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover - dipendenza presente in produzione
        logger.warning("PyMuPDF non disponibile: impossibile leggere il PDF")
        return ""
    try:
        with fitz.open(stream=contenuto, filetype="pdf") as documento:
            pagine = [
                documento[i].get_text()
                for i in range(min(_PAGINE_DA_LEGGERE, documento.page_count))
            ]
    except Exception as exc:
        logger.warning("PDF illeggibile in fase di classificazione: %s", exc)
        return ""
    return "\n".join(pagine)


def route_da_testo(testo: str) -> Optional[str]:
    """Fonte riconosciuta dall'intestazione del documento.

    L'ordine conta: l'estratto PayPal si intitola "Estratto conto bancario",
    e quello Nexi "il suo estratto conto Nexi". Se la banca venisse
    controllata per prima si prenderebbero entrambi per movimenti bancari.
    """
    testo = _pulisci(testo)
    if not testo:
        return None

    if "nexi payments" in testo or "estratto conto nexi" in testo:
        return NEXI

    if "paypal" in testo and any(segno in testo for segno in (
        "codice conto commerciante", "paypal (europe)", "id paypal",
    )):
        return PAYPAL

    if "mutuo" in testo:
        return MUTUO

    if "carta di debito" in testo and "conto appoggio" in testo:
        return BANCA

    if any(segno in testo for segno in (
        "banca nazionale del lavoro", "banco bpm", "banca popolare di milano",
        "bnl bnp paribas",
    )):
        return BANCA

    # Intestazione dell'export movimenti della banca: le colonne sono sue e
    # non compaiono in nessun altro documento di quest'area.
    if "data contabile" in testo and "data valuta" in testo:
        return BANCA

    # Colonne reali dell'export dei terminali Numia/BPM. Il circuito indica la
    # carta del cliente, non un addebito del conto corrente.
    if all(segno in testo for segno in (
        "data e ora", "importo", "stato operazione",
    )) and any(segno in testo for segno in (
        "id terminale", "mid", "punto vendita",
    )):
        return POS

    return None


def _testo_del_csv(contenuto: bytes) -> str:
    """Prime righe del file: l'intestazione basta a riconoscere l'emittente."""
    frammento = contenuto[:8192]
    for codifica in ("utf-8", "latin-1"):
        try:
            return frammento.decode(codifica)
        except UnicodeDecodeError:
            continue
    return frammento.decode("utf-8", errors="replace")


def _testo_del_foglio(contenuto: bytes) -> str:
    """Intestazioni iniziali XLSX/XLSM per distinguere banca e terminale POS."""
    try:
        import io
        import openpyxl

        workbook = openpyxl.load_workbook(
            io.BytesIO(contenuto), read_only=True, data_only=True,
        )
        sheet = workbook.active
        righe = []
        for raw in sheet.iter_rows(min_row=1, max_row=50, max_col=40,
                                   values_only=True):
            valori = [str(value).strip() for value in raw if value not in (None, "")]
            if valori:
                righe.append(" ; ".join(valori))
        workbook.close()
        return "\n".join(righe)
    except Exception as exc:
        logger.warning("Foglio illeggibile in fase di classificazione: %s", exc)
        return ""


def classifica(nome: str, contenuto: Optional[bytes] = None) -> Tuple[Optional[str], str]:
    """Fonte del documento e motivo della scelta, per il registro di audit.

    Restituisce ``(None, motivo)`` quando il documento non e' riconoscibile:
    e' un esito legittimo, non un errore di lettura.
    """
    if not estensione_trattata(nome):
        return None, "estensione non trattata da quest'area"

    # Il contenuto prevale sul nome. Nella cartella reale esistono PDF chiamati
    # tutti "Estratto_Conto (N).pdf", e "Movimenti carta" puo' indicare carta
    # di debito oppure carta di credito.
    if contenuto:
        testo = ""
        if _pulisci(nome).endswith(".pdf"):
            testo = _testo_del_pdf(contenuto)
        elif _pulisci(nome).endswith(".csv"):
            testo = _testo_del_csv(contenuto)
        elif _pulisci(nome).endswith((".xlsx", ".xlsm")):
            testo = _testo_del_foglio(contenuto)
        if testo:
            dal_testo = route_da_testo(testo)
            if dal_testo:
                return dal_testo, "riconosciuto dall'intestazione del documento"

    dal_nome = route_da_nome(nome)
    if dal_nome:
        return dal_nome, "intestazione non decisiva; riconosciuto dal nome del file"

    if contenuto:
        return None, ("intestazione non riconosciuta: il documento non "
                      "dichiara ne' la banca ne' il gestore che lo ha emesso")

    return None, "il nome non dice da quale fonte arrivi"
