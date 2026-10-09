"""La pagina Alert apre il record: link derivato da entita_collection/id.

6.527 alert su 6.536 non avevano `link`: la lista ora lo ricava coi
deep-link canonici e mette le fatture candidate in una lista."""
import asyncio

from app.database import Database
from app.routers import alerts
from app.services.archivio_documenti_memoria import ArchivioDocumenti


def test_link_dai_deep_link_canonici():
    assert alerts.link_record("invoices", "F 1") == "/fatture?invoice_id=F%201"
    assert alerts.link_record("estratto_conto_movimenti", "M-1") == "/riconciliazione/banca?movimento=M-1"
    assert alerts.link_record("prima_nota_banca", "P-1") == "/prima-nota#sezione=banca&selected=P-1"
    assert alerts.link_record("partite_aperte", "X") is None
    assert alerts.link_record("invoices", "") is None


def test_lista_espone_link_e_fatture_candidate(monkeypatch):
    db = ArchivioDocumenti()

    async def scenario():
        await db["alerts"].insert_many([
            {"id": "A-1", "codice": "RIC_PAGAMENTO_MULTIPLO", "stato": "aperto",
             "entita_id": "MOV-1", "entita_collection": "estratto_conto_movimenti",
             "created_at": "2026-09-27T10:00:00",
             "extra": {"fatture_candidate": [
                 {"id": "F-1", "numero": "1/A", "importo": 100.1},
                 {"id": "F-2", "numero": "2/A", "importo": 199.9},
             ]}},
            {"id": "A-2", "codice": "X", "stato": "aperto", "link": "/fornitori?search=Alfa",
             "entita_id": "F-9", "entita_collection": "invoices",
             "created_at": "2026-09-26T10:00:00"},
            {"id": "A-3", "codice": "RIC_DIFFERENZA_IMPORTO", "stato": "aperto",
             "entita_id": "MOV-3", "entita_collection": "estratto_conto_movimenti",
             "created_at": "2026-09-25T10:00:00", "extra": {"fattura_id": "F-7"}},
        ])
        return await alerts.lista_alerts(
            tipo=None, severita=None, modulo=None, alert_id=None, stato="aperto",
            letto=None, risolto=None, offset=0, limit=50,
        )

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    risposta = asyncio.run(scenario())
    per_id = {a["id"]: a for a in risposta["alerts"]}

    assert per_id["A-1"]["link"] == "/riconciliazione/banca?movimento=MOV-1"
    assert per_id["A-1"]["fatture_candidate"] == [
        {"id": "F-1", "numero": "1/A", "importo": 100.1, "link": "/fatture?invoice_id=F-1"},
        {"id": "F-2", "numero": "2/A", "importo": 199.9, "link": "/fatture?invoice_id=F-2"},
    ]
    # un link gia' scritto non si sovrascrive
    assert per_id["A-2"]["link"] == "/fornitori?search=Alfa"
    assert per_id["A-2"]["fatture_candidate"] == []
    # la fattura di un alert di movimento e' fra i record coinvolti
    assert {"collezione": "invoices", "id": "F-7", "link": "/fatture?invoice_id=F-7"} in (
        per_id["A-3"]["record_coinvolti"]
    )
