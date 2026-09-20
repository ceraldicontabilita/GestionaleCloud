"""Guardia: il tetto del ponte limita il lavoro di un giro, non le fatture viste.

Il ponte GestionaleCloud -> Lotti chiedeva l'elenco delle fatture dell'anno e
ne teneva le prime `massimo` (1.000, valore fisso dello scheduler). L'elenco
arriva ordinato per **data crescente**: tagliarlo significa buttare via le
fatture piu' RECENTI.

Misurato in produzione il 20/09/2026: 1.444 fatture 2026 in archivio, tetto a
1.000, e la millesima cade al **30/06/2026**. Le 444 dal 30/06 in poi non
sarebbero mai entrate in Lotti — niente lotti fornitori, niente tracciabilita',
niente prezzi d'acquisto reali — e il buco cresceva di una fattura al giorno.
Nessun errore, nessun alert: solo merce che non arriva.

I lotti fornitori in archivio si fermavano infatti al **26/05/2026**, con
giacenze di latticini ferme da mesi.

La correzione: il tetto si applica alle fatture **ancora da prendere**, dopo
aver tolto quelle gia' registrate. Cosi' ogni giro lavora roba nuova, in pochi
giri l'arretrato si chiude, e a regime il tetto non morde mai. `arretrato` dice
quante ne restano, cosi' il ritardo e' un numero che si legge invece di un
silenzio.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def ponte(monkeypatch):
    import app.lotti.routers.fatture as fatture
    import app.lotti.routers.gestionale_fatture as module

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(module, "db", database)
    monkeypatch.setattr(fatture, "db", database)
    monkeypatch.setenv("GESTIONALECLOUD_API_URL", "https://gestionale.example")
    monkeypatch.setenv("LOTTI_INTEGRATION_KEY", "test-secret")
    return module, database


def _fattura(n: int) -> dict:
    """Fatture ordinate per data crescente, come le manda la fonte."""
    giorno = f"2026-{1 + (n // 100):02d}-{1 + (n % 28):02d}"
    return {
        "source_id": f"invoice-{n:04d}",
        "source_hash": f"hash-{n:04d}",
        "invoice_number": f"{n}/A",
        "invoice_date": giorno,
        "supplier_name": "FORNITORE TEST SRL",
        "supplier_vat": "01234567890",
        "has_xml": True,
        "source": "gestionalecloud",
    }


def _monta_elenco(module, monkeypatch, fatture: list):
    async def elenco(_client, _anno):
        return list(fatture), len(fatture)

    monkeypatch.setattr(module, "_elenco", elenco)


def test_le_fatture_oltre_il_tetto_non_spariscono_ma_restano_in_arretrato(ponte, monkeypatch):
    module, _database = ponte
    fatture = [_fattura(n) for n in range(1444)]
    _monta_elenco(module, monkeypatch, fatture)

    esito = run(module.esegui_sync_gestionale(anno=2026, massimo=1000, anteprima=True))

    assert esito["totale_fonte"] == 1444
    assert esito["importabili"] == 1000, "un giro lavora al massimo `massimo` fatture"
    assert esito["arretrato"] == 444, (
        "Le fatture oltre il tetto devono essere contate come arretrato. "
        "Prima sparivano in silenzio, ed essendo l'elenco ordinato per data "
        "erano sempre le piu' recenti."
    )


def test_il_secondo_giro_prende_le_fatture_che_il_primo_ha_lasciato(ponte, monkeypatch):
    """E' il controllo che descrive il guasto, non il suo rimedio.

    Col taglio applicato all'elenco intero, il secondo giro riceveva di nuovo
    le STESSE prime 1.000 fatture: le ultime non arrivavano mai, per quanti
    giri si facessero.
    """
    module, database = ponte
    fatture = [_fattura(n) for n in range(1444)]
    _monta_elenco(module, monkeypatch, fatture)

    # Il primo giro ha gia' preso le prime 1.000: lo registriamo come farebbe lui.
    run(database.gestionale_fatture_ricevute.insert_many([
        {"source_id": f["source_id"], "source_hash": f["source_hash"],
         "stato": "importata"}
        for f in fatture[:1000]
    ]))

    esito = run(module.esegui_sync_gestionale(anno=2026, massimo=1000, anteprima=True))

    assert esito["gia_ricevute"] == 1000
    assert esito["arretrato"] == 0
    assert esito["importabili"] == 444, (
        f"Il secondo giro ha trovato {esito['importabili']} fatture da prendere "
        "invece di 444: sta rilavorando le stesse di prima e le piu' recenti "
        "non entreranno mai."
    )


def test_una_fattura_cambiata_non_viene_saltata_dal_prefiltro(ponte, monkeypatch):
    """Il prefiltro salta solo chi ha lo STESSO hash: un documento cambiato
    dopo la ricezione deve continuare a diventare un conflitto visibile."""
    module, database = ponte
    fattura = _fattura(1)
    _monta_elenco(module, monkeypatch, [fattura])
    run(database.gestionale_fatture_ricevute.insert_one({
        "source_id": fattura["source_id"], "source_hash": "hash-vecchio",
        "stato": "importata",
    }))

    esito = run(module.esegui_sync_gestionale(anno=2026, massimo=1000, anteprima=True))

    assert esito["gia_ricevute"] == 0
    assert len(esito["conflitti"]) == 1
    assert esito["conflitti"][0]["source_id"] == fattura["source_id"]


def test_un_errore_senza_messaggio_dice_almeno_di_che_tipo_e(ponte, monkeypatch):
    """In produzione quattro giri hanno lasciato scritto soltanto
    «Lettura fonte GestionaleCloud: »: un guasto muto."""
    module, _database = ponte

    class TimeoutSenzaMessaggio(Exception):
        pass

    async def elenco(_client, _anno):
        raise TimeoutSenzaMessaggio()

    monkeypatch.setattr(module, "_elenco", elenco)

    esito = run(module.esegui_sync_gestionale(anno=2026, anteprima=True))

    assert esito["ok"] is False
    (errore,) = esito["errori"]
    assert errore.endswith("TimeoutSenzaMessaggio"), (
        f"L'errore dice «{errore}»: chi lo legge non sa cosa sia successo."
    )


def test_un_errore_con_messaggio_lo_conserva(ponte, monkeypatch):
    module, _database = ponte

    async def elenco(_client, _anno):
        raise RuntimeError("statement timeout sulla RPC")

    monkeypatch.setattr(module, "_elenco", elenco)

    esito = run(module.esegui_sync_gestionale(anno=2026, anteprima=True))

    (errore,) = esito["errori"]
    assert "statement timeout sulla RPC" in errore
    assert "RuntimeError" in errore
