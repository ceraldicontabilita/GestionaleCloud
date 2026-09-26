"""Motore unico dei cedolini: un lettore per ogni tracciato.

Ogni PDF che arriva come cedolino — da Drive, dalla posta o da Documenti >
Import — passa da leggi_pdf e poi da un solo scrittore
(cedolini_manager.processa_tutti_cedolini_pdf). Prima convivevano cinque
strade: il parser multi-template, Document AI, il regex storico
payslip_parser_v2, lo scrittore V1 e il Libro Unico con il suo scrittore
su tabelle mai esistite; ognuna decideva da se' se un file fosse letto, e un
cedolino scartato da una poteva passare da un'altra con numeri diversi.

Il lettore riconosce i tracciati che il titolare ha davvero in archivio:
Zucchetti (classico e con gli spazi scritti «s»), Libro Unico, Teamsystem
(anche 13a e 14a con «14a MENS.»), CSC Napoli. E dice sempre cosa ha trovato:

- buste: una o piu' buste, ciascuna col suo stato_netto;
- presenze: fogli presenze Zucchetti (Aut. 301), che non sono buste;
- fuori_periodo: buste lette ma anteriori allo storico autorizzato;
- non_cedolino: un contratto di lavoro o simili arrivato fra i cedolini;
- illeggibile: nessuna busta e nessun foglio presenze riconosciuto.
"""
from __future__ import annotations

import base64
import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

import fitz

from app.constants.stati_netto import (
    NETTO_NON_PRESENTE_O_NON_LEGGIBILE,
    NETTO_VERIFICATO_DA_CEDOLINO,
)
from app.parsers.busta_paga_multi_template import (
    RIQUADRO_NETTO,
    detect_template,
    parse_template_zucchetti_presenze,
)
from app.parsers.cedolino_voci import leggi_corpo_cedolino, leggi_foglio_presenze

# Per scelta operativa del 03/08/2026 lo storico autorizzato parte dal 2018.
# La guardia evita che un file piu' vecchio, caricato per errore, entri nei
# registri o generi prima nota/partite aperte.
PAYROLL_MIN_YEAR = 2018

ESITO_BUSTE = "buste"
ESITO_PRESENZE = "presenze"
ESITO_FUORI_PERIODO = "fuori_periodo"
ESITO_NON_CEDOLINO = "non_cedolino"
ESITO_ILLEGGIBILE = "illeggibile"

# Un contratto o una lettera d'assunzione citano la busta paga, ma non hanno il
# riquadro del netto: senza quel riquadro non sono cedolini.
_CONTRATTO = re.compile(
    r"CONTRATTO\s+(?:INDIVIDUALE\s+)?DI\s+LAVORO|LETTERA\s+DI\s+ASSUNZIONE|DOCUSIGN"
)


def _summary_cedolino(
    summary: Dict[str, Any],
    raw_text: str,
    *,
    pdf_bytes: bytes,
    page_start: int,
    page_end: int,
    document_pages: int,
) -> Dict[str, Any]:
    """Converte un riepilogo deterministico conservando provenienza e PDF."""
    return {
        "nome_dipendente": summary.get("dipendente_nome") or "",
        "codice_fiscale": summary.get("codice_fiscale") or "",
        "tipo_cedolino": summary.get("tipo_cedolino") or "mensile",
        "mese": summary.get("mese"),
        "anno": summary.get("anno"),
        # Cella vuota -> nullo, mai zero (CLAUDE.md, «Personale»).
        "lordo": summary.get("lordo"),
        "netto": summary.get("netto"),
        "netto_mese": summary.get("netto"),
        # Lo stato lo decide il lettore (`_verifica_netto`); senza, vale la
        # sola presenza del netto letto.
        "stato_netto": summary.get("stato_netto") or (
            NETTO_VERIFICATO_DA_CEDOLINO if summary.get("netto") is not None
            else NETTO_NON_PRESENTE_O_NON_LEGGIBILE
        ),
        "netto_letto": summary.get("netto_letto"),
        "netto_calcolato": summary.get("netto_calcolato"),
        "totale_trattenute": summary.get("trattenute"),
        "tfr_quota": summary.get("tfr_quota"),
        "ore_lavorate": summary.get("ore_lavorate"),
        "giorni_lavorati": summary.get("giorni_lavorati"),
        "livello": summary.get("livello"),
        "formato_rilevato": summary.get("template") or "multi_template",
        "ferie_permessi": {
            "ferie_residuo": summary.get("ferie_residuo"),
            "ferie_godute": summary.get("ferie_godute"),
            "permessi_residuo": summary.get("permessi_residuo"),
            "permessi_goduti": summary.get("permessi_goduti"),
        },
        "cessato": summary.get("cessato", False),
        "cessazione_diciture": summary.get("cessazione_diciture", []),
        "data_cessazione_rilevata": summary.get("data_cessazione_rilevata"),
        "source_page_start": page_start,
        "source_page_end": page_end,
        "source_document_pages": document_pages,
        "_raw_text": raw_text,
        "_pdf_data": base64.b64encode(pdf_bytes).decode("ascii"),
    }


def _summary_complete(parsed: Dict[str, Any], summary: Dict[str, Any]) -> bool:
    """Una busta c'e' se ha persona e periodo e il documento e' una busta.

    Busta vuol dire importi letti **oppure** il riquadro del netto stampato:
    un mese a zero (solo arrotondamento) ha la cella del netto vuota, e prima
    veniva scartato come illeggibile. Il netto puo' restare nullo: lo dice
    stato_netto, e solo quello verificato alimenta Salari.
    """
    return bool(
        (parsed.get("parse_success") or parsed.get("riquadro_netto"))
        and parsed.get("tipo_documento") != "foglio_presenze"
        and summary.get("codice_fiscale")
        and summary.get("mese")
        and summary.get("anno")
    )


def _parse_multi_template_units(file_content: bytes) -> List[Dict[str, Any]]:
    """Separa un fascicolo multipagina per dipendente e periodo.

    Le pagine di continuazione restano aggregate al cedolino precedente. Se il
    fascicolo contiene un solo dipendente, viene conservato integralmente.
    """
    # Import al momento della chiamata: i test sostituiscono il parser sul
    # suo modulo.
    from app.parsers.busta_paga_multi_template import (
        extract_summary,
        parse_busta_paga_from_bytes,
    )

    document = fitz.open(stream=file_content, filetype="pdf")
    try:
        page_count = len(document)
        raw_pages = [page.get_text() for page in document]

        def page_bytes(start: int, end: int) -> bytes:
            output = fitz.open()
            try:
                output.insert_pdf(document, from_page=start, to_page=end)
                return output.tobytes(garbage=3, deflate=True)
            finally:
                output.close()

        if page_count <= 1:
            parsed = parse_busta_paga_from_bytes(file_content)
            summary = extract_summary(parsed)
            if not _summary_complete(parsed, summary):
                return []
            return [_summary_cedolino(
                summary, "\n".join(raw_pages), pdf_bytes=file_content,
                page_start=1, page_end=page_count, document_pages=page_count,
            )]

        candidates: List[Optional[Tuple[Tuple[str, int, int, str], Dict[str, Any]]]] = []
        for index in range(page_count):
            single = page_bytes(index, index)
            parsed = parse_busta_paga_from_bytes(single)
            summary = extract_summary(parsed)
            if _summary_complete(parsed, summary):
                key = (
                    str(summary.get("codice_fiscale") or "").upper(),
                    int(summary["mese"]),
                    int(summary["anno"]),
                    str(summary.get("tipo_cedolino") or "mensile").lower(),
                )
                candidates.append((key, summary))
            else:
                candidates.append(None)

        distinct_keys = {candidate[0] for candidate in candidates if candidate}
        if len(distinct_keys) <= 1:
            parsed = parse_busta_paga_from_bytes(file_content)
            summary = extract_summary(parsed)
            if not _summary_complete(parsed, summary):
                return []
            return [_summary_cedolino(
                summary, "\n".join(raw_pages), pdf_bytes=file_content,
                page_start=1, page_end=page_count, document_pages=page_count,
            )]

        starts: List[Tuple[int, Tuple[str, int, int, str], Dict[str, Any]]] = []
        current_key: Optional[Tuple[str, int, int, str]] = None
        for index, candidate in enumerate(candidates):
            if not candidate:
                continue
            key, summary = candidate
            if key != current_key:
                starts.append((index, key, summary))
                current_key = key

        units: List[Dict[str, Any]] = []
        seen_keys = set()
        for position, (start, expected_key, page_summary) in enumerate(starts):
            if expected_key in seen_keys:
                continue
            seen_keys.add(expected_key)
            end = starts[position + 1][0] - 1 if position + 1 < len(starts) else page_count - 1
            if position == 0:
                start = 0
            chunk = page_bytes(start, end)
            parsed = parse_busta_paga_from_bytes(chunk)
            summary = extract_summary(parsed)
            if not _summary_complete(parsed, summary):
                summary = page_summary
            units.append(_summary_cedolino(
                summary,
                "\n".join(raw_pages[start:end + 1]),
                pdf_bytes=chunk,
                page_start=start + 1,
                page_end=end + 1,
                document_pages=page_count,
            ))
        return units
    finally:
        document.close()


def _presenze(pagine: List[str]) -> List[Dict[str, Any]]:
    fogli = []
    for numero, testo in enumerate(pagine, start=1):
        if detect_template(testo) != "zucchetti_presenze":
            continue
        testata = parse_template_zucchetti_presenze(testo)
        giorni = leggi_foglio_presenze(testo)
        fogli.append({
            "codice_fiscale": (testata.get("dipendente") or {}).get("codice_fiscale"),
            "nome_dipendente": (testata.get("dipendente") or {}).get("nome_completo"),
            "mese": (testata.get("periodo") or {}).get("mese"),
            "anno": (testata.get("periodo") or {}).get("anno"),
            "pagina": numero,
            "giorni_lavorati": giorni.get("giorni_lavorati"),
            "giorni_con_giustificativo": giorni.get("giorni_con_giustificativo"),
            "presenze": giorni.get("presenze") or [],
            "riepilogo_giustificativi": giorni.get("riepilogo_giustificativi") or [],
        })
    return fogli


def _con_voci(busta: Dict[str, Any]) -> Dict[str, Any]:
    """Voci codificate e dati chiave letti dal corpo della stessa busta."""
    from app.services.salari_unificati_v2 import estrai_ferie_rol_from_text

    testo = busta.get("_raw_text") or ""
    corpo = leggi_corpo_cedolino(testo)
    if corpo.get("voci"):
        busta["voci"] = corpo["voci"]
        busta["dati_chiave"] = corpo["dati_chiave"]
    # Ferie, ROL, contributi e TFR letti dal testo: vanno nella scheda
    # Markdown, cosi' la ricarica non ha bisogno del PDF.
    extra = {k: v for k, v in (estrai_ferie_rol_from_text(testo) if testo else {}).items()
             if isinstance(v, (int, float)) and not isinstance(v, bool)}
    if extra:
        busta["dati_extra"] = extra
    if busta.get("_pdf_data"):
        # La chiave documentale del gestionale usa l'MD5 dei byte della busta
        # (`chiave_cedolino`): conservarla fa ritrovare la stessa busta.
        busta["impronta_busta"] = hashlib.md5(base64.b64decode(busta["_pdf_data"])).hexdigest()
    return busta


def _anno(busta: Dict[str, Any]) -> int:
    try:
        return int(busta.get("anno") or 0)
    except (TypeError, ValueError):
        return 0


def leggi_pdf(contenuto: bytes) -> Dict[str, Any]:
    """Legge un PDF di cedolini e dice sempre che cosa ha trovato."""
    documento = fitz.open(stream=contenuto, filetype="pdf")
    try:
        pagine = [pagina.get_text() for pagina in documento]
    finally:
        documento.close()
    testo = "\n".join(pagine)
    alto = re.sub(r"\s+", " ", testo.upper())

    if _CONTRATTO.search(alto) and not RIQUADRO_NETTO.search(testo):
        return {"esito": ESITO_NON_CEDOLINO, "buste": [], "presenze": [], "fuori_periodo": [],
                "motivo": "contratto di lavoro, non una busta paga"}

    buste = [_con_voci(b) for b in _parse_multi_template_units(contenuto)]
    fuori = [b for b in buste if 0 < _anno(b) < PAYROLL_MIN_YEAR]
    buste = [b for b in buste if b not in fuori]
    presenze = _presenze(pagine)

    if buste:
        esito, motivo = ESITO_BUSTE, f"{len(buste)} buste lette"
    elif fuori:
        anni = sorted({_anno(b) for b in fuori})
        esito = ESITO_FUORI_PERIODO
        motivo = f"buste del {', '.join(map(str, anni))}: lo storico autorizzato parte dal {PAYROLL_MIN_YEAR}"
    elif presenze:
        esito, motivo = ESITO_PRESENZE, f"foglio presenze ({len(presenze)} pagine), nessuna busta"
    else:
        esito, motivo = ESITO_ILLEGGIBILE, "nessuna busta e nessun foglio presenze riconosciuto"
    return {"esito": esito, "buste": buste, "presenze": presenze, "fuori_periodo": fuori, "motivo": motivo}
