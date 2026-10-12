import asyncio
from copy import deepcopy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers.invoices import fatture_upload as fu
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.utils.dependencies import get_current_admin_user, get_current_user

def run(coro):
    return asyncio.run(coro)

def setup(monkeypatch, **extra):
    db = ClientArchivioMemoria()['contesto-fiscale-test']
    f = {'id': 123, 'supplier_id': 's1', 'supplier_vat': '00488410010',
         'supplier_name': 'Telecom Italia S.p.A.', 'invoice_date': '2026-09-30',
         'iva': 22.0, 'imponibile': 100.0, 'centro_costo_id': '10.1_TELEFONIA',
         'classificazioni_righe': [{'centro_costo_id': '10.1_TELEFONIA', 'richiede_verifica': False}],
         'linee': [{'descrizione': 'Canone telefonia internet fibra', 'prezzo_totale': 100, 'aliquota_iva': 22}],
         'stato_detrazione_iva': 'DA_VERIFICARE', **extra}
    run(db['invoices'].insert_one(f))
    run(db['fornitori'].insert_one({'id': 's1', 'partita_iva': '00488410010', 'profilo_fiscale': {
        'partita_iva': '00488410010', 'identita_verificata': True, 'stato': 'verificato',
        'regola_iva': 'telefonia', 'centri_costo_ammessi': ['10.1_TELEFONIA'],
        'validita_fiscale': {'dal': '2026-01-01', 'al': '2026-12-31'},
        'fonti': [{'url': 'https://www.tim.it/', 'tipo': 'primaria', 'verificata_il': '2026-10-12',
                   'evidenza': 'PIVA00488410010 e telecomunicazioni'}]}}))
    monkeypatch.setattr(fu.Database, 'get_db', staticmethod(lambda: db))
    return db

def client(ruolo='admin'):
    app = FastAPI()
    app.include_router(fu.router, prefix='/api/fatture')
    if ruolo == 'admin':
        app.dependency_overrides[get_current_admin_user] = lambda: {'role': 'admin', 'user_id': 'jwt-admin'}
    elif ruolo:
        app.dependency_overrides[get_current_user] = lambda: {'role': ruolo, 'user_id': 'jwt-operatore'}
    return TestClient(app)

def dati(**extra):
    return {'inerente': True, 'fonte_documento': 'Contratto linea locale aziendale',
            'validita_fiscale': {'dal': '2026-01-01', 'al': '2026-12-31'},
            'percentuale_utilizzo_aziendale': .75, 'pro_rata_applicabile': False, **extra}

def test_auth_admin(monkeypatch):
    db = setup(monkeypatch)
    for ruolo, status in [(None, 401), ('operatore', 403)]:
        assert client(ruolo).put('/api/fatture/123/contesto-fiscale-iva', json=dati()).status_code == status
    assert run(db['invoices'].find_one({'id': 123})).get('contesto_fiscale_iva') is None

def test_frazione_attore_jwt_audit_e_nessuna_scrittura(monkeypatch):
    db = setup(monkeypatch, classificazione_manuale=True, classificato_da='manuale', iva_detraibile=11)
    r = client().put('/api/fatture/123/contesto-fiscale-iva', json=dati())
    assert r.status_code == 200, r.text
    f = r.json()['fattura']
    assert f['iva_detraibile'] == 16.5 and f['percentuale_detraibilita_iva'] == .75
    assert f['stato_detrazione_iva'] == 'DA_INSERIRE'
    assert f['classificazione_manuale'] is True and f['classificato_da'] == 'manuale'
    assert f['contesto_fiscale_iva']['confermato_da'] == 'jwt-admin'
    assert f['storico_contesto_fiscale_iva'][0]['precedente']['iva_detraibile'] == 11
    for col in ['prima_nota_cassa', 'prima_nota_banca', 'movimenti_contabili', 'pagamenti']:
        assert run(db[col].count_documents({})) == 0

@pytest.mark.parametrize('variante', [
    {'confermato_da': 'forged'}, {'actor': 'forged'}, {'inerente': 'true'},
    {'fonte_documento': ''}, {'percentuale_utilizzo_aziendale': 75},
    {'percentuale_utilizzo_aziendale': True},
    {'validita_fiscale': {'dal': '2026-10-01', 'al': '2026-12-31'}},
    {'validita_fiscale': {'dal': '2026-02-30', 'al': '2026-12-31'}},
    {'validita_fiscale': {'dal': '2026-12-31', 'al': '2026-01-01'}},
    {'pro_rata_applicabile': False, 'pro_rata': .5},
    {'pro_rata_applicabile': True}, {'uso_veicolo': 'esclusivo'},
])
def test_invalido_non_modifica(monkeypatch, variante):
    db = setup(monkeypatch)
    prima = deepcopy(run(db['invoices'].find_one({'id': 123})))
    r = client().put('/api/fatture/123/contesto-fiscale-iva', json=dati(**variante))
    assert r.status_code == 422, r.text
    assert run(db['invoices'].find_one({'id': 123})) == prima

@pytest.mark.parametrize('protezione', [
    {'iva_utilizzata': True}, {'stato_detrazione_iva': 'INSERITA_IN_LIQUIDAZIONE'},
    {'stato_detrazione_iva': 'RECUPERATA_IN_DICHIARAZIONE_ANNUALE'},
])
def test_iva_utilizzata_protetta(monkeypatch, protezione):
    db = setup(monkeypatch, **protezione)
    prima = deepcopy(run(db['invoices'].find_one({'id': 123})))
    assert client().put('/api/fatture/123/contesto-fiscale-iva', json=dati()).status_code == 409
    assert run(db['invoices'].find_one({'id': 123})) == prima

def test_chiuso_protetto_anche_se_manuale(monkeypatch):
    db = setup(monkeypatch, classificazione_manuale=True, classificato_da='manuale', periodo_iva_attribuito='2026-09')
    run(db['liquidazioni_iva'].insert_one({'id': 'l1', 'periodo': '2026-09', 'stato': 'CHIUSA', 'versione': 1}))
    assert client().put('/api/fatture/123/contesto-fiscale-iva', json=dati()).status_code == 409
    assert run(db['invoices'].find_one({'id': 123})).get('contesto_fiscale_iva') is None

def test_pro_rata_preservato_e_applicato(monkeypatch):
    setup(monkeypatch, pro_rata_applicabile=True, pro_rata=.5)
    assert client().put('/api/fatture/123/contesto-fiscale-iva', json=dati()).status_code == 422
    r = client().put('/api/fatture/123/contesto-fiscale-iva', json=dati(pro_rata_applicabile=True, pro_rata=.5))
    assert r.status_code == 200, r.text
    assert r.json()['fattura']['iva_detraibile'] == 8.25

def test_zero_documentato_distinto_da_non_valutato(monkeypatch):
    setup(monkeypatch)
    r = client().put('/api/fatture/123/contesto-fiscale-iva', json=dati(inerente=False))
    assert r.status_code == 200
    assert r.json()['fattura']['iva_detraibile'] == 0
    assert r.json()['fattura']['percentuale_detraibilita_iva'] == 0
