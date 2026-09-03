"""CSRF — stato reale del progetto: NON esiste un meccanismo a token CSRF
esplicito. L'unica protezione contro richieste cross-site che sfruttano il
cookie di sessione `access_token` è l'attributo SameSite=Lax (blocca l'invio
del cookie su richieste cross-site che non siano navigazione top-level GET,
quindi in particolare sulle POST/PUT/DELETE cross-site che modificano dati).

Questo file NON inventa una protezione che non c'è: verifica staticamente,
sul codice sorgente, che ogni punto che imposta il cookie di sessione lo
faccia con samesite="lax" e httponly=True — così una futura modifica che
indebolisse questa unica barriera (es. samesite="none", o la rimozione
dell'attributo) fa fallire il test invece di passare inosservata."""
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

# App esterne portate pari pari dentro il gestionale (Lotti, Menu, AppDipendenti):
# codice di QUELLE app, con la loro autenticazione (PIN/JWT propri, montate a
# /lotti, /menu, /hr fuori dal prefisso /api/ del gestionale). Il censimento
# riguarda il cookie di sessione dell'ERP, non il loro.
APP_PORTATE_PARI_PARI = {"lotti", "menu", "hr"}

# File noti che impostano il cookie "access_token" (censiti in questo test:
# se in futuro se ne aggiunge un altro, va aggiunto anche qui).
FILE_ATTESI = {
    "app/middleware/authentication.py",
    # Login password, PIN, MFA e step-up passano tutti dall'unico helper:
    # i flag di sicurezza del cookie non possono divergere tra i flussi.
    "app/utils/auth_tokens.py",
}


def _trova_set_cookie_access_token():
    """Trova ogni blocco set_cookie(...) che imposta key="access_token" in
    tutto app/, con gli argomenti passati (per verificarne i flag)."""
    trovati = []
    for p in APP.rglob("*.py"):
        if p.relative_to(APP).parts[0] in APP_PORTATE_PARI_PARI:
            continue
        testo = p.read_text(encoding="utf-8")
        for m in re.finditer(r"set_cookie\s*\((.*?)\)", testo, re.DOTALL):
            blocco = m.group(1)
            if 'key="access_token"' in blocco or "key='access_token'" in blocco:
                rel = p.relative_to(APP.parent).as_posix()
                trovati.append((rel, blocco))
    return trovati


def test_censimento_invariato():
    """Se questo elenco cambia, qualcuno ha aggiunto/rimosso un punto che
    imposta il cookie di sessione: va rivisto deliberatamente, non scoperto
    per caso in produzione."""
    trovati = {rel for rel, _ in _trova_set_cookie_access_token()}
    assert trovati == FILE_ATTESI, (
        f"Punti che impostano access_token cambiati.\n"
        f"Nuovi: {trovati - FILE_ATTESI}\nRimossi: {FILE_ATTESI - trovati}"
    )


def test_ogni_set_cookie_access_token_ha_samesite_lax():
    trovati = _trova_set_cookie_access_token()
    assert trovati, "nessun set_cookie(access_token) trovato: il censimento è vuoto?"
    for rel, blocco in trovati:
        assert re.search(r'samesite\s*=\s*["\']lax["\']', blocco, re.IGNORECASE), (
            f"{rel}: il cookie access_token non ha samesite=\"lax\" — "
            f"unica protezione CSRF attualmente presente, non deve sparire"
        )


def test_ogni_set_cookie_access_token_ha_httponly():
    trovati = _trova_set_cookie_access_token()
    for rel, blocco in trovati:
        assert re.search(r"httponly\s*=\s*True", blocco), (
            f"{rel}: il cookie access_token non ha httponly=True — "
            f"un token leggibile da JS è un rischio ulteriore (XSS→furto sessione)"
        )


def test_ogni_set_cookie_access_token_usa_flag_secure_canonico():
    trovati = _trova_set_cookie_access_token()
    for rel, blocco in trovati:
        assert re.search(r"secure\s*=\s*SESSION_COOKIE_SECURE", blocco), (
            f"{rel}: il cookie access_token non usa il flag Secure canonico"
        )


def test_flag_secure_attivo_su_render_e_produzione(monkeypatch):
    from app.utils.session_cookie import session_cookie_secure

    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert session_cookie_secure() is False
    monkeypatch.setenv("RENDER", "true")
    assert session_cookie_secure() is True
