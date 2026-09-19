"""Parser buste paga multi-template — re-export del modulo unico.

La logica vive in `app/parsers/busta_paga_multi_template.py`. Fino al
19/09/2026 qui c'era una copia, e la deriva toccava un dato che decide
l'identita' della busta.

**`tipo_cedolino` sbagliato sui cedolini ordinari.** Questa copia classificava
la busta cercando la parola «TREDICESIMA» o «13MA` in TUTTO il testo. Ma quasi
ogni cedolino mensile contiene la voce «Rateo 13ma Mensilita`, quindi un
marzo qualunque risultava una tredicesima. Misurato su un testo di cedolino
ordinario: la copia ERP diceva `mensile`, questa diceva `tredicesima`. Il lato
ERP aveva gia' la correzione — controllo limitato alle prime 80 righe, voci di
maturazione escluse (RATEO, MATURAT, ACCANTON...), marcatore di testata
richiesto — applicata in entrambi i punti in cui il tipo si determina.
Non e' un'etichetta cosmetica: `tipo_cedolino` entra nella chiave documentale
del cedolino e nella regola «13ma e 14ma restano buste distinte».

Mancavano inoltre: `parse_importo_ita` al posto di una conversione scritta a
mano, `_parse_teamsystem_layout` (lordo, trattenute, netto e quota TFR lette
dalle coordinate del layout TeamSystem), e in `extract_summary` sia
`tipo_cedolino` sia il ripiego di `tfr_quota` su `quota_mese`.

Nell'altro verso questa copia aveva tre funzioni sue — `_verifica_netto`,
`_elementi_retributivi`, `_acconti_e_anticipazioni` — portate sul modulo unico
prima di cancellarla, con le loro chiamate in coda a `parse_busta_paga_multi`.
"""
from app.parsers.busta_paga_multi_template import (  # noqa: F401
    detect_cessazione,
    detect_template,
    extract_summary,
    parse_busta_paga_from_bytes,
    parse_busta_paga_multi,
    parse_importo,
    parse_page2_ore_lavorate,
    parse_template_csc_napoli,
    parse_template_teamsystem,
    parse_template_zucchetti_classic,
    parse_template_zucchetti_new,
    parse_template_zucchetti_presenze,
)

__all__ = [
    "detect_cessazione",
    "detect_template",
    "extract_summary",
    "parse_busta_paga_from_bytes",
    "parse_busta_paga_multi",
    "parse_importo",
    "parse_page2_ore_lavorate",
    "parse_template_csc_napoli",
    "parse_template_teamsystem",
    "parse_template_zucchetti_classic",
    "parse_template_zucchetti_new",
    "parse_template_zucchetti_presenze",
]
