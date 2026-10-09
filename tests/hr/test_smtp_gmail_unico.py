"""Un solo punto di invio email: SMTP_* su Render, altrimenti la password per le
app dell'account Gmail (stessi nomi e stessa precedenza della posta in ingresso).

La pagina Area Commercialista chiede a `email_smtp.credenziali_smtp` sia lo stato
(«SMTP configurato») sia l'invio: le due risposte non possono divergere.
"""
import pytest

from app.hr.services import email_smtp

VARIABILI = (
    "SMTP_HOST", "SMTP_PORT", "SMTP_EMAIL", "SMTP_USER", "SMTP_PASSWORD",
    "PEC_HOST", "PEC_PORT", "PEC_USER", "PEC_PASSWORD",
    "GMAIL_RELAY_URL", "GMAIL_RELAY_SECRET",
)


@pytest.fixture(autouse=True)
def _ambiente_pulito(monkeypatch):
    from app.config import settings
    for nome in VARIABILI:
        monkeypatch.delenv(nome, raising=False)
    for campo in ("IMAP_USER", "EMAIL_USER", "EMAIL_ADDRESS", "GMAIL_EMAIL",
                  "GMAIL_ACCOUNT_AMMINISTRATIVO", "ADMIN_EMAIL", "IMAP_PASSWORD",
                  "EMAIL_APP_PASSWORD", "EMAIL_PASSWORD", "GMAIL_APP_PASSWORD",
                  "GMAIL_APP_PASSWORD_AMMINISTRATIVO"):
        monkeypatch.setattr(settings, campo, None, raising=False)
    return settings


def test_senza_niente_smtp_non_e_configurato():
    assert email_smtp.credenziali_smtp() is None


def test_smtp_esplicito_vince(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.esempio.it")
    monkeypatch.setenv("SMTP_USER", "invio@esempio.it")
    monkeypatch.setenv("SMTP_PASSWORD", "segreto")
    cred = email_smtp.credenziali_smtp()
    assert cred == {"host": "smtp.esempio.it", "port": 465, "user": "invio@esempio.it", "password": "segreto"}


def test_la_password_per_le_app_di_gmail_basta(_ambiente_pulito):
    """Stesso account della posta in ingresso: nessuna variabile SMTP in piu',
    e gli spazi della password copiata da Google si tolgono."""
    _ambiente_pulito.GMAIL_EMAIL = "posta@esempio.it"
    _ambiente_pulito.GMAIL_APP_PASSWORD = "abcd efgh ijkl mnop"
    cred = email_smtp.credenziali_smtp()
    assert cred == {"host": "smtp.gmail.com", "port": 465, "user": "posta@esempio.it",
                    "password": "abcdefghijklmnop"}


def test_i_nomi_alternativi_della_password_sono_gli_stessi_della_posta(_ambiente_pulito):
    _ambiente_pulito.EMAIL_USER = "posta@esempio.it"
    _ambiente_pulito.EMAIL_APP_PASSWORD = "wxyzwxyzwxyzwxyz"
    assert email_smtp.credenziali_smtp()["password"] == "wxyzwxyzwxyzwxyz"


def test_solo_l_utente_senza_password_non_e_configurato(_ambiente_pulito):
    _ambiente_pulito.GMAIL_EMAIL = "posta@esempio.it"
    assert email_smtp.credenziali_smtp() is None


def test_stato_e_invio_dell_area_commercialista_rispondono_uguale(monkeypatch, _ambiente_pulito):
    from fastapi import HTTPException
    from app.routers import commercialista

    assert commercialista.smtp_configurato() is False
    with pytest.raises(HTTPException) as errore:
        commercialista.send_email_with_attachment("a@b.it", "Oggetto", "<p>x</p>", b"%PDF", "x.pdf")
    assert errore.value.status_code == 500

    _ambiente_pulito.GMAIL_EMAIL = "posta@esempio.it"
    _ambiente_pulito.GMAIL_APP_PASSWORD = "abcdabcdabcdabcd"
    assert commercialista.smtp_configurato() is True

    inviati = []
    monkeypatch.setattr(email_smtp, "_invia_via_smtp",
                        lambda cred, dest, ogg, corpo, allegati=None, html=False:
                        inviati.append((cred["user"], dest, ogg, html, [a[3] for a in allegati or []])))
    assert commercialista.send_email_with_attachment("a@b.it", "Oggetto", "<p>x</p>", b"%PDF", "x.pdf") is True
    assert inviati == [("posta@esempio.it", "a@b.it", "Oggetto", True, ["x.pdf"])]


def test_un_corpo_html_va_in_multipart(monkeypatch):
    """L'HTML non passa dal relay (che lo manderebbe come testo): serve SMTP."""
    monkeypatch.setenv("GMAIL_RELAY_URL", "https://relay.example")
    monkeypatch.setenv("GMAIL_RELAY_SECRET", "s")
    monkeypatch.setenv("SMTP_HOST", "smtp.esempio.it")
    monkeypatch.setenv("SMTP_USER", "u@esempio.it")
    monkeypatch.setenv("SMTP_PASSWORD", "p")
    chiamate = []
    monkeypatch.setattr(email_smtp, "_invia_via_smtp",
                        lambda cred, dest, ogg, corpo, allegati=None, html=False: chiamate.append(html))
    monkeypatch.setattr(email_smtp, "_invia_via_relay", lambda *a, **k: chiamate.append("relay"))
    email_smtp.invia_email("a@b.it", "Oggetto", "<b>x</b>", html=True)
    assert chiamate == [True]
