"""Identificazione col web delle righe del Dizionario senza categoria (client Anthropic finto)."""
import asyncio
import json

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import lettura_articoli_ai as la


def run(coro):
    return asyncio.run(coro)


class Risposta:
    def __init__(self, status, corpo):
        self.status_code, self._corpo = status, corpo

    def json(self):
        return self._corpo


class ClientFinto:
    """Un ``LlmChat`` finto: risponde in ordine e registra gli invii (prompt e usi del tool)."""

    def __init__(self, *risposte):
        self.risposte, self.invii = list(risposte), []

    async def cerca_sul_web(self, prompt, *, max_tokens=1500, max_uses=3):
        from app.services.anthropic_llm_client import fonti_web_dei_blocchi, testo_dei_blocchi

        self.invii.append({"prompt": prompt, "max_uses": max_uses, "max_tokens": max_tokens})
        r = self.risposte.pop(0)
        if r.status_code != 200:
            raise RuntimeError(str((r.json().get("error") or {}).get("message", r.status_code)))
        blocchi = r.json()["content"]
        return {"testo": testo_dei_blocchi(blocchi), "fonti": fonti_web_dei_blocchi(blocchi)}


def web(oggetto, fonti=("https://www.produttore.it/p",)):
    return Risposta(200, {"content": [
        {"type": "web_search_tool_result", "content": [{"type": "web_search_result", "url": u} for u in fonti]},
        {"type": "text", "text": "Ecco: " + json.dumps(oggetto)},
    ]})


@pytest.fixture(autouse=True)
def chiave(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chiave-di-prova")


def riga(i, nome, **extra):
    return {"id": i, "nome_originale": nome, "fornitore": "BIG FOOD SRL", **extra}


def prepara(db, *righe):
    run(db.dizionario_prodotti.insert_many(list(righe)))


def leggi(db, i):
    return run(db.dizionario_prodotti.find_one({"id": i}, {"_id": 0}))


def test_concordi_si_associa_e_si_dichiara():
    db = AsyncMongoMockClient()["T"]
    prepara(db, riga("1", "BUONDÌ GR.198 CLASSICO X6", categoria_canonica="Varie Alimentari"))
    client = ClientFinto(web({"marca": "Motta", "prodotto": "Buondì classico", "formato": "198 g",
                              "categoria": "Varie Alimentari", "confidenza": "alta", "motivo": ""}))
    e = run(la.identifica_col_web(db, client=client))
    assert e["associate"] == 1 and e["errori"] == 0
    d = leggi(db, "1")
    assert d["categoria_fonte"] == "web" and d["abbinato_ai"] is True
    assert d["categoria_web_fonti"] == ["https://www.produttore.it/p"]
    # stessa chiamata di schede_tecniche: strumento server-side del client unico, nessun secondo client
    invio = client.invii[0]
    assert invio["max_uses"] == la.WEB_MAX_USES
    assert "Pasta" in invio["prompt"]  # l'elenco ufficiale delle categorie


def test_secondo_giro_nessuna_nuova_ricerca():
    db = AsyncMongoMockClient()["T"]
    prepara(db, riga("1", "FONZIES BUSTONE GR.188  8 BUSTE", categoria_canonica="Varie Alimentari"))
    ok = web({"marca": "Fonzies", "prodotto": "Fonzies", "categoria": "Varie Alimentari", "confidenza": "alta"})
    run(la.identifica_col_web(db, client=ClientFinto(ok)))
    secondo = ClientFinto()
    e = run(la.identifica_col_web(db, client=secondo))
    assert e["cercate"] == 0 and secondo.invii == []


def test_non_concordi_diventa_proposta_non_associazione():
    db = AsyncMongoMockClient()["T"]
    prepara(db, riga("1", "MIX GOLDEN NOW DA KG 15 (4644)", categoria_canonica="Varie Alimentari"))
    client = ClientFinto(web({"marca": "Zeta", "prodotto": "Preparato per pane", "categoria": "Semilavorati Pasticceria",
                              "confidenza": "alta"}))
    e = run(la.identifica_col_web(db, client=client))
    assert e["associate"] == 0 and e["proposte"] == 1
    assert leggi(db, "1")["categoria_canonica"] == "Varie Alimentari"
    p = run(db.nome_mapping.find_one({"fonte": "web"}, {"_id": 0}))
    assert p["confermato"] is False and p["categoria"] == "Semilavorati Pasticceria"
    assert p["fonte_url"] == "https://www.produttore.it/p"


def test_senza_fonte_o_confidenza_bassa_non_associa():
    for oggetto, fonti in (({"marca": "Fonzies", "prodotto": "Fonzies", "categoria": "Varie Alimentari",
                             "confidenza": "alta"}, ()),
                           ({"marca": "Fonzies", "prodotto": "Fonzies", "categoria": "Varie Alimentari",
                             "confidenza": "media"}, ("https://x.it",))):
        db = AsyncMongoMockClient()["T"]
        prepara(db, riga("1", "FONZIES BUSTONE GR.188", categoria_canonica="Varie Alimentari"))
        e = run(la.identifica_col_web(db, client=ClientFinto(web(oggetto, fonti))))
        assert e["associate"] == 0
        assert leggi(db, "1").get("categoria_fonte") is None


def test_categoria_inventata_o_null_mai_scritta_e_motivo_salvato():
    db = AsyncMongoMockClient()["T"]
    prepara(db, riga("1", "IMETTE   GR.200       YMA"), riga("2", "ESSENZA NEROLY BIGARADE GR 80"))
    client = ClientFinto(
        web({"marca": "Yma", "prodotto": "Imette", "categoria": "Golosita", "confidenza": "alta"}),
        web({"marca": "", "prodotto": "", "categoria": None, "confidenza": "bassa", "motivo": "nessun risultato"}),
    )
    e = run(la.identifica_col_web(db, client=client))
    assert e["associate"] == 0 and e["non_identificate"] == 2
    assert "fuori elenco" in leggi(db, "1")["web_motivo"]
    assert leggi(db, "2")["web_motivo"] == "nessun risultato"
    assert leggi(db, "1").get("categoria_canonica") is None


def test_contrasto_con_categoria_dal_nome_non_associa():
    assert la.decidi_associazione(
        {"categoria": "Zuccheri", "confidenza": "alta", "concorda": True, "prodotto": "x"},
        ["https://x.it"], "OLIO SEMI GIRASOLE") == "proposta"


def test_ean_nella_descrizione_basta_a_concordare():
    ident = la.valida_identificazione({"marca": "Xyz", "prodotto": "Abc", "categoria": "Pasta", "ean": "8001234567890",
                                       "confidenza": "alta"}, "ART 8001234567890 CRT")
    assert ident["concorda"] is True


def test_manuale_bevande_ed_esclusi_non_si_cercano():
    db = AsyncMongoMockClient()["T"]
    prepara(db, riga("1", "FONZIES BUSTONE", categoria_fonte="manuale"),
            riga("2", "TOURTEL CL.33X3"), riga("3", "FONZIES SNACK", escluso_ricette=True))
    client = ClientFinto()
    assert run(la.identifica_col_web(db, client=client))["cercate"] == 0 and client.invii == []


def test_errore_api_non_marca_la_riga_e_ferma_il_giro():
    db = AsyncMongoMockClient()["T"]
    prepara(db, riga("1", "FONZIES BUSTONE"), riga("2", "MAIS BONDUELLE GR.300X12"))
    client = ClientFinto(Risposta(529, {"error": {"message": "overloaded"}}))
    e = run(la.identifica_col_web(db, client=client))
    assert e["errori"] == 1 and "RicercaWebErrore" in e["ultimo_errore"] and len(client.invii) == 1
    assert leggi(db, "1").get("web_cercato_at") is None


def test_tetto_giornaliero_e_lotto():
    db = AsyncMongoMockClient()["T"]
    prepara(db, *[riga(str(i), f"PRODOTTO STRANO N{i} ZZZ") for i in range(8)])
    non_noto = {"categoria": None, "confidenza": "bassa", "motivo": "?"}
    client = ClientFinto(*[web(non_noto) for _ in range(8)])
    assert run(la.identifica_col_web(db, client=client))["cercate"] == la.WEB_PER_GIRO
    run(la._stato_web(db, giorno=la._oggi_roma(), chiamate=la.TETTO_WEB_GIORNALIERO))
    e = run(la.identifica_col_web(db, client=ClientFinto()))
    assert e["cercate"] == 0 and e["motivo"] == "tetto giornaliero raggiunto"


def test_proposta_non_tocca_mapping_confermato_o_appreso():
    db = AsyncMongoMockClient()["T"]
    prepara(db, riga("1", "MIX GOLDEN NOW DA KG 15"))
    run(db.nome_mapping.insert_one({"descrizione_key": "mix golden now da kg 15", "nome_canc": "Mix pane",
                                    "fonte": "appreso"}))
    client = ClientFinto(web({"marca": "Zeta", "prodotto": "Preparato", "categoria": "Varie Alimentari",
                              "confidenza": "media"}))
    run(la.identifica_col_web(db, client=client))
    assert run(db.nome_mapping.count_documents({})) == 1
    assert run(db.nome_mapping.find_one({}, {"_id": 0}))["nome_canc"] == "Mix pane"
