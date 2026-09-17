import pytest

from scripts.sync_rt_to_drive import _private_base_url


def test_accetta_indirizzo_lan_del_registratore():
    assert _private_base_url("http://192.168.1.19/www/dati-rt") == (
        "http://192.168.1.19/www/dati-rt/"
    )


@pytest.mark.parametrize("url", ["https://8.8.8.8/rt", "file:///tmp/rt", "https://example.com/rt"])
def test_rifiuta_destinazioni_non_private(url):
    with pytest.raises(ValueError):
        _private_base_url(url)
