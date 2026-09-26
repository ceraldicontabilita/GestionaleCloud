"""Estratto della carta Mastercard SumUp: lettura per posizione, saldi, import.

Il PDF di prova è sintetico e con dati finti: riproduce la tabella ruotata di
SumUp (ogni colonna è una fascia di «y», ogni riga una fascia di «x»), senza
portare nel repository i dati bancari veri.
"""
import asyncio
from decimal import Decimal

import fitz
import pytest

from app.parsers.estratto_conto_sumup_parser import (
    EstrattoSumUpNonValido,
    leggi_estratto_sumup,
)
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.classificazione_estratti import SUMUP, classifica, route_da_testo
from app.services.sumup_conto import COLL_MOVIMENTI, importa_estratto_sumup

# Bordo alto di ogni colonna, come nel PDF di SumUp.
_COLONNE = (
    ("Data", 799), ("Codice", 731), ("Tipo", 642), ("Riferimento", 524),
    ("Causale", 406), ("Stato", 347), ("Importo", 259), ("Importo", 199),
    ("Commis", 140), ("Saldo", 96),
)

# Dalla più recente alla più vecchia, come le stampa SumUp:
# data, ora, codice, tipo, riferimento, causale, uscita, entrata, commissione, saldo
_RIGHE = (
    ("05/08/26,", "09:10", "C9AAAAAAA3", "Pagamento POS", "FORNITORE SRL NAPOLI", "",
     "10.50", "0.00", "0.00", "49.50"),
    ("04/08/26,", "08:00", "C9AAAAAAA2", "Bonifico bancario in uscita",
     "MARIO ROSSI IT60X054281110 1000000123456", "Stipendio",
     "40.00", "0.00", "0.00", "60.00"),
    ("03/08/26,", "07:30", "C9AAAAAAA1", "Pagamento da SumUp", "SUMUP PID111", "",
     "0.00", "100.00", "0.00", "100.00"),
)


def _scrivi(pagina, x, y, testo):
    pagina.insert_text((x, y), testo, fontsize=6, rotate=90)


def pdf_sumup(righe=_RIGHE, saldo_finale="49.50", uscite="50.50") -> bytes:
    documento = fitz.open()
    pagina = documento.new_page(width=595, height=842)
    riepilogo = (
        "Estratto conto SumUp", "Codice IBAN: IE00SUMU00000000000000",
        "Seleziona il periodo di tempo: 03/08/26 - 05/08/26",
        "Saldo iniziale: 0.00", "Pagamenti in entrata: 100.00",
        f"Pagamenti in uscita: {uscite}", f"Saldo finale: {saldo_finale}",
    )
    for indice, riga in enumerate(riepilogo):
        _scrivi(pagina, 40 + indice * 10, 799, riga)
    for etichetta, alto in _COLONNE:
        _scrivi(pagina, 260, alto, etichetta)
    for indice, riga in enumerate(righe):
        x = 290 + indice * 30
        data, ora, codice, tipo, rif, causale, uscita, entrata, comm, saldo = riga
        _scrivi(pagina, x, 799, data)
        _scrivi(pagina, x + 8, 799, ora)
        for testo, (_, alto) in zip(
            (codice, tipo, rif, causale, "Approvato", uscita, entrata, comm, saldo),
            _COLONNE[1:],
        ):
            if testo:
                _scrivi(pagina, x, alto, testo)
    _scrivi(pagina, 560, 799, "Istituto di moneta elettronica")
    return documento.tobytes()


def test_legge_righe_e_catena_dei_saldi():
    estratto = leggi_estratto_sumup(pdf_sumup())
    assert [r.codice for r in estratto.righe] == ["C9AAAAAAA3", "C9AAAAAAA2", "C9AAAAAAA1"]
    bonifico = estratto.righe[1]
    assert bonifico.data == "2026-08-04"
    assert bonifico.tipo_transazione == "Bonifico bancario in uscita"
    assert bonifico.causale == "Stipendio"
    assert bonifico.importo_netto == Decimal("-40.00")
    assert estratto.righe[2].pid == "PID111"
    assert estratto.saldo_finale == Decimal("49.50")
    assert (estratto.periodo_dal, estratto.periodo_al) == ("2026-08-03", "2026-08-05")


def test_saldo_che_non_torna_non_si_importa():
    righe = list(_RIGHE)
    righe[1] = righe[1][:6] + ("41.00",) + righe[1][7:]   # uscita letta male
    with pytest.raises(EstrattoSumUpNonValido, match="saldo non torna"):
        leggi_estratto_sumup(pdf_sumup(righe=tuple(righe), uscite="51.50"))


def test_totali_del_riepilogo_diversi_non_si_importa():
    with pytest.raises(EstrattoSumUpNonValido, match="Totali"):
        leggi_estratto_sumup(pdf_sumup(uscite="60.00"))


def test_riconosciuto_come_sumup_e_non_come_banca():
    assert route_da_testo("Estratto conto SumUp\nData contabile Data valuta") == SUMUP
    assert classifica("Resoconto transazioni.pdf", pdf_sumup())[0] == SUMUP


def test_import_idempotente_e_payout_citato():
    db = ClientArchivioMemoria()["sumup_conto_test"]

    async def scenario():
        await db["sumup_payouts"].insert_one({"payout_id": "SUMUP PID111"})
        pdf = pdf_sumup()
        primo = await importa_estratto_sumup(db, "sumup.pdf", pdf)
        secondo = await importa_estratto_sumup(db, "sumup.pdf", pdf)
        estratti = await db["sumup_conto_estratti"].count_documents({})
        movimenti = await db[COLL_MOVIMENTI].find({}, {"_id": 0}).to_list(None)
        return primo, secondo, movimenti, estratti

    primo, secondo, movimenti, estratti = asyncio.run(scenario())
    assert estratti == 1
    assert primo["nuovi"] == 3 and primo["payout_collegati"] == 1
    assert secondo["nuovi"] == 0 and secondo["duplicate"] is True
    assert len(movimenti) == 3
    per_codice = {m["codice_transazione"]: m for m in movimenti}
    assert per_codice["C9AAAAAAA1"]["payout_id"] == "SUMUP PID111"
    bonifico = per_codice["C9AAAAAAA2"]
    assert bonifico["conto_contabile"] == "19.01.05"
    assert bonifico["importo"] == "-40.00" and bonifico["segno"] == "uscita"
    assert bonifico["iban_beneficiario"] == "IT60X0542811101000000123456"
