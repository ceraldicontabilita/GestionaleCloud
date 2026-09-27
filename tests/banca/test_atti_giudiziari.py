"""Spese di lite: gli atti della causa accanto ai bonifici che ne derivano.

Numeri, parti e importi sono finti. Una sentenza persa lascia bonifici senza
fattura: entrano nel fascicolo solo se la causale cita la sentenza (o il
ruolo generale) o se il titolare ve li mette, mai per importo o controparte.
"""
import asyncio

import fitz

from app.routers.documenti import detect_document_type
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.atti_giudiziari import (
    COLL,
    TIPO_ATTESTAZIONE,
    TIPO_PRECETTO,
    TIPO_RELATA,
    TIPO_SENTENZA,
    atti_del_fascicolo,
    collega_e_registra,
    contenuto,
    leggi_atto,
    numeri_citati,
    registra_atto,
    tipo_atto,
)
from app.services.bank_payment_allocations import (
    _reconcile_unique_identity_matches,
    numeri_fattura_citati,
)
from app.services.mapping_piano_conti import contropartita_per_categoria
from app.services.sumup_conto import COLL_MOVIMENTI

SENTENZA = (
    "REPUBBLICA ITALIANA IN NOME DEL POPOLO ITALIANO IL TRIBUNALE DI NAPOLI "
    "SEZIONE SESTA CIVILE SENTENZA nella controversia civile ... "
    "Sentenza n. 1234/2021 pubbl. il 21/10/2021 RG n. 5678/2016 "
    "CONDANNA gli attori al PAGAMENTO delle SPESE"
)
PRECETTO = (
    "ATTO DI PRECETTO Per l'Avv. Mario Rossi PREMESSO che con sentenza n.1234/2021 "
    "del Tribunale di Napoli nel giudizio R.G. n.5678/2016 ... intima di pagare la "
    "complessiva somma di €. 15.830,25 (quindicimila...)"
)
RELATA = (
    "RELATA DI NOTIFICA A MEZZO DI POSTA ELETTRONICA CERTIFICATA Io sottoscritto "
    "NOTIFICO sentenza del Tribunale di Napoli VI Sezione Civile n. 1234/2021 "
    "nel giudizio RG 5678/2016, atto di precetto, attestazione"
)
ATTESTAZIONE = (
    "Io sottoscritto avv. ATTESTO CHE la copia della sentenza del Tribunale di Napoli "
    "n. 1234/2021 nel giudizio RG 5678/2016 e l'atto di precetto sono conformi"
)


def _maiuscolo(testo):
    return " ".join(testo.split()).upper()


def _pdf(testo):
    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_textbox(fitz.Rect(40, 40, 555, 800), testo, fontsize=9)
    return documento.tobytes()


def _uscita(codice, data, importo, causale, **extra):
    return {
        "id": f"sumup_conto:{codice}", "codice_transazione": codice, "data": data,
        "tipo_transazione": "Bonifico bancario in uscita", "tipo": "uscita",
        "riferimento": "CONTROPARTE SPA", "causale": causale,
        "descrizione": f"CONTROPARTE SPA — {causale}",
        "importo": f"-{importo}", "segno": "uscita", "conto_contabile": "19.01.05", **extra,
    }


def test_tipo_e_numeri_dal_testo():
    assert tipo_atto(_maiuscolo(SENTENZA)) == TIPO_SENTENZA
    assert tipo_atto(_maiuscolo(PRECETTO)) == TIPO_PRECETTO
    assert tipo_atto(_maiuscolo(RELATA)) == TIPO_RELATA
    assert tipo_atto(_maiuscolo(ATTESTAZIONE)) == TIPO_ATTESTAZIONE
    # Senza il numero di una sentenza non si sa di quale causa sia.
    assert tipo_atto("IL TRIBUNALE DI NAPOLI IN NOME DEL POPOLO ITALIANO") is None
    precetto = leggi_atto(b"", _maiuscolo(PRECETTO))
    assert precetto["numero_sentenza"] == "1234/2021"
    assert precetto["ruolo_generale"] == "5678/2016"
    assert precetto["fascicolo"] == "sentenza:1234/2021"
    assert precetto["importo_intimato"] == "15830.25"
    assert leggi_atto(b"", _maiuscolo(SENTENZA))["tribunale"] == "Napoli"


def test_numeri_citati_in_causale():
    assert numeri_citati("Ala sentenza 1234/21 avv. acc. 371/26") == {"1234/2021"}
    assert numeri_citati("saldo RG 5678/2016") == {"5678/2016"}
    assert numeri_citati("Fattura 1234/21") == set()


def test_riconosciuto_all_import():
    assert detect_document_type("atto.pdf", _pdf(SENTENZA)) == "atto_giudiziario"
    assert detect_document_type("relata.pdf", _pdf(RELATA)) == "atto_giudiziario"


def test_atto_archiviato_una_volta_e_pagamenti_nel_fascicolo():
    db = ClientArchivioMemoria()["atti_giudiziari"]
    pdf = _pdf(SENTENZA)

    async def scenario():
        await db[COLL_MOVIMENTI].insert_many([
            # Cita la sentenza: entra da solo.
            _uscita("C9LITE0001", "2026-09-04", "625.00", "Ala sentenza 1234/21 avv. acc. 371/26"),
            # Non la cita, ma il titolare l'ha messa nel fascicolo.
            _uscita("C9LITE0002", "2026-09-04", "2328.26", "Seconda rata transazione Appello",
                    fascicolo_dichiarato="1234/2021"),
            # Stessa controparte, niente citazione ne' dichiarazione: resta fuori.
            _uscita("C9ALTRO001", "2026-09-05", "100.00", "Rimborso spese"),
        ])
        primo = await registra_atto(db, "sentenza.pdf", pdf)
        secondo = await registra_atto(db, "sentenza (1).pdf", pdf)
        pagamenti = await collega_e_registra(db)
        ancora = await collega_e_registra(db)
        movimenti = {m["codice_transazione"]: m for m in await db[COLL_MOVIMENTI].find({}, {"_id": 0}).to_list(None)}
        banca = await db["prima_nota_banca"].find({}, {"_id": 0}).to_list(None)
        return primo, secondo, pagamenti, ancora, movimenti, banca, await contenuto(db, primo["id"]), \
            await atti_del_fascicolo(db, "sentenza:1234/2021"), await db[COLL].count_documents({})

    primo, secondo, pagamenti, ancora, movimenti, banca, originale, atti, quanti = asyncio.run(scenario())
    assert primo["duplicate"] is False and secondo["duplicate"] is True and quanti == 1
    assert originale == (pdf, "sentenza.pdf")
    assert [a["tipo"] for a in atti] == [TIPO_SENTENZA]

    assert pagamenti["collegati"] == 2 and pagamenti["prima_nota_scritte"] == 2
    assert movimenti["C9LITE0001"]["fascicolo_collegato_da"] == "citato_in_causale"
    assert movimenti["C9LITE0002"]["fascicolo_collegato_da"] == "dichiarato_titolare"
    assert "fascicolo_giudiziario" not in movimenti["C9ALTRO001"]

    assert len(banca) == 2
    for riga in banca:
        assert riga["categoria"] == "Spese legali e contenzioso"
        assert riga["conto_contabile"] == "19.01.05"
        assert riga["fascicolo_giudiziario"] == "sentenza:1234/2021"
    # Il secondo giro non scrive niente.
    assert ancora["collegati"] == 0 and ancora["prima_nota_scritte"] == 0


def test_contropartita_delle_spese_di_lite():
    assert contropartita_per_categoria("banca", "uscita", "Spese legali e contenzioso") == "71.03"


def _fattura(fid, numero, data, totale, fornitore="ASCENSORI ROSSI S.R.L.", **extra):
    return {
        "id": fid, "invoice_number": numero, "invoice_date": data, "total_amount": totale,
        "supplier_name": fornitore, "supplier_vat": "01234567890",
        "pagato": False, "stato_pagamento": "da_pagare", "status": "imported", **extra,
    }


def test_bonifico_che_paga_piu_fatture_elencate_in_causale():
    assert numeri_fattura_citati({"causale": "Pagamento Fatture 386, 738, 1436"}) == ["386", "738", "1436"]
    assert numeri_fattura_citati({"causale": "Saldo fatture fvl824 fvl968"}) == ["FVL824", "FVL968"]
    db = ClientArchivioMemoria()["fatture_in_causale"]
    movimento = {
        "id": "sumup_conto:C9MULTI001", "data": "2026-09-22", "tipo": "uscita",
        "importo": "-461.16", "conto_contabile": "19.01.05",
        "causale": "Pagamento Fatture 386, 738, 1436",
        "descrizione": "Ascensori Rossi Srl — IT00X — Pagamento Fatture 386, 738, 1436",
    }
    corto = {**movimento, "id": "sumup_conto:C9MULTI002", "importo": "-307.44",
             "causale": "Pagamento Fatture 386, 999",
             "descrizione": "Ascensori Rossi Srl — Pagamento Fatture 386, 999"}

    async def scenario():
        await db["invoices"].insert_many([
            _fattura("f-386", "386", "2026-02-20", 153.72),
            # Gia' dichiarata pagata dal titolare: attende la prova della banca.
            _fattura("f-738", "738", "2026-04-13", 153.72, stato_pagamento="pagata",
                     pagato=True, in_attesa_riscontro_banca=True),
            _fattura("f-1436", "1436", "2026-07-17", 153.72),
            # Copia archiviata della stessa fattura: non conta.
            _fattura("f-386-arch", "386", "2026-02-20", 153.72, status="archived"),
            # Stesso numero di un altro fornitore: non conta.
            _fattura("f-altro", "738", "2026-04-13", 153.72, fornitore="PANIFICIO BIANCHI SRL"),
        ])
        await db[COLL_MOVIMENTI].insert_many([movimento, corto])
        esito = await _reconcile_unique_identity_matches(db, [dict(movimento), dict(corto)], proponi=False)
        fatture = {f["id"]: f for f in await db["invoices"].find({}, {"_id": 0}).to_list(None)}
        movimenti = {m["id"]: m for m in await db[COLL_MOVIMENTI].find({}, {"_id": 0}).to_list(None)}
        return esito, fatture, movimenti

    esito, fatture, movimenti = asyncio.run(scenario())
    assert sorted(v["fattura_id"] for v in esito["collegati"]) == ["f-1436", "f-386", "f-738"]
    for fid in ("f-386", "f-738", "f-1436"):
        assert fatture[fid]["pagato"] is True
        assert fatture[fid]["movimento_bancario_id"] == "sumup_conto:C9MULTI001"
    assert fatture["f-altro"].get("movimento_bancario_id") is None
    assert movimenti["sumup_conto:C9MULTI001"]["fattura_ids"] == ["f-386", "f-738", "f-1436"]
    # La 999 non esiste ancora: la somma non torna e il bonifico resta com'e'.
    assert not movimenti["sumup_conto:C9MULTI002"].get("riconciliato")
