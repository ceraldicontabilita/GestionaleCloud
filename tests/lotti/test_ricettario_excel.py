import asyncio
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import ricette as mod
from app.lotti.routers.prodotti_vendita import ProdottoVendita

_TEST_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_TEST_LOOP)


def run(coro):
    return _TEST_LOOP.run_until_complete(coro)


def _bundle_minimo():
    return {
        "meta": {
            "bundle_sha256": "bundle-test",
            "sources": [{"file": f"fonte-{i}.xlsx"} for i in range(4)],
            "con_ingredienti": 2,
            "con_preparazione": 2,
        },
        "recipes": [
            {
                "chiave": "baba",
                "nome": "Babà",
                "reparto_hint": "pasticceria",
                "porzioni": 20,
                "ingredienti_dettaglio": [
                    {"nome": "Farina Manitoba", "quantita": 1000, "unita_misura": "g"},
                    {"nome": "Uova", "quantita": 12, "unita_misura": "pz"},
                ],
                "procedimento_testo": "Impastare e lasciare lievitare.",
                "note": "Ricetta laboratorio",
                "fonti_excel": [{"file": "fonte-1.xlsx", "sheet": "Babà", "row": 1}],
            },
            {
                "chiave": "savoiardi",
                "nome": "Savoiardi",
                "reparto_hint": "pasticceria",
                "porzioni": 30,
                "ingredienti_dettaglio": [
                    {"nome": "Albumi", "quantita": 180, "unita_misura": "g"},
                ],
                "procedimento_testo": "Montare e cuocere.",
                "note": "",
                "fonti_excel": [{"file": "fonte-2.xlsx", "sheet": "Savoiardi", "row": 1}],
            },
        ],
    }


def test_bundle_reale_contiene_le_quattro_fonti_e_le_preparazioni():
    bundle = mod._carica_ricettario_excel()
    assert len(bundle["meta"]["sources"]) == 4
    assert bundle["meta"]["ricette_uniche"] == 574
    assert bundle["meta"]["con_ingredienti"] == 535
    assert bundle["meta"]["con_preparazione"] == 306
    assert len(bundle["recipes"]) == 574


def test_import_idempotente_e_non_sovrascrive_ingredienti_manualizzati(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    monkeypatch.setattr(mod, "_carica_ricettario_excel", _bundle_minimo)

    async def scenario():
        await database.ricette.insert_one({
            "id": "manuale-baba",
            "nome": "Babà",
            "fonte": "manuale",
            "ingredienti": ["Farina personale"],
            "ingredienti_dettaglio": [
                {"nome": "Farina personale", "quantita": 777, "unita_misura": "g"},
            ],
            "porzioni": 10,
        })
        first = await mod._importa_ricettario_excel(False, {"nome": "Admin"})
        second = await mod._importa_ricettario_excel(False, {"nome": "Admin"})
        baba = await database.ricette.find_one({"id": "manuale-baba"}, {"_id": 0})
        savoiardi = await database.ricette.find_one({"nome": "Savoiardi"}, {"_id": 0})
        backups = await database.ricette_import_backup.count_documents({})
        return first, second, baba, savoiardi, backups

    first, second, baba, savoiardi, backups = run(scenario())
    assert first["create"] == 1
    assert first["aggiornate"] == 1
    assert second["create"] == 0
    assert second["aggiornate"] == 0
    assert second["invariate"] == 2
    assert baba["ingredienti_dettaglio"][0]["nome"] == "Farina personale"
    assert baba["procedimento_testo"] == "Impastare e lasciare lievitare."
    assert savoiardi["ingredienti_dettaglio"][0]["quantita"] == 180
    assert backups == 1


def test_eliminazione_salva_copia_recuperabile(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.ricette.insert_one({"id": "r1", "nome": "Ricetta prova", "foto_url": "/foto.jpg"})
        result = await mod.delete_ricetta("r1", {"nome": "Admin"})
        live = await database.ricette.find_one({"id": "r1"})
        trash = await database.ricette_cestino.find_one({"ricetta_id": "r1"}, {"_id": 0})
        return result, live, trash

    result, live, trash = run(scenario())
    assert result["recuperabile"] is True
    assert live is None
    assert trash["ricetta"]["foto_url"] == "/foto.jpg"
    assert trash["eliminata_da"] == "Admin"
    assert trash["motivo"] == "eliminazione manuale dall'elenco ricette"


def test_cestino_ripristina_stesso_id_e_secondo_tentativo_non_duplica(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.ricette.insert_one({
            "id": "r1", "nome": "Ricetta prova", "foto_url": "/api/foto/originale",
            "procedimento_testo": "Procedimento operativo", "ingredienti_dettaglio": [{"nome": "Farina"}],
        })
        await mod.delete_ricetta("r1", {"nome": "Admin"})
        cestino = await mod.get_ricette_cestino({"nome": "Admin"})
        prima = await mod.restore_ricetta(cestino[0]["id"], {"nome": "Admin"})
        seconda = await mod.restore_ricetta(cestino[0]["id"], {"nome": "Admin"})
        ricetta = await database.ricette.find_one({"id": "r1"}, {"_id": 0})
        voce = await database.ricette_cestino.find_one({"id": cestino[0]["id"]}, {"_id": 0})
        return cestino, prima, seconda, ricetta, voce, await database.ricette.count_documents({})

    cestino, prima, seconda, ricetta, voce, totale = run(scenario())
    assert len(cestino) == 1
    assert cestino[0]["nome"] == "Ricetta prova"
    assert prima["id"] == seconda["id"] == "r1"
    assert prima["ripristinata"] is True
    assert seconda["ripristinata"] is False
    assert totale == 1
    assert ricetta["foto_url"] == "/api/foto/originale"
    assert ricetta["procedimento_testo"] == "Procedimento operativo"
    assert voce["ripristinata_da"] == "Admin"
    assert run(mod.get_ricette_cestino({"nome": "Admin"})) == []


def test_ripristino_variante_senza_base_conserva_la_copia_nel_cestino(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.ricette_cestino.insert_one({
            "id": "voce-1", "ricetta_id": "variante", "motivo": "eliminazione manuale",
            "ricetta": {"id": "variante", "nome": "Variante", "ricetta_base_id": "base"},
        })
        with pytest.raises(HTTPException) as errore:
            await mod.restore_ricetta("voce-1", {"nome": "Admin"})
        return errore.value, await database.ricette.count_documents({}), await database.ricette_cestino.count_documents({})

    errore, ricette, copie = run(scenario())
    assert errore.status_code == 409
    assert ricette == 0
    assert copie == 1


def test_eliminazione_base_con_varianti_non_orfana_le_varianti(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.ricette.insert_many([
            {"id": "base", "nome": "Arancino base"},
            {"id": "variante", "nome": "Arancino ai funghi", "ricetta_base_id": "base"},
        ])
        with pytest.raises(HTTPException) as errore:
            await mod.delete_ricetta("base", {"nome": "Admin"})
        return errore.value, await database.ricette.find_one({"id": "base"}), await database.ricette.find_one({"id": "variante"})

    errore, base, variante = run(scenario())
    assert errore.status_code == 409
    assert errore.detail["varianti"] == [{"id": "variante", "nome": "Arancino ai funghi"}]
    assert base is not None
    assert variante["ricetta_base_id"] == "base"


def test_prodotto_acquistato_non_ritorna_nelle_ricette_al_reimport(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    monkeypatch.setattr(mod, "_carica_ricettario_excel", _bundle_minimo)

    async def scenario():
        await database.prodotti_vendita.insert_one({
            "id": "prodotto-baba", "nome": "Babà", "fonte": "ricettario_excel_ceraldi",
            "fonte_ricettario_excel_chiave": "baba",
        })
        result = await mod._importa_ricettario_excel(False, {"nome": "Admin"})
        return result, await database.ricette.find_one({"nome": "Babà"})

    result, ricetta = run(scenario())
    assert result["create"] == 1  # Savoiardi resta una ricetta vera
    assert ricetta is None


def test_prodotto_acquistato_conserva_fonte_e_foto():
    prodotto = ProdottoVendita(
        nome="Aranciata", categoria="Bevande", fonte="acquistato",
        fonte_ricettario_excel_chiave="aranciata",
        fonti_excel=[{"file": "Ricettario_Completo_v6.xlsx", "row": 114}],
        immagine_url="/api/foto/foto-originale",
        visibile_ricette=False,
    )
    salvato = prodotto.model_dump()
    assert salvato["fonte_ricettario_excel_chiave"] == "aranciata"
    assert salvato["fonti_excel"][0]["row"] == 114
    assert salvato["immagine_url"] == "/api/foto/foto-originale"
    assert salvato["visibile_ricette"] is False


def test_prodotto_acquistato_scompare_dalle_due_proiezioni_del_ricettario(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    monkeypatch.setattr(mod, "_carica_archivio_dolce", lambda: {
        "meta": {}, "recipes": [{"id": "arch-1", "name": "Aranciata"}], "components": [],
    })

    async def scenario():
        await database.prodotti_vendita.insert_one({
            "id": "bevanda-1", "nome": "Aranciata",
            "fonte_ricettario_excel_chiave": "aranciata",
        })
        await database.ricette.insert_one({"id": "ric-1", "nome": "Aranciata"})
        operative = await mod.get_ricette(search=None)
        unificate = await mod.get_ricette_unificate(search=None)
        archivio = await mod.get_ricette_archivio()
        return operative, unificate, archivio

    operative, unificate, archivio = run(scenario())
    assert operative == []
    assert not any(r.get("nome") == "Aranciata" for r in unificate)
    assert archivio["recipes"] == []


def test_variante_arancini_identica_confluisce_nella_base_senza_perdere_fonti():
    bundle = mod._carica_ricettario_excel()
    canoniche = mod._ricette_excel_canoniche(bundle["recipes"])
    arancini = [r for r in canoniche if r["nome"].lower().startswith("arancini di riso")]
    assert len(arancini) == 2
    base = next(r for r in arancini if r["nome"] == "arancini di riso (base)")
    variante = next(r for r in arancini if "funghi e provola" in r["nome"])
    assert {f["row"] for f in base["fonti_excel"]} == {4, 19}
    assert {f["row"] for f in variante["fonti_excel"]} == {34}
    assert variante["ingredienti_dettaglio"] != base["ingredienti_dettaglio"]


def test_import_mirato_collega_variante_diversa_alla_base(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    base_id = "base-arancini"
    chiave = "arancini di riso funghi e provola variante di arancini di riso"

    async def scenario():
        await database.ricette.insert_one({"id": base_id, "nome": "arancini di riso (base)"})
        esito = await mod._importa_ricettario_excel(False, {"nome": "Admin"}, chiave=chiave)
        variante = await database.ricette.find_one({"nome": {
            "$regex": "^arancini di riso funghi e provola"
        }})
        return esito, variante

    esito, variante = run(scenario())
    assert esito["create"] == 1
    assert esito["duplicati_unificati"] >= 1
    assert variante["ricetta_base_id"] == base_id
