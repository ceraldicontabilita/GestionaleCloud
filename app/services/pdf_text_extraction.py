"""Estrazione testuale PDF resiliente e con budget limitato.

La classificazione documentale non deve dipendere dal primo motore che
restituisce qualche carattere: alcuni PDF espongono testo incompleto con
PyPDF, altri con PyMuPDF, e le copertine possono nascondere il contenuto utile
nelle pagine finali. Questo modulo confronta i due risultati pagina per pagina
e campiona anche la coda del documento senza avviare OCR o servizi esterni.
"""

from __future__ import annotations

import io
import logging
import re
from typing import Iterable

logger = logging.getLogger(__name__)


def _sample_page_indexes(page_count: int, max_pages: int) -> list[int]:
    """Restituisce indici unici privilegiando apertura e chiusura del PDF."""
    if page_count <= 0 or max_pages <= 0:
        return []
    if page_count <= max_pages:
        return list(range(page_count))

    head_count = min(3, max_pages)
    indexes = list(range(head_count))
    remaining = max_pages - len(indexes)
    if remaining:
        indexes.extend(range(max(head_count, page_count - remaining), page_count))
    return indexes


def _quality_score(text: str) -> tuple[int, int, int]:
    """Premia testo informativo e penalizza output composto quasi da spazi."""
    compact = re.sub(r"\s+", " ", text or "").strip()
    alnum = sum(character.isalnum() for character in compact)
    words = len(re.findall(r"\b[\w./-]+\b", compact, flags=re.UNICODE))
    lines = len([line for line in (text or "").splitlines() if line.strip()])
    return alnum, words, lines


def _best_text(candidates: Iterable[str]) -> str:
    return max((candidate or "" for candidate in candidates), key=_quality_score, default="")


def extract_pdf_text(
    file_content: bytes,
    *,
    max_pages: int | None = None,
    include_tail: bool = True,
) -> str:
    """Estrae testo scegliendo il risultato migliore per ciascuna pagina.

    ``max_pages=None`` legge l'intero documento. Con un limite, vengono lette
    le prime pagine e, se ``include_tail`` e' vero, anche le ultime: e' il
    profilo adatto alla classificazione preventiva degli upload.
    """
    if not file_content:
        return ""

    pypdf_reader = None
    pypdf_count = 0
    try:
        from pypdf import PdfReader

        pypdf_reader = PdfReader(io.BytesIO(file_content), strict=False)
        pypdf_count = len(pypdf_reader.pages)
    except Exception as exc:
        logger.debug("Estrazione PyPDF non disponibile: %s", exc)

    fitz_document = None
    fitz_count = 0
    try:
        import fitz

        fitz_document = fitz.open(stream=file_content, filetype="pdf")
        fitz_count = fitz_document.page_count
    except Exception as exc:
        logger.debug("Estrazione PyMuPDF non disponibile: %s", exc)

    page_count = max(pypdf_count, fitz_count)
    if page_count <= 0:
        if fitz_document is not None:
            fitz_document.close()
        return ""

    budget = page_count if max_pages is None else min(page_count, max_pages)
    indexes = (
        _sample_page_indexes(page_count, budget)
        if include_tail
        else list(range(budget))
    )

    pages: list[str] = []
    try:
        for index in indexes:
            candidates: list[str] = []
            if pypdf_reader is not None and index < pypdf_count:
                page = pypdf_reader.pages[index]
                try:
                    candidates.append(page.extract_text(extraction_mode="layout") or "")
                # Le pagine bianche create da scanner/editor possono non
                # avere affatto /Contents: sono valide e valgono testo vuoto.
                except Exception:
                    pass
                try:
                    candidates.append(page.extract_text() or "")
                except Exception:
                    pass
            if fitz_document is not None and index < fitz_count:
                try:
                    candidates.append(fitz_document[index].get_text("text", sort=True) or "")
                except Exception:
                    pass
            best = _best_text(candidates).strip()
            if best:
                pages.append(f"[PAGINA {index + 1}]\n{best}")
    finally:
        if fitz_document is not None:
            fitz_document.close()

    return "\n\n".join(pages)


def pdf_has_searchable_text(file_content: bytes, *, max_pages: int = 5) -> bool:
    """Indica se il PDF contiene abbastanza testo nativo per il parsing."""
    text = extract_pdf_text(file_content, max_pages=max_pages)
    return _quality_score(text)[0] >= 40
