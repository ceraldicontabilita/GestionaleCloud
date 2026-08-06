"""POS reale con piu' terminali (Nexi + SumUp).

Il POS reale del giorno e' la somma dei gestori. Il rischio piu' grave e' il
doppio conteggio: le chiusure gia' in produzione non hanno il campo gestore,
e trattarle come righe di un terminale diverso raddoppierebbe l'incasso.
"""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.scritture_contabili import (
    GESTORE_POS_DEFAULT,
    chiusura_pos_del_giorno,
    filtro_gestore_pos,
    normalizza_gestore_pos,
    registra_chiusura_pos_reale,
)


def _run(awaitable):
    return asyncio.run(awaitable)


def _db():
    return AsyncMongoMockClient()["pos_multi_gestore_test"]


def _chiusura(importo, gestore=None, source="inserimento_manuale_terminale"):
    riga = {"data": "2026-08-06", "importo": importo, "source": source}
    if gestore is not None:
        riga["gestore"] = gestore
    return riga


# --- Normalizzazione -------------------------------------------------------

def test_una_riga_storica_senza_gestore_e_nexi():
    assert normalizza_gestore_pos(None) == GESTORE_POS_DEFAULT
    assert normalizza_gestore_pos("") == GESTORE_POS_DEFAULT
    assert normalizza_gestore_pos("  SumUp ") == "sumup"


def test_il_filtro_nexi_intercetta_anche_le_righe_senza_campo():
    """Altrimenti un nuovo inserimento Nexi creerebbe una riga parallela."""
    filtro = filtro_gestore_pos("nexi")
    alternative = filtro["$or"]
    assert {"gestore": {"$exists": False}} in alternative
    assert {"gestore": "nexi"} in alternative
    # Per gli altri gestori il filtro resta secco.
    assert filtro_gestore_pos("sumup") == {"gestore": "sumup"}


# --- Totale del giorno -----------------------------------------------------

def test_il_totale_somma_i_due_terminali():
    db = _db()
    _run(db.chiusure_pos_manuali.insert_many([
        _chiusura(300.0, "nexi"),
        _chiusura(120.50, "sumup"),
    ]))
    assert _run(chiusura_pos_del_giorno(db, "2026-08-06")) == 420.50


def test_una_chiusura_storica_non_viene_contata_due_volte():
    """Riga senza gestore (Nexi storico) + riga Nexi esplicita: e' lo stesso
    terminale, quindi vale la correzione manuale, non la somma."""
    db = _db()
    _run(db.chiusure_pos_manuali.insert_many([
        _chiusura(300.0),            # storica, senza campo gestore
        _chiusura(280.0, "nexi"),    # correzione dello stesso terminale
    ]))
    assert _run(chiusura_pos_del_giorno(db, "2026-08-06")) == 280.0


def test_la_correzione_di_un_terminale_non_cancella_l_altro():
    db = _db()
    _run(db.chiusure_pos_manuali.insert_many([
        _chiusura(500.0, "nexi", source="import_csv"),
        _chiusura(450.0, "nexi"),     # correzione manuale su Nexi
        _chiusura(80.0, "sumup"),     # SumUp resta intatto
    ]))
    assert _run(chiusura_pos_del_giorno(db, "2026-08-06")) == 530.0


def test_zero_su_un_terminale_resta_un_valore_valido():
    """Zero significa 'quel terminale non ha incassato', non 'dato assente'."""
    db = _db()
    _run(db.chiusure_pos_manuali.insert_many([
        _chiusura(0.0, "sumup"),
        _chiusura(200.0, "nexi"),
    ]))
    assert _run(chiusura_pos_del_giorno(db, "2026-08-06")) == 200.0


def test_senza_chiusure_resta_none_per_il_fallback_xml():
    db = _db()
    assert _run(chiusura_pos_del_giorno(db, "2026-08-06")) is None


def test_il_comportamento_di_nexi_da_solo_non_cambia():
    """Nessuna regressione per chi ha un solo terminale."""
    db = _db()
    _run(db.chiusure_pos_manuali.insert_many([
        _chiusura(1000.0, source="import_csv"),
        _chiusura(950.0),  # correzione manuale, prevale
    ]))
    assert _run(chiusura_pos_del_giorno(db, "2026-08-06")) == 950.0


# --- Registrazione (lato scrittura) ----------------------------------------

DATA = "2026-08-06"


async def _uscita_pos(db):
    return await db["prima_nota_cassa"].find_one(
        {"data": DATA, "categoria": "POS Verso Banca"}
    )


def test_registrare_sumup_non_sovrascrive_la_chiusura_nexi():
    """Il bug piu' costoso: una find_one sulla sola data prendeva la riga
    dell'altro terminale e la riscriveva, perdendo un incasso reale."""
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 300.0, gestore="nexi"))
    _run(registra_chiusura_pos_reale(db, DATA, 120.50, gestore="sumup"))

    righe = _run(db.chiusure_pos_manuali.find({"data": DATA}).to_list(10))
    assert sorted(r["gestore"] for r in righe) == ["nexi", "sumup"]
    assert sorted(r["importo"] for r in righe) == [120.50, 300.0]


def _righe_pos(db, collection, **extra):
    query = {"data": DATA, **extra}
    return _run(db[collection].find(query).to_list(20))


def test_ogni_circuito_ha_la_sua_coppia_di_trasferimento():
    """Esempio dell'utente: corrispettivo 1.000 = 400 contanti + 500 Nexi +
    100 SumUp. Gli accrediti arrivano separati (NUMIA su BPM, payout su
    SumUp): una riga unica da 600 non sarebbe riconciliabile con nessuno."""
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 500.0, gestore="nexi"))
    esito = _run(registra_chiusura_pos_reale(db, DATA, 100.0, gestore="sumup"))

    assert esito["importo"] == 100.0             # la chiusura del circuito
    assert esito["importo_totale_giorno"] == 600.0

    uscite = _righe_pos(db, "prima_nota_cassa", categoria="POS Verso Banca")
    assert {u["circuito"]: u["importo"] for u in uscite} == {
        "NEXI": 500.0, "SUMUP": 100.0}

    banca = _righe_pos(db, "prima_nota_banca", source="trasferimento_pos")
    assert {b["circuito"]: b["importo"] for b in banca} == {
        "NEXI": 500.0, "SUMUP": 100.0}

    # Ogni circuito e' una sola operazione su due registri: stesso
    # trasferimento_id fra la sua uscita e la sua entrata, mai incrociato.
    per_circuito = {u["circuito"]: u["trasferimento_id"] for u in uscite}
    for riga in banca:
        assert riga["trasferimento_id"] == per_circuito[riga["circuito"]]
    assert per_circuito["NEXI"] != per_circuito["SUMUP"]


def test_il_credito_pos_nasce_in_transito():
    """Non e' denaro gia' sul conto finche' l'accredito non lo conferma."""
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 100.0, gestore="sumup"))
    banca = _righe_pos(db, "prima_nota_banca", source="trasferimento_pos")
    assert banca[0]["in_transito"] is True
    assert banca[0]["riconciliato"] is False
    assert banca[0]["giorno_vendita"] == DATA


def test_zero_su_un_terminale_non_archivia_il_trasferimento_dell_altro():
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 500.0, gestore="nexi"))
    _run(registra_chiusura_pos_reale(db, DATA, 100.0, gestore="sumup"))
    # Correzione serale: su SumUp non era passato nulla.
    _run(registra_chiusura_pos_reale(db, DATA, 0, gestore="sumup"))

    uscite = {u["circuito"]: u for u in
              _righe_pos(db, "prima_nota_cassa", categoria="POS Verso Banca")}
    assert uscite["NEXI"].get("status") != "deleted"
    assert uscite["NEXI"]["importo"] == 500.0
    assert uscite["SUMUP"]["status"] == "deleted"
    assert _run(chiusura_pos_del_giorno(db, DATA)) == 500.0


def test_zero_su_tutti_i_terminali_archivia_il_trasferimento():
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 300.0, gestore="nexi"))
    _run(registra_chiusura_pos_reale(db, DATA, 0, gestore="nexi"))

    uscita = _run(_uscita_pos(db))
    assert uscita["status"] == "deleted"


def test_nessun_circuito_crea_una_seconda_entrata_di_cassa():
    """Il ricavo e' gia' nel corrispettivo XML: Nexi e SumUp lo dividono."""
    db = _db()
    _run(db.corrispettivi.insert_one(
        {"id": "c1", "data": DATA, "totale": 1000.0, "pagato_elettronico": 600.0}
    ))
    _run(db.prima_nota_cassa.insert_one({
        "id": "entrata", "data": DATA, "tipo": "entrata",
        "categoria": "Corrispettivi", "importo": 1000.0,
    }))
    _run(registra_chiusura_pos_reale(db, DATA, 500.0, gestore="nexi"))
    _run(registra_chiusura_pos_reale(db, DATA, 100.0, gestore="sumup"))

    entrate = _righe_pos(db, "prima_nota_cassa", tipo="entrata")
    assert len(entrate) == 1
    assert entrate[0]["importo"] == 1000.0
    # saldo contanti = totale XML - Nexi - SumUp
    assert entrate[0]["pagato_contanti"] == 400.0
    assert entrate[0]["pagato_elettronico"] == 600.0
    # Il valore fiscale XML non viene mai toccato.
    assert _run(db.corrispettivi.find_one({"id": "c1"}))["pagato_elettronico"] == 600.0


def test_la_correzione_resta_idempotente_per_gestore():
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 120.50, gestore="sumup"))
    esito = _run(registra_chiusura_pos_reale(db, DATA, 120.50, gestore="sumup"))

    assert esito["action"] == "noop"
    assert len(_run(db.chiusure_pos_manuali.find({"data": DATA}).to_list(10))) == 1


def test_una_chiusura_storica_senza_gestore_viene_corretta_non_duplicata():
    """Produzione: le righe esistenti non hanno il campo gestore."""
    db = _db()
    _run(db.chiusure_pos_manuali.insert_one(
        {"id": "storica", "data": DATA, "importo": 300.0}
    ))
    esito = _run(registra_chiusura_pos_reale(db, DATA, 280.0, gestore="nexi"))

    righe = _run(db.chiusure_pos_manuali.find({"data": DATA}).to_list(10))
    assert len(righe) == 1
    assert righe[0]["id"] == "storica"
    assert righe[0]["gestore"] == "nexi"
    assert esito["importo_precedente"] == 300.0
    assert esito["importo_totale_giorno"] == 280.0
