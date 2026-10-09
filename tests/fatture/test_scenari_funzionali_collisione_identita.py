"""Stessa chiave contabile, due ingressi, una sola decisione (`decidi_stessa_chiave`).

Fino al 02/10/2026 Documenti > Import rispondeva «Fattura duplicata» a un XML con
numero, fornitore e data gia' in archivio anche se il contenuto era un altro: la
seconda copia spariva in silenzio, mentre dal giro Drive entrava «da verificare»
con l'alert. Ora i due ingressi fanno la stessa cosa:

* stesso contenuto (impronta canonica) → gia' presente, `nuovi = 0`, nessun alert;
* contenuto diverso → collisione: copia in archivio con `status` non archiviato,
  `stato_import` di collisione, derivati bloccati, alert; la prima resta intatta.
"""
from tests.fatture._scenari_comuni import (  # noqa: F401 - fixture pytest
    archivio_scenari, crea_fornitore, esegui, importa, ingresso, tutti, xml_fattura,
)

ALERT = "FATTURA_IDENTITA_DA_VERIFICARE"


def test_stesso_contenuto_da_entrambi_gli_ingressi_e_gia_presente(archivio_scenari, ingresso):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        originale = xml_fattura()
        rimaneggiato = b"\xef\xbb\xbf" + originale.replace(b"\n", b"\r\n")  # BOM + a capo Windows
        primo = await importa(db, originale, ingresso)
        secondo = await importa(db, rimaneggiato, ingresso, nome_file="stessa (1).xml")
        terzo = await importa(db, originale, ingresso, nome_file="stessa (2).xml")
        return primo, secondo, terzo, await tutti(db, "invoices"), await tutti(db, "alerts", {"codice": ALERT})

    primo, secondo, terzo, fatture, alert = esegui(scenario())
    assert primo["status"] == "imported"
    assert secondo["status"] == "duplicate" and terzo["status"] == "duplicate"
    assert len(fatture) == 1 and alert == []
    assert fatture[0]["content_hash_canonico"] and fatture[0]["duplicate_review_required"] is False


def test_contenuto_diverso_da_entrambi_gli_ingressi_e_una_collisione_con_alert(archivio_scenari, ingresso):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        prima = await importa(db, xml_fattura(descrizione="Farina 00"), ingresso)
        seconda = await importa(db, xml_fattura(descrizione="Zucchero"), ingresso, nome_file="altra.xml")
        return {"prima": prima, "seconda": seconda, "fatture": {f["id"]: f for f in await tutti(db, "invoices")},
                "partite": await tutti(db, "partite_aperte"), "giornale": await tutti(db, "movimenti_contabili"),
                "banca": await tutti(db, "prima_nota_banca"), "alert": await tutti(db, "alerts", {"codice": ALERT})}

    r = esegui(scenario())
    assert r["prima"]["status"] == "imported" and r["seconda"]["status"] == "imported", r["seconda"]
    assert len(r["fatture"]) == 2
    f1, f2 = r["fatture"][r["prima"]["id"]], r["fatture"][r["seconda"]["id"]]
    assert f1["status"] == "imported" and f1["duplicate_review_required"] is True
    assert f1["identity_collision_with_ids"] == [f2["id"]]
    assert f2["status"] == "da_verificare"
    assert f2["stato_import"] == "collisione_identita_da_verificare"
    assert f2["stato_derivati"] == "bloccato_collisione_identita"
    assert f2["identity_collision_with_ids"] == [f1["id"]]
    # nessun effetto contabile per la copia in collisione
    assert [p["documento_id"] for p in r["partite"]] == [f1["id"]]
    assert [g["fattura_id"] for g in r["giornale"]] == [f1["id"]]
    assert [b["fattura_id"] for b in r["banca"]] == [f1["id"]]
    assert len(r["alert"]) == 1 and r["alert"][0]["entita_id"] == f2["id"]
    if ingresso == "documenti":
        assert r["seconda"]["grezzo"]["collisione_identita"] == 1
        assert "da verificare" in r["seconda"]["grezzo"]["message"]
