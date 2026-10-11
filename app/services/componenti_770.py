"""Un quadro del 770 stampato da solo (``02_Quadro_ST_modulo_1.pdf``).

La stampa dell'Agenzia divide la dichiarazione in un PDF per quadro; ognuno
porta in testa «Identificativo dichiarazione: 10523651165 - 0000002» (il
«770ord» sta nel titolo del PDF, non nel testo della pagina). Non e' una
seconda dichiarazione: e' un pezzo di quella gia' in ``fiscal_documents``
(«Modello 770 - Anno 2019 - 10523651165-0000002.pdf»), e l'aggancio si fa
solo per quell'identificativo, mai per nome, anno o importo. Senza la dichiarazione intera il quadro resta
conservato e da verificare.
"""
from __future__ import annotations

import re
import asyncio
from typing import Any, Dict, Optional

from app.db_collections import COLL_FISCAL_DOCUMENTS

TIPO = "componente_770"
_NOME_QUADRO = re.compile(r"quadro[\s_]+([a-z]{2})(?:[\s_]+modulo[\s_]*(\d+))?", re.I)
_TESTO_QUADRO = re.compile(r"\bQUADRO\s+([A-Z]{2})\b")
# Quadri propri del 770 (sostituto d'imposta): Redditi (R*) e IVA (V*) hanno
# sigle diverse, quindi un loro quadro non finisce qui.
QUADRI_770 = frozenset({
    "DI", "SF", "SG", "SH", "SI", "SK", "SL", "SM", "SO", "SP", "SQ", "SS", "ST", "SV", "SX", "SY",
})
_IDENTIFICATIVO = re.compile(r"IDENTIFICATIVO\s+DICHIARAZIONE\s*:?\s*(\d{11})\s*-\s*(\d{7})", re.I)


def quadro(filename: str, testo: str) -> Optional[str]:
    """La sigla del quadro (``ST``) se il PDF e' un quadro singolo del 770.

    Servono tutte le prove: il nome del file dice «Quadro XX», XX e' un quadro
    del 770, il testo nomina lo stesso quadro e porta l'identificativo della
    dichiarazione. Una dichiarazione intera non si chiama «Quadro …».
    """
    nome = _NOME_QUADRO.search(filename or "")
    testo_maiuscolo = (testo or "").upper()
    if ("frontespizio" in (filename or "").lower() and identificativo(testo_maiuscolo)
            and re.search(r"DATI\s+RELATIVI\s+AL\s+SOSTITUTO", testo_maiuscolo)):
        return "FRONTESPIZIO"
    if not nome or not identificativo(testo_maiuscolo):
        return None
    sigla = nome.group(1).upper()
    if sigla not in QUADRI_770:
        return None
    nel_testo = {m.group(1) for m in _TESTO_QUADRO.finditer(testo_maiuscolo)}
    return sigla if sigla in nel_testo else None


def identificativo(testo: str) -> Optional[str]:
    trovato = _IDENTIFICATIVO.search(testo or "")
    return f"{trovato.group(1)}-{trovato.group(2)}" if trovato else None


async def dichiarazione_di(db, ident: Optional[str]) -> Optional[Dict[str, Any]]:
    """Il 770 intero con lo stesso identificativo, se ce n'e' uno solo."""
    if not ident:
        return None
    candidati = await db[COLL_FISCAL_DOCUMENTS].find(
        {"document_type": "MODELLO_770"}, {"_id": 0, "id": 1, "filename": 1},
    ).to_list(1000)
    chiave = ident.replace("-", "")
    trovati = [
        d for d in candidati
        if chiave in re.sub(r"\D", "", str(d.get("filename") or ""))
    ]
    return trovati[0] if len(trovati) == 1 else None


async def metadati(db, *, filename: str, testo: str, content: bytes | None = None) -> Dict[str, Any]:
    from app.services.declaration_dossiers import document_identity

    ident = identificativo(testo)
    dichiarazione = await dichiarazione_di(db, ident)
    modulo = _NOME_QUADRO.search(filename or "")
    identity = document_identity({"filename": filename, "document_type": "MODELLO_770"}, testo)
    metadata = {
        "declaration_type": "MODELLO_770",
        "codice_fiscale": identity["taxpayer_id"],
        "anno_imposta": identity["tax_year"],
        "quadro": quadro(filename, testo),
        "modulo": int(modulo.group(2)) if modulo and modulo.group(2) else None,
        "identificativo_dichiarazione": ident,
        "dichiarazione_id": (dichiarazione or {}).get("id"),
        "dichiarazione_filename": (dichiarazione or {}).get("filename"),
        "stato_aggancio": "AGGANCIATO" if dichiarazione else "DICHIARAZIONE_INTERA_MANCANTE",
        # Un quadro non apre obblighi: li apre la dichiarazione.
        "obligation_status": "NON_APPLICABILE",
        "relation_keys": {"identificativo_dichiarazione": ident},
    }
    if content and metadata["quadro"] in {"ST", "SV"}:
        from app.services.fiscal_document_ingestion import extract_pdf_pages
        from app.services.dichiarazioni_quadri import estrai_quadri_pagine

        pages = await asyncio.to_thread(extract_pdf_pages, content)
        metadata["quadri"] = estrai_quadri_pagine(pages, "MODELLO_770")
    return metadata
