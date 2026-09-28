import pytest

import scripts.sync_rt_to_drive as rt
from scripts.sync_rt_to_drive import _private_base_url


def test_accetta_indirizzo_lan_del_registratore():
    assert _private_base_url("http://192.168.1.19/www/dati-rt") == (
        "http://192.168.1.19/www/dati-rt/"
    )


@pytest.mark.parametrize("url", ["https://8.8.8.8/rt", "file:///tmp/rt", "https://example.com/rt"])
def test_rifiuta_destinazioni_non_private(url):
    with pytest.raises(ValueError):
        _private_base_url(url)


BASE = "http://192.168.1.19/www/dati-rt/"


def _registratore(monkeypatch, giornate):
    """Finto RT: {giorno: {nome_file: bytes}} servito come elenco di cartelle."""
    def links(url):
        if url == BASE:
            return [f"{BASE}{g}/" for g in giornate]
        g = url.rstrip("/").split("/")[-1]
        return [f"{url}{n}" for n in giornate[g]]

    def get(url):
        g, nome = url[len(BASE):].split("/")
        return giornate[g][nome]

    monkeypatch.setattr(rt, "_links", links)
    monkeypatch.setattr(rt, "_get", get)


def test_giornate_dal_giorno_dell_ultima_copia():
    days = [f"{BASE}{g}/" for g in ("20260826", "20260827", "20260828")]
    assert rt.giornate_da_leggere(days, None) == days
    assert rt.giornate_da_leggere(days, "20260827") == days[1:]
    assert rt.giornate_da_leggere(days, None, dal="20260828") == days[2:]


def test_pc_spento_recupera_le_giornate_perse(monkeypatch, tmp_path):
    monkeypatch.setenv("RT_SYNC_STATE_FILE", str(tmp_path / "stato.json"))
    inbox = tmp_path / "DA ELABORARE"
    giornate = {"20260827": {"CORRISP_1.xml": b"<a/>", "ESITO_1.xml": b"<e/>"}}
    _registratore(monkeypatch, giornate)
    assert rt.sync(BASE, inbox)["copiati"] == 1          # l'ESITO non si copia

    # il PC resta spento tre giorni: al giro dopo arrivano tutte
    giornate.update({"20260828": {"CORRISP_2.xml": b"<b/>"},
                     "20260829": {"CORRISP_3.xml": b"<c/>"},
                     "20260830": {"CORRISP_4.xml": b"<d/>"}})
    esito = rt.sync(BASE, inbox)
    assert esito["giornate"] == ["20260827", "20260828", "20260829", "20260830"]
    assert esito["copiati"] == 3 and esito["duplicati"] == 1
    assert sorted(p.name for p in inbox.iterdir()) == [
        "20260827_CORRISP_1.xml", "20260828_CORRISP_2.xml",
        "20260829_CORRISP_3.xml", "20260830_CORRISP_4.xml"]

    # il secondo giro senza novita' non copia nulla
    assert rt.sync(BASE, inbox)["copiati"] == 0
