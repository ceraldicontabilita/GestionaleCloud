"""Il payload di `fattura.created` si costruisce in un posto solo, e l'alert
sul metodo di pagamento riconosce la parola che il codice stesso scrive.

Due difetti trovati il 19/09/2026, entrambi silenziosi.

1. `fatture_upload.py` componeva il payload due volte a mano. Quella
   dell'upload manuale leggeva `supplier_result["nuovo"]`, chiave che
   `ensure_supplier_exists` non restituisce (torna `supplier_created`):
   `fornitore_nuovo` era sempre falso e `FORN_NUOVO_INCOMPLETO` non e' mai
   scattato per una fattura caricata a mano.
2. `on_fattura_created_alert_fornitore` considerava «non configurato» solo
   `("", "da_configurare", "none")`. Ma il valore che l'import scrive quando
   il fornitore non ha un metodo e' **`"sospesa"`**, e in produzione ce
   l'hanno 583 delle 873 fatture attive. Quel ramo non e' mai stato
   eseguito: zero righe `FORN_MP_MANCANTE` in archivio (i 590
   `FAT_MP_NON_DEFINITO` presenti vengono da un altro punto di emissione).
"""
import asyncio

import pytest

from app.constants.metodi_pagamento import metodo_non_configurato
from app.services.eventi_fattura import costruisci_evento_fattura_created
from app.services.handlers.fattura_handlers import on_fattura_created_alert_fornitore


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


FATTURA = {
    "id": "f-1",
    "invoice_number": "123/26",
    "invoice_date": "2026-03-14",
    "supplier_name": "ACME SRL",
    "supplier_vat": "IT01234567890",
    "tipo_documento": "TD01",
    "total_amount": 1220.0,
    "imponibile": 1000.0,
    "iva": 220.0,
    "fornitore": {"iban": "IT60X0542811101000000123456"},
}


# ── 1. Il costruttore unico ────────────────────────────────────────────────

def test_fornitore_nuovo_legge_la_chiave_che_ensure_supplier_exists_restituisce():
    evento = costruisci_evento_fattura_created(
        FATTURA, supplier_result={"supplier_id": "forn-1", "supplier_created": True}
    )

    assert evento["fornitore_nuovo"] is True, (
        "`ensure_supplier_exists` torna `supplier_created`, non `nuovo`. "
        "Leggere la chiave sbagliata non da' errore: da' sempre False, e "
        "l'alert FORN_NUOVO_INCOMPLETO non scatta mai."
    )
    assert evento["fornitore_id"] == "forn-1"


def test_la_chiave_nuovo_non_e_piu_usata_da_nessuna_parte():
    """La controprova strutturale: se qualcuno la rimette, questo fallisce."""
    from pathlib import Path

    sorgente = (
        Path(__file__).resolve().parents[2]
        / "app" / "routers" / "invoices" / "fatture_upload.py"
    ).read_text(encoding="utf-8")
    assert 'supplier_result.get("nuovo"' not in sorgente


def test_un_fornitore_gia_esistente_non_e_nuovo():
    evento = costruisci_evento_fattura_created(
        FATTURA, supplier_result={"supplier_id": "forn-1", "supplier_created": False}
    )
    assert evento["fornitore_nuovo"] is False


def test_la_data_del_documento_e_invoice_date():
    """`data_documento` la deriva il motore IVA: su una fattura appena
    importata non c'e' ancora."""
    assert costruisci_evento_fattura_created(FATTURA)["data_documento"] == "2026-03-14"


def test_le_rate_non_portano_iban_ne_beneficiario():
    fattura = dict(FATTURA, pagamento_rate=[
        {"importo": 610.0, "data_scadenza": "2026-04-30",
         "iban": "IT60X0542811101000000123456", "beneficiario": "ACME SRL"},
    ])
    rata = costruisci_evento_fattura_created(fattura)["pagamento_rate"][0]

    assert rata["importo"] == 610.0
    assert "iban" not in rata and "beneficiario" not in rata


def test_i_parametri_espliciti_vincono_su_quanto_e_scritto_sulla_fattura():
    """All'import metodo e scadenza sono appena stati calcolati e possono non
    essere ancora salvati sulla fattura."""
    fattura = dict(FATTURA, metodo_pagamento="sospesa", data_scadenza="2026-04-01")
    evento = costruisci_evento_fattura_created(
        fattura, metodo_pagamento="bonifico", data_scadenza="2026-05-31"
    )

    assert evento["metodo_pagamento"] == "bonifico"
    assert evento["data_scadenza"] == "2026-05-31"


# ── 2. «Metodo di pagamento non configurato» ──────────────────────────────

@pytest.mark.parametrize("valore", [
    None, "", "  ", "sospesa", "SOSPESA", " Sospesa ", "da_configurare", "none", "null",
])
def test_questi_valori_significano_non_configurato(valore):
    assert metodo_non_configurato(valore) is True


@pytest.mark.parametrize("valore", ["bonifico", "Bonifico", "SDD/RID", "PayPal", "contanti"])
def test_un_metodo_vero_non_e_non_configurato(valore):
    assert metodo_non_configurato(valore) is False


class _CollezioneAlert:
    def __init__(self):
        self.scritti = []

    async def find_one(self, *a, **k):
        return None

    async def insert_one(self, doc):
        self.scritti.append(doc)
        return doc


class _Db:
    def __init__(self):
        self.alerts = _CollezioneAlert()

    def __getitem__(self, nome):
        return self.alerts


def _codici_emessi(metodo, iban="IT60X0542811101000000123456"):
    db = _Db()
    _run(on_fattura_created_alert_fornitore({
        "fattura_id": "f-1",
        "fornitore_id": "forn-1",
        "fornitore_ragione_sociale": "ACME SRL",
        "metodo_pagamento": metodo,
        "fornitore_iban": iban,
    }, db))
    return [a["codice"] for a in db.alerts.scritti]


def test_sospesa_fa_scattare_gli_alert_sul_metodo_mancante():
    codici = _codici_emessi("sospesa")

    assert "FORN_MP_MANCANTE" in codici and "FAT_MP_NON_DEFINITO" in codici, (
        "«sospesa» e' esattamente il valore che l'import scrive quando il "
        "fornitore non ha un metodo di pagamento (583 fatture attive su 873 "
        "in produzione). Non riconoscerlo vuol dire non avvisare mai."
    )


def test_un_metodo_vero_con_iban_non_fa_scattare_nulla():
    assert _codici_emessi("bonifico") == []


def test_un_metodo_bancario_senza_iban_fa_scattare_solo_l_alert_iban():
    """Non deve trascinarsi dietro anche «metodo mancante»: il metodo c'e'."""
    assert _codici_emessi("bonifico", iban=None) == ["FORN_IBAN_MANCANTE"]
