"""Cruscotto Agenti per settore: conteggi dall'archivio in memoria, nessuno zero inventato."""
import asyncio

from app.services.agenti_settori import SETTORI, stato_settori
from app.services.archivio_documenti_memoria import ArchivioDocumenti


def _coda(settore, nome):
    return next(c for c in settore["code_ferme"] if c["nome"] == nome)


async def _prepara(db):
    await db["sistema_stato"].insert_many([
        {"chiave": "riconciliazione_ultimo_giro", "terminato_at": "2026-10-02T05:30:00+00:00",
         "conteggi": {"bonifici": 3, "f24": 2, "stipendi": 1}, "errore": None},
        {"chiave": "drive_cartella_unica_last_sync", "valore": "2026-10-02T06:00:00+00:00",
         "last_result": {"letti": 100, "elaborati": 80, "errori": 7}, "last_error": None},
        {"chiave": "notifiche_pec_verbali_ultimo_giro", "eseguito_at": "2026-10-02T04:00:00+00:00",
         "totali": 136, "agganciate": 10, "da_agganciare": 120},
    ])
    await db["drive_cartella_unica"].insert_many([
        {"id": "E1", "cartella": "ERRORI", "tipo": "f24", "motivo": "F24 non quadrato o non validato: ..."},
        {"id": "E2", "cartella": "ERRORI", "tipo": "f24", "motivo": "nessuna riga tributo"},
        {"id": "E3", "cartella": "ERRORI", "tipo": "quietanza_f24", "motivo": "senza testo"},
        {"id": "E4", "cartella": "ERRORI", "tipo": "corrispettivo", "motivo": "XML non quadrato"},
        {"id": "E5", "cartella": "ERRORI", "tipo": "non_riconosciuto", "motivo": "tipo di documento non riconosciuto"},
        {"id": "A1", "cartella": "ARRETRATO", "tipo": "non_riconosciuto", "motivo": "documento del 2019"},
        {"id": "OK", "cartella": "ELABORATE", "tipo": "fattura"},
    ])
    await db["verbali_noleggio"].insert_many([
        {"id": "V1", "stato": "da_pagare", "pdf_data": "x" * 10},
        {"id": "V2", "stato": "DA_PAGARE", "driver_id": "D1"},
        {"id": "V3", "stato": "pagato"},
        {"id": "V4", "stato": "quarantena"},
    ])
    await db["cedolini"].insert_many([
        {"id": "C1", "netto": 1200.5, "stato_netto": "NETTO_VERIFICATO_DA_CEDOLINO"},
        {"id": "C2", "netto": None, "stato_netto": "NETTO_NON_PRESENTE_O_NON_LEGGIBILE"},
        {"id": "C3", "netto": 900, "stato_netto": "NETTO_VERIFICATO_DA_CEDOLINO", "status": "sostituito"},
        {"id": "C4", "netto": 800, "varianti_da_decidere": True},
    ])
    await db["invoices"].insert_many([
        {"id": "F1", "status": "imported", "metodo_pagamento": "sospesa"},
        {"id": "F2", "status": "imported", "metodo_pagamento": "bonifico"},
        {"id": "F3", "status": "imported", "pagato": True},
        {"id": "F4", "status": "archived", "metodo_pagamento": "sospesa"},
    ])
    await db["estratto_conto_movimenti"].insert_many([
        {"id": "M1", "data": "2026-09-01", "categoria": None},
        {"id": "M2", "data": "2026-09-02", "categoria": "Fatture"},
        {"id": "M3", "data": "2026-09-03", "ignorata": True},
    ])
    await db["documents_inbox"].insert_many([
        {"id": "I1", "filename": "a.pdf", "needs_review": True},
        {"id": "I2", "filename": "b.pdf", "categoria": "f24"},
    ])
    await db["agenti_proposte"].insert_many([
        {"id": "P1", "settore": "f24", "stato": "proposta"},
        {"id": "P2", "settore": "f24", "stato": "confermata"},
        {"id": "P3", "settore": "altro", "stato": "proposta"},
    ])


def test_conteggi_per_settore(monkeypatch):
    db = ArchivioDocumenti()
    hr = ArchivioDocumenti("HR")
    from app.hr.database import Database as DatabaseHR

    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: hr))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    async def scenario():
        await _prepara(db)
        await hr["bonifici_da_associare"].insert_many([
            {"id": "B1", "stato": "da_associare"}, {"id": "B2", "stato": "associato"}])
        return await stato_settori(db)

    r = asyncio.run(scenario())
    per_id = {s["id"]: s for s in r["settori"]}
    assert [s["id"] for s in r["settori"]] == [s["id"] for s in SETTORI]

    f24 = per_id["f24"]
    assert _coda(f24, "File in ERRORI su Drive")["conteggio"] == 3
    assert _coda(f24, "F24 non quadrati")["conteggio"] == 1
    assert _coda(f24, "F24 non quadrati")["rotta_pagina"] == "/documenti/drive"
    assert f24["proposte_in_attesa"] == 1
    giro = next(g for g in f24["giri"] if g["chiave"] == "riconciliazione_ultimo_giro")
    assert giro["at"] == "2026-10-02T05:30:00+00:00" and giro["conteggi"] == {"associati": 2}
    cartella = next(g for g in f24["giri"] if g["chiave"] == "drive_cartella_unica_last_sync")
    assert cartella["conteggi"] == {"letti": 100, "associati": 80, "errori": 7}

    assert _coda(per_id["corrispettivi"], "Chiusure RT scartate")["conteggio"] == 1
    assert _coda(per_id["verbali"], "Verbali senza driver")["conteggio"] == 1
    pec = next(g for g in per_id["verbali"]["giri"] if g["chiave"] == "notifiche_pec_verbali_ultimo_giro")
    assert pec["conteggi"] == {"letti": 136, "associati": 10, "da_agganciare": 120}
    ricostruzione = next(g for g in per_id["verbali"]["giri"] if g["chiave"] == "verbali_ricostruzione")
    assert ricostruzione["mai_eseguito"] is True and ricostruzione["at"] is None

    assert _coda(per_id["cedolini"], "Buste senza netto verificato")["conteggio"] == 2  # C2 e C4; C3 sostituita non conta
    assert _coda(per_id["cedolini"], "Varianti da decidere")["conteggio"] == 1
    assert _coda(per_id["bonifici"], "Bonifici HR da associare")["conteggio"] == 1
    assert _coda(per_id["bonifici"], "Movimenti banca senza categoria")["conteggio"] == 1
    assert _coda(per_id["fatture"], "Fatture aperte senza metodo")["conteggio"] == 1
    assert _coda(per_id["fatture"], "Letture AI da rivedere")["conteggio"] == 1

    agenti = r["agenti_ai"]
    assert agenti["chiave_presente"] is False
    assert agenti["non_riconosciuti_errori"] == 1 and agenti["arretrato"] == 1
    assert agenti["inbox_non_classificata"] == 1 and agenti["proposte_altro"] == 1


def test_senza_fonte_e_dato_non_disponibile_mai_zero(monkeypatch):
    """HR non configurato e registro che fallisce: None, non 0."""
    db = ArchivioDocumenti()
    from app.hr.database import Database as DatabaseHR, DatabaseNonConfigurato

    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: DatabaseNonConfigurato("non connesso")))

    class Rotta:
        def find(self, *a, **k):
            raise RuntimeError("registro non raggiungibile")

    originale = db.__getitem__

    def getitem(nome):
        return Rotta() if nome == "drive_cartella_unica" else originale(nome)

    monkeypatch.setattr(db, "__getitem__", getitem, raising=False)
    monkeypatch.setattr(type(db), "__getitem__", lambda self, nome: getitem(nome))

    r = asyncio.run(stato_settori(db))
    per_id = {s["id"]: s for s in r["settori"]}
    assert _coda(per_id["bonifici"], "Bonifici HR da associare")["conteggio"] is None
    assert _coda(per_id["f24"], "File in ERRORI su Drive")["conteggio"] is None
    assert "F24 non quadrati" not in {c["nome"] for c in per_id["f24"]["code_ferme"]}
    assert r["agenti_ai"]["non_riconosciuti_errori"] is None
    # un archivio vuoto ma leggibile conta davvero zero
    assert _coda(per_id["verbali"], "Verbali senza driver")["conteggio"] == 0
