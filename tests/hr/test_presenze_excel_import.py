from openpyxl import Workbook

from app.hr.services.presenze_excel import analizza_presenze_workbook


def _workbook_base():
    wb = Workbook()
    riepilogo = wb.active
    riepilogo.title = "Riepilogo Consulente"
    riepilogo.append(["Dipendente", "Codice fiscale", "Festività NON lavorate (pagate)"])
    giornaliere = wb.create_sheet("Presenze Giornaliere")
    giornaliere.append(["Dipendente", "Data", "Entrata", "Tipo timbratura", "Note"])
    assenze = wb.create_sheet("Assenze, Ferie, Malattie")
    assenze.append(["Dipendente", "Tipo", "Dal", "Al", "Protocollo INPS", "Note"])
    return wb, riepilogo, giornaliere, assenze


def test_assenza_prevale_sulla_timbratura_e_fnl_non_viene_inventata():
    wb, riepilogo, giornaliere, assenze = _workbook_base()
    riepilogo.append(["Mario Esempio", "RSSMRA93L21F839G", 1])
    giornaliere.append(["Mario Esempio", "01/09/2026", "08:00", "QR in cassa", None])
    giornaliere.append(["Mario Esempio", "02/09/2026", "08:05", "QR in cassa", "timbratura interna"])
    assenze.append(["Mario Esempio", "Malattia", "02/09/2026", "03/09/2026", "P123", "certificata"])

    risultato = analizza_presenze_workbook(wb)

    assert risultato["periodo"] == "2026-09"
    assert risultato["conteggi"] == {"P": 1, "M": 2, "RS": 27}
    assert "FNL" not in risultato["conteggi"]
    sovrapposta = next(r for r in risultato["record"] if r["data"] == "2026-09-02")
    assert sovrapposta["giustificativo"] == "M"
    assert sovrapposta["entrata"] == "08:05"
    assert "Protocollo INPS: P123" in sovrapposta["note"]


def test_nominativo_giornaliero_fuori_riepilogo_resta_associabile_in_anteprima():
    wb, riepilogo, giornaliere, _assenze = _workbook_base()
    riepilogo.append(["Francesco Iazzetta", "ZZTFNC07A05F839D", 0])
    giornaliere.append(["Liliana Strazzullo", "01/09/2026", "08:00", "QR in cassa", None])

    risultato = analizza_presenze_workbook(wb)

    assert risultato["conteggi"] == {"P": 1, "RS": 29}
    assert risultato["nominativi_da_associare"] == ["Liliana Strazzullo"]
    assert risultato["record"][0]["codice_fiscale"] is None
    assert risultato["errori"][0]["motivo"].startswith("nominativo giornaliero assente")
