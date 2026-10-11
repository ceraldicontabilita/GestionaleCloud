import asyncio
from unittest.mock import AsyncMock
from app.services.archivio_documenti_memoria import ArchivioDocumenti
from app.hr.services.sincronizza_paghe_mensili import sincronizza


def test_sincronizza_non_tronca_cedolini_o_bonifici(monkeypatch):
    db = ArchivioDocumenti('test')
    db['cedolini']._documents = [
        {'_id': f'c{i}', 'id': f'c{i}', 'dipendente_id': f'd{i // 100}',
         'mese': i % 100 % 12 + 1, 'anno': 2018 + i % 100 // 12,
         'netto': 100, 'tipo_cedolino': 'ordinario'} for i in range(3001)
    ]
    db['bonifici']._documents = [
        {'_id': f'b{i}', 'id': f'b{i}', 'cedolino_id': f'c{i}', 'importo': 100} for i in range(1001)
    ]
    writes = AsyncMock()
    monkeypatch.setattr(db['paghe_mensili'], 'update_one', writes)
    monkeypatch.setattr('app.services.associazione_salari.aggiorna_proiezioni', AsyncMock())
    monkeypatch.setattr('app.services.associazione_salari._allinea_cedolini_erp', AsyncMock())
    asyncio.run(sincronizza(db))
    assert writes.await_count == 3001
    rows = [call.args[1]['$set'] for call in writes.call_args_list]
    last_payment = next(r for r in rows if r.get('dipendente_id') == 'd10' and r.get('mese') == 1 and r.get('anno') == 2018)
    assert last_payment['bonifico_importo'] == 100
