"""Resoconto CSV del conto SumUp (19.01.05): stesso motore del PDF, giroconti.

Righe nello stesso formato del file che il titolare scarica da SumUp: data e
ora separate da una virgola libera, una riga intera fra virgolette perche' la
causale contiene virgole. Dati finti, catena dei saldi coerente.
"""
import asyncio

import pytest

from app.parsers.estratto_conto_sumup_parser import (
    EstrattoSumUpNonValido,
    leggi_resoconto_sumup_csv,
)
from app.routers.documenti import detect_document_type
from app.routers.prima_nota_module.banca import _movimenti_conto_sumup
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.sumup_conto import COLL_MOVIMENTI, importa_estratto_sumup

NOME = "Resoconto_transazioni_PROVA_2026-09-27.csv"
INTESTAZIONE = (
    "Data transazione,Codice transazione,Tipo transazione,Riferimento,Causale pagamento,"
    "Stato,Importo di fatturazione in uscita,Importo di fatturazione in entrata,"
    "Valuta della carta,Importo transazione in uscita,Importo transazione in entrata,"
    "Valuta della transazione,Tasso di cambio,Commissione,Saldo disponibile"
)
# Dalla piu' recente alla piu' vecchia, come le scrive SumUp.
RIGHE = [
    "25/09/26, 11:42,COB6KBP5W2,Bonifico bancario in uscita,"
    "Fornitore Prova Srl IT60X0542811101000000123456,fattura 11358,Approvato,"
    "893.73,0.00,EUR,893.73,0.00,EUR,1.00,0.00,645.11",
    '"22/09/26, 18:09,COJQMJZZMJ,Bonifico bancario in uscita,'
    'Ascensori Prova Srl IT60X0542811101000000654321,""Pagamento Fatture 386, 738, 1436"",'
    'Approvato,461.16,0.00,EUR,461.16,0.00,EUR,1.00,0.00,1538.84"',
    "20/09/26, 10:00,CRIFIUTAT1,Pagamento online,NEGOZIO PROVA,,Rifiutato,"
    "50.00,0.00,EUR,50.00,0.00,EUR,1.00,0.00,2000.00",
    "15/09/26, 15:11,CGIRO10000,Bonifico bancario in uscita,"
    "Ceraldi Group srl IT60X0542811101000000999999,Giroconto,Approvato,"
    "10000.00,0.00,EUR,10000.00,0.00,EUR,1.00,0.00,2000.00",
    "14/09/26, 07:30,CPAYOUT111,Pagamento da SumUp,SUMUP PID111,,Pagamento in entrata,"
    "0.00,12000.00,EUR,0.00,12000.00,EUR,1.00,0.00,12000.00",
]


def _csv(righe=RIGHE):
    return ("\n".join([INTESTAZIONE, *righe]) + "\n").encode("utf-8")


def _run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture
def db():
    return ClientArchivioMemoria()["estratto_sumup_csv_test"]


def _payout(db):
    _run(db["sumup_payouts"].insert_one({"payout_id": "SUMUP PID111"}))


def _entrata_bpm(db, giorno="2026-09-15"):
    _run(db["estratto_conto_movimenti"].insert_one({
        "id": "ec-bpm-giro", "data": giorno, "tipo": "entrata", "importo": 10000.0,
        "descrizione": "BONIF. VS. FAVORE - BON.DA ceraldi group srl - Giroconto",
        "riconciliato": False,
    }))


def test_il_csv_regge_data_spezzata_righe_fra_virgolette_e_scarta_i_rifiutati():
    estratto = leggi_resoconto_sumup_csv(_csv())
    assert [r.codice for r in estratto.righe] == [
        "COB6KBP5W2", "COJQMJZZMJ", "CGIRO10000", "CPAYOUT111",
    ]
    assert estratto.righe[1].causale == "Pagamento Fatture 386, 738, 1436"
    assert estratto.righe[0].ora == "11:42"
    assert estratto.righe[3].pid == "PID111"
    assert str(estratto.saldo_iniziale) == "0.00"
    assert str(estratto.saldo_finale) == "645.11"


def test_un_saldo_che_non_torna_non_si_importa():
    rotte = [RIGHE[0].replace("645.11", "645.12"), *RIGHE[1:]]
    with pytest.raises(EstrattoSumUpNonValido):
        leggi_resoconto_sumup_csv(_csv(rotte))


def test_il_csv_va_al_motore_sumup_non_al_conto_bpm():
    assert detect_document_type(NOME, _csv()) == "estratto_conto_sumup"


def test_import_payout_giroconto_e_reimport_idempotente(db):
    _payout(db)
    _entrata_bpm(db)
    primo = _run(importa_estratto_sumup(db, NOME, _csv()))
    assert primo["nuovi"] == 4
    assert primo["payout_collegati"] == 1

    gambe = _run(db["prima_nota_banca"].find({"source": "giroconto_sumup"}).to_list(None))
    per_conto = {g["conto_contabile"]: g for g in gambe}
    assert set(per_conto) == {"19.01.05", "19.01.01"}
    assert per_conto["19.01.05"]["tipo"] == "uscita"
    assert per_conto["19.01.01"]["tipo"] == "entrata"
    assert per_conto["19.01.05"]["trasferimento_collegato_id"] == per_conto["19.01.01"]["id"]
    assert per_conto["19.01.01"]["trasferimento_collegato_id"] == per_conto["19.01.05"]["id"]
    assert per_conto["19.01.01"]["estratto_conto_id"] == "ec-bpm-giro"
    assert {g["operation_id"] for g in gambe} == {"giroconto-sumup:CGIRO10000"}
    assert all(g["categoria"] == "trasferimento_interno" for g in gambe)
    # I bonifici ai fornitori non diventano spese senza documento.
    assert _run(db["prima_nota_banca"].count_documents({})) == 2

    secondo = _run(importa_estratto_sumup(db, NOME, _csv()))
    assert secondo["nuovi"] == 0 and secondo["duplicate"]
    assert _run(db["prima_nota_banca"].count_documents({"source": "giroconto_sumup"})) == 2
    assert _run(db[COLL_MOVIMENTI].count_documents({})) == 4


def test_l_accredito_bpm_arrivato_dopo_si_aggancia_al_giro_successivo(db):
    _run(importa_estratto_sumup(db, NOME, _csv()))
    bpm = _run(db["prima_nota_banca"].find_one({"source": "giroconto_sumup", "conto_contabile": "19.01.01"}))
    assert bpm["in_attesa_estratto_ufficiale"] is True and not bpm.get("estratto_conto_id")

    _entrata_bpm(db, giorno="2026-09-16")
    _run(importa_estratto_sumup(db, NOME, _csv()))
    bpm = _run(db["prima_nota_banca"].find_one({"id": bpm["id"]}))
    assert bpm["estratto_conto_id"] == "ec-bpm-giro"
    assert bpm["in_attesa_estratto_ufficiale"] is False
    assert _run(db["prima_nota_banca"].count_documents({"source": "giroconto_sumup"})) == 2


def test_la_vista_mostra_ogni_movimento_del_giorno_con_il_suo_stato(db):
    _payout(db)
    _entrata_bpm(db)
    _run(importa_estratto_sumup(db, NOME, _csv()))
    movimenti = _run(_movimenti_conto_sumup(db, "2026-01-01", "2026-12-31"))
    assert [(m["data"], m["importo"], m["stato"]) for m in movimenti] == [
        ("2026-09-25", -893.73, "Da registrare"),
        ("2026-09-22", -461.16, "Da registrare"),
        ("2026-09-15", -10000.0, "Giroconto verso BPM"),
        ("2026-09-14", 12000.0, "Payout agganciato"),
    ]
    assert movimenti[0]["controparte"] == "Fornitore Prova Srl"
    assert movimenti[0]["saldo_disponibile"] == 645.11
