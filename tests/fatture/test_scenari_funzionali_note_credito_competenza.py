"""Collaudo funzionale 4 e 6: nota di credito e competenza contro pagamento.

* La nota di credito (TD04) non e' un costo: il giornale scrive l'inverso (meno costo, meno IVA a credito,
  meno debito), la partita e' di tipo nota di credito, mai un cespite.
* Competenza e pagamento sono due date: un F24, una ritenuta o un bonifico pagati non cambiano il costo del
  conto economico; il costo di una fattura di dicembre ricevuta a gennaio sta nell'esercizio di dicembre.
"""
from decimal import Decimal

import pytest

from tests.fatture._scenari_comuni import (
    FilePdf, app_con, archivio_scenari, crea_fornitore, esegui, fattura, importa, importa_estratto, ingresso,
    parser_pdf_con, richiesta, transazione_pdf, tutti, xml_fattura,
)

__all__ = ["archivio_scenari", "ingresso"]


def _d(valore) -> Decimal:
    return Decimal(str(valore))


def _app_bilancio():
    from app.routers.accounting.bilancio import router

    return app_con((router, "/api/bilancio"))


async def _conto_economico(app, anno):
    risposta = await richiesta(app, "GET", f"/api/bilancio/conto-economico?anno={anno}")
    assert risposta.status_code == 200, risposta.text
    return risposta.json()


async def _con_personale(db, anno=2026, mese=9, lordo=1000.0):
    """Una busta con il lordo: senza, il totale dei costi e' `None` («non lo so»), non un numero."""
    await db["cedolini"].insert_one({"id": "ced-1", "anno": anno, "mese": mese, "lordo": lordo,
                                     "tipo_cedolino": "mensile", "status": "attivo"})


# ── 4. nota di credito ───────────────────────────────────────────────────────

def test_nota_di_credito_td04_scrive_l_inverso_non_e_un_costo_e_non_crea_cespiti(archivio_scenari, ingresso):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        # la fattura d'origine ha un bene strumentale (cespite); la nota di credito cita lo stesso articolo
        origine = await importa(db, xml_fattura(numero="1", imponibile="1500.00", iva="330.00", totale="1830.00",
                                                descrizione="Condizionatore split Daikin"), ingresso)
        nota = await importa(db, xml_fattura(numero="NC1", tipo="TD04", data="2026-09-12", imponibile="1500.00",
                                             iva="330.00", totale="1830.00", descrizione="Condizionatore split Daikin"),
                             ingresso, nome_file="nc.xml")
        await _con_personale(db)
        app = _app_bilancio()
        return {"origine": origine, "nota": nota, "giornale": await tutti(db, "movimenti_contabili"),
                "partite": await tutti(db, "partite_aperte"), "cespiti": await tutti(db, "cespiti"),
                "banca": await tutti(db, "prima_nota_banca"), "ce": await _conto_economico(app, 2026),
                "nota_doc": await fattura(db, nota["id"])}

    r = esegui(scenario())
    assert r["origine"]["status"] == "imported" and r["nota"]["status"] == "imported"
    per_fattura = {g["fattura_id"]: g for g in r["giornale"]}
    g_nota = per_fattura[r["nota"]["id"]]
    g_origine = per_fattura[r["origine"]["id"]]
    # l'origine e' un acquisto: il bene va a cespite (DARE), il debito ad AVERE
    assert any(x["conto_codice"] == "01.06.01" and _d(x["dare"]) == Decimal("1500.00") for x in g_origine["righe"])
    # la nota di credito scrive l'inverso della stessa operazione, quadrato, mai un cespite
    assert _d(g_nota["totale_dare"]) == _d(g_nota["totale_avere"]) == Decimal("1830.00")
    per_conto = {x["conto_codice"]: x for x in g_nota["righe"]}
    assert _d(per_conto["02.01.01"]["dare"]) == Decimal("1830.00") and _d(per_conto["02.01.01"]["avere"]) == 0
    assert _d(per_conto["01.04.01"]["avere"]) == Decimal("330.00") and _d(per_conto["01.04.01"]["dare"]) == 0
    costo = [x for c, x in per_conto.items() if c not in ("02.01.01", "01.04.01")]
    assert len(costo) == 1 and _d(costo[0]["avere"]) == Decimal("1500.00") and _d(costo[0]["dare"]) == 0
    assert "01.06.01" not in per_conto, "una nota di credito non e' mai un cespite"
    assert g_nota["idempotency_key"] == f"reg:fattura:{r['nota']['id']}"
    assert len(r["cespiti"]) == 1 and r["cespiti"][0]["fattura_id"] == r["origine"]["id"]
    # la partita e' una nota di credito col segno negativo: non e' un debito
    pa = next(p for p in r["partite"] if p["documento_id"] == r["nota"]["id"])
    assert pa["tipo"] == "nota_credito" and _d(pa["extra"]["importo_con_segno"]) == Decimal("-1830.00")
    # in Prima Nota la nota e' un'entrata provvisoria, mai una seconda uscita
    riga_nota = next(b for b in r["banca"] if b["fattura_id"] == r["nota"]["id"])
    assert riga_nota["tipo"] == "entrata" and riga_nota["provvisorio"] is True
    # conto economico: l'acquisto di 1.500,00 e la nota che lo storna si annullano, resta il solo personale
    costi = r["ce"]["costi"]
    assert _d(costi["acquisti"]) == Decimal("1500.00") and _d(costi["note_credito"]) == Decimal("1500.00")
    assert _d(costi["costi_netti"]) == Decimal("0.00")
    assert _d(costi["totale_costi"]) == Decimal("1000.00")
    assert r["ce"]["statistiche"]["num_note_credito"] == 1


# ── 6a. competenza contro pagamento ──────────────────────────────────────────

def test_f24_ritenuta_e_bonifico_pagati_non_alterano_i_costi_del_bilancio(archivio_scenari, monkeypatch):
    db = archivio_scenari
    import app.services.telegram_notifications as telegram
    from app.routers import ritenute

    async def _muto(*_a, **_k):
        return True

    monkeypatch.setattr(telegram, "send_notification", _muto)

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        await importa(db, xml_fattura(numero="P1", imponibile="1000.00", iva="220.00", totale="1220.00",
                                      ritenuta="200.00", descrizione="Consulenza"), "drive")
        await _con_personale(db)
        app = _app_bilancio()
        costi = {"inizio": (await _conto_economico(app, 2026))["costi"]}
        # il netto esce dal conto (1.020,00): paga il debito col fornitore, non e' un costo nuovo
        parser_pdf_con(monkeypatch, [
            transazione_pdf("2026-09-16", "VS.DISP. RIF. MBVT12345678/001 FAVORE FORNITORE TEST SRL", -1020.0),
            # l'F24 con il 1040 (la ritenuta) e un F24 di imposte: sono debiti verso l'Erario che si estinguono
            transazione_pdf("2026-10-16", "ADDEBITO F24 DELEGA F24 COD.1040 RITENUTE", -200.0)])
        await importa_estratto(FilePdf())
        costi["dopo_banca"] = (await _conto_economico(app, 2026))["costi"]
        riga = {"codice_tributo": "1040", "periodo_riferimento": "09/2026", "importo_debito_cents": 20000,
                "importo_credito_cents": 0}
        await db["quietanze_f24"].insert_one({
            "id": "q-1040", "data_pagamento": "2026-10-16", "protocollo_telematico": "26101612345678901/000001",
            "sezione_erario": [riga], "sezione_regioni": [], "sezione_tributi_locali": [], "sezione_inps": [],
            "totali": {"saldo_netto_cents": 20000}, "f24_associati": []})
        await ritenute.riconcilia_ritenute_esistenti(db)
        costi["dopo_f24"] = (await _conto_economico(app, 2026))["costi"]
        costi["ritenuta"] = (await tutti(db, "ritenute_acconto"))[0]
        costi["ec"] = await tutti(db, "estratto_conto_movimenti")
        return costi

    r = esegui(scenario())
    assert _d(r["inizio"]["acquisti"]) == Decimal("1000.00")
    assert _d(r["inizio"]["totale_costi"]) == Decimal("2000.00")  # 1.000 di parcella + 1.000 di personale
    # i pagamenti sono avvenuti davvero...
    assert r["ritenuta"]["stato_obbligazione"] == "VERSATA"
    assert any(m.get("categoria") == "F24" for m in r["ec"])
    assert any(m.get("riconciliato") for m in r["ec"] if _d(m["importo"]) == Decimal("1020"))
    # ...e il costo non si e' mosso di un centesimo
    assert r["dopo_banca"] == r["inizio"]
    assert r["dopo_f24"] == r["inizio"]


# ── 6b. fattura di dicembre ricevuta a gennaio ───────────────────────────────

def _dicembre_a_gennaio():
    return xml_fattura(numero="D1", data="2026-12-28", descrizione="Farina 00")


def test_fattura_di_dicembre_ricevuta_a_gennaio_ha_l_iva_di_gennaio_mai_retroattribuita(archivio_scenari):
    db = archivio_scenari
    from app.services.handlers.fattura_handlers import on_fattura_created_iva

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, _dicembre_a_gennaio(), "drive")
        await db["invoices"].update_one({"id": esito["id"]}, {"$set": {"data_ricezione": "2027-01-05"}})
        await on_fattura_created_iva({"fattura_id": esito["id"]}, db)
        return await fattura(db, esito["id"]), (await tutti(db, "movimenti_contabili"))[0]

    f, g = esegui(scenario())
    assert f["periodo_iva_attribuito"] == "2027-01" and f["regola_iva_applicata"] == "OPERAZIONE_ANNO_PRECEDENTE"
    # il giornale registra l'operazione nell'esercizio di dicembre (competenza = data documento)
    assert g["anno"] == 2026 and g["data_competenza"] == "2026-12-28"


@pytest.mark.xfail(strict=True, reason=(
    "DIFETTO NOTO, NON CORRETTO (CLAUDE.md «Aperto: Bilancio e competenza»): `/api/bilancio/conto-economico` "
    "(e `conto-economico-dettagliato`) seleziona le fatture per data documento OPPURE data ricezione e ignora "
    "`data_competenza`: una fattura di dicembre ricevuta a gennaio compare in tutti e due gli esercizi. "
    "Il criterio e' ripetuto in sei punti di `bilancio.py` e in `finanziaria.py` con un altro ripiego: "
    "correggerlo in un posto solo lascerebbe i conti in disaccordo fra loro."))
def test_fattura_di_dicembre_ricevuta_a_gennaio_costa_solo_nell_esercizio_di_dicembre(archivio_scenari):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, _dicembre_a_gennaio(), "drive")
        await db["invoices"].update_one({"id": esito["id"]}, {"$set": {"data_ricezione": "2027-01-05"}})
        app = _app_bilancio()
        return await _conto_economico(app, 2026), await _conto_economico(app, 2027)

    ce_2026, ce_2027 = esegui(scenario())
    assert _d(ce_2026["costi"]["acquisti"]) == Decimal("100.00")
    assert _d(ce_2027["costi"]["acquisti"]) == Decimal("0.00"), "il costo e' stato contato anche nel 2027"
