"""Enable Banking: lettura, sessione cifrata, anteprima e import prudente."""
import asyncio
from decimal import Decimal

import httpx
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from mongomock_motor import AsyncMongoMockClient

from app.services import enable_banking as eb


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def configurazione(monkeypatch):
    chiave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = chiave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                               serialization.NoEncryption()).decode()
    monkeypatch.setenv("ENABLE_BANKING_APPLICATION_ID", "app-di-prova")
    monkeypatch.setenv("ENABLE_BANKING_PRIVATE_KEY_PEM", pem)
    monkeypatch.setenv("ENABLE_BANKING_ENABLED", "true")
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    from app.utils import crypto
    crypto._get_fernet.cache_clear()
    yield
    crypto._get_fernet.cache_clear()


def _tx(data, importo, dbit, testo, ref=None, stato="BOOK"):
    return {"status": stato, "booking_date": data, "value_date": data,
            "credit_debit_indicator": "DBIT" if dbit else "CRDT",
            "transaction_amount": {"currency": "EUR", "amount": importo},
            "remittance_information": [testo], "entry_reference": ref}


class Banca:
    """Enable Banking finta: due pagine di movimenti, poi fine."""

    def __init__(self, pagine=None, errori=None):
        self.pagine = pagine or []
        self.errori = list(errori or [])
        self.chiamate = []

    async def get(self, url, headers=None, params=None):
        self.chiamate.append(("GET", url, params))
        if url.endswith("/aspsps"):
            return httpx.Response(200, json={"aspsps": [{"name": "Banco BPM - Corporate", "country": "IT"}]})
        if self.errori:
            return self.errori.pop(0)
        indice = int((params or {}).get("continuation_key") or 0)
        corpo = {"transactions": self.pagine[indice]}
        if indice + 1 < len(self.pagine):
            corpo["continuation_key"] = str(indice + 1)
        return httpx.Response(200, json=corpo)

    async def post(self, url, headers=None, json=None):
        self.chiamate.append(("POST", url, json))
        if url.endswith("/auth"):
            self.state = json["state"]
            return httpx.Response(200, json={"url": "https://banca.example/autorizza"})
        if url.endswith("/sessions"):
            return httpx.Response(200, json={
                "session_id": "sessione-segreta-123",
                "accounts": [{"uid": "uid-1", "name": "false", "account_id": {"iban": "IT60X0542811101000000123456"}}],
                "access": {"valid_until": "2026-12-22T10:00:00+00:00"},
            })
        return httpx.Response(400, json={})


async def _niente(_):
    return None


def test_normalizza_decimal_con_segno_e_impronta():
    mov = eb.normalizza_api(_tx("2026-09-01", "12.5", True, "PAGAMENTO POS"), "IT60****3456", "t")
    assert mov["importo"] == Decimal("-12.50") and mov["tipo"] == "uscita"
    assert len(mov["hash_fonte"]) == 64 and mov["fonte"] == "enable_banking"
    assert eb.normalizza_api({"transaction_amount": {}}, "c", "t") is None
    assert eb.maschera_iban("IT60X0542811101000000123456") == "IT60****3456"


def test_paginazione_solo_book_e_errori():
    banca = Banca(pagine=[[_tx("2026-09-01", "1", True, "A"), _tx("2026-09-01", "2", True, "B", stato="PDNG")],
                          [_tx("2026-09-02", "3", False, "C")]])
    esito = run(eb.leggi_transazioni(banca, "https://x/transactions", headers=dict,
                                     date_from="2026-09-01", attendi=_niente))
    assert esito["pagine"] == 2 and len(esito["movimenti"]) == 2
    assert esito["altri_stati"] == {"PDNG": 1}

    limite = Banca(errori=[httpx.Response(429, json={"error": "ASPSP_RATE_LIMIT_EXCEEDED"})])
    with pytest.raises(eb.ErroreLettura) as exc:
        run(eb.leggi_transazioni(limite, "u", headers=dict, date_from="x", attendi=_niente))
    assert exc.value.stato == "limite_banca"
    assert len(limite.chiamate) == 1  # il limite della banca non si riprova

    temporaneo = Banca(pagine=[[]], errori=[httpx.Response(503, json={}), httpx.Response(503, json={})])
    esito = run(eb.leggi_transazioni(temporaneo, "u", headers=dict, date_from="x", attendi=_niente))
    assert esito["pagine"] == 1 and len(temporaneo.chiamate) == 3

    assert eb.classifica_errore(401, {}) == "consenso_scaduto"


def test_collegamento_salva_solo_session_id_cifrato_e_state_monouso():
    db = AsyncMongoMockClient()["t"]
    banca = Banca()
    url = run(eb.avvia_collegamento(db, banca))
    assert url == "https://banca.example/autorizza"
    with pytest.raises(eb.ErroreLettura):
        run(eb.completa_collegamento(db, banca, code="c", state="state-inventato"))
    stato = run(eb.completa_collegamento(db, banca, code="c", state=banca.state))
    assert stato["collegata"] and stato["valida_fino"].startswith("2026-12-22")
    assert stato["conti"] == [{"iban_mascherato": "IT60****3456", "nome": ""}]
    grezzo = run(db.sistema_stato.find_one({"chiave": eb.CHIAVE_SESSIONE}))
    assert "sessione-segreta-123" not in str(grezzo)
    assert run(eb._sessione_privata(db))["session_id"] == "sessione-segreta-123"
    # lo state e' monouso
    with pytest.raises(eb.ErroreLettura):
        run(eb.completa_collegamento(db, banca, code="c", state=banca.state))


def test_sessione_non_decifrabile_fallisce_chiusa():
    db = AsyncMongoMockClient()["t"]
    run(db.sistema_stato.insert_one({"chiave": eb.CHIAVE_SESSIONE, "session_id_cifrato": "in-chiaro"}))
    assert run(eb._sessione_privata(db)) is None


def test_anteprima_col_motore_dei_doppioni_e_nessuna_scrittura():
    db = AsyncMongoMockClient()["t"]
    banca = Banca()
    run(eb.avvia_collegamento(db, banca))
    run(eb.completa_collegamento(db, banca, code="c", state=banca.state))
    oggi = __import__("datetime").date.today().isoformat()
    banca.pagine = [[
        _tx(oggi, "34.90", True, "VS.DISP. RIF. MB0B45447123/90489167 FAVORE COMUNE DI NAPOLI"),
        _tx(oggi, "10.00", True, "COMMISSIONI"),
        _tx(oggi, "5.00", False, "ACCREDITO NUOVO"),
    ]]
    run(db.estratto_conto_movimenti.insert_many([
        {"id": "a", "data": oggi, "importo": -34.9, "tipo": "uscita", "banca": "Banco BPM",
         "descrizione": "BONIFICO - VS.DISP. RIF. MB0B45447123/90489167 COMUNE DI NAPOLI"},
        {"id": "b", "data": oggi, "importo": -10.0, "tipo": "uscita", "banca": "Banco BPM",
         "descrizione": "SPESE TENUTA CONTO"},
    ]))
    prima = run(db.estratto_conto_movimenti.count_documents({}))
    esito = run(eb.anteprima(db, banca, giorni=5))
    assert esito["dry_run"] is True
    assert esito["conteggi"] == {"letti": 3, "nuovi": 1, "gia_presenti": 2, "da_verificare": 0}
    assert esito["nuovi"][0]["descrizione_originale"] == "ACCREDITO NUOVO"
    assert run(db.estratto_conto_movimenti.count_documents({})) == prima


def test_importa_solo_nuovi_esclude_dubbi_ed_e_idempotente():
    db = AsyncMongoMockClient()["t"]
    banca = Banca()
    run(eb.avvia_collegamento(db, banca))
    run(eb.completa_collegamento(db, banca, code="c", state=banca.state))
    oggi = __import__("datetime").date.today().isoformat()
    banca.pagine = [[
        _tx(oggi, "10.00", True, "COMMISSIONI"),
        _tx(oggi, "5.00", False, "ACCREDITO NUOVO", ref="RIFNUOVO123"),
    ]]
    run(db.estratto_conto_movimenti.insert_one({
        "id": "esistente", "data": oggi, "importo": 10.0, "tipo": "uscita",
        "banca": "Banco BPM", "descrizione": "SPESE TENUTA CONTO",
    }))

    primo = run(eb.importa_nuovi(db, banca, giorni=5))
    assert primo["importati"] == 1
    assert primo["gia_presenti"] == 1 and primo["da_verificare_esclusi"] == 0
    importato = run(db.estratto_conto_movimenti.find_one({"fonte": "enable_banking"}))
    assert importato["descrizione_originale"] == "ACCREDITO NUOVO"
    assert importato["livello_evidenza"] == "provvisoria"
    assert importato["in_attesa_estratto_ufficiale"] is True

    secondo = run(eb.importa_nuovi(db, banca, giorni=5))
    assert secondo["importati"] == 0
    assert run(db.estratto_conto_movimenti.count_documents({"fonte": "enable_banking"})) == 1


def test_flag_spento_per_default(monkeypatch):
    monkeypatch.delenv("ENABLE_BANKING_ENABLED")
    assert eb.attivo() is False


def test_rotte_riservate_all_admin_tranne_il_ritorno_dalla_banca():
    from app.middleware.authentication import PUBLIC_PATHS
    from app.routers.bank import enable_banking as router_eb
    from app.utils.ruoli import richiedi_admin

    per_percorso = {r.path: r for r in router_eb.router.routes}
    for percorso in ("/stato", "/collega", "/anteprima", "/importa"):
        dipendenze = [d.call for d in per_percorso[percorso].dependant.dependencies]
        assert richiedi_admin in dipendenze, percorso
    assert "/api/banca/enable-banking/callback" in PUBLIC_PATHS
    assert not any(p.startswith("/api/banca/enable-banking/") and not p.endswith("/callback")
                   for p in PUBLIC_PATHS)


def test_giro_automatico_importa_i_nuovi_e_lascia_l_esito():
    db = AsyncMongoMockClient()["t"]
    banca = Banca()
    oggi = __import__("datetime").date.today().isoformat()

    # non collegato: salta e lo scrive
    esito = run(eb.giro_automatico(db, banca))
    assert esito["saltato"] == "non_collegato"

    run(eb.avvia_collegamento(db, banca))
    run(eb.completa_collegamento(db, banca, code="c", state=banca.state))
    banca.pagine = [[_tx(oggi, "5.00", False, "ACCREDITO NUOVO", ref="RIFNUOVO123")]]
    primo = run(eb.giro_automatico(db, banca))
    assert primo["importati"] == 1 and primo["giorni"] == eb.GIORNI_PRIMO_GIRO
    stato = run(eb.leggi_sessione(db))
    assert stato["giro_automatico"]["importati"] == 1
    assert "session_id" not in str(stato)

    secondo = run(eb.giro_automatico(db, banca))
    assert secondo["importati"] == 0 and secondo["giorni"] == eb.GIORNI_GIRO
    assert run(db.estratto_conto_movimenti.count_documents({"fonte": "enable_banking"})) == 1


def test_giro_automatico_limite_della_banca_non_rompe(monkeypatch):
    db = AsyncMongoMockClient()["t"]
    banca = Banca()
    run(eb.avvia_collegamento(db, banca))
    run(eb.completa_collegamento(db, banca, code="c", state=banca.state))
    banca.errori = [httpx.Response(429, json={"error": "ASPSP_RATE_LIMIT_EXCEEDED"})]
    esito = run(eb.giro_automatico(db, banca))
    assert esito["errore"] == "limite_banca"
    assert run(eb.leggi_sessione(db))["giro_automatico"]["errore"] == "limite_banca"


# ── stesso conto, parole diverse (26/09/2026: 41 «non importati» gia' in archivio)

def _a(id_, data, importo, tipo, testo):
    return {"id": id_, "data": data, "importo": importo, "tipo": tipo,
            "banca": "Banco BPM", "descrizione": testo}


def _b(data, importo, tipo, testo):
    return {"data": data, "importo": importo if tipo == "entrata" else -importo,
            "tipo": tipo, "descrizione_originale": testo}


def test_parole_diverse_stesso_giorno_e_importo_sono_gia_presenti():
    archivio = [_a("L1", "2026-07-10", 4600.0, "entrata", "VERSAMENTO CONTANTI"),
                _a("L2", "2026-07-11", 1.1, "uscita", "COMM. SU BONIFICO")]
    api = [_b("2026-07-10", 4600.0, "entrata", "VERS. CONTANTI"),
           _b("2026-07-11", 1.1, "uscita", "COMMISSIONI - COMMISSIONI SU BONIFICI")]
    esito = eb.confronta_con_archivio(api, archivio)
    assert len(esito["gia_presenti"]) == 2
    assert esito["da_verificare"] == [] and esito["nuovi"] == []


def test_il_secondo_movimento_uguale_dello_stesso_giorno_resta_nuovo():
    archivio = [_a("L1", "2026-07-10", 1.1, "uscita", "COMMISSIONI")]
    api = [_b("2026-07-10", 1.1, "uscita", "COMMISSIONI"),
           _b("2026-07-10", 1.1, "uscita", "COMMISSIONI")]
    esito = eb.confronta_con_archivio(api, archivio)
    assert len(esito["gia_presenti"]) == 1 and len(esito["nuovi"]) == 1


def test_riferimenti_della_banca_diversi_restano_da_verificare():
    archivio = [_a("L1", "2026-07-10", 500.0, "uscita", "BONIFICO RIF. MB0B11111111/90000001 ROSSI")]
    api = [_b("2026-07-10", 500.0, "uscita", "BONIFICO RIF. MB0B22222222/90000002 BIANCHI")]
    esito = eb.confronta_con_archivio(api, archivio)
    assert len(esito["da_verificare"]) == 1 and esito["gia_presenti"] == []


# ── rilettura da una data (archivio azzerato il 06/10/2026) e finestra ordinaria

def test_giro_automatico_rilegge_dalla_data_chiesta_una_volta_sola(monkeypatch):
    import datetime as _dt

    db = AsyncMongoMockClient()["t"]
    banca = Banca()
    run(eb.avvia_collegamento(db, banca))
    run(eb.completa_collegamento(db, banca, code="c", state=banca.state))
    oggi = _dt.date.today()
    banca.pagine = [[_tx(oggi.isoformat(), "5.00", False, "ACCREDITO", ref="RIF1")]]
    run(eb.giro_automatico(db, banca))            # primo giro: 90 giorni

    dal = (oggi - _dt.timedelta(days=200)).isoformat()
    monkeypatch.setenv("ENABLE_BANKING_DAL", dal)
    rilettura = run(eb.giro_automatico(db, banca))
    assert rilettura["giorni"] == 201 and rilettura["rilettura_dal"] == dal
    assert banca.chiamate[-1][2]["date_from"] <= dal   # la finestra copre la data chiesta
    assert run(eb.leggi_sessione(db))["rilettura_dal"] == dal

    # Stessa data chiesta ancora: non si rilegge, torna la finestra ordinaria.
    ordinario = run(eb.giro_automatico(db, banca))
    assert ordinario["giorni"] == eb.GIORNI_GIRO and "rilettura_dal" not in ordinario

    # Il giro «subito dopo l'avvio» a rilettura gia' fatta non chiama la banca:
    # ogni riavvio consumava una lettura PSD2 e i giri del mattino finivano in limite_banca.
    chiamate = len(banca.chiamate)
    salto = run(eb.giro_di_rilettura(db, banca))
    assert salto["saltato"] == "rilettura_gia_eseguita" and salto["eseguita_il"] == dal
    assert len(banca.chiamate) == chiamate
    # con una nuova data chiesta invece rilegge
    nuova = (oggi - _dt.timedelta(days=30)).isoformat()
    monkeypatch.setenv("ENABLE_BANKING_DAL", nuova)
    assert run(eb.giro_di_rilettura(db, banca))["rilettura_dal"] == nuova


def test_finestra_ordinaria_da_variabile_e_data_non_valida(monkeypatch):
    monkeypatch.delenv("ENABLE_BANKING_GIORNI_GIRO", raising=False)
    assert eb.giorni_giro() == eb.GIORNI_GIRO == 3
    monkeypatch.setenv("ENABLE_BANKING_GIORNI_GIRO", "14")
    assert eb.giorni_giro() == 14
    monkeypatch.setenv("ENABLE_BANKING_GIORNI_GIRO", "x")
    assert eb.giorni_giro() == eb.GIORNI_GIRO
    monkeypatch.setenv("ENABLE_BANKING_DAL", "01/01/2026")
    assert eb.rilettura_dal() is None
    monkeypatch.setenv("ENABLE_BANKING_DAL", "2026-01-01")
    assert eb.rilettura_dal() == "2026-01-01"
    assert eb.rilettura_in_attesa({"rilettura_dal": "2026-01-01"}) is None
    assert eb.rilettura_in_attesa({}) == "2026-01-01"


def test_rilettura_non_segnata_se_la_banca_rifiuta(monkeypatch):
    db = AsyncMongoMockClient()["t"]
    banca = Banca()
    run(eb.avvia_collegamento(db, banca))
    run(eb.completa_collegamento(db, banca, code="c", state=banca.state))
    monkeypatch.setenv("ENABLE_BANKING_DAL", "2026-01-01")
    banca.errori = [httpx.Response(429, json={"error": "ASPSP_RATE_LIMIT_EXCEEDED"})]
    esito = run(eb.giro_automatico(db, banca))
    assert esito["errore"] == "limite_banca" and esito["rilettura_dal"] == "2026-01-01"
    assert run(eb.leggi_sessione(db))["rilettura_dal"] is None   # si riprova al prossimo giro
