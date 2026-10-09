"""Scenario funzionale: parcella con ritenuta → attesa 1040 → quietanza → ritenuta versata (avviso una volta)."""
from datetime import date, timedelta

import pytest

from app.routers import ritenute
from app.services import quietanze_import as qi
from tests.fiscale.scenari_f24_comuni import collezione, quietanza_parsed, run
from tests.fiscale.test_scenari_funzionali_f24_banca import ambiente  # noqa: F401  (fixture)

XML = """<FatturaElettronica><DatiGeneraliDocumento>
<DatiRitenuta><TipoRitenuta>RT01</TipoRitenuta><ImportoRitenuta>280.00</ImportoRitenuta>
<AliquotaRitenuta>20.00</AliquotaRitenuta><CausalePagamento>A</CausalePagamento></DatiRitenuta>
</DatiGeneraliDocumento></FatturaElettronica>"""


@pytest.fixture
def telegram(monkeypatch):
    inviati = []

    async def _invia(testo, *a, **k):
        inviati.append(testo)
        return True

    import app.services.telegram_notifications as tg
    monkeypatch.setattr(tg, "send_notification", _invia)
    return inviati


def _parcella(db, data, fid="fatt-1", pagata_il=None):
    """Parcella con ritenuta, pagata al professionista (per difetto lo stesso giorno).

    Il periodo del 1040 e' il mese del PAGAMENTO al professionista (decisione
    del 02/10/2026), non il mese della fattura: queste scene pagano la parcella
    nel mese della fattura, cosi' il 1040 atteso resta quello del mese.
    """
    return run(ritenute.upsert_ritenuta_da_fattura(db, {
        "id": fid, "invoice_number": "12/2026", "invoice_date": data, "supplier_name": "STUDIO ROSSI",
        "supplier_vat": "01234567890", "xml_raw": XML,
        "stato": "pagata", "data_pagamento": pagata_il or data}))


def _paga_1040(db, letti, periodo, data, righe_extra=(), importo="280.00", n=1):
    righe = [("sezione_erario", "1040", periodo, importo, "0"), *righe_extra]
    pdf = f"%PDF-1040-{n}".encode()
    letti[pdf] = quietanza_parsed(righe, data, f"260{n}0111000000{n:03d}/000001")
    return run(qi.importa_quietanza_bytes(db, pdf, "q1040.pdf", fonte="test"))


def _stato(db):
    [r] = collezione(db, "ritenute_acconto")
    return r


def test_ritenuta_attesa_alert_quietanza_puntuale_e_avviso_una_volta(ambiente, telegram):
    db, letti, _mp = ambiente
    oggi = date.today()
    mese_prima = (oggi.replace(day=1) - timedelta(days=1))
    fattura = mese_prima.replace(day=10).isoformat()
    periodo = f"{mese_prima.month:02d}/{mese_prima.year}"
    rit = _parcella(db, fattura)
    # il fatto crea subito l'attesa: alert e messaggio, prima di qualunque prova
    assert rit["importo_cents"] == 28000
    [alert] = run(db["alerts"].find({"codice": "RITENUTA_DA_VERSARE", "stato": "aperto"}).to_list(5))
    assert alert["entita_id"] == "fatt-1" and "280,00 €" in alert["dettaglio"] and "1040" in alert["dettaglio"]
    assert len(telegram) == 1 and telegram[0].startswith("<b>Ritenuta da versare</b>")

    legale = date.fromisoformat(rit["scadenza_legale"])
    paga_il = min(oggi, legale)
    _paga_1040(db, letti, periodo, paga_il.isoformat())
    r = _stato(db)
    assert r["stato"] == "pagata_puntuale" and r["stato_obbligazione"] == "VERSATA"
    assert r["f24_importo_tributo_cents"] is None and r["quietanza_protocollo"]
    assert run(db["alerts"].find({"codice": "RITENUTA_DA_VERSARE", "stato": "aperto"}).to_list(5)) == []
    assert len(telegram) == 2 and telegram[1].startswith("<b>Ritenuta pagata</b>") and "nei termini" in telegram[1]
    # un secondo riscontro (altra quietanza, riallineamento) non manda un altro messaggio
    run(ritenute.riconcilia_ritenute_esistenti(db))
    assert len(telegram) == 2 and _stato(db)["avviso_versamento_inviato"] is True


def test_versamento_vecchio_si_segna_in_silenzio_e_la_ritardataria_si_classifica(ambiente, telegram):
    db, letti, _mp = ambiente
    _parcella(db, "2025-03-10", "fatt-a")
    _parcella(db, "2025-04-10", "fatt-b")
    # marzo: 1040 versato il 16/04/2025 (puntuale); aprile: 1040 versato il 20/05/2025 senza sanzioni
    _paga_1040(db, letti, "03/2025", "2025-04-16", n=1)
    _paga_1040(db, letti, "04/2025", "2025-05-20", n=2)
    stati = {r["fattura_id"]: r for r in collezione(db, "ritenute_acconto")}
    assert stati["fatt-a"]["stato"] == "pagata_puntuale"
    assert stati["fatt-b"]["stato"] == "pagata_in_ritardo_senza_ravvedimento"
    # oltre 45 giorni: segnata senza messaggio ("e' storia"), una volta
    assert all(r["avviso_versamento_inviato"] is False and r["avviso_versamento_at"] for r in stati.values())
    assert [t for t in telegram if "Ritenuta pagata" in t] == []


def test_ritenuta_ravveduta_con_interessi_cumulati_al_tributo_e_versata(ambiente, telegram):
    """Ris. 18/E: sui 1040 gli interessi si cumulano al tributo (280,00 → 280,31) e la sanzione ha il codice 8948.

    Prima la riga 1040 versata veniva cercata «uguale alla ritenuta al centesimo»: con gli interessi
    nel tributo la ritenuta restava «scaduta da versare» anche se la quietanza provava il versamento.
    """
    db, letti, _mp = ambiente
    _parcella(db, "2025-03-10")
    # scadenza 16/04/2025, versata il 30/04 (14 gg): sanzione 0,1% × 14 = 3,92; interessi legali 0,31
    _paga_1040(db, letti, "03/2025", "2025-04-30", importo="280.31",
               righe_extra=[("sezione_erario", "8948", "03/2025", "3.92", "0")])
    r = _stato(db)
    assert r["stato"] == "pagata_con_ravvedimento" and r["stato_obbligazione"] == "VERSATA"
    assert r["quietanza_data"] == "2025-04-30"
    # la pagina Tributi dice la stessa cosa: ravveduto, con gli interessi cumulati al tributo, non «non torna»
    from app.services import tributi_per_codice as tributi

    voce = [v for v in run(tributi.carica_voci(db))["voci"] if v["codice"] == "1040"][0]
    assert voce["stato"] == tributi.RAVVEDUTO and voce["scarto_cents"] == 0
    assert voce["atteso_cents"] == 28000 and voce["pagato_cents"] == 28031 and voce["interessi_cumulati_cents"] == 31
    # e lo Scadenzario: scadenza della ritenuta (16/04/2025), 14 giorni, sanzione 8948 e interessi cumulati sufficienti
    [scad] = [v for v in collezione(db, "scadenzario_tributi") if v["codice"] == "1040"]
    assert scad["stato"] == "RAVVEDUTO" and scad["scadenza"] == "2025-04-16" and scad["pagamenti"][0]["giorni_ritardo"] == 14


def test_la_riga_maggiore_vale_solo_con_sanzione_e_interessi_plausibili(ambiente, telegram):
    db, letti, _mp = ambiente
    _parcella(db, "2025-03-10")
    # 280,31 senza sanzione nel periodo: un importo vicino, non un ravvedimento
    _paga_1040(db, letti, "03/2025", "2025-04-30", importo="280.31", n=1)
    assert _stato(db)["stato"] == "scaduta_da_versare"
    # sanzione presente ma eccedenza (70,00) ben oltre gli interessi legali dei 14 giorni: non e' la stessa ritenuta
    _paga_1040(db, letti, "03/2025", "2025-04-30", importo="350.00", n=2,
               righe_extra=[("sezione_erario", "8948", "03/2025", "3.92", "0")])
    assert _stato(db)["stato"] == "scaduta_da_versare"
    # e per Tributi un importo cosi' lontano resta «non torna con le fatture»
    from app.services import tributi_per_codice as tributi

    voce = [v for v in run(tributi.carica_voci(db))["voci"] if v["codice"] == "1040"][0]
    assert voce["stato"] == tributi.NON_TORNA and voce["scarto_cents"] != 0


def test_ritenuta_ravveduta_con_modello_e_quietanza_si_aggancia_al_modello(ambiente, telegram):
    from app.services import f24_canonico
    from tests.fiscale.scenari_f24_comuni import modello_parsed

    db, letti, _mp = ambiente
    _parcella(db, "2025-03-10")
    righe = [("sezione_erario", "1040", "03/2025", "280.31", "0"), ("sezione_erario", "8948", "03/2025", "3.92", "0")]
    letti[b"%PDF-modello-ravv"] = modello_parsed(righe, "2025-04-30")
    assert run(f24_canonico.importa_modello_bytes(db, b"%PDF-modello-ravv", "F24 ritenute ravveduto.pdf", source="test"))["success"]
    assert _stato(db).get("stato") != "pagata_con_ravvedimento"      # il modello da solo non prova il versamento
    letti[b"%PDF-q-ravv"] = quietanza_parsed(righe, "2025-04-30", "25043011000000009/000001")
    run(qi.importa_quietanza_bytes(db, b"%PDF-q-ravv", "q ravv.pdf", fonte="test"))
    r = _stato(db)
    assert r["stato"] == "pagata_con_ravvedimento" and r["f24_id"] and r["data_pagamento"] == "2025-04-30"
