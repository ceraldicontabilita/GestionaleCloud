"""Enable Banking in modalita' ombra: lettura, sessione cifrata, confronto
con l'archivio col motore dei doppioni. Nessuna scrittura di movimenti."""
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
    assert esito["conteggi"] == {"letti": 3, "nuovi": 1, "gia_presenti": 1, "da_verificare": 1}
    assert esito["nuovi"][0]["descrizione_originale"] == "ACCREDITO NUOVO"
    # stessa data e importo ma nessun riferimento comune: DA_VERIFICARE, non «gia' presente»
    assert esito["da_verificare"][0]["archivio_id"] == "b"
    assert run(db.estratto_conto_movimenti.count_documents({})) == prima


def test_flag_spento_per_default(monkeypatch):
    monkeypatch.delenv("ENABLE_BANKING_ENABLED")
    assert eb.attivo() is False


def test_rotte_riservate_all_admin_tranne_il_ritorno_dalla_banca():
    from app.middleware.authentication import PUBLIC_PATHS
    from app.routers.bank import enable_banking as router_eb
    from app.utils.ruoli import richiedi_admin

    per_percorso = {r.path: r for r in router_eb.router.routes}
    for percorso in ("/stato", "/collega", "/anteprima"):
        dipendenze = [d.call for d in per_percorso[percorso].dependant.dependencies]
        assert richiedi_admin in dipendenze, percorso
    assert "/api/banca/enable-banking/callback" in PUBLIC_PATHS
    assert not any(p.startswith("/api/banca/enable-banking/") and not p.endswith("/callback")
                   for p in PUBLIC_PATHS)
