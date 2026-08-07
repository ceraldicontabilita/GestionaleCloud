"""Bonifica dei trasferimenti POS ricavati dall'XML.

Sono scritture reali gia' in Prima Nota: la regola dell'utente vieta di
cancellare dati veri. Vanno riclassificate, e la giornata deve tornare a
dichiararsi incompleta invece di dare per buono un importo fiscale.
"""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services import bonifica_pos_xml
from app.services.scritture_contabili import registra_chiusura_pos_reale


def _run(awaitable):
    return asyncio.run(awaitable)


def _db():
    return AsyncMongoMockClient()["bonifica_test"]


def _riga_da_xml(db, data="2026-08-03", importo=1629.50):
    """Riga come quelle in produzione: fonte xml, nessun circuito."""
    _run(db.prima_nota_cassa.insert_one({
        "id": f"c-{data}", "data": data, "tipo": "uscita", "importo": importo,
        "categoria": "POS Verso Banca", "source": "corrispettivo_import",
        "descrizione": f"POS {data} → Banca (da XML)", "quota_pos_fonte": "xml",
    }))
    _run(db.prima_nota_banca.insert_one({
        "id": f"b-{data}", "data": data, "tipo": "entrata", "importo": importo,
        "categoria": "Corrispettivi POS", "source": "trasferimento_pos",
        "quota_pos_fonte": "xml", "riconciliato": False,
    }))
    _run(db.corrispettivi.insert_one({
        "id": f"corr-{data}", "data": data, "totale": 2181.40,
        "pagato_elettronico": importo,
    }))
    return db


# --- Analisi (sola lettura) ------------------------------------------------

def test_l_analisi_trova_le_righe_da_xml_senza_toccarle():
    db = _riga_da_xml(_db())
    esito = _run(bonifica_pos_xml.analizza(db))

    assert esito["giornate_totali"] == 1
    assert esito["righe_cassa"] == 1 and esito["righe_banca"] == 1
    assert esito["importo_totale"] == 1629.50
    # Sola lettura: nessun campo di bonifica scritto.
    riga = _run(db.prima_nota_cassa.find_one({"id": "c-2026-08-03"}))
    assert "bonifica_motivo" not in riga


def test_una_chiusura_nexi_guarisce_gia_da_sola_la_riga_da_xml():
    """La riga storica non ha gestore, quindi appartiene a Nexi: la chiusura
    la corregge sul posto e sparisce dall'ambito della bonifica."""
    db = _riga_da_xml(_db())
    _run(registra_chiusura_pos_reale(db, "2026-08-03", 1500.0, gestore="nexi"))

    esito = _run(bonifica_pos_xml.analizza(db))
    assert esito["giornate_totali"] == 0


def test_distingue_le_giornate_gia_coperte_dal_pos_reale():
    """Chi ha gia' il dato vero si sistema al prossimo riallineamento."""
    db = _riga_da_xml(_db())
    _riga_da_xml(db, data="2026-08-04", importo=900.0)
    # Chiusura di un ALTRO circuito: la riga da XML resta li', ma il giorno
    # una fonte reale ce l'ha.
    _run(registra_chiusura_pos_reale(db, "2026-08-04", 880.0, gestore="sumup"))

    esito = _run(bonifica_pos_xml.analizza(db))
    coperte = [g["data"] for g in esito["gia_coperte_dal_pos_reale"]]
    scoperte = [g["data"] for g in esito["senza_pos_reale"]]
    assert coperte == ["2026-08-04"]
    assert scoperte == ["2026-08-03"]


def test_le_righe_gia_marcate_deleted_restano_fuori():
    db = _db()
    _run(db.prima_nota_cassa.insert_one({
        "id": "vecchia", "data": "2026-08-03", "tipo": "uscita",
        "importo": 100.0, "quota_pos_fonte": "xml", "status": "deleted",
    }))
    assert _run(bonifica_pos_xml.analizza(db))["righe_cassa"] == 0


def test_il_filtro_per_anno_limita_l_ambito():
    db = _riga_da_xml(_db())
    _riga_da_xml(db, data="2025-08-03", importo=500.0)

    assert _run(bonifica_pos_xml.analizza(db, anno=2026))["giornate_totali"] == 1
    assert _run(bonifica_pos_xml.analizza(db))["giornate_totali"] == 2


# --- Applicazione ----------------------------------------------------------

def test_la_bonifica_non_cancella_mai_nulla():
    """Regola vincolante dell'utente: nessuna cancellazione di dati reali."""
    db = _riga_da_xml(_db())
    esito = _run(bonifica_pos_xml.applica(db))

    assert esito["cancellazioni"] == 0
    assert len(_run(db.prima_nota_cassa.find({}).to_list(10))) == 1
    assert len(_run(db.prima_nota_banca.find({}).to_list(10))) == 1


def test_marca_le_righe_come_fonte_non_attendibile():
    db = _riga_da_xml(_db())
    esito = _run(bonifica_pos_xml.applica(db, actor={"sub": "tester"}))

    assert esito["righe_marcate"] == 2
    for registro, chiave in (("prima_nota_cassa", "c-2026-08-03"),
                             ("prima_nota_banca", "b-2026-08-03")):
        riga = _run(db[registro].find_one({"id": chiave}))
        assert riga["pos_fonte_attendibile"] is False
        assert riga["bonifica_motivo"] == "pos_da_xml_non_attendibile"
        assert riga["bonifica_by"] == "tester"
        # L'importo resta quello scritto: la bonifica non inventa il dato.
        assert riga["importo"] == 1629.50


def test_la_giornata_scoperta_torna_in_attesa():
    db = _riga_da_xml(_db())
    esito = _run(bonifica_pos_xml.applica(db))

    assert esito["giornate_riportate_in_attesa"] == 1
    corr = _run(db.corrispettivi.find_one({"data": "2026-08-03"}))
    assert corr["pos_stato"] == "attende_chiusura_pos_reale"


def test_la_giornata_gia_coperta_non_viene_allarmata():
    db = _riga_da_xml(_db(), data="2026-08-04", importo=900.0)
    _run(registra_chiusura_pos_reale(db, "2026-08-04", 880.0, gestore="sumup"))

    esito = _run(bonifica_pos_xml.applica(db))
    assert esito["giornate_riportate_in_attesa"] == 0
    corr = _run(db.corrispettivi.find_one({"data": "2026-08-04"}))
    assert corr.get("pos_stato") != "attende_chiusura_pos_reale"


def test_la_chiusura_reale_successiva_corregge_l_importo():
    """Il percorso completo: bonifica, poi arriva il terminale."""
    db = _riga_da_xml(_db())
    _run(bonifica_pos_xml.applica(db))
    _run(registra_chiusura_pos_reale(db, "2026-08-03", 1500.0, gestore="nexi"))

    # La riga storica senza gestore appartiene a Nexi: viene corretta,
    # non affiancata da una seconda.
    uscite = _run(db.prima_nota_cassa.find({"data": "2026-08-03"}).to_list(10))
    assert len(uscite) == 1
    assert uscite[0]["importo"] == 1500.0
    assert uscite[0]["quota_pos_fonte"] == "chiusura_manuale"


def test_rieseguire_la_bonifica_e_idempotente():
    db = _riga_da_xml(_db())
    primo = _run(bonifica_pos_xml.applica(db))
    secondo = _run(bonifica_pos_xml.applica(db))

    assert primo["righe_cassa"] == secondo["righe_cassa"] == 1
    assert len(_run(db.prima_nota_cassa.find({}).to_list(10))) == 1
