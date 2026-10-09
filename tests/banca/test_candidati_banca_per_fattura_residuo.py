"""«Associa il pagamento in banca»: si cerca il residuo da pagare, non il totale.

La conferma pretende il movimento uguale al residuo pagabile (totale meno
ritenuta, meno quote gia' pagate). Prima i candidati si cercavano sul totale:
il netto di una parcella non compariva mai, e un importo vicino veniva
mostrato ma la conferma lo rifiutava («Quadratura bloccata»).
"""
import asyncio

from app.routers.prima_nota_module import banca as modulo


def _db(monkeypatch, nome, fattura, movimenti):
    from app.services.archivio_documenti_memoria import ClientArchivioMemoria
    db = ClientArchivioMemoria()[nome]
    asyncio.run(db["invoices"].insert_one(dict(fattura)))
    for m in movimenti:
        asyncio.run(db["estratto_conto_movimenti"].insert_one(dict(m)))
    monkeypatch.setattr(modulo.Database, "get_db", staticmethod(lambda: db))
    return db


def _mov(id_, importo, data="2026-05-10"):
    return {"id": id_, "data": data, "importo": importo, "tipo": "uscita",
            "descrizione": "VS.DISP. FAVORE STUDIO ROSSI", "livello_evidenza": "ufficiale"}


PARCELLA = {
    "id": "fatt-parcella", "invoice_number": "12", "invoice_date": "2026-05-02",
    "supplier_name": "STUDIO ROSSI", "total_amount": 1268.80, "importo_ritenuta": 210.0,
    "pagamento_rate_totale": 1058.80,
}


def test_parcella_con_ritenuta_trova_il_netto_e_spiega_il_lordo(monkeypatch):
    _db(monkeypatch, "parcella", PARCELLA, [_mov("netto", -1058.80), _mov("lordo", -1268.80)])
    esito = asyncio.run(modulo.candidati_banca_per_fattura("fatt-parcella"))
    assert esito["residuo"] == 1058.80
    per_id = {c["id"]: c for c in esito["candidati"]}
    assert per_id["netto"]["conferma"] == "intero"
    assert "importo esatto" in per_id["netto"]["prove"]
    assert per_id["lordo"]["conferma"] == "eccede"
    assert "ritenuta" in per_id["lordo"]["spiegazione"]
    assert esito["candidati"][-1]["id"] == "lordo"


def test_importo_vicino_si_conferma_come_acconto(monkeypatch):
    fattura = {"id": "fatt-1", "invoice_number": "7", "invoice_date": "2026-05-02",
               "supplier_name": "ALFA SRL", "total_amount": 500.00}
    _db(monkeypatch, "acconto", fattura, [_mov("vicino", -499.97)])
    esito = asyncio.run(modulo.candidati_banca_per_fattura("fatt-1"))
    candidato = esito["candidati"][0]
    assert candidato["conferma"] == "parziale"
    assert candidato["quota_cents"] == 49997
    assert "0,03" in candidato["spiegazione"]
