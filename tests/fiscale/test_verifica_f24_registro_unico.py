"""Verifica coerenza «F24 registrati vs pagati in banca».

Il controllo filtrava ``f24_unificato`` su ``data_scadenza``, campo che
nessun F24 ha (contava sempre zero), e cercava in banca solo
``descrizione_originale`` con importo negativo, perdendo le righe CSV e
Enable Banking (importo positivo con ``tipo=uscita``). Ora legge il registro
unico F24 per data di versamento e la banca su tutti i campi di causale.
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.verifica_coerenza import VerificaCoerenza


def test_f24_dal_registro_unico_e_banca_con_segno_da_tipo():
    async def scenario():
        db = ClientArchivioMemoria()["test_verifica_f24_registro"]
        await db["f24_unificato"].insert_many([
            {"id": "F24-LUG", "dati_generali": {"data_versamento": "2026-07-16"},
             "totali": {"saldo_finale_cents": 50000}},
            {"id": "F24-AGO", "dati_generali": {"data_versamento": "2026-08-20"},
             "totali": {"saldo_finale_cents": 30000}},
            # Versato l'anno prima: fuori dal conteggio 2026.
            {"id": "F24-2025", "dati_generali": {"data_versamento": "2025-12-16"},
             "totali": {"saldo_finale_cents": 99900}},
        ])
        await db["estratto_conto_movimenti"].insert_many([
            # Riga CSV / Enable Banking: importo positivo, segno nel tipo.
            {"id": "EC-1", "data": "2026-07-17", "importo": 500.00, "tipo": "uscita",
             "descrizione": "I24 AGENZIA ENTRATE DELEGA"},
            # Causale solo nel campo «causale», importo negativo.
            {"id": "EC-2", "data": "2026-03-10", "importo": -200.00,
             "causale": "PAGAMENTO F24 INPS"},
            # Un rimborso in entrata non e' un pagamento F24.
            {"id": "EC-3", "data": "2026-05-02", "importo": 80.00, "tipo": "entrata",
             "descrizione": "RIMBORSO ERARIO"},
            {"id": "EC-4", "data": "2026-05-03", "importo": -70.00, "tipo": "uscita",
             "descrizione": "BONIFICO FORNITORE"},
        ])
        return await VerificaCoerenza(db).verifica_f24_vs_pagamenti(2026)

    esito = asyncio.run(scenario())
    assert esito["f24_totale"] == 800.00
    # Luglio ha l'addebito compatibile (stessa cifra, nella finestra): pagato.
    assert esito["f24_pagati"] == 500.00
    assert esito["pagamenti_banca_f24"] == 700.00
    assert esito["differenza"] == -200.00
