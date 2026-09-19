"""Riconciliazione paghe HR — re-export del modulo unico.

La logica vive in `app/services/paghe_riconciliazione.py`. Fino al 19/09/2026
qui c'era una copia piu' vecchia, e le differenze toccavano **quali movimenti
bancari valgono come prova di pagamento**:

- mancava `_solo_evidenza_ufficiale`: la ricerca accettava anche righe che
  l'ERP esclude di proposito, cioe' quelle senza evidenza bancaria ufficiale;
- mancava il vincolo `in_attesa_estratto_ufficiale != True` su
  `prima_nota_banca`: un movimento ancora in attesa dell'estratto poteva
  saldare un documento;
- la ricerca in `estratto_conto_movimenti` accettava solo l'importo negativo,
  mentre la copia ERP tollera entrambe le convenzioni di segno con
  `tipo: "uscita"`.

Non era teoria: `POST /api/paghe/riconcilia-f24` (in
`app/hr/routers/f24_parser.py`) chiamava `riconcilia_tutti_f24` di QUESTA
copia, e `riconcilia_f24_con_banca` chiamava questo `cerca_in_estratto_conto`.
Erano gli unici chiamanti vivi di entrambe le copie — sul lato ERP quelle tre
funzioni restano solo per audit storico, perche'
`esegui_riconciliazione_paghe_completa` usa ormai i motori canonici
(`stipendi_bonifici` e `f24_bank_reconciliation`).

Nell'altro verso, questa copia aveva una cosa sola in piu': la soglia
`netto_mese >= 50` in `riconcilia_tutti_stipendi`, portata sul modulo unico
prima di cancellarla.
"""
from app.services.paghe_riconciliazione import (  # noqa: F401
    cerca_in_estratto_conto,
    esegui_riconciliazione_paghe_completa,
    marca_movimento_riconciliato,
    riconcilia_tutti_cedolini,
    riconcilia_tutti_f24,
    riconcilia_tutti_stipendi,
)

__all__ = [
    "cerca_in_estratto_conto",
    "esegui_riconciliazione_paghe_completa",
    "marca_movimento_riconciliato",
    "riconcilia_tutti_cedolini",
    "riconcilia_tutti_f24",
    "riconcilia_tutti_stipendi",
]
