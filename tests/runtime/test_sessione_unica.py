"""Guardia: il PIN si inserisce per entrare, non a ogni sezione.

Le quattro app girano nello stesso servizio, ma i token li firmavano con due
segreti diversi: `settings.SECRET_KEY` (ERP e HR) e quello di Lotti. Un token
valido di qua non valeva di la', quindi lo stesso operatore, sullo stesso
tablet, doveva rifare il PIN per passare dal magazzino al portale dipendenti.

La verifica ora e' una sola e prova entrambi i segreti. Quello che NON deve
cambiare, ed e' il motivo di questa guardia: un token scaduto o manomesso
resta rifiutato, e nessuno guadagna un ruolo passando da un'app all'altra.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.services.workforce_tokens import create_workforce_token, normalizza, verifica_token_condiviso

ALG = "HS256"


def _token(segreto: str, **campi) -> str:
    adesso = datetime.now(timezone.utc)
    payload = {"sub": "hr-7", "iat": adesso, "exp": adesso + timedelta(hours=2)}
    payload.update(campi)
    return jwt.encode(payload, segreto, algorithm=ALG)


@pytest.fixture
def segreti(monkeypatch):
    """I due segreti veri delle due app, tenuti distinti come in produzione."""
    monkeypatch.setenv("LOTTI_AUTH_SECRET", "segreto-del-magazzino-0123456789")
    from app.hr.config import settings as impostazioni_hr

    monkeypatch.setattr(impostazioni_hr, "SECRET_KEY", "segreto-del-portale-9876543210")
    import app.lotti.auth as auth_lotti

    monkeypatch.setattr(auth_lotti, "_RUNTIME_SECRET", None, raising=False)
    return "segreto-del-magazzino-0123456789", "segreto-del-portale-9876543210"


def test_il_token_del_magazzino_vale_anche_nel_portale(segreti):
    lotti, _gestionale = segreti

    dati = verifica_token_condiviso(
        _token(lotti, nome="Pocci Salvatore", ruolo="operatore", via="pin")
    )

    assert dati is not None, (
        "Il token del tablet non e' riconosciuto: l'operatore deve rifare il "
        "PIN per passare dal magazzino al portale."
    )
    assert dati["sub"] == "hr-7"
    assert dati["nome"] == "Pocci Salvatore"


def test_il_token_del_portale_vale_anche_nel_magazzino(segreti):
    _lotti, portale = segreti

    dati = verifica_token_condiviso(
        _token(portale, name="Pocci Salvatore", role="dipendente", tipo="dipendente")
    )

    assert dati is not None
    assert dati["nome"] == "Pocci Salvatore"


def test_un_token_scaduto_resta_rifiutato(segreti):
    lotti, _portale = segreti
    ieri = datetime.now(timezone.utc) - timedelta(days=1)
    scaduto = jwt.encode(
        {"sub": "hr-7", "exp": ieri, "iat": ieri - timedelta(hours=1)}, lotti, algorithm=ALG
    )

    assert verifica_token_condiviso(scaduto) is None, (
        "Provare un segreto in piu' non deve abbassare la verifica."
    )


def test_un_token_firmato_con_un_segreto_estraneo_resta_rifiutato(segreti):
    assert verifica_token_condiviso(_token("segreto-di-nessuno-000000000000")) is None


CASI_NON_TOKEN = ["", "   ", "non-un-token", "a.b.c"]


@pytest.mark.parametrize("valore", CASI_NON_TOKEN)
def test_le_stringhe_che_non_sono_token(segreti, valore):
    assert verifica_token_condiviso(valore) is None


def test_ogni_app_trova_il_proprio_vocabolario():
    """La traduzione e' direzionale, una per app.

    Tradurla nei due sensi sullo stesso campo faceva diventare `dipendente`
    un `operatore` anche per HR, che rifiutava il proprio token con
    «unknown user role»: il portale non si apriva piu' a nessuno.
    """
    da_lotti = normalizza({"ruolo": "operatore"})
    assert da_lotti["ruolo"] == "operatore"   # come lo legge Lotti
    assert da_lotti["role"] == "dipendente"   # come lo valida HR

    da_hr = normalizza({"role": "dipendente"})
    assert da_hr["role"] == "dipendente"
    assert da_hr["ruolo"] == "operatore"


def test_nessuno_diventa_amministratore_passando_da_un_app_all_altra():
    assert normalizza({"ruolo": "admin"})["role"] == "admin"
    assert normalizza({"role": "admin"})["ruolo"] == "admin"
    # Un ruolo inventato non diventa nessuno dei ruoli noti.
    assert normalizza({"ruolo": "capo_supremo"})["role"] == "capo_supremo"
    assert normalizza({"ruolo": "capo_supremo"})["ruolo"] == "capo_supremo"


def test_l_identita_ha_i_nomi_di_campo_di_tutte_e_due_le_app():
    """Chi legge il token trova il suo campo senza sapere chi l'ha emesso."""
    dati = normalizza({"sub": "hr-7", "nome": "Tizio", "ruolo": "operatore", "via": "pin"})

    assert dati["nome"] == dati["name"] == "Tizio"
    assert dati["ruolo"] == "operatore" and dati["role"] == "dipendente"
    assert dati["via"] == "pin"


def test_lotti_usa_la_verifica_condivisa(segreti):
    """Il controllo sul comportamento, non sul testo: un token del gestionale
    deve passare da `verify_token` di Lotti."""
    _lotti, portale = segreti
    from app.lotti.auth import verify_token

    assert verify_token(_token(portale, name="Tizio", role="dipendente")) is not None


def test_la_contabilita_resta_fuori_dalla_sessione_condivisa(monkeypatch):
    """Il PIN unico vale fra magazzino e portale, non apre l'ERP.

    `app/utils/ruoli.py` stabilisce che un token del portale dipendenti non
    vale mai sulle rotte del gestionale, e HR tiene apposta un segreto suo.
    Togliere il doppio PIN di reparto non deve diventare una porta sulla
    contabilita'.
    """
    from app.config import settings as impostazioni_erp
    from app.hr.config import settings as impostazioni_hr

    monkeypatch.setenv("LOTTI_AUTH_SECRET", "segreto-del-magazzino-0123456789")
    monkeypatch.setattr(impostazioni_hr, "SECRET_KEY", "segreto-del-portale-9876543210")
    monkeypatch.setattr(impostazioni_erp, "SECRET_KEY", "segreto-della-contabilita-55555")
    import app.lotti.auth as auth_lotti

    monkeypatch.setattr(auth_lotti, "_RUNTIME_SECRET", None, raising=False)

    token_erp = _token("segreto-della-contabilita-55555", name="Admin", role="admin")

    assert verifica_token_condiviso(token_erp) is None, (
        "Un token del gestionale contabile apre magazzino e portale: "
        "la separazione voluta e' saltata."
    )


CASI_SENZA_RUOLO = [
    ("nessun campo ruolo", {}),
    ("ruolo vuoto", {"ruolo": ""}),
    ("role vuoto", {"role": "   "}),
]


@pytest.mark.parametrize("caso,payload", CASI_SENZA_RUOLO, ids=[c[0] for c in CASI_SENZA_RUOLO])
def test_un_token_senza_ruolo_non_ne_riceve_uno_di_ripiego(caso, payload):
    """Fallisce chiuso.

    Mettere «dipendente» per comodita' quando il ruolo manca e' il difetto che
    HR si era gia' corretto: un token senza ruolo diventava l'utente generico
    e passava. La normalizzazione non deve reintrodurlo dalla porta di
    servizio.
    """
    dati = normalizza(payload)

    assert dati["ruolo"] == "" and dati["role"] == "", (
        f"{caso}: il token ha ricevuto il ruolo «{dati['role']}» che non aveva."
    )


def test_emettitore_canonico_produce_payload_leggibile_da_hr_e_lotti(segreti):
    lotti, portale = segreti
    token = create_workforce_token(
        sub="hr-7",
        name="Pocci Salvatore",
        role="dipendente",
        secret=portale,
        expires_in=timedelta(hours=2),
        auth_method="pin_dipendente",
    )
    dati = verifica_token_condiviso(token)
    assert dati is not None
    assert dati["sub"] == "hr-7"
    assert dati["name"] == dati["nome"] == "Pocci Salvatore"
    assert dati["role"] == "dipendente"
    assert dati["ruolo"] == "operatore"
    assert dati["via"] == "pin_dipendente"


def test_emettitore_canonico_non_promuove_ruoli_sconosciuti(segreti):
    _lotti, portale = segreti
    token = create_workforce_token(
        sub="x",
        name="X",
        role="capo_supremo",
        secret=portale,
        expires_in=timedelta(hours=1),
        auth_method="test",
    )
    dati = verifica_token_condiviso(token)
    assert dati["role"] == "capo_supremo"
    assert dati["ruolo"] == "capo_supremo"


def test_emettitore_canonico_non_accetta_segreto_vuoto():
    with pytest.raises(ValueError):
        create_workforce_token(
            sub="x",
            name="X",
            role="dipendente",
            secret="",
            expires_in=timedelta(minutes=5),
            auth_method="test",
        )
