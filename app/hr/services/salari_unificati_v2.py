"""Salari unificati V2 — re-export del modulo unico.

La logica vive in `app/services/salari_unificati_v2.py`. Fino al 19/09/2026 qui
c'era una copia: era una fotografia piu' vecchia del lato ERP, e le mancavano
correzioni che non sono dettagli.

Cosa aveva solo il lato ERP, e che da qui passa anche all'app HR:

- **identita' documentale e deduplica** (`_cedolino_document_key`,
  `_cedolino_identity_filter`): questa copia generava un `uuid4()` nuovo a ogni
  passaggio e faceva l'upsert su `{cf, mese, anno}`, quindi un reimport
  sovrascriveva il record perdendo il collegamento al documento;
- **`_preserva_stato_pagamenti`**: un reimport serve ad arricchire dati e PDF,
  mai a cancellare una riconciliazione, un acconto o un pagamento gia'
  registrato. Qui li azzerava (`"pagamenti": []`);
- **anti-doppio movimento in Prima Nota** (correzione del 15/07/2026): il
  controllo di questa copia cercava solo `tipo="stipendio"` e non riconosceva
  il movimento scritto dall'event bus, che ha `tipo="uscita"`;
- **periodo contabile ammesso** (`salari_periodo.periodo_ammesso_in_prima_nota`):
  senza il filtro una busta fuori esercizio finiva comunque in Prima Nota;
- **busta successiva** (`cessazione_da_cedolino.busta_successiva`): la
  cessazione letta su una busta storica di chi e' stato riassunto non vale
  piu'. Senza questo, Carotenuto, Capezzuto e Guarino tornavano cessati;
- **deposito del cedolino nell'archivio HR**, `parse_importo_ita` al posto del
  `replace(',', '.')` a mano, proiezione senza payload sulle letture.

Cosa aveva solo questa copia, ed e' stato portato sul modulo unico prima di
cancellarla: il netto nullo che resta nullo (`app.constants.stati_netto`, Fase
3) e la lettura in blocco dei cedolini in `get_riepilogo_salari_tutti` al posto
del find per dipendente.

Le funzioni prendono `db` come parametro, quindi l'app HR continua a passare il
proprio (`app.hr.database.Database.get_db()`) e a scrivere sulle proprie
tabelle: cambia l'implementazione, non il database.
"""
from app.services.salari_unificati_v2 import (  # noqa: F401
    estrai_ferie_rol_from_text,
    get_riepilogo_salari_tutti,
    get_saldo_completo_dipendente,
    processa_cedolino_v2,
    registra_pagamento_salario,
)

__all__ = [
    "estrai_ferie_rol_from_text",
    "get_riepilogo_salari_tutti",
    "get_saldo_completo_dipendente",
    "processa_cedolino_v2",
    "registra_pagamento_salario",
]
