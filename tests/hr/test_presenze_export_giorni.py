import csv
import io

import fitz

from app.hr.routers.dipendenti_cloud import _csv_presenze, _pdf_presenze


def test_csv_consulente_e_rettangolare_e_mostra_tutti_i_giorni_di_settembre():
    testo = _csv_presenze(2026, 9, 31, [{"nome": "Rossi Mario", "celle": ["P", "RS"]}])
    assert testo.startswith("\ufeffsep=;\r\n")

    righe = list(csv.reader(io.StringIO(testo.removeprefix("\ufeff")).read().splitlines()[1:], delimiter=";"))
    assert righe[0] == ["Dipendente"] + [str(g) for g in range(1, 31)]
    assert len(righe[1]) == 31
    assert righe[1][:3] == ["Rossi Mario", "P", "RS"]


def test_csv_consulente_calcola_i_giorni_del_mese_senza_fidarsi_del_client():
    testo = _csv_presenze(2026, 2, 31, [{"nome": "Bianchi Anna", "celle": ["P"] * 31}])
    righe = list(csv.reader(io.StringIO(testo.removeprefix("\ufeff")).read().splitlines()[1:], delimiter=";"))
    assert righe[0][-1] == "28"
    assert len(righe[0]) == len(righe[1]) == 29


def test_pdf_consulente_contiene_la_griglia_giorno_per_giorno():
    contenuto = _pdf_presenze(2026, 9, 30, [{"nome": "Rossi Mario", "celle": ["P"] * 30}])
    with fitz.open(stream=contenuto, filetype="pdf") as documento:
        testo = "\n".join(pagina.get_text() for pagina in documento)

    assert "Presenze Settembre 2026" in testo
    assert "Dipendente" in testo and "Rossi Mario" in testo
    assert all(str(g) in testo for g in range(1, 31))
