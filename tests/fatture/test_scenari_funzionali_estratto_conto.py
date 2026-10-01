"""Collaudo funzionale 7 e 8: estratto conto (doppioni fra export, riga senza segno) e categorie delle causali.

Si importa dall'endpoint vero (CSV dell'export operativo, PDF dell'estratto ufficiale): una riga per movimento
qualunque sia la fonte, la Prima Nota resta agganciata, un export senza segno non scrive niente; le causali
non ambigue danno la categoria giusta, quelle ambigue nessuna, e i giroconti non diventano mai un fornitore
ne' pagano una fattura.
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from tests.fatture._scenari_comuni import (
    FileCsv, FilePdf, archivio_scenari, crea_fornitore, esegui, fattura, importa, importa_estratto, parser_pdf_con,
    riga_csv, transazione_pdf, tutti, xml_fattura,
)

__all__ = ["archivio_scenari"]

DESC_CSV = "VOSTRA DISPOSIZIONE - VS.DISP. RIF. MBVT12345678/001 FAVORE FORNITORE TEST SRL FATT. 123"
# l'estratto ufficiale scrive la stessa operazione con altre parole (senza il prefisso dell'export)
DESC_PDF = "VS.DISP. RIF. MBVT12345678/001 FAVORE FORNITORE TEST SRL FATT. 123 SALDO"


def _d(valore) -> Decimal:
    return Decimal(str(valore))


# ── 7. stesso movimento da due export ────────────────────────────────────────

@pytest.mark.parametrize("csv_prima", [True, False], ids=["csv_poi_pdf", "pdf_poi_csv"])
def test_stesso_movimento_da_csv_e_da_pdf_e_una_riga_sola_con_la_prima_nota_agganciata(archivio_scenari, monkeypatch,
                                                                                    csv_prima):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, xml_fattura(), "drive")
        parser_pdf_con(monkeypatch, [transazione_pdf("2026-09-15", DESC_PDF, -122.0)])
        passi = [lambda: importa_estratto(FileCsv([riga_csv(DESC_CSV, "-122,00")])),
                 lambda: importa_estratto(FilePdf())]
        if not csv_prima:
            passi.reverse()
        esiti = [await passo() for passo in passi]
        ripetuti = [await passo() for passo in passi]
        return {"fid": esito["id"], "esiti": esiti, "ripetuti": ripetuti, "ec": await tutti(db, "estratto_conto_movimenti"),
                "banca": await tutti(db, "prima_nota_banca"), "fattura": await fattura(db, esito["id"])}

    r = esegui(scenario())
    from tests.fatture._scenari_comuni import e_pagata_su_ogni_campo

    # il secondo export non crea una riga: la stessa operazione e' una sola
    assert r["esiti"][1]["stats"]["nuovi"] == 0
    assert len(r["ec"]) == 1
    # il PDF ufficiale vince sull'export operativo, qualunque sia l'ordine
    assert r["ec"][0]["evidenza_bancaria_ufficiale"] is True and r["ec"][0]["livello_evidenza"] == "ufficiale"
    # rimportare gli stessi file non scrive niente di nuovo
    assert all(e["stats"]["nuovi"] == 0 for e in r["ripetuti"])
    # Prima Nota riagganciata: ogni riga che cita un estratto cita la riga rimasta, e la fattura e' pagata una volta
    ec_id = r["ec"][0]["id"]
    citate = {b["estratto_conto_id"] for b in r["banca"] if b.get("estratto_conto_id")}
    assert citate == {ec_id}
    contano = [b for b in r["banca"] if b.get("estratto_conto_id") == ec_id and b.get("status") != "deleted"]
    assert len(contano) == 1 and _d(contano[0]["importo"]) == Decimal("122.00")
    assert e_pagata_su_ogni_campo(r["fattura"])


def test_due_movimenti_uguali_nello_stesso_export_restano_due_e_il_reimport_non_li_moltiplica(archivio_scenari):
    db = archivio_scenari

    async def scenario():
        file = lambda: FileCsv([riga_csv("COMMISSIONI - COMM.SU BONIFICI", "-1,10"),  # noqa: E731
                                riga_csv("COMMISSIONI - COMM.SU BONIFICI", "-1,10")])
        primo = await importa_estratto(file())
        secondo = await importa_estratto(file())
        return primo, secondo, await tutti(db, "estratto_conto_movimenti")

    primo, secondo, ec = esegui(scenario())
    assert primo["stats"]["nuovi"] == 2 and secondo["stats"]["nuovi"] == 0
    assert len(ec) == 2


def _righe_tutte_positive():
    return [riga_csv("PRELIEVO ASSEGNO - NUM: 02087693%02d" % g, "1496,96", f"{g:02d}/06/2026") for g in range(1, 8)] + \
           [riga_csv("ADDEBITO DIRETTO SDD - SDD CORE: FASTWEB", "30,50", f"{g:02d}/06/2026") for g in range(8, 13)]


def test_un_export_senza_segno_e_rifiutato_e_non_scrive_niente(archivio_scenari):
    db = archivio_scenari

    async def scenario():
        errore = None
        try:
            await importa_estratto(FileCsv(_righe_tutte_positive()))
        except HTTPException as exc:
            errore = exc
        return errore, await tutti(db, "estratto_conto_movimenti"), await tutti(db, "prima_nota_banca"), \
            await tutti(db, "prima_nota_cassa")

    errore, ec, banca, cassa = esegui(scenario())
    assert errore is not None and errore.status_code == 422 and "senza segno" in errore.detail
    assert ec == [] and banca == [] and cassa == []


def test_un_export_con_il_segno_si_registra_e_tipizza_entrate_e_uscite(archivio_scenari):
    db = archivio_scenari

    async def scenario():
        righe = [riga_csv("PRELIEVO ASSEGNO - NUM: 02087693%02d" % g, "-1496,96", f"{g:02d}/06/2026")
                 for g in range(1, 8)]
        righe += [riga_csv("BONIF. VS. FAVORE - CLIENTE %d" % g, "300,00", f"{g:02d}/06/2026") for g in range(8, 13)]
        await importa_estratto(FileCsv(righe))
        return await tutti(db, "estratto_conto_movimenti")

    ec = esegui(scenario())
    assert len(ec) == 12
    assert sum(1 for m in ec if m["tipo"] == "uscita") == 7 and sum(1 for m in ec if m["tipo"] == "entrata") == 5


# ── 8. categorie ─────────────────────────────────────────────────────────────

CAUSALI = [
    # (causale, importo, categoria attesa, fornitore estratto atteso o None)
    ("ADDEBITO F24 - DELEGA F24 ELEMENTI IDENTIFICATIVI ABCDEF", "-1.000,00", "F24", None),
    ("COMMISSIONI - COMM.SU BONIFICI", "-1,10", "Commissioni bancarie", None),
    ("INC.POS CARTE CREDIT 15/09 ESERCENTE 123", "250,00", "Corrispettivi POS", None),
    ("PRELIEVO ASSEGNO - DM 05387 CRA: 26050700167309 NUM: 0208771000", "-122,00", "Assegni", None),
    ("ADDEBITO MUTUO N. 12345 / 01/2026 RATA", "-1.500,00", "Rata mutuo", None),
    ("ADDEBITO NEXI - SDD CORE: 0000000000000000000012 NEXI PAYMENTS S.P.A.", "-640,00",
     "Addebito carta di credito", "NEXI PAYMENTS S.P.A."),
    ("BON.DA CERALDI GROUP SRL PER GIROCONTO", "5.000,00", "Giroconto", None),
    ("GIROCONTO A MASTERCARD SUMUP", "-300,00", "Giroconto", None),
    ("VERSAMENTO CONTANTI SPORTELLO", "900,00", "Versamento Banca", None),
]


def test_le_causali_non_ambigue_hanno_la_categoria_giusta_e_i_giroconti_mai_un_fornitore(archivio_scenari):
    db = archivio_scenari

    async def scenario():
        righe = [riga_csv(d, i, f"{15 + n:02d}/09/2026") for n, (d, i, _c, _f) in enumerate(CAUSALI)]
        await importa_estratto(FileCsv(righe))
        return {m["descrizione_originale"]: m for m in await tutti(db, "estratto_conto_movimenti")}

    movimenti = esegui(scenario())
    for causale, _importo, categoria, fornitore in CAUSALI:
        m = movimenti[causale]
        assert m["categoria"] == categoria, (causale, m["categoria"])
        assert (m.get("fornitore") or None) == fornitore, (causale, m.get("fornitore"))
    # un giroconto non ha mai un fornitore
    assert all(not m.get("fornitore") for m in movimenti.values() if m["categoria"] == "Giroconto")


def test_una_causale_ambigua_non_si_categorizza_e_l_importo_da_solo_non_collega_fatture(archivio_scenari):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, xml_fattura(), "drive")
        await importa_estratto(FileCsv([
            # due categorie non ambigue nella stessa causale: nessuna scelta a caso
            riga_csv("COMMISSIONI SU PAGAMENTO F24", "-5,00", "15/09/2026"),
            # importo identico alla fattura aperta, testo senza fornitore ne' numero: resta senza categoria
            riga_csv("BONIFICO A FAVORE DI ROSSI MARIO", "-122,00", "16/09/2026")]))
        return await tutti(db, "estratto_conto_movimenti"), await fattura(db, esito["id"])

    ec, inv = esegui(scenario())
    from app.services.stato_pagamento_fattura import e_pagata

    per_testo = {m["descrizione_originale"]: m for m in ec}
    assert not per_testo["COMMISSIONI SU PAGAMENTO F24"].get("categoria")
    rossi = per_testo["BONIFICO A FAVORE DI ROSSI MARIO"]
    assert rossi.get("categoria") != "Fatture" and rossi.get("riconciliato") is not True
    assert not e_pagata(inv)


@pytest.mark.parametrize("causale,fornitore,piva,importo", [
    ("ADDEBITO NEXI - SDD CORE: 0000000000000000000012 NEXI PAYMENTS S.P.A.", "NEXI PAYMENTS S.P.A.", "04107060966",
     "640.00"),
    ("GIROCONTO A MASTERCARD SUMUP", "SUMUP LIMITED", "IE9813461A", "300.00"),
])
def test_giroconti_e_saldo_carta_non_pagano_la_fattura_del_fornitore_con_lo_stesso_nome_e_importo(
        archivio_scenari, monkeypatch, causale, fornitore, piva, importo):
    """Il saldo della carta e il giroconto verso SumUp non sono un costo: non chiudono una fattura omonima."""
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico", piva=piva, nome=fornitore, id_="forn-x")
        netto = (_d(importo) / Decimal("1.22")).quantize(Decimal("0.01"))
        esito = await importa(db, xml_fattura(numero="X1", piva=piva, nome=fornitore, imponibile=str(netto),
                                              iva=str(_d(importo) - netto), totale=importo), "drive")
        parser_pdf_con(monkeypatch, [transazione_pdf("2026-09-18", causale.replace("ADDEBITO NEXI - ", ""),
                                                     -float(importo))])
        await importa_estratto(FileCsv([riga_csv(causale, f"-{importo.replace('.', ',')}", "18/09/2026")]))
        await importa_estratto(FilePdf())
        return await fattura(db, esito["id"]), await tutti(db, "estratto_conto_movimenti")

    inv, ec = esegui(scenario())
    from app.services.stato_pagamento_fattura import e_pagata

    assert not e_pagata(inv), "un giroconto non e' il pagamento di una fattura"
    assert len(ec) == 1 and ec[0]["categoria"] in ("Addebito carta di credito", "Giroconto")
    assert ec[0].get("riconciliato") is not True or ec[0].get("fattura_id") in (None, "")
