import csv
from io import BytesIO
from urllib.error import HTTPError

from scripts.esporta_foto_ricette import INDICE, esporta, nome_file

PNG = b"\x89PNG-uno"


def _scarica(mappa):
    def scarica(url):
        if url not in mappa:
            raise HTTPError(url, 404, "Foto non trovata", {}, BytesIO(b""))
        return mappa[url], "image/png"
    return scarica


def test_nome_file_toglie_caratteri_vietati_e_distingue_gli_omonimi():
    a = nome_file({"id": "6ae4db7a-453b", "nome": 'Torta 1/2 "caprese"?'}, "image/png")
    b = nome_file({"id": "eca03150-6874", "nome": 'Torta 1/2 "caprese"?'}, "image/png")
    assert a == "Torta 1 2 caprese [6ae4db7a].png"
    assert a != b


def test_secondo_giro_non_riscrive_e_la_foto_mancante_resta_mancante(tmp_path):
    ricette = [
        {"id": "r1", "nome": "Amaretti", "foto_url": "/api/foto/a?v=1"},
        {"id": "r2", "nome": "Babà", "foto_url": "/api/foto/rotta?v=1"},
        {"id": "r3", "nome": "Senza foto"},
    ]
    scarica = _scarica({"/api/foto/a?v=1": PNG})

    primo = esporta(ricette, scarica, tmp_path)
    assert (primo["nuove"], primo["mancanti"], primo["senza_foto"]) == (1, 1, 1)
    assert (tmp_path / "Amaretti [r1].png").read_bytes() == PNG

    secondo = esporta(ricette, scarica, tmp_path)
    assert (secondo["nuove"], secondo["invariate"]) == (0, 1)

    with open(tmp_path / INDICE, encoding="utf-8-sig") as fh:
        esiti = {r["ricetta_id"]: r["esito"] for r in csv.DictReader(fh, delimiter=";")}
    assert esiti == {"r1": "invariate", "r2": "mancante", "r3": "senza_foto"}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Amaretti [r1].png", INDICE]


def test_foto_cambiata_sostituisce_la_copia(tmp_path):
    ricetta = [{"id": "r1", "nome": "Amaretti", "foto_url": "/api/foto/a"}]
    esporta(ricetta, _scarica({"/api/foto/a": PNG}), tmp_path)
    esito = esporta(ricetta, _scarica({"/api/foto/a": b"\x89PNG-due"}), tmp_path)
    assert esito["aggiornate"] == 1
    assert (tmp_path / "Amaretti [r1].png").read_bytes() == b"\x89PNG-due"


def test_anteprima_non_scrive(tmp_path):
    dest = tmp_path / "RICETTE"
    esito = esporta([{"id": "r1", "nome": "A", "foto_url": "/f"}], _scarica({"/f": PNG}), dest, preview=True)
    assert esito["nuove"] == 1
    assert not dest.exists()


def test_un_errore_del_server_non_ferma_il_giro(tmp_path):
    def scarica(url):
        if url == "/rotta":
            raise HTTPError(url, 500, "errore", {}, BytesIO(b""))
        return PNG, "image/png"
    ricette = [{"id": "r1", "nome": "A", "foto_url": "/rotta"}, {"id": "r2", "nome": "B", "foto_url": "/ok"}]
    esito = esporta(ricette, scarica, tmp_path)
    assert (esito["errori"], esito["nuove"]) == (1, 1)
