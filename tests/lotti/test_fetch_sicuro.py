"""Gli indirizzi che arrivano da fuori non aprono la rete interna (SSRF).

Scraper schede produttore, fonti catalogo e proxy PDF SAIMA passano tutti da
``app/lotti/servizi/fetch_sicuro.py``: qui si prova che rifiuta loopback,
reti private, metadati cloud, http, porte strane e reindirizzamenti verso
dentro, e che ``/schede-tecniche/scrape`` è riservato all'amministratore.
"""
import ast
import asyncio
from pathlib import Path

import httpx
import pytest

from app.lotti.servizi import fetch_sicuro as fs

RADICE = Path(__file__).resolve().parents[2]


def _risolvi_finto(mappa):
    def _risolvi(host):
        return mappa[host]
    return _risolvi


@pytest.mark.parametrize("url", [
    "http://esempio.it/",
    "https://127.0.0.1/",
    "https://10.0.0.5/",
    "https://192.168.1.1/",
    "https://169.254.169.254/latest/meta-data/",
    "https://[::1]/",
    "https://utente:pw@esempio.it/",
    "https://esempio.it:8080/",
    "ftp://esempio.it/",
    "",
])
def test_forma_rifiutata(url):
    with pytest.raises(fs.UrlNonAmmesso):
        fs.controlla_forma(url)


def test_host_che_risolve_in_rete_interna_rifiutato(monkeypatch):
    monkeypatch.setattr(fs, "_risolvi", _risolvi_finto({"interno.esempio.it": ["10.1.2.3"]}))
    with pytest.raises(fs.UrlNonAmmesso):
        asyncio.run(fs.valida_url("https://interno.esempio.it/"))


def test_host_misto_pubblico_privato_rifiutato(monkeypatch):
    monkeypatch.setattr(fs, "_risolvi", _risolvi_finto({"misto.it": ["93.184.216.34", "127.0.0.1"]}))
    with pytest.raises(fs.UrlNonAmmesso):
        asyncio.run(fs.valida_url("https://misto.it/"))


def test_dominio_fuori_lista_rifiutato():
    with pytest.raises(fs.UrlNonAmmesso):
        fs.controlla_forma("https://saimaspa.com.attacco.it/x.pdf", ("saimaspa.com",))
    assert fs.controlla_forma("https://www.saimaspa.com/x.pdf", ("saimaspa.com",)) == "www.saimaspa.com"


def test_reindirizzamento_verso_rete_interna_bloccato(monkeypatch):
    monkeypatch.setattr(fs, "_risolvi", _risolvi_finto({
        "pubblico.it": ["93.184.216.34"], "interno.it": ["192.168.0.10"],
    }))
    chiamate = []

    def handler(request):
        chiamate.append(str(request.url))
        if request.url.host == "pubblico.it":
            return httpx.Response(302, headers={"location": "https://interno.it/segreto"})
        return httpx.Response(200, content=b"segreto")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fs.scarica("https://pubblico.it/", client=client)

    with pytest.raises(fs.UrlNonAmmesso):
        asyncio.run(scenario())
    assert chiamate == ["https://pubblico.it/"]


def test_reindirizzamento_pubblico_seguito_e_tetto_dimensione(monkeypatch):
    monkeypatch.setattr(fs, "_risolvi", _risolvi_finto({"a.it": ["93.184.216.34"], "b.it": ["93.184.216.35"]}))

    def handler(request):
        if request.url.host == "a.it":
            return httpx.Response(301, headers={"location": "https://b.it/pagina"})
        return httpx.Response(200, content=b"x" * 50, headers={"content-type": "text/html"})

    async def scenario(max_bytes):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fs.scarica("https://a.it/", client=client, max_bytes=max_bytes)

    r = asyncio.run(scenario(1000))
    assert r.url == "https://b.it/pagina" and r.status_code == 200 and r.text == "x" * 50
    with pytest.raises(fs.UrlNonAmmesso):
        asyncio.run(scenario(10))


def _dipendenze(percorso: str, funzione: str) -> str:
    albero = ast.parse((RADICE / percorso).read_text(encoding="utf-8"))
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.AsyncFunctionDef) and nodo.name == funzione:
            return ast.unparse(nodo.args)
    raise AssertionError(f"{funzione} non trovata in {percorso}")


def test_scrape_riservato_admin():
    assert "require_admin" in _dipendenze("app/lotti/routers/schede_tecniche.py", "scrape_scheda")


def test_nessun_urlopen_ne_redirect_ciechi_nei_punti_con_url_esterni():
    for percorso in ("app/lotti/routers/schede_tecniche.py", "app/lotti/routers/fonti_catalogo.py"):
        testo = (RADICE / percorso).read_text(encoding="utf-8")
        assert "urlopen" not in testo, percorso
        assert "follow_redirects=True" not in testo, percorso
    testo = (RADICE / "app/lotti/routers/saima_ricettari.py").read_text(encoding="utf-8")
    inizio = testo.index("async def proxy_pdf")
    assert "follow_redirects=True" not in testo[inizio:testo.index("@router", inizio)]
