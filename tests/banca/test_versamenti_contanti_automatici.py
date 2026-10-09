"""Il versamento si riconosce dall'estratto conto, senza premere niente.

Il titolare: «nell'estratto conto c'e' il segno, la descrizione e l'importo,
quindi non vedo perche' dovrebbe sbagliare. Non devo far riparare niente».

Il vecchio comando «Ripara versamenti» sbagliava per un motivo preciso: il
contante versato e' spesso **gia' scritto a mano** in Prima Nota Cassa il
giorno in cui esce dal negozio, mentre la banca lo contabilizza il giorno
dopo. Il comando creava comunque la gamba di cassa, e il contante usciva due
volte. Questi test tengono fermo che non possa piu' succedere.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services.versamenti_contanti import classifica, riconosci_versamenti


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db(monkeypatch):
    finto = AsyncMongoMockClient()["Gestionale_Test"]
    from app.database import Database

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: finto))
    return finto


def _ec(id_, descrizione, importo, tipo, data="2026-03-10"):
    return {"id": id_, "descrizione_originale": descrizione, "importo": importo,
            "tipo": tipo, "data": data}


async def _prepara(db, movimenti):
    from app.database import Collections

    await db[Collections.BANK_STATEMENTS].insert_many(movimenti)


# ── il riconoscimento ──────────────────────────────────────────────────────

CASI = [
    ("VERS. CONTANTI - VVVVV", "entrata", "versamento"),
    ("VERSAMENTO CONTANTI", "entrata", "versamento"),
    ("PRELIEVO CONTANTI SPORTELLO", "uscita", "prelievo"),
    ("PRELEV. BANCOMAT CARTA 123", "uscita", "prelievo"),
    # Uno storno e' una rettifica della banca, non un secondo deposito.
    ("STORNO VERS. CONTANTI", "entrata", None),
    # Il segno deve concordare con la causale.
    ("VERS. CONTANTI - VVVVV", "uscita", None),
    ("PRELIEVO CONTANTI SPORTELLO", "entrata", None),
    ("BONIFICO A FAVORE DI TIZIO", "uscita", None),
    ("PRELIEVO ASSEGNO - DM 00000", "uscita", None),
]


@pytest.mark.parametrize("descrizione,verso,atteso", CASI,
                         ids=[f"{c[0][:22]}-{c[1]}" for c in CASI])
def test_riconoscimento(descrizione, verso, atteso):
    assert classifica({"descrizione_originale": descrizione, "tipo": verso}) == atteso


# ── le due gambe ───────────────────────────────────────────────────────────

def test_un_versamento_scrive_uscita_cassa_ed_entrata_banca(db):
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI - VVVVV", 5000.0, "entrata")]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    cassa = run(db["prima_nota_cassa"].find({}).to_list(10))
    banca = run(db["prima_nota_banca"].find({}).to_list(10))
    assert len(cassa) == 1 and len(banca) == 1
    assert cassa[0]["tipo"] == "uscita" and banca[0]["tipo"] == "entrata"
    assert cassa[0]["importo"] == banca[0]["importo"] == 5000.0
    assert esito["versamenti"] == 1
    # Ogni gamba ha il suo conto e per contropartita l'altro conto di tesoreria.
    assert banca[0]["conto_contabile"] == "19.01.01"
    assert banca[0]["conto_contropartita"] == "19.03.03"
    assert cassa[0]["conto_contabile"] == "19.03.03"
    assert cassa[0]["conto_contropartita"] == "19.01.01"


def test_un_prelievo_e_il_movimento_opposto(db):
    run(_prepara(db, [_ec("EC2", "PRELIEVO CONTANTI SPORTELLO", 500.0, "uscita")]))

    run(riconosci_versamenti(db, dry_run=False))

    cassa = run(db["prima_nota_cassa"].find({}).to_list(10))
    banca = run(db["prima_nota_banca"].find({}).to_list(10))
    assert cassa[0]["tipo"] == "entrata" and banca[0]["tipo"] == "uscita"


def test_le_due_gambe_sono_collegate_fra_loro(db):
    """CLAUDE.md: due movimenti speculari con `trasferimento_collegato_id`,
    stesso `operation_id` e categoria `trasferimento_interno` — non un flag
    sul singolo movimento."""
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI", 1000.0, "entrata")]))

    run(riconosci_versamenti(db, dry_run=False))

    cassa = run(db["prima_nota_cassa"].find_one({}))
    banca = run(db["prima_nota_banca"].find_one({}))
    assert cassa["operation_id"] == banca["operation_id"] == "versamento:EC1"
    assert cassa["trasferimento_collegato_id"] == banca["id"]
    assert banca["trasferimento_collegato_id"] == cassa["id"]
    assert cassa["categoria"] == banca["categoria"] == "trasferimento_interno"


# ── il difetto che faceva uscire il contante due volte ─────────────────────

def test_la_cassa_gia_registrata_a_mano_si_collega_non_si_duplica(db):
    """Il negozio versa il 9, la banca contabilizza il 10."""
    run(db["prima_nota_cassa"].insert_one({
        "id": "MANUALE", "data": "2026-03-09", "importo": 5000.0, "tipo": "uscita",
        "categoria": "versamento", "descrizione": "Versamento in banca",
    }))
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI - VVVVV", 5000.0, "entrata",
                          data="2026-03-10")]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    cassa = run(db["prima_nota_cassa"].find({}).to_list(10))
    assert len(cassa) == 1, (
        f"Il contante e' uscito due volte dalla cassa: {cassa}"
    )
    assert cassa[0]["id"] == "MANUALE"
    assert cassa[0]["operation_id"] == "versamento:EC1"
    assert esito["gambe_cassa_collegate"] == 1 and esito["gambe_cassa_create"] == 0


def test_fuori_dalla_finestra_di_giorni_non_si_collega(db):
    """Una riga di un mese prima non e' questo versamento."""
    run(db["prima_nota_cassa"].insert_one({
        "id": "VECCHIA", "data": "2026-02-01", "importo": 5000.0, "tipo": "uscita",
        "categoria": "versamento",
    }))
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI", 5000.0, "entrata", data="2026-03-10")]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["gambe_cassa_create"] == 1
    assert run(db["prima_nota_cassa"].find_one({"id": "VECCHIA"})).get("operation_id") is None


def test_un_importo_diverso_non_si_collega(db):
    """L'importo e' parte della prova: deve tornare al centesimo."""
    run(db["prima_nota_cassa"].insert_one({
        "id": "ALTRA", "data": "2026-03-10", "importo": 4999.0, "tipo": "uscita",
        "categoria": "versamento",
    }))
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI", 5000.0, "entrata", data="2026-03-10")]))

    assert run(riconosci_versamenti(db, dry_run=False))["gambe_cassa_create"] == 1


def test_una_riga_di_cassa_chiude_un_solo_versamento(db):
    """Due versamenti uguali lo stesso giorno non possono pescare la stessa riga."""
    run(db["prima_nota_cassa"].insert_one({
        "id": "LEGACY", "data": "2026-03-10", "importo": 5000.0, "tipo": "uscita",
        "categoria": "Versamento Banca",
        "descrizione": "Versamento contanti in banca — Da estratto conto",
    }))
    run(_prepara(db, [
        _ec("EC1", "VERS. CONTANTI", 5000.0, "entrata", data="2026-03-10"),
        _ec("EC2", "VERS. CONTANTI", 5000.0, "entrata", data="2026-03-10"),
    ]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["gambe_cassa_collegate"] == 1
    assert esito["gambe_cassa_create"] == 1
    assert run(db["prima_nota_cassa"].count_documents({})) == 2


# ── idempotenza ────────────────────────────────────────────────────────────

def test_rileggere_lo_stesso_estratto_non_duplica_niente(db):
    """Il criterio di collaudo: il secondo giro non scrive nulla di nuovo."""
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI", 5000.0, "entrata")]))

    run(riconosci_versamenti(db, dry_run=False))
    run(riconosci_versamenti(db, dry_run=False))
    run(riconosci_versamenti(db, dry_run=False))

    assert run(db["prima_nota_cassa"].count_documents({})) == 1
    assert run(db["prima_nota_banca"].count_documents({})) == 1


def test_per_difetto_non_scrive(db):
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI", 5000.0, "entrata")]))

    esito = run(riconosci_versamenti(db))

    assert esito["dry_run"] is True
    assert run(db["prima_nota_cassa"].count_documents({})) == 0


def test_senza_data_o_importo_si_segnala_non_si_indovina(db):
    run(_prepara(db, [{"id": "EC1", "descrizione_originale": "VERS. CONTANTI",
                       "importo": 0, "tipo": "entrata", "data": ""}]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["senza_data_o_importo"] == 1
    assert run(db["prima_nota_cassa"].count_documents({})) == 0


def test_lo_storno_non_crea_movimenti(db):
    run(_prepara(db, [_ec("EC1", "STORNO VERS. CONTANTI", 5000.0, "entrata")]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["esaminati"] == 0
    assert run(db["prima_nota_cassa"].count_documents({})) == 0


# ── gira da solo ───────────────────────────────────────────────────────────

def test_l_orchestratore_lo_chiama_senza_bottoni():
    """Non c'e' piu' niente da premere: sta nel giro dei 30 minuti."""
    import inspect

    from app import scheduler

    sorgente = inspect.getsource(scheduler)
    assert "riconosci_versamenti(db, dry_run=False)" in sorgente
    assert 'id="banca_versamenti_proiezione"' in sorgente
    # Il job parte pochi minuti dopo l'avvio: un deploy dopo l'altro non lo
    # lascia mai a meta' come il giro lungo.
    assert "next_run_time=avvio + timedelta(minutes=2)" in sorgente


def test_il_vecchio_comando_di_riparazione_non_esiste_piu():
    from app.routers.bank import estratto_conto

    assert not hasattr(estratto_conto, "ripara_versamenti_cassa")


# ── la riga esistente deve dichiararsi versamento ──────────────────────────
# Nota del titolare (20/09/2026): «nessun versamento è stato scritto a mano».
# Le 18 righe di cassa che il motore aggancia in produzione vengono
# dall'integrazione legacy del 15/09, non da lui. La prima versione di questo
# modulo le cercava per solo importo e data: bastava un pagamento fornitore in
# contanti dello stesso importo per fargli sovrascrivere la categoria.

def test_un_pagamento_fornitore_in_contanti_non_diventa_un_versamento(db):
    run(db["prima_nota_cassa"].insert_one({
        "id": "FORNITORE", "data": "2026-03-10", "importo": 5000.0, "tipo": "uscita",
        "categoria": "Fatture", "descrizione": "Pagamento fattura 12/2026 Me.Pa. Srl",
        "fornitore": "ME.PA. SRL",
    }))
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI", 5000.0, "entrata", data="2026-03-10")]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["gambe_cassa_collegate"] == 0
    assert esito["gambe_cassa_create"] == 1
    fornitore = run(db["prima_nota_cassa"].find_one({"id": "FORNITORE"}))
    assert fornitore["categoria"] == "Fatture"
    assert not fornitore.get("trasferimento_collegato_id")
    assert not fornitore.get("operation_id")


def test_la_riga_legacy_dell_archivio_viene_agganciata(db):
    """Le 18 vere: «Versamento contanti in banca — Da estratto conto»."""
    run(db["prima_nota_cassa"].insert_one({
        "id": "LEGACY", "data": "2026-01-12", "importo": 3510.0, "tipo": "uscita",
        "source": "legacy_versamenti",
        "descrizione": "Versamento contanti in banca — Da estratto conto",
    }))
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI", 3510.0, "entrata", data="2026-01-12")]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["gambe_cassa_collegate"] == 1
    assert esito["gambe_cassa_create"] == 0
    assert run(db["prima_nota_cassa"].count_documents({})) == 1


def test_chi_non_dichiara_niente_non_viene_agganciato(db):
    """Categoria vuota e descrizione muta: si crea la gamba, non si ruba."""
    run(db["prima_nota_cassa"].insert_one({
        "id": "MUTA", "data": "2026-03-10", "importo": 5000.0, "tipo": "uscita",
    }))
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI", 5000.0, "entrata", data="2026-03-10")]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["gambe_cassa_collegate"] == 0
    assert esito["gambe_cassa_create"] == 1


# ── lo stesso versamento arriva da piu' export ─────────────────────────────
# Produzione, 26/09/2026: ogni versamento era in archivio due o tre volte
# (vecchio archivio, CSV della banca, lettura diretta Enable Banking) e il
# motore scriveva una coppia per copia: 44 uscite di cassa per 27 versamenti,
# 80 entrate in banca. Il contante risultava uscito due volte.

def _copie(data, importo, fonti):
    righe = []
    for n, fonte in enumerate(fonti):
        righe.append({"id": f"{fonte}-{data}-{importo}-{n}", "descrizione_originale": "VERS. CONTANTI - VVVVV",
                      "importo": importo, "tipo": "entrata", "data": data,
                      "source_filename" if fonte.endswith(".csv") else "fonte": fonte})
    return righe


def _attive(db, collezione):
    return run(db[collezione].find({"status": {"$nin": ["deleted", "archived"]}}).to_list(100))


def test_tre_copie_dello_stesso_versamento_sono_un_versamento(db):
    run(_prepara(db, _copie("2026-09-18", 2760.0, ["legacy_staging_2026", "export.csv", "enable_banking"])))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["versamenti"] == 1 and esito["copie_estratto_conto"] == 2
    assert len(_attive(db, "prima_nota_cassa")) == 1
    assert len(_attive(db, "prima_nota_banca")) == 1
    secondo = run(riconosci_versamenti(db, dry_run=False))
    assert secondo["gia_registrati"] == 1
    assert secondo["gambe_cassa_create"] == secondo["gambe_banca_create"] == 0


def test_la_copia_arrivata_dopo_non_scrive_un_secondo_versamento(db):
    """Enable Banking lo porta subito, il CSV ufficiale settimane dopo."""
    run(_prepara(db, _copie("2026-09-23", 4000.0, ["enable_banking"])))
    run(riconosci_versamenti(db, dry_run=False))
    run(_prepara(db, _copie("2026-09-23", 4000.0, ["export.csv"])))

    run(riconosci_versamenti(db, dry_run=False))

    assert len(_attive(db, "prima_nota_cassa")) == 1
    assert len(_attive(db, "prima_nota_banca")) == 1


def test_due_versamenti_uguali_lo_stesso_giorno_restano_due(db):
    """23/03/2026: due versamenti da 5.000 €, in ognuna delle due fonti."""
    run(_prepara(db, _copie("2026-03-23", 5000.0, ["legacy_staging_2026", "legacy_staging_2026",
                                                   "export.csv", "export.csv"])))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["versamenti"] == 2
    assert len(_attive(db, "prima_nota_cassa")) == 2
    assert len(_attive(db, "prima_nota_banca")) == 2


def test_i_doppioni_gia_scritti_dai_motori_si_tolgono(db):
    run(_prepara(db, _copie("2026-01-12", 3510.0, ["legacy_staging_2026", "export.csv"])))
    run(db["prima_nota_banca"].insert_many([
        {"id": "B-LEGACY", "data": "2026-01-12", "importo": 3510.0, "tipo": "entrata",
         "categoria": "Versamento Banca", "source": "legacy_versamenti"},
        {"id": "B-RIC", "data": "2026-01-12", "importo": 3510.0, "tipo": "entrata",
         "categoria": "Versamento Banca", "source": "riconciliazione_ec_versamento"},
        {"id": "B-EC1", "data": "2026-01-12", "importo": 3510.0, "tipo": "entrata",
         "categoria": "trasferimento_interno", "source": "estratto_conto_versamento",
         "operation_id": "versamento:x1", "trasferimento_collegato_id": "C-LEGACY"},
        {"id": "B-EC2", "data": "2026-01-12", "importo": 3510.0, "tipo": "entrata",
         "categoria": "trasferimento_interno", "source": "estratto_conto_versamento",
         "operation_id": "versamento:x2", "trasferimento_collegato_id": "C-EC2"},
    ]))
    run(db["prima_nota_cassa"].insert_many([
        {"id": "C-LEGACY", "data": "2026-01-12", "importo": 3510.0, "tipo": "uscita",
         "categoria": "trasferimento_interno", "source": "legacy_versamenti",
         "operation_id": "versamento:x1", "trasferimento_collegato_id": "B-EC1"},
        {"id": "C-EC2", "data": "2026-01-12", "importo": 3510.0, "tipo": "uscita",
         "categoria": "trasferimento_interno", "source": "estratto_conto_versamento",
         "operation_id": "versamento:x2", "trasferimento_collegato_id": "B-EC2"},
    ]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    banca = _attive(db, "prima_nota_banca")
    cassa = _attive(db, "prima_nota_cassa")
    assert [b["id"] for b in banca] == ["B-EC1"]
    assert [c["id"] for c in cassa] == ["C-LEGACY"]
    assert esito["doppioni_banca_tolti"] == 3 and esito["doppioni_cassa_tolti"] == 1
    tolta = run(db["prima_nota_banca"].find_one({"id": "B-RIC"}))
    assert tolta["status"] == "deleted" and tolta["deleted_reason"] == "doppione_versamento_contanti"


def test_una_riga_scritta_a_mano_in_piu_non_si_tocca(db):
    run(_prepara(db, _copie("2026-03-10", 1000.0, ["export.csv"])))
    run(db["prima_nota_banca"].insert_many([
        {"id": "MANO-1", "data": "2026-03-10", "importo": 1000.0, "tipo": "entrata",
         "categoria": "Versamento Banca", "source": "manuale"},
        {"id": "MANO-2", "data": "2026-03-10", "importo": 1000.0, "tipo": "entrata",
         "categoria": "Versamento Banca", "source": "manuale"},
    ]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert len(_attive(db, "prima_nota_banca")) == 2
    assert esito["da_verificare"] == 1 and esito["doppioni_banca_tolti"] == 0


def test_l_attesa_bancaria_della_cassa_manuale_si_chiude_non_si_duplica(db):
    """Cassa scritta a mano il 9 con la sua gamba bancaria in attesa; la banca il 10."""
    run(db["prima_nota_cassa"].insert_one({
        "id": "C-MANO", "data": "2026-03-09", "importo": 800.0, "tipo": "uscita",
        "categoria": "Versamento Banca", "trasferimento_collegato_id": "B-ATTESA"}))
    run(db["prima_nota_banca"].insert_one({
        "id": "B-ATTESA", "data": "2026-03-09", "importo": 800.0, "tipo": "entrata",
        "categoria": "Versamento Banca", "source": "versamento_cassa_in_attesa",
        "trasferimento_collegato_id": "C-MANO", "provvisorio": True}))
    run(_prepara(db, _copie("2026-03-10", 800.0, ["enable_banking"])))

    run(riconosci_versamenti(db, dry_run=False))

    assert [c["id"] for c in _attive(db, "prima_nota_cassa")] == ["C-MANO"]
    banca = _attive(db, "prima_nota_banca")
    assert [b["id"] for b in banca] == ["B-ATTESA"]
    assert banca[0]["data"] == "2026-03-10" and banca[0]["provvisorio"] is False


def test_la_simulazione_non_toglie_niente(db):
    run(_prepara(db, _copie("2026-01-12", 3510.0, ["export.csv"])))
    run(db["prima_nota_banca"].insert_many([
        {"id": f"B{i}", "data": "2026-01-12", "importo": 3510.0, "tipo": "entrata",
         "categoria": "Versamento Banca", "source": "legacy_versamenti"} for i in range(3)
    ]))

    esito = run(riconosci_versamenti(db))

    assert esito["doppioni_banca_tolti"] == 2
    assert len(_attive(db, "prima_nota_banca")) == 3


def test_il_versamento_annullato_dal_titolare_non_ha_gambe(db):
    """10/07/2026: versamento di un altro cliente accreditato per errore e
    stornato dalla banca il 13/07. Il contante non e' mai uscito dalla cassa."""
    run(_prepara(db, _copie("2026-07-10", 3100.0, ["legacy_staging_2026"])
                 + _copie("2026-07-10", 4600.0, ["legacy_staging_2026"])))
    run(db["prima_nota_banca"].insert_one({
        "id": "B-3100", "data": "2026-07-10", "importo": 3100.0, "tipo": "entrata",
        "categoria": "trasferimento_interno", "source": "estratto_conto_versamento",
        "operation_id": "versamento:v", "trasferimento_collegato_id": "C-3100"}))
    run(db["prima_nota_cassa"].insert_one({
        "id": "C-3100", "data": "2026-07-10", "importo": 3100.0, "tipo": "uscita",
        "categoria": "trasferimento_interno", "source": "estratto_conto_versamento",
        "operation_id": "versamento:v", "trasferimento_collegato_id": "B-3100"}))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["annullati_dal_titolare"] == 1 and esito["versamenti"] == 1
    assert [c["importo"] for c in _attive(db, "prima_nota_cassa")] == [4600.0]
    assert [b["importo"] for b in _attive(db, "prima_nota_banca")] == [4600.0]
    tolta = run(db["prima_nota_cassa"].find_one({"id": "C-3100"}))
    assert tolta["deleted_reason"] == "versamento_non_nostro_stornato_dalla_banca"
    assert run(riconosci_versamenti(db, dry_run=False))["gambe_cassa_create"] == 0
