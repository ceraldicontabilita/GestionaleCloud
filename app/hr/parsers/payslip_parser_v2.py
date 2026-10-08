"""Parser buste paga — re-export del motore unico di `app/parsers/`.

Le due copie erano un fork, e la deriva era fatta di correzioni applicate da
un lato solo — lo stesso schema del limite 15k di `document_ai_extractor`,
qui pero' al contrario: la copia HR aveva `NETTO_MINIMO_PLAUSIBILE` e
`_find_amount_near_label` (la ricerca dell'importo in una finestra di righe
sotto l'etichetta, che regge alle impaginazioni PDF reali), e la copia ERP
no. Verificato prima di fondere che la copia ERP non avesse nulla di suo:
era solo la versione piu' vecchia.

La logica sta ora in un modulo solo, sotto `app/`, come impone CLAUDE.md.
"""
from app.parsers.payslip_parser_v2 import (  # noqa: F401
    PayslipParserMultiFormat,
    parse_payslip_pdf,
)

__all__ = ["PayslipParserMultiFormat", "parse_payslip_pdf"]
