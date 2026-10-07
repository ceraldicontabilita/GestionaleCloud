"""Estratto conto PDF del conto BNL 4500/3192 (chiuso): lettura e archivio.

Il testo piatto del PDF non dice se «597,86 €» e' un'uscita o un'entrata: il
verso sta nella colonna. Le parole sintetiche qui sotto ricalcano le
coordinate del PDF reale (intestazioni «PER UNA USCITA DI» a x≈446-479,
«PER UNA ENTRATA DI» a x≈506-546, importi allineati a destra a 494 e 554).
Dati finti, IBAN finto con ABI 01005, aritmetica dei saldi coerente.
"""
import asyncio
from decimal import Decimal

import pytest

from app.routers.bank import estratto_conto as modulo
from app.services import conti_pos
from app.services.estratto_conto_bnl_parser import (
    FONTE_BNL,
    EstrattoBNLNonValido,
    e_estratto_bnl,
    leggi_parole_bnl,
)

IBAN_FINTO = "IT02L0100503400000000099999"
X_CONTABILE, X_VALUTA, X_ABI, X_DESCRIZIONE = 49.6, 120.5, 197.4, 216.8
X1_USCITA, X1_ENTRATA = 494.4, 553.9


def _parola(testo, x0, top, larghezza=None):
    larghezza = larghezza if larghezza is not None else 4.0 * len(testo)
    return {"text": testo, "x0": x0, "x1": x0 + larghezza, "top": top}


def _riga_testo(top, testo, x0=X_CONTABILE):
    """Una riga di testo libero spezzata in parole, da sinistra."""
    parole, x = [], x0
    for pezzo in testo.split():
        parole.append(_parola(pezzo, x, top))
        x += 4.0 * len(pezzo) + 2.0
    return parole


def _intestazione(top):
    """Le due righe d'intestazione della tabella, come nel PDF reale."""
    return [
        _parola("CAUS.", 189.9, top - 19.6, 20.2),
        _parola("USCITA", 446.4, top - 19.6, 24.2), _parola("DI", 472.4, top - 19.6, 6.9),
        _parola("ENTRATA", 506.0, top - 19.6, 31.2), _parola("DI", 539.1, top - 19.6, 6.9),
        _parola("ABI", 189.9, top - 9.8, 11.5),
        _parola("(DATA", 49.6, top, 21.1), _parola("CONTABILE)", 72.5, top, 40.1),
        _parola("(DATA", 120.5, top, 21.1), _parola("VALUTA)", 143.4, top, 29.4),
    ]


def _importo(testo, top, colonna):
    x1 = X1_USCITA if colonna == "uscita" else X1_ENTRATA
    larghezza = 3.6 * len(testo)
    return [_parola(testo, x1 - larghezza, top, larghezza), _parola("€", x1 + 1.8, top, 4.1)]


def _movimento(top, contabile, valuta, abi, descrizione, importo, colonna):
    parole = [_parola(contabile, X_CONTABILE, top, 38.6), _parola(valuta, X_VALUTA, top, 38.5),
              _parola(abi, X_ABI, top, 8.1)]
    parole += _riga_testo(top, descrizione, X_DESCRIZIONE)
    return parole + _importo(importo, top, colonna)


def _continuazione(top, testo):
    return _riga_testo(top, testo, X_DESCRIZIONE)


def _pagine(saldo_iniziale="+ 173,02", entrate="+ 1.000,11", uscite="- 623,08",
            saldo_finale="+ 550,05", colonna_versamento="entrata"):
    pagina1 = (
        _riga_testo(20, "ESTRATTO CONTO N. 1/2022")
        + _riga_testo(30, "AI MOVIMENTI DAL 03/01/2022 AL 31/03/2022")
        + _riga_testo(40, "C/C N. 4500/3192")
        + _riga_testo(50, f"IBAN¹: {IBAN_FINTO} BIC²: BNLIITRR")
        + _riga_testo(60, f"Quale era il saldo iniziale al 03/01/2022? {saldo_iniziale} €")
        + _riga_testo(70, f"Quali sono le entrate complessive di questo periodo? {entrate} €")
        + _riga_testo(80, f"Quali sono le uscite complessive di questo periodo? {uscite} €")
        + _riga_testo(90, f"QUALE E' IL SALDO FINALE AL 31/03/2022? {saldo_finale} €")
        + _intestazione(120)
        + [_parola("31/12/2021", X_CONTABILE, 134, 38.6)] + _riga_testo(134, "SALDO INIZIALE", X_DESCRIZIONE)
        + _importo("173,02", 134, "entrata")
        + _movimento(146, "03/01/2022", "31/12/2021", "18", "Interessi creditori", "0,11", "entrata")
        + _movimento(158, "03/01/2022", "31/12/2021", "66",
                     "Imposta bollo su Rap n. 003192/4500 al 01.01.22", "25,22", "uscita")
        # Segno di stampa verticale nel margine, fuori dalla tabella.
        + [_parola("1.01", 18.4, 155, 6.0)]
        + _riga_testo(180, "1-Checos'e'l'IBAN? Il codice bancario internazionale", 46.8)
        + _riga_testo(190, "Banca Nazionale del Lavoro SpA - Iscritta all'Albo delle banche", 46.8)
    )
    pagina2 = (
        _riga_testo(20, "ESTRATTO CONTO N. 1/2022")
        + _intestazione(100)
        + _movimento(114, "11/01/2022", "11/01/2022", "78", "Versamento di contante o assimilati",
                     "1.000,00", colonna_versamento)
        + _movimento(126, "31/01/2022", "31/01/2022", "50",
                     "Addebito SEPA DD a fav. di ALD AUTOMOTIVE ITALIA SRL", "597,86", "uscita")
        + _continuazione(136, "di cui 1,50 per Commiss/Spese")
        + _riga_testo(150, "IL SALDO FINALE AL 31/03/2022 E' QUINDI:")
        + _importo("550,05", 148.6, "entrata")
        + _riga_testo(170, "QUALI SONO, IN SINTESI, GLI INTERESSI, LE SPESE E GLI ALTRI COSTI")
    )
    # Pagina senza intestazione della tabella: le righe «con valuta antergata»
    # non sono movimenti e non si leggono.
    pagina3 = (
        _riga_testo(20, "ELENCO OPERAZIONI CON VALUTA ANTERGATA")
        + _riga_testo(30, "03/01 31/12/21 0,11 Competenze su c/c")
    )
    return [pagina1, pagina2, pagina3]


def test_legge_le_due_colonne_le_continuazioni_e_l_intestazione():
    estratto = leggi_parole_bnl(_pagine())

    assert estratto.numero_estratto == "1/2022"
    assert (estratto.periodo_dal, estratto.periodo_al) == ("2022-01-03", "2022-03-31")
    assert estratto.conto == "4500/3192" and estratto.iban == IBAN_FINTO
    assert estratto.saldo_iniziale == Decimal("173.02")
    assert estratto.saldo_finale == Decimal("550.05")
    assert estratto.saldo_iniziale_tabella == Decimal("173.02")
    assert estratto.saldo_finale_tabella == Decimal("550.05")

    righe = estratto.righe
    assert [(r.data_contabile, r.data_valuta, r.causale_abi, r.tipo, r.importo) for r in righe] == [
        ("2022-01-03", "2021-12-31", "18", "entrata", Decimal("0.11")),
        ("2022-01-03", "2021-12-31", "66", "uscita", Decimal("25.22")),
        ("2022-01-11", "2022-01-11", "78", "entrata", Decimal("1000.00")),
        ("2022-01-31", "2022-01-31", "50", "uscita", Decimal("597.86")),
    ]
    assert righe[1].descrizione == "Imposta bollo su Rap n. 003192/4500 al 01.01.22"
    # La continuazione si attacca alla riga; il suo «1,50» non e' un importo.
    assert righe[3].descrizione == (
        "Addebito SEPA DD a fav. di ALD AUTOMOTIVE ITALIA SRL di cui 1,50 per Commiss/Spese"
    )
    assert all(isinstance(r.importo, Decimal) and r.importo > 0 for r in righe)
    assert [r.pagina for r in righe] == [1, 1, 2, 2]


def test_il_verso_viene_dalla_colonna_non_dalla_causale():
    """Lo stesso «Versamento» stampato nella colonna uscite cambia verso e
    fa saltare la verifica: il lettore non corregge, rifiuta."""
    with pytest.raises(EstrattoBNLNonValido) as errore:
        leggi_parole_bnl(_pagine(colonna_versamento="uscita"))
    assert "Totali del riepilogo diversi" in str(errore.value)


def test_rifiuta_un_estratto_che_non_torna():
    # Riepilogo con un'entrata in meno rispetto alle righe lette.
    with pytest.raises(EstrattoBNLNonValido):
        leggi_parole_bnl(_pagine(entrate="+ 1.000,00", saldo_finale="+ 549,94"))
    # Totali coerenti con le righe, ma saldo finale stampato che non segue.
    with pytest.raises(EstrattoBNLNonValido) as errore:
        leggi_parole_bnl(_pagine(saldo_finale="+ 551,05"))
    assert "non torna" in str(errore.value) or "Saldo finale" in str(errore.value)


def test_senza_riepilogo_non_si_puo_verificare_e_non_si_legge():
    pagine = _pagine()
    pagine[0] = [w for w in pagine[0] if w["top"] != 70]  # via le entrate complessive
    with pytest.raises(EstrattoBNLNonValido) as errore:
        leggi_parole_bnl(pagine)
    assert "entrate complessive" in str(errore.value)


@pytest.mark.parametrize("testo, atteso", [
    (f"ESTRATTO CONTO N. 1/2022 IBAN¹: {IBAN_FINTO} (DATA CONTABILE)", True),
    ("ESTRATTO CONTO N. 4/2021 Banca Nazionale del Lavoro SpA (DATA CONTABILE) (DATA VALUTA)", True),
    # Banco BPM: altra banca, altro lettore.
    ("ESTRATTO CONTO N. 2/2026 BANCO BPM 05034 DATA CONTABILE DATA VALUTA", False),
    # La carta BNL Business ha un lettore suo.
    (f"Estratto Conto n. 3 del 01.02.2022 CARTA BNL BUSINESS {IBAN_FINTO} data contabile", False),
    # Una bolletta che cita la banca non e' un estratto.
    ("Addebito automatico presso Banca Nazionale del Lavoro", False),
])
def test_riconoscimento_dal_contenuto(testo, atteso):
    assert e_estratto_bnl(testo) is atteso


# --- Archivio: stesso motore d'import del conto BPM ------------------------

class _File:
    skip_duplicate_repairs = True
    filename = "Estratto_Conto (3).pdf"

    def __init__(self, contenuto=b"%PDF-finto-bnl"):
        self._contenuto = contenuto

    async def read(self):
        return self._contenuto


def _db(monkeypatch, nome):
    from app.services.archivio_documenti_memoria import ClientArchivioMemoria
    finto = ClientArchivioMemoria()[nome]
    monkeypatch.setattr(modulo.Database, "get_db", staticmethod(lambda: finto))
    return finto


def _finge_il_pdf(monkeypatch):
    estratto = leggi_parole_bnl(_pagine())
    monkeypatch.setattr(modulo, "e_estratto_bnl_pdf", lambda contenuto: True)
    monkeypatch.setattr(modulo, "leggi_estratto_bnl", lambda contenuto: estratto)
    return estratto


def test_import_scrive_sul_conto_bnl_senza_prima_nota_e_il_secondo_giro_da_zero(monkeypatch):
    db = _db(monkeypatch, "bnl_import")
    _finge_il_pdf(monkeypatch)

    primo = asyncio.run(modulo.import_estratto_conto(_File()))
    assert primo["stats"]["nuovi"] == 4 and primo["stats"]["duplicati"] == 0

    movimenti = asyncio.run(db["estratto_conto_movimenti"].find({}).to_list(20))
    assert len(movimenti) == 4
    assert {m["conto_contabile"] for m in movimenti} == {conti_pos.CONTO_BNL}
    assert conti_pos.CONTO_BNL != conti_pos.CONTO_BPM
    assert {m["banca"] for m in movimenti} == {"BNL"}
    assert {m["fonte"] for m in movimenti} == {FONTE_BNL}
    assert {m["source"] for m in movimenti} == {FONTE_BNL}
    assert {m["iban"] for m in movimenti} == {IBAN_FINTO}
    assert {m["numero_estratto"] for m in movimenti} == {"1/2022"}
    assert all(m["file_sha256"] and m["source_filename"] == _File.filename for m in movimenti)
    assert all(m["operation_key"] and m["operation_id"].startswith("bank:") for m in movimenti)
    per_data = {(m["data"], m["tipo"]): m for m in movimenti}
    versamento = per_data[("2022-01-11", "entrata")]
    assert versamento["importo"] == 1000.0 and versamento["natura"] == "versamento_contanti"
    assert versamento["causale_abi"] == "78" and versamento["data_pagamento"] == "2022-01-11"
    assert per_data[("2022-01-31", "uscita")]["importo"] == 597.86
    # Nessuna proiezione: niente Prima Nota banca o cassa per il conto BNL.
    assert asyncio.run(db["prima_nota_banca"].count_documents({})) == 0
    assert asyncio.run(db["prima_nota_cassa"].count_documents({})) == 0
    assert not any(m.get("importato_prima_nota") for m in movimenti)

    secondo = asyncio.run(modulo.import_estratto_conto(_File()))
    assert secondo["stats"]["nuovi"] == 0 and secondo["stats"]["duplicati"] == 4
    assert asyncio.run(db["estratto_conto_movimenti"].count_documents({})) == 4
    assert asyncio.run(db["prima_nota_banca"].count_documents({})) == 0


def test_un_estratto_bnl_che_non_quadra_non_entra_in_archivio(monkeypatch):
    from fastapi import HTTPException

    db = _db(monkeypatch, "bnl_non_quadra")
    monkeypatch.setattr(modulo, "e_estratto_bnl_pdf", lambda contenuto: True)

    def esplode(contenuto):
        raise EstrattoBNLNonValido("Il saldo non torna")

    monkeypatch.setattr(modulo, "leggi_estratto_bnl", esplode)
    with pytest.raises(HTTPException) as errore:
        asyncio.run(modulo.import_estratto_conto(_File()))
    assert errore.value.status_code == 422 and "non torna" in errore.value.detail
    assert asyncio.run(db["estratto_conto_movimenti"].count_documents({})) == 0


def test_il_conto_bnl_non_si_accoppia_con_i_doppioni_bpm():
    from app.services.doppioni_estratto_conto import conto_del_movimento

    assert conto_del_movimento({"banca": "BNL"}) == "bnl"
    assert conto_del_movimento({"banca": "Banco BPM"}) == "bpm"


def test_il_vecchio_ingresso_delega_al_motore_unico(monkeypatch):
    from app.parsers import estratto_conto_bnl_parser as legacy
    from app.services import estratto_conto_bnl_parser as motore

    estratto = leggi_parole_bnl(_pagine())
    monkeypatch.setattr(motore, "e_estratto_bnl_pdf", lambda contenuto: True)
    monkeypatch.setattr(motore, "leggi_estratto_bnl", lambda contenuto: estratto)

    esito = legacy.parse_estratto_conto_bnl(b"%PDF-finto")
    assert esito["success"] and esito["tipo_documento"] == "estratto_conto_bnl_cc"
    assert len(esito["transazioni"]) == 4
    assert esito["transazioni"][2]["importo"] == 1000.0
    assert esito["transazioni"][3]["importo"] == -597.86
    assert esito["metadata"]["numero_conto"] == "4500/3192"


# --- Cartella unica: l'arretrato non ferma il conto BNL -------------------

def test_l_arretrato_non_ferma_l_estratto_bnl(monkeypatch):
    import app.routers.documenti as documenti
    import app.services.classificazione_estratti as cls
    from app.services import drive_cartella_unica as cu

    monkeypatch.delenv("DRIVE_ESTRATTI_ANNO_MINIMO", raising=False)
    chiamato = []

    async def upload(**_):
        chiamato.append(1)
        return {"success": True, "tipo_rilevato": "estratto_conto"}

    monkeypatch.setattr(documenti, "detect_document_type", lambda nome, contenuto: "estratto_conto")
    monkeypatch.setattr(documenti, "upload_documento_automatico", upload)
    monkeypatch.setattr(cls, "anno_documento", lambda nome, contenuto: 2022)

    # Un estratto 2022 di un'altra banca resta fermo.
    monkeypatch.setattr(cls, "estratto_storico_ammesso", lambda nome, contenuto: False)
    esito = asyncio.run(cu._smista("Estratto_Conto.pdf", b"%PDF", {}))
    assert esito["arretrato"] is True and not chiamato

    # Lo stesso anno, ma e' il conto BNL chiuso: si legge.
    monkeypatch.setattr(cls, "estratto_storico_ammesso", lambda nome, contenuto: True)
    esito = asyncio.run(cu._smista("Estratto_Conto.pdf", b"%PDF", {}))
    assert chiamato and esito["success"] is True and not esito.get("arretrato")


def test_il_riconoscimento_storico_vale_solo_per_i_pdf_bnl(monkeypatch):
    import app.services.classificazione_estratti as cls

    monkeypatch.setattr(cls, "_testo_del_pdf", lambda contenuto: (
        f"ESTRATTO CONTO N. 4/2021 IBAN¹: {IBAN_FINTO} (DATA CONTABILE)"))
    assert cls.estratto_storico_ammesso("Estratto_Conto.pdf", b"%PDF") is True
    assert cls.estratto_storico_ammesso("Movimenti_BNL_BPM.xlsx", b"x") is False
    monkeypatch.setattr(cls, "_testo_del_pdf", lambda contenuto: "ESTRATTO CONTO BANCO BPM 05034")
    assert cls.estratto_storico_ammesso("Estratto_Conto.pdf", b"%PDF") is False
