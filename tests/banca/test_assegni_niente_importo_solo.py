"""Assegni: nessun abbinamento per solo importo, nessuna cancellazione per filtro.

Fino al 28/09/2026 convivevano cinque motori di associazione. Due sceglievano
la fattura per importo: «Smart» (``learning/associa-intelligente``, 5 EUR di
tolleranza, anche su fatture gia' pagate) e ``auto-associa`` (0,50 EUR piu'
la somiglianza del nome); ``learning/suggerimenti`` proponeva a 10 EUR. La
«Pulizia» cancellava con ``delete_one`` gli assegni con lo stesso numero, e
«Svuota» cancellava per filtro: con ``stato=incassato`` avrebbe tolto tutti i
99 assegni di produzione, tutti incassati.

Restano il motore per identita' e importo al centesimo
(``assegni_fattura_intent``, ``assegni_auto_match``) e i doppioni in
quarantena reversibile (``assegni_doppioni.unifica``, nel giro dell'estratto
conto).
"""
import asyncio
import re
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.router_registry import register_all_routers
from tests.route_table import elenco_route

ROOT = Path(__file__).resolve().parents[2]

TOLTI = [
    ("/api/assegni/learning/associa-intelligente", "POST"),
    ("/api/assegni/learning/associa-combinazioni-avanzato", "POST"),
    ("/api/assegni/learning/suggerimenti/{importo}", "GET"),
    ("/api/assegni/learning/pulizia-duplicati", "POST"),
    ("/api/assegni/auto-associa", "POST"),
    ("/api/assegni/preview-combinazioni", "GET"),
    ("/api/assegni/correggi-associazione/{assegno_id}", "PUT"),
    ("/api/assegni/proposte-associazione", "GET"),
    ("/api/assegni/conferma-proposta/{proposta_id}", "POST"),
    ("/api/assegni/rifiuta-proposta/{proposta_id}", "POST"),
    ("/api/assegni/pulisci-beneficiari-fittizi", "POST"),
    ("/api/assegni/correggi-numeri", "POST"),
]


@pytest.fixture(scope="module")
def rotte():
    app = FastAPI()
    register_all_routers(app)
    return {(r.path, m) for r in elenco_route(app) for m in r.methods}


@pytest.mark.parametrize("percorso, metodo", TOLTI)
def test_gli_abbinamenti_per_importo_e_le_cancellazioni_non_tornano(rotte, percorso, metodo):
    assert (percorso, metodo) not in rotte


def test_il_modulo_assegni_non_cancella_per_filtro():
    for nome in ("app/routers/bank/assegni.py", "app/routers/bank/assegni_learning.py"):
        sorgente = (ROOT / nome).read_text(encoding="utf-8")
        assert "delete_many(" not in sorgente, nome
        for chiamata in re.findall(r"delete_one\(([^)]*)\)", sorgente):
            assert chiamata.strip().startswith('{"id":'), f"{nome}: delete_one({chiamata})"


def test_le_fatture_proponibili_usano_i_criteri_unici():
    sorgente = (ROOT / "app/routers/bank/assegni.py").read_text(encoding="utf-8")
    corpo = sorgente.split("async def fatture_disponibili_per_assegno(", 1)[1].split("\n@router", 1)[0]
    assert "FILTRO_FATTURA_ATTIVA" in corpo and "FILTRO_NON_PAGATE" in corpo
    assert '"pagato": {"$ne": True}' not in corpo


def test_svuota_toglie_solo_moduli_davvero_vuoti(monkeypatch):
    from app.routers.bank import assegni as assegni_router
    from app.services.archivio_documenti_memoria import ArchivioDocumenti

    db = ArchivioDocumenti()
    monkeypatch.setattr(assegni_router.Database, "get_db", staticmethod(lambda: db))

    async def scenario():
        await db["assegni"].insert_many([
            {"id": "v1", "numero": "0208770650", "stato": "vuoto"},
            {"id": "v2", "numero": "0208770651", "stato": "vuoto", "movimento_id": "m9"},
            {"id": "i1", "numero": "0208770652", "stato": "incassato", "importo": 300.0},
        ])
        esito = await assegni_router.clear_generated_assegni(stato="vuoto")
        restano = {d["id"] for d in await db["assegni"].find({}, {"_id": 0}).to_list(None)}
        return esito, restano

    esito, restano = asyncio.run(scenario())
    assert esito["deleted_count"] == 1
    assert restano == {"v2", "i1"}


def test_incassa_rifiuta_un_movimento_di_importo_diverso(monkeypatch):
    from fastapi import HTTPException

    from app.routers.bank import assegni as assegni_router
    from app.services.archivio_documenti_memoria import ArchivioDocumenti

    db = ArchivioDocumenti()
    monkeypatch.setattr(assegni_router.Database, "get_db", staticmethod(lambda: db))

    async def scenario():
        await db["assegni"].insert_one({"id": "a1", "numero": "0208770650", "stato": "emesso", "importo": 300.0})
        await db["estratto_conto_movimenti"].insert_one({"id": "m1", "data": "2026-09-01", "importo": -300.5})
        with pytest.raises(HTTPException) as errore:
            await assegni_router.incassa_assegno("a1", data_incasso=None, movimento_estratto_conto_id="m1")
        return errore.value, await db["assegni"].find_one({"id": "a1"}, {"_id": 0})

    errore, assegno = asyncio.run(scenario())
    assert errore.status_code == 409 and errore.detail["code"] == "IMPORTO_DIVERSO"
    assert assegno["stato"] == "emesso"


def test_arricchisci_pagamenti_non_crea_assegni():
    sorgente = (ROOT / "app/routers/prima_nota_module/manutenzione.py").read_text(encoding="utf-8")
    corpo = sorgente.split("async def arricchisci_pagamenti_banca(", 1)[1].split("\nasync def ", 1)[0]
    assert 'db["assegni"]' not in corpo


def test_gli_stati_vivono_in_un_registro_solo():
    """Nessun modulo tiene la sua lista di stati: il controllo di eliminazione
    conosceva solo emesso/incassato e lasciava cancellare un assegno stornato."""
    from app.constants import stati_assegno as registro
    from app.routers.bank import assegni as assegni_router

    assert assegni_router.ASSEGNO_STATI is registro.ASSEGNO_STATI
    assert registro.STATI_NUMERO_CONSUMATO | registro.STATI_DISPONIBILI == set(registro.ASSEGNO_STATI)
    for nome in ("app/routers/bank/assegni.py", "app/services/business_rules.py", "app/routers/commercialista.py"):
        sorgente = (ROOT / nome).read_text(encoding="utf-8")
        assert "ASSEGNO_STATI = {" not in sorgente, nome
        assert '["vuoto", "compilato"]' not in sorgente, nome
        assert '["emesso", "incassato"]' not in sorgente, nome


@pytest.mark.parametrize("stato", ["emesso", "assegnato", "parzialmente_assegnato", "incassato",
                                   "annullato", "stornato", "scaduto"])
def test_un_numero_uscito_dal_carnet_non_si_elimina(stato):
    from app.services.business_rules import BusinessRules

    assert not BusinessRules.can_delete_assegno({"stato": stato}).is_valid


@pytest.mark.parametrize("stato", ["vuoto", "compilato"])
def test_un_numero_ancora_nel_carnet_si_elimina(stato):
    from app.services.business_rules import BusinessRules

    assert BusinessRules.can_delete_assegno({"stato": stato}).is_valid


def test_l_avvio_non_riporta_gli_assegni_a_vuoto():
    """La vecchia migrazione d'avvio riportava a «vuoto», per filtro, gli assegni
    col beneficiario «Pag. fatt. …»: un numero emesso tornava disponibile."""
    sorgente = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert 'db["assegni"].update_many' not in sorgente
